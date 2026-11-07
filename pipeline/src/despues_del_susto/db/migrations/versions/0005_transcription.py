"""Transcription bookkeeping.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("episode_processing") as batch:
        batch.add_column(sa.Column("transcription_service", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("transcription_model", sa.String(length=50), nullable=True))
        batch.add_column(
            sa.Column("transcribed_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("episode_processing") as batch:
        batch.drop_column("transcribed_at")
        batch.drop_column("transcription_model")
        batch.drop_column("transcription_service")
