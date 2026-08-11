"""varios equipamentos por chamado

Revision ID: t0o1p2q3r4s5
Revises: s9n0o1p2q3r4
Create Date: 2026-08-10

O chamado aceitava um unico equipamento. Na pratica o cliente costuma abrir um
chamado so para varios aparelhos do mesmo produto, e era obrigado a repetir o
chamado ou a citar os seriais na descricao — onde nada disso e pesquisavel.

A coluna tickets.equipment_id sai de cena para nao existirem duas verdades
sobre a mesma informacao. O backfill leva o vinculo atual para a tabela nova
antes de remove-la, e o downgrade refaz o caminho inverso escolhendo o
equipamento mais antigo de cada chamado.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "t0o1p2q3r4s5"
down_revision: str | None = "s9n0o1p2q3r4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ticket_equipments",
        sa.Column(
            "ticket_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "equipment_id",
            UUID(as_uuid=True),
            sa.ForeignKey("equipments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index("ix_ticket_equipments_equipment_id", "ticket_equipments", ["equipment_id"])

    op.execute(
        """
        INSERT INTO ticket_equipments (ticket_id, equipment_id)
        SELECT id, equipment_id FROM tickets WHERE equipment_id IS NOT NULL
        """
    )

    op.drop_column("tickets", "equipment_id")


def downgrade() -> None:
    op.add_column("tickets", sa.Column("equipment_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "tickets_equipment_id_fkey", "tickets", "equipments", ["equipment_id"], ["id"]
    )
    # Um chamado com varios equipamentos nao cabe na coluna unica: fica com o
    # de menor id, e os demais vinculos se perdem.
    op.execute(
        """
        UPDATE tickets t
           SET equipment_id = (
               SELECT te.equipment_id
                 FROM ticket_equipments te
                WHERE te.ticket_id = t.id
                ORDER BY te.equipment_id
                LIMIT 1
           )
        """
    )

    op.drop_index("ix_ticket_equipments_equipment_id", table_name="ticket_equipments")
    op.drop_table("ticket_equipments")
