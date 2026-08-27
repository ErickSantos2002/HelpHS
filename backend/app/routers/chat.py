"""
Chat em tempo real para tickets.

Endpoints REST:
  GET  /tickets/{ticket_id}/messages          — histórico paginado
  POST /tickets/{ticket_id}/messages          — criar mensagem (staff/sistema)
  POST /tickets/{ticket_id}/suggest-reply     — sugestão de resposta por IA (staff only)

WebSocket:
  WS   /ws/tickets/{ticket_id}?token=<jwt>    — canal de tempo real

Permissões:
  - Qualquer usuário autenticado com acesso ao ticket pode participar.
  - Acesso = requester do ticket OU qualquer admin/técnico.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.security import _is_blacklisted, authorize, decode_token, get_current_user
from app.models.models import (
    ChatMessage,
    NotificationType,
    Ticket,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
)
from app.routers.tickets import _auto_transition
from app.schemas.chat import (
    LIMITE_CONTEUDO,
    ChatMessageCreate,
    ChatMessageListResponse,
    ChatMessageResponse,
    ConversationSummaryResponse,
    ImproveMessageRequest,
    ImproveMessageResponse,
    SuggestReplyResponse,
)
from app.services import chat_backplane
from app.services.helo import responde_triagem
from app.services.llm import improve_message, suggest_reply, summarize_conversation
from app.services.notifications import commit_e_notificar, notify
from app.utils.sla import register_first_response
from app.utils.ticket_access import ensure_ticket_visible

router = APIRouter(tags=["Chat"])
settings = get_settings()

# Mesmo texto do 404 de id inexistente — ver `ensure_ticket_visible`. Vale
# também para o WebSocket, onde o vazamento sai como código de fechamento.
_CHAMADO_NAO_ENCONTRADO = "Ticket não encontrado. Ele pode ter sido excluído."


# ── ConnectionManager ─────────────────────────────────────────


class ConnectionManager:
    """Salas de WebSocket na memória DESTE processo, por chamado.

    A `origem` identifica este manager no backplane, e é atributo de
    **instância** — não global de módulo. Com um global, dois managers do mesmo
    processo dividiriam o carimbo, a supressão de eco descartaria a mensagem que
    deveria atravessar, e o backplane ficaria intestável exatamente na
    propriedade que o justifica.
    """

    def __init__(self) -> None:
        # ticket_id (str) → set of active WebSocket connections
        self._rooms: dict[str, set[WebSocket]] = {}
        self.origem = uuid.uuid4().hex[:12]

    def connect(self, ticket_id: str, ws: WebSocket) -> None:
        self._rooms.setdefault(ticket_id, set()).add(ws)

    def disconnect(self, ticket_id: str, ws: WebSocket) -> None:
        room = self._rooms.get(ticket_id)
        if room:
            room.discard(ws)
            if not room:
                del self._rooms[ticket_id]

    async def entregar_local(self, ticket_id: str, payload: dict) -> None:
        """Entrega aos sockets deste processo, e só a eles.

        É também o que o backplane chama ao receber mensagem de outro worker —
        por isso é público e recebe o `ticket_id` como string: o assinante não
        sabe o que é uma sala, só repassa o que chegou.
        """
        room = self._rooms.get(ticket_id, set())
        dead: list[WebSocket] = []
        for ws in list(room):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            room.discard(ws)

    async def broadcast(self, ticket_id: str, payload: dict) -> None:
        """Entrega local PRIMEIRO, publica depois.

        A ordem não é estética: publicar antes faria a latência do Redis atrasar
        o socket que está no mesmo processo — o caso mais comum, ainda mais com
        um worker só. E `publicar` nunca levanta, então o Redis fora do ar deixa
        o chat exatamente como ele é hoje, que é sem Redis nenhum.
        """
        await self.entregar_local(ticket_id, payload)
        await chat_backplane.publicar(self.origem, ticket_id, payload)


manager = ConnectionManager()


# ── Helpers ───────────────────────────────────────────────────


def _msg_to_response(msg: ChatMessage) -> ChatMessageResponse:
    sender = msg.sender
    return ChatMessageResponse(
        id=msg.id,
        ticket_id=msg.ticket_id,
        sender_id=msg.sender_id,
        content=msg.content,
        is_system=msg.is_system,
        is_ai=msg.is_ai,
        read_at=msg.read_at,
        created_at=msg.created_at,
        sender_name=sender.name if sender else "",
        sender_role=sender.role.value if sender else "",
    )


async def _get_ticket_visivel(
    ticket_id: uuid.UUID,
    actor: User,
    db: AsyncSession,
) -> Ticket:
    """
    Devolve o chamado se o ator puder vê-lo; senão, 404.

    Chamado alheio responde igual a id inexistente — o 403 anterior confirmava
    a existência. Staff passa direto porque já lê o sistema inteiro.
    """
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_CHAMADO_NAO_ENCONTRADO,
        )

    if actor.role not in (UserRole.admin, UserRole.technician):
        ensure_ticket_visible(ticket, actor, _CHAMADO_NAO_ENCONTRADO)

    return ticket


async def _authenticate_ws(token: str, db: AsyncSession) -> User | None:
    """Valida o token vindo do query param do WebSocket.

    Confere a blacklist, como o `get_current_user` do caminho HTTP. Sem isso o
    logout derrubava a sessão HTTP e deixava o WebSocket aberto: o token
    revogado continuava valendo aqui até vencer sozinho — até oito horas depois
    de a pessoa ter saído.
    """
    try:
        payload = decode_token(token)
    except JWTError:
        return None

    if payload.get("type") != "access":
        return None

    if await _is_blacklisted(token):
        return None

    user_id_str = payload.get("sub")
    if not user_id_str:
        return None

    try:
        uid = uuid.UUID(user_id_str)
    except ValueError:
        return None

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user is None or user.status != UserStatus.active:
        return None
    return user


def _exige_ia_no_chamado(ticket: Ticket) -> None:
    """
    Recusa quando a IA foi desligada NESTE chamado.

    O guard acima é a chave geral; este é o botão do técnico. Sem ele, "Desligar
    IA neste chamado" calaria só a Helô e deixaria a sugestão de resposta e o
    resumo funcionando — a promessa da tela maior que a do código, que é
    exatamente o que o rótulo do botão não pode fazer.

    Não é dependência como o outro porque precisa do chamado carregado: só dá
    para saber depois de ler o banco, e o 404 de chamado alheio tem precedência.

    409, e não 403: não é falta de permissão, é um estado do chamado que alguém
    da equipe escolheu e qualquer um deles pode desfazer no mesmo botão.
    """
    if not ticket.ai_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A IA está desligada neste chamado.",
        )


def _exige_ia_ligada() -> None:
    """Recusa a chamada quando a IA está desligada — antes de tocar no banco.

    A mensagem é **diferente** da de provedor fora do ar, de propósito. Os três
    endpoints devolviam o mesmo "tente novamente mais tarde" nos dois casos, e
    com a flag desligada isso manda esperar por algo que não volta sozinho. Quem
    opera precisa distinguir "o provedor caiu" de "alguém desligou".

    Sendo dependência, roda antes do corpo do handler: com a IA desligada não há
    por que carregar chamado e mensagens do banco para no fim recusar.

    Lê a configuração na chamada, não no import — o `llm.py` faz o contrário, e
    por isso lá a flag só tem efeito depois de reiniciar o contêiner.
    """
    if not get_settings().llm_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O assistente de IA está desligado neste ambiente.",
        )


# ── REST endpoints ────────────────────────────────────────────


@router.get("/tickets/{ticket_id}/messages", response_model=ChatMessageListResponse)
async def list_messages(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ChatMessageListResponse:
    await _get_ticket_visivel(ticket_id, actor, db)

    total_result = await db.execute(select(func.count()).where(ChatMessage.ticket_id == ticket_id))
    total = total_result.scalar_one()

    rows = await db.execute(
        select(ChatMessage)
        .options(selectinload(ChatMessage.sender))
        .where(ChatMessage.ticket_id == ticket_id)
        .order_by(ChatMessage.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    messages = rows.scalars().all()

    return ChatMessageListResponse(
        items=[_msg_to_response(m) for m in messages],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    ticket_id: uuid.UUID,
    payload: ChatMessageCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> ChatMessageResponse:
    ticket = await _get_ticket_visivel(ticket_id, actor, db)

    now = datetime.now(UTC)
    msg = ChatMessage(
        id=uuid.uuid4(),
        ticket_id=ticket_id,
        sender_id=actor.id,
        content=payload.content.strip(),
        is_system=False,
        is_ai=False,
        created_at=now,
    )
    db.add(msg)

    # SLA: falar com o cliente é o que conta como primeira resposta
    register_first_response(
        ticket, now, responder_id=actor.id, is_ai=msg.is_ai, is_system=msg.is_system
    )

    # A Helô encerra a triagem quando o cliente responde. ANTES da notificação
    # de propósito: é ela quem decide se a equipe precisa ser chamada, e a
    # triagem recém-fechada é justamente o momento em que o chamado passa a ter
    # conteúdo útil e ainda não tem dono.
    encerrou_triagem = False
    if actor.id == ticket.creator_id:
        encerrou_triagem = await responde_triagem(db, ticket, actor, msg.content) is not None

    # Notify the other party
    await _notify_other_party(db, ticket, actor, msg)

    if encerrou_triagem:
        await _avisa_equipe_da_triagem(db, ticket)

    # Auto status transition based on who is sending
    new_status_value = await _apply_chat_transition(db, ticket, actor)

    await commit_e_notificar(db)

    # Reload with sender using selectinload
    result = await db.execute(
        select(ChatMessage)
        .options(selectinload(ChatMessage.sender))
        .where(ChatMessage.id == msg.id)
    )
    msg = result.scalar_one()

    response = _msg_to_response(msg)

    # Broadcast message
    await manager.broadcast(
        str(ticket_id),
        {"type": "message", "data": _response_to_dict(response)},
    )

    # Broadcast status change if a transition occurred
    if new_status_value:
        await manager.broadcast(
            str(ticket_id),
            {"type": "status_update", "data": {"status": new_status_value}},
        )

    return response


@router.post(
    "/tickets/{ticket_id}/suggest-reply",
    response_model=SuggestReplyResponse,
    dependencies=[Depends(_exige_ia_ligada)],
)
async def suggest_ticket_reply(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> SuggestReplyResponse:
    """Generate an AI-suggested reply for a technician based on ticket and chat history."""
    ticket = await _get_ticket_visivel(ticket_id, actor, db)
    _exige_ia_no_chamado(ticket)

    # Load last 10 messages with sender info
    rows = await db.execute(
        select(ChatMessage)
        .options(selectinload(ChatMessage.sender))
        .where(ChatMessage.ticket_id == ticket_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
    )
    messages = list(reversed(rows.scalars().all()))

    history = [
        {
            "sender": m.sender.name if m.sender else "Sistema",
            "role": m.sender.role.value if m.sender else "system",
            "content": m.content,
        }
        for m in messages
    ]

    suggestion = await suggest_reply(
        title=ticket.title,
        description=ticket.description,
        category=(
            ticket.category.value if hasattr(ticket.category, "value") else str(ticket.category)
        ),
        priority=(
            ticket.priority.value if hasattr(ticket.priority, "value") else str(ticket.priority)
        ),
        status=ticket.status.value if hasattr(ticket.status, "value") else str(ticket.status),
        history=history,
    )

    if suggestion is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O assistente de IA está indisponível no momento. Tente novamente mais tarde.",
        )

    return SuggestReplyResponse(suggestion=suggestion)


@router.post(
    "/tickets/{ticket_id}/improve-message",
    response_model=ImproveMessageResponse,
    dependencies=[Depends(_exige_ia_ligada)],
)
async def improve_ticket_message(
    ticket_id: uuid.UUID,
    body: ImproveMessageRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> ImproveMessageResponse:
    """Improve a technician's draft message using AI (grammar, clarity, professionalism)."""
    ticket = await _get_ticket_visivel(ticket_id, actor, db)
    _exige_ia_no_chamado(ticket)

    result = await improve_message(
        draft=body.draft,
        title=ticket.title,
        description=ticket.description,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O assistente de IA está indisponível no momento. Tente novamente mais tarde.",
        )

    return ImproveMessageResponse(improved=result)


