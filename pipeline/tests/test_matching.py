from despues_del_susto.providers.models import Candidate
from despues_del_susto.services.matching import (
    clean_query,
    decide,
    extract_year,
    normalize_title,
    score_candidates,
    similarity,
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


def test_normalize_title_removes_accents_and_punctuation() -> None:
    assert normalize_title("  ¡Hotel Transilvania! ") == "hotel transilvania"


def test_clean_query_removes_a_trailing_year() -> None:
    assert clean_query("Devil May Cry (2001)") == "Devil May Cry"
    assert clean_query("Raw (Grave)") == "Raw"


def test_extract_year() -> None:
    assert extract_year("Devil May Cry (2001)") == 2001
    assert extract_year("Hotel Transilvania") is None


def test_similarity_uses_title_and_original_title() -> None:
    candidate = _candidate(
        "Hotel Transylvania", original="Hotel Transylvania"
    )

    assert similarity("Hotel Transilvania", candidate) > 0.9


def test_score_candidates_deduplicates_by_source_and_id() -> None:
    candidate = _candidate("Hotel Transylvania")
    scored = score_candidates(
        "Hotel Transilvania", [candidate, candidate]
    )

    assert len(scored) == 1


def test_decide_confirms_a_clear_match() -> None:
    scored = score_candidates("Hotel Transilvania", [_candidate("Hotel Transylvania")])

    decision = decide(
        recommendation_type="movie",
        confidence="high",
        year_hint=None,
        scored=scored,
        threshold=0.85,
        min_difference=0.05,
    )

    assert decision.state == "confirmed"
    assert decision.chosen is not None
    assert decision.note is None


def test_decide_sends_a_low_score_to_review() -> None:
    scored = score_candidates("Madre Siniestra", [_candidate("Coraline")])

    decision = decide(
        recommendation_type="movie",
        confidence="high",
        year_hint=None,
        scored=scored,
        threshold=0.85,
        min_difference=0.05,
    )

    assert decision.state == "needs_review"
    assert decision.note == "below_threshold"


def test_decide_sends_low_confidence_to_review() -> None:
    scored = score_candidates("Hotel Transilvania", [_candidate("Hotel Transylvania")])

    decision = decide(
        recommendation_type="movie",
        confidence="low",
        year_hint=None,
        scored=scored,
        threshold=0.85,
        min_difference=0.05,
    )

    assert decision.state == "needs_review"
    assert decision.note == "low_confidence"


def test_decide_uses_the_year_to_break_a_tie() -> None:
    candidates = [
        _candidate("Devil May Cry", type_="videogame", year=2012),
        _candidate("Devil May Cry", type_="videogame", year=2001),
    ]
    scored = score_candidates("Devil May Cry", candidates)

    decision = decide(
        recommendation_type="videogame",
        confidence="high",
        year_hint=2001,
        scored=scored,
        threshold=0.85,
        min_difference=0.05,
    )

    assert decision.state == "confirmed"
    assert decision.chosen is not None
    assert decision.chosen.year == 2001
    assert decision.note == "resolved_by_year"


def test_decide_sends_an_unresolved_tie_to_review() -> None:
    candidates = [
        _candidate("Devil May Cry", type_="videogame", year=2012),
        _candidate("Devil May Cry", type_="videogame", year=2001),
    ]
    scored = score_candidates("Devil May Cry", candidates)

    decision = decide(
        recommendation_type="videogame",
        confidence="high",
        year_hint=None,
        scored=scored,
        threshold=0.85,
        min_difference=0.05,
    )

    assert decision.state == "needs_review"
    assert decision.note == "close_candidates"


def test_decide_sends_a_type_mismatch_to_review() -> None:
    scored = score_candidates(
        "Hotel Transylvania",
        [_candidate("Hotel Transylvania", type_="series")],
    )

    decision = decide(
        recommendation_type="movie",
        confidence="high",
        year_hint=None,
        scored=scored,
        threshold=0.85,
        min_difference=0.05,
    )

    assert decision.state == "needs_review"
    assert decision.note == "type_mismatch"


def test_decide_without_candidates_is_no_match() -> None:
    decision = decide(
        recommendation_type="movie",
        confidence="high",
        year_hint=None,
        scored=[],
        threshold=0.85,
        min_difference=0.05,
    )

    assert decision.state == "no_match"
    assert decision.note == "no_results"
