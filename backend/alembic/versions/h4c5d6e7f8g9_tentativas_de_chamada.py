"""tentativas de chamada

Revision ID: h4c5d6e7f8g9
Revises: h4c5d6e7f8a9
Create Date: 2026-09-22

A tabela onde a telefonia passa a ter memória. **Uma linha é uma TENTATIVA**,
não uma chamada: ela nasce antes de existir chamada do lado do fornecedor, e
pode terminar sem que jamais saibamos se existiu.

Por que `provider_call_id` aceita NULL
--------------------------------------
Porque o estado mais perigoso da integração é justamente aquele em que não
temos o identificador. Um `ReadTimeout` depois do `POST /calls` deixa o
resultado indeterminado: a chamada pode ter sido criada e o telefone de alguém
pode ter tocado. Uma coluna NOT NULL tornaria esse caso **impossível de
registrar** — e é exatamente ele que precisa ser reconciliado depois, e o que
impede uma segunda tentativa às cegas.

Por que a coluna é `TEXT` e não `UUID`
---------------------------------------
A documentação oficial declara o tipo como `string` e mostra **dois formatos
para o mesmo campo**: `1PkXhmBsYAvr9legLB2d7BimT0Q` (27 caracteres, base62) na
referência da API, e `bdf199fa-f85b-4378-80cd-0ac28c1355e9` (UUID textual de
36) no guia de integração. O tipo nativo `UUID` do PostgreSQL **rejeitaria o
primeiro**. Tratamos o identificador como string opaca: sem validar formato,
sem validar comprimento, sem transformar. Quando o fornecedor confirmar o
formato real, estreitar é fácil; ter quebrado em produção por validar o que
ele nunca prometeu, não.

Por que `creation_status` é `String` com `CHECK`, e não enum nativo
--------------------------------------------------------------------
Custo de evolução, já medido nesta casa. Acrescentar valor a enum nativo exige
`ALTER TYPE ... ADD VALUE`, e o alembic daqui roda a cadeia inteira numa
transação só — o valor novo não pode ser citado em DDL posterior
(`UnsafeNewEnumValueUsageError`, a armadilha documentada na `g3b4c5d6e7f8`).
E remover valor custa recriar o tipo e converter toda coluna que o usa, como a
`f2a3b4c5d6e7` teve de fazer com `ticketcategory`. Esta máquina de estados
ainda vai crescer na Fase 2D, quando o webhook trouxer o estado telefônico.
Nascer com esse custo seria escolher errado sabendo.

Por que o pai é `h4c5d6e7f8a9`, e não `g3b4c5d6e7f8`
------------------------------------------------------
Esta revisão nasceu filha de `g3b4c5d6e7f8`. Enquanto ela era escrita, a frente
da triagem mesclou `h4c5d6e7f8a9` (prioridade nasce vazia) com o **mesmo pai** —
duas irmãs, e a cadeia composta passaria a ter DOIS heads, com
`alembic upgrade head` falhando no boot do contêiner. Como a branch nunca tinha
sido publicada, a correção foi reancorar aqui em vez de criar uma revisão de
merge: esta casa tem 38 revisões e nenhuma com dois pais.

O identificador `h4c5d6e7f8g9` foi MANTIDO de propósito. Ele se parece com o da
irmã, mas revision id aqui é opaco: não há gerador no `env.py`, não há
`rev_id` no `alembic.ini`, e a suposta sequência "cada caractere +1" quebra em
10 dos 37 pares da cadeia — a própria raiz é `75ec9d264ccb`, gerada pelo
alembic. Trocar o id só para ficar bonito reescreveria uma referência que os
testes já prendem, sem ganho funcional.

O que esta migration NÃO faz
-----------------------------
Não toca `users`, `tickets` nem `ticket_history`. Não faz backfill — não há
histórico de ligação para reescrever, e dado histórico nesta casa se corrige em
script avulso. Não acrescenta valor a `auditaction`. Não cria endpoint nem
chama ninguém: a Fase 2B é memória, e quem vai escrever nela é a 2C.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "h4c5d6e7f8g9"
down_revision: str | None = "h4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELA = "ticket_calls"

# Os mesmos cinco valores de `CallCreationStatus` em app/models/models.py. A
# lista é escrita aqui à mão, e não importada do model, porque migration que
# importa model passa a depender do código de hoje para reproduzir o schema de
# ontem — e o dia em que o enum mudar, esta revisão passaria a criar outra
# coisa do que criou.
_STATUS = ("pending", "confirmed", "rejected", "unavailable", "indeterminate")
_REGRA_STATUS = "creation_status IN (" + ", ".join(f"'{s}'" for s in _STATUS) + ")"
_REGRA_CONFIRMADA = "creation_status <> 'confirmed' OR provider_call_id IS NOT NULL"


def upgrade() -> None:
    op.create_table(
        _TABELA,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("initiated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider_call_id", sa.Text(), nullable=True),
        sa.Column("creation_status", sa.String(length=20), nullable=False),
        sa.Column("provider_http_status", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["initiated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(_REGRA_STATUS, name="ck_ticket_calls_status_conhecido"),
        sa.CheckConstraint(_REGRA_CONFIRMADA, name="ck_ticket_calls_confirmada_tem_id"),
    )
    op.create_index("ix_ticket_calls_ticket_id", _TABELA, ["ticket_id"])
    op.create_index("ix_ticket_calls_initiated_by_id", _TABELA, ["initiated_by_id"])
    op.create_index("ix_ticket_calls_ticket_created", _TABELA, ["ticket_id", "created_at"])
    # Único, e vários NULL convivem sob ele no PostgreSQL — que é o
    # comportamento desejado: toda tentativa sem identificador é distinta.
    op.create_index("uq_ticket_calls_provider_call_id", _TABELA, ["provider_call_id"], unique=True)


def downgrade() -> None:
    # Só o que esta revisão criou. Os índices saem com a tabela no PostgreSQL,
    # mas são removidos explicitamente para que o downgrade diga o que desfaz.
    op.drop_index("uq_ticket_calls_provider_call_id", table_name=_TABELA)
    op.drop_index("ix_ticket_calls_ticket_created", table_name=_TABELA)
    op.drop_index("ix_ticket_calls_initiated_by_id", table_name=_TABELA)
    op.drop_index("ix_ticket_calls_ticket_id", table_name=_TABELA)
    op.drop_table(_TABELA)
