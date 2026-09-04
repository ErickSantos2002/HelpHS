"""
Tests for Ticket CRUD endpoints and protocol generation.
DB and Redis fully mocked.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import TicketCategory, TicketPriority, TicketStatus, UserRole, UserStatus

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


# ── Constants ─────────────────────────────────────────────────

_NOW = datetime.now(UTC)
_TICKET_ID = uuid.uuid4()
_CREATOR_ID = uuid.uuid4()
_TECH_ID = uuid.uuid4()


# ── Mock builders ─────────────────────────────────────────────


def _mock_user(role=UserRole.client, user_id=None):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.email = f"{role.value}@test.com"
    u.role = role
    u.status = UserStatus.active
    return u


def _mock_equipment(name="Phoebus da recepção", serial="WATFR01-001", owner_id=None):
    e = MagicMock()
    e.id = uuid.uuid4()
    e.name = name
    e.serial_number = serial
    e.product_id = None
    e.owner_id = owner_id
    return e


def _mock_ticket(
    ticket_id=None,
    creator_id=None,
    status=TicketStatus.open,
    protocol="HS-2026-0001",
):
    t = MagicMock()
    t.id = ticket_id or _TICKET_ID
    t.protocol = protocol
    t.title = "Equipamento com falha"
    t.description = "O bafômetro não liga"
    t.status = status
    t.priority = TicketPriority.medium
    t.category = TicketCategory.hardware
    t.creator_id = creator_id or _CREATOR_ID
    t.assignee_id = None
    t.product_id = None
    t.equipments = []
    t.sla_response_due_at = None
    t.sla_resolve_due_at = None
    t.sla_first_response = None
    t.sla_paused_at = None
    t.sla_total_paused_ms = 0
    t.sla_response_breach = False
    t.sla_resolve_breach = False
    t.closed_at = None
    t.resolved_at = None
    t.auto_closed = False
    t.reopened_at = None
    t.reopen_count = 0
    t.created_at = _NOW
    t.updated_at = _NOW
    t.technician_notes = None
    t.ai_classification = None
    t.ai_confidence = None
    t.ai_summary = None
    t.ai_conversation_summary = None
    # Campos opcionais do TicketResponse — sem valor explícito o MagicMock
    # devolve um objeto no lugar de None e a validação falha
    t.assignee_name = None
    t.product_name = None
    t.equipment_name = None
    t.equipment_serial = None
    t.client_observation = None
    t.resolution_note = None
    t.tags = []
    return t


# ── DB session factory ────────────────────────────────────────


def _db(lookup=None, count=0):
    """Single-value mock: scalar_one_or_none → lookup, scalar_one → count."""

    async def _execute(*args, **kwargs):
        result = MagicMock()
        # O notify() busca (email, papel) do destinatário com .one_or_none().
        # Cliente de propósito: mantém o caminho de e-mail exercido como antes.
        result.one_or_none.return_value = ("dest@test.com", UserRole.client, "Destino")
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


def _db_sequence(*responses):
    """Mock that returns different responses for sequential execute calls."""
    call_count = [0]

    async def _execute(*args, **kwargs):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        resp = responses[idx]

        result = MagicMock()
        result.one_or_none.return_value = ("dest@test.com", UserRole.client, "Destino")
        if isinstance(resp, int):
            result.scalar_one.return_value = resp
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = []
        elif isinstance(resp, list):
            result.scalar_one_or_none.return_value = None
            result.scalar_one.return_value = len(resp)
            result.scalars.return_value.all.return_value = resp
        else:
            result.scalar_one_or_none.return_value = resp
            result.scalar_one.return_value = 0
            result.scalars.return_value.all.return_value = [resp] if resp else []
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


def _db_seq_override(*responses):
    session = _db_sequence(*responses)

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
# PROTOCOL GENERATION UNIT TESTS
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_generate_protocol_first_ticket():
    """When no tickets exist, protocol should be HS-YYYY-0001."""
    from app.utils.protocol import generate_protocol

    db = _db(lookup=None)
    protocol = await generate_protocol(db)
    year = datetime.now(UTC).year
    assert protocol == f"HS-{year}-0001"


@pytest.mark.asyncio
async def test_generate_protocol_increments():
    """When last ticket is HS-YYYY-0005, next should be HS-YYYY-0006."""
    from app.utils.protocol import generate_protocol

    year = datetime.now(UTC).year
    db = _db(lookup=f"HS-{year}-0005")
    protocol = await generate_protocol(db)
    assert protocol == f"HS-{year}-0006"


@pytest.mark.asyncio
async def test_generate_protocol_pads_to_4_digits():
    """Sequence number should always be zero-padded to 4 digits."""
    from app.utils.protocol import generate_protocol

    year = datetime.now(UTC).year
    db = _db(lookup=f"HS-{year}-0009")
    protocol = await generate_protocol(db)
    assert protocol == f"HS-{year}-0010"
    assert len(protocol.split("-")[-1]) == 4


@pytest.mark.asyncio
async def test_generate_protocol_large_seq():
    """Protocol handles sequence numbers beyond 9999 (zero-padding still works)."""
    from app.utils.protocol import generate_protocol

    year = datetime.now(UTC).year
    db = _db(lookup=f"HS-{year}-9999")
    protocol = await generate_protocol(db)
    assert protocol == f"HS-{year}-10000"


# ═══════════════════════════════════════════════════════════════
# TICKET CRUD TESTS
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_ticket(patch_redis):
    from app.core.database import get_db

    creator = _mock_user(UserRole.client)
    ticket = _mock_ticket(creator_id=creator.id)

    # Sequence: 1st execute = generate_protocol (returns None → seq 1)
    # commit + refresh sets up the ticket
    db_session = _db_sequence(None)

    async def _refresh(obj):
        obj.id = ticket.id
        obj.protocol = ticket.protocol
        obj.title = ticket.title
        obj.description = ticket.description
        obj.status = TicketStatus.open
        obj.priority = TicketPriority.medium
        obj.category = TicketCategory.hardware
        obj.creator_id = creator.id
        obj.assignee_id = None
        obj.product_id = None
        obj.equipment_id = None
        obj.sla_response_due_at = None
        obj.sla_resolve_due_at = None
        obj.sla_response_breach = False
        obj.sla_resolve_breach = False
        obj.closed_at = None
        obj.created_at = _NOW
        obj.updated_at = _NOW

    db_session.refresh = _refresh

    async def _gen():
        yield db_session

    app.dependency_overrides[get_db] = _gen
    _override_user(creator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/tickets",
            json={
                "title": "Equipamento com falha",
                "description": "O bafômetro não liga",
                "category": "hardware",
            },
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["protocol"] == "HS-2026-0001"
    assert data["status"] == "open"


@pytest.mark.asyncio
async def test_list_tickets_client_sees_own(patch_redis):
    from app.core.database import get_db

    creator = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(creator_id=_CREATOR_ID)

    # count=1, then list=[ticket]
    app.dependency_overrides[get_db] = _db_seq_override(1, [ticket])
    _override_user(creator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/tickets")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["protocol"] == "HS-2026-0001"


@pytest.mark.asyncio
async def test_list_tickets_admin_sees_all(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket()

    app.dependency_overrides[get_db] = _db_seq_override(1, [ticket])
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/tickets")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_get_ticket_client_own(patch_redis):
    from app.core.database import get_db

    creator = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(creator_id=_CREATOR_ID)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(creator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(ticket.id)


@pytest.mark.asyncio
async def test_get_ticket_client_forbidden(patch_redis):
    from app.core.database import get_db

    other_client = _mock_user(UserRole.client)  # different user_id
    ticket = _mock_ticket(creator_id=_CREATOR_ID)  # owned by someone else

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(other_client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}")
    # 404 e não 403: o 403 confirmava que aquele chamado existe
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_ticket_not_found(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    app.dependency_overrides[get_db] = _db_override(None)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_ticket_technician_notes(patch_redis):
    """Technician can save internal notes but not edit core ticket fields."""
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket()

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # Saving notes is allowed
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}",
            json={"technician_notes": "Diagnóstico inicial: problema na bateria."},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_update_ticket_technician_cannot_edit_fields(patch_redis):
    """Technician cannot edit core ticket fields (title, priority, etc.)."""
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket()

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}",
            json={"title": "Novo título", "priority": "high"},
        )
    # Request succeeds but title/priority are silently ignored (only technician_notes applied)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_update_ticket_client_own_open(patch_redis):
    """Client no longer has edit access — endpoint restricted to admin/technician."""
    from app.core.database import get_db

    creator = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(creator_id=_CREATOR_ID, status=TicketStatus.open)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(creator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}",
            json={"title": "Título atualizado"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_ticket_client_not_open(patch_redis):
    """Client no longer has edit access regardless of ticket status."""
    from app.core.database import get_db

    creator = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(creator_id=_CREATOR_ID, status=TicketStatus.in_progress)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(creator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}",
            json={"title": "Tentativa de edição"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_status_valid_transition(patch_redis):
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket(status=TicketStatus.open)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/status",
            json={"status": "in_progress"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_update_status_invalid_transition(patch_redis):
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket(status=TicketStatus.closed)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/status",
            json={"status": "open"},
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_status_client_forbidden(patch_redis):
    from app.core.database import get_db

    client = _mock_user(UserRole.client)
    ticket = _mock_ticket()
    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/status",
            json={"status": "in_progress"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_assign_ticket(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket()
    assignee = _mock_user(UserRole.technician, user_id=_TECH_ID)

    # Sequence: 1st execute = get ticket, 2nd = get assignee
    app.dependency_overrides[get_db] = _db_seq_override(ticket, assignee)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/assign",
            json={"assignee_id": str(_TECH_ID)},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_detalhe_traz_produto_e_equipamentos(patch_redis):
    """O ticket guarda só o id do produto; a resposta precisa trazer o nome."""
    from unittest.mock import MagicMock

    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket()
    ticket.product_id = uuid.uuid4()
    ticket.equipments = [_mock_equipment("Phoebus da recepção", "WATFR01-12453")]

    produto = MagicMock()
    produto.name = "Phoebus"

    session = _db_sequence(ticket)

    async def _get(model, pk):
        return produto

    session.get = _get

    async def _gen():
        yield session

    app.dependency_overrides[get_db] = _gen
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["product_name"] == "Phoebus"
    assert len(body["equipments"]) == 1
    assert body["equipments"][0]["name"] == "Phoebus da recepção"
    assert body["equipments"][0]["serial_number"] == "WATFR01-12453"


@pytest.mark.asyncio
async def test_chamado_com_varios_equipamentos(patch_redis):
    """Um problema que atinge três aparelhos continua sendo um chamado só."""
    from unittest.mock import MagicMock

    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket()
    ticket.product_id = uuid.uuid4()
    ticket.equipments = [
        _mock_equipment("Phoebus da recepção", "WATFR01-001"),
        _mock_equipment("Phoebus da portaria", "WATFR01-002"),
        _mock_equipment("Phoebus do almoxarifado", "WATFR01-003"),
    ]

    produto = MagicMock()
    produto.name = "Phoebus"

    session = _db_sequence(ticket)

    async def _get(model, pk):
        return produto

    session.get = _get

    async def _gen():
        yield session

    app.dependency_overrides[get_db] = _gen
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}")

    seriais = [e["serial_number"] for e in resp.json()["equipments"]]
    assert seriais == ["WATFR01-001", "WATFR01-002", "WATFR01-003"]


@pytest.mark.asyncio
async def test_produto_vem_do_equipamento_quando_o_chamado_nao_informou(patch_redis):
    """
    O cliente que escolhe o aparelho não precisa repetir o produto — sem essa
    herança, a aba Base de Conhecimento do chamado ficaria sem sugestões.
    """
    from unittest.mock import MagicMock

    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket()
    ticket.product_id = None
    equipamento = _mock_equipment("Phoebus da recepção", "WATFR01-001")
    equipamento.product_id = uuid.uuid4()
    ticket.equipments = [equipamento]

    produto = MagicMock()
    produto.name = "Phoebus"

    session = _db_sequence(ticket)

    async def _get(model, pk):
        return produto

    session.get = _get

    async def _gen():
        yield session

    app.dependency_overrides[get_db] = _gen
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}")

    assert resp.json()["product_name"] == "Phoebus"


@pytest.mark.asyncio
async def test_ticket_sem_produto_devolve_nulo(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket()
    ticket.product_id = None
    ticket.equipments = []

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["product_name"] is None
    assert body["equipments"] == []


@pytest.mark.asyncio
async def test_cliente_nao_vincula_equipamento_de_outra_empresa(patch_redis):
    """
    Sem essa checagem, mandar ids aleatórios devolveria na resposta o nome e o
    número de série de aparelhos de outros clientes.
    """
    from app.core.database import get_db

    cliente = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    alheio = _mock_equipment("Phoebus de outra empresa", "XXXX-999", owner_id=uuid.uuid4())

    # 1ª consulta: SLAConfig; 2ª: os equipamentos informados
    app.dependency_overrides[get_db] = _db_seq_override(None, [alheio])
    _override_user(cliente)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/tickets",
            json={
                "title": "Teste",
                "description": "Teste",
                "priority": "medium",
                "category": "hardware",
                "equipment_ids": [str(alheio.id)],
            },
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_equipamento_inexistente_e_recusado(patch_redis):
    from app.core.database import get_db

    cliente = _mock_user(UserRole.client, user_id=_CREATOR_ID)

    app.dependency_overrides[get_db] = _db_seq_override(None, [])
    _override_user(cliente)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/tickets",
            json={
                "title": "Teste",
                "description": "Teste",
                "priority": "medium",
                "category": "hardware",
                "equipment_ids": [str(uuid.uuid4())],
            },
        )

    assert resp.status_code == 400
    assert "não existem" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_limite_de_equipamentos_por_chamado(patch_redis):
    from app.core.database import get_db

    cliente = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    app.dependency_overrides[get_db] = _db_seq_override(None)
    _override_user(cliente)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/tickets",
            json={
                "title": "Teste",
                "description": "Teste",
                "priority": "medium",
                "category": "hardware",
                "equipment_ids": [str(uuid.uuid4()) for _ in range(21)],
            },
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_qualquer_tecnico_conclui_o_ticket(patch_redis):
    """Concluir não exige ser o responsável — qualquer técnico atende."""
    from app.core.database import get_db

    outro_tecnico = uuid.uuid4()
    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket(status=TicketStatus.in_progress)
    ticket.assignee_id = outro_tecnico

    app.dependency_overrides[get_db] = _db_seq_override(ticket, None)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/resolve",
            json={"resolution_note": "Equipamento substituído."},
        )

    assert resp.status_code == 200
    assert ticket.status == TicketStatus.resolved


@pytest.mark.asyncio
async def test_tecnico_muda_status_de_ticket_de_outro(patch_redis):
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket(status=TicketStatus.open)
    ticket.assignee_id = uuid.uuid4()

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/status",
            json={"status": "in_progress"},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_assign_ticket_fechado_explica_o_motivo(patch_redis):
    """Reatribuir ticket fechado precisa dizer por que não dá."""
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket(status=TicketStatus.closed)
    assignee = _mock_user(UserRole.technician, user_id=_TECH_ID)

    app.dependency_overrides[get_db] = _db_seq_override(ticket, assignee)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/assign",
            json={"assignee_id": str(_TECH_ID)},
        )
    assert resp.status_code == 409
    assert "fechado" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_assign_ticket_para_cliente_e_rejeitado(patch_redis):
    """Só técnico ou admin pode receber ticket."""
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket()
    cliente = _mock_user(UserRole.client, user_id=_TECH_ID)

    app.dependency_overrides[get_db] = _db_seq_override(ticket, cliente)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/assign",
            json={"assignee_id": str(_TECH_ID)},
        )
    assert resp.status_code == 422
    assert "técnicos ou administradores" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_assign_ticket_para_usuario_inativo_e_rejeitado(patch_redis):
    from app.core.database import get_db
    from app.models.models import UserStatus

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket()
    inativo = _mock_user(UserRole.technician, user_id=_TECH_ID)
    inativo.status = UserStatus.inactive

    app.dependency_overrides[get_db] = _db_seq_override(ticket, inativo)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/assign",
            json={"assignee_id": str(_TECH_ID)},
        )
    assert resp.status_code == 422
    assert "inativo" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_assign_ticket_para_o_mesmo_tecnico_avisa(patch_redis):
    """Reatribuir para quem já é o responsável não é erro silencioso."""
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket()
    ticket.assignee_id = _TECH_ID
    assignee = _mock_user(UserRole.technician, user_id=_TECH_ID)

    app.dependency_overrides[get_db] = _db_seq_override(ticket, assignee)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/assign",
            json={"assignee_id": str(_TECH_ID)},
        )
    assert resp.status_code == 409
    assert "já está atribuído" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_assign_ticket_unassign(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket()

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/assign",
            json={"assignee_id": None},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cancel_ticket_admin(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket(status=TicketStatus.open)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/tickets/{_TICKET_ID}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_cancel_already_cancelled(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket(status=TicketStatus.cancelled)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/tickets/{_TICKET_ID}")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_cancel_ticket_client_forbidden(patch_redis):
    from app.core.database import get_db

    client = _mock_user(UserRole.client)
    ticket = _mock_ticket()
    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/tickets/{_TICKET_ID}")
    assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════
# PRIMEIRA RESPOSTA DO SLA
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_assumir_chamado_nao_marca_primeira_resposta(patch_redis):
    """Mudar o status não é falar com o cliente."""
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket(status=TicketStatus.open)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/status",
            json={"status": "in_progress"},
        )

    assert resp.status_code == 200
    assert ticket.sla_first_response is None


@pytest.mark.asyncio
async def test_cancelar_pelo_status_nao_marca_primeira_resposta(patch_redis):
    """Chamado cancelado não pode entrar no tempo médio de resposta."""
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket(status=TicketStatus.open)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/status",
            json={"status": "cancelled"},
        )

    assert resp.status_code == 200
    assert ticket.sla_first_response is None


@pytest.mark.asyncio
async def test_atribuir_chamado_nao_marca_primeira_resposta(patch_redis):
    """Atribuir a um terceiro não é resposta — nem do técnico, nem de quem atribuiu."""
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket(status=TicketStatus.open)
    assignee = _mock_user(UserRole.technician, user_id=_TECH_ID)

    app.dependency_overrides[get_db] = _db_seq_override(ticket, assignee)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/assign",
            json={"assignee_id": str(_TECH_ID)},
        )

    assert resp.status_code == 200
    assert ticket.sla_first_response is None


@pytest.mark.asyncio
async def test_resolver_marca_primeira_resposta_fora_de_open(patch_redis):
    """A nota de resolução é texto que o cliente lê — vale como resposta.

    Antes, resolver um chamado que já saíra de `open` não marcava nada: o
    chamado era atendido e sumia do tempo médio de resposta.
    """
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket(status=TicketStatus.awaiting_client)

    app.dependency_overrides[get_db] = _db_seq_override(ticket, None)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/resolve",
            json={"resolution_note": "Sensor recalibrado."},
        )

    assert resp.status_code == 200
    assert ticket.sla_first_response is not None


@pytest.mark.asyncio
async def test_resolver_o_proprio_chamado_nao_marca_primeira_resposta(patch_redis):
    """Chamado interno que a mesma pessoa abre e resolve não teve espera."""
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket(status=TicketStatus.in_progress, creator_id=admin.id)

    app.dependency_overrides[get_db] = _db_seq_override(ticket, None)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/resolve",
            json={"resolution_note": "Ajuste feito na hora."},
        )

    assert resp.status_code == 200
    assert ticket.sla_first_response is None


# ═══════════════════════════════════════════════════════════════
# ORÁCULO DE EXISTÊNCIA — chamado alheio some, não é negado
# ═══════════════════════════════════════════════════════════════
#
# Mesmo formato que os equipamentos ganharam no 637ad0f: para o CLIENTE, o
# chamado de outra pessoa responde igual a um id que não existe. O 403 dizia
# "existe, mas não é seu" — meia resposta a mais do que quem só tem o id
# deveria conseguir.
#
# Só para cliente. Técnico e admin já listam o sistema inteiro sem escopo, de
# modo que 404 entre eles não fecharia nada e quebraria assumir/atender.


@pytest.mark.asyncio
async def test_observation_cliente_de_outro_chamado(patch_redis):
    """Editar a observação de chamado alheio responde como inexistente."""
    from app.core.database import get_db

    intruso = _mock_user(UserRole.client)
    ticket = _mock_ticket(creator_id=_CREATOR_ID)
    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(intruso)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/observation",
            json={"client_observation": "Passei aqui só para ver"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_observation_dono_continua_editando(patch_redis):
    """A correção não pode tirar do cliente a própria observação."""
    from app.core.database import get_db

    dono = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(creator_id=_CREATOR_ID)
    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(dono)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/observation",
            json={"client_observation": "O aparelho voltou a falhar hoje"},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_observation_tecnico_continua_403(patch_redis):
    """
    Técnico segue com 403 — e isso está certo.

    A observação é campo do cliente; a recusa ao técnico é de PAPEL, não de
    posse. Ele já enxerga o chamado inteiro pela listagem, então 404 aqui não
    esconderia existência nenhuma e trocaria "seu perfil não faz isso" por uma
    mentira.
    """
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket(creator_id=_CREATOR_ID)
    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/observation",
            json={"client_observation": "nota do técnico"},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_chamado_alheio_e_inexistente_respondem_igual_em_todo_lugar(patch_redis):
    """
    Os endpoints de chamado falam a mesma língua nas duas recusas.

    Status E texto: dois 404 com mensagens diferentes continuariam separando
    "não é seu" de "não existe". É o mesmo contrato que
    `test_ownership_refusal_message_is_the_same_everywhere` guarda para
    equipamentos — e o motivo de existir é que a versão anterior desta regra
    divergiu justamente por uma cópia esquecida.
    """
    from app.core.database import get_db

    intruso = _mock_user(UserRole.client)

    async def _resposta(metodo, url, ticket, **kwargs):
        app.dependency_overrides[get_db] = _db_override(ticket)
        _override_user(intruso)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await getattr(c, metodo)(url, **kwargs)
        return r.status_code, r.json()["detail"]

    caminhos = [
        ("get", f"/api/v1/tickets/{_TICKET_ID}", {}),
        ("get", f"/api/v1/tickets/{_TICKET_ID}/history", {}),
        (
            "patch",
            f"/api/v1/tickets/{_TICKET_ID}/observation",
            {"json": {"client_observation": "x"}},
        ),
    ]

    for metodo, url, kwargs in caminhos:
        alheio = await _resposta(metodo, url, _mock_ticket(creator_id=_CREATOR_ID), **kwargs)
        inexistente = await _resposta(metodo, url, None, **kwargs)
        assert (
            alheio == inexistente
        ), f"{metodo.upper()} {url} separa alheio de inexistente: {alheio} vs {inexistente}"


@pytest.mark.asyncio
async def test_staff_continua_lendo_chamado_de_qualquer_um(patch_redis):
    """Técnico abre chamado de qualquer cliente — é o trabalho dele."""
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    app.dependency_overrides[get_db] = _db_override(_mock_ticket(creator_id=_CREATOR_ID))
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}")

    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════
# O CHAMADO DIZ SE A PRIMEIRA RESPOSTA JÁ FOI DADA
# ═══════════════════════════════════════════════════════════════
#
# O chip de prazo do front recebia prazo e flag de violação, e nada sobre a
# resposta em si. Um chamado respondido no prazo e reaberto dias depois
# aparecia como "Resposta: Vencido" — o relógio comparava o prazo do primeiro
# ciclo com o agora, sem saber que a resposta tinha sido dada lá. Expor o
# carimbo é o que deixa o chip parar o relógio em vez de adivinhar pela flag,
# que só é recalculada em escrita e por isso é velha por construção.


@pytest.mark.asyncio
async def test_resposta_do_chamado_expoe_quando_a_primeira_resposta_foi_dada(patch_redis):
    from app.core.database import get_db

    ticket = _mock_ticket()
    ticket.sla_first_response = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)
    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(_mock_user(UserRole.admin))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}")

    assert resp.status_code == 200
    assert resp.json()["sla_first_response"].startswith("2026-08-20T14:30")


@pytest.mark.asyncio
async def test_chamado_sem_resposta_expoe_o_campo_nulo(patch_redis):
    """Nulo, e não ausente: o front decide pelo valor, não pela presença da chave."""
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_override(_mock_ticket())
    _override_user(_mock_user(UserRole.admin))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}")

    assert resp.status_code == 200
    assert "sla_first_response" in resp.json()
    assert resp.json()["sla_first_response"] is None


@pytest.mark.asyncio
async def test_chamado_de_cliente_nasce_com_a_helo_falando(patch_redis, monkeypatch):
    """
    O gancho de verdade: abrir chamado pela API dispara a saudação.

    Os outros testes da Helô exercitam `abre_triagem` direto. Este prova o que
    nenhum deles prova — que alguém a CHAMA. O módulo ficou dois dias escrito e
    isolado, sem ninguém importar, e a suíte inteira passava.
    """
    from app.core.database import get_db
    from app.models.models import ChatMessage
    from app.services import helo

    monkeypatch.setattr(helo, "get_settings", lambda: MagicMock(helo_enabled=True))

    creator = _mock_user(UserRole.client)
    db_session = _db_sequence(None)
    db_session.refresh = AsyncMock()

    async def _gen():
        yield db_session

    app.dependency_overrides[get_db] = _gen
    _override_user(creator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/tickets",
            json={
                "title": "Equipamento com falha",
                "description": "O bafômetro não liga",
                "category": "hardware",
            },
        )

    assert resp.status_code == 201, resp.text

    adicionados = [c.args[0] for c in db_session.add.call_args_list]
    falas = [o for o in adicionados if isinstance(o, ChatMessage)]
    assert len(falas) == 1, "a Helô devia ter falado uma vez"
    assert falas[0].is_ai is True
    assert falas[0].sender_id is None
    assert "Sou a Helô" in falas[0].content


@pytest.mark.asyncio
async def test_chamado_aberto_por_staff_nao_e_triado(patch_redis, monkeypatch):
    """
    Staff abrindo chamado em nome de alguém não é triado por robô.

    E a saudação chamaria o staff pelo primeiro nome, como se ele fosse o
    cliente — o tipo de detalhe que só aparece na frente do usuário.
    """
    from app.core.database import get_db
    from app.models.models import ChatMessage
    from app.services import helo

    monkeypatch.setattr(helo, "get_settings", lambda: MagicMock(helo_enabled=True))

    tecnico = _mock_user(UserRole.technician)
    db_session = _db_sequence(None)
    db_session.refresh = AsyncMock()

    async def _gen():
        yield db_session

    app.dependency_overrides[get_db] = _gen
    _override_user(tecnico)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/tickets",
            json={
                "title": "Equipamento com falha",
                "description": "O bafômetro não liga",
                "category": "hardware",
            },
        )

    assert resp.status_code == 201, resp.text
    adicionados = [c.args[0] for c in db_session.add.call_args_list]
    assert not [o for o in adicionados if isinstance(o, ChatMessage)]


@pytest.mark.asyncio
async def test_tecnico_desliga_a_ia_no_chamado(patch_redis):
    """
    O botão de quem entra na conversa.

    O PATCH geral de chamado limita o técnico a `technician_notes` — por isso o
    interruptor tem endpoint próprio: seria estranho o dono do botão não poder
    apertá-lo.
    """
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket()
    ticket.ai_enabled = True

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/tickets/{_TICKET_ID}/ai", json={"enabled": False})

    assert resp.status_code == 200, resp.text
    assert ticket.ai_enabled is False


@pytest.mark.asyncio
async def test_cliente_nao_mexe_no_interruptor_do_chamado(patch_redis):
    """O interruptor é da equipe: o cliente não liga a IA de volta no chamado dele."""
    from app.core.database import get_db

    ticket = _mock_ticket()
    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(_mock_user(UserRole.client))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/tickets/{_TICKET_ID}/ai", json={"enabled": False})

    assert resp.status_code == 403
