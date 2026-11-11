"""Title normalization, scoring and match decisions."""

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

from despues_del_susto.providers.models import Candidate

#: Where a match came from. Ordered most literal (trustworthy) first.
#: ``mentioned``/``corrected``/``alternate`` are titles the host actually said;
#: ``probable`` is the model's guess.
QUERY_LABELS = ("mentioned", "corrected", "probable", "alternate")

#: A probable-only match at or above this similarity means the model's official
#: title resolves to a real catalog work, so it is trusted even when the words
#: spoken (a localized or mistranscribed title) do not resemble it.
PROBABLY_REAL_MATCH = 0.90


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: Candidate
    score: float
    origin: str | None = None


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


#: Genres a horror-podcast recommendation is expected to fall under. Used only
#: to break ties between near-identical candidates, never to filter the search.
#: Names are compared after ``normalize_title``, so both Spanish and English
#: variants from TMDB/IGDB are listed.
HORROR_GENRES = frozenset(
    {
        "terror",
        "horror",
        "misterio",
        "mystery",
        "suspenso",
        "suspense",
        "thriller",
    }
)


def _is_horror(genres: tuple[str, ...]) -> bool:
    """Whether any candidate genre belongs to the expected horror family."""
    return any(normalize_title(genre) in HORROR_GENRES for genre in genres)


#: A short film is not a feature. TMDB returns shorts as ``type=movie`` and does
#: not expose runtime to the candidate, so the only signal we have is a genre
#: label. When a feature movie is available it wins; a short is a last resort.
SHORT_GENRES = frozenset({"short", "cortometraje", "corto"})


def _is_short(candidate: Candidate) -> bool:
    return any(normalize_title(genre) in SHORT_GENRES for genre in candidate.genres)


#: Words the host uses to point at the *old* version of a same-title work.
OLD_MARKERS = (
    "viejita", "viejo", "vieja", "viejos", "viejas",
    "antigua", "antiguo", "antiguas", "antiguos",
    "clasica", "clasico", "original", "primera",
    "blanco y negro",
)

#: Words that point at the *new* version.
NEW_MARKERS = (
    "nueva", "nuevo", "reciente", "moderna", "remake",
    "actual", "ultima", "version 20", "reestreno",
)

#: Country/origin words mapped to TMDB ``origin_country`` codes.
COUNTRY_MARKERS: dict[str, str] = {
    "coreana": "KR", "coreano": "KR",
    "japonesa": "JP", "japones": "JP",
    "espanola": "ES", "espanol": "ES",
    "argentina": "AR", "argentino": "AR",
    "mexicana": "MX", "mexicano": "MX",
    "inglesa": "GB", "britanica": "GB",
    "francesa": "FR", "frances": "FR",
    "americana": "US", "estadounidense": "US",
}


def _era_candidates(
    pool: list[ScoredCandidate], hint: str | None
) -> list[ScoredCandidate] | None:
    """Narrow the pool to the oldest or newest works named by the hint.

    Returns the extreme-year group, or ``None`` when the hint shows no era
    preference. Dated candidates only; an era word never prefers an undated one.
    """
    if not hint:
        return None
    normalized = normalize_title(hint)
    wants_old = any(marker in normalized for marker in OLD_MARKERS)
    wants_new = any(marker in normalized for marker in NEW_MARKERS)
    if wants_old == wants_new:  # neither, or contradictory
        return None
    dated = [item for item in pool if item.candidate.year is not None]
    if not dated:
        return None
    pick = min if wants_old else max
    edge = pick(dated, key=lambda item: item.candidate.year).candidate.year
    return [item for item in dated if item.candidate.year == edge]


def _country_pick(
    pool: list[ScoredCandidate], hint: str | None
) -> tuple[ScoredCandidate | None, str | None]:
    """Prefer the candidate whose origin country matches a word in the hint."""
    if not hint:
        return None, None
    normalized = normalize_title(hint)
    code = next(
        (value for word, value in COUNTRY_MARKERS.items() if word in normalized),
        None,
    )
    if code is None:
        return None, None
    matches = [item for item in pool if item.candidate.origin_country == code]
    if len(matches) == 1:
        return matches[0], "country"
    if len(matches) > 1:
        return None, "country"  # narrowed the pool but not to one
    return None, None


def _distinct_types(items: list[ScoredCandidate]) -> str:
    return ",".join(sorted({item.candidate.type for item in items}))


