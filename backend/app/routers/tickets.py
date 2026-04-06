"""
CRUD de Tickets.

Permissões:
  POST   /tickets                    — qualquer autenticado (creator = current user)
  GET    /tickets                    — qualquer autenticado
                                       (client vê apenas os próprios tickets)
  GET    /tickets/{id}               — qualquer autenticado
                                       (client só acessa os próprios)
  PATCH  /tickets/{id}               — admin/technician (todos os campos)
                                       client (title/description, apenas se status=open)
  PATCH  /tickets/{id}/status        — admin, technician
  PATCH  /tickets/{id}/assign        — admin, technician
  DELETE /tickets/{id}               — admin (cancela o ticket)
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select  # func used in list_tickets subquery
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import authorize, get_current_user
from app.models.models import (
    AuditAction,
    AuditLog,
    NotificationType,
    SLAConfig,
    Ticket,
    TicketHistory,
    TicketStatus,
    User,
    UserRole,
)
from app.schemas.ticket import (
    TicketAssign,
    TicketCreate,
    TicketHistoryListResponse,
    TicketHistoryResponse,
    TicketListResponse,
    TicketResponse,
    TicketStatusUpdate,
    TicketUpdate,
)
from app.services.llm import classify_ticket
from app.services.notifications import notify
from app.utils.protocol import MAX_RETRIES, generate_protocol
from app.utils.sla import (
    _PAUSE_STATUSES,
    apply_sla_config,
    check_breaches,
    pause_sla,
    resume_sla,
)

router = APIRouter(tags=["Tickets"])


# ── LLM background classification ────────────────────────────


async def _classify_ticket_async(
    ticket_id: uuid.UUID,
    title: str,
    description: str,
    category: str,
) -> None:
    """Fire-and-forget: classify ticket with LLM and persist results."""
    from app.core.database import AsyncSessionLocal

    result = await classify_ticket(title, description, category)
    if result is None:
        return

    try:
        async with AsyncSessionLocal() as db:
            row = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
            ticket = row.scalar_one_or_none()
            if ticket is None:
                return
            ticket.ai_classification = result["priority"]
            ticket.ai_confidence = result["confidence"]
            ticket.ai_summary = result["summary"]
            ticket.updated_at = datetime.now(UTC)
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        from loguru import logger

        logger.warning(f"Failed to persist LLM classification for ticket {ticket_id}: {exc}")


# ── Valid status transitions ──────────────────────────────────

_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.open: {TicketStatus.in_progress, TicketStatus.cancelled},
    TicketStatus.in_progress: {
        TicketStatus.awaiting_client,
        TicketStatus.awaiting_technical,
        TicketStatus.resolved,
        TicketStatus.cancelled,
    },
    TicketStatus.awaiting_client: {
        TicketStatus.in_progress,
        TicketStatus.resolved,
        TicketStatus.cancelled,
    },
    TicketStatus.awaiting_technical: {
        TicketStatus.in_progress,
        TicketStatus.resolved,
        TicketStatus.cancelled,
    },
    TicketStatus.resolved: {TicketStatus.closed},
    TicketStatus.closed: set(),
    TicketStatus.cancelled: set(),
}


# ── Helpers ───────────────────────────────────────────────────


def _audit(
    db: AsyncSession,
    action: AuditAction,
    actor_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> None:
    db.add(
        AuditLog(
            user_id=actor_id,
            action=action,
            entity_type="ticket",
            entity_id=entity_id,
        )
    )


def _record_history(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    user_id: uuid.UUID,
    field: str,
    old_value: str | None,
    new_value: str | None,
    comment: str | None = None,
) -> None:
    db.add(
        TicketHistory(
            id=uuid.uuid4(),
            ticket_id=ticket_id,
            user_id=user_id,
            field=field,
            old_value=str(old_value) if old_value is not None else None,
            new_value=str(new_value) if new_value is not None else None,
            comment=comment,
        )
    )


async def _get_ticket_or_404(ticket_id: uuid.UUID, db: AsyncSession) -> Ticket:
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return ticket


# ═══════════════════════════════════════════════════════════════
# TICKETS
# ═══════════════════════════════════════════════════════════════


@router.post("/tickets", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    body: TicketCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TicketResponse:
    ts = datetime.now(UTC)
    ticket_id = uuid.uuid4()

    # Look up SLA config matching this ticket's priority
    sla_result = await db.execute(
        select(SLAConfig).where(
            SLAConfig.level == body.priority.value,
            SLAConfig.is_active.is_(True),
        )
    )
    sla_config = sla_result.scalar_one_or_none()

    for attempt in range(MAX_RETRIES):
        protocol = await generate_protocol(db)
        ticket = Ticket(
            id=ticket_id,
            protocol=protocol,
            title=body.title,
            description=body.description,
            priority=body.priority,
            category=body.category,
            status=TicketStatus.open,
            creator_id=actor.id,
            product_id=body.product_id,
            equipment_id=body.equipment_id,
            sla_response_breach=False,
            sla_resolve_breach=False,
            sla_total_paused_ms=0,
            created_at=ts,
            updated_at=ts,
        )
        if sla_config:
            apply_sla_config(ticket, sla_config, ts)
        db.add(ticket)
        _record_history(db, ticket.id, actor.id, "created", None, "open")
        _audit(db, AuditAction.create, actor.id, ticket.id)
        await notify(
            db,
            actor.id,
            NotificationType.ticket_created,
            "Ticket aberto",
            f"Seu ticket foi registrado com o protocolo {protocol}.",
            data={"ticket_id": str(ticket.id), "protocol": protocol},
            settings=settings,
        )
        try:
            await db.commit()
            break
        except IntegrityError:
            await db.rollback()
            if attempt == MAX_RETRIES - 1:
                raise
            # Regenerate a fresh ticket_id on retry to avoid PK collision
            ticket_id = uuid.uuid4()

    await db.refresh(ticket)

    # Fire-and-forget LLM classification (non-blocking)
    asyncio.create_task(
        _classify_ticket_async(ticket.id, body.title, body.description, body.category.value)
    )

    return TicketResponse.model_validate(ticket)


# Priority sort order: critical=0, high=1, medium=2, low=3
_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

_SORT_COLUMNS = {
    "created_at": Ticket.created_at,
    "updated_at": Ticket.updated_at,
    "priority": Ticket.priority,
    "sla_resolve_due_at": Ticket.sla_resolve_due_at,
}


@router.get("/tickets", response_model=TicketListResponse)
async def list_tickets(
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: TicketStatus | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    category: str | None = Query(default=None),
    assignee_id: uuid.UUID | None = Query(default=None),
    creator_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    sort_by: str = Query(
        default="created_at", pattern="^(created_at|updated_at|priority|sla_resolve_due_at)$"
    ),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> TicketListResponse:
    from sqlalchemy import asc, case, desc

    base = select(Ticket)

    # Clients only see their own tickets
    if actor.role == UserRole.client:
        base = base.where(Ticket.creator_id == actor.id)
    elif creator_id:
        base = base.where(Ticket.creator_id == creator_id)

    if status_filter is not None:
        base = base.where(Ticket.status == status_filter)
    if priority:
        base = base.where(Ticket.priority == priority)
    if category:
        base = base.where(Ticket.category == category)
    if assignee_id:
        base = base.where(Ticket.assignee_id == assignee_id)
    if search:
        base = base.where(Ticket.title.ilike(f"%{search}%") | Ticket.protocol.ilike(f"%{search}%"))

    # Build sort expression
    if sort_by == "priority":
        sort_expr = case(
            (Ticket.priority == "critical", 0),
            (Ticket.priority == "high", 1),
            (Ticket.priority == "medium", 2),
            (Ticket.priority == "low", 3),
            else_=4,
        )
    else:
        sort_expr = _SORT_COLUMNS[sort_by]

    order = asc(sort_expr) if sort_dir == "asc" else desc(sort_expr)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = await db.execute(base.order_by(order).offset(offset).limit(limit))
    tickets = rows.scalars().all()

    return TicketListResponse(
        items=[TicketResponse.model_validate(t) for t in tickets],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> TicketResponse:
    ticket = await _get_ticket_or_404(ticket_id, db)

    if actor.role == UserRole.client and ticket.creator_id != actor.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return TicketResponse.model_validate(ticket)


@router.patch("/tickets/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    ticket_id: uuid.UUID,
    body: TicketUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> TicketResponse:
    ticket = await _get_ticket_or_404(ticket_id, db)

    if actor.role == UserRole.client:
        if ticket.creator_id != actor.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        if ticket.status != TicketStatus.open:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ticket can only be edited while open",
            )
        changes = body.model_dump(include={"title", "description"}, exclude_unset=True)
    else:
        changes = body.model_dump(exclude_unset=True)

    for field, new_val in changes.items():
        old_val = getattr(ticket, field)
        if old_val != new_val:
            _record_history(db, ticket.id, actor.id, field, old_val, new_val)
        setattr(ticket, field, new_val)

    ticket.updated_at = datetime.now(UTC)
    _audit(db, AuditAction.update, actor.id, ticket.id)
    await db.commit()
    await db.refresh(ticket)
    return TicketResponse.model_validate(ticket)


@router.patch("/tickets/{ticket_id}/status", response_model=TicketResponse)
async def update_ticket_status(
    ticket_id: uuid.UUID,
    body: TicketStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TicketResponse:
    ticket = await _get_ticket_or_404(ticket_id, db)

    if body.status not in _TRANSITIONS.get(ticket.status, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot transition from '{ticket.status}' to '{body.status}'",
        )

    now = datetime.now(UTC)
    old_status = ticket.status
    ticket.status = body.status
    ticket.updated_at = now

    # SLA: first response timestamp (when leaving open state)
    if old_status == TicketStatus.open and body.status != TicketStatus.open:
        ticket.sla_first_response = now

    # SLA: pause / resume clock
    if old_status not in _PAUSE_STATUSES and body.status in _PAUSE_STATUSES:
        pause_sla(ticket, now)
    elif old_status in _PAUSE_STATUSES and body.status not in _PAUSE_STATUSES:
        resume_sla(ticket, now)

    check_breaches(ticket, now)

    if body.status in (TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled):
        ticket.closed_at = now

    _record_history(
        db, ticket.id, actor.id, "status", old_status.value, body.status.value, body.comment
    )
    _audit(db, AuditAction.status_change, actor.id, ticket.id)
    await notify(
        db,
        ticket.creator_id,
        NotificationType.ticket_updated,
        "Status do ticket alterado",
        f"O status do ticket {ticket.protocol} foi alterado para '{body.status.value}'.",
        data={
            "ticket_id": str(ticket.id),
            "old_status": old_status.value,
            "new_status": body.status.value,
        },
        settings=settings,
    )
    # Invite creator to fill CSAT survey when ticket is resolved
    if body.status == TicketStatus.resolved:
        await notify(
            db,
            ticket.creator_id,
            NotificationType.satisfaction_survey,
            "Como foi o atendimento?",
            f"O ticket {ticket.protocol} foi resolvido. Deixe sua avaliação!",
            data={"ticket_id": str(ticket.id), "protocol": ticket.protocol},
            settings=settings,
        )
    await db.commit()
    await db.refresh(ticket)
    return TicketResponse.model_validate(ticket)


@router.patch("/tickets/{ticket_id}/assign", response_model=TicketResponse)
async def assign_ticket(
    ticket_id: uuid.UUID,
    body: TicketAssign,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TicketResponse:
    ticket = await _get_ticket_or_404(ticket_id, db)

    if body.assignee_id is not None:
        result = await db.execute(select(User).where(User.id == body.assignee_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignee not found")

    old_assignee = ticket.assignee_id
    ticket.assignee_id = body.assignee_id
    ticket.updated_at = datetime.now(UTC)
    _record_history(db, ticket.id, actor.id, "assignee_id", old_assignee, body.assignee_id)
    _audit(db, AuditAction.assign, actor.id, ticket.id)
    if body.assignee_id is not None:
        await notify(
            db,
            body.assignee_id,
            NotificationType.ticket_assigned,
            "Ticket atribuído a você",
            f"O ticket {ticket.protocol} foi atribuído a você.",
            data={"ticket_id": str(ticket.id), "protocol": ticket.protocol},
            settings=settings,
        )
    await db.commit()
    await db.refresh(ticket)
    return TicketResponse.model_validate(ticket)


@router.delete("/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_ticket(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    ticket = await _get_ticket_or_404(ticket_id, db)

    if ticket.status in (TicketStatus.closed, TicketStatus.cancelled):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ticket is already '{ticket.status}'",
        )

    old_status = ticket.status
    ticket.status = TicketStatus.cancelled
    ticket.closed_at = datetime.now(UTC)
    ticket.updated_at = ticket.closed_at
    _record_history(db, ticket.id, actor.id, "status", old_status.value, "cancelled")
    _audit(db, AuditAction.delete, actor.id, ticket.id)
    await notify(
        db,
        ticket.creator_id,
        NotificationType.ticket_closed,
        "Ticket cancelado",
        f"O ticket {ticket.protocol} foi cancelado.",
        data={"ticket_id": str(ticket.id), "protocol": ticket.protocol},
        settings=settings,
    )
    await db.commit()


@router.get("/tickets/{ticket_id}/history", response_model=TicketHistoryListResponse)
async def get_ticket_history(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> TicketHistoryListResponse:
    ticket = await _get_ticket_or_404(ticket_id, db)

    if actor.role == UserRole.client and ticket.creator_id != actor.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    base = select(TicketHistory).where(TicketHistory.ticket_id == ticket_id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = await db.execute(
        base.order_by(TicketHistory.created_at.asc()).offset(offset).limit(limit)
    )
    entries = rows.scalars().all()

    return TicketHistoryListResponse(
        items=[TicketHistoryResponse.model_validate(h) for h in entries],
        total=total,
        limit=limit,
        offset=offset,
    )
