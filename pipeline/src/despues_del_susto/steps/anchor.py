"""The ``anchor`` step: find the recommendations section in the subtitles."""

import bisect
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from despues_del_susto.config import Settings
from despues_del_susto.db import session_scope
from despues_del_susto.db.models import Episode
from despues_del_susto.services.processing import get_or_create
from despues_del_susto.steps.subtitles import find_subtitle_file, language_of

#: The anchor must be in the second half of the episode.
MIN_RATIO = 0.5
#: And at most this many seconds from the end.
MAX_TAIL_S = 720

_RECOMMEND = r"recom(?:end(?:ar|acion|aron)|iend(?:a|as|an)\b)"
_JUEGO = r"(?:videojuego|juego)s?"
_PELI = r"(?:pelicula|peli)s?"

ANCHOR_PATTERNS: dict[str, tuple[str, ...]] = {
    "juego": (
        rf"que {_JUEGO}\b.{{0,60}}{_RECOMMEND}",
        rf"recomendacion de {_JUEGO}\b",
        rf"{_JUEGO}\b.{{0,40}}\b{_RECOMMEND}",
        rf"tenemos {_JUEGO}\b",
        rf"\brodrigo\b.{{0,40}}{_JUEGO}\b",
    ),
    "peli": (
        rf"que {_PELI}\b.{{0,60}}{_RECOMMEND}",
        rf"recomendacion de {_PELI}\b",
        rf"{_PELI}\b.{{0,40}}\b{_RECOMMEND}",
        rf"tenemos {_PELI}\b",
        rf"\bazul\b.{{0,40}}{_PELI}\b",
    ),
    "intro": (
        r"hicieran recomendaciones",
        r"tenemos\b.{0,25}\brecomendacion",
        rf"que nos (?:va a |vas a )?{_RECOMMEND}",
        r"cual es la recomendacion",
        r"recomendacion de (?:esta semana|hoy|la semana)",
    ),
}


@dataclass(frozen=True)
class SubtitleEvent:
    start_s: float
    text: str


@dataclass(frozen=True)
class AnchorResult:
    state: str
    anchor_s: int | None = None
    anchor_kinds: tuple[str, ...] = ()
    evidence: str | None = None
    tail_s: int | None = None


def load_events(path: Path) -> tuple[list[SubtitleEvent], float]:
    """Read a ``.json3`` file, dropping the repeated lines of rolling captions."""
    data = json.loads(path.read_text(encoding="utf-8"))
    raw: list[SubtitleEvent] = []
    duration_s = 0.0
    for event in data.get("events", []):
        start_ms = event.get("tStartMs", 0)
        duration_s = max(duration_s, (start_ms + event.get("dDurationMs", 0)) / 1000)
        text = _clean("".join(segment.get("utf8", "") for segment in event.get("segs", [])))
        if text:
            raw.append(SubtitleEvent(start_s=start_ms / 1000, text=text))

    events: list[SubtitleEvent] = []
    for index, event in enumerate(raw):
        is_prefix = (
            index + 1 < len(raw)
            and raw[index + 1].text.startswith(event.text)
            and raw[index + 1].text != event.text
        )
        if is_prefix:
            continue
        if events and events[-1].text == event.text:
            continue
        events.append(event)
    return events, duration_s


def detect(events: list[SubtitleEvent], duration_s: float) -> AnchorResult:
    """Apply the anchor rules to one episode's subtitles."""
    if duration_s <= 0 or not events:
        return AnchorResult(state="sin_ancla")

    text, offsets = _flatten(events)
    hits = _find_hits(text, offsets, duration_s)
    if not hits:
        return AnchorResult(state="sin_ancla")

    kind, (anchor_s, evidence) = min(hits.items(), key=lambda item: item[1][0])
    kinds = tuple(sorted(hits))
    state = "ok" if {"juego", "peli"} <= set(kinds) else "parcial"
    return AnchorResult(
        state=state,
        anchor_s=round(anchor_s),
        anchor_kinds=kinds,
        evidence=evidence,
        tail_s=round(duration_s - anchor_s),
    )


def run(episode: Episode, settings: Settings) -> None:
    path = find_subtitle_file(settings, episode.video_id)
    if path is None:
        result = AnchorResult(state="sin_ancla")
        language = None
    else:
        events, duration_s = load_events(path)
        result = detect(events, duration_s)
        language = language_of(path)

    with session_scope(settings) as session:
        row = get_or_create(session, episode.id)
        row.subtitles_available = path is not None
        row.subtitles_language = language
        row.anchor_s = result.anchor_s
        row.anchor_kinds = ",".join(result.anchor_kinds) or None
        row.anchor_state = result.state
        row.anchor_evidence = result.evidence
        row.tail_s = result.tail_s
        session.commit()


def _clean(text: str) -> str:
    return " ".join(text.replace("\n", " ").split())


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return decomposed.encode("ascii", "ignore").decode().lower()


def _flatten(events: list[SubtitleEvent]) -> tuple[str, list[tuple[int, float]]]:
    """Join the events into one normalized string, keeping each event's offset."""
    parts: list[str] = []
    offsets: list[tuple[int, float]] = []
    cursor = 0
    for event in events:
        text = _normalize(event.text)
        if not text:
            continue
        offsets.append((cursor, event.start_s))
        parts.append(text)
        cursor += len(text) + 1
    return " ".join(parts), offsets


def _find_hits(
    text: str, offsets: list[tuple[int, float]], duration_s: float
) -> dict[str, tuple[float, str]]:
    """Earliest valid match of each kind, under the position and tail rules."""
    keys = [position for position, _ in offsets]
    hits: dict[str, tuple[float, str]] = {}
    for kind, patterns in ANCHOR_PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                index = bisect.bisect_right(keys, match.start()) - 1
                if index < 0:
                    continue
                start_s = offsets[index][1]
                if start_s / duration_s < MIN_RATIO:
                    continue
                if duration_s - start_s > MAX_TAIL_S:
                    continue
                if kind not in hits or start_s < hits[kind][0]:
                    hits[kind] = (start_s, text[match.start() : match.start() + 70])
    return hits
