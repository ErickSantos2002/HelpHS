"""
O filtro `?category=` das listagens recusa valor desconhecido com 422 (INC-01, frente C).

`GET /tickets` e `GET /kb/articles` recebiam `category` como `str` cru e o
comparavam com a coluna do enum `ticketcategory`. O PostgreSQL não converte um
literal que não está no tipo, então `other` (que saiu do enum no PR #28),
`xyz` ou `General` derrubavam a consulta: **500**, com `invalid input value for
enum` no log. Agora o valor é validado no tipo, antes de qualquer consulta, e o
erro sai no formato de sempre: `{"detail": [{"field": "category", ...}]}`.

Ausente ou vazio continua sendo "sem filtro" (200). O front manda `""` quando a
pessoa limpa o menu, e recusar isso quebraria a listagem.

Aqui a sessão é de mentira e só registra as consultas, o que basta para provar
que o 422 sai ANTES do banco. O 500 real e a correção contra o PostgreSQL 17
foram reproduzidos fora da suíte (relatório do INC-01): o SQLite não tem enum
e não reproduz o erro.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql

from app.main import app
from app.models.models import TicketCategory, UserRole, UserStatus
from app.utils.categoria import categoria_do_filtro

ROTAS = ["/api/v1/tickets", "/api/v1/kb/articles"]


@pytest.fixture(autouse=True)
def _limpa_overrides():
    yield
    app.dependency_overrides.clear()


def _usuario(papel: UserRole) -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.role = papel
    u.status = UserStatus.active
    u.company_id = None
    return u


def _sessao() -> MagicMock:
    """Responde 0 linhas e guarda cada consulta, já compilada para o PostgreSQL."""
    sessao = MagicMock()
    sessao.consultas = []

    async def _execute(stmt, *a, **kw):
        sessao.consultas.append(
            stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        )
        resultado = MagicMock()
        resultado.scalar_one.return_value = 0
        resultado.scalars.return_value.all.return_value = []
        resultado.all.return_value = []
        return resultado

    sessao.execute = AsyncMock(side_effect=_execute)
    return sessao


async def _get(rota: str, papel: UserRole, params: dict):
    from app.core.database import get_db
    from app.core.security import get_current_user

    sessao = _sessao()

    async def _db():
        yield sessao

    async def _eu():
        return _usuario(papel)

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _eu
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(rota, params=params)
    return resp, sessao


# ── O tipo ─────────────────────────────────────────────────────


@pytest.mark.parametrize("valor", [None, "", "   "])
def test_ausente_ou_vazio_e_sem_filtro(valor) -> None:
    assert categoria_do_filtro(valor) is None


@pytest.mark.parametrize("categoria", list(TicketCategory))
def test_toda_categoria_do_enum_passa(categoria: TicketCategory) -> None:
    assert categoria_do_filtro(categoria.value) is categoria


@pytest.mark.parametrize("valor", ["other", "xyz", "General", " general"])
def test_valor_fora_do_enum_e_recusado(valor: str) -> None:
    with pytest.raises(ValueError, match="Valor inválido. Opções: hardware"):
        categoria_do_filtro(valor)


# ── As rotas ───────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("papel", [UserRole.admin, UserRole.client])
@pytest.mark.parametrize("valor", ["other", "xyz", "General"])
async def test_categoria_invalida_e_422_antes_do_banco(rota, papel, valor) -> None:
    resp, sessao = await _get(rota, papel, {"category": valor})

    assert resp.status_code == 422, resp.text
    (erro,) = resp.json()["detail"]
    assert erro["field"] == "category"
    assert erro["message"].startswith("Valor inválido. Opções: ")
    assert "other" not in erro["message"]
    assert sessao.consultas == []


@pytest.mark.asyncio
@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("params", [{}, {"category": ""}])
async def test_sem_categoria_lista_sem_filtrar(rota, params) -> None:
    resp, sessao = await _get(rota, UserRole.admin, params)

    assert resp.status_code == 200, resp.text
    assert sessao.consultas
    filtrando = [str(q) for q in sessao.consultas if "category =" in str(q)]
    assert not filtrando, filtrando


@pytest.mark.asyncio
@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("valor", ["general", "hardware"])
async def test_categoria_valida_filtra(rota, valor) -> None:
    resp, sessao = await _get(rota, UserRole.admin, {"category": valor})

    assert resp.status_code == 200, resp.text
    assert any(f"category = '{valor}'" in str(q) for q in sessao.consultas)


# ── O que não pode mudar ───────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("rota", ROTAS)
async def test_sem_sessao_continua_401_mesmo_com_categoria_invalida(rota) -> None:
    """A autenticação vem antes da validação: quem não entrou não descobre nada."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(rota, params={"category": "xyz"})
    assert resp.status_code == 401, resp.text


@pytest.mark.parametrize("rota", ROTAS)
def test_openapi_mantem_o_tipo_e_lista_os_valores(rota) -> None:
    (param,) = [
        p for p in app.openapi()["paths"][rota]["get"]["parameters"] if p["name"] == "category"
    ]
    assert param["required"] is False
    assert param["schema"]["anyOf"] == [{"type": "string"}, {"type": "null"}]
    for categoria in TicketCategory:
        assert categoria.value in param["description"]
    assert "other" not in param["description"]
