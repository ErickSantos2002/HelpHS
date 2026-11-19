"""
Seed do cenário da ECE-01 para o e2e (`python -m app.seeds_e2e --ece01`).

O que este arquivo prende:

- sem a opção, o seed do e2e continua criando só o cliente de sempre — os specs
  das outras frentes não passam a depender de dado que não pediram;
- com a opção, nasce o cenário que os specs `ece01-*.spec.ts` leem, e só ele;
- em produção nada disso roda;
- os nomes e as credenciais batem com `frontend/e2e/ece01.ts`.

Sem banco: a sessão é de mentira, como em `test_seeds_e2e.py`. Que o cenário
grava de verdade num Postgres (FKs, CHECK da empresa do equipamento) quem prova
é o próprio workflow de e2e, que roda este seed antes dos specs.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from passlib.context import CryptContext

from app import seeds_e2e
from app.core.config import get_settings
from app.models.models import Company, Equipment, Group, Product, User, UserRole, UserStatus

_settings = get_settings()
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
async def test_os_dois_clientes_sao_colegas_e_entram_prontos_para_logar(ambiente):
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
        assert c.password != dados["password"]
        assert _pwd.verify(dados["password"], c.password)


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


def test_os_nomes_e_as_credenciais_batem_com_o_playwright():
    """`frontend/e2e/ece01.ts` repete estes valores. Se um lado mudar e o outro
    não, o spec falha no login ou não acha o aparelho — este teste diz por quê."""
    do_front = (Path(__file__).resolve().parents[2] / "frontend" / "e2e" / "ece01.ts").read_text(
        encoding="utf-8"
    )

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
            for campo in ("email", "password", "name")
        ),
    ):
        assert f'"{valor}"' in do_front, valor
