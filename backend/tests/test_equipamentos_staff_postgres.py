"""
Listagem de equipamentos da equipe (`GET /equipments`) contra PostgreSQL.

Por que contra banco de verdade
-------------------------------
Os testes de `test_products.py` mockam a sessão e conferem o SQL compilado.
Aqui o que precisa de prova é o RESULTADO: que a busca pelo responsável
atravessa o join, que o filtro de empresa só casa vínculo oficial
(`users.company_id`) e nunca o nome que o cliente digitou, que a paginação não
repete nem perde linha. Isso só um banco responde.

A API é chamada por HTTP, com `get_db` apontando para a sessão do teste — a
autorização (`authorize`) é parte do que se testa, não um detalhe.
"""

import asyncio
import shutil
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.main import app
from app.models.models import (
    Base,
    Company,
    Equipment,
    Group,
    Product,
    User,
    UserRole,
    UserStatus,
)
from tests.test_dashboard_postgres import _sobe_postgres

_AGORA = datetime.now(UTC)


class _FakeRedis:
    async def get(self, k):
        return None

    async def exists(self, k):
        return 0


async def _get_redis():
    return _FakeRedis()


@pytest.fixture(scope="module")
def url_do_banco():
    url, recurso = _sobe_postgres()
    if url is None:
        pytest.skip("sem PostgreSQL: defina TEST_POSTGRES_URL ou instale pgserver")

    async def _monta() -> None:
        motor = create_async_engine(url)
        async with motor.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        await motor.dispose()

    asyncio.run(_monta())
    yield url

    if recurso is not None:
        servidor, pasta = recurso
        try:
            servidor.cleanup()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(pasta, ignore_errors=True)


@pytest_asyncio.fixture
async def db(url_do_banco):
    """Sessão numa transação revertida no fim — isolamento por teste."""
    motor = create_async_engine(url_do_banco)
    async with motor.connect() as conn:
        transacao = await conn.begin()
        async with async_sessionmaker(bind=conn, expire_on_commit=False)() as sessao:
            yield sessao
        await transacao.rollback()
    await motor.dispose()


@pytest.fixture(autouse=True)
def _limpa_overrides():
    with patch("app.core.security.get_redis", new=_get_redis):
        yield
    app.dependency_overrides.clear()


# ── Dados sintéticos ──────────────────────────────────────────


def _usuario(
    papel: UserRole,
    nome: str,
    *,
    email: str | None = None,
    empresa: Company | None = None,
    empresa_declarada: str | None = None,
    cnpj_declarado: str | None = None,
) -> User:
    return User(
        id=uuid.uuid4(),
        name=nome,
        email=email or f"{uuid.uuid4().hex[:8]}@test.com",
        password="x",
        role=papel,
        status=UserStatus.active,
        phone="+5581999999999",
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
        company_id=empresa.id if empresa else None,
        company_name=empresa_declarada,
        cnpj=cnpj_declarado,
        created_at=_AGORA,
        updated_at=_AGORA,
    )


def _aparelho(
    produto: Product,
    nome: str,
    *,
    responsavel: User | None = None,
    serie: str | None = None,
    modelo: str | None = None,
    ativo: bool = True,
) -> Equipment:
    return Equipment(
        id=uuid.uuid4(),
        product_id=produto.id,
        owner_id=responsavel.id if responsavel else None,
        name=nome,
        serial_number=serie,
        model=modelo,
        is_active=ativo,
        created_at=_AGORA,
        updated_at=_AGORA,
    )