@router.post(
    "/tickets/{ticket_id}/summarize",
    response_model=ConversationSummaryResponse,
    dependencies=[Depends(_exige_ia_ligada)],
)
async def summarize_ticket_conversation(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> ConversationSummaryResponse:
    """
    Generate an AI summary of the full ticket conversation and persist it in the ticket.
    Returns the summary text. Subsequent calls regenerate and overwrite the stored summary.
    """
    ticket = await _get_ticket_visivel(ticket_id, actor, db)
    _exige_ia_no_chamado(ticket)

    # Load all messages (up to 200 to keep context manageable)
    rows = await db.execute(
        select(ChatMessage)
        .options(selectinload(ChatMessage.sender))
        .where(ChatMessage.ticket_id == ticket_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(200)
    )
    messages = rows.scalars().all()

    if not messages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Ainda não há mensagens nesta conversa para resumir.",
        )

    history = [
        {
            "sender": m.sender.name if m.sender else "Sistema",
            "role": m.sender.role.value if m.sender else "system",
            "content": m.content,
        }
        for m in messages
    ]

    summary = await summarize_conversation(
        title=ticket.title,
        category=(
            ticket.category.value if hasattr(ticket.category, "value") else str(ticket.category)
        ),
        status=ticket.status.value if hasattr(ticket.status, "value") else str(ticket.status),
        history=history,
    )

    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O assistente de IA está indisponível no momento. Tente novamente mais tarde.",
        )

    # Persist summary in the ticket
    ticket.ai_conversation_summary = summary
    ticket.updated_at = datetime.now(UTC)
    await commit_e_notificar(db)

    return ConversationSummaryResponse(summary=summary)


