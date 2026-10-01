"""
Outbox durável de e-mail — Fase 3A (estrutura, worker) + Fase 3B (notificações

operacionais) + Fase 3C (conta/autenticação).

Desde a Fase 3B, `notifications.py` grava `Notification` + `EmailOutbox` na
MESMA transação (via `enqueue_email`, chamado de dentro de `notify`/
`notifica_audiencia`) — o antigo fire-and-forget (`commit_e_notificar` →
`asyncio.create_task`) não existe mais.

Desde a Fase 3C, os três e-mails de conta/autenticação (`verification`,
`password_reset`, `account_exists`) também passam por aqui, via
`enqueue_account_email` — mas SEM `Notification` por baixo: essa origem
referencia `user_id`+`event_type` direto (ver `app/models/models.py:
EmailOutbox` para a CHECK que garante as duas origens nunca se misturarem).
O token JWT nunca é persistido — é gerado pelo worker, em `_processa_conta`,
no momento do envio, a partir do `User` carregado por `user_id`.

Por que roda dentro da API, e não numa fila
--------------------------------------------
Mesmo motivo do fechamento automático e do aviso de SLA (ver
`ticket_lifecycle.py`, `sla_alertas.py`): um processo só, `start.sh` sobe
apenas o uvicorn, e uma segunda infraestrutura só para isto não se paga.

Concorrência: PostgreSQL, não Redis
------------------------------------
Os dois workers existentes usam um lock Redis (`SET NX EX`) porque a rotina
deles é "faça isto uma vez por intervalo", e o lock decide QUEM faz. Aqui o
problema é outro: múltiplas LINHAS, cada uma podendo ser reivindicada por
qualquer worker, sem que duas reivindiquem a mesma. `SELECT ... FOR UPDATE
SKIP LOCKED` resolve isso nativamente, no próprio PostgreSQL — e com
`--workers 1` em produção hoje, o cenário real de concorrência é entre CICLOS
do laço deste worker (um atrasado, o próximo já disparando), não entre
processos.

Redis não participa da garantia de corretude aqui: não há chamada a ele em
nenhum caminho deste módulo. Um Redis fora do ar não impede a outbox de
funcionar — é o requisito nº10 da auditoria da Fase 3 ("PostgreSQL deve ser a
fonte durável, Redis pode ser lock"), levado ao limite de nem precisar do lock.

Garantia: at-least-once, não exactly-once
-------------------------------------------
Documentado também no modelo (`app/models/models.py:EmailOutbox`): existe uma
janela entre o SMTP aceitar a mensagem e este processo persistir `sent`. Se o
processo morrer nesse intervalo exato, a recuperação de linha travada
(`recupera_travados`) devolve a linha para `pending` e ela É REENVIADA — o
e-mail pode sair duas vezes. Não há como fechar essa janela sem um protocolo
de confirmação do provedor SMTP que este sistema não tem. A escolha é
deliberada: entre "nunca perder" (at-least-once) e "nunca duplicar"
(exactly-once, inatingível aqui sem infraestrutura nova), perder um e-mail
operacional é pior do que raramente duplicar um.
"""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.models.models import EmailOutbox, Notification, NotificationType, Ticket, User, UserStatus
from app.services import account_emails, account_tokens
from app.services.email import (
    EmailDeliveryResult,
    EmailDeliveryStatus,
    send_email_detalhado,
)
from app.services.email_layout import em_html, em_texto
from app.services.notifications import _assunto_do_email, _mensagem_do_email

# ══════════════════════════════════════════════════════════════
# 1. Enqueue — API para quem grava a notificação (usado a partir da Fase 3B)
# ══════════════════════════════════════════════════════════════


def enqueue_email(
    db: AsyncSession,
    notification: Notification,
    *,
    agora: datetime | None = None,
) -> EmailOutbox:
    """Adiciona a linha da outbox à SESSÃO recebida. Não abre sessão própria,

    não commita. Quem chama continua dono da transação — é o que torna
    possível, na Fase 3B, gravar `Notification` + `EmailOutbox` no mesmo
    commit (Transactional Outbox Pattern): se esta função commitasse por
    conta própria, um rollback depois dela deixaria a outbox órfã de uma
    notificação que nunca existiu.

    `notification.id` já está preenchido neste ponto mesmo sem flush — é a
    mesma convenção de `_grava_notificacao`: o id nasce em Python
    (`uuid.uuid4()`), não no banco.
    """
    outbox = EmailOutbox(
        id=uuid.uuid4(),
        notification_id=notification.id,
        status="pending",
        attempts=0,
        next_attempt_at=agora or datetime.now(UTC),
    )
    db.add(outbox)
    return outbox


