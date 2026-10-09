"""estado dispatching na tentativa de chamada

Revision ID: 8d08cbca1768
Revises: d68500999f24
Create Date: 2026-09-24

Um valor a mais no CHECK de `ticket_calls.creation_status`: `dispatching`.

POR QUE ESTE ESTADO PRECISA EXISTIR ANTES DE QUALQUER LIGAÇÃO
--------------------------------------------------------------
Com os cinco estados da Fase 2B, uma linha `pending` sobrevivente a um crash
era AMBÍGUA, e as duas leituras pedem condutas opostas:

  * o processo morreu antes de falar com o fornecedor  → nada tocou, repetir é
    seguro;
  * o processo morreu depois de enviar o `POST /calls` → a ligação pode estar
    acontecendo, e repetir faz o telefone do cliente tocar duas vezes.

Sem distinguir os dois, a única conduta segura era nunca repetir — o que
transforma qualquer falha de infraestrutura em tentativa presa para sempre,
exigindo alguém olhar o painel do fornecedor.

`dispatching` é gravado e COMMITADO imediatamente antes da chamada externa.
Depois disso: `pending` órfã significa "não saiu" (seguro), `dispatching` órfã
significa "não sabemos" (bloqueia). A ambiguidade deixa de existir.

POR QUE ISTO É UMA MIGRATION, E NÃO SÓ UMA LINHA NO ENUM PYTHON
----------------------------------------------------------------
`creation_status` é `String(20)` com `CheckConstraint` — não é enum nativo. Mas
o CHECK enumera os valores aceitos, e o banco recusaria `dispatching` com
violação de constraint. Acrescentar o valor no Python sem mexer no banco daria
um erro que só apareceria na primeira ligação real.

A escolha de `String` + `CHECK` na 2B é justamente o que torna esta migration
barata: derrubar e recriar um CHECK é alteração de catálogo com validação da
tabela, não `ALTER TYPE` nem reescrita. A tabela `ticket_calls` está vazia em
produção (nenhuma ligação foi feita ainda), então a validação é instantânea.

SEM RISCO DE DADO LEGADO
------------------------
O conjunto novo é um SUPERCONJUNTO do antigo: toda linha que satisfazia o CHECK
anterior satisfaz este. Nenhuma linha é lida, escrita ou recusada.

O CAMINHO DE VOLTA
------------------
⚠️ O `downgrade` restaura o CHECK antigo, que NÃO aceita `dispatching`. Se
existir linha nesse estado, ele falha — e é o comportamento correto: voltar o
schema com a linha presente deixaria o banco afirmando um estado que a própria
constraint nega. A linha precisa ser resolvida antes (virar `indeterminate`,
que é o que ela realmente significa quando ninguém sabe o desfecho).

⚠️ ID TROCADO JUNTO COM O DA MIGRATION ANTERIOR
------------------------------------------------
Esta migration nunca colidiu com nada — nasceu `k7f8a9b0c1d2` e nunca foi a
produção. O id mudou porque o `down_revision` dela apontava para a migration do
ramal, que precisou ser reancorada depois de colidir com a do histórico de
aceites da LGPD (ver a nota lá).

Aproveitou-se a troca para adotar id ALEATÓRIO, pelo mesmo motivo: o padrão
"cada caractere +1" é justamente o que faz duas frentes paralelas escolherem o
mesmo número sem saber.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "8d08cbca1768"
down_revision: str | None = "d68500999f24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELA = "ticket_calls"
_NOME = "ck_ticket_calls_status_conhecido"

_ANTES = ("pending", "confirmed", "rejected", "unavailable", "indeterminate")
_DEPOIS = ("pending", "dispatching", "confirmed", "rejected", "unavailable", "indeterminate")


def _regra(valores: tuple[str, ...]) -> str:
    return "creation_status IN (" + ", ".join(f"'{v}'" for v in valores) + ")"


def upgrade() -> None:
    op.drop_constraint(_NOME, _TABELA, type_="check")
    op.create_check_constraint(_NOME, _TABELA, _regra(_DEPOIS))


def downgrade() -> None:
    op.drop_constraint(_NOME, _TABELA, type_="check")
    op.create_check_constraint(_NOME, _TABELA, _regra(_ANTES))
