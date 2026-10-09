"""a Helô saiu deste chamado

Revision ID: b8w9x0y1z2a3
Revises: a7v8w9x0y1z2
Create Date: 2026-09-10

Uma coluna, para separar duas perguntas que estavam sendo respondidas pelo
mesmo campo.

`tickets.ai_enabled` é o botão DE GENTE: "alguém quer a IA fora deste
chamado". `tickets.helo_saiu` é o estado da conversa dela: "a Helô já escalou
e o chamado passou a ser do humano". Enquanto ela falava uma vez por chamado
os dois davam no mesmo, e escrever num só bastava. Com ela conversando, não
basta: escalar por decisão do modelo, por teto de trocas ou por a IA estar fora
do ar desligava junto a sugestão de resposta e o resumo DO TÉCNICO — tirando a
ferramenta dele exatamente nos chamados em que a IA já tinha falhado.

O pedido explícito de humano continua desligando os dois, e isso não é
descuido: ali quem quis sair da IA foi o cliente, e a vontade dele vale para as
ferramentas todas.


POR QUE ESTA MIGRATION É SEGURA NO BOOT — e as duas anteriores não eram
---------------------------------------------------------------------
Ela é ADITIVA e nada mais: uma coluna nova, com `server_default`, sem
constraint, sem índice, sem backfill, sem tocar em linha existente. O
PostgreSQL 11+ resolve `ADD COLUMN ... DEFAULT` sem reescrever a tabela — o
valor default fica no catálogo e as linhas antigas o herdam na leitura. Numa
tabela de chamados de qualquer tamanho isso é instantâneo, e roda no boot do
contêiner sem risco.

**Isto NÃO abre precedente.** Duas migrations desta mesma fase quase derrubaram
a API, e as duas por motivos que continuam valendo:

1. A `a7v8w9x0y1z2` ia rodar `CREATE EXTENSION vector`. Extensão não-*trusted*
   pede superusuário, e as migrations rodam sozinhas no boot — seria privilégio
   de superusuário no caminho do boot, para sempre, por causa de um comando que
   roda uma vez na vida do banco. Virou verificação, com passo manual antes do
   primeiro deploy.

2. A mesma, num rascunho anterior, usava `server_default=func.false()` num
   booleano. Isso renderiza `DEFAULT false()` — sintaxe inválida — e derrubou
   18 testes com `syntax error at "("`. O `alembic check` passou por cima:
   ele não compara `server_default` por padrão. Aqui o default é o literal
   `sa.text("false")`, que é o que o resto do schema usa.

A régua para "pode rodar no boot" continua a mesma, e é sobre o QUE a migration
faz, não sobre o tamanho dela: nada que precise de privilégio que a aplicação
não tem, nada que reescreva tabela, nada que corrija dado histórico (isso é
script avulso, nunca migration). Esta passa nas três. A próxima precisa ser
avaliada de novo.


O `server_default` e o `default` do modelo convivem de propósito
---------------------------------------------------------------
O `default=False` do SQLAlchemy vale para linha criada pela aplicação; o
`server_default` vale para as que já existem e para qualquer `INSERT` que não
passe pelo ORM. Sem o segundo, a coluna nasceria `NULL` nos chamados antigos e
`NOT NULL` recusaria a própria migration.
"""

import sqlalchemy as sa

from alembic import op

revision = "b8w9x0y1z2a3"
down_revision = "a7v8w9x0y1z2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column(
            "helo_saiu",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tickets", "helo_saiu")
