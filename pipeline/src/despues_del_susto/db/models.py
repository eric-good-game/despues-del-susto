"""ORM models for the local database.

Phase 1 defines the two tables the walking skeleton needs: ``episodes`` and
``processing_steps``. Further tables are added as each phase needs them, always
through an Alembic migration.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint
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
    processing: Mapped["EpisodeProcessing | None"] = relationship(
        back_populates="episode",
        cascade="all, delete-orphan",
        uselist=False,
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="episode",
        cascade="all, delete-orphan",
    )


class EpisodeProcessing(Base):
    """Data produced by the per-episode steps.

    Separate from ``processing_steps``, which only tracks orchestration state.
    One row per episode, created by the first step that needs it.
    """

    __tablename__ = "episode_processing"

    episode_id: Mapped[int] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), primary_key=True
    )
    subtitles_available: Mapped[bool] = mapped_column(default=False)
    subtitles_language: Mapped[str | None] = mapped_column(String(20))
    anchor_s: Mapped[int | None]
    anchor_kinds: Mapped[str | None] = mapped_column(String(50))
    anchor_state: Mapped[str | None] = mapped_column(String(20))
    anchor_evidence: Mapped[str | None] = mapped_column(String(500))
    tail_s: Mapped[int | None]
    window_start_s: Mapped[int | None]
    window_origin: Mapped[str | None] = mapped_column(String(20))
    transcription_service: Mapped[str | None] = mapped_column(String(20))
    transcription_model: Mapped[str | None] = mapped_column(String(50))
    transcribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extraction_model: Mapped[str | None] = mapped_column(String(50))
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declared_count: Mapped[int | None]
    extraction_complete: Mapped[bool | None]
    extraction_warnings: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    episode: Mapped[Episode] = relationship(back_populates="processing")


class Recommendation(Base):
    """A work mentioned as a recommendation in one episode."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    #: Resolved by enrichment.
    work_id: Mapped[int | None] = mapped_column(
        ForeignKey("works.id", ondelete="SET NULL")
    )
    type: Mapped[str] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(20), default="extracted")
    mentioned_title: Mapped[str] = mapped_column(String(500))
    #: *Internal.* Orthographic/phonetic fix of the mentioned title, same work
    #: and language, only when the transcription looks broken. Never a new guess.
    corrected_title: Mapped[str | None] = mapped_column(String(500))
    probable_title: Mapped[str | None] = mapped_column(String(500))
    related_mentions: Mapped[str | None] = mapped_column(String(1000))
    confidence: Mapped[str] = mapped_column(String(10))
    #: Release year, stored only when it is said explicitly in the audio (never
    #: inferred). Used to break ties between same-title works during enrichment.
    year: Mapped[int | None]
    #: *Internal.* JSON list of alternative titles the host stated for this same
    #: work (translations, "también conocida como X"). Only when said, never inferred.
    alternate_titles: Mapped[str | None] = mapped_column(Text)
    #: *Internal.* A phrase the host used to tell this work apart ("la más
    #: viejita", "la coreana", "la del 2007"). Never inferred, never published.
    disambiguation: Mapped[str | None] = mapped_column(String(500))
    mention_s: Mapped[int | None]
    mentioned_platform: Mapped[str | None] = mapped_column(String(200))
    match_score: Mapped[float | None] = mapped_column(Float)
    match_note: Mapped[str | None] = mapped_column(String(100))
    decided_by: Mapped[str] = mapped_column(String(10), default="automatic")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    episode: Mapped[Episode] = relationship(back_populates="recommendations")
    work: Mapped["Work | None"] = relationship()
    candidates: Mapped[list["Candidate"]] = relationship(
        back_populates="recommendation",
        cascade="all, delete-orphan",
    )


class Work(Base):
    """A catalog work resolved against TMDB or IGDB."""

    __tablename__ = "works"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_works_source_external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(10))
    external_id: Mapped[str] = mapped_column(String(50))
    official_title: Mapped[str] = mapped_column(String(500))
    original_title: Mapped[str | None] = mapped_column(String(500))
    year: Mapped[int | None]
    genres: Mapped[str | None] = mapped_column(String(500))
    original_language: Mapped[str | None] = mapped_column(String(10))
    origin_country: Mapped[str | None] = mapped_column(String(5))
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(1000))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    data_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Candidate(Base):
    """A possible match stored for review."""

    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendations.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(10))
    type: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(500))
    year: Mapped[int | None]
    image_url: Mapped[str | None] = mapped_column(String(1000))
    score: Mapped[float] = mapped_column(Float)
    origin: Mapped[str] = mapped_column(String(20), default="api")
    chosen: Mapped[bool] = mapped_column(default=False)

    recommendation: Mapped[Recommendation] = relationship(
        back_populates="candidates"
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
