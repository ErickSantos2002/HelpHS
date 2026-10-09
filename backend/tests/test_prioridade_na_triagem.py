"""
A prioridade nasce vazia e é definida na triagem.

Regra aprovada em 22/09/2026: o cliente abre o chamado, o chamado nasce **sem
prioridade**, e técnico ou administrador a define depois. O SLA continua
ancorado em `created_at` — ver `docs/superpowers/specs/
2026-09-22-prioridade-definida-na-triagem-design.md`.

Os mocks aqui provam **contrato e autorização**: quem pode chamar, o que sai no
corpo, o que vai para o histórico. O que depende do banco de verdade está fora
deste arquivo, contra Postgres:

- a coluna aceitar NULL, e o chamado antigo manter a prioridade dele, em
  `test_migrations_postgres.py`;
- o balde "Sem prioridade" no painel — a linha `NULL` do `GROUP BY`, que
  nenhum mock produz —, em `test_dashboard_postgres.py`.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import SLALevel, TicketPriority, TicketStatus, UserRole
from app.utils.sla import add_business_minutes
from tests.test_tickets import (
    _db_sequence,
    _mock_ticket,
    _mock_user,
    _override_user,
    patch_redis,  # noqa: F401  (fixture usada pelos testes deste módulo)
)

# ── Auxiliares ────────────────────────────────────────────────

# Uma abertura no passado, em horário comercial de São Paulo (segunda-feira,
# 09:00 BRT = 12:00 UTC). Fixa de propósito: o teste do prazo compara datas, e
# uma abertura "agora" não distinguiria a âncora certa da errada.
_ABERTURA = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def _mock_sla_config(level=SLALevel.critical, resposta=30, resolucao=120):
    c = MagicMock()
    c.id = uuid.uuid4()
    c.level = level
    c.response_time_minutes = resposta
    c.resolve_time_minutes = resolucao
    c.warning_threshold = 80
    c.is_active = True
    return c


def _ticket_sem_prioridade(**kwargs):
    t = _mock_ticket(**kwargs)
    t.priority = None
    t.created_at = _ABERTURA
    t.sla_config_id = None
    return t


def _db_com(ticket, sla_config=None):
    """Sessão que devolve o ticket na 1ª consulta e o SLAConfig na 2ª."""
    session = _db_sequence(ticket, sla_config)

    async def _gen():
        yield session

    return session, _gen


# ═══════════════════════════════════════════════════════════════
# ABERTURA — o chamado nasce sem prioridade
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_chamado_novo_nasce_sem_prioridade(patch_redis):  # noqa: F811
    """Cliente abre sem mandar prioridade: 201 e `priority` nulo no corpo."""
    from app.core.database import get_db

    criador = _mock_user(UserRole.client)
    gravado = {}

    db_session = _db_sequence(None)

    def _add(obj):
        # O que o endpoint montou, antes de qualquer refresh.
        if hasattr(obj, "protocol"):
            gravado["priority"] = obj.priority
            gravado["sla_config_id"] = obj.sla_config_id
            gravado["sla_response_due_at"] = obj.sla_response_due_at
            gravado["sla_resolve_due_at"] = obj.sla_resolve_due_at

    db_session.add = MagicMock(side_effect=_add)

    async def _refresh(obj):
        obj.id = uuid.uuid4()
        obj.protocol = "HS-2026-0001"
        obj.assignee_name = None
        obj.product_name = None
        obj.tags = []

    db_session.refresh = _refresh

    async def _gen():
        yield db_session

    app.dependency_overrides[get_db] = _gen
    _override_user(criador)

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
    assert resp.json()["priority"] is None
    assert gravado["priority"] is None
    # Sem prioridade não há prazo: nada de SLA carimbado na abertura.
    assert gravado["sla_config_id"] is None
    assert gravado["sla_response_due_at"] is None
    assert gravado["sla_resolve_due_at"] is None


def test_o_contrato_de_abertura_nao_tem_campo_de_prioridade():
    """`TicketCreate` não tem `priority` — e `TicketUpdate` também não (D3).

    Asserção sobre o schema, e não sobre a resposta do endpoint, porque as duas
    defesas cobrem o mesmo caminho: o router não escreve `priority` na criação,
    então um teste de POST continua verde mesmo com o campo de volta no
    contrato. Foi o que a mutação mostrou. Quem prova que o campo não existe é
    esta linha.
    """
    from app.schemas.ticket import TicketCreate, TicketUpdate

    assert "priority" not in TicketCreate.model_fields
    assert "priority" not in TicketUpdate.model_fields


@pytest.mark.asyncio
async def test_prioridade_enviada_na_criacao_nao_e_gravada(patch_redis):  # noqa: F811
    """Cliente que monta o POST à mão com `priority` não define a prioridade.

    O pydantic ignora o campo que sobra: a resposta é 201, não 422, e o chamado
    nasce sem prioridade do mesmo jeito. Este teste prova o comportamento do
    endpoint; que o campo não exista no contrato é o teste acima.
    """
    from app.core.database import get_db

    criador = _mock_user(UserRole.client)
    gravado = {}

    db_session = _db_sequence(None)

    def _add(obj):
        if hasattr(obj, "protocol"):
            gravado["priority"] = obj.priority

    db_session.add = MagicMock(side_effect=_add)

    async def _refresh(obj):
        obj.id = uuid.uuid4()
        obj.protocol = "HS-2026-0002"
        obj.assignee_name = None
        obj.product_name = None
        obj.tags = []

    db_session.refresh = _refresh

    async def _gen():
        yield db_session

    app.dependency_overrides[get_db] = _gen
    _override_user(criador)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/tickets",
            json={
                "title": "Quero prioridade crítica",
                "description": "Mandando o campo na unha",
                "category": "hardware",
                "priority": "critical",
            },
        )

    assert resp.status_code == 201
    assert resp.json()["priority"] is None
    assert gravado["priority"] is None


# ═══════════════════════════════════════════════════════════════
# TRIAGEM — quem pode definir
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cliente_nao_pode_definir_prioridade(patch_redis):  # noqa: F811
    """Cliente recebe 403 no endpoint de prioridade."""
    from app.core.database import get_db

    cliente = _mock_user(UserRole.client)
    ticket = _ticket_sem_prioridade(creator_id=cliente.id)
    _, gen = _db_com(ticket)

    app.dependency_overrides[get_db] = gen
    _override_user(cliente)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{ticket.id}/priority",
            json={"priority": "critical"},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("papel", "prioridade"),
    [(UserRole.technician, "critical"), (UserRole.admin, "high")],
)
async def test_staff_define_prioridade(patch_redis, papel, prioridade):  # noqa: F811
    """Técnico e administrador têm exatamente a mesma permissão aqui."""
    from app.core.database import get_db

    ator = _mock_user(papel)
    ticket = _ticket_sem_prioridade()
    nivel = SLALevel.critical if prioridade == "critical" else SLALevel.high
    _, gen = _db_com(ticket, _mock_sla_config(level=nivel))

    app.dependency_overrides[get_db] = gen
    _override_user(ator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{ticket.id}/priority",
            json={"priority": prioridade},
        )

    assert resp.status_code == 200
    assert resp.json()["priority"] == prioridade


@pytest.mark.asyncio
async def test_definir_prioridade_registra_historico(patch_redis):  # noqa: F811
    """A triagem entra no histórico como campo `priority`, saindo de vazio."""
    from app.core.database import get_db
    from app.models.models import TicketHistory

    tecnico = _mock_user(UserRole.technician)
    ticket = _ticket_sem_prioridade()
    session, gen = _db_com(ticket, _mock_sla_config())

    adicionados = []
    session.add = MagicMock(side_effect=adicionados.append)

    app.dependency_overrides[get_db] = gen
    _override_user(tecnico)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{ticket.id}/priority",
            json={"priority": "critical"},
        )

    assert resp.status_code == 200
    historico = [o for o in adicionados if isinstance(o, TicketHistory)]
    assert len(historico) == 1
    assert historico[0].field == "priority"
    assert historico[0].old_value is None
    assert historico[0].new_value == "critical"
    assert historico[0].user_id == tecnico.id


@pytest.mark.asyncio
async def test_troca_de_prioridade_guarda_a_anterior(patch_redis):  # noqa: F811
    """Chamado que já tinha prioridade registra o valor antigo no histórico."""
    from app.core.database import get_db
    from app.models.models import TicketHistory

    admin = _mock_user(UserRole.admin)
    ticket = _ticket_sem_prioridade()
    ticket.priority = TicketPriority.low
    session, gen = _db_com(ticket, _mock_sla_config())

    adicionados = []
    session.add = MagicMock(side_effect=adicionados.append)

    app.dependency_overrides[get_db] = gen
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{ticket.id}/priority",
            json={"priority": "critical"},
        )

    assert resp.status_code == 200
    historico = [o for o in adicionados if isinstance(o, TicketHistory)]
    assert historico[0].old_value == "low"
    assert historico[0].new_value == "critical"


# ═══════════════════════════════════════════════════════════════
# SLA — o prazo conta da abertura, não do clique
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_prazo_conta_da_abertura_e_nao_da_triagem(patch_redis):  # noqa: F811
    """A âncora é `created_at`. Triar na semana seguinte não estica o prazo.

    Este é o teste que a mutação alvo: trocar `ticket.created_at` por `now` na
    chamada do `apply_sla_config` faz as duas asserções caírem.
    """
    from app.core.database import get_db

    tecnico = _mock_user(UserRole.technician)
    ticket = _ticket_sem_prioridade()
    config = _mock_sla_config(resposta=30, resolucao=120)
    _, gen = _db_com(ticket, config)

    app.dependency_overrides[get_db] = gen
    _override_user(tecnico)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{ticket.id}/priority",
            json={"priority": "critical"},
        )

    assert resp.status_code == 200
    assert ticket.sla_config_id == config.id
    assert ticket.sla_response_due_at == add_business_minutes(_ABERTURA, 30)
    assert ticket.sla_resolve_due_at == add_business_minutes(_ABERTURA, 120)
    # E o prazo de um chamado aberto há mais de uma semana está no passado:
    # ele nasce vencido, e é essa a intenção (D1 da proposta de 22/09).
    assert ticket.sla_resolve_due_at < datetime.now(UTC)
    # Vencido E MARCADO, no mesmo instante. Sem esta asserção a promessa do
    # changelog — "a conformidade piora quando a triagem demora" — dependeria
    # de uma escrita alheia qualquer passar pelo chamado para virar verdade.
    assert ticket.sla_resolve_breach is True


@pytest.mark.asyncio
async def test_resposta_dada_antes_da_triagem_nao_vira_violacao(patch_redis):  # noqa: F811
    """Quem respondeu antes de existir prazo não fica devendo primeira resposta.

    O motor já guarda a violação de resposta atrás de `sla_first_response is
    None`; o teste fixa essa leniência como regra (D4), porque ela é o que
    impede um prazo retroativo de acusar quem respondeu no mesmo dia.
    """
    from app.core.database import get_db

    tecnico = _mock_user(UserRole.technician)
    ticket = _ticket_sem_prioridade()
    ticket.sla_first_response = _ABERTURA + timedelta(hours=1)
    _, gen = _db_com(ticket, _mock_sla_config(resposta=30, resolucao=120))

    app.dependency_overrides[get_db] = gen
    _override_user(tecnico)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{ticket.id}/priority",
            json={"priority": "critical"},
        )

    assert resp.status_code == 200
    # O prazo de resposta está no passado e a resposta veio depois dele — e
    # mesmo assim não há violação de resposta.
    assert ticket.sla_response_due_at < ticket.sla_first_response
    assert ticket.sla_response_breach is False


@pytest.mark.asyncio
async def test_prioridade_sem_sla_configurado_nao_quebra(patch_redis):  # noqa: F811
    """Sem `SLAConfig` ativo para o nível, a prioridade grava e o prazo não."""
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _ticket_sem_prioridade()
    _, gen = _db_com(ticket, None)

    app.dependency_overrides[get_db] = gen
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{ticket.id}/priority",
            json={"priority": "low"},
        )

    assert resp.status_code == 200
    assert resp.json()["priority"] == "low"
    assert ticket.sla_resolve_due_at is None


@pytest.mark.asyncio
async def test_prioridade_invalida_e_recusada(patch_redis):  # noqa: F811
    """O endpoint aceita as quatro prioridades, e só elas."""
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _ticket_sem_prioridade()
    _, gen = _db_com(ticket)

    app.dependency_overrides[get_db] = gen
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{ticket.id}/priority",
            json={"priority": "urgentissima"},
        )

    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════
# O CAMINHO GENÉRICO NÃO DEFINE MAIS PRIORIDADE
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_patch_generico_nao_altera_prioridade(patch_redis):  # noqa: F811
    """Nem o admin muda prioridade pelo `PATCH /tickets/{id}`.

    Um caminho só para prioridade (D3): o genérico gravaria o campo sem tocar no
    SLA, e um chamado crítico ficaria com o prazo de quando era baixo.
    """
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket()
    ticket.priority = TicketPriority.low
    _, gen = _db_com(ticket)

    app.dependency_overrides[get_db] = gen
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{ticket.id}",
            json={"title": "Título novo", "priority": "critical"},
        )

    assert resp.status_code == 200
    assert ticket.priority == TicketPriority.low
    assert ticket.title == "Título novo"


@pytest.mark.asyncio
async def test_tecnico_continua_sem_editar_os_outros_campos(patch_redis):  # noqa: F811
    """A permissão nova é só de prioridade: título e categoria seguem fechados."""
    from app.core.database import get_db

    tecnico = _mock_user(UserRole.technician)
    ticket = _mock_ticket(status=TicketStatus.open)
    ticket.title = "Título original"
    _, gen = _db_com(ticket)

    app.dependency_overrides[get_db] = gen
    _override_user(tecnico)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{ticket.id}",
            json={"title": "Título trocado", "technician_notes": "anotação"},
        )

    assert resp.status_code == 200
    assert ticket.title == "Título original"
    assert ticket.technician_notes == "anotação"
