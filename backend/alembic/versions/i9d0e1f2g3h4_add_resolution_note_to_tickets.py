"""add resolution_note to tickets

Revision ID: i9d0e1f2g3h4
Revises: h8c9d0e1f2g3
Create Date: 2026-05-04

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "i9d0e1f2g3h4"
down_revision: str | None = "h8c9d0e1f2g3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("resolution_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "resolution_note")
