"""
A autorização da foto para outras pessoas — o que se prova sem banco.

- nenhum schema de escrita genérica tem o campo: PATCH, cadastro, onboarding e
  criação pelo admin não têm por onde mudar a escolha;
- nenhuma resposta de usuário a expõe — nem a terceiros, nem o histórico;
- o texto vigente sai da configuração, e versão desconhecida desliga em vez de
  gravar uma versão sem texto;
- a minuta se identifica como minuta, e a explicação muda com o papel.

O comportamento da rota (estado, evento, concorrência) é provado contra o
PostgreSQL em `test_exibicao_da_foto_postgres.py`.
"""

from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.models.models import UserRole
from app.schemas.auth import RegisterRequest
from app.schemas.user import (
    AvatarExibicaoUpdate,
    OnboardingUpdate,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.services import exibicao_da_foto

_CAMPO = "avatar_visivel_a_terceiros"


@pytest.mark.parametrize("schema", [UserUpdate, UserCreate, OnboardingUpdate, RegisterRequest])
def test_nenhuma_escrita_generica_tem_o_campo(schema):
    assert _CAMPO not in schema.model_fields
    assert "autorizada" not in schema.model_fields


def test_nenhuma_resposta_de_usuario_expoe_a_escolha():
    """`UserResponse` serve a listas e ao detalhe de OUTRAS contas."""
    assert _CAMPO not in UserResponse.model_fields


@pytest.mark.parametrize(
    "corpo",
    [
        {"autorizada": "true"},
        {"autorizada": 1},
        {"autorizada": None},
        {},
        {"autorizada": True, "user_id": "x"},
        {"autorizada": True, "versao_aviso": "x" * 41},
    ],
)
def test_o_pedido_nao_coage_nem_aceita_campo_a_mais(corpo):
    with pytest.raises(ValueError):
        AvatarExibicaoUpdate.model_validate(corpo)


def test_sem_versao_configurada_a_autorizacao_fica_desligada():
    assert (
        exibicao_da_foto.aviso_vigente(SimpleNamespace(avatar_aviso_exibicao_versao=None)) is None
    )


def test_versao_configurada_sem_texto_tambem_desliga():
    config = SimpleNamespace(avatar_aviso_exibicao_versao="NAO-EXISTE")
    assert exibicao_da_foto.aviso_vigente(config) is None


def test_os_textos_disponiveis_hoje_sao_todos_minuta():
    """Nenhum texto final existe ainda. Quando existir, entra com outro nome —
    e este teste é o lembrete de que o nome é o que o registro grava."""
    assert exibicao_da_foto.AVISOS
    for versao, aviso in exibicao_da_foto.AVISOS.items():
        assert versao == aviso.versao
        assert versao.startswith("MINUTA-")
        # Nenhum texto foi aprovado nesta rodada.
        assert aviso.aprovado is False


def _config(ambiente: str, versao: str | None):
    """Configurações isoladas — uma cópia, nunca o objeto global."""
    return get_settings().model_copy(
        update={"app_env": ambiente, "avatar_aviso_exibicao_versao": versao}
    )


def _texto_de_teste(versao: str, *, aprovado: bool) -> exibicao_da_foto.Aviso:
    return exibicao_da_foto.Aviso(
        versao=versao,
        rotulo="TESTE — rótulo",
        aprovado=aprovado,
        explicacao_cliente=("TESTE",),
        explicacao_equipe=("TESTE",),
    )


@pytest.mark.parametrize("ambiente", ["production", "prod"])
def test_em_producao_a_minuta_configurada_nao_fica_disponivel(ambiente):
    """Pôr o nome da minuta no painel não a transforma em texto aprovado."""
    assert exibicao_da_foto.aviso_vigente(_config(ambiente, "MINUTA-2026-10-21")) is None


def test_em_producao_texto_de_teste_nao_aprovado_nao_fica_disponivel(monkeypatch):
    texto = _texto_de_teste("TESTE-NAO-APROVADO", aprovado=False)
    monkeypatch.setitem(exibicao_da_foto.AVISOS, texto.versao, texto)

    assert exibicao_da_foto.aviso_vigente(_config("production", texto.versao)) is None
    assert exibicao_da_foto.aviso_vigente(_config("development", texto.versao)) is texto


def test_em_producao_so_vale_a_marca_explicita_de_aprovacao(monkeypatch):
    """O nome não decide: um texto de TESTE marcado como aprovado passa, e
    um sem marca não passa, mesmo sem "MINUTA" no nome. (Texto fictício, só
    neste teste — nada é aprovado no catálogo.)"""
    marcado = _texto_de_teste("TESTE-MARCADO-COMO-APROVADO", aprovado=True)
    sem_marca = _texto_de_teste("VERSAO-QUE-PARECE-FINAL", aprovado=False)
    monkeypatch.setitem(exibicao_da_foto.AVISOS, marcado.versao, marcado)
    monkeypatch.setitem(exibicao_da_foto.AVISOS, sem_marca.versao, sem_marca)

    assert exibicao_da_foto.aviso_vigente(_config("production", marcado.versao)) is marcado
    assert exibicao_da_foto.aviso_vigente(_config("production", sem_marca.versao)) is None


def test_fora_de_producao_a_minuta_serve_para_exercitar_o_fluxo():
    aviso = exibicao_da_foto.aviso_vigente(_config("development", "MINUTA-2026-10-21"))
    assert aviso is not None and aviso.versao == "MINUTA-2026-10-21"


def test_em_producao_versao_inexistente_continua_indisponivel():
    assert exibicao_da_foto.aviso_vigente(_config("production", "NAO-EXISTE")) is None


@pytest.mark.parametrize(
    ("papel", "trecho"),
    [
        (UserRole.client, "Outros clientes nunca veem a sua foto"),
        (UserRole.technician, "nos chamados em que você é o responsável"),
        (UserRole.admin, "nos chamados em que você é o responsável"),
    ],
)
def test_a_explicacao_descreve_a_matriz_do_papel(papel, trecho):
    [aviso] = exibicao_da_foto.AVISOS.values()
    explicacao = " ".join(aviso.explicacao_para(papel))
    assert trecho in explicacao
    assert "opcional" in explicacao
    # Não promete o que não dá para cumprir.
    assert "uma hora" not in explicacao
    assert "copiada não some" in explicacao
