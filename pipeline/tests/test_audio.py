from pathlib import Path

import pytest

from despues_del_susto.config import Settings
from despues_del_susto.steps.audio import (
    AudioDownloadError,
    AudioWindowError,
    Window,
    compute_window,
    download_audio,
)


def _window(anchor_state, anchor_s, tail_s, duration_s, expanded=False):
    return compute_window(
        anchor_state=anchor_state,
        anchor_s=anchor_s,
        tail_s=tail_s,
        duration_s=duration_s,
        expanded=expanded,
    )


def test_ok_uses_the_ninety_second_margin() -> None:
    assert _window("ok", 3000, 600, 3600) == Window(2910, "anchor")


def test_ok_clamps_the_start_at_zero() -> None:
    assert _window("ok", 50, 3550, 3600) == Window(0, "anchor")


def test_partial_uses_the_longer_margin() -> None:
    assert _window("parcial", 3000, 600, 3600) == Window(2760, "anchor")


def test_partial_with_a_short_tail_uses_the_longest_margin() -> None:
    assert _window("parcial", 3500, 100, 3600) == Window(3080, "anchor")


def test_partial_without_tail_derives_it_from_the_duration() -> None:
    assert _window("parcial", 3000, None, 3600) == Window(2760, "anchor")


def test_without_anchor_uses_the_last_45_percent() -> None:
    assert _window("sin_ancla", None, None, 3600) == Window(2100, "fallback")


def test_without_anchor_caps_the_fallback() -> None:
    assert _window("sin_ancla", None, None, 4000) == Window(2500, "fallback")


def test_expanded_uses_the_last_60_percent() -> None:
    assert _window("ok", 3000, 600, 3600, expanded=True) == Window(1440, "expanded")


def test_expanded_caps_the_window() -> None:
    assert _window("ok", 3000, 600, 5000, expanded=True) == Window(2600, "expanded")


def test_unknown_duration_is_an_error() -> None:
    with pytest.raises(AudioWindowError, match="duration"):
        _window("ok", 3000, 600, None)


def test_ok_without_anchor_is_an_error() -> None:
    with pytest.raises(AudioWindowError, match="anchor second"):
        _window("ok", None, 600, 3600)


def test_unknown_state_is_an_error() -> None:
    with pytest.raises(AudioWindowError, match="unknown anchor state"):
        _window(None, None, None, 3600)


def test_download_requests_the_section_and_returns_the_file(
    tmp_path: Path, monkeypatch
) -> None:
    settings = Settings(data_dir=tmp_path)
    calls: list[list[str]] = []

    def fake_run(settings, arguments, *, timeout=None):
        calls.append(arguments)
        video_id = arguments[-1].rsplit("=", 1)[-1]
        (tmp_path / "audio" / f"{video_id}.mp3").write_bytes(b"ID3fake")

    monkeypatch.setattr("despues_del_susto.steps.audio.run_command", fake_run)

    path = download_audio(settings, "abc", 1418)

    assert path.read_bytes() == b"ID3fake"
    arguments = calls[0]
    assert arguments[arguments.index("--download-sections") + 1] == "*1418-inf"
    assert "--force-keyframes-at-cuts" in arguments
    assert arguments[arguments.index("--audio-quality") + 1] == "48K"


def test_download_without_output_is_an_error(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(data_dir=tmp_path)
    monkeypatch.setattr(
        "despues_del_susto.steps.audio.run_command",
        lambda settings, arguments, *, timeout=None: None,
    )

    with pytest.raises(AudioDownloadError, match="no audio"):
        download_audio(settings, "abc", 1418)


def test_download_with_an_empty_file_is_an_error(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(data_dir=tmp_path)

    def fake_run(settings, arguments, *, timeout=None):
        video_id = arguments[-1].rsplit("=", 1)[-1]
        (tmp_path / "audio" / f"{video_id}.mp3").write_bytes(b"")

    monkeypatch.setattr("despues_del_susto.steps.audio.run_command", fake_run)

    with pytest.raises(AudioDownloadError, match="no audio"):
        download_audio(settings, "abc", 1418)


def test_download_failure_cleans_partial_files(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(data_dir=tmp_path)

    def fake_run(settings, arguments, *, timeout=None):
        video_id = arguments[-1].rsplit("=", 1)[-1]
        (tmp_path / "audio" / f"{video_id}.mp3.part").write_bytes(b"x")
        raise RuntimeError("boom")

    monkeypatch.setattr("despues_del_susto.steps.audio.run_command", fake_run)

    with pytest.raises(RuntimeError, match="boom"):
        download_audio(settings, "abc", 1418)

    assert list((tmp_path / "audio").iterdir()) == []
