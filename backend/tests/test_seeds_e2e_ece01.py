"""
Seed do cenário da ECE-01 para o e2e (`python -m app.seeds_e2e --ece01`).

O que este arquivo prende:

- sem a opção, o seed do e2e continua criando só o cliente de sempre — os specs
  das outras frentes não passam a depender de dado que não pediram;
- com a opção, nasce o cenário que os specs `ece01-*.spec.ts` leem, e só ele;
- em produção nada disso roda;
- os nomes e os e-mails batem com `frontend/e2e/ece01.ts`;
- nenhuma senha desses clientes mora no repositório: o seed e o Playwright
  leem as mesmas duas variáveis de ambiente, e sem elas o seed não grava nada.

Sem banco: a sessão é de mentira, como em `test_seeds_e2e.py`. Que o cenário
grava de verdade num Postgres (FKs, CHECK da empresa do equipamento) quem prova
é o próprio workflow de e2e, que roda este seed antes dos specs.
"""

import inspect
import re
import secrets
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from passlib.context import CryptContext

from app import seeds_e2e
from app.core.config import get_settings
from app.models.models import Company, Equipment, Group, Product, User, UserRole, UserStatus

_settings = get_settings()
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

_CONTAS = (seeds_e2e.E2E_ECE01_ANA, seeds_e2e.E2E_ECE01_BRUNO)
_FRONT = Path(__file__).resolve().parents[2] / "frontend" / "e2e" / "ece01.ts"


@pytest.fixture(autouse=True)
def senhas(monkeypatch):
    """Um par sorteado por teste, como o workflow sorteia por execução —
    nem aqui há senha escrita."""
    sorteadas = {dados["senha_env"]: secrets.token_urlsafe(18) for dados in _CONTAS}
    for variavel, valor in sorteadas.items():
        monkeypatch.setenv(variavel, valor)
    return sorteadas


class _Sessao:
    """Não toca em banco: responde ao lookup e guarda o que foi adicionado."""

    def __init__(self, existente=None):
        self.adicionados: list = []
        self.flushes = 0
        self._existente = existente

    async def execute(self, stmt):
        r = MagicMock()
        r.scalar_one_or_none.return_value = self._existente
        return r

    def add(self, obj):
        self.adicionados.append(obj)

    async def flush(self):
        self.flushes += 1

    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def dos(self, tipo):
        return [o for o in self.adicionados if isinstance(o, tipo)]


@pytest.fixture()
def ambiente():
    original = _settings.app_env

    def _em(valor: str):
        _settings.app_env = valor

    yield _em
    _settings.app_env = original


async def _roda(sessao, **opcoes):
    with patch.object(seeds_e2e, "AsyncSessionLocal", lambda: sessao):
        await seeds_e2e.run_seeds_e2e(**opcoes)


@pytest.mark.asyncio
async def test_sem_a_opcao_o_seed_do_e2e_continua_criando_so_o_cliente(ambiente):
    ambiente("testing")
    sessao = _Sessao()

    await _roda(sessao)

    assert [u.email for u in sessao.dos(User)] == [seeds_e2e.E2E_CLIENT["email"]]
    assert len(sessao.adicionados) == 1


@pytest.mark.asyncio
async def test_em_producao_o_cenario_nao_nasce_e_a_sessao_nem_abre(ambiente):
    ambiente("production")
    fabrica = MagicMock()

    with patch.object(seeds_e2e, "AsyncSessionLocal", fabrica):
        with pytest.raises(RuntimeError, match="produ"):
            await seeds_e2e.run_seeds_e2e(ece01=True)

    fabrica.assert_not_called()


@pytest.mark.asyncio
async def test_com_a_opcao_nasce_o_cenario_inteiro(ambiente):
    ambiente("testing")
    sessao = _Sessao()

    await _roda(sessao, ece01=True)

    (grupo,) = sessao.dos(Group)
    empresas = {c.name: c for c in sessao.dos(Company)}
    assert set(empresas) == {seeds_e2e.E2E_ECE01_EMPRESA_ALFA, seeds_e2e.E2E_ECE01_EMPRESA_BETA}
    assert {c.group_id for c in empresas.values()} == {grupo.id}
    (produto,) = sessao.dos(Product)
    assert produto.name == seeds_e2e.E2E_ECE01_PRODUTO
    assert produto.is_active is True
    assert len(sessao.dos(Equipment)) == 4
    assert {e.product_id for e in sessao.dos(Equipment)} == {produto.id}


