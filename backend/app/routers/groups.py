"""
Groups, Companies and Client-assignment endpoints.

Permissões:
  Todos os endpoints — admin | technician, exceto:
  DELETE /groups/{id}                  — admin
  DELETE /groups/{id}/companies/{id}   — admin
  As duas exclusões recusam (409) o que ainda tem conteúdo; ver
  "Exclusão de grupo e empresa" mais abaixo.

Consulta transversal (tela de Empresas, só leitura):
  GET /companies          — todas as empresas, paginado, busca por nome/CNPJ
  GET /companies/{id}     — detalhe sem precisar do grupo
  Ficam DEPOIS de `/companies/suggestions` no arquivo: o FastAPI casa rota na
  ordem de registro, e `/companies/{id}` antes dela tentaria ler "suggestions"
  como UUID e responderia 422.
"""

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import authorize
from app.models.models import (
    AuditAction,
    AuditLog,
    Company,
    CompanyNote,
    Equipment,
    Group,
    GroupNote,
    User,
    UserRole,
    UserStatus,
)
from app.schemas.groups import (
    AssignClientRequest,
    ClientInCompany,
    CompanyCreate,
    CompanyDetail,
    CompanyFromSuggestionResponse,
    CompanyNoteCreate,
    CompanyNoteResponse,
    CompanyResponse,
    CompanyStaffDetail,
    CompanyStaffItem,
    CompanyStaffListResponse,
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
# O nome acima é antigo e engana: `_AdminDep` aceita técnico. As exclusões de
# grupo e empresa são as únicas rotas deste router que exigem admin de fato.
_SoAdminDep = Annotated[User, Depends(authorize(UserRole.admin))]
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


async def _clientes_vinculados(db: AsyncSession, company_id: uuid.UUID) -> list[ClientInCompany]:
    """Quem tem o VÍNCULO oficial (`users.company_id`) — não quem digitou o nome."""
    linhas = await db.execute(select(User).where(User.company_id == company_id).order_by(User.name))
    return [
        ClientInCompany(
            id=u.id,
            name=u.name,
            email=u.email,
            phone=u.phone,
            client_notes=u.client_notes,
        )
        for u in linhas.scalars().all()
    ]


async def _contagem_de_equipamentos_por_empresa(
    db: AsyncSession, company_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """
    Equipamentos cujo RESPONSÁVEL tem vínculo oficial com a empresa.

    O equipamento não tem empresa própria; a dele é a do responsável. Conta os
    inativos também — é o mesmo conjunto que `GET /equipments?company_id=`
    devolve sem filtro de status, e as duas telas não podem discordar.
    """
    if not company_ids:
        return {}
    rows = await db.execute(
        select(User.company_id, func.count(Equipment.id))
        .join(User, User.id == Equipment.owner_id)
        .where(User.company_id.in_(company_ids))
        .group_by(User.company_id)
    )
    return {cid: total for cid, total in rows}


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


# ── Exclusão de grupo e empresa ───────────────────────────────
#
# Até 04/11/2026 excluir um grupo apagava as empresas e as notas dele em
# cascata (`companies.group_id` ON DELETE CASCADE + `delete-orphan` no ORM), e
# excluir uma empresa apagava as notas e soltava os clientes (`users.company_id`
# ON DELETE SET NULL) — sem contar, sem auditar, e o técnico podia (F1-D1).
# Agora só sai o que está vazio; o resto recusa com 409 e as contagens. As FKs
# continuam como estão: a recusa vem antes delas, e trocar o ondelete é
# mudança de model, fora desta entrega.
#
# A trava é `FOR UPDATE` na linha mãe, e o modo importa. Toda escrita que cria
# um filho (empresa, nota, vínculo de cliente) passa pela checagem de FK, e o
# PostgreSQL faz essa checagem pegando `FOR KEY SHARE` na linha mãe. `FOR
# UPDATE` conflita com `FOR KEY SHARE`; `FOR NO KEY UPDATE` não. Então:
#   - filho escrito e ainda não comitado → a exclusão espera o commit dele e,
#     ao contar, já o vê: 409;
#   - exclusão travou primeiro → a escrita do filho espera; se a exclusão
#     comitar, a escrita falha na FK e não grava nada.
# Contar sem trava não basta: o filho não comitado é invisível à contagem, e a
# cascata o apagaria assim que ele comitasse — medido em
# `test_exclusao_grupos_empresas_postgres.py` antes da correção.
#
# Recusa não grava `audit_logs`: vai só para o log da aplicação, com ids e
# contagens (a mesma decisão da F1-A, ver `users.py::_registra_recusa`).


async def _conta(db: AsyncSession, consulta: Select[tuple[int]]) -> int:
    return (await db.execute(consulta)).scalar_one()


async def _dependentes_do_grupo(db: AsyncSession, group_id: uuid.UUID) -> dict[str, int]:
    empresas_do_grupo = select(Company.id).where(Company.group_id == group_id)
    return {
        "empresas": await _conta(
            db, select(func.count()).select_from(Company).where(Company.group_id == group_id)
        ),
        "clientes_vinculados": await _conta(
            db,
            select(func.count()).select_from(User).where(User.company_id.in_(empresas_do_grupo)),
        ),
        "notas_do_grupo": await _conta(
            db, select(func.count()).select_from(GroupNote).where(GroupNote.group_id == group_id)
        ),
        "notas_de_empresas": await _conta(
            db,
            select(func.count())
            .select_from(CompanyNote)
            .where(CompanyNote.company_id.in_(empresas_do_grupo)),
        ),
    }


async def _dependentes_da_empresa(db: AsyncSession, company_id: uuid.UUID) -> dict[str, int]:
    # Não reaproveita `_company_client_count`/`_company_note_count`: a segunda
    # engole erro com `rollback()`, e um rollback aqui soltaria a trava.
    return {
        "clientes_vinculados": await _conta(
            db, select(func.count()).select_from(User).where(User.company_id == company_id)
        ),
        "notas": await _conta(
            db,
            select(func.count())
            .select_from(CompanyNote)
            .where(CompanyNote.company_id == company_id),
        ),
    }


_ROTULOS = {
    "empresas": "empresa(s)",
    "clientes_vinculados": "cliente(s) vinculado(s)",
    "notas_do_grupo": "nota(s) do grupo",
    "notas_de_empresas": "nota(s) de empresa",
    "notas": "nota(s)",
}


def _recusa_exclusao(
    entidade: str, alvo_id: uuid.UUID, ator: User, contagens: dict[str, int]
) -> HTTPException:
    """Monta o 409 e deixa o aviso no log. Só números: nunca quem são os clientes."""
    presentes = {chave: n for chave, n in contagens.items() if n}
    logger.warning(
        "Exclusão recusada (tem conteúdo): entidade={} alvo={} ator={} contagens={}",
        entidade,
        alvo_id,
        ator.id,
        presentes,
    )
    itens = ", ".join(f"{n} {_ROTULOS[chave]}" for chave, n in presentes.items())
    artigo, pronome = ("o grupo", "ele") if entidade == "group" else ("a empresa", "ela")
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"Não é possível excluir {artigo}: {pronome} ainda tem {itens}. "
            f"Remova ou mova esses itens antes de excluir {artigo}."
        ),
    )


