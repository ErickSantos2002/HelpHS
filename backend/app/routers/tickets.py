"""
CRUD de Tickets.

Permissões:
  POST   /tickets                    — qualquer autenticado (creator = current user)
  GET    /tickets                    — qualquer autenticado
                                       (client vê apenas os próprios tickets)
  GET    /tickets/{id}               — qualquer autenticado
                                       (client só acessa os próprios)
  PATCH  /tickets/{id}               — admin/technician (todos os campos)
                                       client (title/description, apenas se status=open)
  PATCH  /tickets/{id}/status        — admin, technician
  PATCH  /tickets/{id}/assign        — admin, technician
  POST   /tickets/{id}/reopen        — criador (dentro do prazo), admin/technician
  DELETE /tickets/{id}               — admin (cancela o ticket)
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select  # func used in list_tickets subquery
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import authorize, get_current_user
from app.models.models import (
    AuditAction,
    AuditLog,
    Equipment,
    NotificationType,
    Product,
    SLAConfig,
    Ticket,
    TicketHistory,
    TicketNote,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
    ticket_equipments,
    ticket_tags,
)
from app.schemas.ticket import (
    InterruptorDaIA,
    TicketAssign,
    TicketCreate,
    TicketHistoryListResponse,
    TicketHistoryResponse,
    TicketListResponse,
    TicketNoteCreate,
    TicketNoteResponse,
    TicketObservationUpdate,
    TicketReopen,
    TicketResolve,
    TicketResponse,
    TicketStatusUpdate,
    TicketUpdate,
)
from app.services.helo import abre_triagem
from app.services.llm import classify_ticket
from app.services.notifications import commit_e_notificar, notify
from app.services.ticket_lifecycle import (
    can_client_reopen,
    reopen_deadline,
    resolution_reference,
)
from app.utils.crud import get_or_404
from app.utils.protocol import MAX_RETRIES, generate_protocol
from app.utils.sla import (
    _PAUSE_STATUSES,
    add_business_hours,
    apply_sla_config,
    check_breaches,
    pause_sla,
    register_first_response,
    resume_sla,
)
from app.utils.ticket_access import ensure_ticket_visible

router = APIRouter(tags=["Tickets"])

# Uma constante só: a recusa de chamado alheio precisa sair com EXATAMENTE o
# mesmo texto do id inexistente, e dois literais soltos divergem em silêncio.
_CHAMADO_NAO_ENCONTRADO = "Ticket not found"


# ── LLM background classification ────────────────────────────


async def _classify_ticket_async(
    ticket_id: uuid.UUID,
    title: str,
    description: str,
    category: str,
) -> None:
    """Fire-and-forget: classify ticket with LLM and persist results."""
    from app.core.database import AsyncSessionLocal

    result = await classify_ticket(title, description, category)
    if result is None:
        return

    try:
        async with AsyncSessionLocal() as db:
            row = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
            ticket = row.scalar_one_or_none()
            if ticket is None:
                return
            ticket.ai_classification = result["priority"]
            ticket.ai_confidence = result["confidence"]
            ticket.ai_summary = result["summary"]
            ticket.updated_at = datetime.now(UTC)
            await commit_e_notificar(db)
    except Exception as exc:  # noqa: BLE001
        from loguru import logger

        logger.warning(f"Failed to persist LLM classification for ticket {ticket_id}: {exc}")


# ── Valid status transitions ──────────────────────────────────

_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.open: {TicketStatus.in_progress, TicketStatus.cancelled},
    TicketStatus.in_progress: {
        TicketStatus.awaiting_client,
        TicketStatus.awaiting_technical,
        TicketStatus.resolved,
        TicketStatus.cancelled,
    },
    TicketStatus.awaiting_client: {
        TicketStatus.in_progress,
        TicketStatus.awaiting_technical,
        TicketStatus.resolved,
        TicketStatus.cancelled,
    },
    TicketStatus.awaiting_technical: {
        TicketStatus.in_progress,
        TicketStatus.awaiting_client,
        TicketStatus.resolved,
        TicketStatus.cancelled,
    },
    TicketStatus.resolved: {TicketStatus.closed},
    TicketStatus.closed: set(),
    TicketStatus.cancelled: set(),
}


# ── Auto status transition (internal) ────────────────────────


async def _auto_transition(
    db: AsyncSession,
    ticket: Ticket,
    new_status: TicketStatus,
    actor_id: uuid.UUID,
    comment: str = "Transição automática",
) -> bool:
    """Apply a status transition programmatically (no HTTP validation).

    Returns True if the transition was applied, False if it was skipped
    (e.g. the transition is not allowed from the current status).
    The caller is responsible for committing the session.
    """
    if new_status not in _TRANSITIONS.get(ticket.status, set()):
        return False

    now = datetime.now(UTC)
    old_status = ticket.status
    ticket.status = new_status
    ticket.updated_at = now

    if new_status == TicketStatus.resolved:
        ticket.resolved_at = now
    if new_status in (TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled):
        ticket.closed_at = now

    if old_status not in _PAUSE_STATUSES and new_status in _PAUSE_STATUSES:
        pause_sla(ticket, now)
    elif old_status in _PAUSE_STATUSES and new_status not in _PAUSE_STATUSES:
        resume_sla(ticket, now)

    check_breaches(ticket, now)

    _record_history(db, ticket.id, actor_id, "status", old_status.value, new_status.value, comment)
    _audit(db, AuditAction.status_change, actor_id, ticket.id)
    await notify(
        db,
        ticket.creator_id,
        NotificationType.ticket_updated,
        "Status do ticket atualizado",
        f"O status do ticket {ticket.protocol} foi atualizado para '{new_status.value}'.",
        data={
            "ticket_id": str(ticket.id),
            "old_status": old_status.value,
            "new_status": new_status.value,
        },
    )
    return True


# ── Helpers ───────────────────────────────────────────────────


def _audit(
    db: AsyncSession,
    action: AuditAction,
    actor_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> None:
    db.add(
        AuditLog(
            user_id=actor_id,
            action=action,
            entity_type="ticket",
            entity_id=entity_id,
        )
    )


def _serialize_ticket(ticket: Ticket) -> TicketResponse:
    """TicketResponse com os campos que são calculados, não armazenados."""
    response = TicketResponse.model_validate(ticket)
    if ticket.status in (TicketStatus.resolved, TicketStatus.closed):
        referencia = resolution_reference(ticket)
        if referencia is not None:
            response.reopen_deadline = reopen_deadline(referencia, get_settings())
    return response


async def _fill_product_and_equipment(
    response: TicketResponse, ticket: Ticket, db: AsyncSession
) -> None:
    """Preenche o nome do produto — o ticket só guarda o id."""
    if ticket.product_id:
        produto = await db.get(Product, ticket.product_id)
        response.product_name = produto.name if produto else None

    # Sem produto informado no chamado, usa o do primeiro equipamento: é o que
    # o cliente responderia se perguntassem "de qual produto é esse chamado?".
    if not response.product_name and ticket.equipments:
        product_id = ticket.equipments[0].product_id
        if product_id:
            produto = await db.get(Product, product_id)
            response.product_name = produto.name if produto else None


async def _set_ticket_equipments(
    db: AsyncSession,
    ticket: Ticket,
    equipment_ids: list[uuid.UUID],
    actor: User,
) -> None:
    """
    Substitui os equipamentos do chamado, recusando id inexistente.

    Um cliente só vincula equipamento que seja dele — sem isso, informar ids
    aleatórios revelaria o número de série de aparelhos de outras empresas na
    resposta da API.
    """
    if not equipment_ids:
        ticket.equipments = []
        return

    unicos = list(dict.fromkeys(equipment_ids))
    # `no_autoflush` é o que faz este endpoint funcionar, não um detalhe de
    # performance. Sem ele o SELECT abaixo dispara o autoflush, o chamado
    # recém-adicionado vira PERSISTENTE, e a atribuição lá embaixo
    # (`ticket.equipments = ...`) passa a precisar carregar a coleção ANTIGA
    # para calcular a diferença. Esse carregamento é IO fora do greenlet do
    # SQLAlchemy async: MissingGreenlet, 500, e o navegador ainda por cima
    # relata como erro de CORS, porque a resposta de erro sai sem o header.
    #
    # Com o chamado ainda pendente, o ORM sabe que não há coleção antiga para
    # buscar. É também por isso que abrir chamado SEM equipamento sempre
    # funcionou: aquele ramo atribui antes de qualquer SELECT.
    with db.no_autoflush:
        rows = await db.execute(select(Equipment).where(Equipment.id.in_(unicos)))
        encontrados = list(rows.scalars().all())

    if len(encontrados) != len(unicos):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Um ou mais equipamentos informados não existem.",
        )

    if actor.role == UserRole.client:
        alheios = [e for e in encontrados if e.owner_id != actor.id]
        if alheios:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Só é possível vincular equipamentos que pertencem a você.",
            )

    ticket.equipments = encontrados


def _record_history(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    # Nulo quando quem agiu foi o sistema — a Helô movendo o chamado para "Em
    # andamento". A coluna já aceitava (`TicketHistory.user_id` é nullable); só
    # a anotação aqui era estreita demais.
    user_id: uuid.UUID | None,
    field: str,
    # Aceita UUID porque varios campos de historico sao id: o corpo faz str()
    # antes de gravar, entao a anotacao estreita era a unica coisa errada.
    old_value: str | uuid.UUID | None,
    new_value: str | uuid.UUID | None,
    comment: str | None = None,
) -> None:
    db.add(
        TicketHistory(
            id=uuid.uuid4(),
            ticket_id=ticket_id,
            user_id=user_id,
            field=field,
            old_value=str(old_value) if old_value is not None else None,
            new_value=str(new_value) if new_value is not None else None,
            comment=comment,
        )
    )


# ═══════════════════════════════════════════════════════════════
# TICKETS
# ═══════════════════════════════════════════════════════════════


@router.post("/tickets", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    body: TicketCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TicketResponse:
    """Create a new support ticket.

    Generates a unique protocol number (HS-YYYY-NNNN), applies the matching
    SLA configuration, persists the ticket, and triggers async AI classification.
    """
    ts = datetime.now(UTC)
    ticket_id = uuid.uuid4()

    # Look up SLA config matching this ticket's priority
    sla_result = await db.execute(
        select(SLAConfig).where(
            SLAConfig.level == body.priority.value,
            SLAConfig.is_active.is_(True),
        )
    )
    sla_config = sla_result.scalar_one_or_none()

    for attempt in range(MAX_RETRIES):
        protocol = await generate_protocol(db)
        ticket = Ticket(
            id=ticket_id,
            protocol=protocol,
            title=body.title,
            description=body.description,
            priority=body.priority,
            category=body.category,
            status=TicketStatus.open,
            creator_id=actor.id,
            product_id=body.product_id,
            client_observation=body.client_observation,
            sla_response_breach=False,
            sla_resolve_breach=False,
            sla_total_paused_ms=0,
            # Explícito, e não pelo `default=True` da coluna: o default do ORM
            # só vale no INSERT, e a Helô é consultada ANTES do flush. Sem esta
            # linha `ticket.ai_enabled` é None no objeto em memória, `bool(None)`
            # é falso, e ela nunca falaria — em produção, silenciosamente.
            #
            # O chamado HERDA a preferência de quem o abriu. Materializar aqui
            # deixa uma pergunta só a ser feita depois — "a IA pode atuar neste
            # chamado?" —, em vez de todo consumidor ter que lembrar de olhar
            # também o dono. Quem desligar o cliente depois não muda o passado,
            # e é o que se quer: chamado em andamento não troca de regra no meio.
            ai_enabled=bool(actor.ai_enabled),
            auto_closed=False,
            reopen_count=0,
            created_at=ts,
            updated_at=ts,
        )
        if sla_config:
            apply_sla_config(ticket, sla_config, ts)
        db.add(ticket)
        await _set_ticket_equipments(db, ticket, body.equipment_ids, actor)
        _record_history(db, ticket.id, actor.id, "created", None, "open")

        # A Helô se apresenta e faz as três perguntas de triagem. Dentro do
        # mesmo commit do chamado de propósito: metade das duas coisas gravada
        # seria um chamado "Em andamento" sem ninguém ter falado, ou uma fala
        # num chamado que não existe.
        #
        # Só para cliente. Staff abrindo chamado em nome de alguém não precisa
        # ser triado por robô, e a saudação chamaria o staff pelo nome errado.
        if actor.role == UserRole.client and await abre_triagem(
            db, ticket, actor, list(ticket.equipments)
        ):
            _record_history(db, ticket.id, None, "status", "open", "in_progress", "Helô")
        _audit(db, AuditAction.create, actor.id, ticket.id)
        await notify(
            db,
            actor.id,
            NotificationType.ticket_created,
            "Ticket aberto",
            f"Seu ticket foi registrado com o protocolo {protocol}.",
            data={"ticket_id": str(ticket.id), "protocol": protocol},
            settings=settings,
        )
        try:
            await commit_e_notificar(db)
            break
        except IntegrityError:
            await db.rollback()
            if attempt == MAX_RETRIES - 1:
                raise
            # Regenerate a fresh ticket_id on retry to avoid PK collision
            ticket_id = uuid.uuid4()

    await db.refresh(ticket)

    # Fire-and-forget LLM classification (non-blocking).
    #
    # O interruptor do chamado vale aqui também: o botão diz "Desligar IA neste
    # chamado", e classificar assim mesmo mandaria o texto do cliente para o
    # provedor de LLM depois de alguém ter pedido para não mandar.
    if ticket.ai_enabled:
        asyncio.create_task(
            _classify_ticket_async(ticket.id, body.title, body.description, body.category.value)
        )

    return _serialize_ticket(ticket)


_SORT_COLUMNS = {
    "created_at": Ticket.created_at,
    "updated_at": Ticket.updated_at,
    "priority": Ticket.priority,
    "sla_resolve_due_at": Ticket.sla_resolve_due_at,
}


@router.get("/tickets", response_model=TicketListResponse)
async def list_tickets(
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=500),
    status_filter: TicketStatus | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    category: str | None = Query(default=None),
    assignee_id: uuid.UUID | None = Query(default=None),
    creator_id: uuid.UUID | None = Query(default=None),
    tag_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    sort_by: str = Query(
        default="created_at", pattern="^(created_at|updated_at|priority|sla_resolve_due_at)$"
    ),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> TicketListResponse:
    """List tickets with filtering, sorting, and pagination.

    Clients automatically see only their own tickets; admins and technicians
    see all. Supports filtering by status, priority, category, assignee, creator,
    and full-text search across title and description.
    """
    from sqlalchemy import asc, case, desc

    base = select(Ticket)

    # Clients only see their own tickets
    if actor.role == UserRole.client:
        base = base.where(Ticket.creator_id == actor.id)
    elif creator_id:
        base = base.where(Ticket.creator_id == creator_id)

    if status_filter is not None:
        base = base.where(Ticket.status == status_filter)
    if priority:
        base = base.where(Ticket.priority == priority)
    if category:
        base = base.where(Ticket.category == category)
    if assignee_id:
        base = base.where(Ticket.assignee_id == assignee_id)
    if tag_id:
        base = base.where(
            Ticket.id.in_(select(ticket_tags.c.ticket_id).where(ticket_tags.c.tag_id == tag_id))
        )
    if search:
        # Título, protocolo e número de série do equipamento — as três formas
        # como as pessoas procuram um chamado
        termo = f"%{search}%"
        base = base.where(
            Ticket.title.ilike(termo)
            | Ticket.protocol.ilike(termo)
            # Basta um dos equipamentos do chamado bater com o número de série
            | Ticket.id.in_(
                select(ticket_equipments.c.ticket_id)
                .join(Equipment, Equipment.id == ticket_equipments.c.equipment_id)
                .where(Equipment.serial_number.ilike(termo))
            )
        )

    # Build sort expression
    if sort_by == "priority":
        sort_expr = case(
            (Ticket.priority == "critical", 0),
            (Ticket.priority == "high", 1),
            (Ticket.priority == "medium", 2),
            (Ticket.priority == "low", 3),
            else_=4,
        )
    else:
        sort_expr = _SORT_COLUMNS[sort_by]  # type: ignore[assignment]

    order = asc(sort_expr) if sort_dir == "asc" else desc(sort_expr)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = await db.execute(base.order_by(order).offset(offset).limit(limit))
    tickets = rows.scalars().all()

    # Batch-fetch assignee names (single query)
    assignee_ids = {t.assignee_id for t in tickets if t.assignee_id}
    name_map: dict[uuid.UUID, str] = {}
    if assignee_ids:
        user_rows = await db.execute(select(User.id, User.name).where(User.id.in_(assignee_ids)))
        name_map = {row.id: row.name for row in user_rows}

    # Produtos em lote — uma consulta só, não uma por ticket. Entram também os
    # produtos dos equipamentos, usados quando o chamado não informou produto.
    product_ids = {t.product_id for t in tickets if t.product_id}
    product_ids |= {e.product_id for t in tickets for e in t.equipments if e.product_id}
    product_map: dict[uuid.UUID, str] = {}
    if product_ids:
        product_rows = await db.execute(
            select(Product.id, Product.name).where(Product.id.in_(product_ids))
        )
        product_map = {row.id: row.name for row in product_rows}

    # Os equipamentos vêm junto pelo lazy="selectin" do relacionamento: uma
    # consulta para a página inteira, não uma por chamado.
    def _serialize(t: Ticket) -> TicketResponse:
        r = _serialize_ticket(t)
        r.assignee_name = name_map.get(t.assignee_id) if t.assignee_id else None
        r.product_name = product_map.get(t.product_id) if t.product_id else None
        if not r.product_name and t.equipments and t.equipments[0].product_id:
            r.product_name = product_map.get(t.equipments[0].product_id)
        if actor.role == UserRole.client:
            r.technician_notes = None
        return r

    return TicketListResponse(
        items=[_serialize(t) for t in tickets],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> TicketResponse:
    """Retrieve a single ticket by ID.

    Clients may only access tickets they created; admins and technicians
    have unrestricted read access.
    """
    ticket = await get_or_404(db, Ticket, ticket_id, _CHAMADO_NAO_ENCONTRADO)

    if actor.role == UserRole.client:
        ensure_ticket_visible(ticket, actor, _CHAMADO_NAO_ENCONTRADO)

    response = _serialize_ticket(ticket)
    if ticket.assignee_id:
        assignee = await db.get(User, ticket.assignee_id)
        response.assignee_name = assignee.name if assignee else None
    await _fill_product_and_equipment(response, ticket, db)
    if actor.role == UserRole.client:
        response.technician_notes = None
    return response


@router.patch("/tickets/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    ticket_id: uuid.UUID,
    body: TicketUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> TicketResponse:
    """Update ticket fields.

    Admin can update all fields. Technician can only update their internal notes.
    Clients have no edit access — ticket content is immutable after creation.
    """
    ticket = await get_or_404(db, Ticket, ticket_id, _CHAMADO_NAO_ENCONTRADO)

    if actor.role == UserRole.technician:
        # Technician may only save internal notes
        changes = body.model_dump(include={"technician_notes"}, exclude_unset=True)
    else:
        # Admin can update any field
        changes = body.model_dump(exclude_unset=True)

    # Os equipamentos vivem numa tabela de ligação, não numa coluna do ticket —
    # o setattr do laço abaixo não daria conta.
    novos_equipamentos = changes.pop("equipment_ids", None)
    if novos_equipamentos is not None:
        antes = sorted(e.name for e in ticket.equipments)
        await _set_ticket_equipments(db, ticket, novos_equipamentos, actor)
        depois = sorted(e.name for e in ticket.equipments)
        if antes != depois:
            _record_history(
                db,
                ticket.id,
                actor.id,
                "equipamentos",
                ", ".join(antes) or None,
                ", ".join(depois) or None,
            )

    for field, new_val in changes.items():
        old_val = getattr(ticket, field)
        if old_val != new_val:
            _record_history(db, ticket.id, actor.id, field, old_val, new_val)
        setattr(ticket, field, new_val)

    ticket.updated_at = datetime.now(UTC)
    _audit(db, AuditAction.update, actor.id, ticket.id)
    await commit_e_notificar(db)
    await db.refresh(ticket)
    return _serialize_ticket(ticket)


@router.patch("/tickets/{ticket_id}/observation", response_model=TicketResponse)
async def update_client_observation(
    ticket_id: uuid.UUID,
    body: TicketObservationUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> TicketResponse:
    """Client updates their own observation field. Admins may also edit it."""
    ticket = await get_or_404(db, Ticket, ticket_id, _CHAMADO_NAO_ENCONTRADO)

    if actor.role == UserRole.client:
        ensure_ticket_visible(ticket, actor, _CHAMADO_NAO_ENCONTRADO)
        if ticket.status in (TicketStatus.closed, TicketStatus.cancelled):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot edit observation on a closed or cancelled ticket",
            )
    elif actor.role == UserRole.technician:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para acessar este item.",
        )

    old = ticket.client_observation
    ticket.client_observation = body.client_observation
    ticket.updated_at = datetime.now(UTC)
    if old != body.client_observation:
        _record_history(db, ticket.id, actor.id, "client_observation", old, body.client_observation)
    _audit(db, AuditAction.update, actor.id, ticket.id)
    await commit_e_notificar(db)
    await db.refresh(ticket)
    return _serialize_ticket(ticket)


@router.patch("/tickets/{ticket_id}/ai", response_model=TicketResponse)
async def toggle_ticket_ai(
    ticket_id: uuid.UUID,
    body: InterruptorDaIA,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> TicketResponse:
    """
    Liga ou desliga a IA neste chamado.

    É o interruptor de quem entra na conversa: o técnico assume, quer a Helô
    calada dali em diante, e não precisa pedir para ninguém mexer no painel.

    Vale para a IA inteira neste chamado, não só para a Helô — desligado aqui,
    nem a classificação automática nem a sugestão de resposta olham para ele.
    "Desliga a IA neste chamado" tem que significar isso.

    Endpoint próprio, e não mais um campo no `PATCH /tickets/{id}`: aquele
    limita o técnico a `technician_notes`, e este é justamente o botão dele.

    Desligar NÃO apaga o que ela já falou. A conversa é registro do
    atendimento; sumir com ela deixaria o cliente falando sozinho no histórico.
    """
    ticket = await get_or_404(db, Ticket, ticket_id, _CHAMADO_NAO_ENCONTRADO)

    if ticket.ai_enabled != body.enabled:
        _record_history(
            db,
            ticket.id,
            actor.id,
            "ai_enabled",
            str(ticket.ai_enabled),
            str(body.enabled),
        )
        ticket.ai_enabled = body.enabled
        _audit(db, AuditAction.update, actor.id, ticket.id)
        await db.commit()
        await db.refresh(ticket)

    response = _serialize_ticket(ticket)
    await _fill_product_and_equipment(response, ticket, db)
    return response


@router.patch("/tickets/{ticket_id}/status", response_model=TicketResponse)
async def update_ticket_status(
    ticket_id: uuid.UUID,
    body: TicketStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TicketResponse:
    ticket = await get_or_404(db, Ticket, ticket_id, _CHAMADO_NAO_ENCONTRADO)

    if body.status not in _TRANSITIONS.get(ticket.status, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot transition from '{ticket.status}' to '{body.status}'",
        )

    now = datetime.now(UTC)
    old_status = ticket.status
    ticket.status = body.status
    ticket.updated_at = now

    # SLA: mudar o status não marca primeira resposta — quem marca é falar com
    # o cliente (chat) ou entregar a resolução. Ver register_first_response.

    # SLA: pause / resume clock
    if old_status not in _PAUSE_STATUSES and body.status in _PAUSE_STATUSES:
        pause_sla(ticket, now)
    elif old_status in _PAUSE_STATUSES and body.status not in _PAUSE_STATUSES:
        resume_sla(ticket, now)

    check_breaches(ticket, now)

    if body.status in (TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled):
        ticket.closed_at = now

    _record_history(
        db, ticket.id, actor.id, "status", old_status.value, body.status.value, body.comment
    )
    _audit(db, AuditAction.status_change, actor.id, ticket.id)
    await notify(
        db,
        ticket.creator_id,
        NotificationType.ticket_updated,
        "Status do ticket alterado",
        f"O status do ticket {ticket.protocol} foi alterado para '{body.status.value}'.",
        data={
            "ticket_id": str(ticket.id),
            "old_status": old_status.value,
            "new_status": body.status.value,
        },
        settings=settings,
    )
    # Invite creator to fill CSAT survey when ticket is resolved (in-app only)
    if body.status == TicketStatus.resolved:
        ticket.resolved_at = now
        await notify(
            db,
            ticket.creator_id,
            NotificationType.satisfaction_survey,
            "Como foi o atendimento?",
            f"O ticket {ticket.protocol} foi resolvido. Deixe sua avaliação!",
            data={"ticket_id": str(ticket.id), "protocol": ticket.protocol},
            settings=settings,
        )
    await commit_e_notificar(db)
    await db.refresh(ticket)
    return _serialize_ticket(ticket)


@router.post("/tickets/{ticket_id}/resolve", response_model=TicketResponse)
async def resolve_ticket(
    ticket_id: uuid.UUID,
    body: TicketResolve,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TicketResponse:
    ticket = await get_or_404(db, Ticket, ticket_id, _CHAMADO_NAO_ENCONTRADO)

    if ticket.status in (TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ticket is already '{ticket.status.value}'",
        )

    now = datetime.now(UTC)
    old_status = ticket.status
    ticket.status = TicketStatus.resolved
    ticket.resolution_note = body.resolution_note
    ticket.closed_at = now
    ticket.resolved_at = now
    ticket.updated_at = now

    # A nota de resolução é texto que o cliente lê: vale como primeira
    # resposta quando ninguém falou antes, venha o chamado de qual status vier.
    register_first_response(ticket, now, responder_id=actor.id)
    if old_status in _PAUSE_STATUSES:
        resume_sla(ticket, now)
    check_breaches(ticket, now)

    _record_history(
        db,
        ticket.id,
        actor.id,
        "status",
        old_status.value,
        TicketStatus.resolved.value,
        f"Ticket resolvido: {body.resolution_note[:100]}",
    )
    _audit(db, AuditAction.status_change, actor.id, ticket.id)

    await notify(
        db,
        ticket.creator_id,
        NotificationType.ticket_updated,
        "Ticket resolvido",
        f"O ticket {ticket.protocol} foi marcado como resolvido.",
        data={"ticket_id": str(ticket.id), "new_status": "resolved"},
        settings=settings,
    )
    await notify(
        db,
        ticket.creator_id,
        NotificationType.satisfaction_survey,
        "Como foi o atendimento?",
        f"O ticket {ticket.protocol} foi resolvido. Deixe sua avaliação!",
        data={"ticket_id": str(ticket.id), "protocol": ticket.protocol},
        settings=settings,
    )

    await commit_e_notificar(db)
    await db.refresh(ticket)
    return _serialize_ticket(ticket)


@router.post("/tickets/{ticket_id}/reopen", response_model=TicketResponse)
async def reopen_ticket(
    ticket_id: uuid.UUID,
    body: TicketReopen,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TicketResponse:
    """
    Reabre um chamado resolvido ou fechado (RN-006).

    O prazo vale para o cliente. Admin e técnico reabrem a qualquer momento —
    quando o encerramento foi engano da própria equipe, um prazo vencido só
    obrigaria a abrir um chamado novo e perder o histórico.
    """
    ticket = await get_or_404(db, Ticket, ticket_id, _CHAMADO_NAO_ENCONTRADO)
    is_staff = actor.role in (UserRole.admin, UserRole.technician)

    if not is_staff:
        ensure_ticket_visible(ticket, actor, _CHAMADO_NAO_ENCONTRADO)

    if ticket.status not in (TicketStatus.resolved, TicketStatus.closed):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Só é possível reabrir um chamado resolvido ou fechado.",
        )

    if not is_staff and not can_client_reopen(ticket, settings):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"O prazo de {settings.ticket_reopen_business_days} dias úteis para reabrir "
                "este chamado já passou. Abra um novo chamado descrevendo o problema."
            ),
        )

    now = datetime.now(UTC)
    old_status = ticket.status
    # Com responsável definido o chamado volta direto para a fila dele; sem
    # responsável volta para Aberto, para ser distribuído como um chamado novo.
    new_status = TicketStatus.in_progress if ticket.assignee_id else TicketStatus.open

    ticket.status = new_status
    ticket.closed_at = None
    ticket.resolved_at = None
    ticket.auto_closed = False
    ticket.reopened_at = now
    ticket.reopen_count = (ticket.reopen_count or 0) + 1
    ticket.updated_at = now

    # Prazo de resolução novo. Sem isso o chamado nasceria reaberto já vencido,
    # com o cronômetro parado no dia em que foi resolvido.
    sla_result = await db.execute(
        select(SLAConfig).where(
            SLAConfig.level == ticket.priority.value,
            SLAConfig.is_active.is_(True),
        )
    )
    sla_config = sla_result.scalar_one_or_none()
    if sla_config:
        ticket.sla_resolve_due_at = add_business_hours(now, sla_config.resolve_time_hours)
        ticket.sla_resolve_breach = False
    ticket.sla_paused_at = None
    # O tempo pausado é acumulado para esticar o prazo do ciclo em que ocorreu.
    # Como o prazo acima já parte de agora, mantê-lo daria ao ciclo novo um
    # bônus de horas que ninguém esperou.
    ticket.sla_total_paused_ms = 0

    _record_history(
        db,
        ticket.id,
        actor.id,
        "status",
        old_status.value,
        new_status.value,
        f"Chamado reaberto: {body.reason}",
    )
    _audit(db, AuditAction.status_change, actor.id, ticket.id)

    # Avisa quem vai precisar agir: o responsável, ou o cliente quando quem
    # reabriu foi a equipe.
    if ticket.assignee_id and ticket.assignee_id != actor.id:
        await notify(
            db,
            ticket.assignee_id,
            NotificationType.ticket_updated,
            "Chamado reaberto",
            f"O ticket {ticket.protocol} foi reaberto por {actor.name}.",
            data={"ticket_id": str(ticket.id), "new_status": new_status.value},
            settings=settings,
        )
    if ticket.creator_id != actor.id:
        await notify(
            db,
            ticket.creator_id,
            NotificationType.ticket_updated,
            "Chamado reaberto",
            f"O ticket {ticket.protocol} foi reaberto e voltou para atendimento.",
            data={"ticket_id": str(ticket.id), "new_status": new_status.value},
            settings=settings,
        )

    await commit_e_notificar(db)
    await db.refresh(ticket)
    return _serialize_ticket(ticket)


@router.patch("/tickets/{ticket_id}/assign", response_model=TicketResponse)
async def assign_ticket(
    ticket_id: uuid.UUID,
    body: TicketAssign,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TicketResponse:
    ticket = await get_or_404(
        db, Ticket, ticket_id, "Ticket não encontrado. Ele pode ter sido excluído."
    )

    if ticket.status in (TicketStatus.closed, TicketStatus.cancelled):
        situacao = "fechado" if ticket.status == TicketStatus.closed else "cancelado"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Este ticket está {situacao} e não pode ser reatribuído. "
                "Reabra o ticket antes de atribuí-lo a outro técnico."
            ),
        )

    new_assignee_user: User | None = None
    if body.assignee_id is not None:
        result = await db.execute(select(User).where(User.id == body.assignee_id))
        new_assignee_user = result.scalar_one_or_none()
        if not new_assignee_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="O técnico selecionado não existe mais no sistema.",
            )
        if new_assignee_user.role not in (UserRole.admin, UserRole.technician):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Tickets só podem ser atribuídos a técnicos ou administradores.",
            )
        if new_assignee_user.status != UserStatus.active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"{new_assignee_user.name} está com o cadastro inativo e não pode "
                    "receber tickets."
                ),
            )
        if ticket.assignee_id == body.assignee_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Este ticket já está atribuído a {new_assignee_user.name}.",
            )

    old_assignee = ticket.assignee_id
    ticket.assignee_id = body.assignee_id
    ticket.updated_at = datetime.now(UTC)
    _record_history(
        db,
        ticket.id,
        actor.id,
        "assignee_id",
        old_assignee,
        body.assignee_id,
        comment=new_assignee_user.name if new_assignee_user else None,
    )
    _audit(db, AuditAction.assign, actor.id, ticket.id)
    if body.assignee_id is not None:
        await notify(
            db,
            body.assignee_id,
            NotificationType.ticket_assigned,
            "Ticket atribuído a você",
            f"O ticket {ticket.protocol} foi atribuído a você.",
            data={"ticket_id": str(ticket.id), "protocol": ticket.protocol},
            settings=settings,
        )
        # Auto-transition → in_progress ao atribuir (de qualquer status ativo)
        if ticket.status in (
            TicketStatus.open,
            TicketStatus.awaiting_client,
            TicketStatus.awaiting_technical,
        ):
            await _auto_transition(
                db, ticket, TicketStatus.in_progress, actor.id, "Atribuído — em andamento"
            )
    await commit_e_notificar(db)
    await db.refresh(ticket)
    return _serialize_ticket(ticket)


@router.delete("/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_ticket(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    ticket = await get_or_404(db, Ticket, ticket_id, _CHAMADO_NAO_ENCONTRADO)

    if ticket.status in (TicketStatus.closed, TicketStatus.cancelled):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ticket is already '{ticket.status}'",
        )

    old_status = ticket.status
    ticket.status = TicketStatus.cancelled
    ticket.closed_at = datetime.now(UTC)
    ticket.updated_at = ticket.closed_at
    _record_history(db, ticket.id, actor.id, "status", old_status.value, "cancelled")
    _audit(db, AuditAction.delete, actor.id, ticket.id)
    await notify(
        db,
        ticket.creator_id,
        NotificationType.ticket_closed,
        "Ticket cancelado",
        f"O ticket {ticket.protocol} foi cancelado.",
        data={"ticket_id": str(ticket.id), "protocol": ticket.protocol},
        settings=settings,
    )
    await commit_e_notificar(db)


# ── Ticket Notes ─────────────────────────────────────────────


@router.get("/tickets/{ticket_id}/notes", response_model=list[TicketNoteResponse])
async def list_ticket_notes(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> list[TicketNoteResponse]:
    await get_or_404(db, Ticket, ticket_id, _CHAMADO_NAO_ENCONTRADO)
    rows = (
        await db.execute(
            select(TicketNote, User.name.label("author_name"))
            .join(User, User.id == TicketNote.author_id)
            .where(TicketNote.ticket_id == ticket_id)
            .order_by(TicketNote.created_at.desc())
        )
    ).all()
    return [
        TicketNoteResponse(
            id=row.TicketNote.id,
            ticket_id=row.TicketNote.ticket_id,
            author_id=row.TicketNote.author_id,
            author_name=row.author_name,
            content=row.TicketNote.content,
            created_at=row.TicketNote.created_at,
        )
        for row in rows
    ]


@router.post(
    "/tickets/{ticket_id}/notes",
    response_model=TicketNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_ticket_note(
    ticket_id: uuid.UUID,
    body: TicketNoteCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> TicketNoteResponse:
    await get_or_404(db, Ticket, ticket_id, _CHAMADO_NAO_ENCONTRADO)
    note = TicketNote(ticket_id=ticket_id, author_id=actor.id, content=body.content)
    db.add(note)
    await commit_e_notificar(db)
    await db.refresh(note)
    return TicketNoteResponse(
        id=note.id,
        ticket_id=note.ticket_id,
        author_id=note.author_id,
        author_name=actor.name,
        content=note.content,
        created_at=note.created_at,
    )


@router.delete("/tickets/{ticket_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ticket_note(
    ticket_id: uuid.UUID,
    note_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> None:
    note = (
        await db.execute(
            select(TicketNote).where(TicketNote.id == note_id, TicketNote.ticket_id == ticket_id)
        )
    ).scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nota não encontrada")
    if actor.role != UserRole.admin and note.author_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para deletar esta nota"
        )
    await db.delete(note)
    await commit_e_notificar(db)


@router.get("/tickets/{ticket_id}/history", response_model=TicketHistoryListResponse)
async def get_ticket_history(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> TicketHistoryListResponse:
    ticket = await get_or_404(db, Ticket, ticket_id, _CHAMADO_NAO_ENCONTRADO)

    if actor.role == UserRole.client:
        ensure_ticket_visible(ticket, actor, _CHAMADO_NAO_ENCONTRADO)

    base = select(TicketHistory).where(TicketHistory.ticket_id == ticket_id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = await db.execute(
        base.options(selectinload(TicketHistory.user))
        .order_by(TicketHistory.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    entries = rows.scalars().all()

    items = []
    for h in entries:
        item = TicketHistoryResponse.model_validate(h)
        item.user_name = h.user.name if h.user else None
        items.append(item)

    return TicketHistoryListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
