from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from despues_del_susto.config import Settings
from despues_del_susto.db import (
    Candidate,
    Episode,
    Recommendation,
    Work,
    ensure_schema,
    session_scope,
)
from despues_del_susto.providers.base import ProviderError
from despues_del_susto.providers.models import Candidate as ProviderCandidate
from despues_del_susto.steps import StopBatch
from despues_del_susto.steps import enrich as enrich_module

MOVIE = ProviderCandidate(
    source="TMDB",
    type="movie",
    external_id="1",
    title="Hotel Transylvania",
    original_title="Hotel Transylvania",
    year=2012,
    image_url="https://image.test/poster.jpg",
    description="A hotel for monsters.",
    source_url="https://www.themoviedb.org/movie/1",
    genres=("Animation", "Comedy"),
    popularity=10.0,
)

GAME = ProviderCandidate(
    source="IGDB",
    type="videogame",
    external_id="2",
    title="Devil May Cry",
    original_title=None,
    year=2001,
    image_url=None,
    description="A game.",
    source_url="https://www.igdb.com/games/devil-may-cry",
    genres=("Hack and slash",),
    popularity=90.0,
)


class FakeTmdb:
    def __init__(self, *args) -> None:
        self.candidates = [MOVIE]

    def search(self, query, media_type, *, language=None, year=None):
        if media_type != "movie":
            return []
        return list(self.candidates)

    def details(self, media_type, external_id):
        return MOVIE


class FakeIgdb:
    def __init__(self, *args) -> None:
        pass

    def search(self, query, *, year=None, max_results=10):
        return [GAME]


class FailingTmdb:
    def __init__(self, *args) -> None:
        pass

    def search(self, query, media_type, *, language=None, year=None):
        raise ProviderError("rate limited", status_code=429)

    def details(self, media_type, external_id):
        raise ProviderError("rate limited", status_code=429)


def _episode(
    settings: Settings,
    recommendations: list[tuple[str, str, str, str]],
    *,
    confidence: str = "high",
) -> int:
    ensure_schema(settings)
    with session_scope(settings) as session:
        episode = Episode(video_id="abc", title="Episode")
        session.add(episode)
        session.flush()
        for type_, role, mentioned, probable in recommendations:
            session.add(
                Recommendation(
                    episode_id=episode.id,
                    type=type_,
                    role=role,
                    state="extracted",
                    mentioned_title=mentioned,
                    probable_title=probable,
                    confidence=confidence,
                    decided_by="automatic",
                )
            )
        session.commit()
        return episode.id


def _run(settings: Settings, episode_id: int) -> None:
    enrich_module.run(
        SimpleNamespace(id=episode_id, video_id="abc"), settings
    )


