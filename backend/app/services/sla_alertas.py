"""
O aviso de SLA de resolucao proximo do vencimento — Fase 2A.

Por que este arquivo existe
---------------------------
`SLAConfig.warning_threshold` esta no schema desde a primeira migration, e
editavel por prioridade na tela de SLA, onde o texto de ajuda afirma ao
administrador: "o alerta dispara quando o percentual do tempo ja consumido
atingir o limiar". **Nada disparava** — nenhum caminho de producao lia o campo.
Esta rotina nao acrescenta funcionalidade; ela cumpre uma promessa que a
interface ja fazia.

O que ela NAO faz
-----------------
Nao produz `sla_breached`. Nao avisa sobre primeira resposta. Nao altera a
formula do SLA, nem a divida conhecida da pausa em horas corridas, nem o 80/60
fixo do frontend. Cada uma dessas e frente propria, e misturar qualquer uma
aqui tornaria este worker responsavel por mudar indicador publicado.

Nao recalcula SLA
-----------------
`prazo_efetivo_de_resolucao` e `business_minutes_between` sao a fonte de
verdade, e este modulo as CONSOME. A casa ja pagou por um espelho: o chip da
tela calculava o vencimento por conta propria e discordava do motor sempre que
havia pausa, escrevendo "Vencido" horas antes.

O percentual e o MESMO que a tela mostra na barra do cartao:

    total     = business_minutes_between(created_at, prazo_efetivo)
    restante  = business_minutes_between(agora,      prazo_efetivo)
    consumido = (total - restante) / total * 100

Como nao repete
---------------
`sla_alert_events`, com indice unico em
`(ticket_id, alert_kind, effective_due_at, warning_threshold)`. A reivindicacao
e um `INSERT ... ON CONFLICT DO NOTHING RETURNING id` na MESMA transacao das
notificacoes: se a criacao delas levantar, o rollback leva o evento embora e a
rodada seguinte tenta de novo. Sem esse acoplamento existiria o pior dos
estados — o evento registrado e ninguem avisado, para sempre.

Redis aqui e LOCK, nunca memoria de evento: chave que expira nao pode ser a
prova de que um aviso foi dado.
"""

import asyncio
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.models import (
    NotificationType,
    SlaAlertEvent,
    SLAConfig,
    SLALevel,
    Ticket,
)
from app.services.notifications import (
    audiencia_operacional,
    commit_e_notificar,
    notifica_audiencia,
)
from app.utils.sla import (
    _TERMINAL_STATUSES,
    business_minutes_between,
    prazo_efetivo_de_resolucao,
)

# O unico tipo de alerta desta fase. String, nao enum nativo — ver o comentario
# de `SlaAlertEvent.alert_kind`.
ALERTA_RESOLUCAO = "resolution_warning"

_LOCK_KEY = "helphs:lock:sla-warning"

# Mesmo teto do fechamento automatico. Adotado desde o inicio: passar a
# paginar depois significaria mexer no worker com ele em producao.
_BATCH_LIMIT = 200

# Texto que a pessoa le: com acento, ao contrario dos comentarios deste arquivo.
_TITULO = "SLA próximo do vencimento"


# ══════════════════════════════════════════════════════════════
# 1. O calculo
# ══════════════════════════════════════════════════════════════


def consumido_pct(ticket: Ticket, agora: datetime) -> float | None:
    """Quanto do prazo UTIL de resolucao ja foi consumido, em percentual.

    `None` quando nao ha o que medir: sem prazo, ou prazo sem duracao util
    nenhuma. O segundo caso e real — triagem feita depois do prazo carimba um
    chamado cujo total util e zero — e devolver 100 ali seria inventar consumo
    a partir de uma divisao por zero.

    Nao ha clamp: se o valor passar de 100, o chamado ja venceu, e quem decide
    o que fazer com isso e `e_candidato`. Aparar aqui esconderia erro de
    calculo em vez de revelar.
    """
    prazo = prazo_efetivo_de_resolucao(ticket)
    if prazo is None:
        return None

    total = business_minutes_between(ticket.created_at, prazo)
    if total <= 0:
        return None

    restante = business_minutes_between(agora, prazo)
    return (total - restante) / total * 100