# ── WebSocket endpoint ────────────────────────────────────────


@router.websocket("/ws/tickets/{ticket_id}")
async def websocket_chat(
    websocket: WebSocket,
    ticket_id: uuid.UUID,
    token: str = Query(...),
) -> None:
    """
    WebSocket chat room for a ticket.

    Query params:
      token — JWT access token (browser WebSocket API doesn't support headers)
    """
    async with AsyncSessionLocal() as db:
        user = await _authenticate_ws(token, db)
        if user is None:
            await websocket.close(code=4001, reason="Unauthorized")
            return

        # Chamado inexistente e chamado alheio fecham IGUAL — mesmo código,
        # mesmo motivo. O 4003 ("Forbidden") de antes dizia que o chamado
        # existe, e quem tivesse uma lista de ids enumerava o sistema pelo
        # WebSocket sem nunca receber um HTTP 403.
        ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = ticket_result.scalar_one_or_none()
        is_staff = user.role in (UserRole.admin, UserRole.technician)
        if ticket is None or (not is_staff and ticket.creator_id != user.id):
            await websocket.close(code=4004, reason="Ticket not found")
            return

    await websocket.accept()
    tid_str = str(ticket_id)
    manager.connect(tid_str, websocket)
    logger.info(f"WS connected: user={user.id} ticket={ticket_id}")

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                content = str(data.get("content", "")).strip()
            except (json.JSONDecodeError, AttributeError):
                await websocket.send_json({"type": "error", "detail": "Invalid JSON"})
                continue

            if not content:
                continue

            # O mesmo teto do schema REST. Aqui é preciso conferir à mão porque
            # este caminho não passa por Pydantic nenhum — e é justamente por
            # isso que ele seria o escolhido por quem quisesse abusar.
            if len(content) > LIMITE_CONTEUDO:
                await websocket.send_json(
                    {
                        "type": "error",
                        "detail": (
                            f"Mensagem longa demais (máximo {LIMITE_CONTEUDO} caracteres). "
                            "Para textos maiores, use um anexo."
                        ),
                    }
                )
                continue

            async with AsyncSessionLocal() as db:
                ticket_res = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
                ticket = ticket_res.scalar_one_or_none()
                if ticket is None:
                    break

                now = datetime.now(UTC)
                msg = ChatMessage(
                    id=uuid.uuid4(),
                    ticket_id=ticket_id,
                    sender_id=user.id,
                    content=content,
                    is_system=False,
                    is_ai=False,
                    created_at=now,
                )
                db.add(msg)

                register_first_response(
                    ticket, now, responder_id=user.id, is_ai=msg.is_ai, is_system=msg.is_system
                )

                await _notify_other_party(db, ticket, user, msg)

                # O chat do front conversa por WebSocket, entao ESTE e o
                # caminho pelo qual a resposta do cliente chega de verdade. O
                # POST existe, mas fica de reserva -- ligar a Helo so la a
                # deixaria muda na tela onde ela aparece.
                fala_da_helo = None
                if user.id == ticket.creator_id:
                    fala_da_helo = await responde_triagem(db, ticket, user, msg.content)
                    if fala_da_helo is not None:
                        await _avisa_equipe_da_triagem(db, ticket)

                new_status_value = await _apply_chat_transition(db, ticket, user)

                await commit_e_notificar(db)

                result = await db.execute(
                    select(ChatMessage)
                    .options(selectinload(ChatMessage.sender))
                    .where(ChatMessage.id == msg.id)
                )
                msg = result.scalar_one()

            response = _msg_to_response(msg)
            await manager.broadcast(
                tid_str,
                {"type": "message", "data": _response_to_dict(response)},
            )
            # A fala dela vai num broadcast proprio, DEPOIS da do cliente: e a
            # ordem em que a conversa aconteceu, e e a ordem em que a tela
            # precisa mostrar.
            if fala_da_helo is not None:
                await manager.broadcast(
                    tid_str,
                    {"type": "message", "data": _response_to_dict(_msg_to_response(fala_da_helo))},
                )
            if new_status_value:
                await manager.broadcast(
                    tid_str,
                    {"type": "status_update", "data": {"status": new_status_value}},
                )

    except WebSocketDisconnect:
        logger.info(f"WS disconnected: user={user.id} ticket={ticket_id}")
    finally:
        manager.disconnect(tid_str, websocket)


