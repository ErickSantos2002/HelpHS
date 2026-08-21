"""
Seeds do e2e: as contas de teste NUNCA podem nascer em produção.

`app.seeds` roda no boot de produção (start.sh). Colocar as contas do Playwright
lá — com senha em texto claro conhecida por qualquer um que leia o repositório
— criaria logins de teste no banco real. Por isso elas vivem num módulo
separado, `app.seeds_e2e`, que só o workflow de e2e chama, e que se recusa a
rodar quando o ambiente é de produção.

Os dois primeiros testes são o contrato: produção não cria; os seeds normais
não conhecem essas contas.
"""

import inspect
from unittest.mock import MagicMock, patch

import pytest
from passlib.context import CryptContext

from app.core.config import get_settings
from app.models.models import User, UserRole, UserStatus

_settings = get_settings()
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


class _Sessao:
    """Sessão que não toca em banco: responde ao lookup e guarda o que foi adicionado."""

    def __init__(self, existente=None):
        self.adicionados: list = []
        self._existente = existente

    async def execute(self, stmt):
        r = MagicMock()
        r.scalar_one_or_none.return_value = self._existente
        return r

    def add(self, obj):
        self.adicionados.append(obj)

    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture()
def ambiente():
    """Troca o APP_ENV só durante o teste e devolve o original depois."""
    original = _settings.app_env

    def _em(valor: str):
        _settings.app_env = valor

    yield _em
    _settings.app_env = original


@pytest.mark.asyncio
async def test_em_producao_nao_cria_nada_e_nem_abre_sessao(ambiente):
    from app import seeds_e2e

    ambiente("production")
    fabrica = MagicMock()

    with patch.object(seeds_e2e, "AsyncSessionLocal", fabrica):
        with pytest.raises(RuntimeError, match="produ"):
            await seeds_e2e.run_seeds_e2e()

    fabrica.assert_not_called()


@pytest.mark.asyncio
async def test_os_seeds_de_producao_nao_conhecem_as_contas_e2e():
    """
    `app.seeds` é o que o start.sh roda. Nenhuma conta e2e pode sair dele.

    Duas provas: o código-fonte não menciona e2e, e rodando os seeds num banco
    vazio nenhum usuário adicionado tem e-mail de teste.
    """
    from app import seeds, seeds_e2e

    assert "e2e" not in inspect.getsource(seeds).lower()

    sessao = _Sessao(existente=None)
    with patch.object(seeds, "AsyncSessionLocal", lambda: sessao):
        await seeds.run_seeds()

    emails = {u.email for u in sessao.adicionados if isinstance(u, User)}
    assert seeds_e2e.E2E_CLIENT["email"] not in emails
    assert not any("e2e" in e for e in emails)


@pytest.mark.asyncio
async def test_cria_o_cliente_e2e_pronto_para_logar(ambiente):
    """
    O cliente nasce ativo, confirmado e COM onboarding feito.

    Sem `onboarding_completed`, o OnboardingGuard o jogaria em /onboarding no
    login e o spec que espera /403 quebraria no primeiro passo.
    """
    from app import seeds_e2e

    ambiente("testing")
    sessao = _Sessao(existente=None)

    with patch.object(seeds_e2e, "AsyncSessionLocal", lambda: sessao):
        await seeds_e2e.run_seeds_e2e()

    clientes = [u for u in sessao.adicionados if isinstance(u, User)]
    assert len(clientes) == 1
    c = clientes[0]
    assert c.email == seeds_e2e.E2E_CLIENT["email"]
    assert c.role == UserRole.client
    assert c.status == UserStatus.active
    assert c.email_verified is True
    assert c.onboarding_completed is True
    assert c.lgpd_consent is True
    # A senha vai com hash, nunca em claro — mesmo sendo de teste
    assert c.password != seeds_e2e.E2E_CLIENT["password"]
    assert _pwd.verify(seeds_e2e.E2E_CLIENT["password"], c.password)


@pytest.mark.asyncio
async def test_rodar_duas_vezes_nao_duplica(ambiente):
    from app import seeds_e2e

    ambiente("testing")
    sessao = _Sessao(existente=MagicMock())  # já existe

    with patch.object(seeds_e2e, "AsyncSessionLocal", lambda: sessao):
        await seeds_e2e.run_seeds_e2e()

    assert sessao.adicionados == []


def test_as_credenciais_batem_com_o_helpers_do_playwright():
    """
    O helpers.ts tem os mesmos valores como default. Se um lado mudar e o
    outro não, o e2e falha no login sem dizer por quê — este teste diz.
    """
    from pathlib import Path

    from app import seeds_e2e

    helpers = (Path(__file__).resolve().parents[2] / "frontend" / "e2e" / "helpers.ts").read_text(
        encoding="utf-8"
    )

    assert seeds_e2e.E2E_CLIENT["email"] in helpers
    assert seeds_e2e.E2E_CLIENT["password"] in helpers
