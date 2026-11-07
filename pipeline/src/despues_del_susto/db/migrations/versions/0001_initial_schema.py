"""Initial schema: episodes and processing steps.

Revision ID: 0001
Revises:
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "episodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_s", sa.Integer(), nullable=True),
        sa.Column("thumbnail_url", sa.String(length=1000), nullable=True),
        sa.Column("playlist_position", sa.Integer(), nullable=True),
        sa.Column("availability", sa.String(length=20), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_episodes_video_id", "episodes", ["video_id"], unique=True)

    op.create_table(
        "processing_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("step", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=2000), nullable=True),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "episode_id", "step", name="uq_processing_steps_episode_step"
        ),
    )
    op.create_index(
        "ix_processing_steps_episode_id", "processing_steps", ["episode_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_processing_steps_episode_id", table_name="processing_steps")
    op.drop_table("processing_steps")
    op.drop_index("ix_episodes_video_id", table_name="episodes")
    op.drop_table("episodes")
