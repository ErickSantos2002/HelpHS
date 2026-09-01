"""
Groups, Companies and Client-assignment endpoints.

Permissões:
  Todos os endpoints — admin | technician
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import authorize
from app.models.models import Company, CompanyNote, Group, GroupNote, User, UserRole, UserStatus
from app.schemas.groups import (
    AssignClientRequest,
    ClientInCompany,
    CompanyCreate,
    CompanyDetail,
    CompanyFromSuggestionResponse,
    CompanyNoteCreate,
    CompanyNoteResponse,
    CompanyResponse,
    CompanySuggestion,
    CompanyUpdate,
    CreateCompanyFromSuggestion,
    GroupCreate,
    GroupDetail,
    GroupNoteCreate,
    GroupNoteResponse,
    GroupResponse,
    GroupUpdate,
    UpdateClientNotesRequest,
)

router = APIRouter(tags=["Groups"])

_AdminDep = Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))]
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


async def _company_note_count(db: AsyncSession, company_id: uuid.UUID) -> int:
    try:
        return (
            await db.execute(
                select(func.count())
                .select_from(CompanyNote)
                .where(CompanyNote.company_id == company_id)
            )
        ).scalar_one()
    except Exception:
        await db.rollback()
        return 0


async def _group_company_count(db: AsyncSession, group_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(Company).where(Company.group_id == group_id)
        )
    ).scalar_one()


# ── Contagens em lote ─────────────────────────────────────────
#
# As listagens montavam a resposta item a item, e cada item disparava os seus
# COUNTs: um por grupo na lista de grupos, dois por empresa na de empresas. Com
# 40 empresas isso é 81 consultas para uma tela. As funções abaixo fazem a
# mesma conta para a página inteira, com GROUP BY — mesmo padrão que o
# `list_tickets` já usa para nomes de responsável e produtos.
#
# Quem aparece na listagem sem nenhum filho não volta do GROUP BY: por isso a
# leitura é sempre `.get(id, 0)`, e não indexação direta.


async def _contagem_de_empresas_por_grupo(
    db: AsyncSession, group_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not group_ids:
        return {}
    rows = await db.execute(
        select(Company.group_id, func.count())
        .where(Company.group_id.in_(group_ids))
        .group_by(Company.group_id)
    )
    return {gid: total for gid, total in rows}


async def _contagem_de_clientes_por_empresa(
    db: AsyncSession, company_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not company_ids:
        return {}
    rows = await db.execute(
        select(User.company_id, func.count())
        .where(User.company_id.in_(company_ids))
        .group_by(User.company_id)
    )
    return {cid: total for cid, total in rows}


async def _contagem_de_notas_por_empresa(
    db: AsyncSession, company_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not company_ids:
        return {}
    try:
        rows = await db.execute(
            select(CompanyNote.company_id, func.count())
            .where(CompanyNote.company_id.in_(company_ids))
            .group_by(CompanyNote.company_id)
        )
        return {cid: total for cid, total in rows}
    except Exception:
        # Mesma tolerância do contador individual: a tabela de notas pode não
        # existir num banco antigo, e a listagem não pode cair por causa disso.
        await db.rollback()
        return {}


def _company_response(c: Company, client_count: int, note_count: int) -> CompanyResponse:
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
        client_count=client_count,
        note_count=note_count,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _group_response(g: Group, company_count: int) -> GroupResponse:
    return GroupResponse(
        id=g.id,
        name=g.name,
        description=g.description,
        notes=g.notes,
        company_count=company_count,
        created_at=g.created_at,
        updated_at=g.updated_at,
    )


async def _companies_to_response(db: AsyncSession, rows: list[Company]) -> list[CompanyResponse]:
    """Uma lista inteira com duas consultas de contagem, não duas por empresa."""
    ids = [c.id for c in rows]
    clientes = await _contagem_de_clientes_por_empresa(db, ids)
    notas = await _contagem_de_notas_por_empresa(db, ids)
    return [_company_response(c, clientes.get(c.id, 0), notas.get(c.id, 0)) for c in rows]


async def _company_to_response(db: AsyncSession, c: Company) -> CompanyResponse:
    """Caminho de item único (criar/atualizar) — aqui não há N+1 a evitar."""
    return _company_response(
        c,
        await _company_client_count(db, c.id),
        await _company_note_count(db, c.id),
    )


async def _group_to_response(db: AsyncSession, g: Group) -> GroupResponse:
    """Caminho de item único (criar/atualizar)."""
    return _group_response(g, await _group_company_count(db, g.id))


# ── Groups CRUD ───────────────────────────────────────────────


@router.get("/groups", response_model=list[GroupResponse])
async def list_groups(db: _DBDep, _: _AdminDep) -> list[GroupResponse]:
    rows = list((await db.execute(select(Group).order_by(Group.name))).scalars().all())
    contagens = await _contagem_de_empresas_por_grupo(db, [g.id for g in rows])
    return [_group_response(g, contagens.get(g.id, 0)) for g in rows]


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
        (
            await db.execute(
                select(Company).where(Company.group_id == group_id).order_by(Company.name)
            )
        )
        .scalars()
        .all()
    )
    companies = await _companies_to_response(db, list(companies_rows))
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
    # `description` e `notes` precisam distinguir "não enviado" de "enviado como
    # nulo": são os campos nullable do modelo, e é nulo explícito que o front
    # manda ao limpar o campo. Com `is not None` esse nulo era ignorado e o
    # texto antigo reaparecia no carregamento seguinte, como se a edição não
    # tivesse acontecido. Mesmo defeito que a agenda tinha (`f8e9554`).
    #
    # `name` fica com `is not None` de propósito: é NOT NULL no modelo, e
    # aceitar nulo nele trocaria um bug de usabilidade por erro de integridade.
    if "description" in body.model_fields_set:
        g.description = body.description
    if "notes" in body.model_fields_set:
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
async def list_companies(group_id: uuid.UUID, db: _DBDep, _: _AdminDep) -> list[CompanyResponse]:
    await _get_group_or_404(db, group_id)
    rows = (
        (
            await db.execute(
                select(Company).where(Company.group_id == group_id).order_by(Company.name)
            )
        )
        .scalars()
        .all()
    )
    return await _companies_to_response(db, list(rows))


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
        (await db.execute(select(User).where(User.company_id == company_id).order_by(User.name)))
        .scalars()
        .all()
    )
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
        note_count=await _company_note_count(db, c.id),
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

    # `model_fields_set` diz o que o cliente **mandou**, e é isso que separa
    # "limpar" de "não mexer". A guarda antiga era `if val is not None`, com a
    # qual os dois casos eram indistinguíveis: o admin apagava o CNPJ na tela,
    # salvava, e o valor velho voltava sem nenhum aviso.
    enviados = body.model_fields_set

    # `companies.name` é NOT NULL no banco. Recusar aqui devolve 422 com
    # motivo; deixar passar mandaria NULL para a coluna e o admin veria erro
    # de servidor por um estado que nunca foi válido.
    if "name" in enviados and not body.name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="O nome da empresa não pode ficar vazio.",
        )

    for field in ("name", "cnpj", "phone", "address", "city", "state", "notes"):
        if field in enviados:
            setattr(c, field, getattr(body, field))

    await db.commit()
    await db.refresh(c)
    return await _company_to_response(db, c)


@router.delete("/groups/{group_id}/companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
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
        await db.execute(select(User).where(User.id == body.user_id, User.role == UserRole.client))
    ).scalar_one_or_none()
    if u is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado")
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
        await db.execute(select(User).where(User.id == client_id, User.company_id == company_id))
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
        await db.execute(select(User).where(User.id == client_id, User.company_id == company_id))
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
        (
            await db.execute(
                select(User)
                .where(
                    User.role == UserRole.client,
                    User.status == UserStatus.active,
                    User.company_id.is_(None),
                )
                .order_by(User.name)
            )
        )
        .scalars()
        .all()
    )
    return [
        ClientInCompany(
            id=u.id, name=u.name, email=u.email, phone=u.phone, client_notes=u.client_notes
        )
        for u in rows
    ]


# ── Company suggestions from client onboarding data ───────────


@router.get("/companies/suggestions", response_model=list[CompanySuggestion])
async def get_company_suggestions(db: _DBDep, _: _AdminDep) -> list[CompanySuggestion]:
    """
    Empresas candidatas, vindas do onboarding de clientes ainda sem vínculo.

    O agrupamento continua sendo pela tupla inteira — nome, CNPJ, cidade, UF e
    endereço —, então dois funcionários da mesma empresa que digitaram o
    endereço diferente ainda geram duas sugestões. **É defeito conhecido**
    (defeito 2 do levantamento de 24/08) e segue aqui de propósito: rechavear
    no CNPJ exige decidir qual nome vence quando os clientes discordam e o que
    fazer com quem tem `company_name` mas não tem CNPJ, e as duas são decisões
    de produto.

    O estrago, porém, deixou de existir: com o reaproveitamento por CNPJ do
    `from-suggestion`, os dois cards caem na **mesma** empresa. O defeito virou
    cosmético — dois cliques em vez de um — em vez de gerar duplicata.

    O agrupamento é feito em Python, e não com `GROUP BY`, porque agora a
    sugestão carrega os clientes: o admin precisa ver **quem** antes de
    confirmar.
    """
    linhas = (
        (
            await db.execute(
                select(User)
                .where(
                    User.role == UserRole.client,
                    User.status == UserStatus.active,
                    User.company_name.is_not(None),
                    User.company_id.is_(None),
                )
                .order_by(User.company_name, User.name)
            )
        )
        .scalars()
        .all()
    )

    agrupadas: dict[tuple, CompanySuggestion] = {}
    for u in linhas:
        chave = (u.company_name, u.cnpj, u.company_city, u.company_state, u.company_address)
        sugestao = agrupadas.get(chave)
        if sugestao is None:
            sugestao = CompanySuggestion(
                company_name=u.company_name,
                cnpj=u.cnpj,
                city=u.company_city,
                state=u.company_state,
                address=u.company_address,
                client_count=0,
                clients=[],
            )
            agrupadas[chave] = sugestao
        sugestao.clients.append(
            ClientInCompany(
                id=u.id, name=u.name, email=u.email, phone=u.phone, client_notes=u.client_notes
            )
        )
        sugestao.client_count += 1

    return list(agrupadas.values())


# ── Criar empresa a partir de uma sugestão ────────────────────


@router.post(
    "/groups/{group_id}/companies/from-suggestion",
    response_model=CompanyFromSuggestionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_company_from_suggestion(
    group_id: uuid.UUID,
    body: CreateCompanyFromSuggestion,
    db: _DBDep,
    _: _AdminDep,
) -> CompanyFromSuggestionResponse:
    """
    Cria a empresa e **vincula** os clientes que a sugeriram.

    Existe separado do `create_company` de propósito: o cadastro manual não
    deveria ganhar efeito colateral de vínculo em massa. Uma empresa criada à
    mão que, por coincidência de CNPJ, arrastasse clientes junto seria o
    inverso do defeito que este endpoint conserta — ação que faz **mais** do
    que diz.

    Antes disso, criar pela sugestão não vinculava ninguém: os clientes
    seguiam sem empresa, a sugestão reaparecia e o clique seguinte criava
    duplicata. O contador "3 clientes" prometia o que a ação não cumpria.

    O vínculo é pela lista explícita do corpo, não por uma consulta refeita
    aqui — o que a tela mostrou é o que é gravado.

    Reaproveita empresa do **mesmo grupo** com o mesmo CNPJ em vez de
    duplicar. Não cruza grupo: `Company.group_id` é `NOT NULL` e único, então
    "reusar" uma empresa de outro grupo seria mudá-la de grupo.

    Recusa tudo com `409` se algum cliente já tiver empresa ou não for
    cliente ativo — conflito de estado, não corpo malformado, e é o caso de
    alguém ter vinculado entre a tela e o clique. Nada é gravado: nem os
    vínculos, nem a empresa.
    """
    await _get_group_or_404(db, group_id)

    alvos = (await db.execute(select(User).where(User.id.in_(body.client_ids)))).scalars().all()
    encontrados = {u.id for u in alvos}
    if faltando := set(body.client_ids) - encontrados:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{len(faltando)} cliente(s) não encontrado(s).",
        )

    indisponiveis = [
        u
        for u in alvos
        if u.role != UserRole.client or u.status != UserStatus.active or u.company_id is not None
    ]
    if indisponiveis:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{len(indisponiveis)} cliente(s) mudaram desde que a lista foi carregada "
                "(já têm empresa ou não estão ativos). Recarregue as sugestões."
            ),
        )

    empresa = None
    if body.cnpj:
        empresa = (
            await db.execute(
                select(Company).where(Company.group_id == group_id, Company.cnpj == body.cnpj)
            )
        ).scalar_one_or_none()

    criada = empresa is None
    if empresa is None:
        empresa = Company(
            group_id=group_id,
            name=body.name,
            cnpj=body.cnpj,
            phone=body.phone,
            address=body.address,
            city=body.city,
            state=body.state,
            notes=body.notes,
        )
        db.add(empresa)
        await db.flush()

    for u in alvos:
        u.company_id = empresa.id

    await db.commit()
    await db.refresh(empresa)

    return CompanyFromSuggestionResponse(
        company=await _company_to_response(db, empresa),
        company_created=criada,
        linked_clients=[
            ClientInCompany(
                id=u.id, name=u.name, email=u.email, phone=u.phone, client_notes=u.client_notes
            )
            for u in alvos
        ],
    )


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


# ── Company Notes ─────────────────────────────────────────────


@router.get(
    "/groups/{group_id}/companies/{company_id}/notes",
    response_model=list[CompanyNoteResponse],
)
async def list_company_notes(
    group_id: uuid.UUID, company_id: uuid.UUID, db: _DBDep, _: _AdminDep
) -> list[CompanyNoteResponse]:
    await _get_company_or_404(db, group_id, company_id)
    rows = (
        await db.execute(
            select(CompanyNote, User.name.label("author_name"))
            .join(User, User.id == CompanyNote.author_id)
            .where(CompanyNote.company_id == company_id)
            .order_by(CompanyNote.created_at.desc())
        )
    ).all()
    return [
        CompanyNoteResponse(
            id=row.CompanyNote.id,
            company_id=row.CompanyNote.company_id,
            author_id=row.CompanyNote.author_id,
            author_name=row.author_name,
            content=row.CompanyNote.content,
            created_at=row.CompanyNote.created_at,
        )
        for row in rows
    ]


@router.post(
    "/groups/{group_id}/companies/{company_id}/notes",
    response_model=CompanyNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_company_note(
    group_id: uuid.UUID,
    company_id: uuid.UUID,
    body: CompanyNoteCreate,
    db: _DBDep,
    actor: _AdminDep,
) -> CompanyNoteResponse:
    await _get_company_or_404(db, group_id, company_id)
    note = CompanyNote(company_id=company_id, author_id=actor.id, content=body.content)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return CompanyNoteResponse(
        id=note.id,
        company_id=note.company_id,
        author_id=note.author_id,
        author_name=actor.name,
        content=note.content,
        created_at=note.created_at,
    )


@router.delete(
    "/groups/{group_id}/companies/{company_id}/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_company_note(
    group_id: uuid.UUID,
    company_id: uuid.UUID,
    note_id: uuid.UUID,
    db: _DBDep,
    actor: _AdminDep,
) -> None:
    note = (
        await db.execute(
            select(CompanyNote).where(
                CompanyNote.id == note_id, CompanyNote.company_id == company_id
            )
        )
    ).scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nota não encontrada")
    await db.delete(note)
    await db.commit()
