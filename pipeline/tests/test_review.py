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
from despues_del_susto.providers.models import Candidate as ProviderCandidate
from despues_del_susto.services import review as review_module
from despues_del_susto.services.matching import ScoredCandidate, score_candidates
from despues_del_susto.services.review import (
    ReviewError,
    discard,
    list_cases,
    resolve_candidate,
    resolve_manual,
    search_alternatives,
    status_summary,
)


def _settings(tmp_path: Path) -> Settings:
    settings = Settings(data_dir=tmp_path)
    ensure_schema(settings)
    return settings


def _episode(settings: Settings, video_id: str = "abc") -> int:
    with session_scope(settings) as session:
        episode = Episode(video_id=video_id, title=f"Episode {video_id}")
        session.add(episode)
        session.commit()
        return episode.id


def _recommendation(
    settings: Settings,
    episode_id: int,
    *,
    type_: str = "movie",
    state: str = "needs_review",
    mentioned: str = "Lights Out",
    probable: str = "Lights Out",
    confidence: str = "medium",
) -> int:
    with session_scope(settings) as session:
        recommendation = Recommendation(
            episode_id=episode_id,
            type=type_,
            role="primary",
            state=state,
            mentioned_title=mentioned,
            probable_title=probable,
            confidence=confidence,
            decided_by="automatic",
        )
        session.add(recommendation)
        session.commit()
        return recommendation.id


def _candidate(
    settings: Settings,
    recommendation_id: int,
    *,
    source: str = "TMDB",
    type_: str = "movie",
    external_id: str = "1",
    title: str = "Lights Out",
    year: int | None = 2016,
    score: float = 0.95,
    chosen: bool = False,
) -> None:
    with session_scope(settings) as session:
        session.add(
            Candidate(
                recommendation_id=recommendation_id,
                source=source,
                type=type_,
                external_id=external_id,
                title=title,
                year=year,
                score=score,
                origin="api",
                chosen=chosen,
            )
        )
        session.commit()


def _details() -> ProviderCandidate:
    return ProviderCandidate(
        source="TMDB",
        type="movie",
        external_id="1",
        title="Lights Out",
        original_title="Lights Out",
        year=2016,
        image_url="https://image.test/poster.jpg",
        description="A horror movie.",
        source_url="https://www.themoviedb.org/movie/1",
        genres=("Horror",),
    )


