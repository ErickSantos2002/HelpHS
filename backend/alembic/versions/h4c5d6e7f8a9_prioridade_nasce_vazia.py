"""prioridade nasce vazia

Revision ID: h4c5d6e7f8a9
Revises: g3b4c5d6e7f8
Create Date: 2026-09-22

O chamado passa a nascer **sem prioridade**. Quem a define é técnico ou
administrador, na triagem — o cliente não escolhe a própria urgência.

Só isto: `tickets.priority` deixa de ser `NOT NULL`.

SEM BACKFILL
------------
Nenhuma linha é escrita no caminho de ida. Chamado antigo mantém exatamente a
prioridade que tem, inclusive os que receberam `medium` por ser o default da
aplicação — a regra nova é prospectiva e não reescreve o passado (ver
`docs/decisoes-e-regras.md`). Quem quiser separar "média de verdade" de "média
por omissão" no histórico precisa de um script avulso e de uma decisão que não
é esta.

Não havia `DEFAULT` no banco para remover: a coluna nasceu apenas `NOT NULL`
(revision `75ec9d264ccb`), e o `medium` vinha do `default=` do ORM, que só vale
no INSERT. O default sai junto no `models.py`.

O índice `ix_tickets_priority` e o composto `ix_tickets_status_priority`
continuam válidos: no PostgreSQL o B-tree indexa `NULL`, então o filtro por
prioridade e a busca por "sem prioridade" seguem servidos pelos mesmos índices.

O DOWNGRADE escreve
-------------------
E é a única forma de ele existir. Voltar o `NOT NULL` com linhas nulas falha, e
os chamados nulos são justamente os que o código antigo teria criado como
`medium` — o downgrade carimba `medium` neles e restaura o mundo anterior tal
como ele era. Não é correção de dado histórico: é a reconstrução do invariante
que a coluna tinha antes desta revision.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "h4c5d6e7f8a9"
down_revision: str | None = "g3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENUM = sa.Enum("critical", "high", "medium", "low", name="ticketpriority")


def upgrade() -> None:
    op.alter_column("tickets", "priority", existing_type=_ENUM, nullable=True)


def downgrade() -> None:
    op.execute("UPDATE tickets SET priority = 'medium' WHERE priority IS NULL")
    op.alter_column("tickets", "priority", existing_type=_ENUM, nullable=False)
