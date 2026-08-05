"""
Respostas rápidas do chat — mensagens prontas inseridas com /atalho.

A lista é única para toda a equipe (não há respostas por usuário).

Permissões:
  GET    /quick-replies       — admin, technician
  POST   /quick-replies       — admin, technician
  PATCH  /quick-replies/{id}  — admin, technician
  DELETE /quick-replies/{id}  — admin, technician
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import authorize
from app.models.models import QuickReply, User, UserRole
from app.schemas.quick_reply import (
    QuickReplyCreate,
    QuickReplyListResponse,
    QuickReplyResponse,
    QuickReplyUpdate,
)

router = APIRouter(tags=["Quick Replies"])

_STAFF = authorize(UserRole.admin, UserRole.technician)


async def _get_or_404(reply_id: uuid.UUID, db: AsyncSession) -> QuickReply:
    result = await db.execute(select(QuickReply).where(QuickReply.id == reply_id))
    reply = result.scalar_one_or_none()
    if reply is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resposta rápida não encontrada. Ela pode já ter sido excluída.",
        )
    return reply


async def _reject_duplicate_shortcut(
    shortcut: str, db: AsyncSession, ignore_id: uuid.UUID | None = None
) -> None:
    query = select(QuickReply).where(QuickReply.shortcut == shortcut)
    if ignore_id is not None:
        query = query.where(QuickReply.id != ignore_id)
    if (await db.execute(query)).scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe uma resposta rápida com o atalho /{shortcut}.",
        )


# ── GET /quick-replies ────────────────────────────────────────


@router.get("/quick-replies", response_model=QuickReplyListResponse)
async def list_quick_replies(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(_STAFF)],
) -> QuickReplyListResponse:
    rows = await db.execute(select(QuickReply).order_by(QuickReply.shortcut))
    items = list(rows.scalars().all())
    return QuickReplyListResponse(
        items=[QuickReplyResponse.model_validate(q) for q in items], total=len(items)
    )


# ── POST /quick-replies ───────────────────────────────────────


@router.post(
    "/quick-replies", response_model=QuickReplyResponse, status_code=status.HTTP_201_CREATED
)
async def create_quick_reply(
    body: QuickReplyCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(_STAFF)],
) -> QuickReplyResponse:
    await _reject_duplicate_shortcut(body.shortcut, db)

    now = datetime.now(UTC)
    reply = QuickReply(
        id=uuid.uuid4(),
        shortcut=body.shortcut,
        title=body.title.strip(),
        content=body.content.strip(),
        is_active=body.is_active,
        created_by=actor.id,
        created_at=now,
        updated_at=now,
    )
    db.add(reply)
    await db.commit()
    await db.refresh(reply)
    return QuickReplyResponse.model_validate(reply)


# ── PATCH /quick-replies/{id} ─────────────────────────────────


@router.patch("/quick-replies/{reply_id}", response_model=QuickReplyResponse)
async def update_quick_reply(
    reply_id: uuid.UUID,
    body: QuickReplyUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(_STAFF)],
) -> QuickReplyResponse:
    reply = await _get_or_404(reply_id, db)

    if body.shortcut is not None and body.shortcut != reply.shortcut:
        await _reject_duplicate_shortcut(body.shortcut, db, ignore_id=reply_id)
        reply.shortcut = body.shortcut

    if body.title is not None:
        reply.title = body.title.strip()
    if body.content is not None:
        reply.content = body.content.strip()
    if body.is_active is not None:
        reply.is_active = body.is_active

    reply.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(reply)
    return QuickReplyResponse.model_validate(reply)


# ── DELETE /quick-replies/{id} ────────────────────────────────


@router.delete("/quick-replies/{reply_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quick_reply(
    reply_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(_STAFF)],
) -> None:
    reply = await _get_or_404(reply_id, db)
    await db.delete(reply)
    await db.commit()
