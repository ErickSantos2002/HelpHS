"""a agenda ganha horário, e a chave de dia inteiro

Revision ID: d0y1z2a3b4c5
Revises: c9x0y1z2a3b4
Create Date: 2026-09-14

Uma coluna: `calendar_events.all_day`, booleana.


O QUE **NÃO** MUDA, E É A METADE IMPORTANTE
-------------------------------------------
`start_date` e `end_date` já eram `TIMESTAMPTZ` desde que a tabela nasceu
(`n4i5j6k7l8m9`). A agenda sempre PÔDE guardar hora — o que faltava é que nada
nunca punha uma hora significativa lá: a tela tinha dois campos de data e
mandava `T00:00:00Z` e `T23:59:59Z`.

Então esta migration não troca tipo de coluna, não converte valor e não toca em
linha nenhuma. Ela só dá NOME a uma convenção que já existia nos dados.


POR QUE O `server_default` ENTRA E SAI NA MESMA MIGRATION
----------------------------------------------------------
Ele entra para que as linhas que já existem recebam `true` sem um UPDATE — e
isso é semântica de criação de coluna, não backfill: nenhum dado histórico está
sendo corrigido, e a regra "backfill nunca em migration"
(`docs/decisoes-e-regras.md`) continua valendo.

O padrão `true` é o correto para o acervo atual porque **todo evento que existe
já é de dia inteiro**: foram todos gravados `00:00:00Z`–`23:59:59Z` pela tela
que só tinha data. Não é suposição sobre o conteúdo — é a forma que o código
que os criou só sabia produzir.

E ele SAI logo depois, ao contrário da `c9x0y1z2a3b4`, que manteve o dela. A
diferença é o que o padrão significaria dali para a frente: lá, artigo novo
legível pela IA é o comportamento desejado para sempre. Aqui, um INSERT que
omitisse a coluna viraria um evento de dia inteiro em silêncio — exatamente o
contrário do que um evento COM horário quer. Depois desta migration, quem
insere declara.


O CAMINHO DE VOLTA
------------------
`downgrade` larga a coluna, e mais nada. As horas continuam onde estão:
evento de dia inteiro permanece `00:00:00Z`–`23:59:59.999999Z`, que é a mesma
convenção que o código anterior já produzia e lia. A versão antiga da tela, que
faz `start_date.slice(0, 10)`, volta a funcionar sem enxergar diferença.

O que se perde ao voltar é a distinção entre "dia inteiro" e "evento que por
acaso dura o dia todo" — e ela é recuperável por convenção, não por backup.
Nenhum evento, nenhuma data e nenhum horário são destruídos.

Volta segura no boot: `DROP COLUMN` de coluna sem índice, sem constraint e sem
chave estrangeira não reescreve a tabela.


POR QUE É SEGURA NO BOOT
------------------------
Aditiva: coluna nova com `server_default`, sem constraint, sem índice, sem
backfill. O PostgreSQL 11+ resolve `ADD COLUMN ... DEFAULT` sem reescrever a
tabela, e `ALTER COLUMN ... DROP DEFAULT` é alteração só de catálogo.
"""

import sqlalchemy as sa

from alembic import op

revision = "d0y1z2a3b4c5"
down_revision = "c9x0y1z2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calendar_events",
        sa.Column(
            "all_day",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    # O padrão existia para as linhas de antes. A partir daqui, quem insere
    # declara: um INSERT que omitisse a coluna viraria dia inteiro em silêncio.
    op.alter_column("calendar_events", "all_day", server_default=None)


def downgrade() -> None:
    op.drop_column("calendar_events", "all_day")
