"""Schemas for Groups, Companies, and Client assignment."""

import uuid
from datetime import datetime

from pydantic import field_validator

from app.schemas.base import AppBaseModel


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
    cnpj: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    notes: str | None = None


class CompanyUpdate(AppBaseModel):
    name: str | None = None
    cnpj: str | None = None
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


class UpdateClientNotesRequest(AppBaseModel):
    client_notes: str | None = None


# ── Detail responses (with nested children) ───────────────────


class CompanyDetail(CompanyResponse):
    clients: list[ClientInCompany] = []


class GroupDetail(GroupResponse):
    companies: list[CompanyResponse] = []
