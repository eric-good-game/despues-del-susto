import json
import sqlite3
from pathlib import Path

import pytest

from despues_del_susto import __version__
from despues_del_susto import steps as steps_module
from despues_del_susto.services.sync import FullMetadata, PlaylistEntry, SyncError
from despues_del_susto.steps import StopBatch, target_step
from despues_del_susto.steps.extract import ExtractionResult, RecommendationDraft
from despues_del_susto.steps.transcribe import Segment, TranscriptionResult


def _entry(video_id: str, title: str, position: int) -> PlaylistEntry:
    return PlaylistEntry(video_id=video_id, title=title, position=position)


def _episodes(db_path: Path) -> dict[str, dict]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        return {
            row["video_id"]: dict(row)
            for row in connection.execute("SELECT * FROM episodes")
        }


@pytest.fixture
def network(monkeypatch) -> dict:
    """Fake yt-dlp: a configurable playlist and metadata responses, no network."""
    state: dict = {"entries": [], "metadata": {}, "calls": [], "failing": set()}

    def listing(settings, url):
        return list(state["entries"])

    def metadata(settings, video_id):
        state["calls"].append(video_id)
        if video_id in state["failing"]:
            raise SyncError("boom")
        return state["metadata"].get(video_id) or FullMetadata(
            published_at=None,
            duration_s=100,
            thumbnail_url=None,
        )

    monkeypatch.setattr("despues_del_susto.services.sync.fetch_flat_listing", listing)
    monkeypatch.setattr("despues_del_susto.services.sync.fetch_full_metadata", metadata)
    return state


@pytest.fixture
def step_calls(monkeypatch) -> list[tuple[str, str]]:
    """Replace the step dispatch with a recorder, so ingest does no real work."""
    calls: list[tuple[str, str]] = []

    def fake(step, episode, settings):
        calls.append((step, episode.video_id))

    monkeypatch.setattr("despues_del_susto.services.ingest.run_step", fake)
    return calls


@pytest.fixture
def subtitle_writer(monkeypatch) -> None:
    """Fake yt-dlp that writes a Spanish subtitle file with an anchor in it."""

    def fake_run(settings, arguments):
        video_id = arguments[-1].rsplit("=", 1)[-1]
        template = arguments[arguments.index("-o") + 1]
        path = Path(template.replace("%(id)s", video_id).replace("%(ext)s", "es.json3"))
        path.write_text(json.dumps({"events": _anchor_events()}), encoding="utf-8")

    monkeypatch.setattr("despues_del_susto.steps.subtitles.run_command", fake_run)


@pytest.fixture
def audio_writer(monkeypatch) -> dict:
    """Fake yt-dlp audio download: records the section and writes an mp3."""
    state: dict = {"starts": []}

    def fake_run(settings, arguments, *, timeout=None):
        state["starts"].append(arguments[arguments.index("--download-sections") + 1])
        video_id = arguments[-1].rsplit("=", 1)[-1]
        directory = settings.data_dir / "audio"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{video_id}.mp3").write_bytes(b"ID3fake")

    monkeypatch.setattr("despues_del_susto.steps.audio.run_command", fake_run)
    return state


@pytest.fixture
def transcriber(monkeypatch) -> None:
    """Replace the Groq call with two segments, no network."""

    def fake(settings, audio_path):
        return TranscriptionResult(
            segments=[Segment(0.0, "hola"), Segment(10.0, "mundo")],
            service="groq",
            model="test-model",
        )

    monkeypatch.setattr("despues_del_susto.steps.transcribe.transcribe_audio", fake)


@pytest.fixture
def extractor(monkeypatch) -> None:
    """Replace the LLM call with one videogame and one movie, no network."""

    def fake(settings, transcript_text, video_id):
        return ExtractionResult(
            provider="fake",
            model="fake-model",
            declared_count=2,
            recommendations=[
                RecommendationDraft(
                    type="videogame",
                    mentioned_title="Juego",
                    probable_title="Game",
                    related_mentions=None,
                    mention_s=2900,
                    mentioned_platform="Steam",
                    confidence="high",
                ),
                RecommendationDraft(
                    type="movie",
                    mentioned_title="Peli",
                    probable_title="Movie",
                    related_mentions=None,
                    mention_s=3000,
                    mentioned_platform=None,
                    confidence="medium",
                ),
            ],
        )

    monkeypatch.setattr(
        "despues_del_susto.steps.extract.request_extraction", fake
    )


