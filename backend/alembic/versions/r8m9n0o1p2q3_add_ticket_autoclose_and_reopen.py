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

DOWNGRADE: só passa se não existir nenhuma linha de sistema. Havendo qualquer
uma, ele ABORTA — repor o NOT NULL exigiria apagar trilha de auditoria, e essa
decisão não é da migration.
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
        sa.Column("auto_closed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
    # Até 02/09/2026 esta função começava com
    #
    #     DELETE FROM ticket_history WHERE user_id IS NULL
    #
    # para conseguir repor o NOT NULL logo abaixo. Só que essas linhas não são
    # desta migration: são o que a APLICAÇÃO grava para representar ação do
    # sistema (`ticket_lifecycle.py`, fechamento automático, e a Helô). Um
    # rollback de emergência apagava a prova do que o sistema fez, calado, e o
    # re-upgrade não traz nenhuma de volta.
    #
    # A política é falhar antes de destruir. Ver docs/decisoes-e-regras.md,
    # "Migrations: a política do caminho de volta", regra 3.
    bloqueiam = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM ticket_history WHERE user_id IS NULL"))
        .scalar_one()
    )
    if bloqueiam:
        raise RuntimeError(
            f"ROLLBACK BLOQUEADO: {bloqueiam} linha(s) de ticket_history com user_id nulo.\n"
            "\n"
            "São ação do SISTEMA — fechamento automático e Helô —, gravadas pela\n"
            "aplicação e não por esta migration. Repor o NOT NULL exigiria apagá-las,\n"
            "e isso destrói trilha de auditoria sem volta: o re-upgrade não recupera\n"
            "nenhuma.\n"
            "\n"
            "Este downgrade NÃO apaga e NÃO preenche com autor falso. A saída é\n"
            "manual — decida o que fazer com essas linhas antes de tentar de novo,\n"
            "ou reverta por restore de backup:\n"
            "\n"
            "    SELECT id, ticket_id, field, created_at\n"
            "      FROM ticket_history WHERE user_id IS NULL;\n"
        )

    op.alter_column("ticket_history", "user_id", existing_type=sa.UUID(), nullable=False)

    op.drop_index("ix_tickets_resolved_at", table_name="tickets")
    op.drop_column("tickets", "reopen_count")
    op.drop_column("tickets", "reopened_at")
    op.drop_column("tickets", "auto_closed")
    op.drop_column("tickets", "resolved_at")
