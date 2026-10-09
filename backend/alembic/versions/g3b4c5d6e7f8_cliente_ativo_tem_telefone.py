"""cliente ativo tem telefone

Revision ID: g3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-21

A trava de banco da regra que a Fase 1A pôs na aplicação: **cliente ativo
precisa de telefone**. Ela fecha o que a aplicação sozinha não consegue
garantir — que nenhum caminho de escrita FUTURO esqueça a regra.

Por que só agora, e não junto com a Fase 1A
--------------------------------------------
Porque antes ela derrubaria contas legítimas. O desenho original previa
`CHECK ... NOT VALID`, no entendimento de que isso isentaria as linhas antigas.
**Não isenta**: `NOT VALID` pula apenas o escaneamento inicial, e dali em
diante o PostgreSQL avalia o CHECK sobre a nova versão da linha em todo
`UPDATE` — inclusive o que só troca o nome. Medido em PostgreSQL 16.2, com uma
linha por cenário: três divergências em onze, todas sobre o legado. O banco
contradiria a regra prospectiva publicada.

Um gatilho `BEFORE UPDATE` resolveria (ele enxerga `OLD` e `NEW`, e foi medido
com zero divergências), e foi **rejeitado** por outro motivo: duplicaria a
regra em PL/pgSQL e em Python, sem teste de mutação nem `mypy` do lado do
banco. Os dois descartes estão em `docs/decisoes-e-regras.md`.

O caminho escolhido foi zerar o legado primeiro. A ferramenta de readiness
(`scripts/diagnostico_telefone.py`, Fase 1B) mediu `LEGADO_INVALIDO=14` em
produção; as contas eram exemplos, foram **inativadas administrativamente** —
sem telefone inventado, sem exclusão de histórico — e a medição seguinte deu
`LEGADO_INVALIDO=0`. Só então esta migration passou a poder existir.

PRESENÇA, não formato
---------------------
O predicado exige que sobre alguma coisa depois de tirar todo espaço em
branco — `NULL`, `''`, espaços, tabulação e quebra de linha são todos
ausência, na mesma definição que o readiness usa. **E.164 não é checado
aqui**: traduzir o normalizador para uma regex de SQL criaria uma segunda
fonte de verdade que deriva da primeira. O formato é garantido pelo tipo
anotado (`app/utils/telefone.py`) em toda porta de escrita.

`companies.phone` segue fora: não é fonte da telefonia.

SEM BACKFILL, e não é omissão. Esta migration não escreve em linha nenhuma.
Se existir cliente ativo sem telefone no momento da aplicação, ela **falha** —
e falhar é o comportamento certo: sanear dado é decisão administrativa, nunca
efeito colateral de um deploy. Quem encontrar essa falha roda o readiness, que
diz exatamente quantas linhas faltam.

O UPGRADE é aditivo para quem já está em conformidade: nenhuma conta muda,
nenhum login muda, nenhuma tela muda.

O DOWNGRADE remove só a constraint. Nada de dado é perdido no caminho de
volta, porque nada de dado foi escrito no caminho de ida.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "g3b4c5d6e7f8"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOME = "ck_users_cliente_ativo_tem_telefone"

# `NOT (... AND ...)` e não a forma negada campo a campo: as duas são
# equivalentes aqui (role e status são NOT NULL), e esta diz o que a regra é —
# "fora do estado cliente+ativo, a constraint não opina".
#
# ⚠️ E há um motivo TÉCNICO para o predicado nomear só `client` e `active`,
# descoberto ao mutar esta constraint: o projeto não usa
# `transaction_per_migration`, então `alembic upgrade head` roda a cadeia
# INTEIRA numa transação só — e `anonymized` entrou em `userstatus` por
# `ALTER TYPE ... ADD VALUE` (revision b2c3d4e5f6a7). Citar esse literal aqui
# estoura com `unsafe use of new value "anonymized" of enum type userstatus`
# ao subir do zero. A forma acima isenta o anonimizado SEM nomeá-lo, então não
# esbarra nisso. Vale para qualquer migration futura que queira mencionar um
# valor de enum acrescentado depois da criação do tipo.
#
# O `\s` cobre tabulação e quebra de linha, que um `btrim` deixaria passar como
# se fossem telefone. É a mesma expressão do readiness, palavra por palavra: se
# as duas divergirem, o portão passa a medir uma coisa e o banco a exigir outra.
_REGRA = (
    "NOT (role = 'client' AND status = 'active') "
    r"OR regexp_replace(coalesce(phone, ''), '\s', '', 'g') <> ''"
)


def upgrade() -> None:
    op.create_check_constraint(_NOME, "users", _REGRA)


def downgrade() -> None:
    op.drop_constraint(_NOME, "users", type_="check")
