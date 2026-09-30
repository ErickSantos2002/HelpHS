"""outbox de email

Revision ID: ae3cf7068dd6
Revises: f7a8b9c0d1e2
Create Date: 2026-09-29

Fase 3A — a tabela que torna o envio de e-mail durável. Uma linha e uma
PROMESSA de envio, nao o envio em si: o worker
(`app/services/email_outbox.py`) tenta, registra o desfecho e decide se tenta
de novo.

Por que nenhum call site real grava aqui ainda
-----------------------------------------------
Esta migration so cria estrutura. `notifications.py` continua mandando e-mail
do jeito que manda hoje (`commit_e_notificar` -> `asyncio.create_task`,
fire-and-forget); os e-mails de conta/autenticacao continuam via
`BackgroundTasks`. A tabela fica vazia em producao ate a Fase 3B migrar o
primeiro disparador de verdade. Sem backfill de proposito: nao ha envio
historico para reconstruir.

Por que nao guarda destinatario, assunto ou corpo
---------------------------------------------------
A auditoria da Fase 3 mediu que os ~20 pontos de disparo hoje convergem em
duas funcoes (`notify`, `notifica_audiencia`), e tudo que elas recebem ja e
persistido em `notifications` primeiro: `title`/`message`/`data` reconstroem
assunto e corpo em tempo de envio, e `user_id -> users.email` da o
destinatario. Duplicar qualquer um desses campos aqui criaria uma SEGUNDA
copia de dado pessoal — endereco, e possivelmente o titulo de um chamado
escrito pelo cliente — numa tabela nova, sem necessidade nenhuma. Esta tabela
guarda so ESTADO OPERACIONAL.

`notification_id` e UNIQUE, com FK `ON DELETE CASCADE`
--------------------------------------------------------
No maximo uma linha de outbox por notificacao. E o `CASCADE` espelha o
precedente ja corrigido em `notifications.user_id -> users.id`
(migration da Fase de exclusao de usuario, PR #64): apagar a notificacao nao
pode deixar uma linha de outbox orfa tentando mandar e-mail para um evento que
nao existe mais.

Por que `status` e `String` com CHECK, e nao enum nativo
------------------------------------------------------------
Mesma razao ja registrada em `sla_alert_events.alert_kind` (migration
`f7a8b9c0d1e2`): acrescentar um estado novo a um enum nativo do Postgres exige
`ALTER TYPE ... ADD VALUE`, e essa cadeia de migrations roda inteira numa
transacao so — o valor novo nao pode ser citado em DDL posterior na mesma
migration que o cria. `String` + `CHECK` nao tem essa amarra.

O indice parcial
-----------------
`ix_email_outbox_pending_next_attempt` cobre só `WHERE status = 'pending'` — e
exatamente a consulta do hot path do worker
(`status='pending' AND next_attempt_at <= now()`). As linhas `sent`/`dead`, que
tendem a ser a maioria com o tempo, nunca entram nele.

O que esta migration NAO faz
------------------------------
Nao toca `notifications`, `send_email` nem nenhum router. Nao migra call site
nenhum. Nao mexe em `sla_warning`. Nao faz backfill.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "ae3cf7068dd6"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELA = "email_outbox"


def upgrade() -> None:
    op.create_table(
        _TABELA,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_by", sa.String(length=120), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'sent', 'dead')",
            name="ck_email_outbox_status_conhecido",
        ),
    )
    op.create_index(
        "uq_email_outbox_notification_id",
        _TABELA,
        ["notification_id"],
        unique=True,
    )
    op.create_index(
        "ix_email_outbox_pending_next_attempt",
        _TABELA,
        ["next_attempt_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_email_outbox_pending_next_attempt", table_name=_TABELA)
    op.drop_index("uq_email_outbox_notification_id", table_name=_TABELA)
    op.drop_table(_TABELA)
