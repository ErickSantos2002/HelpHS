"""
`POST /users` não pode ser a porta que `PATCH /users/{id}` já tinha fechado.

O sistema tem uma regra declarada sobre papel, e ela vive em `update_user`:
*apenas administradores alteram o tipo de usuário*. Existe desde sempre, tem
suíte própria (`tests/test_escalacao_por_users_me.py`) e cobre as duas rotas de
edição — o próprio perfil e o de terceiros.

`create_user` não a tinha. A rota inteira é `admin | technician`, e dentro dela
o `role` do corpo ia direto para o `User()`. Um técnico criava um administrador
em uma requisição — e depois entrava nele, porque escolheu a senha. A regra
existia, só não valia no único lugar onde a conta nasce.

Esta suíte mede os dois lados da mesma moeda:

* **Fecha**: técnico não produz conta de staff — nem admin, nem outro técnico.
  Criar técnico é escalação também, só que lateral: staff lê chamado alheio e
  nota interna, que é exatamente o que a outra metade desta fase protege.
* **Não fecha demais**: técnico continua criando cliente, que é o uso real da
  tela, e admin continua criando qualquer papel.

Os bloqueios conferem que **nada foi escrito** — nem a consulta de e-mail
saiu. A guarda é de autorização: roda antes de qualquer trabalho, não depois.

⚠️ O front (`UsersPage.tsx`) manda `role` SEMPRE, com `defaultValues:
{role: "client"}`. Por isso a regra olha o papel que RESULTA, e não se o campo
veio no corpo: barrar "mandou `role`" transformaria toda criação de cliente
feita por técnico em 403.
"""

import ast
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import UserRole, UserStatus

_MENSAGEM = "Apenas administradores podem alterar o tipo de usuário."


def _ator(role: UserRole) -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.role = role
    u.status = UserStatus.active
    u.email = f"{role.value}@teste.com"
    u.name = f"Ator {role.value}"
    return u


class _Sessao:
    """Sessão falsa que CONTA as consultas — o bloqueio precisa provar que
    nenhuma saiu, não só que o 403 voltou."""

    def __init__(self) -> None:
        self.consultas = 0
        self.add = MagicMock()
        self.commit = AsyncMock()
        self.refresh = AsyncMock()

    async def execute(self, *args, **kwargs):
        self.consultas += 1
        resultado = MagicMock()
        # Nenhum usuário com este e-mail: a criação segue.
        resultado.scalar_one_or_none.return_value = None
        return resultado

    @property
    def gravou(self) -> bool:
        return self.add.called

    @property
    def usuario_gravado(self):
        """O endpoint faz DOIS `add`: a conta e o registro de auditoria. Pegar
        o `call_args` cru devolve o segundo."""
        from app.models.models import User

        gravados = [c.args[0] for c in self.add.call_args_list if isinstance(c.args[0], User)]
        assert len(gravados) == 1, f"esperava uma conta gravada, vieram {len(gravados)}"
        return gravados[0]


def _prepara(ator: MagicMock) -> _Sessao:
    from app.core.database import get_db
    from app.core.security import get_current_user

    sessao = _Sessao()

    async def _db():
        yield sessao

    async def _atual():
        return ator

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _atual
    return sessao


def _corpo(papel: str | None, **extras) -> dict:
    corpo: dict = {
        "name": "Conta Nova",
        "email": "conta.nova@teste.com",
        "password": "SenhaForte1",
        "lgpd_consent": True,
    }
    if papel is not None:
        corpo["role"] = papel
    # Cliente ativo exige telefone desde a Fase 1C; sem isto o 422 do telefone
    # chegaria antes do que estes testes medem.
    if papel in (None, "client"):
        corpo["phone"] = "(81) 99999-9999"
    corpo.update(extras)
    return corpo


