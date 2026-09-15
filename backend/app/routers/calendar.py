"""
Agenda da equipe — CRUD de eventos do calendário.

Permissões:
  GET    /calendar/events         — admin | technician
  GET    /calendar/event-types    — admin | technician
  POST   /calendar/events         — admin | technician
  PATCH  /calendar/events/{id}    — admin | technician
  DELETE /calendar/events/{id}    — admin | technician
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import authorize
from app.models.models import CalendarEvent, User, UserRole
from app.schemas.calendar import (
    CalendarEventCreate,
    CalendarEventListResponse,
    CalendarEventResponse,
    CalendarEventTypeResponse,
    CalendarEventUpdate,
)
from app.utils.agenda import (
    COR_POR_TIPO,
    FUSO_UTC,
    bordas_do_dia_inteiro,
    cor_do_tipo,
    fala_a_convencao_da_tela_antiga,
    janela_do_mes,
    resolve_fuso,
)

router = APIRouter(prefix="/calendar", tags=["Calendar"])


def _to_response(event: CalendarEvent) -> CalendarEventResponse:
    resp = CalendarEventResponse.model_validate(event)
    if event.creator:
        resp.creator_name = event.creator.name
    return resp


def _fuso_ou_422(nome: str | None) -> ZoneInfo:
    try:
        return resolve_fuso(nome)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


def _bordas(inicio: datetime, fim: datetime, dia_inteiro: bool) -> tuple[datetime, datetime]:
    """As datas como vão para o banco: derivadas quando é dia inteiro."""
    if dia_inteiro:
        return bordas_do_dia_inteiro(inicio, fim)
    return inicio, fim


def _dia_inteiro_do_pedido(
    campos_enviados: set[str], inicio: datetime, fim: datetime, enviado: bool | None
) -> bool | None:
    """O `all_day` que o pedido quis dizer, ou `None` se ele não disse nada.

    **Explícito vence, nos dois sentidos.** A inferência existe só para o cliente
    que não conhece o campo — a tela no ar —, e nunca reescreve a escolha de
    quem o mandou.

    **A pegada é lida no que chegou**, e só quando as duas datas chegaram. Uma
    edição que não mandou data nenhuma não falou convenção nenhuma: ler a linha
    do banco transformaria qualquer troca de título num backfill escondido.
    """
    if "all_day" in campos_enviados:
        return enviado
    datas_chegaram = {"start_date", "end_date"} <= campos_enviados
    if datas_chegaram and fala_a_convencao_da_tela_antiga(inicio, fim):
        return True
    return None


def _valida_ordem(inicio: datetime, fim: datetime) -> None:
    """O fim vem DEPOIS do início. Igual não passa: evento de duração zero não existe.

    A conferência roda sobre os valores JÁ derivados, e não sobre o que chegou.
    Um dia inteiro de um dia só chega com início e fim na mesma data — igual,
    portanto — e só depois de derivado vira `00:00` a `23:59:59.999999`.
    Conferir antes recusaria justamente o caso mais comum da agenda.
    """
    if fim <= inicio:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A data de fim precisa ser posterior à data de início.",
        )


# ── GET /calendar/events ──────────────────────────────────────


@router.get("/events", response_model=CalendarEventListResponse)
async def list_events(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
    # O fuso de quem olha. Sem ele a janela do mês seria a de UTC, e um evento
    # às 22:00 do dia 31 — que é 01:00Z do dia 1º seguinte — cairia no mês
    # errado: a pessoa cria em janeiro e ele aparece em fevereiro.
    timezone: str | None = Query(default=None),
) -> CalendarEventListResponse:
    fuso = _fuso_ou_422(timezone)
    stmt = select(CalendarEvent).order_by(CalendarEvent.start_date)

    if year and month:
        # DUAS janelas, porque são duas naturezas de evento.
        #
        # O evento COM HORA é um instante: ele pertence ao mês de quem olha, e a
        # janela dele é a local. O evento de DIA INTEIRO é data flutuante,
        # ancorada em UTC — a janela dele é a de UTC.
        #
        # Usar só a local punha todo evento antigo de dia inteiro do dia 1º
        # também no mês ANTERIOR: eles são `00:00:00Z`–`23:59:59Z`, e a janela
        # local de Recife só começa às 03:00Z do dia 1º, de modo que o instante
        # inicial deles cai antes dela. Para um evento com hora esse
        # deslocamento é a verdade; para um de dia inteiro é justamente o que a
        # ancoragem em UTC existe para negar. Medido em
        # `test_calendar_postgres.py`.
        inicio_local, fim_local = janela_do_mes(year, month, fuso)
        inicio_utc, fim_utc = janela_do_mes(year, month, FUSO_UTC)
        # Sobreposição, e não contenção: um evento que atravessa a virada do mês
        # pertence aos dois. `>=` e não `>` porque o último microssegundo do dia
        # inteiro ainda está dentro dele.
        stmt = stmt.where(
            or_(
                and_(
                    CalendarEvent.all_day.is_(False),
                    CalendarEvent.start_date < fim_local,
                    CalendarEvent.end_date >= inicio_local,
                ),
                and_(
                    CalendarEvent.all_day.is_(True),
                    CalendarEvent.start_date < fim_utc,
                    CalendarEvent.end_date >= inicio_utc,
                ),
            )
        )

    rows = await db.execute(stmt)
    events = rows.scalars().all()

    # Load creators
    creator_ids = [e.created_by for e in events if e.created_by]
    creators: dict[uuid.UUID, User] = {}
    if creator_ids:
        creator_rows = await db.execute(select(User).where(User.id.in_(creator_ids)))
        for u in creator_rows.scalars().all():
            creators[u.id] = u
    for e in events:
        if e.created_by and e.created_by in creators:
            e.creator = creators[e.created_by]

    return CalendarEventListResponse(
        items=[_to_response(e) for e in events],
        total=len(events),
    )


# ── GET /calendar/event-types ─────────────────────────────────


@router.get("/event-types", response_model=list[CalendarEventTypeResponse])
async def list_event_types(
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> list[CalendarEventTypeResponse]:
    """O mapa tipo → cor, para a tela não precisar de uma cópia dele.

    Sem este endpoint o modal só mostraria a cor de um tipo antes de salvar se
    tivesse o mapa escrito localmente — e a segunda fonte, que esta mudança
    existe para eliminar, voltaria pela porta da frente. Rótulo não vem: texto é
    da tela.

    A ordem é a da declaração do enum, que é a ordem em que a tela já oferece os
    tipos.
    """
    return [CalendarEventTypeResponse(value=tipo, color=cor) for tipo, cor in COR_POR_TIPO.items()]


# ── POST /calendar/events ─────────────────────────────────────


@router.post("/events", response_model=CalendarEventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    body: CalendarEventCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> CalendarEventResponse:
    # A tela no ar não manda `all_day` e fala dia inteiro por convenção — ver
    # `fala_a_convencao_da_tela_antiga`. Sem esta leitura, o padrão `False` do
    # schema gravava cada evento dela como evento com horário.
    dia_inteiro = (
        _dia_inteiro_do_pedido(body.model_fields_set, body.start_date, body.end_date, body.all_day)
        or False
    )
    inicio, fim = _bordas(body.start_date, body.end_date, dia_inteiro)
    _valida_ordem(inicio, fim)

    now = datetime.now(UTC)
    event = CalendarEvent(
        id=uuid.uuid4(),
        title=body.title,
        description=body.description,
        event_type=body.event_type,
        # A coluna é CÓPIA do mapa, gravada para quem lê o banco direto e para um
        # rollback do código. A resposta não a lê — ver `CalendarEventResponse`.
        color=cor_do_tipo(body.event_type),
        start_date=inicio,
        end_date=fim,
        all_day=dia_inteiro,
        created_by=actor.id,
        # Explícito: o default da coluna só valeria no INSERT e a resposta é
        # montada a partir do objeto em memória
        created_at=now,
        updated_at=now,
    )
    event.creator = actor
    db.add(event)
    await db.commit()
    await db.refresh(event)
    event.creator = actor
    return _to_response(event)


# ── PATCH /calendar/events/{event_id} ────────────────────────


@router.patch("/events/{event_id}", response_model=CalendarEventResponse)
async def update_event(
    event_id: uuid.UUID,
    body: CalendarEventUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> CalendarEventResponse:
    result = await db.execute(select(CalendarEvent).where(CalendarEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento não encontrado. Ele pode ter sido removido da agenda.",
        )

    if body.title is not None:
        event.title = body.title
    # `description` é o único campo aqui que precisa distinguir "não enviado" de
    # "enviado como nulo": é o único nullable no modelo, e o front manda nulo
    # explícito quando a pessoa limpa o campo. Com `is not None` esse nulo era
    # ignorado e o texto antigo reaparecia no carregamento seguinte.
    #
    # NÃO uniformize os outros quatro. `title`, `event_type`, `start_date` e
    # `end_date` são NOT NULL no modelo — para eles, ignorar o
    # nulo está correto, e aceitá-lo trocaria este bug por um erro de
    # integridade no banco.
    if "description" in body.model_fields_set:
        event.description = body.description
    if body.event_type is not None:
        event.event_type = body.event_type
        # A cópia acompanha o tipo. Sem isto a coluna voltaria a divergir — que é o
        # defeito que esta mudança existe para fechar.
        event.color = cor_do_tipo(body.event_type)
    if body.start_date is not None:
        event.start_date = body.start_date
    if body.end_date is not None:
        event.end_date = body.end_date
    # Mesma leitura do POST, sobre os valores QUE CHEGARAM. A tela antiga
    # reenvia o payload inteiro ao editar, e é assim que um evento gravado com a
    # chave errada volta a dizer o que ele é.
    dia_inteiro = _dia_inteiro_do_pedido(
        body.model_fields_set, event.start_date, event.end_date, body.all_day
    )
    if dia_inteiro is not None:
        event.all_day = dia_inteiro

    # As bordas são derivadas DEPOIS de aplicar os campos, e com a chave que
    # vale agora. Ligar "dia inteiro" sem mandar data nenhuma precisa reescrever
    # as horas que já estavam lá — senão a coluna diria 14:30 e a chave diria
    # dia inteiro, e o registro passaria a se contradizer.
    event.start_date, event.end_date = _bordas(event.start_date, event.end_date, event.all_day)
    _valida_ordem(event.start_date, event.end_date)

    await db.commit()
    await db.refresh(event)

    if event.created_by:
        creator_row = await db.execute(select(User).where(User.id == event.created_by))
        event.creator = creator_row.scalar_one_or_none()

    return _to_response(event)


# ── DELETE /calendar/events/{event_id} ───────────────────────


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> None:
    result = await db.execute(select(CalendarEvent).where(CalendarEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento não encontrado. Ele pode ter sido removido da agenda.",
        )

    await db.delete(event)
    await db.commit()
