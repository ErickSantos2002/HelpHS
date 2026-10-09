"""prazos de SLA passam a ser guardados em minutos

Revision ID: a7b8c9d0e1f2
Revises: z6u7v8w9x0y1
Create Date: 2026-09-08

O SGI aprovou cortar cada prazo de SLA pela metade. Sete dos oito valores
sobrevivem em horas inteiras; o oitavo nao: metade da resposta do nivel critico
e 30 minutos, e `response_time_hours` e `Integer` com `ge=1` no schema. Nao ha
como guardar meia hora numa coluna de horas inteiras.

Dai a troca de unidade. As duas colunas passam a contar MINUTOS, o que remove a
fracao do problema em vez de acomoda-la: 30 minutos e um inteiro, e qualquer
prazo futuro que nao seja hora cheia tambem sera.

POR QUE A CONVERSAO DE VALOR ENTRA AQUI, e nao num script avulso
-----------------------------------------------------------------
A regra da casa e que dado historico se corrige em script avulso, nunca em
migration. Esta conversao nao e disso: ela nao reescreve o passado nem muda o
significado de nada. `4` em horas e `240` em minutos sao **o mesmo prazo** — o
UPDATE apenas mantem verdadeiro o que a coluna ja dizia, depois que o nome dela
mudou. Deixar de multiplicar seria o defeito: `4` passaria a significar quatro
MINUTOS, e todo chamado novo nasceria com prazo 60 vezes menor.

Ou seja: sem o UPDATE, esta migration corrompe. Com ele, preserva.

OS VALORES APROVADOS NAO ENTRAM AQUI
------------------------------------
Esta revision so troca a unidade. Os prazos pela metade sao dado de
configuracao, editavel pela interface, e vao para producao pela mao de quem
opera — nao por migration, que rodaria sozinha no boot e mudaria SLA de
producao sem ninguem clicar. A semente em `app/seeds.py` carrega os valores
aprovados para ambientes NOVOS, e o seed so cria o que ainda nao existe: quem ja
tem as linhas nao e tocado.

`server_default` nao e necessario: as colunas ja existem e ja sao NOT NULL, e o
`alter_column` preserva essa condicao.

O downgrade desfaz a conta com divisao INTEIRA, e por isso perde precisao em
valor que nao seja hora cheia — 30 minutos volta como 0. E o unico caminho
possivel para uma coluna de horas inteiras, e e o motivo de o downgrade elevar
para 1 em vez de aceitar zero: prazo zero faria todo chamado nascer vencido.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "z6u7v8w9x0y1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_COLUNAS = (
    ("response_time_hours", "response_time_minutes"),
    ("resolve_time_hours", "resolve_time_minutes"),
)


def upgrade() -> None:
    for antiga, nova in _COLUNAS:
        op.alter_column("sla_configs", antiga, new_column_name=nova)
        # Mesmo prazo, outra unidade. Ver o cabecalho: sem esta linha a
        # migration corrompe em vez de converter.
        op.execute(sa.text(f"UPDATE sla_configs SET {nova} = {nova} * 60"))


def downgrade() -> None:
    for antiga, nova in _COLUNAS:
        # `GREATEST(..., 1)` porque a divisao inteira leva 30 minutos a zero, e
        # prazo zero faz o chamado nascer vencido.
        op.execute(sa.text(f"UPDATE sla_configs SET {nova} = GREATEST({nova} / 60, 1)"))
        op.alter_column("sla_configs", nova, new_column_name=antiga)