async def _cria(ator: MagicMock, papel: str | None, **extras):
    sessao = _prepara(ator)
    # bcrypt custa ~250 ms por conta e nada aqui depende do hash real.
    with patch("app.routers.users.hash_password", return_value="hash-de-teste"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
            resposta = await http.post("/api/v1/users", json=_corpo(papel, **extras))
    return resposta, sessao


@pytest.fixture(autouse=True)
def _limpa():
    yield
    app.dependency_overrides.clear()


# ── O que a rota passa a recusar ──────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", ["admin", "technician"])
async def test_tecnico_nao_cria_conta_de_staff(papel):
    """O achado. Antes da correção isto voltava 201 com a conta já gravada."""
    resposta, sessao = await _cria(_ator(UserRole.technician), papel)

    assert resposta.status_code == 403, resposta.text
    assert resposta.json()["detail"] == _MENSAGEM
    assert not sessao.gravou, "a conta chegou a ser gravada"
    assert sessao.consultas == 0, "a guarda rodou depois de ir ao banco"


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", ["Admin", "ADMIN", "superuser", "staff"])
async def test_papel_que_nao_existe_nao_atravessa(papel):
    """Variações de grafia não são um caminho alternativo: o enum recusa antes,
    e o que importa é que NENHUMA delas devolve 201."""
    resposta, sessao = await _cria(_ator(UserRole.technician), papel)

    assert resposta.status_code == 422, resposta.text
    assert not sessao.gravou


@pytest.mark.asyncio
async def test_cliente_segue_barrado_pela_propria_rota():
    """Antes da guarda de papel existe a guarda de rota, e ela não mudou."""
    resposta, sessao = await _cria(_ator(UserRole.client), "admin")

    assert resposta.status_code == 403
    assert not sessao.gravou


# ── O que a rota NÃO pode ter perdido ─────────────────────────


@pytest.mark.asyncio
async def test_tecnico_continua_criando_cliente():
    """O uso real da tela. O front manda `role: "client"` explícito."""
    resposta, sessao = await _cria(_ator(UserRole.technician), "client")

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["role"] == "client"
    assert sessao.gravou


@pytest.mark.asyncio
async def test_tecnico_continua_criando_cliente_sem_mandar_o_papel():
    """E o caminho em que o papel vem do default do schema."""
    resposta, sessao = await _cria(_ator(UserRole.technician), None)

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["role"] == "client"
    assert sessao.gravou


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", ["admin", "technician", "client"])
async def test_admin_continua_criando_qualquer_papel(papel):
    resposta, sessao = await _cria(_ator(UserRole.admin), papel)

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["role"] == papel
    assert sessao.gravou
    # E grava o papel pedido, não um papel rebaixado em silêncio.
    assert sessao.usuario_gravado.role == UserRole(papel)


# ── A regra mora em UM lugar ──────────────────────────────────


_FONTE = Path(__file__).resolve().parents[1] / "app" / "routers" / "users.py"


def test_as_duas_rotas_consultam_a_mesma_guarda():
    """Criar e editar decidem papel pela MESMA função.

    A falha original não foi esquecer a regra: foi a regra existir só num dos
    dois lugares onde papel é atribuído. Se amanhã surgir um terceiro, que ele
    quebre aqui.
    """
    arvore = ast.parse(_FONTE.read_text(encoding="utf-8"))
    chamadas = {
        no.name: {
            c.func.id
            for c in ast.walk(no)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
        }
        for no in ast.walk(arvore)
        if isinstance(no, ast.AsyncFunctionDef)
    }

    for rota in ("create_user", "update_user"):
        assert (
            "_guarda_de_atribuicao_de_papel" in chamadas[rota]
        ), f"{rota} decide papel por conta própria"


def test_a_recusa_de_papel_tem_um_unico_autor():
    """A mensagem aparece uma vez só. Duas seriam duas regras se separando."""
    assert _FONTE.read_text(encoding="utf-8").count(_MENSAGEM) == 1
