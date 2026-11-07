"""Episode sync bookkeeping.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("episodes") as batch:
        batch.add_column(sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("metadata_fetched_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("metadata_error", sa.String(length=2000), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("episodes") as batch:
        batch.drop_column("metadata_error")
        batch.drop_column("metadata_fetched_at")
        batch.drop_column("last_seen_at")
