"""
`PATCH /users/me` não pode virar caminho de escalação de privilégio.

Por que este arquivo existe: `PATCH /users/me` e `PATCH /users/{id}` usam o
MESMO schema, `UserUpdate`. O de terceiros tem guarda explícita de papel
(`Apenas administradores podem alterar o tipo de usuário`); o próprio perfil
não tem — ele depende de UMA palavra, o `exclude={"role"}` do `model_dump` em
`update_me`. Antes desta suíte, **nenhum teste cobria `PATCH /users/me`**:
apagar aquele `exclude` passaria verde e daria a qualquer cliente o poder de
se promover a admin.

São duas defesas, com forças diferentes, e vale saber qual é qual:

1. **Campo que não existe em `UserUpdate`** (`status`, `email`, `password`,
   `company_id`, `email_verified`, `mfa_enabled`, `ai_enabled`, ...) é
   descartado pelo Pydantic, que roda com `extra="ignore"`. Defesa estrutural:
   só cai se alguém acrescentar o campo ao schema.

2. **`role` EXISTE no schema** e atravessa a validação intacto. O que o barra
   é só o `exclude` do router. Defesa de uma linha — e é por ela que os
   testes abaixo existem.

Cada teste confere o **valor no objeto depois da requisição**, não o corpo da
resposta: é o `setattr` do router que gravaria, então é o atributo que precisa
provar que nada mudou. E todos alteram o `name` junto, para que "nada mudou"
não possa ser confundido com "a requisição não chegou".
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import UserRole, UserStatus


def _user(role=UserRole.client, status=UserStatus.active):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = "cliente@test.com"
    u.name = "Nome Original"
    u.role = role
    u.status = status
    u.phone = "+5581999999999"
    u.department = None
    u.avatar_url = None
    u.last_login = None
    u.lgpd_consent = True
    u.lgpd_consent_at = None
    u.company_name = None
    u.cnpj = None
    u.company_cep = None
    u.company_address = None
    u.company_city = None
    u.company_state = None
    u.onboarding_completed = True
    u.ai_enabled = True
    u.email_verified = True
    u.mfa_enabled = False
    u.password = "hash-original"
    u.company_id = None
    u.created_at = datetime.now(UTC)
    u.updated_at = datetime.now(UTC)
    return u


def _db(alvo):
    async def _execute(*args, **kwargs):
        resultado = MagicMock()
        resultado.scalar_one_or_none.return_value = alvo
        resultado.scalars.return_value.all.return_value = [alvo] if alvo else []
        resultado.scalar_one.return_value = 1 if alvo else 0
        return resultado

    sessao = AsyncMock()
    sessao.execute = _execute
    sessao.add = MagicMock()
    sessao.commit = AsyncMock()
    sessao.refresh = AsyncMock()

    async def _gen():
        yield sessao

    return _gen


@pytest.fixture(autouse=True)
def _limpa_overrides():
    yield
    app.dependency_overrides.clear()


async def _patch_me(corpo, ator):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _db(ator)
    app.dependency_overrides[get_current_user] = lambda: ator
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
        return await cliente.patch("/api/v1/users/me", json=corpo)


# ── O controle: a requisição realmente chega e grava ───────────


@pytest.mark.asyncio
async def test_o_proprio_perfil_edita_o_que_e_dele():
    """Controle do experimento. Sem ele, todos os testes abaixo passariam
    também se o endpoint estivesse quebrado ou respondendo 404."""
    cliente = _user()
    resposta = await _patch_me({"name": "Nome Novo"}, cliente)
    assert resposta.status_code == 200, resposta.text
    assert cliente.name == "Nome Novo"


# ── `role`: a defesa de uma linha ──────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", ["admin", "technician"])
async def test_cliente_nao_se_promove_pelo_proprio_perfil(papel):
    cliente = _user(role=UserRole.client)
    resposta = await _patch_me({"name": "Nome Novo", "role": papel}, cliente)

    assert resposta.status_code == 200, resposta.text
    # O que importa é o objeto que seria gravado, não o corpo da resposta.
    assert cliente.role == UserRole.client, (
        f"ESCALAÇÃO DE PRIVILÉGIO: o cliente virou {cliente.role} por "
        f"PATCH /users/me — o `exclude={{'role'}}` de update_me caiu"
    )
    assert resposta.json()["role"] == "client"
    # E o resto do pedido foi aplicado: a recusa é do campo, não da requisição.
    assert cliente.name == "Nome Novo"


@pytest.mark.asyncio
async def test_tecnico_nao_se_promove_a_admin_pelo_proprio_perfil():
    """O papel do meio é o que mais interessa: o técnico já é staff, e um
    degrau a mais lhe daria gestão de usuários e de configuração."""
    tecnico = _user(role=UserRole.technician)
    resposta = await _patch_me({"role": "admin"}, tecnico)

    assert resposta.status_code == 200, resposta.text
    assert tecnico.role == UserRole.technician


@pytest.mark.asyncio
async def test_cliente_nao_se_promove_nem_pela_rota_de_terceiros():
    """O outro caminho para o mesmo campo. Aqui a recusa é explícita (403),
    e não silenciosa — a diferença entre os dois endpoints é deliberada e
    fica registrada aqui."""
    from app.core.database import get_db
    from app.core.security import get_current_user

    cliente = _user(role=UserRole.client)
    app.dependency_overrides[get_db] = _db(cliente)
    app.dependency_overrides[get_current_user] = lambda: cliente
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
        resposta = await http.patch(f"/api/v1/users/{cliente.id}", json={"role": "admin"})

    assert resposta.status_code == 403
    assert cliente.role == UserRole.client


# ── Campos que nem existem no schema ───────────────────────────


@pytest.mark.asyncio
async def test_situacao_da_conta_nao_e_editavel_pelo_proprio_perfil():
    """`status` não é campo de `UserUpdate`: o Pydantic o descarta. Se
    alguém o acrescentar ao schema, este teste cai — e é o ponto."""
    cliente = _user(status=UserStatus.active)
    resposta = await _patch_me({"name": "Nome Novo", "status": "inactive"}, cliente)

    assert resposta.status_code == 200, resposta.text
    assert cliente.status == UserStatus.active
    assert cliente.name == "Nome Novo"


@pytest.mark.asyncio
async def test_reativar_a_si_mesmo_nao_funciona_pelo_proprio_perfil():
    """O caminho inverso, que seria o interessante para uma conta desligada:
    conta inativa nem chega aqui (o `get_current_user` a barra antes), mas
    se um dia chegasse, `status` continua fora do schema."""
    inativo = _user(status=UserStatus.inactive)
    resposta = await _patch_me({"status": "active"}, inativo)

    assert resposta.status_code == 200, resposta.text
    assert inativo.status == UserStatus.inactive


@pytest.mark.asyncio
async def test_nenhum_campo_administrativo_atravessa_o_proprio_perfil():
    """Varredura: manda de uma vez tudo que daria poder, identidade ou
    vínculo, e confere campo a campo que nada pegou."""
    cliente = _user()
    antes = {
        "role": cliente.role,
        "status": cliente.status,
        "email": cliente.email,
        "password": cliente.password,
        "company_id": cliente.company_id,
        "email_verified": cliente.email_verified,
        "mfa_enabled": cliente.mfa_enabled,
        "ai_enabled": cliente.ai_enabled,
        "lgpd_consent": cliente.lgpd_consent,
        "onboarding_completed": cliente.onboarding_completed,
        "id": cliente.id,
    }

    resposta = await _patch_me(
        {
            "name": "Nome Novo",
            "role": "admin",
            "status": "inactive",
            "email": "invasor@test.com",
            "password": "SenhaNova1",
            "company_id": str(uuid.uuid4()),
            "email_verified": False,
            "mfa_enabled": True,
            "ai_enabled": False,
            "lgpd_consent": False,
            "onboarding_completed": False,
            "id": str(uuid.uuid4()),
        },
        cliente,
    )

    assert resposta.status_code == 200, resposta.text
    for campo, valor_antigo in antes.items():
        assert getattr(cliente, campo) == valor_antigo, (
            f"`{campo}` foi alterado por PATCH /users/me — campo administrativo "
            f"não pode ser editável pelo próprio usuário"
        )
    assert cliente.name == "Nome Novo"


# ── O que É editável pelo próprio usuário, e é correto que seja ──


@pytest.mark.asyncio
async def test_os_campos_de_cadastro_seguem_editaveis_pelo_dono():
    """O contraponto: a rota existe para isto. Documenta a superfície real
    de `/users/me` — se alguém acrescentar campo a `UserUpdate`, ele entra
    aqui por padrão, e é essa a armadilha que a lista abaixo torna visível.

    ⚠️ `company_cep` e `cnpj` entram por aqui SEM a validação de CEP que o
    onboarding aplica (`OnboardingUpdate`). É defeito anterior à Fase 1A e
    está registrado como tal — não é regressão desta fase.
    """
    cliente = _user()
    resposta = await _patch_me(
        {
            "name": "Nome Novo",
            "department": "Compras",
            "company_name": "Empresa X",
            "company_city": "Recife",
        },
        cliente,
    )

    assert resposta.status_code == 200, resposta.text
    assert cliente.name == "Nome Novo"
    assert cliente.department == "Compras"
    assert cliente.company_name == "Empresa X"
    assert cliente.company_city == "Recife"


def test_o_schema_do_perfil_nao_ganhou_campo_administrativo():
    """Guard de fonte: fixa a superfície de `UserUpdate`.

    Campo novo aqui é editável pelo próprio usuário por padrão — e é assim
    que um campo administrativo entraria sem ninguém decidir. Acrescentar um
    exige atualizar esta lista, o que força a pergunta.
    """
    from app.schemas.user import UserUpdate

    esperados = {
        "name",
        "phone",
        "department",
        "avatar_url",
        "role",  # existe no schema, mas o update_me o exclui — ver testes acima
        "company_name",
        "cnpj",
        "company_cep",
        "company_address",
        "company_city",
        "company_state",
    }
    assert set(UserUpdate.model_fields) == esperados, (
        "a superfície de UserUpdate mudou — confirme que o campo novo pode "
        "mesmo ser editado pelo próprio usuário em PATCH /users/me"
    )
