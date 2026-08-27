"""
Tests for Chat REST endpoints (T52 — Sprint 6 integration tests).
WebSocket is tested at the unit level; REST endpoints are fully mocked.
"""

import contextlib
import json
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
_MSG_ID = uuid.uuid4()


# ── Mock builders ─────────────────────────────────────────────


def _mock_user(role=UserRole.technician, user_id=None):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.name = f"{role.value}_user"
    u.email = f"{role.value}@test.com"
    u.role = role
    u.status = UserStatus.active
    return u


def _mock_ticket(creator_id=None):
    t = MagicMock()
    t.id = _TICKET_ID
    t.protocol = "HS-2026-0001"
    t.title = "Falha no bafômetro"
    t.description = "Dispositivo não inicializa"
    t.status = TicketStatus.open
    t.priority = TicketPriority.medium
    t.category = TicketCategory.hardware
    t.creator_id = creator_id or _CREATOR_ID
    t.assignee_id = _TECH_ID
    t.ai_conversation_summary = None
    t.updated_at = _NOW
    t.sla_response_due_at = None
    t.sla_first_response = None
    t.sla_paused_at = None
    t.sla_total_paused_ms = 0
    t.sla_response_breach = False
    t.sla_resolve_breach = False
    return t


def _mock_message(sender=None):
    msg = MagicMock()
    msg.id = _MSG_ID
    msg.ticket_id = _TICKET_ID
    msg.sender_id = _TECH_ID
    msg.content = "Olá, vou analisar o problema."
    msg.is_system = False
    msg.is_ai = False
    msg.read_at = None
    msg.created_at = _NOW
    msg.sender = sender or _mock_user()
    return msg


# ── DB helpers ────────────────────────────────────────────────


def _db_sequence(*responses):
    call_count = [0]

    async def _execute(*args, **kwargs):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        resp = responses[idx]

        result = MagicMock()
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
            result.scalar_one.return_value = resp
            result.scalars.return_value.all.return_value = [resp] if resp else []
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _db_seq_override(*responses):
    session = _db_sequence(*responses)

    async def _gen():
        yield session

    return _gen


# ── Fixtures ──────────────────────────────────────────────────


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
# LIST MESSAGES
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_messages_returns_history(patch_redis):
    """GET /tickets/{id}/messages returns paginated message list."""
    tech = _mock_user(UserRole.technician, _TECH_ID)
    ticket = _mock_ticket()
    msg = _mock_message(sender=tech)

    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, 1, [msg])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/tickets/{_TICKET_ID}/messages")

    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["content"] == msg.content


@pytest.mark.asyncio
async def test_tecnico_nao_atribuido_envia_mensagem(patch_redis):
    """Qualquer técnico atende no chat, mesmo sem ser o responsável."""
    outro_tecnico = uuid.uuid4()
    tech = _mock_user(UserRole.technician, outro_tecnico)
    ticket = _mock_ticket()  # assignee_id = _TECH_ID (outra pessoa)
    msg = _mock_message(sender=tech)

    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, msg, msg)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            f"/api/v1/tickets/{_TICKET_ID}/messages",
            json={"content": "Bom dia, vou dar andamento neste chamado."},
        )

    assert r.status_code == 201


@pytest.mark.asyncio
async def test_list_messages_client_own_ticket(patch_redis):
    """Client can list messages for their own ticket."""
    client_user = _mock_user(UserRole.client, _CREATOR_ID)
    ticket = _mock_ticket(creator_id=_CREATOR_ID)
    msg = _mock_message(sender=client_user)

    _override_user(client_user)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, 1, [msg])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/tickets/{_TICKET_ID}/messages")

    assert r.status_code == 200