@pytest.fixture
def enricher(monkeypatch) -> None:
    """Replace the enrichment step with a no-op; its own tests cover it."""
    monkeypatch.setitem(
        steps_module._RUNNERS, "enrich", lambda episode, settings: None
    )


def _set_duration(db_path: Path, video_id: str, seconds: int) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE episodes SET duration_s = ? WHERE video_id = ?",
            (seconds, video_id),
        )


def _anchor_events() -> list[dict]:
    def event(start_s: int, text: str) -> dict:
        return {"tStartMs": start_s * 1000, "dDurationMs": 2000, "segs": [{"utf8": text}]}

    return [
        event(0, "hola"),
        event(2900, "tenemos recomendaciones"),
        event(3000, "que videojuego recomiendas"),
        event(3100, "recomendacion de pelicula"),
        event(3590, "gracias"),
    ]


def _processing(db_path: Path, video_id: str) -> dict:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT p.* FROM episode_processing p "
            "JOIN episodes e ON e.id = p.episode_id WHERE e.video_id = ?",
            (video_id,),
        ).fetchone()
    return dict(row)


def _step_statuses(db_path: Path, video_id: str) -> dict[str, str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT s.step, s.status FROM processing_steps s "
            "JOIN episodes e ON e.id = s.episode_id WHERE e.video_id = ?",
            (video_id,),
        ).fetchall()
    return dict(rows)


def test_version_command_prints_version(invoke) -> None:
    result = invoke("version")

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_running_without_arguments_shows_help(invoke) -> None:
    result = invoke()

    assert "Usage" in result.output


def test_db_upgrade_creates_the_schema(invoke, db_path: Path) -> None:
    result = invoke("db", "upgrade")

    assert result.exit_code == 0
    assert db_path.exists()
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"episodes", "processing_steps", "alembic_version"} <= tables


def test_episode_add_and_status(invoke) -> None:
    added = invoke("episode", "add", "abc123", "--title", "Episode one")
    assert added.exit_code == 0
    assert "abc123" in added.output

    status = invoke("status")
    assert status.exit_code == 0
    assert "abc123" in status.output
    assert "not started" in status.output


def test_episode_add_rejects_duplicates(invoke) -> None:
    invoke("episode", "add", "abc123", "--title", "Episode one")

    duplicate = invoke("episode", "add", "abc123", "--title", "Episode one again")

    assert duplicate.exit_code == 1
    assert "already exists" in duplicate.output


def test_status_without_episodes_explains_what_to_do(invoke) -> None:
    result = invoke("status")

    assert result.exit_code == 0
    assert "dds episode add" in result.output


def test_ingest_runs_every_step_and_skips_them_on_a_second_run(invoke, step_calls) -> None:
    invoke("episode", "add", "abc123", "--title", "Episode one")

    first = invoke("ingest", "abc123")
    assert first.exit_code == 0
    assert first.stdout.count(": done (") == 7

    second = invoke("ingest", "abc123")
    assert second.exit_code == 0
    assert second.stdout.count(": skipped") == 7

    status = invoke("status")
    assert "7/7" in status.output
    assert "complete" in status.output


def test_ingest_rejects_unknown_episodes(invoke) -> None:
    result = invoke("ingest", "missing")

    assert result.exit_code == 1
    assert "not registered" in result.output


def test_ingest_stops_at_a_failure_and_resumes_from_there(invoke, monkeypatch) -> None:
    invoke("episode", "add", "abc123", "--title", "Episode one")
    calls: list[str] = []

    def failing(step: str, episode, settings) -> None:
        calls.append(step)
        if step == "audio":
            raise RuntimeError("boom")

    monkeypatch.setattr("despues_del_susto.services.ingest.run_step", failing)

    first = invoke("ingest", "abc123")
    assert first.exit_code == 1
    assert "audio: failed" in first.output
    assert calls == ["subs", "anchor", "audio"]

    calls.clear()
    monkeypatch.setattr(
        "despues_del_susto.services.ingest.run_step",
        lambda *args: calls.append(args[0]),
    )

    second = invoke("ingest", "abc123")
    assert second.exit_code == 0
    assert calls == ["audio", "transcribe", "extract", "enrich", "publish"]


def test_sync_requires_a_playlist(invoke) -> None:
    result = invoke("sync")

    assert result.exit_code == 1
    assert "DDS_PLAYLIST_URL" in result.output