# ── Internal helpers ──────────────────────────────────────────


def _response_to_dict(r: ChatMessageResponse) -> dict:
    return {
        "id": str(r.id),
        "ticket_id": str(r.ticket_id),
        # Nulo quando quem falou foi a Helô. Sem a guarda isto vira a STRING
        # "None", que o front compara com o id do usuário logado e nunca bate —
        # funcionaria por acidente, e mentiria no tipo declarado.
        "sender_id": str(r.sender_id) if r.sender_id else None,
        "sender_name": r.sender_name,
        "sender_role": r.sender_role,
        "content": r.content,
        "is_system": r.is_system,
        "is_ai": r.is_ai,
        "created_at": r.created_at.isoformat(),
    }


async def _apply_chat_transition(
    db: AsyncSession,
    ticket: Ticket,
    sender: User,
) -> str | None:
    """Auto-transition ticket status when a chat message is sent.

    Staff sending → awaiting_client (if in_progress or awaiting_technical).
    Client sending → awaiting_technical (if awaiting_client).

    Returns the new status value string if a transition occurred, else None.
    """
    is_staff = sender.role in (UserRole.admin, UserRole.technician)

    if is_staff and ticket.status in (TicketStatus.in_progress, TicketStatus.awaiting_technical):
        changed = await _auto_transition(
            db, ticket, TicketStatus.awaiting_client, sender.id, "Técnico respondeu"
        )
        return TicketStatus.awaiting_client.value if changed else None

    if not is_staff and ticket.status in (TicketStatus.in_progress, TicketStatus.awaiting_client):
        changed = await _auto_transition(
            db, ticket, TicketStatus.awaiting_technical, sender.id, "Cliente respondeu"
        )
        return TicketStatus.awaiting_technical.value if changed else None

    return None


