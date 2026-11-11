from despues_del_susto.providers.models import Candidate
from despues_del_susto.services.matching import ScoredCandidate
from despues_del_susto.services.matching_enhanced import (
    _normalize_for_lookup,
    _remove_articles,
    _strip_trailing_number,
    generate_search_variants,
)


def _candidate(
    title: str,
    *,
    type_: str = "movie",
    year: int | None = None,
    original: str | None = None,
    popularity: float = 0.0,
) -> Candidate:
    return Candidate(
        source="TMDB",
        type=type_,
        external_id=f"{title}-{year}" if year else title,
        title=title,
        original_title=original,
        year=year,
        image_url=None,
        description=None,
        source_url=None,
        popularity=popularity,
    )


def test_generate_variants_remove_articles() -> None:
    variants = generate_search_variants("La posesión de Verónica")
    assert "posesión de Verónica" in variants or "posesion de Veronica" in variants


def test_generate_variants_strip_trailing_numbers() -> None:
    variants = generate_search_variants("Silent Hill 1")
    assert "Silent Hill" in variants


def test_generate_variants_return_known_translation() -> None:
    variants = generate_search_variants("Voraz")
    assert "raw" in variants
    assert "grave" in variants


def test_generate_variants_match_accented_known_translation() -> None:
    variants = generate_search_variants("La posesión de Verónica")
    assert "veronica" in variants
    assert "the possession of veronica" in variants


def test_normalize_for_lookup_removes_accents() -> None:
    assert _normalize_for_lookup("La posesión de Verónica") == "la posesion de veronica"


def test_remove_articles_handles_spanish_and_english() -> None:
    assert _remove_articles("The Lodge") == ["Lodge"]
    assert _remove_articles("La cabaña") == ["cabaña"]
    assert _remove_articles("Un juego") == ["juego"]


def test_strip_trailing_number_removes_roman_and_arabic() -> None:
    assert _strip_trailing_number("Silent Hill 1") == ["Silent Hill"]
    assert _strip_trailing_number("Final Fantasy VII") == ["Final Fantasy"]
    assert _strip_trailing_number("Silent Hill") == []


def _scored(title: str, score: float) -> ScoredCandidate:
    return ScoredCandidate(_candidate(title), score)


def test_scored_candidate_is_sortable() -> None:
    items = [_scored("A", 0.9), _scored("B", 0.95)]
    items.sort(key=lambda item: item.score, reverse=True)
    assert items[0].candidate.title == "B"