_EVENT_TYPES_CONTA = frozenset({"verification", "password_reset", "account_exists"})


def enqueue_account_email(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    event_type: str,
    intent_id: uuid.UUID | str,
    agora: datetime | None = None,
) -> EmailOutbox:
    """Adiciona a linha da outbox de CONTA à sessão recebida — mesma regra de

    `enqueue_email`: não abre sessão própria, não commita, quem chama
    continua dono da transação.

    `intent_id` é OBRIGATÓRIO e vem de fora — esta função não gera um UUID
    novo internamente. Isso é o que separa duplicação técnica (o CHAMADOR
    reusa o mesmo `intent_id` — mesma requisição, retry de framework — e
    colide na UNIQUE de `dedup_key`) de um pedido novo legítimo (o chamador
    gera um `intent_id` novo a cada request de negócio — ex.: cada clique em
    "esqueci minha senha" — e a `dedup_key` sai diferente, sem colidir).

    `dedup_key = f"{event_type}:{user_id}:{intent_id}"` — o mesmo papel que
    `UNIQUE(notification_id)` cumpre para a origem Notification, adaptado
    para uma origem sem `Notification` para ancorar a identidade.
    """
    if event_type not in _EVENT_TYPES_CONTA:
        raise ValueError(f"event_type desconhecido: {event_type}")

    outbox = EmailOutbox(
        id=uuid.uuid4(),
        user_id=user_id,
        event_type=event_type,
        dedup_key=f"{event_type}:{user_id}:{intent_id}",
        status="pending",
        attempts=0,
        next_attempt_at=agora or datetime.now(UTC),
    )
    db.add(outbox)
    return outbox


async def enfileira_email_de_conta_em_segundo_plano(
    user_id: uuid.UUID, event_type: str, intent_id: uuid.UUID
) -> None:
    """Abre uma sessão curta própria e SÓ enfileira — nunca manda SMTP.

    Usada via `BackgroundTasks` em `forgot_password`/`resend_verification`
    (`app/routers/auth.py`): esses dois fluxos não têm alteração de negócio
    para ancorar a intenção na mesma transação do request (diferente de
    `register`, que sempre cria ou encontra um `User`) — mover só o ENQUEUE
    para depois da resposta preserva a neutralidade de tempo entre "usuário
    existe" e "usuário não existe" que esses dois endpoints já garantiam
    antes da Fase 3C (ver a auditoria da Fase 3C, achado central).

    Isto reabre, deliberadamente, uma pequena janela de não-durabilidade
    entre a resposta HTTP sair e este commit acontecer: se o processo morrer
    nesse intervalo exato, a intenção se perde e a pessoa não recebe o
    e-mail, sem nenhum registro de que deveria. A janela é bem menor que a de
    antes da Fase 3 inteira (só um INSERT, não mais um SMTP síncrono
    aguardado), mas não é zero — é o preço de não reabrir o oráculo de tempo
    de resposta, e foi uma escolha deliberada, não um descuido.
    """
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        enqueue_account_email(db, user_id=user_id, event_type=event_type, intent_id=intent_id)
        await db.commit()


# ══════════════════════════════════════════════════════════════
# 2. Backoff — regra pura, centralizada, testável isoladamente
# ══════════════════════════════════════════════════════════════

MAX_ATTEMPTS = 5

# Minutos de espera depois da N-ésima tentativa malsucedida. Chave 5 não
# existe de propósito: a 5ª falha vai direto para `dead` (ver
# `proximo_estado_apos_falha`), e um valor aqui nunca seria lido.
_BACKOFF_MINUTOS_APOS_TENTATIVA: dict[int, int] = {1: 1, 2: 5, 3: 15, 4: 60}


def proximo_estado_apos_falha(attempts: int, agora: datetime) -> tuple[str, datetime | None]:
    """`attempts` já é a contagem PÓS-incremento desta falha (1..5).

    Devolve `(status, next_attempt_at)`. `next_attempt_at` é `None` quando o
    status devolvido é `dead` — não há próxima tentativa para agendar.
    """
    if attempts >= MAX_ATTEMPTS:
        return "dead", None
    delay_min = _BACKOFF_MINUTOS_APOS_TENTATIVA[attempts]
    return "pending", agora + timedelta(minutes=delay_min)


