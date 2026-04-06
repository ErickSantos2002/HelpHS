"""
Notificações in-app do usuário autenticado.

Permissões: todos os endpoints são restritos ao próprio usuário.
  GET    /notifications              — listar (filtro: unread_only)
  PATCH  /notifications/read-all    — marcar todas como lidas
  PATCH  /notifications/{id}/read   — marcar uma como lida
  DELETE /notifications/{id}        — remover notificação
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Notification, User
from app.schemas.notification import NotificationListResponse, NotificationResponse

router = APIRouter(tags=["Notifications"])


# ── Helpers ───────────────────────────────────────────────────


async def _get_own_or_404(
    notification_id: uuid.UUID, actor: User, db: AsyncSession
) -> Notification:
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == actor.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return notif


# ═══════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════


@router.get("/notifications", response_model=NotificationListResponse)
async def list_notifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    unread_only: bool = Query(default=False),
) -> NotificationListResponse:
    base = select(Notification).where(Notification.user_id == actor.id)
    if unread_only:
        base = base.where(Notification.read.is_(False))

    # Total matching the filter
    from sqlalchemy import func

    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()

    # Unread count (always, regardless of filter)
    unread_result = await db.execute(
        select(func.count()).where(Notification.user_id == actor.id, Notification.read.is_(False))
    )
    unread = unread_result.scalar_one()

    rows = await db.execute(
        base.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
    )
    notifications = rows.scalars().all()

    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in notifications],
        total=total,
        unread=unread,
        limit=limit,
        offset=offset,
    )


@router.patch("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> None:
    now = datetime.now(UTC)
    await db.execute(
        update(Notification)
        .where(Notification.user_id == actor.id, Notification.read.is_(False))
        .values(read=True, read_at=now)
    )
    await db.commit()


@router.patch("/notifications/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(
    notification_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> NotificationResponse:
    notif = await _get_own_or_404(notification_id, actor, db)
    if not notif.read:
        notif.read = True
        notif.read_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(notif)
    return NotificationResponse.model_validate(notif)


@router.delete("/notifications/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> None:
    notif = await _get_own_or_404(notification_id, actor, db)
    await db.delete(notif)
    await db.commit()