@pytest.mark.asyncio
async def test_list_messages_client_other_ticket_forbidden(patch_redis):
    """Client cannot list messages for another user's ticket."""
    other_id = uuid.uuid4()
    client_user = _mock_user(UserRole.client, other_id)
    ticket = _mock_ticket(creator_id=_CREATOR_ID)  # owned by CREATOR_ID

    _override_user(client_user)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/tickets/{_TICKET_ID}/messages")

    # 404 e não 403: o 403 confirmava que aquele chamado existe
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_messages_ticket_not_found(patch_redis):
    """Returns 404 when ticket does not exist."""
    tech = _mock_user(UserRole.technician)
    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/tickets/{uuid.uuid4()}/messages")

    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# CREATE MESSAGE
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_message_technician(patch_redis):
    """Technician can post a message to a ticket."""
    tech = _mock_user(UserRole.technician, _TECH_ID)
    ticket = _mock_ticket()
    msg = _mock_message(sender=tech)

    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, msg)

    with patch("app.routers.chat.notify", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                f"/api/v1/tickets/{_TICKET_ID}/messages",
                json={"content": "Olá, vou analisar o problema."},
            )

    assert r.status_code == 201
    assert r.json()["content"] == msg.content


@pytest.mark.asyncio
async def test_create_message_empty_content_rejected(patch_redis):
    """Empty content should be rejected (422)."""
    tech = _mock_user(UserRole.technician, _TECH_ID)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            f"/api/v1/tickets/{_TICKET_ID}/messages",
            json={"content": ""},
        )

    assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════
# SUGGEST REPLY
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_suggest_reply_returns_suggestion(patch_redis):
    """POST /tickets/{id}/suggest-reply returns an AI suggestion."""
    tech = _mock_user(UserRole.technician, _TECH_ID)
    ticket = _mock_ticket()
    msg = _mock_message(sender=tech)

    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, [msg])

    with patch(
        "app.routers.chat.suggest_reply",
        new=AsyncMock(return_value="Prezado solicitante, identificamos o problema."),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(f"/api/v1/tickets/{_TICKET_ID}/suggest-reply")

    assert r.status_code == 200
    assert "suggestion" in r.json()
    assert len(r.json()["suggestion"]) > 0


@pytest.mark.asyncio
async def test_suggest_reply_llm_unavailable_returns_503(patch_redis):
    """Returns 503 when LLM returns None."""
    tech = _mock_user(UserRole.technician, _TECH_ID)
    ticket = _mock_ticket()
    msg = _mock_message(sender=tech)

    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, [msg])

    with patch("app.routers.chat.suggest_reply", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(f"/api/v1/tickets/{_TICKET_ID}/suggest-reply")

    assert r.status_code == 503


@pytest.mark.asyncio
async def test_suggest_reply_client_forbidden(patch_redis):
    """Clients cannot access suggest-reply (403)."""
    client_user = _mock_user(UserRole.client, _CREATOR_ID)
    _override_user(client_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(f"/api/v1/tickets/{_TICKET_ID}/suggest-reply")

    assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════
# SUMMARIZE CONVERSATION
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_summarize_returns_summary(patch_redis):
    """POST /tickets/{id}/summarize returns and persists a summary."""
    tech = _mock_user(UserRole.technician, _TECH_ID)
    ticket = _mock_ticket()
    msg = _mock_message(sender=tech)

    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, [msg])

    with patch(
        "app.routers.chat.summarize_conversation",
        new=AsyncMock(return_value="O técnico identificou falha no hardware do bafômetro."),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(f"/api/v1/tickets/{_TICKET_ID}/summarize")

    assert r.status_code == 200
    assert "summary" in r.json()


@pytest.mark.asyncio
async def test_summarize_no_messages_returns_422(patch_redis):
    """Returns 422 when there are no messages to summarize."""
    tech = _mock_user(UserRole.technician, _TECH_ID)
    ticket = _mock_ticket()

    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, [])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(f"/api/v1/tickets/{_TICKET_ID}/summarize")

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_summarize_client_forbidden(patch_redis):
    """Clients cannot access summarize (403)."""
    client_user = _mock_user(UserRole.client, _CREATOR_ID)
    _override_user(client_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(f"/api/v1/tickets/{_TICKET_ID}/summarize")

    assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════
# PRIMEIRA RESPOSTA DO SLA
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_mensagem_do_tecnico_marca_primeira_resposta(patch_redis):
    """Responder pelo chat é o que registra a primeira resposta do SLA."""
    tech = _mock_user(UserRole.technician, _TECH_ID)
    ticket = _mock_ticket()
    msg = _mock_message(sender=tech)

    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, msg)

    with patch("app.routers.chat.notify", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                f"/api/v1/tickets/{_TICKET_ID}/messages",
                json={"content": "Bom dia, já estou olhando o equipamento."},
            )

    assert r.status_code == 201
    assert ticket.sla_first_response is not None


@pytest.mark.asyncio
async def test_mensagem_do_autor_nao_marca_primeira_resposta(patch_redis):
    """O cliente escrevendo no próprio chamado não responde a si mesmo."""
    autor = _mock_user(UserRole.client, _CREATOR_ID)
    ticket = _mock_ticket(creator_id=_CREATOR_ID)
    msg = _mock_message(sender=autor)

    _override_user(autor)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, msg)

    with patch("app.routers.chat.notify", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                f"/api/v1/tickets/{_TICKET_ID}/messages",
                json={"content": "O aparelho continua sem ligar."},
            )

    assert r.status_code == 201
    assert ticket.sla_first_response is None


