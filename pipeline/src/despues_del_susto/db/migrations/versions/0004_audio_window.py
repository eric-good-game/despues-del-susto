"""Audio window bookkeeping.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("episode_processing") as batch:
        batch.add_column(sa.Column("window_start_s", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("window_origin", sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("episode_processing") as batch:
        batch.drop_column("window_origin")
        batch.drop_column("window_start_s")
