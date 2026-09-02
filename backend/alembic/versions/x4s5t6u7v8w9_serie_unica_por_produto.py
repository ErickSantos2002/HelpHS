"""numero de serie unico por produto, nao por dono

Revision ID: x4s5t6u7v8w9
Revises: w3r4s5t6u7v8
Create Date: 2026-08-26

A chave do aparelho passa a ser `(produto, serie)`, decidida com o cliente em
26/08. O dono sai da unicidade: duas pessoas que cadastram a mesma serie do
mesmo produto tem o MESMO aparelho fisico, e quem diz quem usa e a
`equipment_users`.

Sai o escopo por dono, que era a regra de 21/08 (`u1p2q3r4s5t6`). Ele existia
por um motivo que continua valido -- o 409 global era um oraculo, contava ao
cliente que outra empresa tinha aquela serie -- mas resolvia isso do lado
errado: em vez de esconder a informacao, deixava o mesmo aparelho virar duas
linhas. Quem fecha o oraculo agora e o `/equipment/my`, que ANEXA a pessoa ao
aparelho existente e responde 201 igual ao cadastro comum.

Sai tambem o indice parcial dos orfaos. Ele so fazia sentido enquanto "sem
dono" era um escopo a parte; sob a chave nova, orfao e aparelho como qualquer
outro.

POR QUE ESTA REVISION PODE ENTRAR AGORA: o `scripts/diagnostico_empresa_
aparelho.py` rodou contra producao em 26/08 e o bloco 2 voltou vazio -- nenhum
par (produto, serie) duplicado. O indice unico sobe limpo. Sem esse numero
esta migration nao poderia ser escrita: indice unico falha na CRIACAO se
houver duplicata, e falha de migration aqui e API que nao sobe.

Serie nula nao conflita: em SQL, NULL nunca e igual a NULL, entao varios
equipamentos sem numero de serie continuam convivendo. E o que se quer --
aparelho sem serie cadastrada e caso comum, nao duplicata.

O DOWNGRADE recria os dois indices antigos e pode falhar: se depois desta
revision duas pessoas passarem a usar o mesmo aparelho por donos diferentes...
nao falha por isso (a linha e uma so). Falha se alguem cadastrar a mesma serie
do mesmo dono em produtos diferentes, que a chave nova permite e a antiga nao.
E a natureza da volta -- quem precisar voltar resolve os casos antes.
"""

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "x4s5t6u7v8w9"
down_revision: str | None = "w3r4s5t6u7v8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_equipments_owner_serial", table_name="equipments")
    op.drop_index("uq_equipments_orphan_serial", table_name="equipments")
    op.create_index(
        "uq_equipments_product_serial",
        "equipments",
        ["product_id", "serial_number"],
        unique=True,
    )


_CONFLITO_POR_DONO = """
    SELECT count(*) FROM (
        SELECT owner_id, serial_number
          FROM equipments
         WHERE owner_id IS NOT NULL AND serial_number IS NOT NULL
         GROUP BY owner_id, serial_number
        HAVING count(*) > 1
    ) g
"""

_CONFLITO_ENTRE_ORFAOS = """
    SELECT count(*) FROM (
        SELECT serial_number
          FROM equipments
         WHERE owner_id IS NULL AND serial_number IS NOT NULL
         GROUP BY serial_number
        HAVING count(*) > 1
    ) g
"""


def downgrade() -> None:
    # Pré-validação acrescentada em 02/09/2026. Os dois indices abaixo são
    # UNIQUE e podem não caber no dado de hoje — o docstring já previa isso
    # ("quem precisar voltar resolve os casos antes"), mas o `CREATE UNIQUE
    # INDEX` estourando sozinho dá um erro que não diz quantos casos existem,
    # não diz o que fazer, e AINDA POR CIMA imprime o número de série do
    # aparelho conflitante na mensagem de erro do PostgreSQL.
    #
    # NULL não conflita em nenhum dos dois: em SQL, NULL nunca é igual a NULL.
    # Por isso as duas consultas filtram explicitamente — contar os nulos daria
    # falso positivo e bloquearia rollback legítimo.
    bind = op.get_bind()
    por_dono = bind.execute(text(_CONFLITO_POR_DONO)).scalar_one()
    entre_orfaos = bind.execute(text(_CONFLITO_ENTRE_ORFAOS)).scalar_one()

    if por_dono or entre_orfaos:
        raise RuntimeError(
            "ROLLBACK BLOQUEADO: o dado de hoje não cabe na chave antiga.\n"
            "\n"
            f"    uq_equipments_owner_serial   (owner_id, serial_number): {por_dono} grupo(s)\n"
            f"    uq_equipments_orphan_serial  (serial_number, só órfãos): {entre_orfaos} grupo(s)\n"
            "\n"
            "A chave de hoje é (product_id, serial_number). A antiga era por dono, e\n"
            "proíbe o mesmo dono ter a mesma série em produtos diferentes — que a\n"
            "chave atual permite de propósito.\n"
            "\n"
            "Nada foi apagado nem deduplicado: reconciliar é decisão humana. Os casos\n"
            "saem daqui, e o dado NÃO é despejado nesta mensagem por ser série de\n"
            "aparelho de cliente:\n"
            "\n"
            "    SELECT owner_id, serial_number, count(*) FROM equipments\n"
            "     WHERE owner_id IS NOT NULL AND serial_number IS NOT NULL\n"
            "     GROUP BY 1, 2 HAVING count(*) > 1;\n"
        )

    op.drop_index("uq_equipments_product_serial", table_name="equipments")
    op.create_index(
        "uq_equipments_owner_serial",
        "equipments",
        ["owner_id", "serial_number"],
        unique=True,
    )
    op.create_index(
        "uq_equipments_orphan_serial",
        "equipments",
        ["serial_number"],
        unique=True,
        postgresql_where=text("owner_id IS NULL"),
    )
