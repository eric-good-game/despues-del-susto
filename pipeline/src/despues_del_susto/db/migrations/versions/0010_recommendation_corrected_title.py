"""Add a transcription-corrected title to recommendations.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("recommendations") as batch:
        batch.add_column(
            sa.Column("corrected_title", sa.String(length=500), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("recommendations") as batch:
        batch.drop_column("corrected_title")