def test_list_cases_returns_pending_states(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    episode_id = _episode(settings)
    pending = _recommendation(settings, episode_id, state="needs_review")
    _recommendation(settings, episode_id, state="confirmed", mentioned="Other")
    _recommendation(settings, episode_id, state="discarded", mentioned="Gone")

    cases = list_cases(settings)

    assert [case.recommendation_id for case in cases] == [pending]
    assert all(case.state == "needs_review" for case in cases)


def test_list_cases_can_include_confirmed(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    episode_id = _episode(settings)
    _recommendation(settings, episode_id, state="needs_review")
    _recommendation(settings, episode_id, state="confirmed", mentioned="Other")

    cases = list_cases(settings, include_confirmed=True)

    assert len(cases) == 2


def test_status_summary_counts_states(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    episode_id = _episode(settings)
    _recommendation(settings, episode_id, state="needs_review")
    _recommendation(settings, episode_id, state="confirmed", mentioned="Other")
    _recommendation(settings, episode_id, state="manual_pending", mentioned="Book")

    summary = status_summary(settings)

    assert summary["counts"]["needs_review"] == 1
    assert summary["counts"]["confirmed"] == 1
    assert summary["counts"]["manual_pending"] == 1
    assert summary["pending_episodes"] == 1
    assert summary["total"] == 3


def test_resolve_candidate_links_and_marks_the_choice(
    monkeypatch, tmp_path: Path
) -> None:
    settings = _settings(tmp_path)
    episode_id = _episode(settings)
    recommendation_id = _recommendation(settings, episode_id)
    _candidate(settings, recommendation_id)
    monkeypatch.setattr(review_module, "fetch_details", lambda *args: _details())

    work = resolve_candidate(
        settings,
        recommendation_id,
        source="TMDB",
        type="movie",
        external_id="1",
        title="Lights Out",
        year=2016,
        image_url=None,
        score=0.95,
    )

    with session_scope(settings) as session:
        recommendation = session.get(Recommendation, recommendation_id)
        candidate = session.scalar(
            select(Candidate).where(Candidate.recommendation_id == recommendation_id)
        )
        assert recommendation is not None
        assert recommendation.state == "manual_resolved"
        assert recommendation.decided_by == "manual"
        assert recommendation.work_id == work.id
        assert recommendation.match_note == "manual_choice"
        assert candidate is not None
        assert candidate.chosen is True
    assert work.official_title == "Lights Out"
    assert work.source == "TMDB"


def test_resolve_candidate_with_a_new_search_replaces_candidates(
    monkeypatch, tmp_path: Path
) -> None:
    settings = _settings(tmp_path)
    episode_id = _episode(settings)
    recommendation_id = _recommendation(settings, episode_id)
    _candidate(settings, recommendation_id, external_id="old")
    candidate = _details()
    scored = [
        ScoredCandidate(candidate, 0.91),
        ScoredCandidate(
            ProviderCandidate(
                source="TMDB",
                type="movie",
                external_id="2",
                title="Other",
                original_title="Other",
                year=2010,
                image_url=None,
                description=None,
                source_url=None,
            ),
            0.70,
        ),
    ]
    monkeypatch.setattr(review_module, "fetch_details", lambda *args: candidate)

    resolve_candidate(
        settings,
        recommendation_id,
        source="TMDB",
        type="movie",
        external_id="1",
        title="Lights Out",
        year=2016,
        image_url=None,
        score=0.91,
        scored=scored,
    )

    with session_scope(settings) as session:
        candidates = list(
            session.scalars(
                select(Candidate).where(
                    Candidate.recommendation_id == recommendation_id
                )
            )
        )
    assert len(candidates) == 2
    assert [item.chosen for item in candidates] == [True, False]


def test_resolve_manual_creates_a_manual_work(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    episode_id = _episode(settings)
    recommendation_id = _recommendation(
        settings, episode_id, type_="book", mentioned="El libro", probable="El libro"
    )

    work = resolve_manual(
        settings,
        recommendation_id,
        type="book",
        title="El libro",
        year=2020,
        description="A book.",
    )

    assert work.source == "manual"
    assert work.external_id.startswith("manual:el-libro")
    with session_scope(settings) as session:
        recommendation = session.get(Recommendation, recommendation_id)
        assert recommendation is not None
        assert recommendation.state == "manual_resolved"
        assert recommendation.decided_by == "manual"
        assert recommendation.work_id == work.id
        assert recommendation.match_note == "manual_work"


def test_discard_marks_the_recommendation(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    episode_id = _episode(settings)
    recommendation_id = _recommendation(settings, episode_id)

    discard(settings, recommendation_id)

    with session_scope(settings) as session:
        recommendation = session.get(Recommendation, recommendation_id)
    assert recommendation is not None
    assert recommendation.state == "discarded"
    assert recommendation.decided_by == "manual"
    assert recommendation.match_note == "manual_discard"


def test_search_alternatives_returns_scored_candidates(
    monkeypatch, tmp_path: Path
) -> None:
    settings = _settings(tmp_path)
    episode_id = _episode(settings)
    recommendation_id = _recommendation(settings, episode_id)
    candidate = _details()
    scored = score_candidates("Lights Out", [candidate])
    monkeypatch.setattr(review_module, "make_clients", lambda settings: (None, None))
    monkeypatch.setattr(
        review_module,
        "search_candidates",
        lambda settings, tmdb, igdb, type_, query, *, year_hint=None: scored,
    )

    results = search_alternatives(settings, recommendation_id, "Lights Out")

    assert results[0].candidate.title == "Lights Out"


def test_search_alternatives_requires_an_existing_case(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with pytest.raises(ReviewError, match="not found"):
        search_alternatives(settings, 999, "Lights Out")


def test_enrich_does_not_touch_manual_decisions(tmp_path: Path) -> None:
    from despues_del_susto.steps import enrich as enrich_module

    settings = _settings(tmp_path)
    episode_id = _episode(settings)
    recommendation_id = _recommendation(
        settings,
        episode_id,
        state="manual_resolved",
        mentioned="Lights Out",
        probable="Lights Out",
    )
    with session_scope(settings) as session:
        work = Work(
            source="manual",
            external_id="manual:test",
            type="movie",
            official_title="Manual",
        )
        session.add(work)
        session.flush()
        recommendation = session.get(Recommendation, recommendation_id)
        recommendation.work_id = work.id
        recommendation.decided_by = "manual"
        session.commit()

    enrich_module.run(
        SimpleNamespace(id=episode_id, video_id="abc"), settings
    )

    with session_scope(settings) as session:
        recommendation = session.get(Recommendation, recommendation_id)
    assert recommendation is not None
    assert recommendation.state == "manual_resolved"
    assert recommendation.decided_by == "manual"