class _Parque:
    """Dois clientes de empresas diferentes, um órfão e um sem vínculo."""

    def __init__(self) -> None:
        self.grupo = Group(id=uuid.uuid4(), name="Grupo Norte")
        self.alfa = Company(id=uuid.uuid4(), group_id=self.grupo.id, name="Alfa Transportes")
        self.beta = Company(id=uuid.uuid4(), group_id=self.grupo.id, name="Beta Logística")
        self.titan = Product(id=uuid.uuid4(), name="Titan")
        self.phoebus = Product(id=uuid.uuid4(), name="Phoebus")

        # Vinculada à Alfa, mas digitou outro nome no cadastro: os dois
        # aparecem, cada um no seu campo.
        self.maria = _usuario(
            UserRole.client,
            "Maria Souza",
            email="maria@alfa.com.br",
            empresa=self.alfa,
            empresa_declarada="Alfa Transp. LTDA",
            cnpj_declarado="11222333000181",
        )
        self.joao = _usuario(UserRole.client, "João Lima", empresa=self.beta)
        # Sem vínculo oficial. DIGITOU o nome da Alfa — e isso não pode fazer
        # dele cliente da Alfa para filtro nenhum.
        self.pedro = _usuario(UserRole.client, "Pedro Alves", empresa_declarada="Alfa Transportes")
        self.tecnico = _usuario(UserRole.technician, "Téc. Ana")
        self.admin = _usuario(UserRole.admin, "Adm. Bruno")

        self.da_maria = _aparelho(
            self.titan, "Titan da recepção", responsavel=self.maria, serie="SN-MAR-1", modelo="TN-X"
        )
        self.do_joao = _aparelho(
            self.phoebus, "Phoebus do pátio", responsavel=self.joao, serie="PH-JOA-9"
        )
        self.do_pedro = _aparelho(self.titan, "Titan do Pedro", responsavel=self.pedro)
        self.orfao = _aparelho(self.titan, "Titan sem dono", serie="SN-ORF-3", ativo=False)

    async def grava(self, db) -> "_Parque":
        db.add_all([self.grupo, self.titan, self.phoebus])
        await db.flush()
        db.add_all([self.alfa, self.beta])
        await db.flush()
        db.add_all([self.maria, self.joao, self.pedro, self.tecnico, self.admin])
        await db.flush()
        db.add_all([self.da_maria, self.do_joao, self.do_pedro, self.orfao])
        await db.flush()
        return self


async def _get(db, ator: User, caminho: str, **params):
    from app.core.database import get_db
    from app.core.security import get_current_user

    async def _sessao():
        yield db

    async def _ator():
        return ator

    app.dependency_overrides[get_db] = _sessao
    app.dependency_overrides[get_current_user] = _ator
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.get(f"/api/v1{caminho}", params=params)


def _nomes(resp) -> set[str]:
    return {i["name"] for i in resp.json()["items"]}


# ── Quem pode listar ──────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", ["tecnico", "admin"])
async def test_equipe_lista_equipamentos_de_clientes_diferentes(db, papel):
    parque = await _Parque().grava(db)
    ator = parque.tecnico if papel == "tecnico" else parque.admin

    resp = await _get(db, ator, "/equipments")

    assert resp.status_code == 200, resp.text
    assert _nomes(resp) == {
        "Titan da recepção",
        "Phoebus do pátio",
        "Titan do Pedro",
        "Titan sem dono",
    }
    assert resp.json()["total"] == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [{}, {"search": "Titan"}, {"company_id": "00000000-0000-0000-0000-000000000000"}],
    ids=["sem-parametro", "com-busca", "com-empresa"],
)
async def test_cliente_recebe_403_na_listagem_da_equipe(db, params):
    """A recusa é de papel e vem antes de qualquer consulta: nenhum parâmetro a contorna."""
    parque = await _Parque().grava(db)

    resp = await _get(db, parque.maria, "/equipments", **params)

    assert resp.status_code == 403
    assert "Titan" not in resp.text


# ── Paginação e ordem ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_paginas_nao_repetem_nem_perdem_equipamento(db):
    parque = await _Parque().grava(db)

    primeira = await _get(db, parque.tecnico, "/equipments", limit=2, offset=0)
    segunda = await _get(db, parque.tecnico, "/equipments", limit=2, offset=2)

    assert primeira.json()["total"] == segunda.json()["total"] == 4
    assert primeira.json()["limit"] == 2 and segunda.json()["offset"] == 2
    nomes = [i["name"] for i in primeira.json()["items"] + segunda.json()["items"]]
    assert nomes == sorted(nomes), "a ordem pelo nome é o que torna a página estável"
    assert len(set(nomes)) == 4