def test_run_confirms_movies_and_games(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    episode_id = _episode(
        settings,
        [
            ("movie", "primary", "Hotel Transilvania", "Hotel Transilvania"),
            ("videogame", "primary", "Devil May Cry", "Devil May Cry"),
        ],
    )
    monkeypatch.setattr(enrich_module, "TmdbClient", FakeTmdb)
    monkeypatch.setattr(enrich_module, "IgdbClient", FakeIgdb)

    _run(settings, episode_id)

    with session_scope(settings) as session:
        recommendations = list(
            session.scalars(select(Recommendation).order_by(Recommendation.id))
        )
        works = list(session.scalars(select(Work)))
        candidates = list(session.scalars(select(Candidate)))

    assert [item.state for item in recommendations] == ["confirmed", "confirmed"]
    assert all(item.work_id is not None for item in recommendations)
    assert len(works) == 2
    assert {work.source for work in works} == {"TMDB", "IGDB"}
    assert len(candidates) == 2
    assert all(candidate.chosen for candidate in candidates)
    assert recommendations[0].match_score is not None
    assert recommendations[0].match_score > 0.85


def test_run_sends_a_weak_match_to_review(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    episode_id = _episode(
        settings,
        [("movie", "primary", "Madre Siniestra", "Madre Siniestra")],
    )

    coraline = ProviderCandidate(
        source="TMDB",
        type="movie",
        external_id="3",
        title="Coraline",
        original_title="Coraline",
        year=2009,
        image_url=None,
        description=None,
        source_url=None,
    )

    class WeakTmdb(FakeTmdb):
        def __init__(self, *args) -> None:
            self.candidates = [coraline]

    monkeypatch.setattr(enrich_module, "TmdbClient", WeakTmdb)
    monkeypatch.setattr(enrich_module, "IgdbClient", FakeIgdb)

    _run(settings, episode_id)

    with session_scope(settings) as session:
        recommendation = session.scalar(select(Recommendation))
        candidates = list(session.scalars(select(Candidate)))
        works = list(session.scalars(select(Work)))

    assert recommendation is not None
    assert recommendation.state == "needs_review"
    assert recommendation.match_note == "below_threshold"
    assert recommendation.work_id is None
    assert len(candidates) == 1
    assert candidates[0].chosen is False
    assert works == []


def test_run_sends_an_uncertain_title_to_review(
    monkeypatch, tmp_path: Path
) -> None:
    settings = Settings(data_dir=tmp_path)
    episode_id = _episode(
        settings,
        [("movie", "primary", "Other Mother", "Madre Siniestra")],
        confidence="medium",
    )

    other = ProviderCandidate(
        source="TMDB",
        type="movie",
        external_id="9",
        title="Madre siniestra",
        original_title="Madre siniestra",
        year=2026,
        image_url=None,
        description=None,
        source_url=None,
    )

    class OtherTmdb(FakeTmdb):
        def __init__(self, *args) -> None:
            self.candidates = [other]

    monkeypatch.setattr(enrich_module, "TmdbClient", OtherTmdb)
    monkeypatch.setattr(enrich_module, "IgdbClient", FakeIgdb)

    _run(settings, episode_id)

    with session_scope(settings) as session:
        recommendation = session.scalar(select(Recommendation))

    assert recommendation is not None
    assert recommendation.state == "needs_review"
    assert recommendation.match_note == "uncertain_title"
    assert recommendation.work_id is None


def test_run_removes_orphan_works_on_replay(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    episode_id = _episode(
        settings,
        [("movie", "primary", "Hotel Transilvania", "Hotel Transilvania")],
    )
    monkeypatch.setattr(enrich_module, "TmdbClient", FakeTmdb)
    monkeypatch.setattr(enrich_module, "IgdbClient", FakeIgdb)

    _run(settings, episode_id)
    with session_scope(settings) as session:
        assert len(list(session.scalars(select(Work)))) == 1

    coraline = ProviderCandidate(
        source="TMDB",
        type="movie",
        external_id="3",
        title="Coraline",
        original_title="Coraline",
        year=2009,
        image_url=None,
        description=None,
        source_url=None,
    )

    class WeakTmdb(FakeTmdb):
        def __init__(self, *args) -> None:
            self.candidates = [coraline]

    monkeypatch.setattr(enrich_module, "TmdbClient", WeakTmdb)
    _run(settings, episode_id)

    with session_scope(settings) as session:
        recommendation = session.scalar(select(Recommendation))
        works = list(session.scalars(select(Work)))

    assert recommendation is not None
    assert recommendation.state == "needs_review"
    assert works == []


def test_run_marks_books_as_manual(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    episode_id = _episode(
        settings,
        [("book", "additional", "El libro", "El libro")],
    )
    monkeypatch.setattr(enrich_module, "TmdbClient", FakeTmdb)
    monkeypatch.setattr(enrich_module, "IgdbClient", FakeIgdb)

    _run(settings, episode_id)

    with session_scope(settings) as session:
        recommendation = session.scalar(select(Recommendation))

    assert recommendation is not None
    assert recommendation.state == "manual_pending"
    assert recommendation.match_note == "manual_source"
    assert recommendation.work_id is None


def test_run_reuses_a_work_across_episodes(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    first = _episode(
        settings, [("movie", "primary", "Hotel Transilvania", "Hotel Transilvania")]
    )
    with session_scope(settings) as session:
        second_episode = Episode(video_id="def", title="Other")
        session.add(second_episode)
        session.flush()
        session.add(
            Recommendation(
                episode_id=second_episode.id,
                type="movie",
                role="primary",
                state="extracted",
                mentioned_title="Hotel Transilvania",
                probable_title="Hotel Transilvania",
                confidence="high",
                decided_by="automatic",
            )
        )
        session.commit()
        second = second_episode.id

    monkeypatch.setattr(enrich_module, "TmdbClient", FakeTmdb)
    monkeypatch.setattr(enrich_module, "IgdbClient", FakeIgdb)

    _run(settings, first)
    _run(settings, second)

    with session_scope(settings) as session:
        works = list(session.scalars(select(Work)))
        recommendations = list(session.scalars(select(Recommendation)))

    assert len(works) == 1
    assert {item.work_id for item in recommendations} == {works[0].id}


def test_run_stops_the_batch_on_a_rate_limit(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    episode_id = _episode(
        settings, [("movie", "primary", "Hotel Transilvania", "Hotel Transilvania")]
    )
    monkeypatch.setattr(enrich_module, "TmdbClient", FailingTmdb)
    monkeypatch.setattr(enrich_module, "IgdbClient", FakeIgdb)

    with pytest.raises(StopBatch, match="rate limit"):
        _run(settings, episode_id)