def test_sync_adds_episodes_and_fetches_metadata(invoke, network, db_path: Path) -> None:
    network["entries"] = [_entry("aaa", "Flat A", 1), _entry("bbb", "Flat B", 2)]

    result = invoke("sync", "--playlist-url", "https://example.test/list")

    assert result.exit_code == 0
    assert "added: 2" in result.output
    rows = _episodes(db_path)
    assert set(rows) == {"aaa", "bbb"}
    assert rows["aaa"]["title"] == "Flat A"
    assert rows["aaa"]["availability"] == "available"
    assert rows["aaa"]["metadata_fetched_at"] is not None
    assert network["calls"] == ["aaa", "bbb"]


def test_sync_is_idempotent(invoke, network, db_path: Path) -> None:
    network["entries"] = [_entry("aaa", "A", 1), _entry("bbb", "B", 2)]
    invoke("sync", "--playlist-url", "https://example.test/list")
    network["calls"].clear()

    second = invoke("sync", "--playlist-url", "https://example.test/list")

    assert second.exit_code == 0
    assert "unchanged: 2" in second.output
    assert network["calls"] == []


def test_sync_updates_title_and_position(invoke, network, db_path: Path) -> None:
    network["entries"] = [_entry("aaa", "A", 1)]
    invoke("sync", "--playlist-url", "https://example.test/list")

    network["entries"] = [_entry("aaa", "A renamed", 3)]
    result = invoke("sync", "--playlist-url", "https://example.test/list")

    assert "updated: 1" in result.output
    row = _episodes(db_path)["aaa"]
    assert row["title"] == "A renamed"
    assert row["playlist_position"] == 3


def test_sync_marks_missing_unavailable_and_reactivates(invoke, network, db_path: Path) -> None:
    network["entries"] = [_entry("aaa", "A", 1), _entry("bbb", "B", 2)]
    invoke("sync", "--playlist-url", "https://example.test/list")

    network["entries"] = [_entry("aaa", "A", 1)]
    removed = invoke("sync", "--playlist-url", "https://example.test/list")
    assert "unavailable: 1" in removed.output
    assert _episodes(db_path)["bbb"]["availability"] == "unavailable"

    network["entries"] = [_entry("aaa", "A", 1), _entry("bbb", "B", 2)]
    restored = invoke("sync", "--playlist-url", "https://example.test/list")
    assert "reactivated: 1" in restored.output
    assert _episodes(db_path)["bbb"]["availability"] == "available"


def _seed_four(invoke) -> None:
    for video_id in ("a", "b", "c", "d"):
        assert invoke("episode", "add", video_id, "--title", video_id).exit_code == 0


def test_sync_refuses_a_truncated_listing(invoke, network, db_path: Path) -> None:
    _seed_four(invoke)
    network["entries"] = [_entry("a", "A", 1)]

    result = invoke("sync", "--playlist-url", "https://example.test/list")

    assert result.exit_code == 1
    assert "known episodes" in result.output
    assert all(row["availability"] == "available" for row in _episodes(db_path).values())


def test_sync_force_accepts_a_truncated_listing(invoke, network, db_path: Path) -> None:
    _seed_four(invoke)
    network["entries"] = [_entry("a", "A", 1)]

    result = invoke("sync", "--force", "--playlist-url", "https://example.test/list")

    assert result.exit_code == 0
    assert "unavailable: 3" in result.output


def test_sync_aborts_on_an_empty_listing(invoke, network, db_path: Path) -> None:
    network["entries"] = []

    result = invoke("sync", "--playlist-url", "https://example.test/list")

    assert result.exit_code == 1
    assert "no entries" in result.output
    assert not db_path.exists()


def test_sync_dry_run_writes_nothing(invoke, network, db_path: Path) -> None:
    network["entries"] = [_entry("aaa", "A", 1)]

    result = invoke("sync", "--dry-run", "--playlist-url", "https://example.test/list")

    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert "added: 1" in result.output
    assert _episodes(db_path) == {}
    assert network["calls"] == []


def test_sync_retries_failed_metadata(invoke, network, db_path: Path) -> None:
    network["entries"] = [_entry("aaa", "A", 1)]
    network["failing"].add("aaa")

    first = invoke("sync", "--playlist-url", "https://example.test/list")
    assert first.exit_code == 0
    assert "metadata failed: 1" in first.output
    row = _episodes(db_path)["aaa"]
    assert row["metadata_fetched_at"] is None
    assert row["metadata_error"] == "boom"

    network["failing"].clear()
    second = invoke("sync", "--playlist-url", "https://example.test/list")
    assert "metadata fetched: 1" in second.output
    row = _episodes(db_path)["aaa"]
    assert row["metadata_fetched_at"] is not None
    assert row["metadata_error"] is None
    assert network["calls"] == ["aaa", "aaa"]