# ── Busca ─────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "termo, esperado",
    [
        ("recepção", {"Titan da recepção"}),  # nome do equipamento
        ("joa-9", {"Phoebus do pátio"}),  # número de série
        ("tn-x", {"Titan da recepção"}),  # modelo
        ("pedro alves", {"Titan do Pedro"}),  # nome do responsável
        ("maria@alfa", {"Titan da recepção"}),  # e-mail do responsável
    ],
    ids=["nome", "serie", "modelo", "nome-do-responsavel", "email-do-responsavel"],
)
async def test_busca(db, termo, esperado):
    parque = await _Parque().grava(db)

    resp = await _get(db, parque.tecnico, "/equipments", search=termo)

    assert resp.status_code == 200, resp.text
    assert _nomes(resp) == esperado


@pytest.mark.asyncio
async def test_busca_nao_procura_na_empresa_declarada(db):
    """O nome digitado pelo cliente não é campo de busca — não é dado do equipamento."""
    parque = await _Parque().grava(db)

    resp = await _get(db, parque.tecnico, "/equipments", search="Transp. LTDA")

    assert resp.json()["items"] == []


# ── Filtros ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_filtro_de_produto(db):
    parque = await _Parque().grava(db)

    resp = await _get(db, parque.tecnico, "/equipments", product_id=str(parque.phoebus.id))

    assert _nomes(resp) == {"Phoebus do pátio"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ativo, esperado",
    [
        ("true", {"Titan da recepção", "Phoebus do pátio", "Titan do Pedro"}),
        ("false", {"Titan sem dono"}),
    ],
)
async def test_filtro_de_ativo(db, ativo, esperado):
    parque = await _Parque().grava(db)

    resp = await _get(db, parque.tecnico, "/equipments", is_active=ativo)

    assert _nomes(resp) == esperado


@pytest.mark.asyncio
async def test_filtro_sem_responsavel(db):
    parque = await _Parque().grava(db)

    resp = await _get(db, parque.tecnico, "/equipments", without_owner="true")

    assert _nomes(resp) == {"Titan sem dono"}


@pytest.mark.asyncio
async def test_filtro_de_empresa_casa_so_o_vinculo_oficial(db):
    """O Pedro DIGITOU "Alfa Transportes", mas não tem vínculo: fica de fora."""
    parque = await _Parque().grava(db)

    resp = await _get(db, parque.tecnico, "/equipments", company_id=str(parque.alfa.id))

    assert _nomes(resp) == {"Titan da recepção"}
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_filtros_somam(db):
    parque = await _Parque().grava(db)

    resp = await _get(
        db,
        parque.tecnico,
        "/equipments",
        company_id=str(parque.alfa.id),
        product_id=str(parque.phoebus.id),
    )

    assert resp.json()["items"] == []


# ── O que cada linha carrega ──────────────────────────────────


def _item(resp, nome):
    return next(i for i in resp.json()["items"] if i["name"] == nome)


@pytest.mark.asyncio
async def test_linha_traz_produto_responsavel_e_as_duas_empresas_separadas(db):
    parque = await _Parque().grava(db)

    resp = await _get(db, parque.tecnico, "/equipments")
    linha = _item(resp, "Titan da recepção")

    assert linha["product_name"] == "Titan"
    assert linha["owner_id"] == str(parque.maria.id)
    assert linha["owner_name"] == "Maria Souza"
    assert linha["owner_email"] == "maria@alfa.com.br"
    # Oficial: vem de users.company_id -> companies.
    assert linha["linked_company_id"] == str(parque.alfa.id)
    assert linha["linked_company_name"] == "Alfa Transportes"
    # Declarada: o que ela digitou, em campo próprio, sem se misturar.
    assert linha["company_name"] == "Alfa Transp. LTDA"
    assert linha["company_cnpj"] == "11222333000181"


@pytest.mark.asyncio
async def test_empresa_declarada_nao_vira_vinculo(db):
    parque = await _Parque().grava(db)

    resp = await _get(db, parque.tecnico, "/equipments")
    linha = _item(resp, "Titan do Pedro")

    assert linha["linked_company_id"] is None
    assert linha["linked_company_name"] is None
    assert linha["company_name"] == "Alfa Transportes"


