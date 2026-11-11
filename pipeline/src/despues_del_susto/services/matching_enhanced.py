"""Multi-strategy title matching without external AI calls.

Phase 1 improves enrichment by:

* searching several variants of the extracted title (article removal,
  trailing number removal, known translations),
* scoring every provider candidate against the best matching variant.

The provider search is unfiltered. Year and genre are used later, in the match
decision, to break ties between same-title works.

All variants are generated locally; no LLM is used here.
"""

import logging
import re
import unicodedata

from despues_del_susto.config import Settings
from despues_del_susto.providers.igdb import IgdbClient
from despues_del_susto.providers.models import Candidate
from despues_del_susto.providers.tmdb import TmdbClient
from despues_del_susto.services.matching import (
    QUERY_LABELS,
    ScoredCandidate,
    clean_query,
    normalize_title,
    similarity,
)

logger = logging.getLogger(__name__)

#: Small dictionary of Spanish/English horror titles that simple heuristics miss.
#: Keys are normalized (accent-free, lower-case); values are raw search strings.
_KNOWN_TRANSLATIONS: dict[str, list[str]] = {
    "voraz": ["raw", "grave"],
    "la posesion de veronica": ["veronica", "the possession of veronica"],
    "la cabana siniestra": ["the lodge"],
    "el hombre elefante": ["the elephant man"],
    "nosotros": ["us"],
    "martires": ["martyrs"],
    "el ritual": ["the ritual"],
    "la aldea": ["the village"],
    "cuando las luces se apagan": ["lights out"],
    "la mano que mece la cuna": ["the hand that rocks the cradle"],
    "gonjiam hospital maldito": ["gonjiam haunted asylum"],
    "rec": ["rec"],
}

#: Leading articles in English and Spanish that are often omitted in databases.
_ARTICLES = ("the ", "a ", "an ", "la ", "el ", "los ", "las ", "un ", "una ")

#: Trailing numeric/ordinal suffixes such as "Silent Hill 1" or "Silent Hill I".
_TRAILING_NUMBER = re.compile(r"\s+([1-9]|[IVXLCDM]+)$", re.IGNORECASE)


def _normalize_for_lookup(value: str) -> str:
    """Lower-case and remove accents, keeping only letters and numbers."""
    decomposed = unicodedata.normalize("NFKD", value.lower())
    ascii_text = decomposed.encode("ascii", "ignore").decode()
    return "".join(
        char for char in ascii_text if char.isalnum() or char.isspace()
    ).strip()


def _remove_articles(title: str) -> list[str]:
    """Return versions of ``title`` without a leading article."""
    variants: list[str] = []
    lower = title.lower()
    for article in _ARTICLES:
        if lower.startswith(article):
            stripped = title[len(article) :].strip()
            if stripped:
                variants.append(stripped)
    return variants


def _strip_trailing_number(title: str) -> list[str]:
    """Return the title without a trailing "1", "I", "II", etc."""
    match = _TRAILING_NUMBER.search(title)
    if match:
        stripped = title[: match.start()].strip()
        if stripped:
            return [stripped]
    return []


def _known_variants(title: str) -> list[str]:
    """Look up hard-coded translations for the normalized title."""
    normalized = _normalize_for_lookup(title)
    return list(_KNOWN_TRANSLATIONS.get(normalized, []))


def generate_search_variants(title: str) -> list[str]:
    """Generate local search variants for a title.

    Variants come from article removal, trailing number removal and a small
    dictionary of known translations. Keyword fragments are intentionally
    avoided because short fragments match unrelated titles and create false
    ties during scoring.

    The original title is intentionally **not** included in the returned list;
    callers should use it as the base query and combine it with these variants.
    """
    base = title.strip()
    if not base:
        return []

    seen: set[str] = set()
    variants: list[str] = []

    def _add(value: str) -> None:
        cleaned = clean_query(value).strip()
        if cleaned and cleaned.lower() != base.lower() and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            variants.append(cleaned)

    for known in _known_variants(base):
        _add(known)

    for without_article in _remove_articles(base):
        _add(without_article)
        # Also try removing articles from the already-stripped form.
        for nested in _remove_articles(without_article):
            _add(nested)

    for without_number in _strip_trailing_number(base):
        _add(without_number)

    return variants


