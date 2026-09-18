"""a Base de Conhecimento decide o que a Helô lê

Revision ID: c9x0y1z2a3b4
Revises: b8w9x0y1z2a3
Create Date: 2026-09-10

Uma coluna: `kb_articles.helo_pode_ler`, booleana, padrão `true`.

A partir desta versão a fonte da Helô é a Base de Conhecimento — artigo
publicado alimenta as respostas dela sem ninguém rodar nada. Esta coluna é o
jeito de manter um artigo na barra lateral e FORA das respostas da IA.


POR QUE COLUNA, E NÃO TAG
-------------------------
`kb_articles.tags` já existe e custaria zero migration. Foi recusada porque é
texto livre: `nao-helo`, `não-helo` e `naohelo` são strings diferentes, e
escolher a errada muda o comportamento em SILÊNCIO — o artigo que alguém achou
que tinha excluído continua alimentando as respostas. É a classe de defeito que
a fase inteira da Helô vem eliminando. Coluna tem tipo, tem padrão e aparece na
tela ao lado do botão de publicar.


POR QUE O PADRÃO É `true` — com o número e a data, para ser revisável
---------------------------------------------------------------------
Em 10/09/2026 existia UM artigo publicado em produção, nenhum rascunho,
nenhum arquivado. O número é do Rickelme, informado nesse dia; não foi medido
por esta migration nem por quem a escreveu.

O padrão oposto (`false`, opt-in) foi considerado e descartado. Ele existiria
para proteger de um ACERVO DESCONHECIDO — artigos antigos sobre procedimento
interno virando fonte da IA no instante do deploy. Com um acervo de uma linha,
que uma pessoa confere em trinta segundos, a proteção não protege nada e custa
o passo manual que a mudança de fonte existe para eliminar.

**Se o acervo crescer e alguém reabrir esta decisão**, o argumento acima está
datado de propósito: ele vale para um acervo de um artigo. Com centenas, a
conta pode inverter.


POR QUE É SEGURA NO BOOT
------------------------
Aditiva e nada mais: coluna nova com `server_default`, sem constraint, sem
índice, sem backfill. O PostgreSQL 11+ resolve `ADD COLUMN ... DEFAULT` sem
reescrever a tabela. E o padrão cobre o único artigo que existe hoje sem que
esta migration toque em linha nenhuma — corrigir linha existente em migration
é proibido neste projeto (`docs/decisoes-e-regras.md`, "Backfill nunca em
migration").
"""

import sqlalchemy as sa

from alembic import op

revision = "c9x0y1z2a3b4"
down_revision = "b8w9x0y1z2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "kb_articles",
        sa.Column(
            "helo_pode_ler",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("kb_articles", "helo_pode_ler")
