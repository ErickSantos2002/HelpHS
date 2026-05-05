"""add company_cep and company_address to users

Revision ID: h8c9d0e1f2g3
Revises: g7b8c9d0e1f2
Create Date: 2026-05-04

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "h8c9d0e1f2g3"
down_revision: str | None = "g7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("company_cep", sa.String(9), nullable=True))
    op.add_column("users", sa.Column("company_address", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "company_address")
    op.drop_column("users", "company_cep")
