"""
Audit Log endpoint.

Permissões:
  GET /audit-logs — admin only (LGPD compliance)

Filtros disponíveis:
  - action       (AuditAction enum)
  - entity_type  (str)
  - user_id      (uuid)
  - date_from    / date_to (ISO datetime, UTC)
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import authorize
from app.models.models import AuditAction, AuditLog, User, UserRole
from app.schemas.audit import AuditLogListResponse, AuditLogResponse

router = APIRouter(tags=["Audit"])


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin))],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    action: AuditAction | None = Query(default=None),
    entity_type: str | None = Query(default=None, max_length=50),
    user_id: uuid.UUID | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
) -> AuditLogListResponse:
    base = select(AuditLog)

    if action is not None:
        base = base.where(AuditLog.action == action)
    if entity_type is not None:
        base = base.where(AuditLog.entity_type == entity_type)
    if user_id is not None:
        base = base.where(AuditLog.user_id == user_id)
    if date_from is not None:
        base = base.where(AuditLog.created_at >= date_from)
    if date_to is not None:
        base = base.where(AuditLog.created_at <= date_to)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = await db.execute(base.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit))
    entries = rows.scalars().all()

    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(e) for e in entries],
        total=total,
        limit=limit,
        offset=offset,
    )
