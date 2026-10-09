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

"Mais antigo" e por `equipments.created_at`, com `id` de desempate. Nao ha data
na `ticket_equipments`, entao o criterio e a idade do APARELHO, e nao a do
vinculo com o chamado -- a distincao importa para quem for ler o resultado de
um rollback.
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
    # MAIS ANTIGO, e os demais vinculos se perdem.
    #
    # Ate 02/09/2026 isto ordenava por `te.equipment_id`. O comentario dizia
    # "menor id" e o docstring dizia "mais antigo" -- e nenhuma das duas coisas
    # acontecia, porque `Equipment.id` e UUID v4: nao carrega cronologia
    # nenhuma. A escolha era aleatoria, com cara de criterio.
    #
    # `equipments.created_at` e o unico campo temporal disponivel aqui: a
    # `ticket_equipments` guarda so o par (ticket_id, equipment_id), sem data.
    # Entao "mais antigo" quer dizer o aparelho CADASTRADO ha mais tempo, e nao
    # o vinculado ao chamado ha mais tempo -- que e o que o docstring sempre
    # disse, e o que o SQL agora faz. O `, e.id` e desempate deterministico:
    # dois aparelhos cadastrados no mesmo instante nao podem devolver resultado
    # diferente a cada execucao.
    op.execute(
        """
        UPDATE tickets t
           SET equipment_id = (
               SELECT te.equipment_id
                 FROM ticket_equipments te
                 JOIN equipments e ON e.id = te.equipment_id
                WHERE te.ticket_id = t.id
                ORDER BY e.created_at, e.id
                LIMIT 1
           )
        """
    )

    op.drop_index("ix_ticket_equipments_equipment_id", table_name="ticket_equipments")
    op.drop_table("ticket_equipments")