def threshold_da_prioridade(ticket: Ticket, configs: dict[SLALevel, SLAConfig]) -> int | None:
    """O limiar da prioridade ATUAL do chamado, em percentual inteiro.

    `None` sem prioridade ou sem `SLAConfig` ativa para o nivel. Chutar 80 aqui
    reproduziria exatamente a divergencia que esta fase fecha: um numero fixo no
    codigo ao lado de um campo configuravel que ninguem le.

    A conversao `SLALevel(...)` e explicita porque `Ticket.priority` e
    `TicketPriority`: dois enums distintos com os mesmos valores, e o router da
    triagem tambem compara por valor.
    """
    if ticket.priority is None:
        return None
    config = configs.get(SLALevel(ticket.priority.value))
    return None if config is None else config.warning_threshold


def e_candidato(ticket: Ticket, agora: datetime, configs: dict[SLALevel, SLAConfig]) -> bool:
    """O chamado merece aviso NESTE instante?

    Reaplica em Python as condicoes que a consulta ja filtra em SQL. Nao e
    redundancia inutil: a consulta pre-seleciona pela coluna MATERIALIZADA
    (`sla_resolve_effective_due_at`, que e indexada), e a decisao e tomada pelo
    motor (`prazo_efetivo_de_resolucao`). Quando os dois discordam — coluna
    desatualizada —, quem vale e o motor.

    Vencido sai fora: passado o prazo o assunto e violacao, e dizer "esta
    chegando" sobre algo que ja chegou e pior que calar.

    Pausado sai fora: a pausa EM CURSO nao entra no prazo efetivo (divida
    antiga, documentada), logo um chamado parado continua se aproximando do
    vencimento. Avisar a equipe sobre um chamado que ela nao pode tocar porque
    espera o cliente e o comeco do ruido que derruba o canal.
    """
    if ticket.status in _TERMINAL_STATUSES:
        return False
    if ticket.sla_paused_at is not None:
        return False

    limiar = threshold_da_prioridade(ticket, configs)
    if limiar is None:
        return False

    prazo = prazo_efetivo_de_resolucao(ticket)
    if prazo is None or prazo <= agora:
        return False

    consumido = consumido_pct(ticket, agora)
    if consumido is None:
        return False

    # `>=`, e nao `>`: o limiar e o ponto em que o aviso deve sair. Com `>`, um
    # chamado que caisse exatamente em 80,0 so avisaria na rodada seguinte — ou
    # nunca, se o expediente fechasse no meio.
    return consumido >= limiar


# ══════════════════════════════════════════════════════════════
# 2. O texto
# ══════════════════════════════════════════════════════════════


def assunto_do_aviso(ticket: Ticket) -> str:
    """Protocolo, nunca titulo.

    O titulo e texto escrito pelo cliente. Ele saiu das linhas de log em
    25/09/2026 pela mesma razao, e assunto de e-mail atravessa mais caixas de
    entrada do que log atravessa terminais.
    """
    return f"[HelpHS] {_TITULO} — {ticket.protocol}"


def mensagem_do_aviso(ticket: Ticket, consumido: float, restante_min: int) -> str:
    """O corpo do sininho e do e-mail: protocolo, consumo e o que sobra.

    Informacao operacional suficiente para agir sem abrir o chamado, e nada
    mais: sem titulo, sem nome de cliente, sem empresa.
    """
    return (
        f"{ticket.protocol} — {consumido:.0f}% do prazo de resolução consumido. "
        f"Restam {restante_min} minutos úteis."
    )


def dados_do_aviso(
    ticket: Ticket, prazo: datetime, limiar: int, consumido: float
) -> dict[str, object]:
    """O `data` da notificacao.

    `ticket_id` e obrigatorio e nao e decoracao: e dele que
    `_link_do_chamado` monta o botao do e-mail e a navegacao do sininho. Doze
    dos catorze e-mails chegavam sem link em 04/09 justamente por nao usar esta
    chave.
    """
    return {
        "ticket_id": str(ticket.id),
        "protocol": ticket.protocol,
        "sla_kind": "resolution",
        "warning_threshold": limiar,
        "effective_due_at": prazo.isoformat(),
        "consumed_pct": round(consumido, 1),
    }


# ══════════════════════════════════════════════════════════════
# 3. A rodada
# ══════════════════════════════════════════════════════════════


