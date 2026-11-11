import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from despues_del_susto.config import Settings
from despues_del_susto.db import (
    Episode,
    EpisodeProcessing,
    Recommendation,
    ensure_schema,
    session_scope,
)
from despues_del_susto.steps import StopBatch
from despues_del_susto.steps import extract as extract_module
from despues_del_susto.steps.extract import (
    ExtractionError,
    ExtractionResult,
    LlmProvider,
    RecommendationDraft,
    assign_roles,
    completeness,
    resolve_provider,
)


def _draft(
    type_: str,
    title: str = "X",
    confidence: str = "high",
    year: int | None = None,
) -> RecommendationDraft:
    return RecommendationDraft(
        type=type_,
        mentioned_title=title,
        probable_title=None,
        year=year,
        related_mentions=None,
        mention_s=1,
        mentioned_platform=None,
        confidence=confidence,
    )


def _result(recommendations: list[RecommendationDraft]) -> ExtractionResult:
    return ExtractionResult(
        provider="fake",
        model="fake-model",
        declared_count=len(recommendations),
        recommendations=recommendations,
    )


def test_assign_roles_marks_game_and_movie_primary() -> None:
    roles = assign_roles([_draft("videogame"), _draft("movie"), _draft("series")])

    assert [item.role for item in roles] == ["primary", "primary", "additional"]


def test_assign_roles_lets_a_series_replace_the_movie() -> None:
    roles = assign_roles([_draft("videogame"), _draft("series")])

    assert [item.role for item in roles] == ["primary", "primary"]


def test_completeness_with_game_and_movie() -> None:
    recommendations = assign_roles([_draft("videogame"), _draft("movie")])

    complete, warnings = completeness(recommendations, 2)

    assert complete is True
    assert warnings == []


def test_completeness_accepts_a_series_in_place_of_the_movie() -> None:
    recommendations = assign_roles([_draft("videogame"), _draft("series")])

    complete, warnings = completeness(recommendations, 2)

    assert complete is True
    assert warnings == ["series_in_place_of_movie"]


def test_completeness_blocks_a_missing_videogame() -> None:
    recommendations = assign_roles([_draft("movie")])

    complete, warnings = completeness(recommendations, 1)

    assert complete is False
    assert "missing_videogame" in warnings


def test_completeness_warns_about_extra_works_without_blocking() -> None:
    recommendations = assign_roles(
        [_draft("videogame"), _draft("movie"), _draft("movie", "Other")]
    )

    complete, warnings = completeness(recommendations, 3)

    assert complete is True
    assert warnings == ["more_than_one_movie"]


def test_completeness_blocks_fewer_than_declared() -> None:
    recommendations = assign_roles([_draft("videogame"), _draft("movie")])

    complete, warnings = completeness(recommendations, 3)

    assert complete is False
    assert warnings == ["fewer_than_declared"]


def test_normalize_cleans_types_titles_and_confidence() -> None:
    data = {
        "declared_count": 2,
        "recommendations": [
            {
                "type": "movie",
                "mentioned_title": " A ",
                "probable_title": "",
                "year": 2018,
                "related_mentions": None,
                "mention_s": 10.5,
                "mentioned_platform": "Netflix",
                "confidence": "HIGH",
            },
            {
                "type": "weird",
                "mentioned_title": "B",
                "confidence": "nope",
            },
            {"type": "videogame"},
        ],
    }

    result = extract_module._normalize(data, "fake", "model")

    assert result.declared_count == 2
    assert len(result.recommendations) == 2
    assert result.recommendations[0].mentioned_title == "A"
    assert result.recommendations[0].probable_title is None
    assert result.recommendations[0].year == 2018
    assert result.recommendations[0].mention_s == 10
    assert result.recommendations[0].confidence == "high"
    assert result.recommendations[1].type == "other"
    assert result.recommendations[1].confidence == "low"
    assert result.recommendations[1].year is None


def test_parse_json_accepts_a_fenced_block() -> None:
    assert extract_module._parse_json('```json\n{"ok": true}\n```') == {"ok": True}


