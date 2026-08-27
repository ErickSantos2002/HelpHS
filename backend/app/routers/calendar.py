"""
Agenda da equipe — CRUD de eventos do calendário.

Permissões:
  GET    /calendar/events         — admin | technician
  POST   /calendar/events         — admin | technician
  PATCH  /calendar/events/{id}    — admin | technician
  DELETE /calendar/events/{id}    — admin | technician
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import authorize
from app.models.models import CalendarEvent, User, UserRole
from app.schemas.calendar import (
    CalendarEventCreate,
    CalendarEventListResponse,
    CalendarEventResponse,
    CalendarEventUpdate,
)

router = APIRouter(prefix="/calendar", tags=["Calendar"])


def _to_response(event: CalendarEvent) -> CalendarEventResponse:
    resp = CalendarEventResponse.model_validate(event)
    if event.creator:
        resp.creator_name = event.creator.name
    return resp


# ── GET /calendar/events ──────────────────────────────────────


@router.get("/events", response_model=CalendarEventListResponse)
async def list_events(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
) -> CalendarEventListResponse:
    stmt = select(CalendarEvent).order_by(CalendarEvent.start_date)

    if year and month:
        start = datetime(year, month, 1, tzinfo=UTC)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=UTC)
        else:
            end = datetime(year, month + 1, 1, tzinfo=UTC)
        stmt = stmt.where(CalendarEvent.start_date < end, CalendarEvent.end_date >= start)

    rows = await db.execute(stmt)
    events = rows.scalars().all()

    # Load creators
    creator_ids = [e.created_by for e in events if e.created_by]
    creators: dict[uuid.UUID, User] = {}
    if creator_ids:
        creator_rows = await db.execute(select(User).where(User.id.in_(creator_ids)))
        for u in creator_rows.scalars().all():
            creators[u.id] = u
    for e in events:
        if e.created_by and e.created_by in creators:
            e.creator = creators[e.created_by]

    return CalendarEventListResponse(
        items=[_to_response(e) for e in events],
        total=len(events),
    )


# ── POST /calendar/events ─────────────────────────────────────


@router.post("/events", response_model=CalendarEventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    body: CalendarEventCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> CalendarEventResponse:
    if body.end_date < body.start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A data de fim precisa ser igual ou posterior à data de início.",
        )

    now = datetime.now(UTC)
    event = CalendarEvent(
        id=uuid.uuid4(),
        title=body.title,
        description=body.description,
        event_type=body.event_type,
        color=body.color,
        start_date=body.start_date,
        end_date=body.end_date,
        created_by=actor.id,
        # Explícito: o default da coluna só valeria no INSERT e a resposta é
        # montada a partir do objeto em memória
        created_at=now,
        updated_at=now,
    )
    event.creator = actor
    db.add(event)
    await db.commit()
    await db.refresh(event)
    event.creator = actor
    return _to_response(event)


# ── PATCH /calendar/events/{event_id} ────────────────────────


@router.patch("/events/{event_id}", response_model=CalendarEventResponse)
async def update_event(
    event_id: uuid.UUID,
    body: CalendarEventUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> CalendarEventResponse:
    result = await db.execute(select(CalendarEvent).where(CalendarEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento não encontrado. Ele pode ter sido removido da agenda.",
        )

    if body.title is not None:
        event.title = body.title
    # `description` é o único campo aqui que precisa distinguir "não enviado" de
    # "enviado como nulo": é o único nullable no modelo, e o front manda nulo
    # explícito quando a pessoa limpa o campo. Com `is not None` esse nulo era
    # ignorado e o texto antigo reaparecia no carregamento seguinte.
    #
    # NÃO uniformize os outros cinco. `title`, `event_type`, `color`,
    # `start_date` e `end_date` são NOT NULL no modelo — para eles, ignorar o
    # nulo está correto, e aceitá-lo trocaria este bug por um erro de
    # integridade no banco.
    if "description" in body.model_fields_set:
        event.description = body.description
    if body.event_type is not None:
        event.event_type = body.event_type
    if body.color is not None:
        event.color = body.color
    if body.start_date is not None:
        event.start_date = body.start_date
    if body.end_date is not None:
        event.end_date = body.end_date

    if event.end_date < event.start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A data de fim precisa ser igual ou posterior à data de início.",
        )

    await db.commit()
    await db.refresh(event)

    if event.created_by:
        creator_row = await db.execute(select(User).where(User.id == event.created_by))
        event.creator = creator_row.scalar_one_or_none()

    return _to_response(event)


# ── DELETE /calendar/events/{event_id} ───────────────────────


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> None:
    result = await db.execute(select(CalendarEvent).where(CalendarEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento não encontrado. Ele pode ter sido removido da agenda.",
        )

    await db.delete(event)
    await db.commit()