async def configs_por_nivel(db: AsyncSession) -> dict[SLALevel, SLAConfig]:
    """As quatro configuracoes ativas, em UMA consulta por rodada.

    Consultar por chamado faria N+1 com N igual ao lote — 200 consultas para
    ler quatro linhas que nao mudam durante a rodada.
    """
    resultado = await db.execute(select(SLAConfig).where(SLAConfig.is_active.is_(True)))
    return {config.level: config for config in resultado.scalars().all()}


async def candidatos(db: AsyncSession, agora: datetime) -> Sequence[Ticket]:
    """Os chamados que PODEM estar na faixa, em um lote ordenado por urgencia.

    O filtro usa a coluna materializada `sla_resolve_effective_due_at`, que e
    indexada (`ix_tickets_sla_resolve_effective_due_at`) e escrita apenas por
    `atualiza_prazo_efetivo`. A decisao final e do motor — ver `e_candidato`.

    `ORDER BY` crescente: os prazos mais proximos primeiro. Com o lote cheio, o
    que fica de fora e o que tem mais tempo, e ele volta na rodada seguinte.
    """
    resultado = await db.execute(
        select(Ticket)
        .where(
            Ticket.status.not_in(_TERMINAL_STATUSES),
            Ticket.priority.is_not(None),
            Ticket.sla_resolve_effective_due_at.is_not(None),
            Ticket.sla_paused_at.is_(None),
            Ticket.sla_resolve_effective_due_at > agora,
        )
        .order_by(Ticket.sla_resolve_effective_due_at.asc())
        .limit(_BATCH_LIMIT)
    )
    return resultado.scalars().all()


async def reivindica_evento(
    db: AsyncSession,
    ticket: Ticket,
    prazo: datetime,
    limiar: int,
) -> bool:
    """Tenta registrar o evento. `True` significa "e meu, pode avisar".

    `ON CONFLICT DO NOTHING RETURNING id` e uma operacao so: o banco decide quem
    ganhou, e nao ha janela entre consultar e inserir. Duas instancias que
    cheguem juntas no mesmo chamado serializam no indice unico — a segunda
    espera a primeira e recebe zero linhas.

    A insercao fica na transacao da rodada de proposito. Se a criacao das
    notificacoes levantar depois disto, o rollback leva o evento embora e a
    proxima rodada tenta de novo. Commitar aqui separado criaria o unico estado
    irrecuperavel possivel: evento gravado, ninguem avisado, para sempre.
    """
    comando = (
        pg_insert(SlaAlertEvent)
        .values(
            id=uuid.uuid4(),
            ticket_id=ticket.id,
            alert_kind=ALERTA_RESOLUCAO,
            effective_due_at=prazo,
            warning_threshold=limiar,
            priority=None if ticket.priority is None else ticket.priority.value,
            reopen_count=ticket.reopen_count or 0,
            extension_total_min=ticket.sla_resolve_extension_total_min or 0,
        )
        .on_conflict_do_nothing(
            index_elements=["ticket_id", "alert_kind", "effective_due_at", "warning_threshold"]
        )
        .returning(SlaAlertEvent.id)
    )
    resultado = await db.execute(comando)
    return resultado.scalar_one_or_none() is not None


async def avisa_sla_proximo(
    db: AsyncSession,
    settings: Settings,
    agora: datetime | None = None,
) -> int:
    """Uma rodada completa. Devolve quantos chamados geraram aviso.

    A audiencia e carregada NO MAXIMO uma vez, e so quando ha o primeiro aviso a
    dar: rodada sem nada na faixa — o caso comum — nao consulta usuarios.

    O commit e daqui: esta rotina nao tem handler HTTP dono da transacao, como
    no fechamento automatico.
    """
    agora = agora or datetime.now(UTC)
    configs = await configs_por_nivel(db)
    if not configs:
        return 0

    equipe: Sequence | None = None
    avisados = 0

    for ticket in await candidatos(db, agora):
        if not e_candidato(ticket, agora, configs):
            continue

        prazo = prazo_efetivo_de_resolucao(ticket)
        limiar = threshold_da_prioridade(ticket, configs)
        consumido = consumido_pct(ticket, agora)
        # Garantido por `e_candidato`; a guarda existe para o mypy e para quem
        # chamar esta funcao fora da ordem.
        if prazo is None or limiar is None or consumido is None:
            continue

        if not await reivindica_evento(db, ticket, prazo, limiar):
            continue  # outra instancia ganhou, ou ja avisamos deste prazo

        if equipe is None:
            equipe = await audiencia_operacional(db)

        await notifica_audiencia(
            db,
            equipe,
            NotificationType.sla_warning,
            _TITULO,
            mensagem_do_aviso(ticket, consumido, business_minutes_between(agora, prazo)),
            data=dados_do_aviso(ticket, prazo, limiar, consumido),
            settings=settings,
            email_subject=assunto_do_aviso(ticket),
        )
        avisados += 1

    if avisados:
        await commit_e_notificar(db)
        logger.info(f"Aviso de SLA: {avisados} chamado(s) na faixa de alerta")

    return avisados


