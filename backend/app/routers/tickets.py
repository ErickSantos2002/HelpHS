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
  PATCH  /tickets/{id}/priority      — admin, technician (a triagem)
  PATCH  /tickets/{id}/assign        — admin, technician
  POST   /tickets/{id}/reopen        — criador (dentro do prazo), admin/technician
  DELETE /tickets/{id}               — admin (cancela o ticket)
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

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
    TicketSlaExtension,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
    ticket_equipments,
    ticket_tags,
)
from app.schemas.telefonia import TicketCallCreate, TicketCallResponse
from app.schemas.ticket import (
    DiasDeExtensao,
    ExpedienteInfo,
    InterruptorDaIA,
    SlaExtensionPreview,
    SlaExtensionRequest,
    TicketAssign,
    TicketCreate,
    TicketHistoryListResponse,
    TicketHistoryResponse,
    TicketListResponse,
    TicketNoteCreate,
    TicketNoteResponse,
    TicketObservationUpdate,
    TicketPriorityUpdate,
    TicketReopen,
    TicketResolve,
    TicketResponse,
    TicketStatusUpdate,
    TicketUpdate,
)
from app.services import ligacao
from app.services.helo import abre_triagem
from app.services.llm import classify_ticket
from app.services.notifications import (
    audiencia_operacional,
    commit_e_notificar,
    notifica_audiencia,
    notify,
)
from app.services.ticket_lifecycle import (
    can_client_reopen,
    reopen_deadline,
    resolution_reference,
)
from app.utils.crud import get_or_404
from app.utils.history import filtra_historico_para, registra_historico
from app.utils.protocol import MAX_RETRIES, generate_protocol
from app.utils.sla import (
    _PAUSE_STATUSES,
    _TERMINAL_STATUSES,
    FUSO_DA_JORNADA,
    add_business_minutes,
    apply_sla_config,
    atualiza_prazo_efetivo,
    business_minutes_between,
    check_breaches,
    estado_do_expediente,
    inicio_do_ciclo_de_resolucao,
    marca_violacao_ao_resolver,
    minutos_uteis_de_dias,
    pause_sla,
    prazo_efetivo_de_resolucao,
    prazo_efetivo_de_resposta,
    register_first_response,
    resume_sla,
    violacao_ao_resolver,
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

    registra_historico(
        db, ticket.id, actor_id, "status", old_status.value, new_status.value, comment
    )
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


def _expediente(agora: datetime) -> ExpedienteInfo:
    """O relógio do servidor, para a tela congelar o contador sem calendário."""
    aberto, virada = estado_do_expediente(agora)
    return ExpedienteInfo(
        agora=agora,
        aberto=aberto,
        proxima_virada=virada,
        fuso=FUSO_DA_JORNADA,
    )


def _formata_prazo(quando: datetime | None) -> str:
    """ "24/09/2026 às 12:11" no fuso em que a jornada é definida.

    O fuso vem do motor (`FUSO_DA_JORNADA`), e não de um literal daqui: o
    horário do vencimento só faz sentido na jornada que o produziu.
    """
    if quando is None:
        return "sem prazo"
    local = quando.astimezone(ZoneInfo(FUSO_DA_JORNADA))
    return local.strftime("%d/%m/%Y às %H:%M")


def _serialize_ticket(
    ticket: Ticket,
    agora: datetime | None = None,
    *,
    actor: User,
    com_expediente: bool = True,
) -> TicketResponse:
    """TicketResponse com os campos que são calculados, não armazenados.

    ⚠️ `actor` é OBRIGATÓRIO, e keyword-only, e isso é a correção inteira.

    `technician_notes` é declarada interna no modelo ("visível apenas para
    admin/técnico"), mas a máscara morava no call site — cada endpoint
    precisava lembrar de apagá-la. Dois lembraram e **três esqueceram**:
    `PATCH /observation`, `POST /reopen` e, pior, `GET /history`, que entregava
    todas as VERSÕES da nota. Um cliente dono do chamado lia tudo com 200.

    Enquanto o parâmetro tivesse default, esquecer voltaria a vazar em
    silêncio. Sem default, esquecer é `TypeError` na primeira chamada — o
    esquecimento passa a ser barulhento, e é o único jeito de a regra parar de
    depender de memória.

    `agora` é parâmetro, e não `datetime.now()` lá dentro, por dois motivos: a
    listagem serializa cinquenta chamados e todos devem ser lidos do MESMO
    instante, e o teste precisa fixar o relógio sem congelar o processo.

    `com_expediente=False` é o que a listagem usa: lá o bloco vem uma vez no
    topo da resposta.
    """
    agora = agora or datetime.now(UTC)
    response = TicketResponse.model_validate(ticket)

    # A nota interna nunca sai para o cliente. Note que apagamos no RESPONSE,
    # não no `ticket`: mexer no objeto ORM marcaria a coluna como suja e o
    # próximo `commit()` da requisição gravaria NULL no banco.
    if actor.role == UserRole.client:
        response.technician_notes = None

    if ticket.status in (TicketStatus.resolved, TicketStatus.closed):
        referencia = resolution_reference(ticket)
        if referencia is not None:
            response.reopen_deadline = reopen_deadline(referencia, get_settings())

    # O prazo EFETIVO, e o tempo ÚTIL que falta até ele. As duas contas que a
    # tela fazia errado: ela ignorava a pausa e subtraía tempo corrido.
    response.sla_response_vence_em = prazo_efetivo_de_resposta(ticket)
    response.sla_resolve_vence_em = prazo_efetivo_de_resolucao(ticket)
    if response.sla_response_vence_em is not None:
        response.sla_response_restante_min = business_minutes_between(
            agora, response.sla_response_vence_em
        )
        response.sla_response_total_min = business_minutes_between(
            ticket.created_at, response.sla_response_vence_em
        )
    if response.sla_resolve_vence_em is not None:
        response.sla_resolve_restante_min = business_minutes_between(
            agora, response.sla_resolve_vence_em
        )
        # Do início do CICLO, e não da abertura. A reabertura recomeça o prazo de
        # resolução e não o `created_at`: contar da abertura original contra um
        # prazo do ciclo novo inflava o total — medido em 25/09/2026, chamado com
        # dez dias úteis de vida aparecia com 90% da barra cheia no instante em
        # que foi reaberto, porque o total dava 5400 minutos úteis contra 540 de
        # restante.
        #
        # É a MESMA função que o aviso de SLA consome (`sla_alertas.py`), de
        # propósito: com duas contas, o e-mail diria 0% e o cartão 90%.
        #
        # ⚠️ A linha do prazo de RESPOSTA acima continua em `created_at`, e está
        # certa: `reopen_ticket` não recarimba `sla_response_due_at`, então
        # aquele prazo tem um ciclo só.
        response.sla_resolve_total_min = business_minutes_between(
            inicio_do_ciclo_de_resolucao(ticket), response.sla_resolve_vence_em
        )

    if com_expediente:
        response.expediente = _expediente(agora)

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


def _justificativa_de_sla(ticket: Ticket, now: datetime, enviada: str | None) -> str | None:
    """
    Recusa resolver chamado fora do prazo sem justificativa escrita.

    Roda ANTES de qualquer mutação, de propósito: uma recusa depois de o status
    já ter mudado deixaria o chamado resolvido e o pedido rejeitado ao mesmo
    tempo, e o cliente da API não teria como saber em que estado ficou.

    A violação é calculada da DATA, não das marcas `sla_*_breach` — ver
    `violacao_ao_resolver`, que explica por que as marcas não servem aqui. Se
    servissem, um chamado vencido e esquecido passaria batido, e é exatamente
    ele que a exigência existe para pegar.

    Justificativa enviada sem haver violação é gravada mesmo assim: quem
    explicou não perde o texto por ter entregado no prazo.
    """
    resposta_violada, resolucao_violada = violacao_ao_resolver(ticket, now)
    limpa = (enviada or "").strip()

    if not (resposta_violada or resolucao_violada):
        return limpa or None

    if not limpa:
        quais = []
        if resposta_violada:
            quais.append("o de primeira resposta")
        if resolucao_violada:
            quais.append("o de resolução")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Este chamado passou do prazo ({' e '.join(quais)}). "
                "Informe 'sla_breach_justification' com o motivo do atraso para resolvê-lo."
            ),
        )

    return limpa


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

    Generates a unique protocol number (HS-YYYY-NNNN), persists the ticket and
    triggers async AI classification.

    **O chamado nasce sem prioridade e, por consequência, sem prazo de SLA.**
    Quem define a prioridade é a triagem (`PATCH /tickets/{id}/priority`), e é
    ela que carrega a `SLAConfig` e carimba os prazos — contados da abertura,
    não do instante da triagem. Buscar uma configuração de SLA aqui não teria
    por qual nível procurar: não existe prioridade ainda.
    """
    ts = datetime.now(UTC)
    ticket_id = uuid.uuid4()

    for attempt in range(MAX_RETRIES):
        protocol = await generate_protocol(db)
        ticket = Ticket(
            id=ticket_id,
            protocol=protocol,
            title=body.title,
            description=body.description,
            category=body.category,
            status=TicketStatus.open,
            creator_id=actor.id,
            product_id=body.product_id,
            client_observation=body.client_observation,
            sla_response_breach=False,
            sla_resolve_breach=False,
            sla_total_paused_ms=0,
            # Explícito, e não pelo `default=0` da coluna, pelo mesmo motivo do
            # `ai_enabled` logo abaixo: o default do ORM só vale no INSERT, e o
            # chamado é SERIALIZADO antes do flush. Sem esta linha o campo sai
            # `None` na resposta da criação, e o contrato diz `int`.
            sla_resolve_extension_total_min=0,
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
        db.add(ticket)
        await _set_ticket_equipments(db, ticket, body.equipment_ids, actor)
        registra_historico(db, ticket.id, actor.id, "created", None, "open")

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
            registra_historico(db, ticket.id, None, "status", "open", "in_progress", "Helô")
        _audit(db, AuditAction.create, actor.id, ticket.id)
        dados_da_notificacao = {"ticket_id": str(ticket.id), "protocol": protocol}
        await notify(
            db,
            actor.id,
            NotificationType.ticket_created,
            "Ticket aberto",
            f"Seu ticket foi registrado com o protocolo {protocol}.",
            data=dados_da_notificacao,
            settings=settings,
        )
        # E a equipe inteira, para o atendimento não depender de alguém olhar o
        # quadro. Vai para TODOS os técnicos e admins ativos, e não para um
        # sorteado: o chamado nasce sem dono, e escolher um seria inventar uma
        # atribuição que ninguém pediu — o mesmo argumento que já vale para o
        # aviso da Helô (ver `_avisa_equipe_da_helo`).
        #
        # O AUTOR SAI DA AUDIÊNCIA. Staff que abre chamado em nome de um cliente
        # cai nas duas regras, e a confirmação acima é a que fica: ela diz "Seu
        # ticket foi registrado", que é a informação de quem abriu. Trocá-la pelo
        # aviso operacional seria substituir uma mensagem dirigida a ele por uma
        # escrita para outra pessoa.
        #
        # A exclusão é EXPLÍCITA e não depende desta ordem de chamadas: inverter
        # as duas linhas dá o mesmo resultado. Ver `notifica_audiencia`.
        await notifica_audiencia(
            db,
            await audiencia_operacional(db),
            NotificationType.ticket_created,
            "Novo chamado",
            f"{protocol} — {body.title}",
            data=dados_da_notificacao,
            settings=settings,
            email_subject=f"[HelpHS] Novo chamado {protocol} — {body.title}",
            exclude_user_ids={actor.id},
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

    return _serialize_ticket(ticket, actor=actor)


_SORT_COLUMNS = {
    "created_at": Ticket.created_at,
    "updated_at": Ticket.updated_at,
    "priority": Ticket.priority,
    # Ordena pelo prazo EFETIVO, que e o que a tela mostra e o que o motor
    # cobra. Pela coluna crua, um chamado prorrogado para daqui a 15 dias
    # continuaria aparecendo como se vencesse hoje. O nome do parametro
    # nao muda: quem chama pede "por prazo de resolucao", e essa resposta
    # passou a ser outra coluna.
    "sla_resolve_due_at": Ticket.sla_resolve_effective_due_at,
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
        # **Sem prioridade vem ANTES de "Crítica"**, e não no fim da fila.
        #
        # Ordenar por urgência passou a ter duas perguntas dentro: quão urgente
        # é, e alguém já disse quão urgente é. A segunda vem primeiro — o
        # chamado não triado é o que precisa de ação inicial, e o prazo de
        # resolução dele **já corre desde a abertura** (o SLA é ancorado em
        # `created_at`). Mandá-lo para o fim esconderia justamente quem ainda
        # não foi olhado, e o atraso chegaria pronto.
        #
        # O `else_` continua sendo o fim: valor que o banco tenha e este código
        # não conheça é dado estranho, não fila de triagem.
        sort_expr = case(
            (Ticket.priority.is_(None), -1),
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
    # Um instante só para a página inteira: cinquenta chamados lidos de
    # relógios ligeiramente diferentes dariam restantes que não somam.
    agora = datetime.now(UTC)

    def _serialize(t: Ticket) -> TicketResponse:
        r = _serialize_ticket(t, agora, actor=actor, com_expediente=False)
        r.assignee_name = name_map.get(t.assignee_id) if t.assignee_id else None
        r.product_name = product_map.get(t.product_id) if t.product_id else None
        if not r.product_name and t.equipments and t.equipments[0].product_id:
            r.product_name = product_map.get(t.equipments[0].product_id)
        return r

    return TicketListResponse(
        items=[_serialize(t) for t in tickets],
        total=total,
        limit=limit,
        offset=offset,
        expediente=_expediente(agora),
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

    response = _serialize_ticket(ticket, actor=actor)
    if ticket.assignee_id:
        assignee = await db.get(User, ticket.assignee_id)
        response.assignee_name = assignee.name if assignee else None
    await _fill_product_and_equipment(response, ticket, db)
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
            registra_historico(
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
            registra_historico(db, ticket.id, actor.id, field, old_val, new_val)
        setattr(ticket, field, new_val)

    ticket.updated_at = datetime.now(UTC)
    _audit(db, AuditAction.update, actor.id, ticket.id)
    await commit_e_notificar(db)
    await db.refresh(ticket)
    return _serialize_ticket(ticket, actor=actor)


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
        registra_historico(
            db, ticket.id, actor.id, "client_observation", old, body.client_observation
        )
    _audit(db, AuditAction.update, actor.id, ticket.id)
    await commit_e_notificar(db)
    await db.refresh(ticket)
    return _serialize_ticket(ticket, actor=actor)


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
        registra_historico(
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

    response = _serialize_ticket(ticket, actor=actor)
    await _fill_product_and_equipment(response, ticket, db)
    return response


def _pode_estender(ticket: Ticket, agora: datetime) -> datetime:
    """Garante que este chamado aceita prorrogação e devolve o prazo atual.

    Quatro recusas, todas 409 — a requisição está bem formada, o ESTADO é que
    não permite:

    - chamado encerrado: prorrogar prazo de quem já acabou não quer dizer nada;
    - sem prioridade: não há prazo de resolução para prorrogar;
    - sem `sla_resolve_due_at`: idem, e é o caso do chamado não triado;
    - **prazo efetivo já vencido**.

    A última recusa NÃO olha `sla_resolve_breach`. A flag só é recalculada em
    caminhos de escrita, então um chamado vencido e intocado chega com ela
    falsa — e seria justamente esse que alguém prorrogaria para apagar a
    violação antes que ela fosse marcada. Quem decide é a comparação de `agora`
    com o prazo efetivo que o motor calcula.
    """
    if ticket.status in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Este chamado já foi encerrado e o prazo de resolução não pode "
                "mais ser estendido."
            ),
        )

    if ticket.priority is None or ticket.sla_resolve_due_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Este chamado ainda não tem prazo de resolução. Defina a "
                "prioridade antes de estender o SLA."
            ),
        )

    atual = prazo_efetivo_de_resolucao(ticket)
    if atual is None or agora > atual:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "O prazo de resolução deste chamado já venceu. A extensão serve "
                "para evitar o atraso, não para desfazê-lo."
            ),
        )

    return atual


@router.get(
    "/tickets/{ticket_id}/sla/extend/preview",
    response_model=SlaExtensionPreview,
)
async def preview_sla_extension(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    days: DiasDeExtensao = Query(...),
) -> SlaExtensionPreview:
    """O prazo que a concessão produziria, sem conceder nada.

    Existe para o modal poder mostrar "de … para …" antes de confirmar **sem
    recalcular prazo na tela**: dia útil, jornada e feriado são do motor, e um
    `add_business_days` em TypeScript seria a segunda verdade que a entrega do
    relógio acabou de eliminar.

    Só leitura — não escreve, não commita. As mesmas recusas do POST valem
    aqui, para o modal não oferecer um botão que o servidor vai negar.
    """
    ticket = await get_or_404(db, Ticket, ticket_id, _CHAMADO_NAO_ENCONTRADO)
    agora = datetime.now(UTC)
    atual = _pode_estender(ticket, agora)

    minutos = minutos_uteis_de_dias(int(days))
    return SlaExtensionPreview(
        days=int(days),
        business_minutes=minutos,
        prazo_atual=atual,
        novo_prazo=add_business_minutes(atual, minutos),
    )


@router.post("/tickets/{ticket_id}/sla/extend", response_model=TicketResponse)
async def extend_sla(
    ticket_id: uuid.UUID,
    body: SlaExtensionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TicketResponse:
    """Prorroga o prazo de RESOLUÇÃO em dias úteis, com justificativa pública.

    POST e não PATCH porque cada concessão é um EVENTO: acontece mais de uma
    vez, é cumulativa, e cada uma vira uma linha própria em
    `ticket_sla_extensions`.

    **O prazo original não é tocado.** `sla_resolve_due_at` continua sendo o
    que a prioridade carimbou; o que cresce é o acumulador
    `sla_resolve_extension_total_min`. Guardar o acumulado — e não um prazo já
    calculado — é o que faz duas concessões de +3 e +1 valerem exatamente uma
    de +4, e o que faz a extensão sobreviver a uma troca de prioridade, que
    recarimba só a base.

    O SLA de RESPOSTA não muda: a extensão só existe no caminho da resolução,
    e isso é estrutural — `prazo_efetivo_de_resposta` nem recebe o campo.
    """
    ticket = await get_or_404(db, Ticket, ticket_id, _CHAMADO_NAO_ENCONTRADO)
    agora = datetime.now(UTC)
    prazo_anterior = _pode_estender(ticket, agora)

    dias = int(body.days)
    minutos = minutos_uteis_de_dias(dias)
    ticket.sla_resolve_extension_total_min = (ticket.sla_resolve_extension_total_min or 0) + minutos
    # A coluna que o painel consome acompanha na mesma escrita. Sem isto, o
    # chamado apareceria prorrogado na tela e violado no relatório.
    atualiza_prazo_efetivo(ticket)
    ticket.updated_at = agora

    novo_prazo = ticket.sla_resolve_effective_due_at

    # O evento, com tudo que a auditoria precisa. A tabela é append-only pela
    # regra de negócio: nenhum fluxo edita ou apaga uma concessão.
    db.add(
        TicketSlaExtension(
            id=uuid.uuid4(),
            ticket_id=ticket.id,
            user_id=actor.id,
            days=dias,
            business_minutes=minutos,
            justification=body.justification,
            previous_effective_due_at=prazo_anterior,
            new_effective_due_at=novo_prazo,
        )
    )

    # E a linha da timeline, para a Atividade não ficar com um buraco onde
    # houve decisão de prazo. A fonte auditável dos dados é a tabela acima.
    registra_historico(
        db,
        ticket.id,
        actor.id,
        "sla_extension",
        prazo_anterior.isoformat() if prazo_anterior else None,
        novo_prazo.isoformat() if novo_prazo else None,
        body.justification,
    )
    _audit(db, AuditAction.update, actor.id, ticket.id)

    plural_dias = "dia útil" if dias == 1 else "dias úteis"
    await notify(
        db,
        ticket.creator_id,
        NotificationType.ticket_updated,
        "Prazo de resolução atualizado",
        (
            f"O prazo de resolução do chamado {ticket.protocol} foi estendido em "
            f"{dias} {plural_dias}.\n"
            f"Novo prazo: {_formata_prazo(novo_prazo)}.\n"
            f"Justificativa: {body.justification}"
        ),
        data={
            "ticket_id": str(ticket.id),
            "protocol": ticket.protocol,
            "days": dias,
        },
        settings=settings,
    )

    await commit_e_notificar(db)
    await db.refresh(ticket)
    return _serialize_ticket(ticket, actor=actor)


@router.patch("/tickets/{ticket_id}/priority", response_model=TicketResponse)
async def update_ticket_priority(
    ticket_id: uuid.UUID,
    body: TicketPriorityUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> TicketResponse:
    """A triagem: define (ou troca) a prioridade e carimba o SLA correspondente.

    Técnico e administrador têm a MESMA permissão aqui — quem tria é quem
    atende. O cliente recebe 403: ele descreve o problema, não classifica a
    urgência dele.

    **O prazo conta da ABERTURA, não deste clique.** `apply_sla_config` recebe
    `ticket.created_at`, e não o `now`, porque o RN-013 diz que o SLA conta da
    abertura até a resolução (ver "SLA" em `docs/decisoes-e-regras.md`) e a
    triagem não é um recomeço. A consequência é real e foi decidida com ela à
    vista: triagem demorada entrega um chamado que **já nasce vencido**, e é
    assim que a demora aparece na conformidade em vez de sumir.

    Duas coisas que esta função deliberadamente NÃO faz:

    **Não desfaz violação de primeira resposta.** `check_breaches` só olha o
    prazo de resposta enquanto `sla_first_response` é nulo, então um chamado já
    respondido não passa a dever resposta por causa de um prazo retroativo. A
    espera continua medida onde ela é medida — `sla_first_response -
    created_at`, no relatório —, só não vira acusação de prazo que não existia.

    **Não mexe no SLA de chamado encerrado.** Resolvido, fechado ou cancelado
    guardam prazos e marcas do momento em que foram encerrados, e uma
    justificativa de violação já escrita se apoia naqueles números. Corrigir a
    prioridade de um chamado morto é catalogação: grava o campo e o histórico,
    e deixa o relógio como está. É a mesma regra do `marca_violacao_ao_resolver`
    — só acrescenta, nunca desmarca.
    """
    ticket = await get_or_404(db, Ticket, ticket_id, _CHAMADO_NAO_ENCONTRADO)

    anterior = ticket.priority
    if anterior == body.priority:
        return _serialize_ticket(ticket, actor=actor)

    now = datetime.now(UTC)

    sla_result = await db.execute(
        select(SLAConfig).where(
            SLAConfig.level == body.priority.value,
            SLAConfig.is_active.is_(True),
        )
    )
    sla_config = sla_result.scalar_one_or_none()

    ticket.priority = body.priority

    # Sem `SLAConfig` ativa para o nível não há prazo a carimbar — a prioridade
    # grava assim mesmo. O contrário deixaria o chamado sem triagem porque
    # falta uma linha de catálogo.
    if sla_config and ticket.status not in _TERMINAL_STATUSES:
        apply_sla_config(ticket, sla_config, ticket.created_at)
        # Com o prazo vindo da abertura, a violação pode já ser fato no
        # instante em que ele é carimbado. Avaliar aqui evita um chamado
        # vencido que só se declara vencido na próxima escrita alheia.
        check_breaches(ticket, now)

    ticket.updated_at = now

    registra_historico(
        db,
        ticket.id,
        actor.id,
        "priority",
        anterior.value if anterior else None,
        body.priority.value,
    )
    _audit(db, AuditAction.update, actor.id, ticket.id)
    await commit_e_notificar(db)
    await db.refresh(ticket)
    return _serialize_ticket(ticket, actor=actor)


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
    # Antes de mudar qualquer coisa: fora do prazo sem justificativa, recusa.
    justificativa = (
        _justificativa_de_sla(ticket, now, body.sla_breach_justification)
        if body.status == TicketStatus.resolved
        else None
    )
    old_status = ticket.status
    ticket.status = body.status
    ticket.updated_at = now

    # A marca precisa ser carimbada AQUI, e nao pelo `check_breaches` mais
    # abaixo: quando ele roda, o status ja e terminal e ele pula o teste de
    # resolucao. Ver marca_violacao_ao_resolver.
    if body.status == TicketStatus.resolved:
        marca_violacao_ao_resolver(ticket, now)

    if justificativa:
        ticket.sla_breach_justification = justificativa
        registra_historico(
            db,
            ticket.id,
            actor.id,
            "sla_breach_justification",
            None,
            justificativa,
            "Justificativa do SLA violado",
        )

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

    registra_historico(
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
    return _serialize_ticket(ticket, actor=actor)


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
    # Antes de mudar qualquer coisa: fora do prazo sem justificativa, recusa.
    justificativa = _justificativa_de_sla(ticket, now, body.sla_breach_justification)
    old_status = ticket.status
    ticket.status = TicketStatus.resolved
    ticket.resolution_note = body.resolution_note
    # Mesmo motivo do caminho do PATCH: o `check_breaches` la embaixo ja
    # encontra o status terminal e nao marca a violacao de resolucao.
    marca_violacao_ao_resolver(ticket, now)

    if justificativa:
        ticket.sla_breach_justification = justificativa
        registra_historico(
            db,
            ticket.id,
            actor.id,
            "sla_breach_justification",
            None,
            justificativa,
            "Justificativa do SLA violado",
        )
    ticket.closed_at = now
    ticket.resolved_at = now
    ticket.updated_at = now

    # A nota de resolução é texto que o cliente lê: vale como primeira
    # resposta quando ninguém falou antes, venha o chamado de qual status vier.
    register_first_response(ticket, now, responder_id=actor.id)
    if old_status in _PAUSE_STATUSES:
        resume_sla(ticket, now)
    check_breaches(ticket, now)

    registra_historico(
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
        data={"ticket_id": str(ticket.id), "protocol": ticket.protocol, "new_status": "resolved"},
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
    return _serialize_ticket(ticket, actor=actor)


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
    #
    # Chamado sem prioridade não tem por qual nível procurar, e reabrir não é
    # hora de arbitrar uma: ele volta sem prazo, como voltou para a fila de
    # triagem. Quem triar carimba o prazo pelo endpoint de prioridade.
    sla_config = None
    if ticket.priority is not None:
        sla_result = await db.execute(
            select(SLAConfig).where(
                SLAConfig.level == ticket.priority.value,
                SLAConfig.is_active.is_(True),
            )
        )
        sla_config = sla_result.scalar_one_or_none()
    if sla_config:
        # Usa a configuração VIGENTE, não a que valia quando o chamado nasceu.
        # É exceção consciente à regra de transição dos prazos aprovados pelo
        # SGI: chamado antigo mantém o prazo de origem, mas quem é REABERTO
        # começa um ciclo novo e ele segue a regra de hoje. Congelar exigiria
        # versionar `sla_configs`, porque `sla_config_id` aponta para a linha
        # atual, já editada.
        ticket.sla_resolve_due_at = add_business_minutes(now, sla_config.resolve_time_minutes)
        ticket.sla_resolve_breach = False
    ticket.sla_paused_at = None
    # O tempo pausado é acumulado para esticar o prazo do ciclo em que ocorreu.
    # Como o prazo acima já parte de agora, mantê-lo daria ao ciclo novo um
    # bônus de horas que ninguém esperou.
    ticket.sla_total_paused_ms = 0
    # A extensão pertence ao ciclo que acabou. O ciclo novo começa com o prazo
    # da prioridade, sem o tempo que foi concedido no anterior — herdar daria
    # um bônus que ninguém aprovou para este ciclo.
    #
    # As linhas de `ticket_sla_extensions` do ciclo anterior NÃO são tocadas:
    # a prorrogação aconteceu, foi comunicada ao cliente, e continua auditável.
    ticket.sla_resolve_extension_total_min = 0
    # Os três campos acima mudaram os insumos do prazo efetivo; a coluna que o
    # painel consome acompanha.
    atualiza_prazo_efetivo(ticket)

    registra_historico(
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
            data={
                "ticket_id": str(ticket.id),
                "protocol": ticket.protocol,
                "new_status": new_status.value,
            },
            settings=settings,
        )
    if ticket.creator_id != actor.id:
        await notify(
            db,
            ticket.creator_id,
            NotificationType.ticket_updated,
            "Chamado reaberto",
            f"O ticket {ticket.protocol} foi reaberto e voltou para atendimento.",
            data={
                "ticket_id": str(ticket.id),
                "protocol": ticket.protocol,
                "new_status": new_status.value,
            },
            settings=settings,
        )

    await commit_e_notificar(db)
    await db.refresh(ticket)
    return _serialize_ticket(ticket, actor=actor)


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
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Tickets só podem ser atribuídos a técnicos ou administradores.",
            )
        if new_assignee_user.status != UserStatus.active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
    registra_historico(
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
    return _serialize_ticket(ticket, actor=actor)


@router.post(
    "/tickets/{ticket_id}/calls",
    response_model=TicketCallResponse,
    status_code=status.HTTP_201_CREATED,
)
async def iniciar_ligacao(
    ticket_id: uuid.UUID,
    body: TicketCallCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> TicketCallResponse:
    """Liga para o cliente que abriu o chamado.

    ⚠️ O navegador NÃO escolhe nada. O corpo é `{}` e qualquer campo a mais é
    422 — ver `TicketCallCreate`. Destinatário, telefone, ramal e origem saem
    todos do banco, no instante da ação, em `services/ligacao.py`.

    **201 mesmo quando o fornecedor recusa**, e isso é desenho, não descuido: o
    que esta rota promete é REGISTRAR a tentativa, e ela foi registrada. O
    desfecho vai em `creation_status`, no corpo. Devolver 5xx depois de um
    efeito externo possivelmente ocorrido convida proxy, biblioteca e usuário a
    tentar de novo — e o telefone tocaria duas vezes.

    As recusas que acontecem ANTES de qualquer efeito têm status próprio:
    403 (cliente), 404 (chamado), 422 (estado inválido, destinatário
    inelegível, ator sem ramal), 409 (ligação em andamento ou tentativa recente),
    429 (teto por hora) e 503 (telefonia desligada).
    """
    tentativa = await ligacao.inicia_ligacao(db, ticket_id=ticket_id, ator=actor)
    return TicketCallResponse.model_validate(tentativa)


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
    registra_historico(db, ticket.id, actor.id, "status", old_status.value, "cancelled")
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
    # O cliente não lê evento de campo interno — nem o `field`, nem o antes, nem
    # o depois. No `base`, antes do count, para que total e paginação enxerguem
    # o mesmo conjunto que os itens.
    recorte = filtra_historico_para(actor)
    if recorte is not None:
        base = base.where(recorte)
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
