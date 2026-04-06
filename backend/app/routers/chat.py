"""
Chat em tempo real para tickets.

Endpoints REST:
  GET  /tickets/{ticket_id}/messages          — histórico paginado
  POST /tickets/{ticket_id}/messages          — criar mensagem (staff/sistema)

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
from app.core.security import decode_token, get_current_user
from app.models.models import (
    ChatMessage,
    NotificationType,
    Ticket,
    User,
    UserRole,
    UserStatus,
)
from app.schemas.chat import ChatMessageCreate, ChatMessageListResponse, ChatMessageResponse
from app.services.notifications import notify

router = APIRouter(tags=["Chat"])
settings = get_settings()


# ── ConnectionManager ─────────────────────────────────────────


class ConnectionManager:
    """In-memory WebSocket room manager keyed by ticket_id."""

    def __init__(self) -> None:
        # ticket_id (str) → set of active WebSocket connections
        self._rooms: dict[str, set[WebSocket]] = {}

    def connect(self, ticket_id: str, ws: WebSocket) -> None:
        self._rooms.setdefault(ticket_id, set()).add(ws)

    def disconnect(self, ticket_id: str, ws: WebSocket) -> None:
        room = self._rooms.get(ticket_id)
        if room:
            room.discard(ws)
            if not room:
                del self._rooms[ticket_id]

    async def broadcast(self, ticket_id: str, payload: dict) -> None:
        """Send JSON payload to every connected client in the room."""
        room = self._rooms.get(ticket_id, set())
        dead: list[WebSocket] = []
        for ws in list(room):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            room.discard(ws)


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


async def _get_ticket_or_403(
    ticket_id: uuid.UUID,
    actor: User,
    db: AsyncSession,
) -> Ticket:
    """Return ticket if the actor may access it, else raise 403/404."""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    is_staff = actor.role in (UserRole.admin, UserRole.technician)
    is_requester = ticket.creator_id == actor.id
    if not is_staff and not is_requester:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return ticket


async def _authenticate_ws(token: str, db: AsyncSession) -> User | None:
    """Validate JWT token from WS query param. Returns User or None."""
    try:
        payload = decode_token(token)
    except JWTError:
        return None

    if payload.get("type") != "access":
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


# ── REST endpoints ────────────────────────────────────────────


@router.get("/tickets/{ticket_id}/messages", response_model=ChatMessageListResponse)
async def list_messages(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ChatMessageListResponse:
    await _get_ticket_or_403(ticket_id, actor, db)

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
    ticket = await _get_ticket_or_403(ticket_id, actor, db)

    msg = ChatMessage(
        id=uuid.uuid4(),
        ticket_id=ticket_id,
        sender_id=actor.id,
        content=payload.content.strip(),
        is_system=False,
        is_ai=False,
        created_at=datetime.now(UTC),
    )
    db.add(msg)

    # Notify the other party
    await _notify_other_party(db, ticket, actor, msg)

    await db.commit()

    # Reload with sender using selectinload
    result = await db.execute(
        select(ChatMessage)
        .options(selectinload(ChatMessage.sender))
        .where(ChatMessage.id == msg.id)
    )
    msg = result.scalar_one()

    response = _msg_to_response(msg)

    # Broadcast to WebSocket room
    await manager.broadcast(
        str(ticket_id),
        {"type": "message", "data": _response_to_dict(response)},
    )

    return response


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

        ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = ticket_result.scalar_one_or_none()
        if ticket is None:
            await websocket.close(code=4004, reason="Ticket not found")
            return

        is_staff = user.role in (UserRole.admin, UserRole.technician)
        is_requester = ticket.creator_id == user.id
        if not is_staff and not is_requester:
            await websocket.close(code=4003, reason="Forbidden")
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

            async with AsyncSessionLocal() as db:
                ticket_res = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
                ticket = ticket_res.scalar_one_or_none()
                if ticket is None:
                    break

                msg = ChatMessage(
                    id=uuid.uuid4(),
                    ticket_id=ticket_id,
                    sender_id=user.id,
                    content=content,
                    is_system=False,
                    is_ai=False,
                    created_at=datetime.now(UTC),
                )
                db.add(msg)

                await _notify_other_party(db, ticket, user, msg)

                await db.commit()

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

    except WebSocketDisconnect:
        logger.info(f"WS disconnected: user={user.id} ticket={ticket_id}")
    finally:
        manager.disconnect(tid_str, websocket)


# ── Internal helpers ──────────────────────────────────────────


def _response_to_dict(r: ChatMessageResponse) -> dict:
    return {
        "id": str(r.id),
        "ticket_id": str(r.ticket_id),
        "sender_id": str(r.sender_id),
        "sender_name": r.sender_name,
        "sender_role": r.sender_role,
        "content": r.content,
        "is_system": r.is_system,
        "is_ai": r.is_ai,
        "created_at": r.created_at.isoformat(),
    }


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
