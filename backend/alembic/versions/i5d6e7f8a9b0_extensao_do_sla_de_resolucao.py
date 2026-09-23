"""extensao do sla de resolucao

Revision ID: i5d6e7f8a9b0
Revises: h4c5d6e7f8g9
Create Date: 2026-09-23

Técnico e administrador passam a poder prorrogar o prazo de RESOLUÇÃO, em dias
úteis, com justificativa pública. Três coisas entram no banco:

1. `tickets.sla_resolve_extension_total_min` — o acumulado de minutos úteis
   concedidos no ciclo atual. `NOT NULL DEFAULT 0`, então todo chamado que já
   existe nasce com zero sem escrita nenhuma.

2. `tickets.sla_resolve_effective_due_at` — o prazo efetivo MATERIALIZADO.

3. `ticket_sla_extensions` — uma linha por concessão.

POR QUE MATERIALIZAR O PRAZO EFETIVO
------------------------------------
O painel e os relatórios decidem violação em SQL agregado
(`count(...).filter(...)`), sem passar pelo motor. Eles comparavam
`sla_resolve_due_at < now()` — a coluna CRUA. Isso já ignorava
`sla_total_paused_ms` hoje, e ignoraria a extensão amanhã: um chamado
prorrogado apareceria "no prazo" na tela e "violado" no painel.

A coluna é escrita só por `atualiza_prazo_efetivo` e é função pura de três
campos persistidos — prazo base, pausa acumulada e extensão acumulada. A pausa
EM CURSO não participa, porque o motor nunca a considerou; é isso que permite
guardar o resultado em vez de recalcular a cada leitura.

O BACKFILL AQUI É CÁLCULO, NÃO CORREÇÃO DE DADO
-----------------------------------------------
A coluna nova precisa nascer preenchida, senão o painel leria NULL em todo
chamado antigo e pararia de contar violação — o oposto do que esta entrega
quer. O UPDATE abaixo copia `sla_resolve_due_at + sla_total_paused_ms`, que é
exatamente o prazo efetivo de quem ainda não tem extensão (e ninguém tem, na
subida).

Isso NÃO é backfill de regra nova sobre o passado: nenhum prazo muda, nenhuma
decisão é reescrita. É a materialização de um valor que já era o que o motor
calculava — só não estava guardado. A soma é feita em SQL puro porque, sem
extensão, o prazo efetivo não envolve horário útil nenhum: é adição de
intervalo.

⚠️ **A conformidade do painel muda no deploy**, e é a intenção: chamados com
pausa passam a ser medidos pelo mesmo prazo que o chamado mostra. Ver "SLA" em
`docs/decisoes-e-regras.md`.

O DOWNGRADE não perde nada que não seja recalculável: derruba as três coisas, e
o prazo efetivo volta a ser o que o motor calcula em Python.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "i5d6e7f8a9b0"
down_revision: str | None = "h4c5d6e7f8g9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column(
            "sla_resolve_extension_total_min",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "tickets",
        sa.Column("sla_resolve_effective_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_tickets_sla_resolve_effective_due_at",
        "tickets",
        ["sla_resolve_effective_due_at"],
    )

    # O prazo efetivo de quem ainda não tem extensão: base + pausa acumulada.
    # `sla_total_paused_ms` é NOT NULL com default 0 no modelo, mas o
    # `coalesce` protege linha antiga que tenha escapado disso.
    op.execute(
        """
        UPDATE tickets
           SET sla_resolve_effective_due_at =
               sla_resolve_due_at
               + make_interval(secs => coalesce(sla_total_paused_ms, 0) / 1000.0)
         WHERE sla_resolve_due_at IS NOT NULL
        """
    )

    op.create_table(
        "ticket_sla_extensions",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("business_minutes", sa.Integer(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("previous_effective_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_effective_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_ticket_sla_extensions_ticket_id",
        "ticket_sla_extensions",
        ["ticket_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ticket_sla_extensions_ticket_id", table_name="ticket_sla_extensions")
    op.drop_table("ticket_sla_extensions")
    op.drop_index("ix_tickets_sla_resolve_effective_due_at", table_name="tickets")
    op.drop_column("tickets", "sla_resolve_effective_due_at")
    op.drop_column("tickets", "sla_resolve_extension_total_min")