# ══════════════════════════════════════════════════════════════
# 3. Reivindicação — SELECT ... FOR UPDATE SKIP LOCKED, transação curta
# ══════════════════════════════════════════════════════════════


async def reivindica_lote(
    db_factory: async_sessionmaker[AsyncSession],
    *,
    limite: int,
    worker_id: str,
    agora: datetime | None = None,
) -> list[uuid.UUID]:
    """Reivindica até `limite` linhas `pending` vencidas, atomicamente.

    BEGIN → SELECT ... FOR UPDATE SKIP LOCKED → UPDATE para `processing` →
    COMMIT. O commit acontece ANTES de qualquer tentativa de envio: nenhum
    lock de linha fica aberto durante a chamada de rede ao SMTP — é a garantia
    de que um provedor lento nunca prende o banco.

    Duas chamadas concorrentes desta função (dois workers, ou dois ciclos
    sobrepostos) nunca reivindicam a mesma linha: `SKIP LOCKED` faz a segunda
    pular qualquer linha que a primeira já tenha travado, mesmo que a primeira
    ainda não tenha commitado.
    """
    agora = agora or datetime.now(UTC)
    async with db_factory() as db:
        resultado = await db.execute(
            select(EmailOutbox.id)
            .where(EmailOutbox.status == "pending", EmailOutbox.next_attempt_at <= agora)
            .order_by(EmailOutbox.next_attempt_at)
            .limit(limite)
            .with_for_update(skip_locked=True)
        )
        ids = [linha[0] for linha in resultado.all()]
        if ids:
            await db.execute(
                update(EmailOutbox)
                .where(EmailOutbox.id.in_(ids))
                .values(status="processing", locked_at=agora, locked_by=worker_id)
            )
        await db.commit()
        return ids


async def recupera_travados(
    db_factory: async_sessionmaker[AsyncSession],
    *,
    stale_minutes: int,
    agora: datetime | None = None,
) -> int:
    """Devolve para `pending` toda linha `processing` cujo `locked_at` é mais

    velho que `stale_minutes` — o worker que a travou morreu sem terminar (ou
    sem terminar de registrar o desfecho). Sem heartbeat: o valor de
    `stale_minutes` é a única confiança de que um envio SMTP nunca leva mais
    que isso.

    Um `UPDATE` isolado, e não um `SELECT ... FOR UPDATE` seguido de `UPDATE`:
    o `UPDATE` já é atômico por linha — duas chamadas concorrentes desta
    função nunca liberam a mesma linha duas vezes, porque a segunda,
    executando depois da primeira ter commitado, não encontra mais nenhuma
    linha `processing` com aquele `locked_at` velho para casar no `WHERE`.
    """
    agora = agora or datetime.now(UTC)
    limite = agora - timedelta(minutes=stale_minutes)
    async with db_factory() as db:
        resultado = await db.execute(
            update(EmailOutbox)
            .where(EmailOutbox.status == "processing", EmailOutbox.locked_at < limite)
            .values(status="pending", locked_by=None, locked_at=None)
        )
        await db.commit()
        return resultado.rowcount or 0


# ══════════════════════════════════════════════════════════════
# 4. Envio — reconstrói o conteúdo a partir de `Notification`, nunca da
#    própria outbox (que não guarda nada disso — ver o modelo)
# ══════════════════════════════════════════════════════════════


async def _carrega_contexto(
    db: AsyncSession, notification_id: uuid.UUID
) -> tuple[Notification, User, Ticket | None] | None:
    """`Notification` + `User` (join, uma consulta) e, quando aplicável, o

    `Ticket` — buscado à parte, só para `ticket_created`, que é o único tipo
    cujo assunto reconstruído precisa do título do chamado (ver
    `_assunto_reconstruido`). Os demais tipos nunca pagam essa segunda
    consulta.
    """
    resultado = await db.execute(
        select(Notification, User)
        .join(User, User.id == Notification.user_id)
        .where(Notification.id == notification_id)
    )
    linha = resultado.first()
    if linha is None:
        return None
    notif, user = linha

    ticket: Ticket | None = None
    if notif.type == NotificationType.ticket_created:
        ticket_id = (notif.data or {}).get("ticket_id")
        if ticket_id:
            ticket = await db.get(Ticket, uuid.UUID(str(ticket_id)))

    return notif, user, ticket


