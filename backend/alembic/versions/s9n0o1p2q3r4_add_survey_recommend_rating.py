"""nota de recomendacao da empresa na pesquisa de satisfacao

Revision ID: s9n0o1p2q3r4
Revises: r8m9n0o1p2q3
Create Date: 2026-08-07

A coluna nasce nullable e assim permanece: as avaliacoes ja enviadas nao tem
essa resposta e nao ha como inventa-la. Os relatorios ignoram os nulos ao
calcular a media, em vez de trata-los como nota zero.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "s9n0o1p2q3r4"
down_revision: str | None = "r8m9n0o1p2q3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "satisfaction_surveys",
        sa.Column("recommend_rating", sa.SmallInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("satisfaction_surveys", "recommend_rating")
