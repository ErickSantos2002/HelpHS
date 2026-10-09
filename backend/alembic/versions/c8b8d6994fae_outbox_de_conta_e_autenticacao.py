"""outbox de conta e autenticacao

Revision ID: c8b8d6994fae
Revises: ae3cf7068dd6
Create Date: 2026-09-30

Fase 3C — generaliza `email_outbox` (Fase 3A/3B) para aceitar uma SEGUNDA
origem, sem criar uma segunda tabela nem um segundo worker: os e-mails de
conta/autenticacao (`verification`, `password_reset`, `account_exists`), que
nunca tiveram `Notification` por baixo.

Por que generalizar em vez de criar `account_email_outbox`
------------------------------------------------------------
A auditoria da Fase 3C mediu que os tres eventos SEMPRE tem `user_id`
disponivel no momento do enqueue -- nenhum precisa de uma linha `Notification`
nem de um desenho de schema proprio. Duas tabelas dobrariam a maquina de
estado (retry, backoff, stale processing, `FOR UPDATE SKIP LOCKED`) sem
ganhar nada: a MESMA maquina, ja em producao desde a Fase 3A, serve as duas
origens.

O que muda no schema
---------------------
`notification_id` deixa de ser NOT NULL. Ganham `user_id` (FK `users.id`,
`ON DELETE CASCADE`), `event_type` (string + CHECK, mesma convencao de
`status`) e `dedup_key` (UNIQUE quando preenchido). Uma CHECK garante que
toda linha e OU Notification (so `notification_id`) OU Account (so
`user_id`+`event_type`+`dedup_key`) -- nunca as duas, nunca nenhuma.

Por que nao persiste token, senha, e-mail, subject ou corpo
---------------------------------------------------------------
Mesma disciplina da Fase 3A: o worker reconstroi tudo a partir do `User`
carregado por `user_id`, no momento do envio -- inclusive o JWT de
verificacao/reset, gerado ali, nunca gravado. A auditoria da Fase 3C provou
que isso e seguro: a validacao dos dois tokens compara o ESTADO embutido
contra o estado atual do usuario no momento do clique, nao contra um registro
de "qual foi o ultimo token emitido" -- multiplos tokens validos para o mesmo
usuario ja coexistem hoje, antes desta fase.

Por que `dedup_key`, e nao `UNIQUE(user_id, event_type)`
------------------------------------------------------------
`UNIQUE(user_id, event_type)` impediria um segundo pedido legitimo de reset
de senha dias depois do primeiro. `dedup_key` e derivada de
`event_type:user_id:intent_id`, onde `intent_id` nasce no chamador (o router)
a cada PEDIDO -- a mesma intencao (retry tecnico, chamada duplicada) reusa o
mesmo `intent_id` e colide na UNIQUE; um pedido novo tem `intent_id` novo e
passa.

Seguranca contra a producao ja rodando
-----------------------------------------
Nenhuma linha existente e tocada: `ADD COLUMN ... NULL` nao reescreve linhas
no Postgres moderno, e as linhas de hoje (so `notification_id` preenchido)
ja satisfazem o primeiro ramo da CHECK sem precisar de backfill. A CHECK
nasce `NOT VALID` (sem lock de leitura da tabela inteira) e e validada logo
em seguida, na MESMA migration, com `VALIDATE CONSTRAINT` -- que nao bloqueia
escrita concorrente. `sent`/`dead`/`attempts` de linhas antigas nao mudam.

O que esta migration NAO faz
------------------------------
Nao cria tabela nova. Nao migra nenhum call site (isso e o resto da Fase 3C,
em codigo Python). Nao mexe em `notifications`, `users` alem da FK nova, nem
em `sla_alert_events`. Nao faz backfill.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c8b8d6994fae"
down_revision: str | None = "ae3cf7068dd6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELA = "email_outbox"


def upgrade() -> None:
    op.alter_column(_TABELA, "notification_id", nullable=True)

    op.add_column(_TABELA, sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(_TABELA, sa.Column("event_type", sa.String(length=20), nullable=True))
    op.add_column(_TABELA, sa.Column("dedup_key", sa.String(length=160), nullable=True))

    op.create_foreign_key(
        "fk_email_outbox_user_id_users",
        _TABELA,
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index(
        "uq_email_outbox_dedup_key",
        _TABELA,
        ["dedup_key"],
        unique=True,
    )

    op.create_check_constraint(
        "ck_email_outbox_event_type_conhecido",
        _TABELA,
        "event_type IS NULL OR event_type IN ('verification', 'password_reset', 'account_exists')",
    )

    # NOT VALID: não relê as linhas existentes na hora do ALTER TABLE, sem
    # lock de leitura da tabela inteira nem bloqueio de escrita concorrente.
    op.execute(
        f"""
        ALTER TABLE {_TABELA}
        ADD CONSTRAINT ck_email_outbox_origem_valida CHECK (
            (notification_id IS NOT NULL AND user_id IS NULL AND event_type IS NULL
             AND dedup_key IS NULL)
            OR
            (notification_id IS NULL AND user_id IS NOT NULL AND event_type IS NOT NULL
             AND dedup_key IS NOT NULL)
        ) NOT VALID
        """
    )
    # Validação em passo separado, na mesma migration: varre as linhas
    # existentes SEM bloquear escrita concorrente (só lock leve, ao contrário
    # de criar a CHECK já validada). As linhas de hoje (só notification_id)
    # satisfazem o primeiro ramo — a validação não deveria encontrar nenhuma
    # violação, mas é aqui que o Postgres provaria isso, não em teoria.
    op.execute(f"ALTER TABLE {_TABELA} VALIDATE CONSTRAINT ck_email_outbox_origem_valida")


def downgrade() -> None:
    op.execute(f"ALTER TABLE {_TABELA} DROP CONSTRAINT ck_email_outbox_origem_valida")
    op.drop_constraint("ck_email_outbox_event_type_conhecido", _TABELA, type_="check")
    op.drop_index("uq_email_outbox_dedup_key", table_name=_TABELA)
    op.drop_constraint("fk_email_outbox_user_id_users", _TABELA, type_="foreignkey")
    op.drop_column(_TABELA, "dedup_key")
    op.drop_column(_TABELA, "event_type")
    op.drop_column(_TABELA, "user_id")
    op.alter_column(_TABELA, "notification_id", nullable=False)
