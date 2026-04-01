"""
Pydantic v2 schemas for Product and Equipment endpoints.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# ── Product ───────────────────────────────────────────────────


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    version: str | None = Field(default=None, max_length=50)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    version: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None


class ProductResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    description: str | None
    version: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int
    limit: int
    offset: int


# ── Equipment ─────────────────────────────────────────────────


class EquipmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    serial_number: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    description: str | None = None


class EquipmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    serial_number: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    description: str | None = None
    is_active: bool | None = None


class EquipmentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    product_id: uuid.UUID
    name: str
    serial_number: str | None
    model: str | None
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class EquipmentListResponse(BaseModel):
    items: list[EquipmentResponse]
    total: int
    limit: int
    offset: int
