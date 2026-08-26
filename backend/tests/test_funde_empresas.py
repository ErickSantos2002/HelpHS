"""
O plano de fusão de empresas duplicadas — a parte que decide, sem banco.

`planeja_fusao` é pura de propósito: é ela que poderia eleger a empresa errada
e mandar cliente e nota de uma empresa real para o lugar errado. A parte que
grava não tem decisão nenhuma dentro, então o que precisa de teste é esta.
"""

from datetime import UTC, datetime, timedelta

from scripts.funde_empresas_duplicadas import Empresa, planeja_fusao

_ONTEM = datetime(2026, 8, 25, 10, 0, tzinfo=UTC)
_GRUPO = "grupo-1"


def _empresa(nome, *, clientes=0, notas=0, idade_em_dias=0, doc="12345678000110", grupo=_GRUPO):
    return Empresa(
        id=f"id-{nome}",
        doc=doc,
        nome=nome,
        group_id=grupo,
        criada_em=_ONTEM + timedelta(days=idade_em_dias),
        clientes=clientes,
        notas=notas,
    )


def test_sobrevive_a_que_tem_mais_conteudo():
    """O critério é preservar história, não a ordem de criação."""
    vazia = _empresa("vazia", idade_em_dias=0)
    cheia = _empresa("cheia", clientes=2, notas=1, idade_em_dias=5)

    fusoes, recusadas = planeja_fusao([vazia, cheia])

    assert recusadas == []
    assert len(fusoes) == 1
    assert fusoes[0].sobrevivente.nome == "cheia"
    assert [a.nome for a in fusoes[0].absorvidas] == ["vazia"]


def test_empate_de_conteudo_fica_com_a_mais_antiga():
    """Duas cascas vazias: sem critério de conteúdo, a idade desempata."""
    nova = _empresa("nova", idade_em_dias=10)
    antiga = _empresa("antiga", idade_em_dias=0)

    fusoes, _ = planeja_fusao([nova, antiga])

    assert fusoes[0].sobrevivente.nome == "antiga"


def test_clientes_e_notas_somam_no_criterio():
    """
    Uma com 3 notas ganha de uma com 1 cliente.

    Poderia ser o contrário — cliente "vale mais" que nota — mas as duas são
    movidas para o sobrevivente de qualquer jeito. O que o critério decide é
    só qual id sobrevive; nada se perde na escolha.
    """
    so_cliente = _empresa("so_cliente", clientes=1, idade_em_dias=0)
    so_notas = _empresa("so_notas", notas=3, idade_em_dias=5)

    fusoes, _ = planeja_fusao([so_cliente, so_notas])

    assert fusoes[0].sobrevivente.nome == "so_notas"


def test_grupos_diferentes_nao_sao_fundidos():
    """
    Fundir mudaria a que grupo os clientes pertencem — decisão de operação.

    O script relata e sai de perto. Recusar é o comportamento certo: um script
    que decide isso sozinho move gente de grupo sem ninguém pedir.
    """
    de_um = _empresa("a", grupo="grupo-1")
    de_outro = _empresa("b", grupo="grupo-2")

    fusoes, recusadas = planeja_fusao([de_um, de_outro])

    assert fusoes == []
    assert len(recusadas) == 1
    assert {e.nome for e in recusadas[0]} == {"a", "b"}


def test_cnpj_sem_repeticao_nao_entra_no_plano():
    """Idempotência: rodar de novo depois de fundir não propõe nada."""
    fusoes, recusadas = planeja_fusao([_empresa("unica", clientes=2)])

    assert fusoes == []
    assert recusadas == []


def test_documentos_diferentes_nao_se_misturam():
    """O agrupamento é por CNPJ — o teste que pegaria um `for` mal escrito."""
    a1 = _empresa("a1", doc="11111111000191", idade_em_dias=0)
    a2 = _empresa("a2", doc="11111111000191", idade_em_dias=1)
    b1 = _empresa("b1", doc="22222222000181", idade_em_dias=0)

    fusoes, _ = planeja_fusao([a1, a2, b1])

    assert len(fusoes) == 1
    assert fusoes[0].doc == "11111111000191"
    assert [a.nome for a in fusoes[0].absorvidas] == ["a2"]
