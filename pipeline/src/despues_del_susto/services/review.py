"""Review pending recommendation matches."""

from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from despues_del_susto.config import Settings
from despues_del_susto.db import Candidate as CandidateRow
from despues_del_susto.db import Recommendation, Work, ensure_schema, session_scope
from despues_del_susto.db.models import Episode
from despues_del_susto.providers.base import ProviderError
from despues_del_susto.providers.models import Candidate
from despues_del_susto.services.matching import ScoredCandidate
from despues_del_susto.services.metadata import make_clients, search_candidates
from despues_del_susto.services.works import (
    cleanup_orphans,
    create_manual_work,
    upsert_work,
)

PENDING_STATES = ("needs_review", "no_match", "manual_pending")
ALL_STATES = (
    "extracted",
    "confirmed",
    "needs_review",
    "no_match",
    "manual_pending",
    "manual_resolved",
    "discarded",
)


class ReviewError(RuntimeError):
    """A review action could not be completed."""


@dataclass(frozen=True)
class CandidateView:
    id: int
    source: str
    type: str
    external_id: str
    title: str
    year: int | None
    image_url: str | None
    score: float
    chosen: bool


@dataclass(frozen=True)
class ReviewCase:
    recommendation_id: int
    episode_video_id: str
    episode_title: str
    type: str
    state: str
    mentioned_title: str
    probable_title: str | None
    confidence: str
    mention_s: int | None
    match_score: float | None
    match_note: str | None
    candidates: list[CandidateView]


def list_cases(
    settings: Settings,
    *,
    episode: str | None = None,
    include_confirmed: bool = False,
) -> list[ReviewCase]:
    """Return the cases that need a decision, in playlist order."""
    states = list(PENDING_STATES)
    if include_confirmed:
        states.append("confirmed")

    ensure_schema(settings)
    with session_scope(settings) as session:
        query = (
            select(Recommendation)
            .join(Episode)
            .options(selectinload(Recommendation.candidates))
            .where(Recommendation.state.in_(states))
            .order_by(
                Episode.playlist_position.is_(None),
                Episode.playlist_position,
                Episode.id,
                Recommendation.id,
            )
        )
        if episode:
            query = query.where(Episode.video_id == episode)
        rows = session.scalars(query).all()
        return [_case(row) for row in rows]


def status_summary(settings: Settings) -> dict:
    ensure_schema(settings)
    with session_scope(settings) as session:
        rows = session.execute(
            select(Recommendation.state, func.count()).group_by(
                Recommendation.state
            )
        ).all()
        counts = dict.fromkeys(ALL_STATES, 0)
        counts.update({state: count for state, count in rows})
        pending_episodes = session.scalar(
            select(func.count(func.distinct(Recommendation.episode_id))).where(
                Recommendation.state.in_(PENDING_STATES)
            )
        )
        works = session.scalar(select(func.count()).select_from(Work))
        total = session.scalar(select(func.count()).select_from(Recommendation))
    return {
        "counts": counts,
        "pending_episodes": pending_episodes or 0,
        "works": works or 0,
        "total": total or 0,
    }


def search_alternatives(
    settings: Settings, recommendation_id: int, query: str
) -> list[ScoredCandidate]:
    with session_scope(settings) as session:
        recommendation = session.get(Recommendation, recommendation_id)
        if recommendation is None:
            raise ReviewError(f"recommendation {recommendation_id} not found")
        type_ = recommendation.type

    tmdb, igdb = make_clients(settings)
    try:
        scored = search_candidates(settings, tmdb, igdb, type_, query)
    except ProviderError as exc:
        raise ReviewError(str(exc)) from exc
    return scored[: settings.max_candidates]


def resolve_candidate(
    settings: Settings,
    recommendation_id: int,
    *,
    source: str,
    type: str,
    external_id: str,
    title: str,
    year: int | None,
    image_url: str | None,
    score: float,
    scored: list[ScoredCandidate] | None = None,
) -> Work:
    """Link the recommendation to one provider candidate."""
    try:
        details = fetch_details(settings, source, type, external_id)
    except ProviderError as exc:
        raise ReviewError(str(exc)) from exc

    with session_scope(settings) as session:
        recommendation = session.get(Recommendation, recommendation_id)
        if recommendation is None:
            raise ReviewError(f"recommendation {recommendation_id} not found")

        work = upsert_work(session, details)
        recommendation.work_id = work.id
        recommendation.state = "manual_resolved"
        recommendation.decided_by = "manual"
        recommendation.match_score = score
        recommendation.match_note = "manual_choice"

        if scored is not None:
            _replace_candidates(
                session,
                recommendation_id,
                scored,
                source,
                external_id,
                settings.max_candidates,
            )
        else:
            _mark_chosen(
                session,
                recommendation_id,
                source=source,
                type_=type,
                external_id=external_id,
                title=title,
                year=year,
                image_url=image_url,
                score=score,
            )

        cleanup_orphans(session)
        session.commit()
        return work