def _assunto_reconstruido(notif: Notification, ticket: Ticket | None) -> str:
    """O assunto que os call sites customizavam via `email_subject=`, antes da

    Fase 3B remover esse parâmetro de `notify`/`notifica_audiencia` — o
    conteúdo do e-mail passou a nascer inteiramente aqui, nunca no momento do
    enqueue.

    `sla_warning` não precisa de caso especial: `sla_alertas.assunto_do_aviso`
    já era, byte a byte, o mesmo que `_assunto_do_email(notif.title,
    notif.data)` produz — `_TITULO` é o `title` passado a `notify`, e
    `ticket.protocol` é o `data["protocol"]`.

    `ticket_created` é o único caso genuinamente especial: o aviso "Novo
    chamado" para a EQUIPE embute o título do chamado (texto do cliente) no
    assunto, e a confirmação "Ticket aberto" para o AUTOR não. As duas usam o
    mesmo `NotificationType`, então a distinção não pode ser o tipo — é se
    quem recebe é quem abriu o chamado. `notif.user_id != ticket.creator_id`
    é exatamente essa pergunta, direto da regra de negócio, e não uma
    comparação de texto contra o título da notificação (frágil a mudança de
    redação).
    """
    if (
        notif.type == NotificationType.ticket_created
        and ticket is not None
        and notif.user_id != ticket.creator_id
    ):
        protocolo = (notif.data or {}).get("protocol") or ticket.protocol
        return f"[HelpHS] Novo chamado {protocolo} — {ticket.title}"
    return _assunto_do_email(notif.title, notif.data)


def _conteudo_do_email(
    notif: Notification, user: User, ticket: Ticket | None, settings: Settings
) -> tuple[str, str, str]:
    """(assunto, corpo em texto, corpo em HTML) — reconstruído inteiramente a

    partir do que já está persistido (`Notification`, `User`, e o `Ticket`
    quando aplicável). Nada disso vem da outbox: ela não guarda conteúdo (ver
    o modelo `EmailOutbox`).
    """
    assunto = _assunto_reconstruido(notif, ticket)
    mensagem = _mensagem_do_email(notif.title, notif.message, notif.data, user.name, settings)
    return assunto, em_texto(mensagem), em_html(mensagem)


async def _persiste_resultado(
    db_factory: async_sessionmaker[AsyncSession],
    outbox_id: uuid.UUID,
    resultado: EmailDeliveryResult,
    *,
    agora: datetime | None = None,
) -> None:
    """Persiste o desfecho da tentativa. No sucesso, também marca

    `Notification.email_sent = True` — NO MESMO COMMIT que marca
    `EmailOutbox.status = sent`: as duas colunas descrevem o mesmo fato
    ("este e-mail foi entregue"), e um commit que movesse só uma delas
    deixaria as duas fontes divergentes até a próxima tentativa (que não
    haveria, porque `sent` não tenta de novo). Em retry ou `dead`,
    `email_sent` simplesmente não é tocado — continua `False`, o valor com
    que `Notification` sempre nasce.

    Linhas de origem Account (Fase 3C) não têm `Notification` — `outbox.
    notification_id` é `None` para elas, e o UPDATE nunca é tentado.
    """
    agora = agora or datetime.now(UTC)
    async with db_factory() as db:
        outbox = await db.get(EmailOutbox, outbox_id)
        if outbox is None:
            return  # defensivo: a linha sumiu entre a reivindicação e aqui

        if resultado.status == EmailDeliveryStatus.success:
            outbox.status = "sent"
            outbox.sent_at = agora
            outbox.last_error = None
            if outbox.notification_id is not None:
                notif = await db.get(Notification, outbox.notification_id)
                if notif is not None:
                    notif.email_sent = True
        else:
            outbox.attempts += 1
            outbox.last_error = resultado.error_summary
            if resultado.status == EmailDeliveryStatus.permanent_failure:
                outbox.status = "dead"
            else:
                novo_status, proxima = proximo_estado_apos_falha(outbox.attempts, agora)
                outbox.status = novo_status
                if proxima is not None:
                    outbox.next_attempt_at = proxima

        outbox.locked_by = None
        outbox.locked_at = None
        await db.commit()


