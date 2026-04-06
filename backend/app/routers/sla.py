"""
SLA Configuration endpoints.

Permissions:
  GET  /sla-configs          — any authenticated user
  PATCH /sla-configs/{id}    — admin only
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import authorize, get_current_user
from app.models.models import AuditAction, AuditLog, SLAConfig, User, UserRole
from app.schemas.sla import SLAConfigResponse, SLAConfigUpdate

router = APIRouter(prefix="/sla-configs", tags=["SLA"])


@router.get("", response_model=list[SLAConfigResponse])
async def list_sla_configs(
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SLAConfig]:
    result = await db.execute(select(SLAConfig).order_by(SLAConfig.level))
    return list(result.scalars().all())


@router.patch("/{config_id}", response_model=SLAConfigResponse)
async def update_sla_config(
    config_id: uuid.UUID,
    payload: SLAConfigUpdate,
    current_user: User = Depends(authorize(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
) -> SLAConfig:
    result = await db.execute(select(SLAConfig).where(SLAConfig.id == config_id))
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SLA config not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)
    config.updated_at = datetime.now(UTC)

    db.add(
        AuditLog(
            user_id=current_user.id,
            action=AuditAction.update,
            resource_type="sla_config",
            resource_id=str(config_id),
            new_values=update_data,
        )
    )

    await db.commit()
    await db.refresh(config)
    return config