@pytest.mark.asyncio
async def test_os_dois_clientes_sao_colegas_e_entram_prontos_para_logar(ambiente, senhas):
    ambiente("testing")
    sessao = _Sessao()

    await _roda(sessao, ece01=True)

    alfa = next(c for c in sessao.dos(Company) if c.name == seeds_e2e.E2E_ECE01_EMPRESA_ALFA)
    clientes = {u.email: u for u in sessao.dos(User)}
    for dados in (seeds_e2e.E2E_ECE01_ANA, seeds_e2e.E2E_ECE01_BRUNO):
        c = clientes[dados["email"]]
        # O vínculo oficial com a MESMA empresa é o que os faz colegas.
        assert c.company_id == alfa.id
        assert c.role == UserRole.client
        assert c.status == UserStatus.active
        assert c.email_verified is True
        assert c.onboarding_completed is True
        assert c.lgpd_consent is True
        assert c.phone
        # A senha é a do ambiente, e vai com hash — nunca em claro.
        assert c.password != senhas[dados["senha_env"]]
        assert _pwd.verify(senhas[dados["senha_env"]], c.password)
    # Cada um com a sua: a senha de um não abre a conta do outro.
    ana, bruno = (clientes[d["email"]] for d in _CONTAS)
    assert not _pwd.verify(senhas[seeds_e2e.E2E_ECE01_ANA["senha_env"]], bruno.password)
    assert not _pwd.verify(senhas[seeds_e2e.E2E_ECE01_BRUNO["senha_env"]], ana.password)


@pytest.mark.asyncio
@pytest.mark.parametrize("falta", [d["senha_env"] for d in _CONTAS])
@pytest.mark.parametrize("como", ["ausente", "vazia"])
async def test_sem_a_senha_no_ambiente_o_cenario_nao_grava_nada(
    ambiente, senhas, monkeypatch, falta, como
):
    """Sem valor de reserva: faltou uma das duas, o seed para antes de
    consultar o banco, diz QUAL variável falta e não repete senha nenhuma."""
    ambiente("testing")
    if como == "ausente":
        monkeypatch.delenv(falta)
    else:
        monkeypatch.setenv(falta, "")
    sessao = _Sessao()
    consultas = []
    execute = sessao.execute

    async def conta_consulta(stmt):
        consultas.append(str(stmt))
        return await execute(stmt)

    sessao.execute = conta_consulta

    with pytest.raises(RuntimeError) as erro:
        await _roda(sessao, ece01=True)

    assert falta in str(erro.value)
    assert not any(valor in str(erro.value) for valor in senhas.values())
    # Só o cliente de sempre, que vem antes: do cenário, nada.
    assert sessao.dos(Group) + sessao.dos(Company) + sessao.dos(Equipment) == []
    assert [u.email for u in sessao.dos(User)] == [seeds_e2e.E2E_CLIENT["email"]]
    assert not any("groups" in c for c in consultas)


@pytest.mark.asyncio
async def test_sem_a_opcao_o_seed_nao_pede_senha_nenhuma(ambiente, monkeypatch):
    """A suíte geral não define as variáveis, e tem de seguir rodando."""
    ambiente("testing")
    for dados in _CONTAS:
        monkeypatch.delenv(dados["senha_env"])
    sessao = _Sessao()

    await _roda(sessao)

    assert len(sessao.adicionados) == 1


def test_nenhuma_senha_dos_clientes_da_ece01_esta_escrita_no_repositorio():
    """O que o GitGuardian acusou no PR #117. Uma senha fixa, mesmo fictícia,
    é um literal que alguém copia — e que o verificador não distingue de uma
    de verdade."""
    for dados in _CONTAS:
        assert set(dados) == {"email", "senha_env", "name", "phone"}
        assert re.fullmatch(r"E2E_ECE01_[A-Z]+_PASSWORD", dados["senha_env"])

    # No seed: do cenário da ECE-01 em diante, nenhuma chave de senha com valor.
    do_cenario = inspect.getsource(seeds_e2e).split("# ── Cenário da ECE-01", 1)[1]
    assert not re.search(r"""["']password["']\s*:""", do_cenario)

    # No Playwright: a conta carrega o NOME da variável, nunca um valor.
    do_front = _FRONT.read_text(encoding="utf-8")
    assert not re.search(r"""\b(password|senha)\s*:\s*["'`]""", do_front)
    assert "process.env[conta.senhaEnv]" in do_front