async def _processa_notification(
    db_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    outbox_id: uuid.UUID,
    notification_id: uuid.UUID,
) -> None:
    """A origem Notification (Fase 3A/3B) — inalterada pela Fase 3C."""
    async with db_factory() as db:
        contexto = await _carrega_contexto(db, notification_id)

    if contexto is None:
        # Não deveria acontecer: `notification_id` tem FK com CASCADE, então a
        # notificação some JUNTO com a linha de outbox, nunca sozinha. Mas se
        # acontecer, não há destinatário para reconstruir — retry não ajudaria.
        await _persiste_resultado(
            db_factory,
            outbox_id,
            EmailDeliveryResult(EmailDeliveryStatus.permanent_failure, "NotificationNotFound"),
        )
        return

    notif, user, ticket = contexto
    assunto, texto, html = _conteudo_do_email(notif, user, ticket, settings)
    resultado = await send_email_detalhado(
        user.email,
        assunto,
        texto,
        settings,
        html=html,
        contexto=f"outbox {outbox_id}",
    )
    await _persiste_resultado(db_factory, outbox_id, resultado)


# Motivos seguros para `last_error` quando a linha vai para `dead` sem
# tentativa de SMTP — nunca PII, mesma disciplina de `_resumo_do_erro`.
_CONTA_USUARIO_NAO_ENCONTRADO = "AccountUserNotFound"
_CONTA_USUARIO_ANONIMIZADO = "AccountUserAnonymized"
_CONTA_USUARIO_INATIVO = "AccountUserInactive"
_CONTA_VERIFICACAO_JA_CONCLUIDA = "AccountAlreadyVerified"


async def _processa_conta(
    db_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    outbox_id: uuid.UUID,
    user_id: uuid.UUID,
    event_type: str,
) -> None:
    """A origem Account (Fase 3C) — verification/password_reset/account_exists.

    Elegibilidade checada ANTES de qualquer tentativa de SMTP, na ordem que a
    auditoria da Fase 3C fechou:

    1. usuário sumiu (`ON DELETE CASCADE` já deveria ter levado a linha junto
       — chegar aqui é defensivo) → dead, sem SMTP;
    2. `anonymized` → dead, sem SMTP. Nunca tenta mandar para o endereço
       sintético (`anon_...@anonymized.invalid`) que a anonimização grava —
       checagem explícita de `status`, não confiança em bounce de DNS;
    3. `password_reset` para usuário `inactive` → dead, sem SMTP. Ninguém
       consegue logar mesmo, o link não serviria para nada;
    4. `verification` quando `email_verified` já é `True` (confirmado por
       outro caminho entre o enqueue e o processamento) → dead, sem SMTP —
       mandar a confirmação de novo seria ruído, e o link gerado nem
       validaria (`vrf` do token bateria com o estado atual, mas o endpoint
       de confirmação já responde "já estava confirmado" antes de checar o
       token).

    `verification`/`account_exists` para `inactive` são PERMITIDOS — só
    `password_reset` é bloqueado por status.

    O token, quando o evento tem um, nasce AQUI — nunca antes, nunca
    persistido (ver `app/services/account_tokens.py` e a auditoria da Fase
    3C: a validação compara estado embutido contra o estado ATUAL do usuário,
    não contra um registro de qual foi o último token emitido, então gerar no
    momento do envio é seguro e não precisa de token duplicado no banco).
    """
    async with db_factory() as db:
        user = await db.get(User, user_id)

    if user is None:
        await _persiste_resultado(
            db_factory,
            outbox_id,
            EmailDeliveryResult(
                EmailDeliveryStatus.permanent_failure, _CONTA_USUARIO_NAO_ENCONTRADO
            ),
        )
        return

    if user.status == UserStatus.anonymized:
        await _persiste_resultado(
            db_factory,
            outbox_id,
            EmailDeliveryResult(EmailDeliveryStatus.permanent_failure, _CONTA_USUARIO_ANONIMIZADO),
        )
        return

    if event_type == "password_reset" and user.status == UserStatus.inactive:
        await _persiste_resultado(
            db_factory,
            outbox_id,
            EmailDeliveryResult(EmailDeliveryStatus.permanent_failure, _CONTA_USUARIO_INATIVO),
        )
        return

    if event_type == "verification" and user.email_verified:
        await _persiste_resultado(
            db_factory,
            outbox_id,
            EmailDeliveryResult(
                EmailDeliveryStatus.permanent_failure, _CONTA_VERIFICACAO_JA_CONCLUIDA
            ),
        )
        return

    token: str | None = None
    if event_type == "verification":
        token = account_tokens.create_email_verification_token(
            user.id, user.email_verified, settings
        )
    elif event_type == "password_reset":
        token = account_tokens.create_password_reset_token(user.id, user.password, settings)
    # account_exists: sem token.

    assunto, texto, html = account_emails.conteudo_da_conta(
        event_type, name=user.name, token=token, settings=settings
    )
    resultado = await send_email_detalhado(
        user.email,
        assunto,
        texto,
        settings,
        html=html,
        contexto=f"outbox {outbox_id}",
    )
    await _persiste_resultado(db_factory, outbox_id, resultado)


