"""Create and maintain catalog works."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from despues_del_susto.db.models import Recommendation, Work, utcnow
from despues_del_susto.providers.models import Candidate
from despues_del_susto.services.matching import normalize_title


def upsert_work(session: Session, candidate: Candidate) -> Work:
    """Create or update the work for a provider candidate."""
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
    work.original_language = candidate.original_language
    work.origin_country = candidate.origin_country
    work.description = candidate.description
    work.image_url = candidate.image_url
    work.source_url = candidate.source_url
    work.data_updated_at = utcnow()
    session.flush()
    return work


def create_manual_work(
    session: Session,
    *,
    type: str,
    title: str,
    year: int | None = None,
    description: str | None = None,
    image_url: str | None = None,
) -> Work:
    """Create or update a work that has no automatic source, such as a book."""
    external_id = _manual_external_id(title, year)
    work = session.scalar(
        select(Work).where(Work.source == "manual", Work.external_id == external_id)
    )
    if work is None:
        work = Work(
            source="manual",
            external_id=external_id,
            type=type,
            official_title=title,
        )
        session.add(work)

    work.type = type
    work.official_title = title
    work.year = year
    work.description = description or None
    work.image_url = image_url or None
    work.data_updated_at = utcnow()
    session.flush()
    return work


def cleanup_orphans(session: Session) -> None:
    """Delete works that no recommendation points to."""
    referenced = select(Recommendation.work_id).where(
        Recommendation.work_id.is_not(None)
    )
    session.execute(delete(Work).where(Work.id.not_in(referenced)))


def _manual_external_id(title: str, year: int | None) -> str:
    slug = normalize_title(title).replace(" ", "-") or "work"
    suffix = f":{year}" if year else ""
    return f"manual:{slug}{suffix}"
