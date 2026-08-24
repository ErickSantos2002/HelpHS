"""Schemas for Groups, Companies, and Client assignment."""

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.base import AppBaseModel
from app.utils.documents import CnpjOpcional

# ── Group schemas ─────────────────────────────────────────────


class GroupCreate(AppBaseModel):
    name: str
    description: str | None = None
    notes: str | None = None


class GroupUpdate(AppBaseModel):
    name: str | None = None
    description: str | None = None
    notes: str | None = None


class GroupResponse(AppBaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    notes: str | None
    company_count: int
    created_at: datetime
    updated_at: datetime


# ── Company schemas ───────────────────────────────────────────


class CompanyCreate(AppBaseModel):
    name: str
    cnpj: CnpjOpcional = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    notes: str | None = None


class CompanyUpdate(AppBaseModel):
    name: str | None = None
    cnpj: CnpjOpcional = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    notes: str | None = None


class CompanyResponse(AppBaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    name: str
    cnpj: str | None
    phone: str | None
    address: str | None
    city: str | None
    state: str | None
    notes: str | None
    client_count: int
    note_count: int
    created_at: datetime
    updated_at: datetime


# ── Client-in-company schemas ─────────────────────────────────


class ClientInCompany(AppBaseModel):
    id: uuid.UUID
    name: str
    email: str
    phone: str | None
    client_notes: str | None


class AssignClientRequest(AppBaseModel):
    user_id: uuid.UUID


class CompanySuggestion(AppBaseModel):
    """
    Empresa candidata, montada a partir do onboarding de clientes sem vínculo.

    Traz os `clients` e não só a contagem: o admin precisa **ver quem** antes
    de confirmar um vínculo em massa, que é ação que ninguém desfaz.
    """

    company_name: str
    cnpj: str | None
    city: str | None
    state: str | None
    address: str | None
    client_count: int
    clients: list[ClientInCompany] = []


class CreateCompanyFromSuggestion(AppBaseModel):
    """
    Cria (ou reaproveita) a empresa e vincula os clientes que o admin confirmou.

    `client_ids` é a lista **explícita** que a tela mostrou, não um critério
    que o servidor refaz: o que foi visto é o que é gravado. Refazer a consulta
    aqui abriria a janela de vincular gente que apareceu entre a tela e o
    clique.
    """

    name: str
    cnpj: CnpjOpcional = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    notes: str | None = None
    client_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=200)


class CompanyFromSuggestionResponse(AppBaseModel):
    """
    `company_created` diz se a empresa é nova ou foi reaproveitada.

    O status é sempre `201` porque a requisição sempre cria alguma coisa — os
    vínculos. Se a linha de `companies` era nova ou não é **dado**, não
    protocolo, e mentir `201` sobre uma empresa reaproveitada seria pior.
    """

    company: CompanyResponse
    company_created: bool
    linked_clients: list[ClientInCompany]


class UpdateClientNotesRequest(AppBaseModel):
    client_notes: str | None = None


# ── Detail responses (with nested children) ───────────────────


class CompanyDetail(CompanyResponse):
    clients: list[ClientInCompany] = []


class GroupDetail(GroupResponse):
    companies: list[CompanyResponse] = []


# ── Group Note schemas ────────────────────────────────────────


class GroupNoteCreate(AppBaseModel):
    content: str


class GroupNoteResponse(AppBaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    author_id: uuid.UUID
    author_name: str
    content: str
    created_at: datetime


# ── Company Note schemas ──────────────────────────────────────


class CompanyNoteCreate(AppBaseModel):
    content: str


class CompanyNoteResponse(AppBaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    author_id: uuid.UUID
    author_name: str
    content: str
    created_at: datetime
