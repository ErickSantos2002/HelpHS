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

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select  # func used in list_tickets subquery
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import authorize, get_current_user
from app.models.models import (
    AuditAction,
    AuditLog,
    Ticket,
    TicketStatus,
    User,
    UserRole,
)
from app.schemas.ticket import (
    TicketAssign,
    TicketCreate,
    TicketListResponse,
    TicketResponse,
    TicketStatusUpdate,
    TicketUpdate,
)
from app.utils.protocol import MAX_RETRIES, generate_protocol

router = APIRouter(tags=["Tickets"])

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
) -> TicketResponse:
    ts = datetime.now(UTC)
    ticket_id = uuid.uuid4()

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
        db.add(ticket)
        _audit(db, AuditAction.create, actor.id, ticket.id)
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
    return TicketResponse.model_validate(ticket)


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
) -> TicketListResponse:
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
        base = base.where(Ticket.title.ilike(f"%{search}%"))

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = await db.execute(base.order_by(Ticket.created_at.desc()).offset(offset).limit(limit))
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
        # Clients may only update title and description
        allowed = body.model_dump(include={"title", "description"}, exclude_unset=True)
        for field, value in allowed.items():
            setattr(ticket, field, value)
    else:
        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(ticket, field, value)

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
) -> TicketResponse:
    ticket = await _get_ticket_or_404(ticket_id, db)

    if body.status not in _TRANSITIONS.get(ticket.status, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot transition from '{ticket.status}' to '{body.status}'",
        )

    ticket.status = body.status
    ticket.updated_at = datetime.now(UTC)

    if body.status in (TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled):
        ticket.closed_at = ticket.updated_at

    _audit(db, AuditAction.status_change, actor.id, ticket.id)
    await db.commit()
    await db.refresh(ticket)
    return TicketResponse.model_validate(ticket)


@router.patch("/tickets/{ticket_id}/assign", response_model=TicketResponse)
async def assign_ticket(
    ticket_id: uuid.UUID,
    body: TicketAssign,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> TicketResponse:
    ticket = await _get_ticket_or_404(ticket_id, db)

    if body.assignee_id is not None:
        result = await db.execute(select(User).where(User.id == body.assignee_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignee not found")

    ticket.assignee_id = body.assignee_id
    ticket.updated_at = datetime.now(UTC)
    _audit(db, AuditAction.assign, actor.id, ticket.id)
    await db.commit()
    await db.refresh(ticket)
    return TicketResponse.model_validate(ticket)


@router.delete("/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_ticket(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin))],
) -> None:
    ticket = await _get_ticket_or_404(ticket_id, db)

    if ticket.status in (TicketStatus.closed, TicketStatus.cancelled):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ticket is already '{ticket.status}'",
        )

    ticket.status = TicketStatus.cancelled
    ticket.closed_at = datetime.now(UTC)
    ticket.updated_at = ticket.closed_at
    _audit(db, AuditAction.delete, actor.id, ticket.id)
    await db.commit()