async def _avisa_equipe_da_triagem(db: AsyncSession, ticket: Ticket) -> None:
    """
    Chama a equipe quando a Helô termina de triar.

    Sem isto o chamado fica em "Em andamento" sem dono e sem ninguém avisado: a
    notificação normal do chat vai para o RESPONSÁVEL, e a essa altura não há
    responsável nenhum. O chamado dependeria de alguém olhar o quadro.

    Vai para todos os técnicos e admins ativos, e não para um sorteado: sem
    dono, escolher um seria inventar uma atribuição que ninguém pediu — e o
    escolhido poderia estar de férias.
    """
    equipe = (
        (
            await db.execute(
                select(User).where(
                    User.role.in_([UserRole.admin, UserRole.technician]),
                    User.status == UserStatus.active,
                )
            )
        )
        .scalars()
        .all()
    )

    for pessoa in equipe:
        await notify(
            db,
            pessoa.id,
            NotificationType.ticket_updated,
            f"Triagem concluída — {ticket.protocol}",
            "A Helô terminou a triagem e o chamado está esperando atendimento.",
            data={"ticket_id": str(ticket.id), "protocol": ticket.protocol},
        )


async def _notify_other_party(
    db: AsyncSession,
    ticket: Ticket,
    sender: User,
    msg: ChatMessage,
) -> None:
    """
    Notify the other party in the conversation:
    - If sender is the requester → notify assignee (if any)
    - If sender is staff → notify requester
    """
    is_requester = ticket.creator_id == sender.id

    if is_requester:
        # Notify assignee if assigned
        if ticket.assignee_id:
            await notify(
                db,
                ticket.assignee_id,
                NotificationType.chat_message,
                f"Nova mensagem no chamado {ticket.protocol}",
                f"{sender.name}: {msg.content[:120]}",
                data={"ticket_id": str(ticket.id)},
            )
    else:
        # Notify requester
        await notify(
            db,
            ticket.creator_id,
            NotificationType.chat_message,
            f"Nova mensagem no chamado {ticket.protocol}",
            f"{sender.name}: {msg.content[:120]}",
            data={"ticket_id": str(ticket.id)},
        )
