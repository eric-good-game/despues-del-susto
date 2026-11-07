from datetime import UTC, datetime

import pytest

from despues_del_susto.config import Settings
from despues_del_susto.services import sync as sync_module
from despues_del_susto.services.sync import (
    SyncError,
    _parse_upload_date,
    fetch_flat_listing,
)
from despues_del_susto.ytdlp import YtDlpError


def test_parse_upload_date() -> None:
    assert _parse_upload_date("20260131") == datetime(2026, 1, 31, tzinfo=UTC)
    assert _parse_upload_date("") is None
    assert _parse_upload_date("31-01-2026") is None
    assert _parse_upload_date(None) is None


def test_fetch_flat_listing_skips_duplicates_and_keeps_positions(monkeypatch) -> None:
    monkeypatch.setattr(
        sync_module,
        "run_json",
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


def test_fetch_flat_listing_wraps_ytdlp_errors(monkeypatch) -> None:
    def failing(settings, arguments):
        raise YtDlpError("video unavailable")

    monkeypatch.setattr(sync_module, "run_json", failing)

    with pytest.raises(SyncError, match="video unavailable"):
        fetch_flat_listing(Settings(), "https://example.test/list")
