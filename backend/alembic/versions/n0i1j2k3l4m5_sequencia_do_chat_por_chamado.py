"""sequencia das mensagens do chat por chamado

Revision ID: n0i1j2k3l4m5
Revises: m9h0i1j2k3l4
Create Date: 2026-11-04

F1-B-04c. `created_at` é carimbado ANTES do commit — antes da Helô, que pode
levar até 40 s —, e por isso a ordem de `created_at` não é a ordem em que as
mensagens ficam visíveis. Quem relê "o que veio depois do que eu já vi" por
`created_at` perde a mensagem que comitou tarde (medido na prova de conceito
de 04/11/2026). Esta revision cria a numeração que segue a ORDEM DE COMMIT:

- `tickets.chat_seq` (BIGINT, NOT NULL, DEFAULT 0): o contador do chamado;
- `chat_messages.seq` (BIGINT, nula): o número da mensagem no chamado;
- `uq_chat_messages_seq`: único em (ticket_id, seq), só onde há número;
- `chat_seq_corte`: UMA linha, com o instante em que esta revision terminou.

O MARCO DO CORTE
----------------
`chat_seq_corte.migrada_em` é `clock_timestamp()` no ÚLTIMO comando daqui.
Nesse ponto esta transação já segura `ACCESS EXCLUSIVE` em `chat_messages`
(o `ADD COLUMN`), e só o solta no commit: nenhuma mensagem comita entre o
marco e o fim da migration. Logo, mensagem com `seq` nula e `created_at` a
partir do marco foi gravada DEPOIS — por uma imagem antiga, durante a troca
ou num recuo. É o que a aplicação consulta antes de anunciar o modo
incremental (`app/services/chat_sequencia.py`), e o ponto de partida do
script de recuperação. Fica no banco, e não numa variável de ambiente, para
sobreviver a recuo de imagem e voltar junto com um backup.

Quem numera é a aplicação (`app/services/chat_sequencia.py`), no fim da
transação do envio, travando a linha do chamado com o próprio UPDATE do
contador. Não há gatilho: a decisão da Sessão 0 (04/11/2026) foi a estratégia
B, atribuição explícita pela aplicação.

NADA MUDA PARA AS MENSAGENS QUE JÁ EXISTEM
------------------------------------------
- `ADD COLUMN ... DEFAULT 0` com default constante só altera o catálogo no
  PostgreSQL 11+: a tabela de chamados não é reescrita.
- `seq` nasce nula e assim fica nas mensagens antigas, para sempre: o
  histórico NÃO é numerado, nem aqui nem por script (decisão definitiva da
  Sessão 0, 04/11/2026). Mensagem sem número continua no histórico
  (`before`/`offset`) e só não volta pela consulta incremental `after_seq`.
- O índice parcial nasce vazio — nenhuma linha tem `seq` ainda.

POR QUE SEM `CREATE INDEX CONCURRENTLY`
---------------------------------------
Os mesmos motivos de `m9h0i1j2k3l4`: o `env.py` roda as revisions pendentes
numa transação só, um `CONCURRENTLY` falho deixa índice inválido que derruba o
boot seguinte, e a montagem aqui é uma varredura que não acha linha nenhuma
com `seq`. A varredura segura escrita em `chat_messages` durante a montagem;
o tempo dela foi medido na F1-B-04c (notas da sessão).

ROLLBACK
--------
⚠️ Uma imagem que não contém ESTE arquivo não sobe num banco que já passou por
ele (`start.sh`: `alembic upgrade head` com `set -e`).

- O rollback PREFERENCIAL mantém esta revision: imagem com o código anterior
  E os arquivos desta revision e da `m9h0i1j2k3l4` (produção está em
  `l8g9h0i1j2k3`). O código anterior ignora as duas colunas e grava `seq` nula
  — o índice parcial aceita. As mensagens dessa janela ficam sem número e não
  voltam por `after_seq` até `scripts/numera_mensagens_sem_seq.py` rodar.
- O DOWNGRADE não é estratégia de rollback e só roda com autorização
  específica. Ele apaga a numeração inteira: nenhuma mensagem se perde, mas
  toda âncora de cliente fica maior que o contador recriado, e o cliente
  precisa da ressincronização integral (409 do `after_seq`).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "n0i1j2k3l4m5"
down_revision: str | None = "m9h0i1j2k3l4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("chat_seq", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("chat_messages", sa.Column("seq", sa.BigInteger(), nullable=True))
    op.create_index(
        "uq_chat_messages_seq",
        "chat_messages",
        ["ticket_id", "seq"],
        unique=True,
        postgresql_where=sa.text("seq IS NOT NULL"),
    )
    op.create_table(
        "chat_seq_corte",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("migrada_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_chat_seq_corte_uma_linha"),
    )
    # O ÚLTIMO comando, de propósito — ver "O MARCO DO CORTE" acima.
    op.execute("INSERT INTO chat_seq_corte (id, migrada_em) VALUES (1, clock_timestamp())")


def downgrade() -> None:
    op.drop_table("chat_seq_corte")
    op.drop_index("uq_chat_messages_seq", table_name="chat_messages")
    op.drop_column("chat_messages", "seq")
    op.drop_column("tickets", "chat_seq")
