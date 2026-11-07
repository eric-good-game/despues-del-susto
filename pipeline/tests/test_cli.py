import sqlite3
from pathlib import Path

from despues_del_susto import __version__


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


def test_sync_requires_a_playlist_and_is_still_a_stub(invoke) -> None:
    without_url = invoke("sync")
    assert without_url.exit_code == 1
    assert "DDS_PLAYLIST_URL" in without_url.output

    with_url = invoke("sync", "--playlist-url", "https://www.youtube.com/playlist?list=x")
    assert with_url.exit_code == 1
    assert "phase 2" in with_url.output