# ══════════════════════════════════════════════════════════════
# 4. O laco
# ══════════════════════════════════════════════════════════════

# Instante da ultima rodada que terminou sem erro. Vive na memoria DESTE
# processo, como no fechamento automatico: a pergunta que ele responde e "o laco
# deste processo continua girando?", nao "a rotina esta em dia no cluster".
_ultima_rodada_sem_erro: datetime | None = None


def ultima_rodada_sem_erro() -> datetime | None:
    """Quando esta instancia concluiu uma rodada de aviso sem erro.

    `None` significa que nenhuma rodada concluiu desde o boot — o laco espera
    antes da primeira, entao `None` e o normal logo depois de subir.

    Conta como concluida a rodada em que OUTRO worker segurava o lock: a rotina
    aconteceu, este processo apenas cedeu a vez.

    NAO conta rodada pulada por Redis fora do ar nem rodada que levantou: nos
    dois casos o aviso nao aconteceu, e dizer que aconteceu seria a mentira que
    este carimbo existe para evitar.
    """
    return _ultima_rodada_sem_erro


async def _run_once() -> None:
    """Uma rodada, protegida por lock para nao repetir entre os workers."""
    global _ultima_rodada_sem_erro

    from app.core.database import AsyncSessionLocal
    from app.core.redis import get_redis

    settings = get_settings()
    ttl = max(60, settings.sla_warning_interval_seconds - 60)

    try:
        redis = await get_redis()
        got_lock = await redis.set(_LOCK_KEY, "1", nx=True, ex=ttl)
    except Exception as exc:  # noqa: BLE001 — Redis fora do ar nao pode derrubar a API
        logger.warning(f"Aviso de SLA pulado (Redis indisponivel): {exc}")
        return

    if not got_lock:
        # Outra instancia esta cuidando desta rodada — a rotina aconteceu.
        _ultima_rodada_sem_erro = datetime.now(UTC)
        return

    try:
        async with AsyncSessionLocal() as db:
            await avisa_sla_proximo(db, settings)
        _ultima_rodada_sem_erro = datetime.now(UTC)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Falha na rotina de aviso de SLA: {exc}")


async def sla_warning_loop() -> None:
    settings = get_settings()
    intervalo = settings.sla_warning_interval_seconds

    # Um respiro depois do boot: migrations e seeds ainda podem estar rodando.
    await asyncio.sleep(min(60, intervalo))

    while True:
        try:
            await _run_once()
        except asyncio.CancelledError:
            # Redundante por construcao — CancelledError e BaseException desde o
            # 3.8 —, e escrito para que a linha de baixo nunca seja alargada
            # para BaseException sem que alguem veja o que isso quebraria: o
            # shutdown faz cancel() e depois await na task, e um laco que
            # engolisse o cancelamento travaria esse await.
            raise
        except Exception as exc:  # noqa: BLE001
            # Sem este except a task morre aqui e o aviso para ate o proximo
            # restart, calado. Nem todo caminho de `_run_once` esta protegido
            # por dentro: os imports tardios e o `get_settings()` ficam fora.
            logger.error(f"Rodada de aviso de SLA levantou; o laco segue: {exc}")

        await asyncio.sleep(intervalo)


def start_sla_warning_worker() -> asyncio.Task | None:
    """Sobe o laco em background. Devolve None quando a rotina esta desligada."""
    settings = get_settings()
    if settings.sla_warning_interval_seconds <= 0:
        logger.info("Aviso de SLA desligado (intervalo = 0)")
        return None

    logger.info(f"Aviso de SLA ativo: verificando a cada {settings.sla_warning_interval_seconds}s")
    return asyncio.create_task(sla_warning_loop(), name="sla-warning")
