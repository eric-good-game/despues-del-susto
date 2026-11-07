"""Per-episode data produced by the pipeline steps.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "episode_processing",
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("subtitles_available", sa.Boolean(), nullable=False),
        sa.Column("subtitles_language", sa.String(length=20), nullable=True),
        sa.Column("anchor_s", sa.Integer(), nullable=True),
        sa.Column("anchor_kinds", sa.String(length=50), nullable=True),
        sa.Column("anchor_state", sa.String(length=20), nullable=True),
        sa.Column("anchor_evidence", sa.String(length=500), nullable=True),
        sa.Column("tail_s", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("episode_id"),
    )


def downgrade() -> None:
    op.drop_table("episode_processing")
