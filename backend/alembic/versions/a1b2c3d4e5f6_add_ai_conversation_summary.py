"""add ai_conversation_summary to tickets

Revision ID: a1b2c3d4e5f6
Revises: 75ec9d264ccb
Create Date: 2026-04-06 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "75ec9d264ccb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("ai_conversation_summary", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tickets", "ai_conversation_summary")
