"""
Seeds de produção: a conta de admin não pode nascer com senha do repositório.

`start.sh` roda `python -m app.seeds` **a cada boot do container**, inclusive em
produção, entre a migration e o uvicorn. Enquanto `seed_admin` teve a senha
`Admin@123456` escrita no código e nenhuma guarda de ambiente, todo deploy
criava — ou recriava, se alguém apagasse a linha — um administrador ativo com
credencial publicada neste repositório.

O `app.seeds_e2e` já tinha essa proteção e a docstring dele já dizia o porquê;
o raciocínio tinha sido aplicado à conta de teste e não à de admin, que é a
mais poderosa das duas.

São duas defesas independentes, e os testes cobrem as duas separadamente:

1. `APP_ENV` de produção não cria admin.
2. Sem `SEED_ADMIN_PASSWORD` não cria admin — nunca há literal para cair.

A segunda existe porque a primeira falha aberta: `app_env` tem default
`"development"`, então variável ausente ou digitada errada desligaria a guarda
de ambiente sozinha.

**Nenhum dos dois caminhos derruba o boot.** `start.sh` roda com `set -e`:
`seed_admin` levantando exceção deixaria o container sem subir. Produtos e
configurações de SLA continuam sendo semeados normalmente em produção — quem
não pode nascer lá é o usuário.
"""

import inspect
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import get_settings
from app.models.models import Product, SLAConfig, User

_settings = get_settings()

SENHA_DE_TESTE = "SenhaDeTeste@123"


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
    """Troca APP_ENV e SEED_ADMIN_PASSWORD só durante o teste."""
    env_original = _settings.app_env
    senha_original = _settings.seed_admin_password

    def _configura(app_env: str, senha: str | None = SENHA_DE_TESTE):
        _settings.app_env = app_env
        _settings.seed_admin_password = senha

    yield _configura
    _settings.app_env = env_original
    _settings.seed_admin_password = senha_original


async def _roda_seeds() -> _Sessao:
    from app import seeds

    sessao = _Sessao(existente=None)
    with patch.object(seeds, "AsyncSessionLocal", lambda: sessao):
        await seeds.run_seeds()
    return sessao


def _usuarios(sessao: _Sessao) -> list[User]:
    return [o for o in sessao.adicionados if isinstance(o, User)]


# ═══════════════════════════════════════════════════════════════
# Defesa 1 — ambiente
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_em_producao_nao_cria_admin(ambiente):
    """Mesmo com a senha configurada, produção não ganha conta de seed."""
    ambiente("production", SENHA_DE_TESTE)

    sessao = await _roda_seeds()

    assert _usuarios(sessao) == []


@pytest.mark.asyncio
async def test_em_producao_produtos_e_sla_continuam_sendo_semeados(ambiente):
    """
    A guarda é sobre o **usuário**, não sobre os seeds. Produto e SLA são
    catálogo, não credencial, e o boot de produção depende deles.
    """
    ambiente("production", SENHA_DE_TESTE)

    sessao = await _roda_seeds()

    assert [o for o in sessao.adicionados if isinstance(o, Product)]
    assert [o for o in sessao.adicionados if isinstance(o, SLAConfig)]


@pytest.mark.asyncio
async def test_em_producao_nao_levanta_e_nao_derruba_o_boot(ambiente):
    """
    **Isto é o contrário do `seeds_e2e`, e de propósito.**

    Lá o `RuntimeError` é seguro: nada chama aquele módulo em produção. Aqui
    `run_seeds` está no caminho do boot (`start.sh`, com `set -e`), então
    levantar deixaria o container sem subir — trocar um vazamento de
    credencial por uma indisponibilidade. A recusa é registrada em log e a
    execução segue.
    """
    ambiente("production", SENHA_DE_TESTE)

    await _roda_seeds()  # não levanta


# ═══════════════════════════════════════════════════════════════
# Defesa 2 — senha vem do ambiente, nunca de literal
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sem_a_variavel_nao_cria_admin_e_nao_explode(ambiente):
    """
    A defesa que segura sozinha quando `APP_ENV` está errado ou ausente —
    e `app_env` tem default `"development"`, então isso é plausível.
    """
    ambiente("development", None)

    sessao = await _roda_seeds()

    assert _usuarios(sessao) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("vazia", ["", "   "])
async def test_variavel_vazia_conta_como_ausente(ambiente, vazia):
    """Variável declarada e vazia no painel não pode virar senha em branco."""
    ambiente("development", vazia)

    sessao = await _roda_seeds()

    assert _usuarios(sessao) == []


@pytest.mark.asyncio
async def test_com_a_variavel_em_desenvolvimento_cria_o_admin(ambiente):
    ambiente("development", SENHA_DE_TESTE)

    sessao = await _roda_seeds()

    criados = _usuarios(sessao)
    assert len(criados) == 1
    assert criados[0].email == "admin@healthsafety.com"