def _break_tie(
    tied: list[ScoredCandidate],
    year_hint: int | None,
    expected_type: str | None,
    hint: str | None = None,
) -> tuple[ScoredCandidate, list[str]]:
    """Pick one from tied candidates: type, genre, era, country, year, popularity.

    * **Type** (movie vs series): the podcast convention is a movie, so same-type
      candidates win. If only the other type exists we keep it but note it, and
      when both exist we note the same-name alternative type. Shorts yield to
      feature movies of the same type.
    * **Genre**: a single horror-family candidate wins.
    * **Era / country**: words in the disambiguation ``hint`` ("la más viejita",
      "la coreana") pick the oldest/newest or the matching-origin candidate.
    * **Year**: an explicit ``year_hint`` within ±1 wins; otherwise a year inside
      the hint ("la del 2007 o por ahí") wins within ±2.
    * **Popularity**: the final fallback, always flagged for later review.

    Returns ``(chosen, notes)``; ``notes`` are ordered reason + extra flags.
    """
    notes: list[str] = []
    pool = list(tied)

    if expected_type in ("movie", "series"):
        same = [item for item in pool if item.candidate.type == expected_type]
        other = [item for item in pool if item.candidate.type != expected_type]
        if same:
            features = [item for item in same if not _is_short(item.candidate)]
            if features:
                if len(features) < len(same):
                    notes.append("shorts_yielded")
                pool = features
            else:
                pool = same
                notes.append("only_short")
            if other:
                notes.append(f"same_title_other_type={_distinct_types(other)}")
        elif other:
            pool = other
            notes.append(f"type_substituted={_distinct_types(other)}")

    if len(pool) == 1:
        return pool[0], ["resolved_by_type"] + notes

    on_theme = [item for item in pool if _is_horror(item.candidate.genres)]
    if len(on_theme) == 1:
        return on_theme[0], ["resolved_by_genre"] + notes
    if len(on_theme) > 1:
        pool = on_theme

    era_group = _era_candidates(pool, hint)
    if era_group:
        if len(era_group) == 1:
            return era_group[0], ["resolved_by_era"] + notes
        # Several works share the extreme year: keep only those so the next
        # steps (and popularity) decide among the old/new ones, not against them.
        notes.append("era_group")
        pool = era_group

    country_pick, country_reason = _country_pick(pool, hint)
    if country_pick is not None:
        return country_pick, [f"resolved_by_{country_reason}"] + notes
    if country_reason == "country":
        # Matched the country but to several works; keep the narrowed pool.
        code = next(
            (v for w, v in COUNTRY_MARKERS.items() if w in normalize_title(hint or "")),
            None,
        )
        pool = [item for item in pool if item.candidate.origin_country == code]

    if year_hint is not None:
        by_year = [
            item
            for item in pool
            if item.candidate.year is not None
            and abs(item.candidate.year - year_hint) <= 1
        ]
        if len(by_year) == 1:
            return by_year[0], ["resolved_by_year"] + notes
        if by_year:
            pool = by_year
    else:
        hint_year = extract_year(hint)
        if hint_year is not None:
            by_hint = [
                item
                for item in pool
                if item.candidate.year is not None
                and abs(item.candidate.year - hint_year) <= 2
            ]
            if len(by_hint) == 1:
                return by_hint[0], ["resolved_by_hint_year"] + notes
            if by_hint:
                pool = by_hint

    if len(pool) > 1:
        pool.sort(key=lambda item: item.candidate.popularity, reverse=True)
        return pool[0], ["resolved_by_popularity"] + notes

    return pool[0], notes


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
    mentioned: str | None = None,
    hint: str | None = None,
) -> Decision:
    """Apply the match rules to the scored candidates.

    ``scored`` items carry ``origin``: which extracted title justified the match
    (``mentioned``, ``corrected`` or ``probable``). A literal match (mentioned /
    corrected) is trusted; a probable-only match is a semantic jump and is held
    to a higher bar.
    """
    if not scored:
        return Decision("no_match", None, None, "no_results", [])

    top = scored[0]
    if top.score < threshold:
        return Decision("needs_review", None, top.score, "below_threshold", scored)

    expected = {
        "movie": "movie",
        "series": "series",
        "videogame": "videogame",
    }.get(recommendation_type)

    tied = [item for item in scored if top.score - item.score < min_difference]
    if len(tied) > 1:
        chosen, note_parts = _break_tie(tied, year_hint, expected, hint)
        reason = note_parts[0] if note_parts else None
    else:
        chosen = top
        note_parts = []
        reason = None

    origin = chosen.origin
    hint_decisive = reason in {
        "resolved_by_era",
        "resolved_by_country",
        "resolved_by_hint_year",
    }
    # A match justified by what was actually said (or its transcription fix) is
    # strong evidence; a probable-only match is a semantic guess.
    # ``mentioned``/``corrected``/``alternate`` are titles the host said, so they
    # are trusted like the literal mention; ``probable`` alone is a guess.
    literal = origin in ("mentioned", "corrected", "alternate")

    # Low confidence goes to review unless the literal title matched the work or
    # the host's disambiguation word settled the version.
    if confidence == "low" and not (literal or hint_decisive):
        return Decision("needs_review", None, top.score, "low_confidence", scored)

    # A probable-only match that does not resemble what was said (a translation
    # guess) is held for review unless the confidence is high or the hint decides.
    # It is trusted when the model's official title resolves to a real work (a
    # score at or above PROBABLY_REAL_MATCH), which is what lets "No vayas a
    # casa" -> "Don't Come Home" confirm: the guess matches a catalog work exactly.
    if (
        not literal
        and confidence != "high"
        and not hint_decisive
        and mentioned
        and similarity(mentioned, chosen.candidate) < 0.5
    ):
        if chosen.score < PROBABLY_REAL_MATCH:
            return Decision(
                "needs_review", None, chosen.score, "uncertain_title", scored
            )
        note_parts = [*note_parts, "probable_strong"]

    note_parts = [f"from_{origin}", *note_parts] if origin else note_parts

    # A single top candidate of the wrong medium is kept but flagged: the audio
    # sometimes calls a series a movie (and the reverse).
    if expected is not None and chosen.candidate.type != expected:
        if not any(part.startswith("type_substituted") for part in note_parts):
            note_parts = [f"type_substituted={chosen.candidate.type}", *note_parts]

    note = ";".join(note_parts)[:100] if note_parts else None
    return Decision("confirmed", chosen.candidate, chosen.score, note, scored)


def clean_query(value: str) -> str:
    """Drop a trailing parenthetical before asking the provider."""
    return re.sub(r"\s*\([^)]*\)\s*$", " ", value).strip()


def extract_year(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", value)
    return int(match.group(0)) if match else None
