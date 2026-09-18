"""justificativa obrigatoria ao resolver chamado com SLA violado

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-09-08

Resolver chamado cujo prazo estourou passa a exigir uma justificativa escrita.
Esta revision so cria a coluna onde ela mora; a regra que a torna obrigatoria
vive na API.

NASCE NULA, e assim fica para todo chamado que ja existe. A exigencia e
PROSPECTIVA: vale para resolucao daqui em diante. Preencher retroativamente
seria inventar motivo que ninguem escreveu -- e chamado ja resolvido nao tem
quem justifique.

Por isso tambem nao ha `server_default` nem NOT NULL: nulo aqui significa
"resolvido antes da regra existir, ou resolvido dentro do prazo", e essas duas
situacoes sao legitimas e permanentes. Uma coluna NOT NULL com default vazio
apagaria a diferenca entre "nao precisou" e "nao preencheu".

O downgrade derruba a coluna e perde as justificativas escritas. Nao ha para
onde guarda-las num schema que nao tem o campo.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("sla_breach_justification", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tickets", "sla_breach_justification")
