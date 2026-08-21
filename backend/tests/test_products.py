"""
Tests for Product and Equipment CRUD endpoints.
DB and Redis fully mocked.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import UserRole, UserStatus

# ── Fake Redis ────────────────────────────────────────────────


class _FakeRedis:
    def __init__(self):
        self._store: dict = {}

    async def setex(self, k, t, v):
        self._store[k] = v

    async def get(self, k):
        return self._store.get(k)

    async def delete(self, k):
        self._store.pop(k, None)

    async def exists(self, k):
        return 1 if k in self._store else 0


_redis = _FakeRedis()


async def _get_redis():
    return _redis


# ── Mock builders ─────────────────────────────────────────────

_NOW = datetime.now(UTC)
_PRODUCT_ID = uuid.uuid4()
_EQUIP_ID = uuid.uuid4()


def _mock_user(role=UserRole.admin):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = f"{role.value}@test.com"
    u.role = role
    u.status = UserStatus.active
    return u


def _mock_product(name="Titan", is_active=True):
    p = MagicMock()
    p.id = _PRODUCT_ID
    p.name = name
    p.description = "Bafômetro Titan"
    p.version = None
    p.is_active = is_active
    p.created_at = _NOW
    p.updated_at = _NOW
    return p


def _mock_equipment(serial=None):
    e = MagicMock()
    e.id = _EQUIP_ID
    e.product_id = _PRODUCT_ID
    e.name = "Titan #001"
    e.serial_number = serial or "SN-001"
    e.model = "TN-X"
    e.description = None
    e.location = None
    e.owner_id = None
    e.is_active = True
    e.created_at = _NOW
    e.updated_at = _NOW
    # Dados do dono, preenchidos só na listagem de admin
    e.owner_name = None
    e.owner_email = None
    e.company_name = None
    e.company_cnpj = None
    return e


_ADMIN = _mock_user(UserRole.admin)
_CLIENT = _mock_user(UserRole.client)


# ── DB session factory ────────────────────────────────────────


def _db(lookup=None, count=0):
    """Single-value mock: scalar_one_or_none returns `lookup`, scalar_one returns `count`."""

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = lookup
        result.scalar_one.return_value = count
        result.scalars.return_value.all.return_value = [lookup] if lookup else []
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _db_override(lookup=None, count=0):
    session = _db(lookup, count)

    async def _gen():
        yield session

    return _gen


# ── Fixture helpers ───────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def patch_redis():
    with patch("app.core.security.get_redis", new=_get_redis):
        yield


def _override_user(user):
    from app.core.security import get_current_user

    async def _u():
        return user

    app.dependency_overrides[get_current_user] = _u


# ═══════════════════════════════════════════════════════════════
# PRODUCT TESTS
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_product_as_admin(patch_redis):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_override(None)  # name not found
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/products", json={"name": "Titan"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "Titan"


@pytest.mark.asyncio
async def test_create_product_as_client_forbidden(patch_redis):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_override(None)
    _override_user(_CLIENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/products", json={"name": "Titan"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_product_duplicate_name(patch_redis):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_override(_mock_product())  # name exists
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/products", json={"name": "Titan"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_products(patch_redis):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_override(_mock_product(), count=1)
    _override_user(_CLIENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/products")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] == 1


@pytest.mark.asyncio
async def test_get_product(patch_redis):
    from app.core.database import get_db

    product = _mock_product()
    app.dependency_overrides[get_db] = _db_override(product)
    _override_user(_CLIENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/products/{_PRODUCT_ID}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Titan"


@pytest.mark.asyncio
async def test_get_product_not_found(patch_redis):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_override(None)
    _override_user(_CLIENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/products/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_product_as_admin(patch_redis):
    from app.core.database import get_db

    product = _mock_product()
    app.dependency_overrides[get_db] = _db_override(product)
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/products/{_PRODUCT_ID}", json={"version": "2.0"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_product_soft(patch_redis):
    from app.core.database import get_db

    product = _mock_product()
    app.dependency_overrides[get_db] = _db_override(product)
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/products/{_PRODUCT_ID}")
    assert resp.status_code == 204


# ═══════════════════════════════════════════════════════════════
# EQUIPMENT TESTS
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_equipment_as_admin(patch_redis):
    from app.core.database import get_db

    product = _mock_product()

    # execute calls: 1) product lookup, 2) serial number check
    call_seq = [product, None]
    idx = 0

    async def _execute(*args, **kwargs):
        nonlocal idx
        val = call_seq[idx] if idx < len(call_seq) else None
        idx += 1
        result = MagicMock()
        result.scalar_one_or_none.return_value = val
        result.scalar_one.return_value = 0
        result.scalars.return_value.all.return_value = []
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    async def _gen():
        yield session

    app.dependency_overrides[get_db] = _gen
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/products/{_PRODUCT_ID}/equipments",
            json={"name": "Titan #001", "serial_number": "SN-001"},
        )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Titan #001"


@pytest.mark.asyncio
async def test_create_equipment_duplicate_serial(patch_redis):
    from app.core.database import get_db

    product = _mock_product()
    existing_equip = _mock_equipment("SN-001")

    call_seq = [product, existing_equip]
    idx = 0

    async def _execute(*args, **kwargs):
        nonlocal idx
        val = call_seq[idx] if idx < len(call_seq) else None
        idx += 1
        result = MagicMock()
        result.scalar_one_or_none.return_value = val
        result.scalar_one.return_value = 0
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def _gen():
        yield session

    app.dependency_overrides[get_db] = _gen
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/products/{_PRODUCT_ID}/equipments",
            json={"name": "Titan #002", "serial_number": "SN-001"},
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_equipments(patch_redis):
    from app.core.database import get_db

    product = _mock_product()
    equip = _mock_equipment()

    call_seq = [product, equip]
    idx = 0

    async def _execute(*args, **kwargs):
        nonlocal idx
        val = call_seq[idx] if idx < len(call_seq) else None
        idx += 1
        result = MagicMock()
        result.scalar_one_or_none.return_value = val
        result.scalar_one.return_value = 1
        result.scalars.return_value.all.return_value = [equip] if val == product else []
        return result

    session = AsyncMock()
    session.execute = _execute

    async def _gen():
        yield session

    app.dependency_overrides[get_db] = _gen
    _override_user(_CLIENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/products/{_PRODUCT_ID}/equipments")
    assert resp.status_code == 200
    assert "items" in resp.json()


@pytest.mark.asyncio
async def test_get_equipment(patch_redis):
    # Ator staff: equipamento sem dono não é mais visível ao cliente — ver os
    # testes de escopo por dono no fim do arquivo
    from app.core.database import get_db

    equip = _mock_equipment()
    app.dependency_overrides[get_db] = _db_override(equip)
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/equipments/{_EQUIP_ID}")
    assert resp.status_code == 200
    assert resp.json()["serial_number"] == "SN-001"


@pytest.mark.asyncio
async def test_delete_equipment_soft(patch_redis):
    from app.core.database import get_db

    equip = _mock_equipment()
    app.dependency_overrides[get_db] = _db_override(equip)
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/equipments/{_EQUIP_ID}")
    assert resp.status_code == 204


# ═══════════════════════════════════════════════════════════════
# ESCOPO POR DONO — o cliente só enxerga o próprio equipamento
# ═══════════════════════════════════════════════════════════════
#
# Sem esse escopo, qualquer autenticado lia equipamento (com número de série)
# de qualquer outro cliente. Staff (admin/técnico) continua vendo tudo, porque
# precisa para dar suporte.


def _db_capturando_queries(product, equipments, count=1):
    """
    Mock de sessão que registra as queries emitidas.

    O banco é mockado, então um `.where()` a mais não muda o resultado — para a
    listagem, a prova do escopo é a query emitida conter o filtro por dono.

    O resultado é o mesmo para toda chamada: cada consumidor lê só o campo que
    lhe interessa (`scalar_one_or_none` para o produto, `scalar_one` para a
    contagem, `scalars().all()` para as linhas), então não é preciso acertar a
    ordem das chamadas — e o teste não quebra se o endpoint passar a consultar
    em outra sequência.
    """
    queries: list[str] = []

    async def _execute(stmt, *args, **kwargs):
        queries.append(str(stmt))
        result = MagicMock()
        result.scalar_one_or_none.return_value = product
        result.scalar_one.return_value = count
        result.scalars.return_value.all.return_value = equipments
        return result

    session = AsyncMock()
    session.execute = _execute

    async def _gen():
        yield session

    return _gen, queries


@pytest.mark.asyncio
async def test_client_listing_is_scoped_to_own_equipment(patch_redis):
    """Cliente listando equipamentos de um produto: a query filtra pelo dono."""
    from app.core.database import get_db

    gen, queries = _db_capturando_queries(_mock_product(), [_mock_equipment()])
    app.dependency_overrides[get_db] = gen
    _override_user(_CLIENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/products/{_PRODUCT_ID}/equipments")

    assert resp.status_code == 200
    # `equipments.owner_id` sozinho apareceria na lista de colunas do SELECT;
    # o que prova o escopo é a comparação no WHERE
    assert any("equipments.owner_id =" in q for q in queries), (
        "a listagem do cliente precisa filtrar por owner_id — sem isso ele vê "
        "equipamento de outros clientes"
    )


@pytest.mark.asyncio
async def test_staff_listing_is_not_scoped(patch_redis):
    """Admin e técnico continuam vendo o parque inteiro."""
    from app.core.database import get_db

    gen, queries = _db_capturando_queries(_mock_product(), [_mock_equipment()])
    app.dependency_overrides[get_db] = gen
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/products/{_PRODUCT_ID}/equipments")

    assert resp.status_code == 200
    assert not any("equipments.owner_id =" in q for q in queries)


@pytest.mark.asyncio
async def test_client_cannot_get_other_owners_equipment(patch_redis):
    """
    Equipamento de outro cliente devolve 404, mesmo sabendo o UUID.

    404 e não 403: o 403 confirmava que aquele id existe. Como o objetivo da
    correção era justamente fechar oráculos de existência, distinguir "não é
    seu" de "não existe" entregava de graça o que o resto da mudança tirou.
    """
    from app.core.database import get_db

    equip = _mock_equipment()
    equip.owner_id = uuid.uuid4()  # de outra pessoa
    app.dependency_overrides[get_db] = _db_override(equip)
    _override_user(_CLIENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/equipments/{_EQUIP_ID}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_client_cannot_get_ownerless_equipment(patch_redis):
    """
    Equipamento sem dono também é negado ao cliente (fail closed).

    Mesmo critério do /equipment/my, que só devolve o que é dele.
    """
    from app.core.database import get_db

    equip = _mock_equipment()
    equip.owner_id = None
    app.dependency_overrides[get_db] = _db_override(equip)
    _override_user(_CLIENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/equipments/{_EQUIP_ID}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_client_can_get_own_equipment(patch_redis):
    """O próprio equipamento continua acessível — a correção não pode atrapalhar."""
    from app.core.database import get_db

    equip = _mock_equipment()
    equip.owner_id = _CLIENT.id
    app.dependency_overrides[get_db] = _db_override(equip)
    _override_user(_CLIENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/equipments/{_EQUIP_ID}")

    assert resp.status_code == 200
    assert resp.json()["serial_number"] == "SN-001"


@pytest.mark.asyncio
async def test_ownership_refusal_message_is_the_same_everywhere(patch_redis):
    """
    Os três pontos que recusam equipamento alheio falam a mesma língua.

    O check de dono estava copiado inline em três lugares do arquivo, e a cópia
    mais nova respondia com uma mensagem diferente das outras duas — o mesmo
    "não é seu" chegava ao usuário de dois jeitos.
    """
    from app.core.database import get_db

    equip = _mock_equipment()
    equip.owner_id = uuid.uuid4()  # de outra pessoa

    async def _detalhe(metodo: str, url: str, **kwargs) -> str:
        app.dependency_overrides[get_db] = _db_override(equip)
        _override_user(_CLIENT)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await getattr(c, metodo)(url, **kwargs)
        assert resp.status_code == 404, resp.text
        return resp.json()["detail"]

    mensagens = {
        await _detalhe("get", f"/api/v1/equipments/{_EQUIP_ID}"),
        await _detalhe("patch", f"/api/v1/equipment/my/{_EQUIP_ID}", json={"name": "Outro nome"}),
        await _detalhe("delete", f"/api/v1/equipment/my/{_EQUIP_ID}"),
    }

    assert len(mensagens) == 1, f"mensagens divergentes para a mesma recusa: {mensagens}"


@pytest.mark.asyncio
async def test_staff_can_get_any_equipment(patch_redis):
    """Técnico abre equipamento de qualquer cliente — é o trabalho dele."""
    from app.core.database import get_db

    equip = _mock_equipment()
    equip.owner_id = uuid.uuid4()
    app.dependency_overrides[get_db] = _db_override(equip)
    _override_user(_mock_user(UserRole.technician))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/equipments/{_EQUIP_ID}")

    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════
# ATRIBUIÇÃO DE DONO PELO STAFF
# ═══════════════════════════════════════════════════════════════
#
# Sem isto o equipamento cadastrado pela tela de Produtos nascia órfão e assim
# ficava: nenhum endpoint atribuía dono depois, então o cliente real não via o
# aparelho na listagem, era barrado no GET, não conseguia abrir chamado para
# ele e nem recadastrar (o número de série já estava tomado).
#
# O dono só pode ser atribuído pelos endpoints de STAFF. O schema é separado de
# propósito: se `owner_id` entrasse no `EquipmentCreate`/`EquipmentUpdate`
# compartilhado, o cliente passaria a mexer no dono pelos `/equipment/my`.


def _db_por_entidade(**por_tabela):
    """
    Sessão que responde de acordo com a tabela consultada.

    Um mesmo endpoint faz várias consultas (produto, série duplicada, dono), e
    o mock de valor único devolvia a mesma linha para todas. Despachar pelo
    nome da tabela no SQL é independente da ordem das chamadas — mock por
    índice quebra a cada consulta nova.
    """

    def _para(stmt):
        texto = str(stmt).lower()
        for tabela, valor in por_tabela.items():
            if f"from {tabela}" in texto:
                return valor
        return None

    async def _execute(stmt, *args, **kwargs):
        encontrado = _para(stmt)
        result = MagicMock()
        result.scalar_one_or_none.return_value = encontrado
        result.scalar_one.return_value = 0
        result.scalars.return_value.all.return_value = [encontrado] if encontrado else []
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    async def _gen():
        yield session

    return _gen


@pytest.mark.asyncio
async def test_staff_can_assign_owner_on_create(patch_redis):
    """Admin cadastra o equipamento já vinculado ao cliente dono."""
    from app.core.database import get_db

    dono = _mock_user(UserRole.client)
    app.dependency_overrides[get_db] = _db_por_entidade(
        products=_mock_product(), equipments=None, users=dono
    )
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/products/{_PRODUCT_ID}/equipments",
            json={"name": "Titan #002", "owner_id": str(dono.id)},
        )

    assert resp.status_code == 201, resp.text
    # Sem gravar o owner_id o equipamento nasce órfão e fica invisível ao cliente.
    assert resp.json()["owner_id"] == str(dono.id), "o dono informado não foi gravado"


@pytest.mark.asyncio
async def test_staff_create_without_owner_still_works(patch_redis):
    """`owner_id` é opcional: o cadastro sem dono continua valendo."""
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_por_entidade(products=_mock_product(), equipments=None)
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/products/{_PRODUCT_ID}/equipments", json={"name": "Titan #003"}
        )

    assert resp.status_code == 201, resp.text
    assert resp.json()["owner_id"] is None


@pytest.mark.asyncio
async def test_staff_cannot_assign_owner_that_does_not_exist(patch_redis):
    """UUID que não é de ninguém não pode virar dono."""
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_por_entidade(
        products=_mock_product(), equipments=None, users=None
    )
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/products/{_PRODUCT_ID}/equipments",
            json={"name": "Titan #004", "owner_id": str(uuid.uuid4())},
        )

    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_staff_cannot_assign_owner_that_is_not_a_client(patch_redis):
    """
    Só cliente é dono de equipamento.

    Apontar o dono para um técnico faria o equipamento sumir do parque de todo
    mundo: o filtro por dono da listagem só devolve o que é do cliente.
    """
    from app.core.database import get_db

    tecnico = _mock_user(UserRole.technician)
    app.dependency_overrides[get_db] = _db_por_entidade(
        products=_mock_product(), equipments=None, users=tecnico
    )
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/products/{_PRODUCT_ID}/equipments",
            json={"name": "Titan #005", "owner_id": str(tecnico.id)},
        )

    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_staff_can_assign_owner_on_update(patch_redis):
    """O equipamento já cadastrado sem dono pode ser corrigido pelo PATCH de staff."""
    from app.core.database import get_db

    dono = _mock_user(UserRole.client)
    equip = _mock_equipment()
    equip.owner_id = None
    app.dependency_overrides[get_db] = _db_por_entidade(equipments=equip, users=dono)
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/equipments/{_EQUIP_ID}", json={"owner_id": str(dono.id)})

    assert resp.status_code == 200, resp.text
    assert equip.owner_id == dono.id


@pytest.mark.asyncio
async def test_staff_update_rejects_owner_that_is_not_a_client(patch_redis):
    """A mesma validação do POST vale no PATCH — senão a porta fica aberta do lado."""
    from app.core.database import get_db

    admin_alvo = _mock_user(UserRole.admin)
    equip = _mock_equipment()
    equip.owner_id = None
    app.dependency_overrides[get_db] = _db_por_entidade(equipments=equip, users=admin_alvo)
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/equipments/{_EQUIP_ID}", json={"owner_id": str(admin_alvo.id)}
        )

    assert resp.status_code == 400, resp.text
    assert equip.owner_id is None


# ── O cliente NÃO alcança o owner_id ───────────────────────────
#
# Estes dois são a armadilha do schema compartilhado: se `owner_id` for parar
# no `EquipmentCreate`/`EquipmentUpdate` que os `/equipment/my` também usam, o
# cliente passa a escolher o dono do próprio equipamento — e o segundo teste
# fica vermelho na hora, porque o PATCH aplica o corpo inteiro com `setattr`.


@pytest.mark.asyncio
async def test_client_cannot_set_owner_on_self_service_create(patch_redis):
    """`owner_id` enviado pelo cliente no cadastro próprio é ignorado."""
    from app.core.database import get_db

    outro = uuid.uuid4()
    app.dependency_overrides[get_db] = _db_por_entidade(products=_mock_product(), equipments=None)
    _override_user(_CLIENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/equipment/my?product_id={_PRODUCT_ID}",
            json={"name": "Meu Titan", "owner_id": str(outro)},
        )

    assert resp.status_code == 201, resp.text
    # O dono do equipamento criado em /equipment/my é sempre quem fez a chamada.
    assert resp.json()["owner_id"] == str(_CLIENT.id), "o cliente escolheu o dono"


@pytest.mark.asyncio
async def test_client_cannot_set_owner_on_self_service_update(patch_redis):
    """`owner_id` enviado pelo cliente na edição própria não chega ao banco."""
    from app.core.database import get_db

    equip = _mock_equipment()
    equip.owner_id = _CLIENT.id
    app.dependency_overrides[get_db] = _db_por_entidade(equipments=equip)
    _override_user(_CLIENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/equipment/my/{_EQUIP_ID}",
            json={"name": "Outro nome", "owner_id": str(uuid.uuid4())},
        )

    assert resp.status_code == 200, resp.text
    # Transferir o dono pelo /equipment/my daria ao cliente o controle do vínculo.
    assert equip.owner_id == _CLIENT.id, "o owner_id do corpo chegou ao banco"


# ── A recusa não pode denunciar o que existe ──────────────────
#
# Decisão revista: o par 403/"não é seu" + 404/"não existe" dizia ao cliente
# quais ids estão em uso. A consistência com o 403 dos chamados era o argumento
# a favor de manter, e perde — fechar o oráculo aqui não custa nada.


@pytest.mark.asyncio
async def test_refusal_is_indistinguishable_from_not_found(patch_redis):
    """
    A resposta para equipamento alheio é igual, byte a byte, à de inexistente.

    Não basta o status bater: se o texto do detalhe diferisse, a mensagem
    viraria o oráculo que o status deixou de ser.
    """
    from app.core.database import get_db

    alheio = _mock_equipment()
    alheio.owner_id = uuid.uuid4()

    async def _resposta(equipamento):
        app.dependency_overrides[get_db] = _db_override(equipamento)
        _override_user(_CLIENT)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            return await c.get(f"/api/v1/equipments/{_EQUIP_ID}")

    de_outro = await _resposta(alheio)
    inexistente = await _resposta(None)

    assert de_outro.status_code == inexistente.status_code == 404
    assert de_outro.json() == inexistente.json()


# ═══════════════════════════════════════════════════════════════
# /equipment/my É DO CLIENTE (nos verbos que escrevem)
# ═══════════════════════════════════════════════════════════════
#
# `POST /equipment/my` fazia `owner_id = actor.id` com qualquer perfil
# autenticado, então técnico e admin criavam equipamento pertencente a staff —
# exatamente o estado que o `_valida_dono` recusa com 400 nos endpoints de
# staff. Equipamento assim some da listagem escopada (nenhum cliente o possui)
# e nunca pode ser vinculado a chamado: a mesma regra valia num endpoint e não
# no outro.
#
# A leitura continua aberta de propósito: se algum usuário virou staff depois
# de ter sido cliente, o equipamento antigo dele continua existindo, e negar o
# GET esconderia o que ele já podia ver. Staff sem equipamento recebe lista
# vazia, que é o comportamento de hoje.

_VERBOS_DE_ESCRITA = [
    ("post", f"/api/v1/equipment/my?product_id={_PRODUCT_ID}", {"name": "Titan"}),
    ("patch", f"/api/v1/equipment/my/{_EQUIP_ID}", {"name": "Outro nome"}),
    ("delete", f"/api/v1/equipment/my/{_EQUIP_ID}", None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("metodo", "url", "corpo"), _VERBOS_DE_ESCRITA)
@pytest.mark.parametrize("perfil", [UserRole.admin, UserRole.technician])
async def test_staff_cannot_write_through_self_service(patch_redis, metodo, url, corpo, perfil):
    """Admin e técnico são recusados nos três verbos que escrevem."""
    from app.core.database import get_db

    equip = _mock_equipment()
    equip.owner_id = None
    app.dependency_overrides[get_db] = _db_por_entidade(products=_mock_product(), equipments=equip)
    _override_user(_mock_user(perfil))

    kwargs = {"json": corpo} if corpo is not None else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await getattr(c, metodo)(url, **kwargs)

    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
@pytest.mark.parametrize(("metodo", "url", "corpo"), _VERBOS_DE_ESCRITA)
async def test_client_still_writes_through_self_service(patch_redis, metodo, url, corpo):
    """O cliente continua cadastrando, editando e removendo o próprio parque."""
    from app.core.database import get_db

    equip = _mock_equipment()
    equip.owner_id = _CLIENT.id
    app.dependency_overrides[get_db] = _db_por_entidade(products=_mock_product(), equipments=equip)
    _override_user(_CLIENT)

    kwargs = {"json": corpo} if corpo is not None else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await getattr(c, metodo)(url, **kwargs)

    assert resp.status_code in (200, 201, 204), resp.text


@pytest.mark.asyncio
@pytest.mark.parametrize("perfil", [UserRole.admin, UserRole.technician, UserRole.client])
async def test_self_service_listing_stays_open_to_every_role(patch_redis, perfil):
    """
    A leitura segue aberta a todos os perfis.

    É o que preserva o acesso de quem virou staff depois de ter sido cliente —
    o equipamento antigo continua existindo, e negar o GET esconderia dele o
    que já era seu.
    """
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_por_entidade(equipments=None)
    _override_user(_mock_user(perfil))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/equipment/my")

    assert resp.status_code == 200, resp.text


# ═══════════════════════════════════════════════════════════════
# FILTRO "SEM DONO" — achar os órfãos para atribuir
# ═══════════════════════════════════════════════════════════════
#
# A atribuição de dono existe desde 3efb0cf, mas para usá-la o staff precisa
# primeiro ACHAR o equipamento órfão — e a listagem é paginada no servidor.
# Filtrar no navegador só varreria a página aberta: com 200 equipamentos e 20
# por página, o órfão da página 7 fica invisível para sempre.


@pytest.mark.asyncio
async def test_staff_listing_without_owner_filters_by_null_owner(patch_redis):
    """`without_owner=true` filtra no banco, não na página."""
    from app.core.database import get_db

    gen, queries = _db_capturando_queries(_mock_product(), [])
    app.dependency_overrides[get_db] = gen
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            f"/api/v1/products/{_PRODUCT_ID}/equipments", params={"without_owner": "true"}
        )

    assert resp.status_code == 200
    assert any("equipments.owner_id IS NULL" in q for q in queries), (
        "o filtro precisa virar WHERE owner_id IS NULL — filtrar depois de "
        "paginar esconderia o órfão que está fora da página aberta"
    )


@pytest.mark.asyncio
async def test_staff_listing_without_the_flag_lists_everyone(patch_redis):
    """Sem o parâmetro, a listagem continua a mesma — o filtro é opcional."""
    from app.core.database import get_db

    gen, queries = _db_capturando_queries(_mock_product(), [_mock_equipment()])
    app.dependency_overrides[get_db] = gen
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/products/{_PRODUCT_ID}/equipments")

    assert resp.status_code == 200
    assert not any("equipments.owner_id IS NULL" in q for q in queries)


@pytest.mark.asyncio
async def test_staff_listing_without_owner_false_lists_everyone(patch_redis):
    """`without_owner=false` é o mesmo que não mandar — e não vira IS NOT NULL."""
    from app.core.database import get_db

    gen, queries = _db_capturando_queries(_mock_product(), [_mock_equipment()])
    app.dependency_overrides[get_db] = gen
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            f"/api/v1/products/{_PRODUCT_ID}/equipments", params={"without_owner": "false"}
        )

    assert resp.status_code == 200
    assert not any("equipments.owner_id IS" in q for q in queries)


@pytest.mark.asyncio
async def test_client_asking_for_ownerless_stays_scoped(patch_redis):
    """
    Cliente pedindo `without_owner=true` não fura o escopo dele.

    O filtro é somado ao escopo por dono, nunca o substitui: a query pede
    owner_id = <cliente> E owner_id IS NULL, que não casa com nada. Se o filtro
    trocasse o escopo, o cliente passaria a enumerar o parque órfão inteiro.
    """
    from app.core.database import get_db

    gen, queries = _db_capturando_queries(_mock_product(), [])
    app.dependency_overrides[get_db] = gen
    _override_user(_CLIENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            f"/api/v1/products/{_PRODUCT_ID}/equipments", params={"without_owner": "true"}
        )

    assert resp.status_code == 200
    assert any(
        "equipments.owner_id =" in q for q in queries
    ), "o escopo por dono do cliente não pode sumir quando ele manda o filtro"


@pytest.mark.asyncio
async def test_listing_without_owner_combines_with_the_other_filters(patch_redis):
    """O filtro novo soma com busca e situação — não os substitui."""
    from app.core.database import get_db

    gen, queries = _db_capturando_queries(_mock_product(), [])
    app.dependency_overrides[get_db] = gen
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            f"/api/v1/products/{_PRODUCT_ID}/equipments",
            params={"without_owner": "true", "search": "titan", "is_active": "true"},
        )

    assert resp.status_code == 200
    consulta = next(q for q in queries if "equipments.owner_id IS NULL" in q)
    assert "lower(equipments.name) LIKE" in consulta
    assert "equipments.is_active =" in consulta
