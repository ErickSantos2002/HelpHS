"""historico de aceites lgpd

Revision ID: j6e7f8a9b0c1
Revises: i5d6e7f8a9b0
Create Date: 2026-09-24

Cria `lgpd_consents`: uma linha por aceite da Política de Privacidade (e dos
Termos de Uso, quando existirem), com a revisão aceita, a origem e o momento.
A seção 15 da política promete provar QUAL texto cada pessoa aceitou, e até
aqui o sistema guardava só `users.lgpd_consent` e `users.lgpd_consent_at` —
que revogar zerava.

A TABELA NASCE VAZIA, E ISSO É O CERTO
--------------------------------------
Não há backfill. Quem se cadastrou antes desta migration aceitou um texto que
ainda não existia: a revisão dessas pessoas é DESCONHECIDA, não "00". Criar uma
linha "00" para elas seria fabricar prova. A ausência de linha é o que fica
gravado, e é ela que dispara o re-aceite quando `LGPD_EXIGE_REACEITE` for
ligado.

`user_id` é `ON DELETE SET NULL` (decisão de 24/09/2026): excluir a conta não
apaga o registro de que houve aceite daquela revisão.

O DOWNGRADE derruba a tabela e perde o histórico gravado desde a subida — é o
único dado que só existe aqui. Descer esta revision em produção depois de
aceites reais exige salvar a tabela antes.

Desenho em `docs/superpowers/specs/2026-08-31-registro-da-revisao-aceita-design.md`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "j6e7f8a9b0c1"
down_revision: str | None = "i5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mesma regra do `CheckConstraint` do model — o autogenerate não compara CHECK,
# então a paridade é conferida em `test_lgpd_consents_postgres.py`.
_REGRA_ORIGEM = "origem IN ('auto_cadastro', 'criado_por_terceiro', 'alteracao_propria')"


def upgrade() -> None:
    op.create_table(
        "lgpd_consents",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("revisao_politica", sa.String(20), nullable=True),
        sa.Column("revisao_termos", sa.String(20), nullable=True),
        sa.Column("origem", sa.String(30), nullable=False),
        sa.Column(
            "concedido_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revogado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.CheckConstraint(_REGRA_ORIGEM, name="ck_lgpd_consents_origem_conhecida"),
    )
    op.create_index("ix_lgpd_consents_user_id", "lgpd_consents", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_lgpd_consents_user_id", table_name="lgpd_consents")
    op.drop_table("lgpd_consents")