_ERRO_MUDOU_DURANTE = (
    "Não foi possível excluir: o registro mudou durante a operação. "
    "Atualize a página e tente de novo."
)


async def _exclui_e_comita(db: AsyncSession, alvo: Group | Company) -> None:
    """Exclusão com rede: uma FK que a contagem não previu vira 409, não 500.

    A exclusão e a auditoria são a mesma transação — se uma falha, nenhuma fica.
    O `delete` entra na rede junto com o commit: ele carrega as coleções em
    cascata, e esse carregamento faz autoflush da auditoria já adicionada.
    """
    try:
        await db.delete(alvo)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=_ERRO_MUDOU_DURANTE
        ) from None


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group_id: uuid.UUID, db: _DBDep, actor: _SoAdminDep) -> None:
    g = (
        await db.execute(select(Group).where(Group.id == group_id).with_for_update())
    ).scalar_one_or_none()
    if g is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo não encontrado")

    contagens = await _dependentes_do_grupo(db, group_id)
    if any(contagens.values()):
        raise _recusa_exclusao("group", group_id, actor, contagens)

    db.add(
        AuditLog(
            user_id=actor.id,
            action=AuditAction.delete,
            entity_type="group",
            entity_id=group_id,
            old_data={"name": g.name, **contagens},
        )
    )
    await _exclui_e_comita(db, g)


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
    clients = await _clientes_vinculados(db, company_id)
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
    group_id: uuid.UUID, company_id: uuid.UUID, db: _DBDep, actor: _SoAdminDep
) -> None:
    c = (
        await db.execute(
            select(Company)
            .where(Company.id == company_id, Company.group_id == group_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa não encontrada")

    contagens = await _dependentes_da_empresa(db, company_id)
    if any(contagens.values()):
        raise _recusa_exclusao("company", company_id, actor, contagens)

    # Nome e CNPJ dizem QUAL empresa saiu — dados da empresa, não de pessoa.
    # Nenhum dado de cliente entra: a exclusão só passa sem cliente vinculado.
    db.add(
        AuditLog(
            user_id=actor.id,
            action=AuditAction.delete,
            entity_type="company",
            entity_id=company_id,
            old_data={"name": c.name, "cnpj": c.cnpj, "group_id": str(c.group_id), **contagens},
        )
    )
    await _exclui_e_comita(db, c)


# ── Client assignment ─────────────────────────────────────────
#
# `users.company_id` é a única autoridade sobre a empresa de um cliente (ver
# "Qual é a autoridade…" em docs/decisoes-e-regras.md), e já decide escopo: a
# Helô recorta o histórico de chamados por ele. Por isso o vínculo tem regra
# própria desde a F2-A1:
#   - cliente sem empresa → vincula (201) e audita;
#   - já na MESMA empresa → nada muda (200), sem auditoria;
#   - em OUTRA empresa → 409. Até aqui `assign_client` sobrescrevia: mover
#     cliente de empresa acontecia sem aviso e sem rastro. Transferência, se
#     vier, é operação própria, explícita;
#   - cliente inativo ou anonimizado → 409.
# Recusa não grava `audit_logs` (decisão da F1-A): só o aviso no log.
#
# Ordem das travas, a mesma nas três rotas: ATOR (`FOR KEY SHARE`) → grupo ou
# empresa (`FOR KEY SHARE`) → clientes (`FOR UPDATE`, em ordem de id).
#   - O ator vem primeiro porque o INSERT em `audit_logs` checa a FK `user_id`
#     pegando `FOR KEY SHARE` na linha dele, e as alterações de conta da F1-A
#     (`_trava_para_alterar_conta`) travam TODOS os admins com `FOR UPDATE` e
#     depois o alvo. Com a auditoria por último, "eu tenho o cliente e espero
#     o ator; ela tem o ator e espera o cliente" é deadlock — medido em
#     PostgreSQL antes desta escrita. Pegando o ator antes do cliente, quem
#     chega depois espera sem segurar nada que a outra precise.
#   - A empresa (ou o grupo) em `FOR KEY SHARE` fecha a corrida com a
#     exclusão da F1-D1, que trava a mesma linha com `FOR UPDATE`: ou a
#     exclusão espera o vínculo e recusa (409, há cliente), ou o vínculo espera
#     a exclusão e encontra a empresa sumida (404) — nunca o 500 da FK.
#   - O cliente em `FOR UPDATE` serializa dois vínculos simultâneos (o segundo
#     relê o vínculo comitado e recebe 409) e o vínculo contra a desativação ou
#     anonimização, que travam a mesma linha.


async def _trava_ator(db: AsyncSession, ator: User) -> None:
    await db.execute(
        select(User.id).where(User.id == ator.id).with_for_update(read=True, key_share=True)
    )


async def _trava_clientes(db: AsyncSession, ids: list[uuid.UUID]) -> list[User]:
    """`FOR UPDATE` em ordem de id: duas listas cruzadas não esperam em círculo.

    `populate_existing`: a linha pode já estar no mapa de identidade da sessão,
    e sem ele o SQLAlchemy devolveria os valores de antes da espera.
    """
    return list(
        (
            await db.execute(
                select(User)
                .where(User.id.in_(ids))
                .order_by(User.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )


def _retrato_do_vinculo(empresa: Company | None) -> dict[str, str | None]:
    if empresa is None:
        return {"company_id": None}
    return {"company_id": str(empresa.id), "group_id": str(empresa.group_id)}


def _audita_vinculo(
    db: AsyncSession,
    ator: User,
    cliente_id: uuid.UUID,
    antes: Company | None,
    depois: Company | None,
) -> None:
    """Mesma transação do vínculo: se um não fica, o outro também não."""
    db.add(
        AuditLog(
            user_id=ator.id,
            action=AuditAction.assign,
            entity_type="user",
            entity_id=cliente_id,
            old_data=_retrato_do_vinculo(antes),
            new_data=_retrato_do_vinculo(depois),
        )
    )


def _cliente_na_empresa(u: User) -> ClientInCompany:
    return ClientInCompany(
        id=u.id, name=u.name, email=u.email, phone=u.phone, client_notes=u.client_notes
    )


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
    actor: _AdminDep,
) -> ClientInCompany | JSONResponse:
    await _trava_ator(db, actor)
    empresa = (
        await db.execute(
            select(Company)
            .where(Company.id == company_id, Company.group_id == group_id)
            .with_for_update(read=True, key_share=True)
        )
    ).scalar_one_or_none()
    if empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa não encontrada")

    travados = await _trava_clientes(db, [body.user_id])
    u = travados[0] if travados else None
    if u is None or u.role != UserRole.client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado")

    # A situação vem antes da idempotência: conta inativa ou anonimizada não
    # recebe confirmação de vínculo, nem do que já existia.
    if u.status != UserStatus.active:
        logger.warning(
            "Vínculo recusado (cliente não ativo): cliente={} empresa={} ator={}",
            u.id,
            company_id,
            actor.id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Só é possível vincular cliente ativo.",
        )

    if u.company_id == company_id:
        return JSONResponse(
            status_code=status.HTTP_200_OK, content=jsonable_encoder(_cliente_na_empresa(u))
        )

    if u.company_id is not None:
        atual = (
            await db.execute(select(Company.name).where(Company.id == u.company_id))
        ).scalar_one_or_none()
        logger.warning(
            "Vínculo recusado (cliente já tem outra empresa): cliente={} empresa_atual={} "
            "empresa_pedida={} ator={}",
            u.id,
            u.company_id,
            company_id,
            actor.id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f'Este cliente já está vinculado à empresa "{atual}". '
                "Desvincule-o antes de vinculá-lo a outra."
            ),
        )

    u.company_id = company_id
    _audita_vinculo(db, actor, u.id, None, empresa)
    await db.commit()
    await db.refresh(u)
    return _cliente_na_empresa(u)


@router.delete(
    "/groups/{group_id}/companies/{company_id}/clients/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unassign_client(
    group_id: uuid.UUID,
    company_id: uuid.UUID,
    client_id: uuid.UUID,
    db: _DBDep,
    actor: _AdminDep,
) -> None:
    await _trava_ator(db, actor)
    empresa = (
        await db.execute(
            select(Company)
            .where(Company.id == company_id, Company.group_id == group_id)
            .with_for_update(read=True, key_share=True)
        )
    ).scalar_one_or_none()
    if empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa não encontrada")

    # Sem filtro de papel nem de situação, como antes: desvincular é o único
    # jeito de limpar a empresa de quem deixou de ser cliente ou está inativo.
    travados = await _trava_clientes(db, [client_id])
    u = travados[0] if travados else None
    if u is None or u.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado nesta empresa"
        )
    u.company_id = None
    _audita_vinculo(db, actor, u.id, empresa, None)
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
    actor: _AdminDep,
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

    Travas na ordem de "Client assignment" (ator → grupo → empresa
    reaproveitada → clientes por id). A conferência acima só vale porque é
    feita com os clientes travados: sem isso, duas confirmações simultâneas
    com o mesmo cliente passavam as duas e a segunda o transferia em silêncio.

    ⚠️ Fica de fora: duas confirmações simultâneas com o MESMO CNPJ e clientes
    diferentes ainda podem criar duas empresas — nada trava "o CNPJ" e
    `companies.cnpj` não é único (DAT-06). É decisão de integridade de empresa,
    não de vínculo.
    """
    await _trava_ator(db, actor)
    grupo = (
        await db.execute(
            select(Group.id).where(Group.id == group_id).with_for_update(read=True, key_share=True)
        )
    ).scalar_one_or_none()
    if grupo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo não encontrado")

    empresa = None
    if body.cnpj:
        empresa = (
            await db.execute(
                select(Company)
                .where(Company.group_id == group_id, Company.cnpj == body.cnpj)
                .with_for_update(read=True, key_share=True)
            )
        ).scalar_one_or_none()

    alvos = await _trava_clientes(db, list(body.client_ids))
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
        logger.warning(
            "Vínculo pela sugestão recusado: grupo={} ator={} indisponiveis={}",
            group_id,
            actor.id,
            sorted(str(u.id) for u in indisponiveis),
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{len(indisponiveis)} cliente(s) mudaram desde que a lista foi carregada "
                "(já têm empresa ou não estão ativos). Recarregue as sugestões."
            ),
        )

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
        db.add(
            AuditLog(
                user_id=actor.id,
                action=AuditAction.create,
                entity_type="company",
                entity_id=empresa.id,
                new_data={"name": empresa.name, "cnpj": empresa.cnpj, "group_id": str(group_id)},
            )
        )

    for u in alvos:
        u.company_id = empresa.id
        _audita_vinculo(db, actor, u.id, None, empresa)

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


# ── Consulta transversal: tela de Empresas (só leitura) ───────
#
# A manutenção continua toda nas rotas por grupo acima: criar, editar,
# excluir, vincular cliente e notas. Estas duas só leem.

# Só dígitos e a pontuação do CNPJ: "11.222.333/0001-81", "222333", "555.666".
# Um nome com dígito ("Filial 2") NÃO cai aqui — senão casaria com qualquer
# CNPJ que tivesse um 2.
_PARECE_CNPJ = re.compile(r"[\d./\-\s]+")


def _busca_de_empresa(termo: str) -> ColumnElement[bool]:
    condicoes = [Company.name.ilike(f"%{termo}%")]
    digitos = re.sub(r"\D", "", termo)
    if digitos and _PARECE_CNPJ.fullmatch(termo):
        # A normalização do CNPJ das empresas antigas nunca rodou em produção:
        # há valor pontuado e valor só com dígitos. Tirar a pontuação dos DOIS
        # lados acha os dois.
        condicoes.append(func.regexp_replace(Company.cnpj, r"\D", "", "g").like(f"%{digitos}%"))
    return or_(*condicoes)


async def _linhas_da_equipe(db: AsyncSession, rows: list[Company]) -> list[CompanyStaffItem]:
    """A página inteira com uma consulta por contagem, e não uma por empresa."""
    ids = [c.id for c in rows]
    clientes = await _contagem_de_clientes_por_empresa(db, ids)
    notas = await _contagem_de_notas_por_empresa(db, ids)
    equipamentos = await _contagem_de_equipamentos_por_empresa(db, ids)
    grupos: dict[uuid.UUID, str] = {}
    ids_de_grupo = {c.group_id for c in rows}
    if ids_de_grupo:
        linhas = await db.execute(select(Group.id, Group.name).where(Group.id.in_(ids_de_grupo)))
        grupos = {gid: nome for gid, nome in linhas.all()}
    return [
        CompanyStaffItem(
            **_company_response(c, clientes.get(c.id, 0), notas.get(c.id, 0)).model_dump(),
            group_name=grupos.get(c.group_id, ""),
            equipment_count=equipamentos.get(c.id, 0),
        )
        for c in rows
    ]


@router.get("/companies", response_model=CompanyStaffListResponse)
async def list_all_companies(
    db: _DBDep,
    _: _AdminDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=100),
    group_id: uuid.UUID | None = Query(default=None),
) -> CompanyStaffListResponse:
    """
    Todas as empresas, de todos os grupos — consulta da equipe.

    O cliente é recusado pelo papel (403), antes de qualquer consulta: ele não
    lista empresas, nem a própria, e não vê os colegas vinculados a ela.
    """
    base = select(Company)
    if group_id is not None:
        base = base.where(Company.group_id == group_id)
    if search:
        base = base.where(_busca_de_empresa(search))

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        (await db.execute(base.order_by(Company.name, Company.id).offset(offset).limit(limit)))
        .scalars()
        .all()
    )
    return CompanyStaffListResponse(
        items=await _linhas_da_equipe(db, list(rows)),
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/companies/{company_id}", response_model=CompanyStaffDetail)
async def get_company_for_staff(
    company_id: uuid.UUID, db: _DBDep, _: _AdminDep
) -> CompanyStaffDetail:
    """O detalhe sem precisar saber o grupo — a tela de Empresas parte do id."""
    c = (await db.execute(select(Company).where(Company.id == company_id))).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa não encontrada")
    (linha,) = await _linhas_da_equipe(db, [c])
    clientes = await _clientes_vinculados(db, c.id)
    return CompanyStaffDetail(
        **linha.model_dump(exclude={"client_count"}),
        client_count=len(clientes),
        clients=clientes,
    )
