"""
A classificação do script de preenchimento da empresa do equipamento — a parte
que decide, sem banco.

`classifica` é pura de propósito: é ela que poderia, com um descuido, dar a um
aparelho a empresa errada. A gravação e o levantamento rodam contra PostgreSQL
em `test_empresa_do_equipamento_postgres.py`.
"""

import pytest

from scripts.preenche_empresa_do_equipamento import CATEGORIAS, Linha, classifica, planeja

_EMPRESA = "empresa-x"
_OUTRA = "empresa-y"


def _linha(**mudancas) -> Linha:
    base = {
        "id": "aparelho-1",
        "nome": "Titan #1",
        "serie": "SN-1",
        "empresa_atual": None,
        "responsavel_id": "cliente-1",
        "responsavel_papel": "client",
        "responsavel_situacao": "active",
        "empresa_do_responsavel": _EMPRESA,
        "empresas_de_usuarios": (),
        "empresas_de_chamados": (),
    }
    return Linha(**{**base, **mudancas})


def test_responsavel_ativo_e_vinculado_sem_sinal_contrario_e_preenchivel():
    assert classifica(_linha())[0] == "preenchivel"


def test_gente_da_mesma_empresa_ligada_ao_aparelho_nao_e_sinal_contrario():
    linha = _linha(empresas_de_usuarios=(_EMPRESA,), empresas_de_chamados=(_EMPRESA,))

    assert classifica(linha)[0] == "preenchivel"


@pytest.mark.parametrize(
    ("mudancas", "trecho"),
    [
        ({"empresas_de_usuarios": (_OUTRA,)}, "usuário(s) do aparelho"),
        ({"empresas_de_chamados": (_OUTRA,)}, "chamado(s) aberto(s)"),
        ({"empresas_de_usuarios": (_EMPRESA, _OUTRA)}, "usuário(s) do aparelho"),
    ],
)
def test_alguem_de_outra_empresa_ligado_ao_aparelho_e_ambiguo(mudancas, trecho):
    categoria, motivo = classifica(_linha(**mudancas))

    assert categoria == "ambiguo"
    assert trecho in motivo and _OUTRA in motivo


def test_sem_responsavel():
    linha = _linha(
        responsavel_id=None,
        responsavel_papel=None,
        responsavel_situacao=None,
        empresa_do_responsavel=None,
    )

    assert classifica(linha)[0] == "sem_responsavel"


def test_responsavel_sem_vinculo():
    assert classifica(_linha(empresa_do_responsavel=None))[0] == "responsavel_sem_vinculo"


@pytest.mark.parametrize(
    "mudancas",
    [
        {"responsavel_situacao": "inactive"},
        {"responsavel_situacao": "anonymized"},
        {"responsavel_papel": "technician"},
        {"responsavel_papel": "admin"},
    ],
)
def test_responsavel_que_nao_e_cliente_ativo_nao_empresta_a_empresa(mudancas):
    """Mesmo com `company_id` na conta: conta parada não fala pelo aparelho."""
    assert classifica(_linha(**mudancas))[0] == "responsavel_inapto"


def test_inapto_vence_sem_vinculo():
    """A ordem das perguntas: primeiro se a conta serve, depois se tem empresa."""
    linha = _linha(responsavel_situacao="inactive", empresa_do_responsavel=None)

    assert classifica(linha)[0] == "responsavel_inapto"


def test_aparelho_que_ja_tem_empresa_so_e_informado():
    linha = _linha(empresa_atual=_OUTRA)

    assert classifica(linha)[0] == "divergente"


def test_o_plano_tem_todas_as_categorias_e_guarda_a_empresa_certa():
    plano = planeja(
        [
            _linha(id="limpo"),
            _linha(id="de_fora", empresas_de_usuarios=(_OUTRA,)),
            _linha(id="ja_tem", empresa_atual=_OUTRA),
        ]
    )

    assert tuple(plano) == CATEGORIAS
    assert [(i.id, i.empresa) for i in plano["preenchivel"]] == [("limpo", _EMPRESA)]
    assert [i.id for i in plano["ambiguo"]] == ["de_fora"]
    # No divergente a empresa mostrada é a que o aparelho TEM, não a do responsável.
    assert [(i.id, i.empresa) for i in plano["divergente"]] == [("ja_tem", _OUTRA)]
    assert plano["sem_responsavel"] == []


def test_sem_empresa_por_decisao_nunca_e_preenchivel():
    """Responsável ativo, vinculado, sem sinal contrário — e ainda assim não."""
    categoria, motivo = classifica(_linha(por_decisao=True))

    assert categoria == "sem_empresa_por_decisao"
    assert "de propósito" in motivo


@pytest.mark.parametrize(
    "mudancas",
    [
        {"responsavel_id": None},
        {"responsavel_situacao": "inactive"},
        {"empresa_do_responsavel": None},
        {"empresas_de_usuarios": (_OUTRA,)},
    ],
)
def test_a_decisao_da_equipe_vence_qualquer_outro_motivo(mudancas):
    assert classifica(_linha(por_decisao=True, **mudancas))[0] == "sem_empresa_por_decisao"


def test_sem_a_marca_a_linha_segue_o_caminho_de_sempre():
    assert classifica(_linha(por_decisao=False))[0] == "preenchivel"
    assert "sem_empresa_por_decisao" in CATEGORIAS
    assert planeja([_linha(id="m", por_decisao=True)])["preenchivel"] == []