def resolve_manual(
    settings: Settings,
    recommendation_id: int,
    *,
    type: str,
    title: str,
    year: int | None = None,
    description: str | None = None,
    image_url: str | None = None,
) -> Work:
    """Create a manual work for a book or another work without a source."""
    with session_scope(settings) as session:
        recommendation = session.get(Recommendation, recommendation_id)
        if recommendation is None:
            raise ReviewError(f"recommendation {recommendation_id} not found")

        work = create_manual_work(
            session,
            type=type,
            title=title,
            year=year,
            description=description,
            image_url=image_url,
        )
        recommendation.work_id = work.id
        recommendation.state = "manual_resolved"
        recommendation.decided_by = "manual"
        recommendation.match_score = None
        recommendation.match_note = "manual_work"
        cleanup_orphans(session)
        session.commit()
        return work


def discard(settings: Settings, recommendation_id: int) -> None:
    """Mark a recommendation as not a real recommendation."""
    with session_scope(settings) as session:
        recommendation = session.get(Recommendation, recommendation_id)
        if recommendation is None:
            raise ReviewError(f"recommendation {recommendation_id} not found")
        recommendation.state = "discarded"
        recommendation.decided_by = "manual"
        recommendation.work_id = None
        recommendation.match_score = None
        recommendation.match_note = "manual_discard"
        cleanup_orphans(session)
        session.commit()


def fetch_details(
    settings: Settings, source: str, type: str, external_id: str
) -> Candidate:
    tmdb, igdb = make_clients(settings)
    if source == "TMDB":
        media_type = "movie" if type == "movie" else "tv"
        return tmdb.details(media_type, external_id)
    if source == "IGDB":
        return igdb.details(external_id)
    raise ReviewError(f"unknown source {source}")


def _case(recommendation: Recommendation) -> ReviewCase:
    candidates = sorted(
        recommendation.candidates, key=lambda candidate: candidate.score, reverse=True
    )
    return ReviewCase(
        recommendation_id=recommendation.id,
        episode_video_id=recommendation.episode.video_id,
        episode_title=recommendation.episode.title,
        type=recommendation.type,
        state=recommendation.state,
        mentioned_title=recommendation.mentioned_title,
        probable_title=recommendation.probable_title,
        confidence=recommendation.confidence,
        mention_s=recommendation.mention_s,
        match_score=recommendation.match_score,
        match_note=recommendation.match_note,
        candidates=[
            CandidateView(
                id=candidate.id,
                source=candidate.source,
                type=candidate.type,
                external_id=candidate.external_id,
                title=candidate.title,
                year=candidate.year,
                image_url=candidate.image_url,
                score=candidate.score,
                chosen=candidate.chosen,
            )
            for candidate in candidates
        ],
    )


def _replace_candidates(
    session,
    recommendation_id: int,
    scored: list[ScoredCandidate],
    chosen_source: str,
    chosen_external_id: str,
    limit: int,
) -> None:
    session.execute(
        delete(CandidateRow).where(
            CandidateRow.recommendation_id == recommendation_id
        )
    )
    for item in scored[:limit]:
        session.add(
            CandidateRow(
                recommendation_id=recommendation_id,
                source=item.candidate.source,
                type=item.candidate.type,
                external_id=item.candidate.external_id,
                title=item.candidate.title,
                year=item.candidate.year,
                image_url=item.candidate.image_url,
                score=item.score,
                origin="api",
                chosen=(
                    item.candidate.source == chosen_source
                    and item.candidate.external_id == chosen_external_id
                ),
            )
        )


def _mark_chosen(
    session,
    recommendation_id: int,
    *,
    source: str,
    type_: str,
    external_id: str,
    title: str,
    year: int | None,
    image_url: str | None,
    score: float,
) -> None:
    rows = list(
        session.scalars(
            select(CandidateRow).where(
                CandidateRow.recommendation_id == recommendation_id
            )
        )
    )
    found = False
    for row in rows:
        row.chosen = row.source == source and row.external_id == external_id
        if row.chosen:
            row.score = score
            found = True
    if not found:
        session.add(
            CandidateRow(
                recommendation_id=recommendation_id,
                source=source,
                type=type_,
                external_id=external_id,
                title=title,
                year=year,
                image_url=image_url,
                score=score,
                origin="api",
                chosen=True,
            )
        )
