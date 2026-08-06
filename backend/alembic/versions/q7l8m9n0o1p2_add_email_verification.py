"""add email verification fields to users

Revision ID: q7l8m9n0o1p2
Revises: p6k7l8m9n0o1
Create Date: 2026-08-06

Quem já usa o sistema entra como verificado: a regra vale só para cadastros
novos, para não trancar ninguém do lado de fora.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "q7l8m9n0o1p2"
down_revision: str | None = "p6k7l8m9n0o1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Contas que já existem passam a valer como verificadas
    op.execute("UPDATE users SET email_verified = true, email_verified_at = NOW()")


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email_verified")
