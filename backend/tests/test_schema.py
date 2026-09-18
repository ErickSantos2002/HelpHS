"""
Invariantes do schema declarado (`app/models/models.py`).

Testes de METADATA, não de banco: rodam sem conexão nenhuma e valem para os
dois bancos. O que prendem é a coerência da declaração — o tipo de erro que
não aparece em produção, porque lá o schema foi construído pelas migrations do
Alembic, e só estoura quando alguém pede `create_all` (uma fixture de teste,
um ambiente novo).
"""

from collections import Counter

from app.models.models import Base


def test_nenhum_indice_e_declarado_duas_vezes():
    """
    `index=True` na coluna já gera um índice chamado `ix_<tabela>_<coluna>`.
    Declarar um `Index()` com esse mesmo nome em `__table_args__` cria a
    definição duas vezes: o `create_all` emite dois CREATE INDEX e o segundo
    falha com "relation already exists".

    Produção não sofria porque quem construiu o schema foi o Alembic, que cria
    o índice uma vez só — mas a divergência entre modelo e migration é dívida,
    e trava qualquer fixture que monte o schema a partir dos modelos.
    """
    nomes = [indice.name for tabela in Base.metadata.tables.values() for indice in tabela.indexes]
    duplicados = sorted(nome for nome, quantas in Counter(nomes).items() if quantas > 1)

    assert duplicados == [], (
        f"índice(s) declarado(s) mais de uma vez: {duplicados}. "
        "Provavelmente `index=True` na coluna e um `Index()` de mesmo nome em __table_args__."
    )


def test_categoria_nao_tem_mais_o_valor_other():
    """`other` saiu do enum em 18/09/2026, e este caso prende a saída.

    Ele não era categoria de nada: zero chamados, zero artigos e zero linhas de
    histórico o usavam — medido em produção antes de mexer. O que ele fazia era
    dar à API uma oitava resposta possível que ninguém sabia ler, e à tela uma
    opção que empurrava a pessoa para longe de escolher a categoria certa.

    "Geral" já é o balde de quem não sabe classificar. Dois baldes não são
    redundância: são duas perguntas diferentes feitas à mesma pessoa, com a
    mesma resposta esperada.

    Voltar a acrescentá-lo exige migration — o tipo no Postgres é um só, o
    `ticketcategory`, e serve `tickets.category` e `kb_articles.category`.
    """
    from app.models.models import TicketCategory

    assert [c.value for c in TicketCategory] == [
        "hardware",
        "software",
        "network",
        "access",
        "email",
        "security",
        "general",
    ]