@pytest.mark.asyncio
async def test_equipamento_sem_responsavel_vem_sem_responsavel_nem_empresa(db):
    parque = await _Parque().grava(db)

    resp = await _get(db, parque.tecnico, "/equipments")
    linha = _item(resp, "Titan sem dono")

    for campo in (
        "owner_id",
        "owner_name",
        "owner_email",
        "linked_company_id",
        "linked_company_name",
        "company_name",
        "company_cnpj",
    ):
        assert linha[campo] is None, campo
    assert linha["product_name"] == "Titan"


@pytest.mark.asyncio
async def test_numero_de_consultas_nao_cresce_com_a_pagina(db):
    """Sem N+1: responsável, empresa e produto chegam em consultas fixas."""
    parque = await _Parque().grava(db)
    motor = db.bind.sync_engine if hasattr(db.bind, "sync_engine") else db.bind.engine.sync_engine
    contagem = {"n": 0}

    def _conta(*_args, **_kwargs):
        contagem["n"] += 1

    event.listen(motor, "before_cursor_execute", _conta)
    try:
        contagem["n"] = 0
        await _get(db, parque.tecnico, "/equipments", limit=1)
        uma_linha = contagem["n"]
        contagem["n"] = 0
        await _get(db, parque.tecnico, "/equipments", limit=4)
        quatro_linhas = contagem["n"]
    finally:
        event.remove(motor, "before_cursor_execute", _conta)

    assert quatro_linhas == uma_linha, (uma_linha, quatro_linhas)


# ── Consulta por id ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_detalhe_para_a_equipe_traz_responsavel_e_empresa(db):
    parque = await _Parque().grava(db)

    resp = await _get(db, parque.tecnico, f"/equipments/{parque.da_maria.id}")

    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    assert corpo["owner_name"] == "Maria Souza"
    assert corpo["linked_company_name"] == "Alfa Transportes"
    assert corpo["company_name"] == "Alfa Transp. LTDA"
    assert corpo["product_name"] == "Titan"


@pytest.mark.asyncio
async def test_detalhe_do_proprio_equipamento_nao_ganha_dado_novo_para_o_cliente(db):
    """O cliente continua recebendo o que recebia: o vínculo oficial não é dele ler."""
    parque = await _Parque().grava(db)

    resp = await _get(db, parque.maria, f"/equipments/{parque.da_maria.id}")

    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    assert corpo["linked_company_id"] is None
    assert corpo["linked_company_name"] is None
    assert str(parque.alfa.id) not in resp.text
    assert "Alfa Transportes" not in resp.text


@pytest.mark.asyncio
@pytest.mark.parametrize("de_quem", ["outra-empresa", "mesma-empresa"])
async def test_detalhe_alheio_continua_404_para_o_cliente(db, de_quem):
    """Estar na mesma empresa não abre o equipamento de outra pessoa."""
    parque = await _Parque().grava(db)
    if de_quem == "mesma-empresa":
        colega = _usuario(UserRole.client, "Colega da Maria", empresa=parque.alfa)
        db.add(colega)
        await db.flush()
        ator = colega
    else:
        ator = parque.joao

    resp = await _get(db, ator, f"/equipments/{parque.da_maria.id}")

    assert resp.status_code == 404
    assert "Titan" not in resp.text


@pytest.mark.asyncio
async def test_listagem_por_produto_nao_entrega_o_vinculo_oficial_ao_cliente(db):
    parque = await _Parque().grava(db)

    resp = await _get(db, parque.maria, f"/products/{parque.titan.id}/equipments")

    assert resp.status_code == 200, resp.text
    assert _nomes(resp) == {"Titan da recepção"}
    assert str(parque.alfa.id) not in resp.text
    linha = resp.json()["items"][0]
    assert linha["linked_company_id"] is None and linha["linked_company_name"] is None


@pytest.mark.asyncio
async def test_listagem_por_produto_entrega_o_vinculo_oficial_a_equipe(db):
    """A tela de Produtos usa o mesmo modal de detalhe — e ganha o mesmo dado."""
    parque = await _Parque().grava(db)

    resp = await _get(db, parque.admin, f"/products/{parque.titan.id}/equipments")

    linha = _item(resp, "Titan da recepção")
    assert linha["linked_company_name"] == "Alfa Transportes"
    assert linha["company_name"] == "Alfa Transp. LTDA"
