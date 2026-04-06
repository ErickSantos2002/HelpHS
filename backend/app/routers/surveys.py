"""
Pesquisa de satisfação (CSAT).

Permissões:
  POST /tickets/{id}/survey   — client que criou o ticket
                                 (ticket deve estar resolved ou closed)
  GET  /tickets/{id}/survey   — qualquer autenticado com acesso ao ticket
  GET  /surveys               — admin, technician (relatórios)

Regras:
  - Uma pesquisa por ticket (unique constraint no model)
  - Avaliação de 1 a 5
  - Não pode ser alterada após envio
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import authorize, get_current_user
from app.models.models import (
    AuditAction,
    AuditLog,
    SatisfactionSurvey,
    Ticket,
    TicketStatus,
    User,
    UserRole,
)
from app.schemas.survey import SurveyCreate, SurveyListResponse, SurveyResponse

router = APIRouter(tags=["Surveys"])

_ELIGIBLE_STATUSES = frozenset({TicketStatus.resolved, TicketStatus.closed})


def _audit(db: AsyncSession, actor_id: uuid.UUID, entity_id: uuid.UUID) -> None:
    db.add(
        AuditLog(
            user_id=actor_id,
            action=AuditAction.create,
            entity_type="survey",
            entity_id=entity_id,
        )
    )


# ── Helpers ───────────────────────────────────────────────────


async def _get_ticket_or_404(ticket_id: uuid.UUID, db: AsyncSession) -> Ticket:
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return ticket


# ═══════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════


@router.post(
    "/tickets/{ticket_id}/survey",
    response_model=SurveyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_survey(
    ticket_id: uuid.UUID,
    body: SurveyCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> SurveyResponse:
    ticket = await _get_ticket_or_404(ticket_id, db)

    # Only the ticket creator can submit the survey
    if ticket.creator_id != actor.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Ticket must be resolved or closed
    if ticket.status not in _ELIGIBLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Survey can only be submitted for resolved or closed tickets",
        )

    survey = SatisfactionSurvey(
        id=uuid.uuid4(),
        ticket_id=ticket_id,
        user_id=actor.id,
        rating=body.rating,
        comment=body.comment,
        created_at=datetime.now(UTC),
    )
    db.add(survey)
    _audit(db, actor.id, survey.id)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Survey already submitted for this ticket",
        )

    await db.refresh(survey)
    return SurveyResponse.model_validate(survey)


@router.get("/tickets/{ticket_id}/survey", response_model=SurveyResponse)
async def get_survey(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> SurveyResponse:
    ticket = await _get_ticket_or_404(ticket_id, db)

    # Client can only see survey for their own ticket
    if actor.role == UserRole.client and ticket.creator_id != actor.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(SatisfactionSurvey).where(SatisfactionSurvey.ticket_id == ticket_id)
    )
    survey = result.scalar_one_or_none()
    if not survey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No survey found for this ticket"
        )

    return SurveyResponse.model_validate(survey)


@router.get("/surveys", response_model=SurveyListResponse)
async def list_surveys(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    rating: int | None = Query(default=None, ge=1, le=5),
) -> SurveyListResponse:
    base = select(SatisfactionSurvey)
    if rating is not None:
        base = base.where(SatisfactionSurvey.rating == rating)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    avg_result = await db.execute(
        select(func.avg(SatisfactionSurvey.rating)).select_from(base.subquery())
    )
    avg_raw = avg_result.scalar_one()
    average_rating = round(float(avg_raw), 2) if avg_raw is not None else None

    rows = await db.execute(
        base.order_by(SatisfactionSurvey.created_at.desc()).offset(offset).limit(limit)
    )
    surveys = rows.scalars().all()

    return SurveyListResponse(
        items=[SurveyResponse.model_validate(s) for s in surveys],
        total=total,
        average_rating=average_rating,
        limit=limit,
        offset=offset,
    )