@pytest.mark.asyncio
async def test_cada_aparelho_nasce_na_situacao_que_o_spec_espera(ambiente):
    ambiente("testing")
    sessao = _Sessao()

    await _roda(sessao, ece01=True)

    empresas = {c.name: c.id for c in sessao.dos(Company)}
    alfa = empresas[seeds_e2e.E2E_ECE01_EMPRESA_ALFA]
    beta = empresas[seeds_e2e.E2E_ECE01_EMPRESA_BETA]
    donos = {u.email: u.id for u in sessao.dos(User)}
    ana = donos[seeds_e2e.E2E_ECE01_ANA["email"]]
    bruno = donos[seeds_e2e.E2E_ECE01_BRUNO["email"]]
    aparelhos = {e.name: (e.owner_id, e.company_id) for e in sessao.dos(Equipment)}

    assert aparelhos == {
        seeds_e2e.E2E_ECE01_APARELHO_DA_ANA: (ana, alfa),
        seeds_e2e.E2E_ECE01_APARELHO_DO_BRUNO: (bruno, alfa),
        # Da Ana, mas em OUTRA empresa: é a divergência que a equipe vê, e o
        # aparelho que o Bruno não pode enxergar nem com a flag ligada.
        seeds_e2e.E2E_ECE01_APARELHO_DIVERGENTE: (ana, beta),
        seeds_e2e.E2E_ECE01_APARELHO_A_CLASSIFICAR: (None, None),
    }
    assert all(e.is_active for e in sessao.dos(Equipment))
    # Sem empresa aqui é "falta classificar", não decisão de ninguém.
    assert not any(e.sem_empresa_por_decisao for e in sessao.dos(Equipment))


@pytest.mark.asyncio
async def test_quem_vem_antes_na_hierarquia_e_gravado_antes(ambiente):
    """Os ids nascem no seed, sem relacionamento que ordene o INSERT: é o
    `flush` por degrau que faz a FK achar a linha de quem veio antes."""
    ambiente("testing")
    sessao = _Sessao()

    await _roda(sessao, ece01=True)

    ordem = [type(o) for o in sessao.adicionados if not isinstance(o, User | Product)]
    assert ordem == [Group, Company, Company, Equipment, Equipment, Equipment, Equipment]
    posicao = {id(o): i for i, o in enumerate(sessao.adicionados)}
    primeiro_aparelho = min(posicao[id(e)] for e in sessao.dos(Equipment))
    assert all(posicao[id(o)] < primeiro_aparelho for o in sessao.dos(User) + sessao.dos(Product))
    assert sessao.flushes == 4


@pytest.mark.asyncio
async def test_rodar_duas_vezes_nao_duplica_o_cenario(ambiente):
    ambiente("testing")
    sessao = _Sessao(existente=MagicMock())  # o grupo (e o cliente) já existem

    await _roda(sessao, ece01=True)

    assert sessao.adicionados == []


def test_o_cenario_nao_decide_o_modo_do_compartilhamento():
    """O dado é o mesmo com a flag ligada ou desligada; quem escolhe o modo é o
    ambiente de cada execução do workflow, nunca o seed."""
    import inspect

    fonte = inspect.getsource(seeds_e2e.seed_e2e_ece01)
    assert "equipamento_por_empresa" not in fonte.replace("EQUIPAMENTO_POR_EMPRESA", "")
    assert "get_settings" not in fonte


def test_os_nomes_e_as_variaveis_de_senha_batem_com_o_playwright():
    """`frontend/e2e/ece01.ts` repete estes valores — e lê as senhas das MESMAS
    variáveis. Se um lado mudar e o outro não, o spec falha no login ou não
    acha o aparelho — este teste diz por quê."""
    do_front = _FRONT.read_text(encoding="utf-8")

    for valor in (
        seeds_e2e.E2E_ECE01_PRODUTO,
        seeds_e2e.E2E_ECE01_EMPRESA_ALFA,
        seeds_e2e.E2E_ECE01_EMPRESA_BETA,
        seeds_e2e.E2E_ECE01_APARELHO_DA_ANA,
        seeds_e2e.E2E_ECE01_APARELHO_DO_BRUNO,
        seeds_e2e.E2E_ECE01_APARELHO_DIVERGENTE,
        seeds_e2e.E2E_ECE01_APARELHO_A_CLASSIFICAR,
        *(
            dados[campo]
            for dados in (seeds_e2e.E2E_ECE01_ANA, seeds_e2e.E2E_ECE01_BRUNO)
            for campo in ("email", "senha_env", "name")
        ),
    ):
        assert f'"{valor}"' in do_front, valor
