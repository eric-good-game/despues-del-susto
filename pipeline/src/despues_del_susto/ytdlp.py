"""Thin wrapper around the ``yt-dlp`` command.

Two shapes are needed: JSON output for discovery and metadata, and plain file
output for subtitles. Both share the same error handling.
"""

import json
import subprocess

from despues_del_susto.config import Settings


class YtDlpError(RuntimeError):
    """yt-dlp could not run or returned something unusable."""


def run_json(settings: Settings, arguments: list[str], *, timeout: int | None = None) -> dict:
    """Run yt-dlp with ``--dump-single-json`` and parse the result."""
    command = [settings.yt_dlp_path, "--no-warnings", "--dump-single-json", *arguments]
    result = _run(command, settings, timeout)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise YtDlpError("yt-dlp returned invalid JSON") from exc


def run_command(
    settings: Settings, arguments: list[str], *, timeout: int | None = None
) -> subprocess.CompletedProcess:
    """Run yt-dlp and return its result, without interpreting the output."""
    command = [settings.yt_dlp_path, "--no-warnings", *arguments]
    return _run(command, settings, timeout)


def _run(
    command: list[str], settings: Settings, timeout: int | None
) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout or settings.yt_dlp_timeout_s,
            check=False,
        )
    except FileNotFoundError as exc:
        raise YtDlpError(
            f"{settings.yt_dlp_path} not found; install it with `brew install yt-dlp`"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise YtDlpError(f"yt-dlp timed out after {timeout or settings.yt_dlp_timeout_s}s") from exc

    if result.returncode != 0:
        lines = (result.stderr or result.stdout).strip().splitlines()
        detail = lines[-1] if lines else f"exit code {result.returncode}"
        raise YtDlpError(f"yt-dlp failed: {detail}")
    return result
