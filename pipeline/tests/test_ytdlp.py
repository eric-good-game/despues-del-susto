import pytest

from despues_del_susto import ytdlp
from despues_del_susto.config import Settings
from despues_del_susto.ytdlp import YtDlpError


def test_run_json_raises_when_the_binary_is_missing(monkeypatch) -> None:
    def missing(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(ytdlp.subprocess, "run", missing)

    with pytest.raises(YtDlpError, match="not found"):
        ytdlp.run_json(Settings(), ["x"])


def test_run_json_raises_on_failure(monkeypatch) -> None:
    class Result:
        returncode = 1
        stdout = ""
        stderr = "ERROR: video unavailable"

    monkeypatch.setattr(ytdlp.subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(YtDlpError, match="video unavailable"):
        ytdlp.run_json(Settings(), ["x"])


def test_run_json_raises_on_invalid_json(monkeypatch) -> None:
    class Result:
        returncode = 0
        stdout = "not json"
        stderr = ""

    monkeypatch.setattr(ytdlp.subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(YtDlpError, match="invalid JSON"):
        ytdlp.run_json(Settings(), ["x"])
