"""
CRUD de usuários.

Permissões:
  POST   /users                   — admin
  GET    /users                   — admin
  GET    /users/me                — qualquer autenticado
  GET    /users/technicians       — admin | technician (lista técnicos ativos)
  GET    /users/{id}              — admin (ou o próprio usuário)
  PATCH  /users/{id}              — admin (ou o próprio usuário, sem mudar role)
  PATCH  /users/{id}/status       — admin
  PATCH  /users/me/lgpd-consent   — qualquer autenticado (próprio consentimento)
  POST   /users/{id}/anonymize    — admin (anonimiza PII — LGPD)
  DELETE /users/{id}              — admin (exclusão, apenas sem tickets)
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import authorize, get_current_user, hash_password, verify_password
from app.models.models import AuditAction, AuditLog, Ticket, User, UserRole, UserStatus
from app.schemas.user import (
    LGPDConsentUpdate,
    PasswordChange,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserStatusUpdate,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["Users"])


# ── Helpers ───────────────────────────────────────────────────


def _to_response(user: User) -> UserResponse:
    return UserResponse.model_validate(user)


def _audit(
    db: AsyncSession, action: AuditAction, actor_id: uuid.UUID, target_id: uuid.UUID
) -> None:
    db.add(
        AuditLog(
            user_id=actor_id,
            action=action,
            entity_type="user",
            entity_id=target_id,
        )
    )


# ── POST /users ───────────────────────────────────────────────


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin))],
) -> UserResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    ts = datetime.now(UTC)
    user = User(
        id=uuid.uuid4(),
        name=body.name,
        email=body.email,
        password=hash_password(body.password),
        role=body.role,
        status=UserStatus.active,
        phone=body.phone,
        department=body.department,
        lgpd_consent=body.lgpd_consent,
        lgpd_consent_at=ts if body.lgpd_consent else None,
        created_at=ts,
        updated_at=ts,
    )
    db.add(user)
    _audit(db, AuditAction.create, actor.id, user.id)
    await db.commit()
    await db.refresh(user)
    return _to_response(user)


# ── GET /users ────────────────────────────────────────────────


@router.get("", response_model=UserListResponse)
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin))],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    role: UserRole | None = Query(default=None),
    status_filter: UserStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=100),
) -> UserListResponse:
    base = select(User)
    if role:
        base = base.where(User.role == role)
    if status_filter:
        base = base.where(User.status == status_filter)
    if search:
        pattern = f"%{search}%"
        base = base.where(User.name.ilike(pattern) | User.email.ilike(pattern))

    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()

    rows = await db.execute(base.order_by(User.created_at.desc()).offset(offset).limit(limit))
    users = rows.scalars().all()

    return UserListResponse(
        items=[_to_response(u) for u in users],
        total=total,
        limit=limit,
        offset=offset,
    )


# ── GET /users/me ─────────────────────────────────────────────


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    return _to_response(current_user)


# ── GET /users/technicians ────────────────────────────────────


@router.get("/technicians", response_model=UserListResponse)
async def list_technicians(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> UserListResponse:
    """Active technicians — used by staff to populate assignee filter/dropdown."""
    rows = await db.execute(
        select(User)
        .where(User.role == UserRole.technician, User.status == UserStatus.active)
        .order_by(User.name)
    )
    users = rows.scalars().all()
    return UserListResponse(
        items=[_to_response(u) for u in users], total=len(users), limit=100, offset=0
    )


# ── GET /users/{user_id} ──────────────────────────────────────


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    # Non-admins can only see their own profile
    if current_user.role != UserRole.admin and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return _to_response(user)


# ── PATCH /users/me ───────────────────────────────────────────


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = body.model_dump(exclude_unset=True, exclude={"role"})
    for field, value in update_data.items():
        setattr(user, field, value)

    user.updated_at = datetime.now(UTC)
    _audit(db, AuditAction.update, current_user.id, user.id)
    await db.commit()
    await db.refresh(user)
    return _to_response(user)


# ── POST /users/me/change-password ────────────────────────────


@router.post("/me/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChange,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not verify_password(body.current_password, user.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Senha atual incorreta",
        )

    user.password = hash_password(body.new_password)
    user.updated_at = datetime.now(UTC)
    _audit(db, AuditAction.update, current_user.id, user.id)
    await db.commit()


# ── PATCH /users/{user_id} ────────────────────────────────────


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    # Non-admins can only edit themselves and cannot change role
    if current_user.role != UserRole.admin:
        if current_user.id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        if body.role is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can change roles",
            )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    _audit(db, AuditAction.update, current_user.id, user.id)
    await db.commit()
    await db.refresh(user)
    return _to_response(user)


# ── PATCH /users/{user_id}/status ─────────────────────────────


@router.patch("/{user_id}/status", response_model=UserResponse)
async def update_user_status(
    user_id: uuid.UUID,
    body: UserStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin))],
) -> UserResponse:
    if actor.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot change their own status",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.status = body.status
    _audit(db, AuditAction.status_change, actor.id, user.id)
    await db.commit()
    await db.refresh(user)
    return _to_response(user)


# ── PATCH /users/me/lgpd-consent ──────────────────────────────


@router.patch("/me/lgpd-consent", response_model=UserResponse)
async def update_lgpd_consent(
    body: LGPDConsentUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.lgpd_consent = body.lgpd_consent
    user.lgpd_consent_at = datetime.now(UTC) if body.lgpd_consent else None
    user.updated_at = datetime.now(UTC)
    _audit(db, AuditAction.update, current_user.id, user.id)
    await db.commit()
    await db.refresh(user)
    return _to_response(user)


# ── POST /users/{user_id}/anonymize ───────────────────────────


@router.post("/{user_id}/anonymize", response_model=UserResponse)
async def anonymize_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin))],
) -> UserResponse:
    """Anonimiza os dados pessoais do usuário (LGPD — direito ao esquecimento)."""
    if actor.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot anonymize their own account",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.status == UserStatus.anonymized:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="User is already anonymized"
        )

    ts = datetime.now(UTC)
    user.name = f"Usuário Anonimizado {str(user_id)[:8]}"
    user.email = f"anon_{str(user_id).replace('-', '')}@anonymized.invalid"
    user.phone = None
    user.department = None
    user.avatar_url = None
    user.lgpd_consent = False
    user.lgpd_consent_at = None
    user.status = UserStatus.anonymized
    user.updated_at = ts

    db.add(
        AuditLog(
            user_id=actor.id,
            action=AuditAction.anonymize,
            entity_type="user",
            entity_id=user_id,
            new_data={"anonymized_at": ts.isoformat()},
        )
    )
    await db.commit()
    await db.refresh(user)
    return _to_response(user)


# ── DELETE /users/{user_id} ───────────────────────────────────


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin))],
) -> None:
    """Exclui permanentemente um usuário sem tickets (LGPD)."""
    if actor.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot delete their own account",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    ticket_count = (
        await db.execute(
            select(func.count()).select_from(Ticket).where(Ticket.creator_id == user_id)
        )
    ).scalar_one()
    if ticket_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete user with existing tickets. Use anonymize instead.",
        )

    _audit(db, AuditAction.delete, actor.id, user_id)
    await db.delete(user)
    await db.commit()
