"""The ``enrich`` step: match recommendations to catalog works."""

import json
import logging
from dataclasses import dataclass

from sqlalchemy import delete, select

from despues_del_susto.config import MetadataSettings, Settings
from despues_del_susto.db import Candidate as CandidateRow
from despues_del_susto.db import Recommendation, session_scope
from despues_del_susto.db.models import Episode
from despues_del_susto.providers.base import ProviderError
from despues_del_susto.providers.cache import JsonCache
from despues_del_susto.providers.igdb import IgdbClient
from despues_del_susto.providers.tmdb import TmdbClient
from despues_del_susto.services.matching import (
    Decision,
    decide,
    extract_year,
)
from despues_del_susto.services.matching_enhanced import build_queries
from despues_del_susto.services.metadata import search_candidates
from despues_del_susto.services.works import cleanup_orphans, upsert_work
from despues_del_susto.steps.errors import StopBatch

logger = logging.getLogger(__name__)

MANUAL_TYPES = {"book", "other"}


class EnrichmentError(RuntimeError):
    """A recommendation could not be matched."""


@dataclass(frozen=True)
class RecommendationInput:
    id: int
    type: str
    mentioned_title: str
    corrected_title: str | None
    probable_title: str | None
    year: int | None
    confidence: str
    disambiguation: str | None
    alternate_titles: tuple[str, ...]


def _parse_alternates(value: str | None) -> tuple[str, ...]:
    """Read the JSON list stored on a recommendation, tolerating bad data."""
    if not value:
        return ()
    try:
        data = json.loads(value)
    except (ValueError, TypeError):
        return ()
    if not isinstance(data, list):
        return ()
    return tuple(str(item) for item in data if isinstance(item, str) and item.strip())


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
                mentioned_title=row.mentioned_title,
                corrected_title=row.corrected_title,
                probable_title=row.probable_title,
                year=row.year,
                confidence=row.confidence,
                disambiguation=row.disambiguation,
                alternate_titles=_parse_alternates(row.alternate_titles),
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

    with session_scope(settings) as session:
        cleanup_orphans(session)
        session.commit()


def _match(
    settings: Settings,
    tmdb: TmdbClient,
    igdb: IgdbClient,
    item: RecommendationInput,
) -> Decision:
    if item.type in MANUAL_TYPES:
        return Decision("manual_pending", None, None, "manual_source", [])

    queries = build_queries(
        item.mentioned_title,
        item.corrected_title,
        item.probable_title,
        item.alternate_titles,
    )
    if not queries:
        return Decision("no_match", None, None, "empty_title", [])

    year_hint = (
        item.year
        or extract_year(item.probable_title)
        or extract_year(item.mentioned_title)
    )
    scored = search_candidates(settings, tmdb, igdb, item.type, queries)
    return decide(
        recommendation_type=item.type,
        confidence=item.confidence,
        year_hint=year_hint,
        scored=scored,
        threshold=settings.match_threshold,
        min_difference=settings.match_min_difference,
        mentioned=item.mentioned_title,
        hint=item.disambiguation,
    )


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
            work = upsert_work(session, details)
            recommendation.work_id = work.id
        else:
            recommendation.work_id = None
        recommendation.state = decision.state
        recommendation.match_score = decision.score
        recommendation.match_note = decision.note
        session.commit()
