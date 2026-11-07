"""The ``enrich`` step: match recommendations to catalog works."""

import logging
from dataclasses import dataclass

from sqlalchemy import delete, select

from despues_del_susto.config import MetadataSettings, Settings
from despues_del_susto.db import Candidate as CandidateRow
from despues_del_susto.db import Recommendation, Work, session_scope
from despues_del_susto.db.models import Episode, utcnow
from despues_del_susto.providers.base import ProviderError
from despues_del_susto.providers.cache import JsonCache
from despues_del_susto.providers.igdb import IgdbClient
from despues_del_susto.providers.models import Candidate
from despues_del_susto.providers.tmdb import TmdbClient
from despues_del_susto.services.matching import (
    Decision,
    clean_query,
    decide,
    extract_year,
    score_candidates,
    similarity,
)
from despues_del_susto.steps.errors import StopBatch

logger = logging.getLogger(__name__)

MANUAL_TYPES = {"book", "other"}


class EnrichmentError(RuntimeError):
    """A recommendation could not be matched."""


@dataclass(frozen=True)
class RecommendationInput:
    id: int
    type: str
    probable_title: str | None
    mentioned_title: str
    confidence: str


def run(episode: Episode, settings: Settings) -> None:
    with session_scope(settings) as session:
        rows = session.scalars(
            select(Recommendation).where(
                Recommendation.episode_id == episode.id,
                Recommendation.decided_by == "automatic",
            )
        ).all()
        items = [
            RecommendationInput(
                id=row.id,
                type=row.type,
                probable_title=row.probable_title,
                mentioned_title=row.mentioned_title,
                confidence=row.confidence,
            )
            for row in rows
        ]

    if not items:
        return

    metadata = MetadataSettings()
    cache = JsonCache(settings.data_dir / "cache")
    tmdb = TmdbClient(settings, metadata, cache)
    igdb = IgdbClient(settings, metadata, cache)

    for item in items:
        try:
            decision = _match(settings, tmdb, igdb, item)
        except ProviderError as exc:
            if exc.status_code == 429:
                raise StopBatch(
                    "metadata provider rate limit exhausted; run the batch again later"
                ) from exc
            raise EnrichmentError(str(exc)) from exc
        _persist(settings, item, decision, tmdb)

    _cleanup_orphan_works(settings)


def _cleanup_orphan_works(settings: Settings) -> None:
    """Remove works that no recommendation points to after a re-match."""
    with session_scope(settings) as session:
        referenced = select(Recommendation.work_id).where(
            Recommendation.work_id.is_not(None)
        )
        session.execute(delete(Work).where(Work.id.not_in(referenced)))
        session.commit()


def _match(
    settings: Settings,
    tmdb: TmdbClient,
    igdb: IgdbClient,
    item: RecommendationInput,
) -> Decision:
    if item.type in MANUAL_TYPES:
        return Decision("manual_pending", None, None, "manual_source", [])

    query = (item.probable_title or item.mentioned_title or "").strip()
    if not query:
        return Decision("no_match", None, None, "empty_title", [])

    year_hint = extract_year(item.probable_title) or extract_year(
        item.mentioned_title
    )
    search_query = clean_query(query)
    if item.type == "videogame":
        candidates = igdb.search(search_query)
    else:
        candidates = []
        for language in (settings.metadata_language, "en-US"):
            candidates.extend(
                tmdb.search(search_query, "movie", language=language)
            )
            candidates.extend(tmdb.search(search_query, "tv", language=language))

    scored = score_candidates(search_query, candidates)
    decision = decide(
        recommendation_type=item.type,
        confidence=item.confidence,
        year_hint=year_hint,
        scored=scored,
        threshold=settings.match_threshold,
        min_difference=settings.match_min_difference,
    )
    if (
        decision.state == "confirmed"
        and item.confidence != "high"
        and decision.chosen is not None
        and similarity(item.mentioned_title, decision.chosen) < 0.5
    ):
        return Decision(
            "needs_review", None, decision.score, "uncertain_title", decision.candidates
        )
    return decision


def _persist(
    settings: Settings,
    item: RecommendationInput,
    decision: Decision,
    tmdb: TmdbClient,
) -> None:
    details = decision.chosen
    if details is not None and details.source == "TMDB":
        media_type = "movie" if details.type == "movie" else "tv"
        details = tmdb.details(media_type, details.external_id)

    with session_scope(settings) as session:
        recommendation = session.get(Recommendation, item.id)
        if recommendation is None:
            return

        session.execute(
            delete(CandidateRow).where(
                CandidateRow.recommendation_id == item.id
            )
        )
        for scored in decision.candidates[: settings.max_candidates]:
            session.add(
                CandidateRow(
                    recommendation_id=item.id,
                    source=scored.candidate.source,
                    type=scored.candidate.type,
                    external_id=scored.candidate.external_id,
                    title=scored.candidate.title,
                    year=scored.candidate.year,
                    image_url=scored.candidate.image_url,
                    score=scored.score,
                    origin="api",
                    chosen=(
                        decision.chosen is not None
                        and scored.candidate.source == decision.chosen.source
                        and scored.candidate.external_id
                        == decision.chosen.external_id
                    ),
                )
            )

        if decision.state == "confirmed" and details is not None:
            work = _upsert_work(session, details)
            recommendation.work_id = work.id
        else:
            recommendation.work_id = None
        recommendation.state = decision.state
        recommendation.match_score = decision.score
        recommendation.match_note = decision.note
        session.commit()


def _upsert_work(session, candidate: Candidate) -> Work:
    work = session.scalar(
        select(Work).where(
            Work.source == candidate.source,
            Work.external_id == candidate.external_id,
        )
    )
    if work is None:
        work = Work(
            source=candidate.source,
            external_id=candidate.external_id,
            type=candidate.type,
            official_title=candidate.title,
        )
        session.add(work)

    work.type = candidate.type
    work.official_title = candidate.title
    work.original_title = candidate.original_title
    work.year = candidate.year
    work.genres = ", ".join(candidate.genres) or None
    work.description = candidate.description
    work.image_url = candidate.image_url
    work.source_url = candidate.source_url
    work.data_updated_at = utcnow()
    session.flush()
    return work
