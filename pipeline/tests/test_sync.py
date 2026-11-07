from datetime import UTC, datetime

import pytest

from despues_del_susto.config import Settings
from despues_del_susto.services import sync as sync_module
from despues_del_susto.services.sync import (
    SyncError,
    _parse_upload_date,
    fetch_flat_listing,
)


def test_parse_upload_date() -> None:
    assert _parse_upload_date("20260131") == datetime(2026, 1, 31, tzinfo=UTC)
    assert _parse_upload_date("") is None
    assert _parse_upload_date("31-01-2026") is None
    assert _parse_upload_date(None) is None


def test_fetch_flat_listing_skips_duplicates_and_keeps_positions(monkeypatch) -> None:
    monkeypatch.setattr(
        sync_module,
        "_run_yt_dlp",
        lambda settings, arguments: {
            "entries": [
                {"id": "a", "title": "A"},
                {"id": "a", "title": "A again"},
                {"id": "b", "title": "B"},
                {"title": "no id"},
            ]
        },
    )

    entries = fetch_flat_listing(Settings(), "https://example.test/list")

    assert [(entry.video_id, entry.position) for entry in entries] == [("a", 1), ("b", 3)]


def test_run_yt_dlp_raises_when_the_binary_is_missing(monkeypatch) -> None:
    def missing(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(sync_module.subprocess, "run", missing)

    with pytest.raises(SyncError, match="not found"):
        sync_module._run_yt_dlp(Settings(), ["x"])


def test_run_yt_dlp_raises_on_failure(monkeypatch) -> None:
    class Result:
        returncode = 1
        stdout = ""
        stderr = "ERROR: video unavailable"

    monkeypatch.setattr(sync_module.subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(SyncError, match="video unavailable"):
        sync_module._run_yt_dlp(Settings(), ["x"])


def test_run_yt_dlp_raises_on_invalid_json(monkeypatch) -> None:
    class Result:
        returncode = 0
        stdout = "not json"
        stderr = ""

    monkeypatch.setattr(sync_module.subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(SyncError, match="invalid JSON"):
        sync_module._run_yt_dlp(Settings(), ["x"])
