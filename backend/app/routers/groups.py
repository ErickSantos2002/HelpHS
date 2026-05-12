"""
Groups, Companies and Client-assignment endpoints.

Permissões:
  Todos os endpoints — admin only
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import authorize
from app.models.models import Company, Group, GroupNote, User, UserRole, UserStatus
from app.schemas.groups import (
    AssignClientRequest,
    ClientInCompany,
    CompanyCreate,
    CompanyDetail,
    CompanyResponse,
    CompanyUpdate,
    GroupCreate,
    GroupDetail,
    GroupNoteCreate,
    GroupNoteResponse,
    GroupResponse,
    GroupUpdate,
    UpdateClientNotesRequest,
)

router = APIRouter(tags=["Groups"])

_AdminDep = Annotated[User, Depends(authorize(UserRole.admin))]
_DBDep = Annotated[AsyncSession, Depends(get_db)]


# ── helpers ───────────────────────────────────────────────────


async def _get_group_or_404(db: AsyncSession, group_id: uuid.UUID) -> Group:
    row = (await db.execute(select(Group).where(Group.id == group_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo não encontrado")
    return row


async def _get_company_or_404(
    db: AsyncSession, group_id: uuid.UUID, company_id: uuid.UUID
) -> Company:
    row = (
        await db.execute(
            select(Company).where(Company.id == company_id, Company.group_id == group_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa não encontrada")
    return row


async def _company_client_count(db: AsyncSession, company_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(User).where(User.company_id == company_id)
        )
    ).scalar_one()


async def _group_company_count(db: AsyncSession, group_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(Company).where(Company.group_id == group_id)
        )
    ).scalar_one()


async def _company_to_response(db: AsyncSession, c: Company) -> CompanyResponse:
    return CompanyResponse(
        id=c.id,
        group_id=c.group_id,
        name=c.name,
        cnpj=c.cnpj,
        phone=c.phone,
        address=c.address,
        city=c.city,
        state=c.state,
        notes=c.notes,
        client_count=await _company_client_count(db, c.id),
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


async def _group_to_response(db: AsyncSession, g: Group) -> GroupResponse:
    return GroupResponse(
        id=g.id,
        name=g.name,
        description=g.description,
        notes=g.notes,
        company_count=await _group_company_count(db, g.id),
        created_at=g.created_at,
        updated_at=g.updated_at,
    )


# ── Groups CRUD ───────────────────────────────────────────────


@router.get("/groups", response_model=list[GroupResponse])
async def list_groups(db: _DBDep, _: _AdminDep) -> list[GroupResponse]:
    rows = (await db.execute(select(Group).order_by(Group.name))).scalars().all()
    return [await _group_to_response(db, g) for g in rows]


@router.post("/groups", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(body: GroupCreate, db: _DBDep, _: _AdminDep) -> GroupResponse:
    g = Group(name=body.name, description=body.description, notes=body.notes)
    db.add(g)
    await db.commit()
    await db.refresh(g)
    return await _group_to_response(db, g)


@router.get("/groups/{group_id}", response_model=GroupDetail)
async def get_group(group_id: uuid.UUID, db: _DBDep, _: _AdminDep) -> GroupDetail:
    g = await _get_group_or_404(db, group_id)
    companies_rows = (
        await db.execute(select(Company).where(Company.group_id == group_id).order_by(Company.name))
    ).scalars().all()
    companies = [await _company_to_response(db, c) for c in companies_rows]
    return GroupDetail(
        id=g.id,
        name=g.name,
        description=g.description,
        notes=g.notes,
        company_count=len(companies),
        created_at=g.created_at,
        updated_at=g.updated_at,
        companies=companies,
    )


@router.put("/groups/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: uuid.UUID, body: GroupUpdate, db: _DBDep, _: _AdminDep
) -> GroupResponse:
    g = await _get_group_or_404(db, group_id)
    if body.name is not None:
        g.name = body.name
    if body.description is not None:
        g.description = body.description
    if body.notes is not None:
        g.notes = body.notes
    await db.commit()
    await db.refresh(g)
    return await _group_to_response(db, g)


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group_id: uuid.UUID, db: _DBDep, _: _AdminDep) -> None:
    g = await _get_group_or_404(db, group_id)
    await db.delete(g)
    await db.commit()


# ── Companies CRUD ────────────────────────────────────────────


@router.get("/groups/{group_id}/companies", response_model=list[CompanyResponse])
async def list_companies(
    group_id: uuid.UUID, db: _DBDep, _: _AdminDep
) -> list[CompanyResponse]:
    await _get_group_or_404(db, group_id)
    rows = (
        await db.execute(select(Company).where(Company.group_id == group_id).order_by(Company.name))
    ).scalars().all()
    return [await _company_to_response(db, c) for c in rows]


@router.post(
    "/groups/{group_id}/companies",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_company(
    group_id: uuid.UUID, body: CompanyCreate, db: _DBDep, _: _AdminDep
) -> CompanyResponse:
    await _get_group_or_404(db, group_id)
    c = Company(
        group_id=group_id,
        name=body.name,
        cnpj=body.cnpj,
        phone=body.phone,
        address=body.address,
        city=body.city,
        state=body.state,
        notes=body.notes,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return await _company_to_response(db, c)


@router.get("/groups/{group_id}/companies/{company_id}", response_model=CompanyDetail)
async def get_company(
    group_id: uuid.UUID, company_id: uuid.UUID, db: _DBDep, _: _AdminDep
) -> CompanyDetail:
    c = await _get_company_or_404(db, group_id, company_id)
    clients_rows = (
        await db.execute(select(User).where(User.company_id == company_id).order_by(User.name))
    ).scalars().all()
    clients = [
        ClientInCompany(
            id=u.id,
            name=u.name,
            email=u.email,
            phone=u.phone,
            client_notes=u.client_notes,
        )
        for u in clients_rows
    ]
    return CompanyDetail(
        id=c.id,
        group_id=c.group_id,
        name=c.name,
        cnpj=c.cnpj,
        phone=c.phone,
        address=c.address,
        city=c.city,
        state=c.state,
        notes=c.notes,
        client_count=len(clients),
        created_at=c.created_at,
        updated_at=c.updated_at,
        clients=clients,
    )


@router.put("/groups/{group_id}/companies/{company_id}", response_model=CompanyResponse)
async def update_company(
    group_id: uuid.UUID,
    company_id: uuid.UUID,
    body: CompanyUpdate,
    db: _DBDep,
    _: _AdminDep,
) -> CompanyResponse:
    c = await _get_company_or_404(db, group_id, company_id)
    for field in ("name", "cnpj", "phone", "address", "city", "state", "notes"):
        val = getattr(body, field)
        if val is not None:
            setattr(c, field, val)
    await db.commit()
    await db.refresh(c)
    return await _company_to_response(db, c)


@router.delete(
    "/groups/{group_id}/companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_company(
    group_id: uuid.UUID, company_id: uuid.UUID, db: _DBDep, _: _AdminDep
) -> None:
    c = await _get_company_or_404(db, group_id, company_id)
    await db.delete(c)
    await db.commit()


# ── Client assignment ─────────────────────────────────────────


@router.post(
    "/groups/{group_id}/companies/{company_id}/clients",
    response_model=ClientInCompany,
    status_code=status.HTTP_201_CREATED,
)
async def assign_client(
    group_id: uuid.UUID,
    company_id: uuid.UUID,
    body: AssignClientRequest,
    db: _DBDep,
    _: _AdminDep,
) -> ClientInCompany:
    await _get_company_or_404(db, group_id, company_id)
    u = (
        await db.execute(
            select(User).where(User.id == body.user_id, User.role == UserRole.client)
        )
    ).scalar_one_or_none()
    if u is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado"
        )
    u.company_id = company_id
    await db.commit()
    await db.refresh(u)
    return ClientInCompany(
        id=u.id, name=u.name, email=u.email, phone=u.phone, client_notes=u.client_notes
    )


@router.delete(
    "/groups/{group_id}/companies/{company_id}/clients/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unassign_client(
    group_id: uuid.UUID,
    company_id: uuid.UUID,
    client_id: uuid.UUID,
    db: _DBDep,
    _: _AdminDep,
) -> None:
    await _get_company_or_404(db, group_id, company_id)
    u = (
        await db.execute(
            select(User).where(User.id == client_id, User.company_id == company_id)
        )
    ).scalar_one_or_none()
    if u is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado nesta empresa"
        )
    u.company_id = None
    await db.commit()


@router.patch(
    "/groups/{group_id}/companies/{company_id}/clients/{client_id}/notes",
    response_model=ClientInCompany,
)
async def update_client_notes(
    group_id: uuid.UUID,
    company_id: uuid.UUID,
    client_id: uuid.UUID,
    body: UpdateClientNotesRequest,
    db: _DBDep,
    _: _AdminDep,
) -> ClientInCompany:
    await _get_company_or_404(db, group_id, company_id)
    u = (
        await db.execute(
            select(User).where(User.id == client_id, User.company_id == company_id)
        )
    ).scalar_one_or_none()
    if u is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado nesta empresa"
        )
    u.client_notes = body.client_notes
    await db.commit()
    await db.refresh(u)
    return ClientInCompany(
        id=u.id, name=u.name, email=u.email, phone=u.phone, client_notes=u.client_notes
    )


# ── Unassigned clients list (for assignment modal) ────────────


@router.get("/clients/unassigned", response_model=list[ClientInCompany])
async def list_unassigned_clients(db: _DBDep, _: _AdminDep) -> list[ClientInCompany]:
    rows = (
        await db.execute(
            select(User)
            .where(
                User.role == UserRole.client,
                User.status == UserStatus.active,
                User.company_id.is_(None),
            )
            .order_by(User.name)
        )
    ).scalars().all()
    return [
        ClientInCompany(id=u.id, name=u.name, email=u.email, phone=u.phone, client_notes=u.client_notes)
        for u in rows
    ]


# ── Company suggestions from client onboarding data ───────────


@router.get("/companies/suggestions")
async def get_company_suggestions(db: _DBDep, _: _AdminDep) -> list[dict]:
    """Unique companies from client onboarding not yet linked to any group."""
    rows = (
        await db.execute(
            select(
                User.company_name,
                User.cnpj,
                User.company_city,
                User.company_state,
                User.company_address,
                func.count().label("client_count"),
            )
            .where(
                User.role == UserRole.client,
                User.status == UserStatus.active,
                User.company_name.is_not(None),
                User.company_id.is_(None),
            )
            .group_by(
                User.company_name,
                User.cnpj,
                User.company_city,
                User.company_state,
                User.company_address,
            )
            .order_by(User.company_name)
        )
    ).all()
    return [
        {
            "company_name": r.company_name,
            "cnpj": r.cnpj,
            "city": r.company_city,
            "state": r.company_state,
            "address": r.company_address,
            "client_count": r.client_count,
        }
        for r in rows
    ]


# ── Group Notes ───────────────────────────────────────────────


@router.get("/groups/{group_id}/notes", response_model=list[GroupNoteResponse])
async def list_group_notes(
    group_id: uuid.UUID, db: _DBDep, _: _AdminDep
) -> list[GroupNoteResponse]:
    await _get_group_or_404(db, group_id)
    rows = (
        await db.execute(
            select(GroupNote, User.name.label("author_name"))
            .join(User, User.id == GroupNote.author_id)
            .where(GroupNote.group_id == group_id)
            .order_by(GroupNote.created_at.desc())
        )
    ).all()
    return [
        GroupNoteResponse(
            id=row.GroupNote.id,
            group_id=row.GroupNote.group_id,
            author_id=row.GroupNote.author_id,
            author_name=row.author_name,
            content=row.GroupNote.content,
            created_at=row.GroupNote.created_at,
        )
        for row in rows
    ]


@router.post(
    "/groups/{group_id}/notes",
    response_model=GroupNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_group_note(
    group_id: uuid.UUID, body: GroupNoteCreate, db: _DBDep, actor: _AdminDep
) -> GroupNoteResponse:
    await _get_group_or_404(db, group_id)
    note = GroupNote(group_id=group_id, author_id=actor.id, content=body.content)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return GroupNoteResponse(
        id=note.id,
        group_id=note.group_id,
        author_id=note.author_id,
        author_name=actor.name,
        content=note.content,
        created_at=note.created_at,
    )


@router.delete("/groups/{group_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group_note(
    group_id: uuid.UUID, note_id: uuid.UUID, db: _DBDep, actor: _AdminDep
) -> None:
    note = (
        await db.execute(
            select(GroupNote).where(GroupNote.id == note_id, GroupNote.group_id == group_id)
        )
    ).scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nota não encontrada")
    await db.delete(note)
    await db.commit()
