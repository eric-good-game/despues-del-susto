"""Catalog works and match candidates.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "works",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column("official_title", sa.String(length=500), nullable=False),
        sa.Column("original_title", sa.String(length=500), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("genres", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=1000), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("data_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source", "external_id", name="uq_works_source_external_id"
        ),
    )

    op.create_table(
        "candidates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recommendation_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("image_url", sa.String(length=1000), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("origin", sa.String(length=20), nullable=False),
        sa.Column("chosen", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["recommendation_id"], ["recommendations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_candidates_recommendation_id", "candidates", ["recommendation_id"]
    )

    with op.batch_alter_table("recommendations", recreate="always") as batch:
        batch.add_column(sa.Column("match_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("match_note", sa.String(length=100), nullable=True))
        batch.create_foreign_key(
            "fk_recommendations_work_id",
            "works",
            ["work_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("recommendations", recreate="always") as batch:
        batch.drop_constraint("fk_recommendations_work_id", type_="foreignkey")
        batch.drop_column("match_note")
        batch.drop_column("match_score")
    op.drop_index("ix_candidates_recommendation_id", table_name="candidates")
    op.drop_table("candidates")
    op.drop_table("works")
