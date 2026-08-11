"""
Pydantic v2 schemas for Ticket endpoints.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict, Field

from app.models.models import TicketCategory, TicketPriority, TicketStatus
from app.schemas.base import AppBaseModel
from app.schemas.tag import TagResponse

# Um chamado sobre a frota inteira de um cliente ainda é um chamado só; o teto
# existe para o campo não virar depósito de equipamento sem relação com o caso.
MAX_EQUIPMENTS_PER_TICKET = 20


class TicketCreate(AppBaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    priority: TicketPriority = TicketPriority.medium
    category: TicketCategory = TicketCategory.general
    product_id: uuid.UUID | None = None
    equipment_ids: list[uuid.UUID] = Field(
        default_factory=list, max_length=MAX_EQUIPMENTS_PER_TICKET
    )
    client_observation: str | None = Field(default=None, max_length=2000)


class TicketUpdate(AppBaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    priority: TicketPriority | None = None
    category: TicketCategory | None = None
    product_id: uuid.UUID | None = None
    # None = não mexe nos equipamentos; lista vazia = desvincula todos
    equipment_ids: list[uuid.UUID] | None = Field(
        default=None, max_length=MAX_EQUIPMENTS_PER_TICKET
    )
    technician_notes: str | None = None


class TicketStatusUpdate(AppBaseModel):
    status: TicketStatus
    comment: str | None = Field(default=None, max_length=1000)


class TicketAssign(AppBaseModel):
    assignee_id: uuid.UUID | None = None


class TicketObservationUpdate(AppBaseModel):
    client_observation: str | None = Field(default=None, max_length=2000)


class TicketResolve(AppBaseModel):
    resolution_note: str = Field(..., min_length=1, max_length=5000)


class TicketReopen(AppBaseModel):
    # O motivo é obrigatório: quem for atender de novo precisa saber o que
    # continuou errado, e a nota de resolução original fica no chamado.
    reason: str = Field(..., min_length=5, max_length=2000)


class TicketEquipmentBrief(AppBaseModel):
    """O necessário para exibir o equipamento no chamado, sem a ficha inteira."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    serial_number: str | None = None
    product_id: uuid.UUID | None = None


class TicketResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: uuid.UUID
    protocol: str
    title: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    category: TicketCategory
    creator_id: uuid.UUID
    assignee_id: uuid.UUID | None
    product_id: uuid.UUID | None
    equipments: list[TicketEquipmentBrief] = []
    sla_response_due_at: datetime | None
    sla_resolve_due_at: datetime | None
    sla_response_breach: bool
    sla_resolve_breach: bool
    closed_at: datetime | None
    resolved_at: datetime | None = None
    auto_closed: bool = False
    reopened_at: datetime | None = None
    reopen_count: int = 0
    # Até quando este chamado ainda aceita reabertura. Vem calculado do backend
    # para que o frontend não precise repetir a conta de dias úteis.
    reopen_deadline: datetime | None = None
    created_at: datetime
    updated_at: datetime
    assignee_name: str | None = None
    product_name: str | None = None
    technician_notes: str | None = None
    ai_classification: str | None = None
    ai_confidence: float | None = None
    ai_summary: str | None = None
    ai_conversation_summary: str | None = None
    client_observation: str | None = None
    resolution_note: str | None = None
    tags: list[TagResponse] = []


class TicketListResponse(AppBaseModel):
    items: list[TicketResponse]
    total: int
    limit: int
    offset: int


class TicketHistoryResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    user_id: uuid.UUID | None = None  # NULL = ação do sistema
    user_name: str | None = None
    field: str
    old_value: str | None
    new_value: str | None
    comment: str | None
    created_at: datetime


class TicketHistoryListResponse(AppBaseModel):
    items: list[TicketHistoryResponse]
    total: int
    limit: int
    offset: int


class TicketNoteCreate(AppBaseModel):
    content: str = Field(..., min_length=1)


class TicketNoteResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID
    author_name: str
    content: str
    created_at: datetime
