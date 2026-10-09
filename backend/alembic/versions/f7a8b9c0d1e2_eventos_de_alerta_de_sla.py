"""eventos de alerta de sla

Revision ID: f7a8b9c0d1e2
Revises: 8d08cbca1768
Create Date: 2026-09-25

A tabela que faz o aviso de SLA acontecer **uma vez**. Uma linha e um aviso que
JA FOI dado.

Por que uma tabela, e nao um booleano em `tickets`
--------------------------------------------------
Porque "ja avisei" nao e pergunta de sim/nao: e pergunta sobre QUAL prazo e QUAL
limiar. Prorrogacao, troca de prioridade, reabertura e edicao da `sla_configs`
produzem prazos novos que merecem aviso novo — e um booleano ja ligado os
engoliria em silencio, que e o pior desfecho possivel para um alerta.

Por que nao serve consultar `notifications`
-------------------------------------------
Aquela tabela guarda o EFEITO: uma linha por destinatario, com
`ondelete=CASCADE` para `users`. Excluir a ultima pessoa avisada apagaria a
prova de que o aviso aconteceu, e a rodada seguinte reenviaria. O precedente da
casa para "o worker ja fez isto" e estado persistido proprio — `helo_indexacoes`
na indexacao, e a transicao de status no fechamento automatico. Nenhum dos dois
usa Redis, e este tambem nao: chave que expira nao pode ser a prova de um
evento.

A identidade, e o que ela decide
--------------------------------
`uq_sla_alert_events_identidade` cobre
`(ticket_id, alert_kind, reopen_count, effective_due_at, warning_threshold)`.

O `reopen_count` esta ai por medicao, nao por precaucao. A primeira versao desta
migration contava com o prazo distinguir os ciclos, e ele NAO distingue:
`add_business_minutes` avanca o instante para dentro do expediente antes de
somar, entao duas reaberturas em momentos diferentes da mesma janela fechada
colapsam no mesmo inicio de jornada e produzem o MESMO vencimento -- sabado as
11:00 e domingo as 19:30 BRT, 32 horas de diferenca, prazo identico. E a
reabertura zera pausa e extensao, entao o prazo do ciclo novo e independente do
anterior e pode coincidir com ele. Sem `reopen_count` na chave, o segundo aviso
ficava silenciado, que e o pior desfecho possivel para um alerta.

`priority` e `extension_total_min` ficam de FORA: sao auditoria, nenhum dos dois
muda o ciclo, e os dois ja mudam o prazo -- que esta na chave. Incluir qualquer
um criaria uma segunda resposta para "e o mesmo aviso?".

O indice unico nao e enfeite de integridade: e ele que permite o
`INSERT ... ON CONFLICT DO NOTHING RETURNING id` do worker. Sem um indice unico
o `ON CONFLICT` nao tem em que conflitar, e a reivindicacao do evento deixaria
de ser atomica — duas instancias avisariam o mesmo chamado.

Por que `alert_kind` e `String` com CHECK, e nao enum nativo
------------------------------------------------------------
Mesma razao ja registrada na `h4c5d6e7f8g9` e medida nesta casa: acrescentar
valor a enum nativo exige `ALTER TYPE ... ADD VALUE`, e o alembic daqui roda a
cadeia inteira numa transacao so — o valor novo nao pode ser citado em DDL
posterior (`UnsafeNewEnumValueUsageError`, documentado na `g3b4c5d6e7f8`). A
Fase 2B acrescenta `response_warning`, e nascer com esse custo seria escolher
errado sabendo.

O CHECK do limiar
-----------------
`warning_threshold BETWEEN 1 AND 100` — o mesmo dominio que `SLAConfigUpdate` ja
valida. Existe porque o campo tem uma historia de escala errada: as fixtures de
`frontend/src/test/services/slaService.test.ts` usam `0.8` e `0.5`, como se
fosse fracao. Um aviso gravado com `warning_threshold = 0` dispararia a cada
rodada em qualquer chamado, e o banco recusar e melhor que descobrir isso pelo
volume de e-mail.

O que esta migration NAO faz
----------------------------
Nao toca `tickets`, `sla_configs`, `notifications` nem o enum
`notificationtype` — `sla_warning` ja existe nele desde o schema inicial
(`75ec9d264ccb`), e e por isso que produzir a notificacao nao custa mudanca de
schema. Nao faz backfill: aviso que nao aconteceu nao se inventa
retroativamente, e um backfill aqui silenciaria o primeiro aviso legitimo de
todo chamado hoje na faixa.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "8d08cbca1768"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELA = "sla_alert_events"


def upgrade() -> None:
    op.create_table(
        _TABELA,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_kind", sa.String(length=40), nullable=False),
        sa.Column("effective_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("warning_threshold", sa.Integer(), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=True),
        sa.Column("reopen_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extension_total_min", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "alert_kind IN ('resolution_warning')",
            name="ck_sla_alert_events_kind_conhecido",
        ),
        sa.CheckConstraint(
            "warning_threshold >= 1 AND warning_threshold <= 100",
            name="ck_sla_alert_events_threshold_percentual",
        ),
    )
    op.create_index(
        "uq_sla_alert_events_identidade",
        _TABELA,
        ["ticket_id", "alert_kind", "reopen_count", "effective_due_at", "warning_threshold"],
        unique=True,
    )
    op.create_index("ix_sla_alert_events_ticket_created", _TABELA, ["ticket_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_sla_alert_events_ticket_created", table_name=_TABELA)
    op.drop_index("uq_sla_alert_events_identidade", table_name=_TABELA)
    op.drop_table(_TABELA)