def test_resolve_provider_reads_opencode(monkeypatch) -> None:
    monkeypatch.setenv("PROVIDER", "opencode")
    monkeypatch.setenv("OPENCODE_API_KEY", "key")
    monkeypatch.setenv("OPENCODE_MODEL", "model")
    monkeypatch.setenv("OPENCODE_FALLBACK_MODELS", "fallback, other")

    provider = resolve_provider()

    assert provider.name == "opencode"
    assert provider.api_key == "key"
    assert provider.models == ("model", "fallback", "other")


def test_resolve_provider_rejects_unknown_names(monkeypatch) -> None:
    monkeypatch.setenv("PROVIDER", "nope")

    with pytest.raises(ExtractionError, match="unknown provider"):
        resolve_provider()


def test_resolve_provider_requires_a_key(monkeypatch) -> None:
    monkeypatch.setenv("PROVIDER", "opencode")
    monkeypatch.setenv("OPENCODE_API_KEY", "")

    with pytest.raises(ExtractionError, match="API key"):
        resolve_provider()


class FakeError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


def _client(create) -> object:
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )
    )


def _response(content: str) -> object:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _provider() -> LlmProvider:
    return LlmProvider(
        name="fake",
        base_url="https://example.test",
        api_key="key",
        models=("model",),
    )


def test_request_extraction_retries_invalid_json(monkeypatch) -> None:
    calls = {"count": 0}
    valid = {
        "declared_count": 1,
        "recommendations": [
            {
                "type": "movie",
                "mentioned_title": "A",
                "confidence": "high",
            }
        ],
    }

    def create(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return _response("not json")
        return _response(json.dumps(valid))

    monkeypatch.setattr(extract_module, "resolve_provider", _provider)
    monkeypatch.setattr(extract_module, "OpenAI", lambda **kwargs: _client(create))
    monkeypatch.setattr(extract_module.time, "sleep", lambda seconds: None)

    result = extract_module.request_extraction(Settings(), "[t=1] hola", "abc")

    assert result.declared_count == 1
    assert result.recommendations[0].mentioned_title == "A"
    assert calls["count"] == 2


def test_request_extraction_stops_the_batch_on_rate_limit(monkeypatch) -> None:
    calls = {"count": 0}

    def create(**kwargs):
        calls["count"] += 1
        raise FakeError(429)

    monkeypatch.setattr(extract_module, "resolve_provider", _provider)
    monkeypatch.setattr(extract_module, "OpenAI", lambda **kwargs: _client(create))
    monkeypatch.setattr(extract_module.time, "sleep", lambda seconds: None)

    with pytest.raises(StopBatch, match="quota"):
        extract_module.request_extraction(Settings(), "[t=1] hola", "abc")

    assert calls["count"] == 5


def test_run_persists_recommendations_and_replaces_them_on_replay(
    monkeypatch, tmp_path: Path
) -> None:
    settings = Settings(data_dir=tmp_path)
    ensure_schema(settings)
    with session_scope(settings) as session:
        episode = Episode(video_id="abc", title="Episode")
        session.add(episode)
        session.commit()
        episode_id = episode.id

    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    (transcripts / "abc.json").write_text(
        json.dumps([{"t": 10, "text": "hola"}]), encoding="utf-8"
    )

    monkeypatch.setattr(
        extract_module,
        "request_extraction",
        lambda settings, text, video_id: _result(
            [_draft("videogame", "Game"), _draft("movie", "Movie")]
        ),
    )
    episode = SimpleNamespace(id=episode_id, video_id="abc")
    extract_module.run(episode, settings)

    with session_scope(settings) as session:
        rows = session.scalars(select(Recommendation)).all()
        processing = session.get(EpisodeProcessing, episode_id)
        assert len(rows) == 2
        assert {row.role for row in rows} == {"primary"}
        assert processing.extraction_model == "fake-model"
        assert processing.extraction_complete is True
        assert processing.extraction_warnings is None

    artifact = json.loads(
        (tmp_path / "extractions" / "abc.json").read_text(encoding="utf-8")
    )
    assert artifact["complete"] is True
    assert len(artifact["recommendations"]) == 2

    monkeypatch.setattr(
        extract_module,
        "request_extraction",
        lambda settings, text, video_id: _result([_draft("movie", "Only movie")]),
    )
    extract_module.run(episode, settings)

    with session_scope(settings) as session:
        rows = session.scalars(select(Recommendation)).all()
        assert len(rows) == 1
        assert rows[0].mentioned_title == "Only movie"
