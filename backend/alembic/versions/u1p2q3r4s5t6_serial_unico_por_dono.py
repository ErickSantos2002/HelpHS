"""numero de serie unico por dono, nao no sistema inteiro

Revision ID: u1p2q3r4s5t6
Revises: t0o1p2q3r4s5
Create Date: 2026-08-21

A unicidade de `equipments.serial_number` era global. Empresas diferentes podem
ter aparelhos com o mesmo número — fabricantes repetem séries entre lotes e
linhas — e o 409 global era um oráculo: contava ao cliente que OUTRA empresa
tinha cadastrado aquele serial.

Passa a ser única por dono (`owner_id`). São DOIS índices porque, em SQL, NULL
não conflita com NULL: só o composto deixaria dois equipamentos sem dono com o
mesmo serial passarem em silêncio. O índice parcial fecha esse caso sem
depender de `NULLS NOT DISTINCT`, que exige Postgres 15.

O índice simples por serial fica, não-único: a busca de chamados por número de
série do equipamento usa essa coluna.

Sem backfill e sem risco no upgrade: a regra nova é estritamente mais fraca
que a antiga, então tudo que satisfazia a unicidade global satisfaz a nova.

O DOWNGRADE pode falhar: se depois do upgrade dois donos cadastrarem o mesmo
serial, recriar o índice global único recusa. É a natureza da volta, não um
bug — quem precisar voltar resolve os duplicados antes.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "u1p2q3r4s5t6"
down_revision: str | None = "t0o1p2q3r4s5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_equipments_serial_number", table_name="equipments")
    op.create_index("ix_equipments_serial_number", "equipments", ["serial_number"], unique=False)
    op.create_index(
        "uq_equipments_owner_serial", "equipments", ["owner_id", "serial_number"], unique=True
    )
    op.create_index(
        "uq_equipments_orphan_serial",
        "equipments",
        ["serial_number"],
        unique=True,
        postgresql_where=sa.text("owner_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_equipments_orphan_serial", table_name="equipments")
    op.drop_index("uq_equipments_owner_serial", table_name="equipments")
    op.drop_index("ix_equipments_serial_number", table_name="equipments")
    op.create_index("ix_equipments_serial_number", "equipments", ["serial_number"], unique=True)
