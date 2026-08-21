"""
Encerramento do chamado — fechamento automático (RN-005) e reabertura (RN-006).

O que estes testes protegem:
  - o prazo é contado em DIAS ÚTEIS, então resolver na sexta não consome o
    fim de semana do cliente;
  - a rotina só fecha quem já venceu, e registra a ação como "sistema"
    (histórico sem autor) em vez de atribuí-la a alguém que não fez nada;
  - o prazo de reabertura vale para o cliente, não para a equipe;
  - reabrir devolve um prazo de SLA novo — senão o chamado voltaria já vencido.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from app.models.models import (
    TicketCategory,
    TicketPriority,
    TicketStatus,
    UserRole,
    UserStatus,
)
from app.services.ticket_lifecycle import (
    auto_close_deadline,
    can_client_reopen,
    close_expired_tickets,
    reopen_deadline,
)
from app.utils.sla import SP_TZ, add_business_days

_settings = get_settings()

_TICKET_ID = uuid.uuid4()
_CREATOR_ID = uuid.uuid4()


# ── Mocks ─────────────────────────────────────────────────────


def _mock_user(role=UserRole.client, user_id=None):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.name = "Fulano de Tal"
    u.email = f"{role.value}@test.com"
    u.role = role
    u.status = UserStatus.active
    return u


def _mock_ticket(status=TicketStatus.resolved, resolved_at=None, creator_id=None):
    t = MagicMock()
    t.id = _TICKET_ID
    t.protocol = "HS-2026-0010"
    t.title = "O aparelho travou"
    t.description = "meu aparelho travou"
    t.status = status
    t.priority = TicketPriority.medium
    t.category = TicketCategory.hardware
    t.creator_id = creator_id or _CREATOR_ID
    t.assignee_id = None
    t.product_id = None
    t.equipment_id = None
    t.sla_response_due_at = None
    t.sla_resolve_due_at = None
    t.sla_first_response = None
    t.sla_paused_at = None
    t.sla_total_paused_ms = 0
    t.sla_response_breach = False
    t.sla_resolve_breach = True  # resolvido depois do prazo, como no caso real
    t.closed_at = resolved_at
    t.resolved_at = resolved_at
    t.auto_closed = False
    t.reopened_at = None
    t.reopen_count = 0
    t.created_at = datetime.now(UTC)
    t.updated_at = datetime.now(UTC)
    t.technician_notes = None
    t.ai_classification = None
    t.ai_confidence = None
    t.ai_summary = None
    t.ai_conversation_summary = None
    t.assignee_name = None
    t.product_name = None
    t.equipment_name = None
    t.equipment_serial = None
    t.client_observation = None
    t.resolution_note = "Trocamos a placa."
    t.tags = []
    return t


def _db(*lookups):
    """Sessão mock: cada execute() devolve o próximo item de `lookups`."""
    calls = [0]

    async def _execute(*_a, **_k):
        idx = min(calls[0], len(lookups) - 1)
        calls[0] += 1
        item = lookups[idx]

        result = MagicMock()
        if isinstance(item, list):
            result.scalars.return_value.all.return_value = item
            result.scalar_one_or_none.return_value = None
        else:
            result.scalars.return_value.all.return_value = [item] if item else []
            result.scalar_one_or_none.return_value = item
        result.scalar_one.return_value = 0
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _db_override(*lookups):
    session = _db(*lookups)

    async def _gen():
        yield session

    return _gen


def _override_user(user):
    from app.core.security import get_current_user

    async def _u():
        return user

    app.dependency_overrides[get_current_user] = _u


@pytest.fixture(autouse=True)
def _limpa():
    yield
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════
# PRAZOS EM DIAS ÚTEIS
# ═══════════════════════════════════════════════════════════════


def test_prazo_pula_o_fim_de_semana():
    """
    Resolvido sexta 16h, o fechamento em 3 dias úteis cai na quarta — em dias
    corridos cairia na segunda, dando ao cliente um único dia de trabalho.
    """
    sexta = SP_TZ.localize(datetime(2026, 8, 7, 16, 0))
    assert sexta.weekday() == 4

    prazo = add_business_days(sexta, 3)

    assert prazo.weekday() == 2  # quarta
    assert prazo.day == 12


def test_reabertura_tem_prazo_maior_que_o_fechamento():
    """O cliente ainda pode reabrir depois que o chamado já fechou sozinho."""
    resolvido = SP_TZ.localize(datetime(2026, 8, 3, 9, 0))  # segunda

    assert reopen_deadline(resolvido, _settings) > auto_close_deadline(resolvido, _settings)


def test_chamado_sem_data_nenhuma_nao_aceita_reabertura():
    """Sem data de resolução nem de fechamento não há como contar prazo."""
    ticket = _mock_ticket(status=TicketStatus.closed, resolved_at=None)
    ticket.closed_at = None

    assert can_client_reopen(ticket, _settings) is False


def test_chamado_antigo_usa_o_closed_at_como_referencia():
    """
    Chamados encerrados antes da v1.4.0 não têm resolved_at. Sem o fallback
    para closed_at eles ficariam sem prazo nenhum — nem fecham, nem reabrem.
    """
    ticket = _mock_ticket(status=TicketStatus.resolved, resolved_at=None)
    ticket.closed_at = datetime.now(UTC)

    assert can_client_reopen(ticket, _settings) is True


@pytest.mark.asyncio
async def test_fechamento_automatico_alcanca_chamado_antigo_sem_resolved_at():
    antigo = _mock_ticket(resolved_at=None)
    antigo.closed_at = datetime.now(UTC) - timedelta(days=30)
    db = _db([antigo])

    with patch("app.services.ticket_lifecycle.notify", new=AsyncMock()):
        fechados = await close_expired_tickets(db, _settings)

    assert fechados == 1
    assert antigo.status == TicketStatus.closed


def test_chamado_aberto_nao_aceita_reabertura():
    ticket = _mock_ticket(status=TicketStatus.in_progress, resolved_at=datetime.now(UTC))

    assert can_client_reopen(ticket, _settings) is False


# ═══════════════════════════════════════════════════════════════
# FECHAMENTO AUTOMÁTICO (RN-005)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_fecha_o_chamado_que_passou_do_prazo():
    vencido = _mock_ticket(resolved_at=datetime.now(UTC) - timedelta(days=30))
    db = _db([vencido])

    with patch("app.services.ticket_lifecycle.notify", new=AsyncMock()):
        fechados = await close_expired_tickets(db, _settings)

    assert fechados == 1
    assert vencido.status == TicketStatus.closed
    assert vencido.auto_closed is True
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_nao_fecha_quem_acabou_de_ser_resolvido():
    recem = _mock_ticket(resolved_at=datetime.now(UTC))
    db = _db([recem])

    with patch("app.services.ticket_lifecycle.notify", new=AsyncMock()):
        fechados = await close_expired_tickets(db, _settings)

    assert fechados == 0
    assert recem.status == TicketStatus.resolved
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_fechamento_automatico_fica_no_historico_sem_autor():
    """
    Apontar a ação para um administrador qualquer registraria no histórico algo
    que ninguém praticou — por isso user_id fica nulo e a tela mostra "Sistema".
    """
    vencido = _mock_ticket(resolved_at=datetime.now(UTC) - timedelta(days=30))
    db = _db([vencido])

    with patch("app.services.ticket_lifecycle.notify", new=AsyncMock()):
        await close_expired_tickets(db, _settings)

    historicos = [
        c.args[0] for c in db.add.call_args_list if type(c.args[0]).__name__ == "TicketHistory"
    ]
    assert len(historicos) == 1
    assert historicos[0].user_id is None
    assert historicos[0].new_value == "closed"
    assert "automaticamente" in historicos[0].comment


@pytest.mark.asyncio
async def test_rodada_sem_nada_vencido_nao_toca_no_banco():
    db = _db([])

    fechados = await close_expired_tickets(db, _settings)

    assert fechados == 0
    db.commit.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════
# REABERTURA (RN-006)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cliente_reabre_dentro_do_prazo():
    from app.core.database import get_db

    cliente = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(status=TicketStatus.closed, resolved_at=datetime.now(UTC))

    app.dependency_overrides[get_db] = _db_override(ticket, None)
    _override_user(cliente)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/reopen",
            json={"reason": "O aparelho voltou a travar hoje de manhã."},
        )

    assert resp.status_code == 200
    assert ticket.status == TicketStatus.open  # sem responsável, volta para a fila
    assert ticket.reopen_count == 1
    assert ticket.closed_at is None
    assert ticket.resolved_at is None


@pytest.mark.asyncio
async def test_reabertura_devolve_o_chamado_ao_responsavel():
    from app.core.database import get_db

    cliente = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(status=TicketStatus.resolved, resolved_at=datetime.now(UTC))
    ticket.assignee_id = uuid.uuid4()

    app.dependency_overrides[get_db] = _db_override(ticket, None)
    _override_user(cliente)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/reopen",
            json={"reason": "Continua com o mesmo defeito."},
        )

    assert resp.status_code == 200
    assert ticket.status == TicketStatus.in_progress


@pytest.mark.asyncio
async def test_cliente_fora_do_prazo_recebe_o_motivo_da_recusa():
    from app.core.database import get_db

    cliente = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(
        status=TicketStatus.closed, resolved_at=datetime.now(UTC) - timedelta(days=60)
    )

    app.dependency_overrides[get_db] = _db_override(ticket, None)
    _override_user(cliente)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/reopen",
            json={"reason": "Voltou o problema de novo."},
        )

    assert resp.status_code == 409
    assert "prazo" in resp.json()["detail"]
    assert ticket.status == TicketStatus.closed


@pytest.mark.asyncio
async def test_equipe_reabre_mesmo_com_o_prazo_vencido():
    """Encerramento errado da própria equipe não pode virar chamado novo."""
    from app.core.database import get_db

    tecnico = _mock_user(UserRole.technician)
    ticket = _mock_ticket(
        status=TicketStatus.closed, resolved_at=datetime.now(UTC) - timedelta(days=60)
    )

    app.dependency_overrides[get_db] = _db_override(ticket, None)
    _override_user(tecnico)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/reopen",
            json={"reason": "Fechei o chamado errado."},
        )

    assert resp.status_code == 200
    assert ticket.status == TicketStatus.open


@pytest.mark.asyncio
async def test_cliente_nao_reabre_chamado_de_outra_pessoa():
    from app.core.database import get_db

    intruso = _mock_user(UserRole.client)  # id diferente do creator
    ticket = _mock_ticket(status=TicketStatus.closed, resolved_at=datetime.now(UTC))

    app.dependency_overrides[get_db] = _db_override(ticket, None)
    _override_user(intruso)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/reopen",
            json={"reason": "Quero acompanhar este chamado."},
        )

    # 404 e não 403: o 403 confirmava que aquele chamado existe
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_nao_da_para_reabrir_chamado_em_andamento():
    from app.core.database import get_db

    cliente = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(status=TicketStatus.in_progress, resolved_at=None)

    app.dependency_overrides[get_db] = _db_override(ticket, None)
    _override_user(cliente)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/reopen",
            json={"reason": "Só testando o botão."},
        )

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_motivo_muito_curto_e_recusado():
    from app.core.database import get_db

    cliente = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(status=TicketStatus.closed, resolved_at=datetime.now(UTC))

    app.dependency_overrides[get_db] = _db_override(ticket, None)
    _override_user(cliente)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(f"/api/v1/tickets/{_TICKET_ID}/reopen", json={"reason": "oi"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reabertura_dá_um_prazo_de_sla_novo():
    """Sem prazo novo o chamado voltaria já vencido, parado no dia da resolução."""
    from app.core.database import get_db
    from app.models.models import SLALevel

    cliente = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(status=TicketStatus.closed, resolved_at=datetime.now(UTC))

    sla = MagicMock()
    sla.level = SLALevel.medium
    sla.resolve_time_hours = 8
    sla.is_active = True

    app.dependency_overrides[get_db] = _db_override(ticket, sla)
    _override_user(cliente)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/reopen",
            json={"reason": "O defeito voltou ontem à noite."},
        )

    assert resp.status_code == 200
    assert ticket.sla_resolve_breach is False
    assert ticket.sla_resolve_due_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_reabertura_zera_o_tempo_pausado_acumulado():
    """
    O tempo pausado estica o prazo do ciclo em que aconteceu. Como o prazo novo
    já parte de agora, carregá-lo daria ao ciclo reaberto horas de bônus que
    ninguém esperou.
    """
    from app.core.database import get_db
    from app.models.models import SLALevel

    cliente = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(status=TicketStatus.closed, resolved_at=datetime.now(UTC))
    ticket.sla_total_paused_ms = 40 * 60 * 60 * 1000  # 40 h paradas no ciclo anterior

    sla = MagicMock()
    sla.level = SLALevel.medium
    sla.resolve_time_hours = 8
    sla.is_active = True

    app.dependency_overrides[get_db] = _db_override(ticket, sla)
    _override_user(cliente)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/reopen",
            json={"reason": "O problema reapareceu."},
        )

    assert resp.status_code == 200
    assert ticket.sla_total_paused_ms == 0


# ═══════════════════════════════════════════════════════════════
# ORÁCULO DE EXISTÊNCIA NA REABERTURA
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_reabertura_alheia_e_inexistente_respondem_igual():
    """
    Reabrir chamado alheio responde como reabrir chamado que não existe.

    A reabertura é um ponto tentador para enumerar: aceita POST com um id só,
    não precisa de corpo válido para chegar à recusa e o cliente pode chamá-la
    à vontade.
    """
    from app.core.database import get_db

    intruso = _mock_user(UserRole.client)

    async def _resposta(ticket):
        app.dependency_overrides[get_db] = _db_override(ticket, None)
        _override_user(intruso)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                f"/api/v1/tickets/{_TICKET_ID}/reopen",
                json={"reason": "Quero acompanhar este chamado."},
            )
        return r.status_code, r.json()["detail"]

    alheio = await _resposta(
        _mock_ticket(status=TicketStatus.closed, resolved_at=datetime.now(UTC))
    )
    inexistente = await _resposta(None)

    assert alheio == inexistente, f"o cliente distingue os dois casos: {alheio} vs {inexistente}"


@pytest.mark.asyncio
async def test_staff_continua_reabrindo_chamado_de_qualquer_um():
    """Técnico reabre chamado alheio — é o caso de encerramento por engano."""
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket(status=TicketStatus.closed, resolved_at=datetime.now(UTC))
    app.dependency_overrides[get_db] = _db_override(ticket, None)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/reopen",
            json={"reason": "Fechei por engano, desculpe."},
        )

    assert resp.status_code == 200
