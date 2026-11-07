"""ORM models for the local database.

Phase 1 defines the two tables the walking skeleton needs: ``episodes`` and
``processing_steps``. Further tables are added as each phase needs them, always
through an Alembic migration.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from despues_del_susto.db.base import Base


def utcnow() -> datetime:
    """Current time, in UTC."""
    return datetime.now(UTC)


class Episode(Base):
    """A video from the podcast, identified by its YouTube ``video_id``."""

    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_s: Mapped[int | None]
    thumbnail_url: Mapped[str | None] = mapped_column(String(1000))
    playlist_position: Mapped[int | None]
    availability: Mapped[str] = mapped_column(String(20), default="available")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_error: Mapped[str | None] = mapped_column(String(2000))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    steps: Mapped[list["ProcessingStep"]] = relationship(
        back_populates="episode",
        cascade="all, delete-orphan",
    )


class ProcessingStep(Base):
    """The state of one pipeline step for one episode."""

    __tablename__ = "processing_steps"
    __table_args__ = (
        UniqueConstraint("episode_id", "step", name="uq_processing_steps_episode_step"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(2000))

    episode: Mapped[Episode] = relationship(back_populates="steps")
