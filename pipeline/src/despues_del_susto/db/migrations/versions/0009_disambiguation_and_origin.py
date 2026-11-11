"""Disambiguation hint and work origin data.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("recommendations") as batch:
        batch.add_column(sa.Column("disambiguation", sa.String(length=500), nullable=True))
    with op.batch_alter_table("works") as batch:
        batch.add_column(sa.Column("original_language", sa.String(length=10), nullable=True))
        batch.add_column(sa.Column("origin_country", sa.String(length=5), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("works") as batch:
        batch.drop_column("origin_country")
        batch.drop_column("original_language")
    with op.batch_alter_table("recommendations") as batch:
        batch.drop_column("disambiguation")
