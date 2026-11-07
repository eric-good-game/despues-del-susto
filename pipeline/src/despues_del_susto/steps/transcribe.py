"""The ``transcribe`` step: turn the audio window into text with seconds."""

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

from despues_del_susto.config import GroqSettings, Settings
from despues_del_susto.db import EpisodeProcessing, session_scope
from despues_del_susto.db.models import Episode, utcnow
from despues_del_susto.services.processing import get_or_create
from despues_del_susto.steps.errors import StopBatch

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MAX_BYTES = 25 * 1024 * 1024
RETRY_WAITS = (5, 15, 45, 90)


class TranscriptionError(RuntimeError):
    """The audio could not be transcribed."""


@dataclass(frozen=True)
class Segment:
    start_s: float
    text: str


@dataclass(frozen=True)
class TranscriptionResult:
    segments: list[Segment]
    service: str
    model: str


def transcribe_audio(settings: Settings, audio_path: Path) -> TranscriptionResult:
    """Send one audio file to Groq and return its segments.

    Transient errors are retried. If the retries end on a rate limit, the batch
    is stopped: the quota will not recover in the next few seconds.
    """
    groq = GroqSettings()
    if not groq.groq_api_key:
        raise TranscriptionError("GROQ_API_KEY is not set; add it to .env")

    client = OpenAI(
        base_url=GROQ_BASE_URL,
        api_key=groq.groq_api_key,
        timeout=settings.transcribe_timeout_s,
    )

    last: Exception | None = None
    attempts = (0, *RETRY_WAITS)
    for index, wait in enumerate(attempts):
        if wait:
            time.sleep(wait)
        try:
            with audio_path.open("rb") as handle:
                response = client.audio.transcriptions.create(
                    file=handle,
                    model=groq.groq_model,
                    language="es",
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
            return TranscriptionResult(
                segments=_segments_from(response),
                service="groq",
                model=groq.groq_model,
            )
        except Exception as exc:  # noqa: BLE001 - classified below
            last = exc
            if not _is_transient(exc):
                raise TranscriptionError(f"transcription failed: {exc}") from exc
            logger.warning(
                "transient transcription error (attempt %s/%s): %s",
                index + 1,
                len(attempts),
                exc,
            )

    if last is not None and _is_rate_limit(last):
        raise StopBatch(
            "Groq rate limit or quota exhausted; run the batch again later"
        ) from last
    raise TranscriptionError(f"transcription failed after retries: {last}") from last


def run(episode: Episode, settings: Settings) -> None:
    audio_path = settings.data_dir / "audio" / f"{episode.video_id}.mp3"
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise TranscriptionError(
            f"audio window not found for {episode.video_id}; run the audio step first"
        )
    if audio_path.stat().st_size > MAX_BYTES:
        raise TranscriptionError(
            f"audio window is larger than the {MAX_BYTES // (1024 * 1024)} MB limit"
        )

    with session_scope(settings) as session:
        processing = session.get(EpisodeProcessing, episode.id)
        if processing is None or processing.window_start_s is None:
            raise TranscriptionError("the audio step has not run for this episode")
        offset = processing.window_start_s

    result = transcribe_audio(settings, audio_path)
    if not result.segments:
        raise TranscriptionError("the transcription returned no segments")

    entries = [
        {"t": int(segment.start_s) + offset, "text": segment.text}
        for segment in result.segments
    ]
    _write_artifacts(settings, episode.video_id, entries)

    with session_scope(settings) as session:
        row = get_or_create(session, episode.id)
        row.transcription_service = result.service
        row.transcription_model = result.model
        row.transcribed_at = utcnow()
        session.commit()


def _segments_from(response: object) -> list[Segment]:
    raw = getattr(response, "segments", None)
    if raw is None and isinstance(response, dict):
        raw = response.get("segments")

    segments: list[Segment] = []
    for item in raw or []:
        start = item.get("start") if isinstance(item, dict) else getattr(item, "start", 0)
        text = item.get("text") if isinstance(item, dict) else getattr(item, "text", "")
        if text:
            segments.append(
                Segment(start_s=float(start or 0), text=str(text).strip())
            )

    if not segments:
        text = getattr(response, "text", "")
        if isinstance(response, dict):
            text = response.get("text", text)
        if text and str(text).strip():
            segments.append(Segment(start_s=0.0, text=str(text).strip()))
    return segments


def _is_transient(exc: Exception) -> bool:
    status = _status_code(exc)
    if status in (429, 500, 502, 503, 504):
        return True
    message = str(exc).lower()
    return any(
        marker in message
        for marker in ("overloaded", "rate limit", "timeout", "connection")
    )


def _is_rate_limit(exc: Exception) -> bool:
    if _status_code(exc) == 429:
        return True
    message = str(exc).lower()
    return "rate limit" in message or "quota" in message


def _status_code(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _write_artifacts(
    settings: Settings, video_id: str, entries: list[dict]
) -> None:
    directory = settings.data_dir / "transcripts"
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_write(
        directory / f"{video_id}.json",
        json.dumps(entries, ensure_ascii=False, indent=1),
    )
    lines = [
        f"[{entry['t'] // 60:02d}:{entry['t'] % 60:02d}] {entry['text']}"
        for entry in entries
    ]
    _atomic_write(directory / f"{video_id}.txt", "\n".join(lines) + "\n")


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