def test_ingest_all_processes_every_episode(invoke, step_calls) -> None:
    invoke("episode", "add", "aaa", "--title", "A")
    invoke("episode", "add", "bbb", "--title", "B")

    result = invoke("ingest", "--all")

    assert result.exit_code == 0
    assert "aaa: done 7, skipped 0" in result.output
    assert "bbb: done 7, skipped 0" in result.output
    assert len(step_calls) == 14


def test_ingest_redo_resets_the_step_and_everything_after_it(invoke, step_calls) -> None:
    invoke("episode", "add", "abc", "--title", "E")
    invoke("ingest", "abc")
    step_calls.clear()

    result = invoke("ingest", "abc", "--redo", "anchor")

    assert result.exit_code == 0
    assert step_calls == [
        ("anchor", "abc"),
        ("audio", "abc"),
        ("transcribe", "abc"),
        ("extract", "abc"),
        ("enrich", "abc"),
        ("publish", "abc"),
    ]
    assert "subs: skipped" in result.output


def test_ingest_rejects_unknown_redo_steps(invoke) -> None:
    result = invoke("ingest", "abc", "--redo", "nope")

    assert result.exit_code == 1
    assert "unknown step" in result.output


def test_ingest_requires_an_episode_or_all(invoke) -> None:
    result = invoke("ingest")

    assert result.exit_code == 1
    assert "pass a video_id" in result.output


def test_ingest_all_and_a_video_id_are_exclusive(invoke) -> None:
    result = invoke("ingest", "abc", "--all")

    assert result.exit_code == 1
    assert "not both" in result.output


def test_subs_and_anchor_store_the_section(
    invoke, subtitle_writer, audio_writer, transcriber, extractor, enricher, db_path: Path
) -> None:
    invoke("episode", "add", "abc", "--title", "E")
    _set_duration(db_path, "abc", 3600)

    result = invoke("ingest", "abc")

    assert result.exit_code == 0
    row = _processing(db_path, "abc")
    assert row["subtitles_available"] == 1
    assert row["subtitles_language"] == "es"
    assert row["anchor_state"] == "ok"
    assert row["anchor_s"] == 2900
    assert row["tail_s"] == 692
    assert row["anchor_kinds"] == "intro,juego,peli"
    assert row["window_start_s"] == 2810
    assert row["window_origin"] == "anchor"
    assert row["transcription_service"] == "groq"
    assert row["transcription_model"] == "test-model"
    assert row["transcribed_at"] is not None
    assert row["extraction_model"] == "fake-model"
    assert row["extracted_at"] is not None
    assert row["declared_count"] == 2
    assert row["extraction_complete"] == 1
    assert row["extraction_warnings"] is None
    assert audio_writer["starts"] == ["*2810-inf"]
    assert "audio: done" in result.output
    assert "transcribe: done" in result.output
    assert "extract: done" in result.output
    assert "enrich: done" in result.output
    assert "publish: not implemented yet" in result.output
    assert _step_statuses(db_path, "abc")["extract"] == "done"
    assert _step_statuses(db_path, "abc")["enrich"] == "done"
    assert _step_statuses(db_path, "abc")["publish"] == "pending"

    transcript = json.loads(
        (db_path.parent / "transcripts" / "abc.json").read_text(encoding="utf-8")
    )
    assert transcript == [
        {"t": 2810, "text": "hola"},
        {"t": 2820, "text": "mundo"},
    ]

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        recommendations = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM recommendations "
                "WHERE episode_id = (SELECT id FROM episodes WHERE video_id = 'abc') "
                "ORDER BY id"
            )
        ]
    assert len(recommendations) == 2
    assert recommendations[0]["type"] == "videogame"
    assert recommendations[0]["role"] == "primary"
    assert recommendations[0]["state"] == "extracted"
    assert recommendations[0]["decided_by"] == "automatic"
    assert recommendations[1]["type"] == "movie"
    assert recommendations[1]["role"] == "primary"

    artifact = json.loads(
        (db_path.parent / "extractions" / "abc.json").read_text(encoding="utf-8")
    )
    assert artifact["complete"] is True
    assert artifact["warnings"] == []
    assert artifact["model"] == "fake-model"
    assert [item["role"] for item in artifact["recommendations"]] == [
        "primary",
        "primary",
    ]


