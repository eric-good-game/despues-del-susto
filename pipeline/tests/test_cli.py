import sqlite3
from pathlib import Path

import pytest

from despues_del_susto import __version__
from despues_del_susto.services.sync import FullMetadata, PlaylistEntry, SyncError


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


def test_ingest_runs_every_step_and_skips_them_on_a_second_run(invoke) -> None:
    invoke("episode", "add", "abc123", "--title", "Episode one")

    first = invoke("ingest", "abc123")
    assert first.exit_code == 0
    assert first.stdout.count(": done") == 7

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