# ═══════════════════════════════════════════════════════════════
# ORÁCULO DE EXISTÊNCIA — o chat, inclusive no WebSocket
# ═══════════════════════════════════════════════════════════════
#
# O 403 de chamado alheio confirmava que aquele id existe. No REST isso sai
# como status; no WebSocket sai como CÓDIGO DE FECHAMENTO — 4003 contra 4004 —
# que é o mesmo vazamento numa roupa que varredura de status HTTP não enxerga.


@pytest.mark.asyncio
async def test_create_message_client_other_ticket_404(patch_redis):
    """Mandar mensagem em chamado alheio responde como chamado inexistente."""
    from app.core.database import get_db

    client_user = _mock_user(UserRole.client)
    ticket = _mock_ticket(creator_id=_CREATOR_ID)

    _override_user(client_user)
    app.dependency_overrides[get_db] = _db_seq_override(ticket)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            f"/api/v1/tickets/{_TICKET_ID}/messages",
            json={"content": "oi"},
        )

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_chat_alheio_e_inexistente_respondem_igual(patch_redis):
    """
    Alheio e inexistente devolvem status E texto idênticos.

    Só o status não basta: dois 404 com mensagens diferentes continuam
    separando "não é seu" de "não existe".
    """
    from app.core.database import get_db

    client_user = _mock_user(UserRole.client)

    async def _resposta(ticket):
        _override_user(client_user)
        app.dependency_overrides[get_db] = _db_seq_override(ticket)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get(f"/api/v1/tickets/{_TICKET_ID}/messages")
        return r.status_code, r.json()["detail"]

    alheio = await _resposta(_mock_ticket(creator_id=_CREATOR_ID))
    inexistente = await _resposta(None)

    assert alheio == inexistente, f"o cliente distingue os dois casos: {alheio} vs {inexistente}"


def _ws_close_code(user, ticket):
    """
    Abre o WS com um usuário e um ticket fixos e devolve (código, motivo).

    O handler do WS não usa a dependência `get_db` — abre `AsyncSessionLocal`
    na mão —, então o mock é do session maker e da autenticação por token.
    """
    from starlette.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    session = AsyncMock()

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = ticket
        return result

    session.execute = _execute

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return False

    async def _auth(token, db):
        return user

    with (
        patch("app.routers.chat.AsyncSessionLocal", lambda: _Ctx()),
        patch("app.routers.chat._authenticate_ws", _auth),
    ):
        # Sem `with TestClient(app)`: o lifespan da app abre conexão real com o
        # Postgres, e o que está sob teste é o handler, não a subida.
        tc = TestClient(app)
        try:
            with tc.websocket_connect(f"/api/v1/ws/tickets/{_TICKET_ID}?token=x"):
                return None, None
        except WebSocketDisconnect as exc:
            return exc.code, exc.reason


