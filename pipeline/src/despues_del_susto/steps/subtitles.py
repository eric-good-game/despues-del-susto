"""Subtitle acquisition, shared by the ``subs`` and ``anchor`` steps."""

import logging
from dataclasses import dataclass
from pathlib import Path

from despues_del_susto.config import Settings
from despues_del_susto.ytdlp import run_command

logger = logging.getLogger(__name__)

#: Preferred Spanish variants, best first. Anything else that starts with ``es``
#: comes after these.
LANGUAGE_PREFERENCE = ("es", "es-orig", "es-419", "es-mx", "es-es")
SUBTITLE_SUFFIX = ".json3"


@dataclass(frozen=True)
class SubtitleDownload:
    available: bool
    language: str | None = None
    path: Path | None = None


def download_subtitles(settings: Settings, video_id: str) -> SubtitleDownload:
    """Download the automatic Spanish subtitles for one episode.

    Missing subtitles are not an error: the episode is marked as having none and
    the audio step will use its fallback window.
    """
    directory = settings.data_dir / "subs"
    directory.mkdir(parents=True, exist_ok=True)
    template = str(directory / "%(id)s.%(ext)s")
    run_command(
        settings,
        [
            "--skip-download",
            "--write-auto-subs",
            "--sub-format",
            "json3",
            "--sub-langs",
            "es.*",
            "--no-progress",
            "-o",
            template,
            f"https://www.youtube.com/watch?v={video_id}",
        ],
    )

    files = sorted(directory.glob(f"{video_id}.*{SUBTITLE_SUFFIX}"))
    if not files:
        logger.info("no Spanish subtitles found for %s", video_id)
        return SubtitleDownload(available=False)

    chosen = min(files, key=_preference)
    for extra in files:
        if extra != chosen:
            extra.unlink(missing_ok=True)
    return SubtitleDownload(
        available=True,
        language=language_of(chosen),
        path=chosen,
    )


def find_subtitle_file(settings: Settings, video_id: str) -> Path | None:
    """Return the preferred subtitle file already on disk, if any."""
    files = sorted((settings.data_dir / "subs").glob(f"{video_id}.*{SUBTITLE_SUFFIX}"))
    if not files:
        return None
    return min(files, key=_preference)


def language_of(path: Path) -> str:
    """Extract the language code from ``<video_id>.<lang>.json3``."""
    parts = path.name.split(".")
    return parts[1] if len(parts) >= 3 else ""


def _preference(path: Path) -> tuple[int, str]:
    language = language_of(path).lower()
    if language in LANGUAGE_PREFERENCE:
        return (LANGUAGE_PREFERENCE.index(language), language)
    return (len(LANGUAGE_PREFERENCE), language)
