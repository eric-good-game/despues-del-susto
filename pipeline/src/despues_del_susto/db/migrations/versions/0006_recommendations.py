"""Recommendation extraction.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("work_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("mentioned_title", sa.String(length=500), nullable=False),
        sa.Column("probable_title", sa.String(length=500), nullable=True),
        sa.Column("related_mentions", sa.String(length=1000), nullable=True),
        sa.Column("confidence", sa.String(length=10), nullable=False),
        sa.Column("mention_s", sa.Integer(), nullable=True),
        sa.Column("mentioned_platform", sa.String(length=200), nullable=True),
        sa.Column("decided_by", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recommendations_episode_id", "recommendations", ["episode_id"]
    )

    with op.batch_alter_table("episode_processing") as batch:
        batch.add_column(sa.Column("extraction_model", sa.String(length=50), nullable=True))
        batch.add_column(
            sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("declared_count", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("extraction_complete", sa.Boolean(), nullable=True)
        )
        batch.add_column(
            sa.Column("extraction_warnings", sa.String(length=500), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("episode_processing") as batch:
        batch.drop_column("extraction_warnings")
        batch.drop_column("extraction_complete")
        batch.drop_column("declared_count")
        batch.drop_column("extracted_at")
        batch.drop_column("extraction_model")
    op.drop_index("ix_recommendations_episode_id", table_name="recommendations")
    op.drop_table("recommendations")
