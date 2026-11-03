"""idempotencia do envio de mensagem no chat

Revision ID: m9h0i1j2k3l4
Revises: l8g9h0i1j2k3
Create Date: 2026-11-03

D4 da F1-B-04a. Uma mensagem reenviada com a mesma chave (`client_message_id`)
pela mesma pessoa no mesmo chamado devolve a que já foi gravada, em vez de
gravar outra. Esta revision cria:

- `chat_messages.client_message_id` (UUID, nula): a chave, gerada por quem envia;
- `chat_messages.client_message_fingerprint` (64 caracteres, nula): o SHA-256 do
  que foi pedido, para recusar a chave reaproveitada com outro conteúdo;
- `ck_chat_messages_chave_com_impressao`: as duas nascem e morrem juntas;
- `uq_chat_messages_envio`: único em (ticket_id, sender_id, client_message_id),
  só onde há chave. É ele, e não o código, a garantia contra o envio duplicado.

NADA MUDA PARA AS MENSAGENS QUE JÁ EXISTEM
------------------------------------------
As duas colunas nascem nulas, sem `server_default`: o PostgreSQL só altera o
catálogo, não reescreve a tabela. Nenhuma linha antiga ganha chave, e o índice
parcial nasce vazio. Não há backfill: mensagem antiga não tem chave a deduzir.

POR QUE SEM `CREATE INDEX CONCURRENTLY`
---------------------------------------
Avaliado e recusado:

- o `env.py` roda TODAS as revisions pendentes numa transação só, e o
  `CONCURRENTLY` não roda dentro de transação. O `autocommit_block` resolveria
  comitando no meio, e um deploy que pulasse várias revisions deixaria de
  ser atômico por causa desta;
- se o `CONCURRENTLY` falha, sobra um índice INVÁLIDO com o mesmo nome, e o
  `upgrade` seguinte no boot do contêiner morre em "already exists";
- o ganho seria não bloquear escrita durante a montagem do índice, e aqui a
  montagem é uma leitura da tabela que não acha nenhuma linha com chave. O
  `ADD COLUMN` logo antes já pede o bloqueio exclusivo de qualquer jeito;
- o repositório já cria índice único parcial assim (`x4s5t6u7v8w9`,
  `u1p2q3r4s5t6`).

O DOWNGRADE apaga o índice, a regra e as duas colunas. Perde só as chaves
gravadas desde a subida; nenhuma mensagem é apagada.

⚠️ VOLTAR A IMAGEM ANTERIOR SEM DESCER O BANCO DERRUBA O BOOT. O `start.sh`
roda `alembic upgrade head` com `set -e`, e o código anterior não conhece esta
revision: "Can't locate revision identified by 'm9h0i1j2k3l4'" (medido em
03/11/2026). As duas saídas, ambas medidas:

- descer ANTES, com a imagem nova ainda no ar
  (`alembic downgrade l8g9h0i1j2k3`), e só então subir a anterior;
- ou reverter o código MANTENDO este arquivo: as colunas ficam, nulas, e o
  código anterior grava as duas nulas, o que a regra aceita.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "m9h0i1j2k3l4"
down_revision: str | None = "l8g9h0i1j2k3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A mesma regra do `CheckConstraint` do model. O autogenerate não compara
# CHECK; a paridade é conferida em `test_chat_idempotencia_postgres.py`.
_REGRA_CHAVE = "(client_message_id IS NULL) = (client_message_fingerprint IS NULL)"


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("client_message_id", sa.UUID(), nullable=True))
    op.add_column(
        "chat_messages",
        sa.Column("client_message_fingerprint", sa.String(64), nullable=True),
    )
    op.create_check_constraint(
        "ck_chat_messages_chave_com_impressao", "chat_messages", _REGRA_CHAVE
    )
    op.create_index(
        "uq_chat_messages_envio",
        "chat_messages",
        ["ticket_id", "sender_id", "client_message_id"],
        unique=True,
        postgresql_where=sa.text("client_message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_chat_messages_envio", table_name="chat_messages")
    op.drop_constraint("ck_chat_messages_chave_com_impressao", "chat_messages", type_="check")
    op.drop_column("chat_messages", "client_message_fingerprint")
    op.drop_column("chat_messages", "client_message_id")