def test_ws_chamado_alheio_fecha_como_chamado_inexistente():
    """
    Cliente em chamado alheio recebe o MESMO fechamento de um id que não existe.

    O 4003 ("Forbidden") dizia que o chamado existe; quem tivesse a lista de
    ids enumerava o sistema pelo WebSocket sem nunca receber um HTTP 403.
    """
    client_user = _mock_user(UserRole.client)

    alheio = _ws_close_code(client_user, _mock_ticket(creator_id=_CREATOR_ID))
    inexistente = _ws_close_code(client_user, None)

    assert alheio == inexistente, f"o WS distingue os dois casos: {alheio} vs {inexistente}"
    assert alheio[0] == 4004


def test_ws_dono_do_chamado_continua_entrando():
    """A correção não pode fechar o chat de quem tem direito a ele."""
    dono = _mock_user(UserRole.client, user_id=_CREATOR_ID)

    codigo, _ = _ws_close_code(dono, _mock_ticket(creator_id=_CREATOR_ID))

    assert codigo is None, "o autor do chamado foi barrado do próprio chat"


def test_ws_staff_continua_entrando():
    """Técnico entra em qualquer chat — é o trabalho dele."""
    tech = _mock_user(UserRole.technician)

    codigo, _ = _ws_close_code(tech, _mock_ticket(creator_id=_CREATOR_ID))

    assert codigo is None


# ── Helô: remetente nulo ──────────────────────────────────────


def test_mensagem_da_ia_sem_remetente_vira_resposta_valida():
    """
    A fala da Helô não tem gente do outro lado: `sender_id` é nulo.

    Enquanto o campo era obrigatório no `ChatMessageResponse`, a primeira
    mensagem dela derrubaria o GET de mensagens do chamado com
    ValidationError — um 500 para todo mundo que abrisse aquele chat, não só
    para quem falou com ela. Era o 🔴 #2 da revisão técnica da Fase 1.
    """
    from app.routers.chat import _msg_to_response

    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.ticket_id = uuid.uuid4()
    msg.sender_id = None
    msg.sender = None
    msg.content = "Olá! Sou a Helô, assistente da Health & Safety."
    msg.is_system = False
    msg.is_ai = True
    msg.read_at = None
    msg.created_at = datetime.now(UTC)

    resposta = _msg_to_response(msg)

    assert resposta.sender_id is None
    assert resposta.is_ai is True
    # Vazio, não "Sistema" nem "Helô": o nome que a bolha mostra é decisão da
    # tela, e o back inventar um texto aqui tiraria essa escolha dela.
    assert resposta.sender_name == ""
    assert resposta.sender_role == ""


def test_mensagem_de_gente_continua_trazendo_o_remetente():
    """O nulo é exceção, não o novo normal — o caminho comum não mudou."""
    from app.routers.chat import _msg_to_response

    autor = MagicMock()
    autor.name = "Suelen"
    autor.role = UserRole.client

    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.ticket_id = uuid.uuid4()
    msg.sender_id = uuid.uuid4()
    msg.sender = autor
    msg.content = "O aparelho não liga."
    msg.is_system = False
    msg.is_ai = False
    msg.read_at = None
    msg.created_at = datetime.now(UTC)

    resposta = _msg_to_response(msg)

    assert resposta.sender_id == msg.sender_id
    assert resposta.sender_name == "Suelen"
    assert resposta.sender_role == "client"


# ── Token revogado não abre WebSocket ─────────────────────────


