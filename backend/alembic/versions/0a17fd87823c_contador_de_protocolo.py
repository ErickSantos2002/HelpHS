"""contador duravel de protocolo por ano

Revision ID: 0a17fd87823c
Revises: k7f8g9h0i1j2
Create Date: 2026-10-07

O protocolo `HS-AAAA-NNNN` era `max()+1` sobre `tickets`. Apagar chamados
devolvia numeros: com a tabela vazia, o proximo voltava a `0001`, reusando
protocolos que ja tinham saido por e-mail. Esta revision cria a fonte da
verdade que nao depende do que sobrou: o ultimo numero EMITIDO de cada ano.

A semente e o maior protocolo de cada ano presente em `tickets` no instante da
migration. Em producao (07/10/2026), 2026 nasce em 26 — o maximo emitido e
`HS-2026-0026`, e o buraco de um chamado ja apagado abaixo dele nao muda isso.
Numero emitido e APAGADO acima do maior que restou nao tem como ser recuperado
daqui; em producao isso nao acontece, porque o 0026 existe.

So entram protocolos no formato do gerador (`^HS-AAAA-digitos$`): linha gravada
a mao com sufixo nao numerico nao derruba a migration num CAST.

Nenhum chamado e alterado e nenhum protocolo e renumerado: a revision so le
`tickets`.

Deploy com o container antigo ainda no ar: depois desta migration, o codigo
velho segue abrindo chamados com `max()+1` sem tocar no contador. O gerador novo
le o maior protocolo existente como PISO e nunca propoe um numero abaixo dele,
entao esses chamados nao colidem. Ver `app/utils/protocol.py`.

O downgrade remove a tabela e nada mais; o codigo antigo volta a `max()+1`.
"""

import sqlalchemy as sa

from alembic import op

revision = "0a17fd87823c"
down_revision = "k7f8g9h0i1j2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_protocol_counters",
        sa.Column("year", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.CheckConstraint("last_number >= 0", name="ck_ticket_protocol_counters_last_number"),
        sa.PrimaryKeyConstraint("year"),
    )
    op.execute(
        """
        INSERT INTO ticket_protocol_counters (year, last_number)
        SELECT substring(protocol FROM '^HS-([0-9]{4})-[0-9]+$')::int,
               max(substring(protocol FROM '^HS-[0-9]{4}-([0-9]+)$')::int)
          FROM tickets
         WHERE protocol ~ '^HS-[0-9]{4}-[0-9]+$'
         GROUP BY 1
        """
    )


def downgrade() -> None:
    op.drop_table("ticket_protocol_counters")