def build_queries(
    mentioned: str | None,
    corrected: str | None,
    probable: str | None,
    alternate_titles: list[str] | tuple[str, ...] | None = None,
) -> list[tuple[str, str]]:
    """Turn the extracted titles into ``[(label, base_query), ...]``.

    Labels are kept in literal order (mentioned, corrected, probable, then the
    ``alternate`` titles the host stated). A query that repeats an earlier one is
    dropped, so the more trusted label owns the search and scoring.
    """
    pairs: list[tuple[str, str | None]] = [
        ("mentioned", mentioned),
        ("corrected", corrected),
        ("probable", probable),
    ]
    for title in alternate_titles or ():
        pairs.append(("alternate", title))
    queries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label, title in pairs:
        base = clean_query((title or "").strip())
        if not base:
            continue
        key = normalize_title(base)
        if key in seen:
            continue
        seen.add(key)
        queries.append((label, base))
    return queries


def _score_with_provenance(
    labelled: list[tuple[str, list[str]]],
    candidates: list[Candidate],
) -> list[ScoredCandidate]:
    """Score candidates against each label and record the best-matching one.

    ``labelled`` is ``[(label, [query, variant, ...]), ...]``. The score is the
    maximum similarity over all labels; ``origin`` is the most literal label that
    attains it. Deduplicated by ``(source, external_id)``.
    """
    best: dict[tuple[str, str], ScoredCandidate] = {}
    for candidate in candidates:
        top_score = 0.0
        origin: str | None = None
        for label, queries in labelled:
            score = max((similarity(query, candidate) for query in queries), default=0.0)
            # Strictly greater keeps the first (most literal) label on a tie,
            # because labelled is already in QUERY_LABELS order.
            if score > top_score:
                top_score = score
                origin = label
        key = (candidate.source, candidate.external_id)
        scored = ScoredCandidate(candidate, top_score, origin)
        current = best.get(key)
        if current is None or scored.score > current.score:
            best[key] = scored
    return sorted(
        best.values(),
        key=lambda item: (item.score, item.candidate.popularity),
        reverse=True,
    )


def enhanced_search_candidates(
    settings: Settings,
    tmdb: TmdbClient,
    igdb: IgdbClient,
    type_: str,
    queries: list[tuple[str, str]],
) -> list[ScoredCandidate]:
    """Search providers for every labeled title and score with provenance.

    ``queries`` is the output of :func:`build_queries` (or a single ``("search", q)``
    pair from review). Movies and series are looked up in TMDB as ``movie`` and
    ``tv`` in both `es-MX` and `en-US`; videogames in IGDB. The search is
    **unfiltered** so a wrong year never drops the right candidate. Provider
    calls are deduplicated across labels.
    """
    if not queries:
        return []

    # Group bases by label, literal-first, so provenance ties resolve to the most
    # trusted label and multiple ``alternate`` titles are all kept.
    bases_by_label: dict[str, list[str]] = {}
    for label, base in sorted(
        queries,
        key=lambda it: QUERY_LABELS.index(it[0]) if it[0] in QUERY_LABELS else len(QUERY_LABELS),
    ):
        bases_by_label.setdefault(label, []).append(base)

    labelled: list[tuple[str, list[str]]] = []
    search_strings: list[str] = []
    seen: set[str] = set()
    for label, bases in bases_by_label.items():
        queries_for_label: list[str] = []
        for base in bases:
            for search_query in [base, *generate_search_variants(base)]:
                if search_query not in queries_for_label:
                    queries_for_label.append(search_query)
        labelled.append((label, queries_for_label))
        for search_query in queries_for_label:
            key = normalize_title(search_query)
            if key not in seen:
                seen.add(key)
                search_strings.append(search_query)

    all_candidates: list[Candidate] = []
    if type_ == "videogame":
        for search_query in search_strings:
            all_candidates.extend(igdb.search(search_query))
    else:
        languages = (settings.metadata_language, "en-US")
        for search_query in search_strings:
            for language in languages:
                all_candidates.extend(tmdb.search(search_query, "movie", language=language))
                all_candidates.extend(tmdb.search(search_query, "tv", language=language))

    return _score_with_provenance(labelled, all_candidates)
