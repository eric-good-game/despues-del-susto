"""Title normalization, scoring and match decisions."""

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

from despues_del_susto.providers.models import Candidate


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: Candidate
    score: float


@dataclass(frozen=True)
class Decision:
    state: str
    chosen: Candidate | None
    score: float | None
    note: str | None
    candidates: list[ScoredCandidate]


def normalize_title(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = decomposed.encode("ascii", "ignore").decode().lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", ascii_text)
    return " ".join(cleaned.split())


def similarity(query: str, candidate: Candidate) -> float:
    normalized_query = normalize_title(query)
    if not normalized_query:
        return 0.0
    titles = [candidate.title, candidate.original_title or ""]
    scores = [
        fuzz.token_sort_ratio(normalized_query, normalize_title(title)) / 100
        for title in titles
        if title
    ]
    return max(scores, default=0.0)


def score_candidates(query: str, candidates: list[Candidate]) -> list[ScoredCandidate]:
    best: dict[tuple[str, str], ScoredCandidate] = {}
    for candidate in candidates:
        scored = ScoredCandidate(candidate, similarity(query, candidate))
        key = (candidate.source, candidate.external_id)
        current = best.get(key)
        if current is None or scored.score > current.score:
            best[key] = scored
    return sorted(
        best.values(),
        key=lambda item: (item.score, item.candidate.popularity),
        reverse=True,
    )


def decide(
    *,
    recommendation_type: str,
    confidence: str,
    year_hint: int | None,
    scored: list[ScoredCandidate],
    threshold: float,
    min_difference: float,
) -> Decision:
    """Apply the match rules to the scored candidates."""
    if not scored:
        return Decision("no_match", None, None, "no_results", [])

    top = scored[0]
    if top.score < threshold:
        return Decision("needs_review", None, top.score, "below_threshold", scored)
    if confidence == "low":
        return Decision("needs_review", None, top.score, "low_confidence", scored)

    chosen = top
    note: str | None = None
    tied = [
        item for item in scored if top.score - item.score < min_difference
    ]
    if len(tied) > 1:
        if year_hint is not None:
            by_year = [
                item
                for item in tied
                if item.candidate.year is not None
                and abs(item.candidate.year - year_hint) <= 1
            ]
            if len(by_year) == 1:
                chosen = by_year[0]
                note = "resolved_by_year"
            else:
                return Decision(
                    "needs_review", None, top.score, "close_candidates", scored
                )
        else:
            return Decision(
                "needs_review", None, top.score, "close_candidates", scored
            )

    expected = {
        "movie": "movie",
        "series": "series",
        "videogame": "videogame",
    }.get(recommendation_type)
    if expected is not None and chosen.candidate.type != expected:
        return Decision(
            "needs_review", None, chosen.score, "type_mismatch", scored
        )
    return Decision("confirmed", chosen.candidate, chosen.score, note, scored)


def clean_query(value: str) -> str:
    """Drop a trailing parenthetical before asking the provider."""
    return re.sub(r"\s*\([^)]*\)\s*$", " ", value).strip()


def extract_year(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", value)
    return int(match.group(0)) if match else None