@pytest.mark.asyncio
async def test_token_na_blacklist_nao_abre_websocket():
    """Logout derrubava o HTTP e deixava o WebSocket aberto.

    `_authenticate_ws` conferia assinatura, tipo e status da conta, mas não a
    blacklist — que é justamente onde o logout escreve. Um token revogado
    continuava abrindo chat até vencer sozinho, o que pode ser oito horas
    depois de a pessoa ter saído.
    """
    from app.core.security import create_access_token
    from app.routers.chat import _authenticate_ws

    user = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    token = create_access_token(user.id, user.role.value, "quem@quer.com")

    sessao = AsyncMock()

    async def _execute(*a, **k):
        r = MagicMock()
        r.scalar_one_or_none.return_value = user
        return r

    sessao.execute = _execute

    class _RedisComToken:
        async def exists(self, chave):
            return 1 if token in chave else 0

    async def _redis():
        return _RedisComToken()

    with patch("app.core.security.get_redis", new=_redis):
        assert await _authenticate_ws(token, sessao) is None


@pytest.mark.asyncio
async def test_token_valido_continua_abrindo_websocket():
    """A defesa não pode fechar a porta de quem não foi revogado."""
    from app.core.security import create_access_token
    from app.routers.chat import _authenticate_ws

    user = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    token = create_access_token(user.id, user.role.value, "quem@quer.com")

    sessao = AsyncMock()

    async def _execute(*a, **k):
        r = MagicMock()
        r.scalar_one_or_none.return_value = user
        return r

    sessao.execute = _execute

    class _RedisVazio:
        async def exists(self, chave):
            return 0

    async def _redis():
        return _RedisVazio()

    with patch("app.core.security.get_redis", new=_redis):
        assert await _authenticate_ws(token, sessao) is user


# ── Tamanho da mensagem ───────────────────────────────────────


def test_o_limite_de_tamanho_existe_no_schema():
    """Nenhum dos dois caminhos limitava tamanho, e a coluna é `Text`.

    O REST validava só `min_length=1`; o WebSocket nem schema usava. Um cliente
    autenticado podia gravar uma mensagem de megabytes.
    """
    from app.schemas.chat import LIMITE_CONTEUDO, ChatMessageCreate

    with pytest.raises(ValueError):
        ChatMessageCreate(content="x" * (LIMITE_CONTEUDO + 1))

    # E o limite não pode ser apertado a ponto de estorvar o uso real: técnico
    # cola log e mensagem de erro no chat o tempo todo.
    assert LIMITE_CONTEUDO >= 10_000
    assert ChatMessageCreate(content="x" * LIMITE_CONTEUDO).content


def test_o_websocket_recusa_mensagem_grande_sem_gravar():
    """O WS grava `content` cru — se o limite ficar só no schema REST, o
    caminho mais fácil de abusar é o que não valida."""
    from starlette.testclient import TestClient

    from app.schemas.chat import LIMITE_CONTEUDO

    user = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(creator_id=_CREATOR_ID)
    gravadas = []

    sessao = AsyncMock()

    async def _execute(*a, **k):
        r = MagicMock()
        r.scalar_one_or_none.return_value = ticket
        return r

    sessao.execute = _execute
    sessao.add = lambda o: gravadas.append(o)

    class _Ctx:
        async def __aenter__(self):
            return sessao

        async def __aexit__(self, *a):
            return False

    async def _auth(token, db):
        return user

    with (
        patch("app.routers.chat.AsyncSessionLocal", lambda: _Ctx()),
        patch("app.routers.chat._authenticate_ws", _auth),
    ):
        tc = TestClient(app)
        with tc.websocket_connect(f"/api/v1/ws/tickets/{_TICKET_ID}?token=x") as ws:
            ws.send_text(json.dumps({"content": "x" * (LIMITE_CONTEUDO + 1)}))
            resposta = ws.receive_json()

    assert resposta["type"] == "error"
    assert gravadas == [], "a mensagem grande foi gravada mesmo assim"


