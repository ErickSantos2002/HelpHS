"""
O ramal da API4COM é provisionamento de admin — e de mais ninguém.

Por que este arquivo existe: `api4com_extension` é o campo que vai decidir, na
Fase 2C, COM QUAL IDENTIDADE uma ligação sai. Quem controla o próprio ramal
controla de quem a ligação parece ter vindo. Por isso a regra aqui é mais
apertada que a do papel: nem o próprio técnico mexe no seu.

São três guardas distintas, e cada uma fecha uma porta diferente:

1. `_guarda_de_atribuicao_de_ramal` — QUEM pode atribuir. Olha se o campo veio,
   não o valor: `null` é remover, e um não-admin mandando `null` estaria
   apagando ramal alheio.
2. `_guarda_de_ramal_do_cliente` — cliente não origina ligação, logo não tem
   ramal. Olha o estado RESULTANTE, o que cobre também rebaixar a cliente quem
   já tem ramal.
3. `_guarda_de_ramal_unico` — um ramal, um usuário, com 409 em vez do
   `IntegrityError` cru.

E há a defesa que não é guarda nenhuma: o `exclude` do `PATCH /users/me`, igual
ao do `role`. Uma palavra, e por isso testada.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import UserRole, UserStatus

_RAMAL = "1000"
_OUTRO_RAMAL = "1001"


def _usuario(role=UserRole.client, ramal=None, uid=None):
    u = MagicMock()
    u.id = uid or uuid.uuid4()
    u.name = f"Pessoa {role.value}"
    u.email = f"{uuid.uuid4().hex[:8]}@teste.com"
    u.role = role
    u.status = UserStatus.active
    u.phone = "+5581999999999"
    u.department = None
    u.avatar_url = None
    u.last_login = None
    u.lgpd_consent = True
    u.lgpd_consent_at = None
    u.email_verified = True
    u.company_name = None
    u.cnpj = None
    u.company_cep = None
    u.company_address = None
    u.company_city = None
    u.company_state = None
    u.onboarding_completed = True
    u.api4com_extension = ramal
    u.ai_enabled = True
    u.created_at = datetime.now(UTC)
    u.updated_at = datetime.now(UTC)
    return u


class _Sessao:
    """Sessão falsa com respostas EM SEQUÊNCIA.

    `update_user` consulta o alvo e, quando um ramal é enviado, consulta de
    novo para ver se o ramal já é de alguém. Um mock que devolvesse sempre a
    mesma coisa faria a segunda consulta achar o próprio alvo e inventar um
    conflito que não existe.
    """

    def __init__(self, *respostas):
        self._respostas = list(respostas)
        self._n = 0
        self.add = MagicMock()
        self.commit = AsyncMock()
        self.refresh = AsyncMock()

    async def execute(self, *a, **k):
        valor = self._respostas[min(self._n, len(self._respostas) - 1)]
        self._n += 1
        r = MagicMock()
        r.scalar_one_or_none.return_value = valor
        return r


def _prepara(ator, sessao):
    from app.core.database import get_db
    from app.core.security import get_current_user

    async def _db():
        yield sessao

    async def _atual():
        return ator

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _atual


async def _patch(ator, alvo_id, corpo, sessao):
    _prepara(ator, sessao)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
        return await http.patch(f"/api/v1/users/{alvo_id}", json=corpo)


@pytest.fixture(autouse=True)
def _limpa():
    yield
    app.dependency_overrides.clear()


# ── Quem pode configurar ─────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_configura_ramal_de_tecnico():
    admin = _usuario(UserRole.admin)
    alvo = _usuario(UserRole.technician)
    # alvo encontrado; nenhuma outra pessoa com o ramal
    resposta = await _patch(admin, alvo.id, {"api4com_extension": _RAMAL}, _Sessao(alvo, None))

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["api4com_extension"] == _RAMAL
    assert alvo.api4com_extension == _RAMAL


@pytest.mark.asyncio
async def test_admin_configura_ramal_de_outro_admin():
    admin = _usuario(UserRole.admin)
    alvo = _usuario(UserRole.admin)
    resposta = await _patch(admin, alvo.id, {"api4com_extension": _RAMAL}, _Sessao(alvo, None))

    assert resposta.status_code == 200, resposta.text
    assert alvo.api4com_extension == _RAMAL


@pytest.mark.asyncio
async def test_admin_remove_o_ramal():
    """`null` é operação, não ausência: é assim que se desvincula."""
    admin = _usuario(UserRole.admin)
    alvo = _usuario(UserRole.technician, ramal=_RAMAL)
    resposta = await _patch(admin, alvo.id, {"api4com_extension": None}, _Sessao(alvo, None))

    assert resposta.status_code == 200, resposta.text
    assert alvo.api4com_extension is None


@pytest.mark.asyncio
async def test_campo_limpo_no_formulario_tambem_remove():
    """O front manda `""`, não `null`, quando o usuário esvazia o campo."""
    admin = _usuario(UserRole.admin)
    alvo = _usuario(UserRole.technician, ramal=_RAMAL)
    resposta = await _patch(admin, alvo.id, {"api4com_extension": ""}, _Sessao(alvo, None))

    assert resposta.status_code == 200, resposta.text
    assert alvo.api4com_extension is None, "string vazia virou valor em vez de remoção"


@pytest.mark.asyncio
async def test_tecnico_nao_altera_o_proprio_ramal():
    tecnico = _usuario(UserRole.technician)
    resposta = await _patch(
        tecnico, tecnico.id, {"api4com_extension": _RAMAL}, _Sessao(tecnico, None)
    )

    assert resposta.status_code == 403, resposta.text
    assert tecnico.api4com_extension is None


@pytest.mark.asyncio
async def test_tecnico_nao_altera_ramal_alheio():
    tecnico = _usuario(UserRole.technician)
    alvo = _usuario(UserRole.technician)
    resposta = await _patch(tecnico, alvo.id, {"api4com_extension": _RAMAL}, _Sessao(alvo, None))

    assert resposta.status_code == 403
    assert alvo.api4com_extension is None


@pytest.mark.asyncio
async def test_tecnico_nao_apaga_ramal_alheio_mandando_nulo():
    """A guarda olha se o campo VEIO, não o valor — senão nulo passaria."""
    tecnico = _usuario(UserRole.technician)
    alvo = _usuario(UserRole.technician, ramal=_RAMAL)
    resposta = await _patch(tecnico, alvo.id, {"api4com_extension": None}, _Sessao(alvo, None))

    assert resposta.status_code == 403, resposta.text
    assert alvo.api4com_extension == _RAMAL


@pytest.mark.asyncio
async def test_cliente_nao_altera_ramal():
    cliente = _usuario(UserRole.client)
    alvo = _usuario(UserRole.technician)
    resposta = await _patch(cliente, alvo.id, {"api4com_extension": _RAMAL}, _Sessao(alvo, None))

    assert resposta.status_code == 403
    assert alvo.api4com_extension is None


@pytest.mark.asyncio
async def test_o_proprio_perfil_nao_provisiona_ramal():
    """`PATCH /users/me` descarta o campo, como já descarta o papel."""
    from app.core.database import get_db
    from app.core.security import get_current_user

    eu = _usuario(UserRole.technician)
    sessao = _Sessao(eu)

    async def _db():
        yield sessao

    async def _atual():
        return eu

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _atual

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
        resposta = await http.patch(
            "/api/v1/users/me", json={"api4com_extension": _RAMAL, "name": "Nome Novo"}
        )

    assert resposta.status_code == 200, resposta.text
    assert eu.api4com_extension is None, "o próprio perfil se deu um ramal"
    assert eu.name == "Nome Novo", "a requisição nem chegou — o teste não prova nada"


# ── Cliente não tem ramal ────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_nao_da_ramal_a_cliente():
    admin = _usuario(UserRole.admin)
    alvo = _usuario(UserRole.client)
    resposta = await _patch(admin, alvo.id, {"api4com_extension": _RAMAL}, _Sessao(alvo, None))

    assert resposta.status_code == 422, resposta.text
    assert alvo.api4com_extension is None


@pytest.mark.asyncio
async def test_rebaixar_a_cliente_quem_tem_ramal_e_recusado():
    """O caminho que uma guarda de campo deixaria passar."""
    admin = _usuario(UserRole.admin)
    alvo = _usuario(UserRole.technician, ramal=_RAMAL)
    resposta = await _patch(admin, alvo.id, {"role": "client"}, _Sessao(alvo, None))

    assert resposta.status_code == 422, resposta.text
    assert alvo.role == UserRole.technician
    assert alvo.api4com_extension == _RAMAL


@pytest.mark.asyncio
async def test_rebaixar_a_cliente_junto_com_a_remocao_do_ramal_funciona():
    """O jeito certo de fazer a mesma coisa: tirar o ramal na mesma requisição."""
    admin = _usuario(UserRole.admin)
    alvo = _usuario(UserRole.technician, ramal=_RAMAL)
    resposta = await _patch(
        admin, alvo.id, {"role": "client", "api4com_extension": None}, _Sessao(alvo, None)
    )

    assert resposta.status_code == 200, resposta.text
    assert alvo.api4com_extension is None


# ── Um ramal, um usuário ─────────────────────────────────────


@pytest.mark.asyncio
async def test_ramal_ja_vinculado_devolve_409_e_nao_500():
    admin = _usuario(UserRole.admin)
    alvo = _usuario(UserRole.technician)
    dono = _usuario(UserRole.technician, ramal=_RAMAL)
    # 1ª consulta acha o alvo; 2ª acha quem já tem o ramal
    resposta = await _patch(admin, alvo.id, {"api4com_extension": _RAMAL}, _Sessao(alvo, dono))

    assert resposta.status_code == 409, resposta.text
    assert alvo.api4com_extension is None


@pytest.mark.asyncio
async def test_regravar_o_mesmo_ramal_no_proprio_dono_nao_e_conflito():
    """A consulta exclui o próprio usuário: idempotência não é colisão."""
    admin = _usuario(UserRole.admin)
    alvo = _usuario(UserRole.technician, ramal=_RAMAL)
    resposta = await _patch(admin, alvo.id, {"api4com_extension": _RAMAL}, _Sessao(alvo, None))

    assert resposta.status_code == 200, resposta.text
    assert alvo.api4com_extension == _RAMAL


@pytest.mark.asyncio
async def test_remover_ramal_nao_consulta_conflito():
    """Nulo não colide com ninguém — e vários nulos convivem sob o UNIQUE."""
    admin = _usuario(UserRole.admin)
    alvo = _usuario(UserRole.technician, ramal=_RAMAL)
    sessao = _Sessao(alvo, _usuario(UserRole.technician, ramal=_RAMAL))
    resposta = await _patch(admin, alvo.id, {"api4com_extension": None}, sessao)

    assert resposta.status_code == 200, resposta.text
    assert alvo.api4com_extension is None


# ── Auditoria ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_alteracao_do_ramal_entra_no_audit_log():
    from app.models.models import AuditAction, AuditLog

    admin = _usuario(UserRole.admin)
    alvo = _usuario(UserRole.technician)
    sessao = _Sessao(alvo, None)
    resposta = await _patch(admin, alvo.id, {"api4com_extension": _OUTRO_RAMAL}, sessao)

    assert resposta.status_code == 200, resposta.text
    registros = [c.args[0] for c in sessao.add.call_args_list if isinstance(c.args[0], AuditLog)]
    assert len(registros) == 1, "a alteração do ramal não foi auditada"
    assert registros[0].action == AuditAction.update
    assert registros[0].entity_type == "user"
    assert registros[0].user_id == admin.id
    assert registros[0].entity_id == alvo.id


# ── Contrato dos schemas ─────────────────────────────────────


def test_usercreate_nao_provisiona_ramal():
    """Conta nasce sem ramal. O provisionamento é um segundo ato, de admin."""
    from app.schemas.user import UserCreate

    assert "api4com_extension" not in UserCreate.model_fields

    corpo = UserCreate.model_validate(
        {
            "name": "Conta Nova",
            "email": "nova@teste.com",
            "password": "SenhaForte1",
            "role": "technician",
            "api4com_extension": _RAMAL,
        }
    )
    assert not hasattr(corpo, "api4com_extension")


def test_userupdate_e_userresponse_conhecem_o_campo():
    from app.schemas.user import UserResponse, UserUpdate

    assert "api4com_extension" in UserUpdate.model_fields
    assert "api4com_extension" in UserResponse.model_fields


def test_o_ramal_e_string_e_nao_numero():
    """O fornecedor declara identificador textual; `0700` não pode virar 700."""
    from app.schemas.user import UserUpdate

    assert UserUpdate.model_validate({"api4com_extension": "0700"}).api4com_extension == "0700"


def test_a_recusa_de_ramal_tem_um_unico_autor():
    """Mensagem repetida seriam duas regras se separando — como no papel."""
    from pathlib import Path

    fonte = Path(__file__).resolve().parents[1] / "app" / "routers" / "users.py"
    texto = fonte.read_text(encoding="utf-8")
    assert texto.count("Apenas administradores podem configurar o ramal da telefonia.") == 1


def test_o_modelo_declara_o_indice_unico():
    """A unicidade é invariante de banco, não disciplina de endpoint."""
    from app.models.models import User

    indices = {i.name: i for i in User.__table__.indexes}
    assert "uq_users_api4com_extension" in indices
    alvo = indices["uq_users_api4com_extension"]
    assert alvo.unique is True
    assert [c.name for c in alvo.columns] == ["api4com_extension"]
    assert User.__table__.c.api4com_extension.nullable is True
