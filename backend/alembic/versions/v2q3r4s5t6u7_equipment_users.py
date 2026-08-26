"""aparelho passa a ter usuarios, nao so um dono

Revision ID: v2q3r4s5t6u7
Revises: u1p2q3r4s5t6
Create Date: 2026-08-26

O mesmo aparelho físico é usado por mais de uma pessoa. Hoje isso vira duas
linhas em `equipments`, cada uma se achando dona, e nenhuma sabe da outra —
`owner_id` é um campo só.

Esta revision é ADITIVA de propósito: cria a tabela e copia os vínculos que já
existem. Nenhum endpoint passa a usá-la aqui, nenhum comportamento muda, e por
isso ela não pode derrubar o boot — que é como as migrations rodam neste
projeto (`start.sh`: alembic upgrade head a cada boot do container).

O que ela NÃO faz, e a razão:

- **Não cria o `UNIQUE (product_id, serial_number)`.** Índice único falha na
  criação se o banco já tiver duplicata, e a duplicata é justamente o caso que
  motivou a mudança. Antes disso é preciso rodar
  `scripts/diagnostico_empresa_aparelho.py` contra produção e fundir o que ele
  apontar — fusão é decisão humana: dois donos distintos são o aparelho
  compartilhado de verdade; duas linhas do mesmo dono são cadastro repetido.
- **Não mexe em `owner_id`.** Ele passa a significar "quem cadastrou" — quem
  edita o registro —, e continua sendo lido pelos mesmos lugares de sempre.

O backfill copia `owner_id` para a tabela nova. Órfãos (`owner_id IS NULL`)
ficam sem nenhuma linha, que é a leitura correta: aparelho sem dono é aparelho
sem usuário conhecido.

O DOWNGRADE derruba a tabela e perde os vínculos que existirem além do
`owner_id` — os que foram acrescentados depois. É a natureza da volta: a
informação nova não tem para onde voltar num modelo que só comporta um dono.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "v2q3r4s5t6u7"
down_revision: str | None = "u1p2q3r4s5t6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "equipment_users",
        sa.Column("equipment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("equipment_id", "user_id"),
    )

    # Backfill dos vínculos que já existem. `ON CONFLICT DO NOTHING` deixa a
    # revision idempotente: reaplicar depois de um rollback parcial não estoura
    # na chave primária composta.
    op.execute(
        """
        INSERT INTO equipment_users (equipment_id, user_id, created_at)
             SELECT id, owner_id, created_at
               FROM equipments
              WHERE owner_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("equipment_users")