# ── IA desligada responde diferente de IA quebrada ────────────
#
# Os tres endpoints devolviam o MESMO 503 "tente novamente mais tarde" nos dois
# casos. Com a flag desligada, retentar nao ajuda nunca — e quem opera o sistema
# nao tinha como distinguir "provedor fora do ar" de "alguem desligou".
#
# A guarda tambem roda ANTES de qualquer consulta: com a IA desligada, carregar
# chamado e mensagens do banco e trabalho jogado fora.


@contextlib.contextmanager
def _ia_desligada():
    from app.core.config import get_settings

    s = get_settings()
    antes = s.llm_enabled
    s.llm_enabled = False
    try:
        yield
    finally:
        s.llm_enabled = antes


_ROTAS_DE_IA = [
    ("suggest-reply", {}),
    ("improve-message", {"draft": "rascunho qualquer"}),
    ("summarize", {}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("rota,corpo", _ROTAS_DE_IA)
async def test_com_a_ia_desligada_a_mensagem_diz_que_esta_desligada(patch_redis, rota, corpo):
    _override_user(_mock_user(UserRole.technician, _TECH_ID))
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(_mock_ticket(), [])

    with _ia_desligada():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(f"/api/v1/tickets/{_TICKET_ID}/{rota}", json=corpo)

    assert r.status_code == 503
    detalhe = r.json()["detail"].lower()
    assert "desligad" in detalhe, detalhe
    assert "mais tarde" not in detalhe, "manda esperar por algo que nao volta sozinho"


@pytest.mark.asyncio
@pytest.mark.parametrize("rota,corpo", _ROTAS_DE_IA)
async def test_com_a_ia_desligada_o_banco_nem_e_consultado(patch_redis, rota, corpo):
    """A guarda roda antes de tudo — nao ha por que carregar o chamado."""
    _override_user(_mock_user(UserRole.technician, _TECH_ID))
    from app.core.database import get_db

    consultas = []

    def _db_espiao():
        sessao = AsyncMock()

        async def _execute(*a, **k):
            consultas.append(1)
            resultado = MagicMock()
            resultado.scalar_one_or_none.return_value = _mock_ticket()
            return resultado

        sessao.execute = _execute

        async def _gen():
            yield sessao

        return _gen

    app.dependency_overrides[get_db] = _db_espiao()

    with _ia_desligada():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(f"/api/v1/tickets/{_TICKET_ID}/{rota}", json=corpo)

    assert consultas == [], f"{len(consultas)} consultas com a IA desligada"


# ── improve-message: o endpoint que nao tinha teste nenhum ────
#
# E o unico que manda para fora texto que o tecnico AINDA NAO PUBLICOU.


@pytest.mark.asyncio
async def test_improve_message_devolve_o_texto_melhorado(patch_redis):
    _override_user(_mock_user(UserRole.technician, _TECH_ID))
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(_mock_ticket(), [])

    with patch(
        "app.routers.chat.improve_message",
        new=AsyncMock(return_value="Prezado cliente, o equipamento foi calibrado."),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                f"/api/v1/tickets/{_TICKET_ID}/improve-message",
                json={"draft": "calibrei o aparelho"},
            )

    assert r.status_code == 200
    assert r.json()["improved"].startswith("Prezado")


@pytest.mark.asyncio
async def test_improve_message_com_provedor_fora_responde_503(patch_redis):
    _override_user(_mock_user(UserRole.technician, _TECH_ID))
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(_mock_ticket(), [])

    with patch("app.routers.chat.improve_message", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                f"/api/v1/tickets/{_TICKET_ID}/improve-message",
                json={"draft": "calibrei o aparelho"},
            )

    assert r.status_code == 503
    # A mensagem de provedor fora do ar CONTINUA mandando tentar de novo — aqui
    # tentar de novo e exatamente a coisa certa a fazer.
    assert "mais tarde" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_improve_message_e_do_staff(patch_redis):
    """Cliente nao usa o assistente de redacao do tecnico."""
    _override_user(_mock_user(UserRole.client, _CREATOR_ID))
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(_mock_ticket(), [])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(f"/api/v1/tickets/{_TICKET_ID}/improve-message", json={"draft": "oi"})

    assert r.status_code == 403


@pytest.mark.asyncio
async def test_ia_desligada_no_chamado_recusa_a_sugestao(patch_redis):
    """
    O botão diz "Desligar IA neste chamado" e precisa desligar mesmo.

    Antes disto ele calava só a Helô: sugestão de resposta, resumo e
    classificação seguiam mandando o texto do cliente para a OpenAI depois de
    alguém ter pedido para não mandar. A promessa da tela era maior que a do
    código.

    409 e não 403: não é falta de permissão, é um estado do chamado que a
    própria equipe escolheu e desfaz no mesmo botão.
    """
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket()
    ticket.ai_enabled = False

    app.dependency_overrides[get_db] = _db_seq_override(ticket)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(f"/api/v1/tickets/{_TICKET_ID}/suggest-reply")

    assert resp.status_code == 409, resp.text
    assert "desligada neste chamado" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_ia_desligada_nao_impede_gente_de_conversar(patch_redis):
    """
    O interruptor é da IA, não do chat.

    Desligar a IA num chamado não pode calar o técnico e o cliente — seria
    transformar um botão de "sem robô" num "sem atendimento".
    """
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket()
    ticket.ai_enabled = False

    app.dependency_overrides[get_db] = _db_seq_override(ticket, _mock_message())
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/messages",
            json={"content": "Bom dia, já estou olhando seu chamado."},
        )

    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_cliente_respondendo_chamado_sem_dono_nao_vai_para_ag_tecnico(patch_redis):
    """
    "Aguardando técnico" exige um técnico esperando por ele.

    Antes da Helô esse caso quase não existia — o cliente raramente escrevia
    antes de alguém falar com ele. Agora ele responde a triagem em segundos, e
    todo chamado triado caía num estado que anuncia um atendimento que não
    começou. E pior: aquele estado PAUSA o relógio do SLA, justamente enquanto
    o cliente espera um humano.
    """
    from app.core.database import get_db

    cliente = _mock_user(UserRole.client)
    ticket = _mock_ticket(creator_id=cliente.id)
    ticket.status = TicketStatus.in_progress
    ticket.assignee_id = None

    app.dependency_overrides[get_db] = _db_seq_override(ticket, _mock_message())
    _override_user(cliente)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/messages",
            json={"content": "O aparelho não liga desde ontem"},
        )

    assert resp.status_code == 201, resp.text
    assert ticket.status is TicketStatus.in_progress


@pytest.mark.asyncio
async def test_cliente_respondendo_chamado_com_dono_vai_para_ag_tecnico(patch_redis):
    """Com responsável, a transição continua: há alguém de quem se espera resposta."""
    from app.core.database import get_db

    cliente = _mock_user(UserRole.client)
    tecnico = _mock_user(UserRole.technician)
    ticket = _mock_ticket(creator_id=cliente.id)
    ticket.status = TicketStatus.in_progress
    ticket.assignee_id = tecnico.id
    # A transição passa pelo check_breaches, que compara prazos: com MagicMock
    # nesses campos a comparação estoura antes de o teste chegar ao que importa.
    ticket.sla_response_due_at = None
    ticket.sla_resolve_due_at = None
    ticket.sla_first_response = None
    ticket.sla_paused_at = None
    ticket.sla_total_paused_ms = 0

    app.dependency_overrides[get_db] = _db_seq_override(ticket, _mock_message())
    _override_user(cliente)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/messages",
            json={"content": "continua sem ligar"},
        )

    assert resp.status_code == 201, resp.text
    assert ticket.status is TicketStatus.awaiting_technical