@pytest.mark.asyncio
async def test_a_senha_gravada_e_a_da_variavel(ambiente):
    """
    Prova que a senha **usada** vem do ambiente, não que a variável apenas
    destranca um literal escondido.
    """
    from passlib.context import CryptContext

    ambiente("development", SENHA_DE_TESTE)

    sessao = await _roda_seeds()

    hash_gravado = _usuarios(sessao)[0].password
    assert CryptContext(schemes=["bcrypt"], deprecated="auto").verify(SENHA_DE_TESTE, hash_gravado)


@pytest.mark.asyncio
async def test_admin_que_ja_existe_nao_e_recriado(ambiente):
    """
    A idempotência que protege quem já trocou a senha em produção: com a linha
    presente, o seed não a toca.
    """
    ambiente("development", SENHA_DE_TESTE)
    from app import seeds

    sessao = _Sessao(existente=MagicMock())
    with patch.object(seeds, "AsyncSessionLocal", lambda: sessao):
        await seeds.run_seeds()

    assert _usuarios(sessao) == []


# ═══════════════════════════════════════════════════════════════
# A regressão que fecha o achado
# ═══════════════════════════════════════════════════════════════


def test_o_codigo_dos_seeds_nao_carrega_senha_nenhuma():
    """
    O objetivo real: **nenhuma** senha em texto claro no módulo que roda no
    boot de produção. Guarda de ambiente é defesa; senha ausente é a correção.
    """
    from app import seeds

    fonte = inspect.getsource(seeds)
    assert "Admin@123456" not in fonte
    assert "password" not in seeds.ADMIN_USER


def test_o_workflow_de_e2e_sorteia_a_senha_do_admin_e_nao_a_escreve():
    """
    Sem `SEED_ADMIN_PASSWORD`, o `app.seeds` não cria admin — e o Playwright
    faz login com ele. O workflow tem de entregar a MESMA senha aos dois lados.

    Até 24/11/2026 ela estava escrita no bloco `env:` dos dois jobs, e o runner
    imprime esse bloco no log de cada passo. Agora nasce em tempo de execução:

    - nenhuma chave `SEED_ADMIN_PASSWORD:`/`ADMIN_PASSWORD:` com valor no YAML;
    - o default do `helpers.ts` não aparece no workflow;
    - cada job sorteia, mascara (`add-mask`) ANTES de gravar no ambiente, e
      grava as duas variáveis com o mesmo valor;
    - o passo vem antes do seed que consome a senha;
    - o `helpers.ts` continua lendo `ADMIN_PASSWORD` do ambiente.
    """
    import re
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    workflow = (raiz / ".github" / "workflows" / "e2e.yml").read_text(encoding="utf-8")
    helpers = (raiz / "frontend" / "e2e" / "helpers.ts").read_text(encoding="utf-8")

    assert not re.search(r"^\s*(SEED_)?ADMIN_PASSWORD\s*:", workflow, flags=re.M)

    padrao = re.search(r'process\.env\.ADMIN_PASSWORD \?\? "([^"]+)"', helpers)
    assert padrao, "o helpers.ts precisa ler ADMIN_PASSWORD do ambiente"
    assert padrao.group(1) not in workflow

    linhas = [x.strip() for x in workflow.splitlines()]
    sorteios = [i for i, x in enumerate(linhas) if x.startswith('senha="E2e-$(openssl rand')]
    mascaras = [i for i, x in enumerate(linhas) if x == 'echo "::add-mask::${senha}"']
    do_seed = [i for i, x in enumerate(linhas) if x == 'echo "SEED_ADMIN_PASSWORD=${senha}"']
    do_playwright = [i for i, x in enumerate(linhas) if x == 'echo "ADMIN_PASSWORD=${senha}"']
    seeds = [i for i, x in enumerate(linhas) if x == "run: python -m app.seeds"]

    # Um por job (`e2e` e `ece01`), e nessa ordem dentro de cada um.
    assert len(do_seed) == len(do_playwright) == len(seeds) == 2
    for seed_env, playwright_env, seed in zip(do_seed, do_playwright, seeds, strict=True):
        sorteio = max(i for i in sorteios if i < seed_env)
        mascara = max(i for i in mascaras if i < seed_env)
        assert sorteio < mascara < seed_env < playwright_env < seed
        # Entre a máscara e o seed, nada imprime: só as duas gravações.
        assert playwright_env - mascara <= 3

    # Nenhum `echo` solto do valor, nem `set -x`, em lugar nenhum.
    assert not re.search(r"echo\s+\"?\$\{?senha\}?\"?\s*$", workflow, flags=re.M)
    assert "set -x" not in workflow
