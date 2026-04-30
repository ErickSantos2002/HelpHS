"""
CRUD de etiquetas (tags) e vinculação em tickets.

Permissões:
  GET    /tags                     — qualquer autenticado
  POST   /tags                     — admin | technician
  PATCH  /tags/{id}                — admin
  DELETE /tags/{id}                — admin
  PUT    /tickets/{ticket_id}/tags — admin | technician
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import authorize, get_current_user
from app.models.models import Tag, Ticket, UserRole, ticket_tags
from app.schemas.tag import TagCreate, TagListResponse, TagResponse, TagUpdate, TicketTagsUpdate

router = APIRouter(tags=["Tags"])


# ── GET /tags ─────────────────────────────────────────────────


@router.get("/tags", response_model=TagListResponse)
async def list_tags(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[object, Depends(get_current_user)],
) -> TagListResponse:
    rows = await db.execute(select(Tag).order_by(Tag.name))
    tags = rows.scalars().all()
    return TagListResponse(items=[TagResponse.model_validate(t) for t in tags], total=len(tags))


# ── POST /tags ────────────────────────────────────────────────


@router.post("/tags", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    body: TagCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[object, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> TagResponse:
    existing = await db.execute(select(Tag).where(Tag.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tag name already exists")

    tag = Tag(id=uuid.uuid4(), name=body.name, color=body.color, created_by=actor.id)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return TagResponse.model_validate(tag)


# ── PATCH /tags/{tag_id} ──────────────────────────────────────


@router.patch("/tags/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: uuid.UUID,
    body: TagUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[object, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> TagResponse:
    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")

    if body.name is not None:
        conflict = await db.execute(select(Tag).where(Tag.name == body.name, Tag.id != tag_id))
        if conflict.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Tag name already exists"
            )
        tag.name = body.name

    if body.color is not None:
        tag.color = body.color

    await db.commit()
    await db.refresh(tag)
    return TagResponse.model_validate(tag)


# ── DELETE /tags/{tag_id} ─────────────────────────────────────


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[object, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> None:
    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")

    await db.delete(tag)
    await db.commit()


# ── PUT /tickets/{ticket_id}/tags ─────────────────────────────


@router.put("/tickets/{ticket_id}/tags", response_model=list[TagResponse])
async def set_ticket_tags(
    ticket_id: uuid.UUID,
    body: TicketTagsUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[object, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> list[TagResponse]:
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    # Verify all tag IDs exist
    if body.tag_ids:
        tags_result = await db.execute(select(Tag).where(Tag.id.in_(body.tag_ids)))
        found_tags = tags_result.scalars().all()
        if len(found_tags) != len(set(body.tag_ids)):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="One or more tags not found"
            )
    else:
        found_tags = []

    # Replace association rows directly for efficiency
    await db.execute(ticket_tags.delete().where(ticket_tags.c.ticket_id == ticket_id))
    if found_tags:
        await db.execute(
            ticket_tags.insert(),
            [{"ticket_id": ticket_id, "tag_id": t.id} for t in found_tags],
        )

    await db.commit()

    # Re-fetch ordered tags
    rows = await db.execute(
        select(Tag)
        .join(ticket_tags, Tag.id == ticket_tags.c.tag_id)
        .where(ticket_tags.c.ticket_id == ticket_id)
        .order_by(Tag.name)
    )
    return [TagResponse.model_validate(t) for t in rows.scalars().all()]
