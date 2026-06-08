"""
Agenda da equipe — CRUD de eventos do calendário.

Permissões:
  GET    /calendar/events         — admin | technician
  POST   /calendar/events         — admin | technician
  PATCH  /calendar/events/{id}    — admin | technician
  DELETE /calendar/events/{id}    — admin | technician
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import authorize, get_current_user
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
        from datetime import datetime, timezone
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
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
            detail="end_date must be >= start_date",
        )

    event = CalendarEvent(
        id=uuid.uuid4(),
        title=body.title,
        description=body.description,
        event_type=body.event_type,
        color=body.color,
        start_date=body.start_date,
        end_date=body.end_date,
        created_by=actor.id,
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    if body.title is not None:
        event.title = body.title
    if body.description is not None:
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
            detail="end_date must be >= start_date",
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    await db.delete(event)
    await db.commit()
