"""The ``audio`` step: compute the window and download that section."""

import logging
from dataclasses import dataclass
from pathlib import Path

from despues_del_susto.config import Settings
from despues_del_susto.db import EpisodeProcessing, session_scope
from despues_del_susto.db.models import Episode
from despues_del_susto.services.processing import get_or_create
from despues_del_susto.ytdlp import run_command

logger = logging.getLogger(__name__)

MARGIN_OK_S = 90
MARGIN_PARTIAL_S = 240
SHORT_TAIL_S = 150
MARGIN_SHORT_TAIL_S = 420
FALLBACK_RATIO = 0.45
FALLBACK_MAX_S = 1500
EXPANDED_RATIO = 0.60
EXPANDED_MAX_S = 2400


class AudioError(RuntimeError):
    """The audio window cannot be computed or downloaded."""


class AudioWindowError(AudioError):
    """The data needed to compute the window is missing or inconsistent."""


class AudioDownloadError(AudioError):
    """yt-dlp did not produce a usable audio file."""


@dataclass(frozen=True)
class Window:
    start_s: int
    origin: str


def compute_window(
    *,
    anchor_state: str | None,
    anchor_s: int | None,
    tail_s: int | None,
    duration_s: int | None,
    expanded: bool = False,
) -> Window:
    """Apply the window rules to one episode."""
    if duration_s is None or duration_s <= 0:
        raise AudioWindowError("episode duration is unknown; run `dds sync` first")

    if expanded:
        length = min(EXPANDED_MAX_S, round(duration_s * EXPANDED_RATIO))
        return Window(start_s=max(0, duration_s - length), origin="expanded")

    if anchor_state == "ok":
        if anchor_s is None:
            raise AudioWindowError("anchor state is ok but the anchor second is missing")
        return Window(start_s=max(0, anchor_s - MARGIN_OK_S), origin="anchor")

    if anchor_state == "parcial":
        if anchor_s is None:
            raise AudioWindowError("anchor state is parcial but the anchor second is missing")
        tail = tail_s if tail_s is not None else duration_s - anchor_s
        margin = MARGIN_SHORT_TAIL_S if tail < SHORT_TAIL_S else MARGIN_PARTIAL_S
        return Window(start_s=max(0, anchor_s - margin), origin="anchor")

    if anchor_state == "sin_ancla":
        length = min(FALLBACK_MAX_S, round(duration_s * FALLBACK_RATIO))
        return Window(start_s=max(0, duration_s - length), origin="fallback")

    raise AudioWindowError(
        f"unknown anchor state: {anchor_state!r}; run the anchor step first"
    )


def download_audio(settings: Settings, video_id: str, start_s: int) -> Path:
    """Download the audio from ``start_s`` to the end of the episode."""
    directory = settings.data_dir / "audio"
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f"{video_id}.mp3"
    output.unlink(missing_ok=True)

    try:
        run_command(
            settings,
            [
                "--download-sections",
                f"*{start_s}-inf",
                "-x",
                "--audio-format",
                "mp3",
                "--audio-quality",
                settings.audio_quality,
                "--force-keyframes-at-cuts",
                "--force-overwrites",
                "--no-progress",
                "-o",
                str(directory / "%(id)s.%(ext)s"),
                f"https://www.youtube.com/watch?v={video_id}",
            ],
            timeout=settings.audio_timeout_s,
        )
    except Exception:
        for leftover in directory.glob(f"{video_id}.*"):
            leftover.unlink(missing_ok=True)
        raise

    if not output.exists() or output.stat().st_size == 0:
        for leftover in directory.glob(f"{video_id}.*"):
            leftover.unlink(missing_ok=True)
        raise AudioDownloadError(f"yt-dlp produced no audio for {video_id}")

    for leftover in directory.glob(f"{video_id}.*"):
        if leftover != output:
            leftover.unlink(missing_ok=True)
    return output


def run(episode: Episode, settings: Settings) -> None:
    if episode.duration_s is None:
        raise AudioWindowError(
            f"episode {episode.video_id} has no duration; run `dds sync` first"
        )

    with session_scope(settings) as session:
        processing = session.get(EpisodeProcessing, episode.id)
        if processing is None or processing.anchor_state is None:
            raise AudioWindowError(
                f"the anchor step has not run for {episode.video_id}"
            )
        window = compute_window(
            anchor_state=processing.anchor_state,
            anchor_s=processing.anchor_s,
            tail_s=processing.tail_s,
            duration_s=episode.duration_s,
        )

    download_audio(settings, episode.video_id, window.start_s)

    with session_scope(settings) as session:
        row = get_or_create(session, episode.id)
        row.window_start_s = window.start_s
        row.window_origin = window.origin
        session.commit()
