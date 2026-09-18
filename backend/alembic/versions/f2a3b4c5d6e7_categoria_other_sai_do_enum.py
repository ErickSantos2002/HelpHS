"""o valor `other` sai do enum ticketcategory

Revision ID: f2a3b4c5d6e7
Revises: e1z2a3b4c5d6
Create Date: 2026-09-18

Por que não é um `ALTER TYPE ... DROP VALUE`
--------------------------------------------
Porque não existe. O PostgreSQL acrescenta valor a enum (`ADD VALUE`) e não
tira: o caminho é recriar o tipo sem o valor, converter toda coluna que o usa e
derrubar o antigo. `ticketcategory` é UM tipo servindo DUAS colunas —
`tickets.category` e `kb_articles.category` —, então as duas convertem aqui, na
mesma transação. Deixar uma para depois deixaria o tipo velho vivo e preso.

O que esta migration NÃO faz
----------------------------
Não converte dado. A regra da casa é backfill em script avulso, nunca em
migration, e aqui nem script existe: as três contagens em produção deram ZERO
(chamados, artigos e linhas de `ticket_history` com `other`), medidas em
18/09/2026 antes de escrever. Se alguma linha aparecer entre a medição e o
deploy, o `USING` abaixo reprova e o boot do container para — de propósito. O
`guarda` explícito existe só para que a mensagem diga o que houve, em vez de
deixar o operador com um "invalid input value for enum" às três da manhã.

O caminho de volta
------------------
O `downgrade` devolve o tipo COM `other`, e é tudo o que ele promete: nenhuma
linha volta a ser `other`, porque nenhuma era. Se um dia esta migration descer
num banco onde alguém já converteu linhas na mão, essa informação não está aqui
para ser recuperada — ela teria de estar no script que as converteu.

O índice `ix_kb_articles_category_status` é reconstruído sozinho pelo
`ALTER COLUMN ... TYPE`; não precisa ser derrubado nem recriado à mão.
"""

import sqlalchemy as sa

from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e1z2a3b4c5d6"
branch_labels = None
depends_on = None


_COLUNAS = (("tickets", "category"), ("kb_articles", "category"))

_SEM_OTHER = (
    "hardware",
    "software",
    "network",
    "access",
    "email",
    "security",
    "general",
)
_COM_OTHER = (*_SEM_OTHER, "other")


def _guarda(valor: str) -> None:
    """Para antes de converter, dizendo QUAL tabela e QUANTAS linhas."""
    conexao = op.get_bind()
    presos = []
    for tabela, coluna in _COLUNAS:
        quantas = conexao.execute(
            sa.text(f"SELECT count(*) FROM {tabela} WHERE {coluna}::text = :valor"),  # noqa: S608
            {"valor": valor},
        ).scalar_one()
        if quantas:
            presos.append(f"{tabela}.{coluna}: {quantas}")

    if presos:
        raise RuntimeError(
            f"não dá para tirar '{valor}' do enum ticketcategory: ainda há linha usando o valor "
            f"({', '.join(presos)}). Converta essas linhas para 'general' num script avulso, "
            "registrando os ids convertidos, e rode a migration depois — a conversão não entra "
            "aqui de propósito: migration não corrige dado histórico."
        )


def _troca_o_tipo(valores: tuple[str, ...]) -> None:
    """Renomeia o tipo velho, cria o novo, converte as colunas e derruba o velho."""
    op.execute("ALTER TYPE ticketcategory RENAME TO ticketcategory_antigo")

    novo = sa.Enum(*valores, name="ticketcategory")
    novo.create(op.get_bind(), checkfirst=False)

    for tabela, coluna in _COLUNAS:
        op.execute(
            f"ALTER TABLE {tabela} ALTER COLUMN {coluna} "  # noqa: S608
            f"TYPE ticketcategory USING {coluna}::text::ticketcategory"
        )

    op.execute("DROP TYPE ticketcategory_antigo")


def upgrade() -> None:
    _guarda("other")
    _troca_o_tipo(_SEM_OTHER)


def downgrade() -> None:
    _troca_o_tipo(_COM_OTHER)
