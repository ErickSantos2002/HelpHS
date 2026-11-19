"""empresa do equipamento

Revision ID: o1j2k3l4m5n6
Revises: n0i1j2k3l4m5
Create Date: 2026-11-17

ECE-01, Fase 1. O equipamento só tinha `owner_id` — quem cadastrou —, e a
empresa dele era deduzida da empresa do responsável. Esta revision dá ao
aparelho a empresa PRÓPRIA:

- `equipments.company_id` (UUID, nula);
- `fk_equipments_company_id_companies` → `companies.id`, `ON DELETE RESTRICT`;
- `ix_equipments_company_id`;
- `equipments.sem_empresa_por_decisao` (BOOLEAN NOT NULL DEFAULT false);
- `ck_equipments_sem_empresa_por_decisao`: a marca só existe sem empresa.

DOIS NULOS, DUAS COISAS
-----------------------
`company_id` nulo quer dizer "ainda não classificado" — é o que o vínculo do
cliente e o script de preenchimento completam. Quando é a EQUIPE que deixa o
aparelho sem empresa de propósito (`company_id: null` explícito), a marca
`sem_empresa_por_decisao` fica verdadeira e nenhum preenchimento automático
toca na linha. Informar uma empresa desfaz a marca. O `CHECK` impede o estado
sem sentido: marca verdadeira com empresa gravada.

SÓ ADITIVA, SEM DADO
--------------------
A coluna nasce nula em todas as linhas e esta revision não preenche nenhuma.
Dado histórico se corrige em script avulso, com conferência humana
(`scripts/preenche_empresa_do_equipamento.py`): "a empresa atual do
responsável" não é necessariamente a empresa do aparelho antigo, e migration
roda sozinha no boot — não é lugar de presumir.

- `ADD COLUMN` nula e sem default só altera o catálogo: a tabela não é
  reescrita. O mesmo vale para a booleana: default CONSTANTE não reescreve a
  tabela desde o PostgreSQL 11.
- O `CHECK` é validado numa varredura, contra linhas que nascem todas com a
  marca falsa — não há o que falhar.
- A FK é validada na criação, mas contra uma coluna inteira nula — não há o
  que conferir, e por isso não há o que falhar no boot.
- O índice é montado numa varredura de `equipments` (dezenas de linhas).
  Sem `CONCURRENTLY`, pelos motivos de `m9h0i1j2k3l4`: o `env.py` roda as
  revisions pendentes numa transação só.

POR QUE `RESTRICT`
------------------
`users.company_id` é `SET NULL`, e por isso excluir empresa soltava cliente
sem avisar até a F1-D1 pôr a recusa na frente. Aqui a regra já nasce escrita:
empresa com equipamento vinculado não pode ser excluída. Quem recusa com 409 e
contagem é a aplicação (`groups.py::_dependentes_da_empresa`); a FK garante
que nenhum outro caminho — script, SQL à mão — solte o aparelho em silêncio.

NADA MUDA PARA QUEM USA
-----------------------
Nenhuma leitura consulta a coluna nesta entrega, e a flag
`EQUIPAMENTO_POR_EMPRESA` nasce desligada. O que passa a acontecer é só a
GRAVAÇÃO da empresa no cadastro e no vínculo do cliente.

ROLLBACK
--------
⚠️ Uma imagem que não contém ESTE arquivo não sobe num banco que já passou por
ele (`start.sh`: `alembic upgrade head` com `set -e`).

- O rollback PREFERENCIAL mantém esta revision: imagem com o código anterior
  E este arquivo. O código anterior ignora a coluna; os aparelhos cadastrados
  nessa janela ficam sem empresa e entram no próximo levantamento do script.
- O DOWNGRADE não é estratégia de rollback. Ele apaga a coluna e, com ela, a
  empresa de cada aparelho — que não tem de onde ser reconstruída: a empresa
  do responsável pode ter mudado, e a escolha feita pela equipe só existe
  aqui. Por isso ele ABORTA enquanto houver aparelho com empresa — ou com a
  marca de "sem empresa por decisão", que também só existe aqui.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "o1j2k3l4m5n6"
down_revision: str | None = "n0i1j2k3l4m5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK = "fk_equipments_company_id_companies"
_INDICE = "ix_equipments_company_id"
_MARCA = "sem_empresa_por_decisao"
_CHECK = "ck_equipments_sem_empresa_por_decisao"


def upgrade() -> None:
    op.add_column(
        "equipments",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        _FK,
        "equipments",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(_INDICE, "equipments", ["company_id"])
    op.add_column(
        "equipments",
        sa.Column(_MARCA, sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_check_constraint(
        _CHECK, "equipments", "NOT sem_empresa_por_decisao OR company_id IS NULL"
    )


def downgrade() -> None:
    bind = op.get_bind()
    com_empresa = bind.execute(
        sa.text("SELECT count(*) FROM equipments WHERE company_id IS NOT NULL")
    ).scalar_one()
    por_decisao = bind.execute(
        sa.text("SELECT count(*) FROM equipments WHERE sem_empresa_por_decisao")
    ).scalar_one()

    if com_empresa or por_decisao:
        raise RuntimeError(
            "ROLLBACK BLOQUEADO: "
            f"{com_empresa} equipamento(s) perderiam a empresa e {por_decisao} "
            "perderiam a marca de 'sem empresa por decisão'.\n"
            "\n"
            "Descer apaga `equipments.company_id`, e a empresa de cada aparelho não\n"
            "tem de onde ser reconstruída: a do responsável pode ter mudado, e a que a\n"
            "equipe escolheu só existe nesta coluna.\n"
            "\n"
            "Para recuar a REGRA, desligue EQUIPAMENTO_POR_EMPRESA e mantenha esta\n"
            "revision. Para descer mesmo assim, guarde antes o retrato:\n"
            "\n"
            "    SELECT id, company_id, sem_empresa_por_decisao FROM equipments\n"
            "     WHERE company_id IS NOT NULL OR sem_empresa_por_decisao;\n"
            "\n"
            "e então zere as duas colunas à mão, com autorização específica."
        )

    op.drop_constraint(_CHECK, "equipments", type_="check")
    op.drop_column("equipments", _MARCA)
    op.drop_index(_INDICE, table_name="equipments")
    op.drop_constraint(_FK, "equipments", type_="foreignkey")
    op.drop_column("equipments", "company_id")