def test_missing_subtitles_is_a_state_not_a_failure(
    invoke, monkeypatch, audio_writer, transcriber, extractor, enricher, db_path: Path
) -> None:
    def no_files(settings, arguments):
        return None

    monkeypatch.setattr("despues_del_susto.steps.subtitles.run_command", no_files)
    invoke("episode", "add", "abc", "--title", "E")
    _set_duration(db_path, "abc", 3600)

    result = invoke("ingest", "abc")

    assert result.exit_code == 0
    assert "subs: done" in result.output
    assert "audio: done" in result.output
    assert "transcribe: done" in result.output
    assert "extract: done" in result.output
    assert "enrich: done" in result.output
    assert "publish: not implemented yet" in result.output
    row = _processing(db_path, "abc")
    assert row["subtitles_available"] == 0
    assert row["anchor_state"] == "sin_ancla"
    assert row["window_start_s"] == 2100
    assert row["window_origin"] == "fallback"

    transcript = json.loads(
        (db_path.parent / "transcripts" / "abc.json").read_text(encoding="utf-8")
    )
    assert [entry["t"] for entry in transcript] == [2100, 2110]


def test_ingest_limit_processes_only_the_requested_batch(invoke, step_calls) -> None:
    for video_id in ("aaa", "bbb", "ccc"):
        invoke("episode", "add", video_id, "--title", video_id)

    result = invoke("ingest", "--all", "--limit", "2")

    assert result.exit_code == 0
    assert len({video_id for _, video_id in step_calls}) == 2
    assert "Batch: 2 processed" in result.output
    assert f"1 pending for {target_step()}" in result.output


def test_ingest_limit_requires_all(invoke) -> None:
    result = invoke("ingest", "abc", "--limit", "2")

    assert result.exit_code == 1
    assert "--limit requires --all" in result.output


def test_ingest_limit_must_be_positive(invoke) -> None:
    result = invoke("ingest", "--all", "--limit", "0")

    assert result.exit_code == 1
    assert "at least 1" in result.output


def test_batch_skips_episodes_that_finished_the_target_step(invoke, step_calls) -> None:
    invoke("episode", "add", "aaa", "--title", "A")
    invoke("episode", "add", "bbb", "--title", "B")
    invoke("ingest", "aaa")
    step_calls.clear()

    result = invoke("ingest", "--all")

    assert result.exit_code == 0
    assert {video_id for _, video_id in step_calls} == {"bbb"}
    assert "Batch: 1 processed" in result.output


def test_batch_stops_when_a_step_asks_to_stop(
    invoke, monkeypatch, db_path: Path
) -> None:
    invoke("episode", "add", "aaa", "--title", "A")
    invoke("episode", "add", "bbb", "--title", "B")

    def fake(step, episode, settings):
        if step == "transcribe":
            raise StopBatch("quota exhausted")

    monkeypatch.setattr("despues_del_susto.services.ingest.run_step", fake)

    result = invoke("ingest", "--all")

    assert result.exit_code == 1
    assert "quota exhausted" in result.output
    assert "stopped early" in result.output
    assert _step_statuses(db_path, "aaa")["transcribe"] == "pending"
    assert _step_statuses(db_path, "bbb") == {}


def test_single_ingest_prints_live_progress(invoke, step_calls) -> None:
    invoke("episode", "add", "abc", "--title", "E")

    result = invoke("ingest", "abc")

    assert result.exit_code == 0
    assert result.stdout.index("subs: running") < result.stdout.index("subs: done (")


def test_quiet_suppresses_progress_but_keeps_the_summary(invoke, step_calls) -> None:
    invoke("episode", "add", "abc", "--title", "E")

    result = invoke("--quiet", "ingest", "abc")

    assert result.exit_code == 0
    assert "running" not in result.output
    assert "abc: done 7, skipped 0" in result.output


def test_quiet_batch_prints_only_the_summary(invoke, step_calls) -> None:
    invoke("episode", "add", "abc", "--title", "E")

    result = invoke("--quiet", "ingest", "--all")

    assert result.exit_code == 0
    assert "subs: running" not in result.output
    assert "Batch: 1 processed" in result.output


def test_sync_prints_metadata_progress(invoke, network) -> None:
    network["entries"] = [_entry("aaa", "A", 1)]

    result = invoke("sync", "--playlist-url", "https://example.test/list")

    assert result.exit_code == 0
    assert "metadata 1/1" in result.output
