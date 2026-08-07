"""fechamento automatico (RN-005) e reabertura de chamado (RN-006)

Revision ID: r8m9n0o1p2q3
Revises: q7l8m9n0o1p2
Create Date: 2026-08-07

`resolved_at` guarda o momento em que o chamado entrou em Resolvido e é a
referência dos dois prazos. Não dá para usar `closed_at` no lugar dele porque
`closed_at` é reescrito quando o chamado passa para Fechado — o relógio da
reabertura reiniciaria sozinho.

Backfill: os chamados que já estão resolvidos/fechados recebem
`resolved_at = closed_at`. Sem isso eles ficariam de fora da rotina de
fechamento automático para sempre.

`ticket_history.user_id` passa a aceitar NULL para representar o que o próprio
sistema fez — o fechamento automático não tem autor humano, e apontá-lo para um
administrador qualquer registraria no histórico uma ação que ninguém praticou.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "r8m9n0o1p2q3"
down_revision: str | None = "q7l8m9n0o1p2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "tickets",
        sa.Column(
            "auto_closed", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column("tickets", sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "tickets",
        sa.Column("reopen_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_tickets_resolved_at", "tickets", ["resolved_at"])

    op.execute(
        """
        UPDATE tickets
           SET resolved_at = closed_at
         WHERE closed_at IS NOT NULL
           AND status::text IN ('resolved', 'closed')
        """
    )

    op.alter_column("ticket_history", "user_id", existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM ticket_history WHERE user_id IS NULL")
    op.alter_column("ticket_history", "user_id", existing_type=sa.UUID(), nullable=False)

    op.drop_index("ix_tickets_resolved_at", table_name="tickets")
    op.drop_column("tickets", "reopen_count")
    op.drop_column("tickets", "reopened_at")
    op.drop_column("tickets", "auto_closed")
    op.drop_column("tickets", "resolved_at")