async def _processa_um(
    db_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    outbox_id: uuid.UUID,
) -> None:
    async with db_factory() as db:
        outbox = await db.get(EmailOutbox, outbox_id)
        if outbox is None or outbox.status != "processing":
            return  # já tratada por outro caminho; defensivo
        notification_id = outbox.notification_id
        user_id = outbox.user_id
        event_type = outbox.event_type

    if notification_id is not None:
        await _processa_notification(db_factory, settings, outbox_id, notification_id)
    else:
        assert user_id is not None and event_type is not None  # garantido pela CHECK do banco
        await _processa_conta(db_factory, settings, outbox_id, user_id, event_type)


async def processa_lote(
    db_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    worker_id: str,
    agora: datetime | None = None,
) -> int:
    """Uma rodada completa: recupera travadas, reivindica um lote, processa

    cada item. Devolve quantos itens foram reivindicados nesta rodada.
    """
    agora = agora or datetime.now(UTC)
    await recupera_travados(
        db_factory, stale_minutes=settings.email_outbox_stale_processing_minutes, agora=agora
    )
    ids = await reivindica_lote(
        db_factory, limite=settings.email_outbox_batch_size, worker_id=worker_id, agora=agora
    )
    for outbox_id in ids:
        await _processa_um(db_factory, settings, outbox_id)
    return len(ids)


# ══════════════════════════════════════════════════════════════
# 5. Observabilidade — contagens por estado, sem PII (base para a Fase 3D)
# ══════════════════════════════════════════════════════════════


async def contadores_por_status(db_factory: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    """`{"pending": N, "processing": N, "sent": N, "dead": N}` — só contagens

    e nomes de estado, nada que identifique um destinatário ou um evento.
    Existe para a Fase 3D montar o bloco `email_outbox` do `/api/v1/health`
    (mesmo formato de `auto_close`/`sla_warning`); não é chamada em nenhum
    endpoint nesta fase.
    """
    contagens = {"pending": 0, "processing": 0, "sent": 0, "dead": 0}
    async with db_factory() as db:
        resultado = await db.execute(
            select(EmailOutbox.status, func.count()).group_by(EmailOutbox.status)
        )
        for status, total in resultado.all():
            contagens[status] = total
    return contagens


# ══════════════════════════════════════════════════════════════
# 6. O laço
# ══════════════════════════════════════════════════════════════

_ultima_rodada_sem_erro: datetime | None = None


def ultima_rodada_sem_erro() -> datetime | None:
    """Mesma semântica de `ticket_lifecycle.ultima_rodada_sem_erro` e

    `sla_alertas.ultima_rodada_sem_erro`: quando ESTE processo concluiu uma
    rodada sem levantar, não se a fila está em dia. `None` até a primeira
    rodada concluir.
    """
    return _ultima_rodada_sem_erro


async def _run_once(worker_id: str) -> None:
    global _ultima_rodada_sem_erro

    from app.core.database import AsyncSessionLocal

    settings = get_settings()
    try:
        await processa_lote(AsyncSessionLocal, settings, worker_id=worker_id)
        _ultima_rodada_sem_erro = datetime.now(UTC)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Falha na rodada da outbox de e-mail: {exc}")


async def email_outbox_loop() -> None:
    settings = get_settings()
    intervalo = settings.email_outbox_interval_seconds
    worker_id = f"outbox-{os.getpid()}"

    # Um respiro depois do boot, como nos outros dois workers: migrations e
    # seeds ainda podem estar rodando.
    await asyncio.sleep(min(30, intervalo))

    while True:
        try:
            await _run_once(worker_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Laço da outbox de e-mail levantou; o laço segue: {exc}")

        await asyncio.sleep(intervalo)


def start_email_outbox_worker() -> asyncio.Task | None:
    """Sobe o laço em background. Devolve `None` quando a rotina está desligada."""
    settings = get_settings()
    if settings.email_outbox_interval_seconds <= 0:
        logger.info("Outbox de e-mail desligada (intervalo = 0)")
        return None

    logger.info(
        f"Outbox de e-mail ativa: verificando a cada {settings.email_outbox_interval_seconds}s"
    )
    return asyncio.create_task(email_outbox_loop(), name="email-outbox")
