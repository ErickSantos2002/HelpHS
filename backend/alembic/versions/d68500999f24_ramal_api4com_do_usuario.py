"""ramal api4com do usuario

Revision ID: d68500999f24
Revises: j6e7f8a9b0c1
Create Date: 2026-09-24

Uma coluna e um índice: `users.api4com_extension`, e a unicidade dela.

POR QUE O RAMAL MORA AQUI, E NÃO É RESOLVIDO NA HORA DA LIGAÇÃO
---------------------------------------------------------------
O `POST /calls` da API4COM exige `extension` (o ramal de quem liga) e `caller`
(que a própria documentação descreve como "normalmente o mesmo valor que
`extension`"). O fornecedor instrui, por escrito, que o integrador guarde o
ramal do seu lado, relacionado ao usuário interno.

A alternativa — perguntar o ramal à API4COM a cada clique, casando por e-mail —
foi MEDIDA e descartada em 24/09/2026: dos 16 e-mails de admin/técnico do
HelpHS, **zero** aparece entre os 18 ramais da conta. Os domínios sequer se
encontram (`healthsafetytech.com`/`helphs.com` de um lado,
`healthsafety.com.br` do outro). E a conta tem `sac@healthsafety.com.bt` ao
lado de `sac@healthsafety.com.br` — um erro de digitação que um casamento
automático por e-mail transformaria em ligação originada do ramal errado.

NADA É PREENCHIDO AQUI
----------------------
Sem `server_default`, sem UPDATE, sem backfill, sem ramal padrão. Todo usuário
existente nasce com `NULL`, e `NULL` significa exatamente "não liga". Os 18
ramais encontrados pertencem à operação comercial; os ramais do suporte do
HelpHS ainda não existem. Inventar vínculo aqui seria fazer uma pessoa ligar
com a identidade de outra — e dado histórico, nesta casa, nunca se corrige em
migration.

O ÍNDICE ÚNICO, E POR QUE ELE É A PARTE QUE IMPORTA
---------------------------------------------------
Ramal é identidade SIP, com senha própria no fornecedor. Dois usuários sob o
mesmo ramal produzem ligações indistinguíveis na origem: quando os webhooks
entrarem (Fase 2D), não haverá como atribuir a chamada a uma pessoa. A trilha
de auditoria quebraria sem erro nenhum, que é a pior forma de quebrar.

No PostgreSQL vários `NULL` convivem sob UNIQUE — é o comportamento desejado, e
o mesmo que o `uq_ticket_calls_provider_call_id` já usa: dezesseis pessoas sem
ramal não colidem entre si.

POR QUE É SEGURA NO BOOT
------------------------
Aditiva pura. `ADD COLUMN` nullable e **sem default** não reescreve a tabela em
PostgreSQL, e o índice único nasce sobre uma coluna inteiramente nula — leitura
instantânea, sem risco de recusa por dado legado. Não há estado de `users` hoje
que possa violar esta migration.

O CAMINHO DE VOLTA
------------------
`downgrade` derruba o índice e a coluna. Perde-se o vínculo usuário→ramal, que
é configuração e se refaz na tela; nenhum chamado, usuário ou ligação é tocado.

⚠️ COLISÃO DE REVISION ID — E POR QUE ESTE ID É ALEATÓRIO
----------------------------------------------------------
Esta migration nasceu como `j6e7f8a9b0c1`, escolhido seguindo o padrão visual
da cadeia: "cada caractere +1" sobre a anterior. Outra frente, trabalhando em
paralelo, fez exatamente a mesma conta para a migration do histórico de aceites
da LGPD — e a dela chegou primeiro. `j6e7f8a9b0c1` está em PRODUÇÃO desde
24/09/2026, e pertence a `lgpd_consents`.

Duas migrations diferentes com o mesmo id NÃO dão conflito de merge: os
arquivos têm nomes distintos e nunca se tocam. O sintoma só apareceu no banco —
`alembic_version` dizia `j6e7f8a9b0c1` e a coluna desta migration não existia,
porque quem rodou foi a outra.

Por isso o id agora é ALEATÓRIO, como o alembic gera por padrão (a raiz desta
cadeia, `75ec9d264ccb`, é assim). Um padrão previsível GARANTE que duas frentes
paralelas escolham o mesmo número; um id aleatório torna a colisão desprezível.

Esta migration passou a descender da LGPD, e não mais de `i5d6e7f8a9b0`: é onde
a cadeia realmente está em produção.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d68500999f24"
down_revision: str | None = "j6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELA = "users"
_COLUNA = "api4com_extension"
_INDICE = "uq_users_api4com_extension"


def upgrade() -> None:
    op.add_column(_TABELA, sa.Column(_COLUNA, sa.String(length=20), nullable=True))
    op.create_index(_INDICE, _TABELA, [_COLUNA], unique=True)


def downgrade() -> None:
    op.drop_index(_INDICE, table_name=_TABELA)
    op.drop_column(_TABELA, _COLUNA)
