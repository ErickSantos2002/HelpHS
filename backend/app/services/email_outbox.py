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

Fase 3D — observabilidade e retenção
-------------------------------------
Três coisas novas, nenhuma delas mexendo em schema, retry, backoff, SMTP,
templates ou na semântica de `Notification`:

1. **Snapshot em memória.** O WORKER mede a fila uma vez por rodada e guarda o
   resultado aqui; o `/api/v1/health` só LÊ memória. Se o endpoint consultasse
   a tabela, cada probe pagaria um `GROUP BY` — e a resolução ganha com isso
   seria menor que o próprio ciclo do worker. Por isso o snapshot carrega um
   `as_of` obrigatório: contagem em cache ao lado de um heartbeat parado é
   interpretável, sem o `as_of` alguém lê contagem velha como atual.

2. **Dois heartbeats, de propósito.** `_ultima_rodada_iniciada` é carimbado no
   INÍCIO da rodada e `_ultima_rodada_sem_erro` só quando o NÚCLEO (recuperar
   travadas → reivindicar → processar) termina sem levantar. Limpeza e coleta
   de métricas rodam DEPOIS, cada uma com o seu próprio `except`: uma falha
   nelas não pode transformar uma rodada de envio bem-sucedida em falha do
   worker.

3. **Retenção.** `sent` e `dead` expiram; `pending` e `processing` NUNCA —
   apagar um deles por retenção seria descartar e-mail em silêncio. A limpeza
   roda dentro deste mesmo laço (não há worker novo: é o precedente da
   "Arrumação" de `helo_indexacao.varre`), em lotes, com
   `FOR UPDATE SKIP LOCKED` na subconsulta. Dois processos limpando ao mesmo
   tempo pegam lotes DISJUNTOS — sem Redis e sem advisory lock, pela mesma
   razão arquitetural da seção acima.

Dívida técnica conhecida e deliberadamente NÃO tocada aqui (achado A3 da
auditoria da Fase 3D): `recupera_travados` devolve a linha para `pending` sem
incrementar `attempts` nem reagendar `next_attempt_at`. É a única transição
que não avança a máquina de estado, e uma mensagem que trave repetidamente
pode circular para sempre sem alcançar `MAX_ATTEMPTS`. A Fase 3D a torna
OBSERVÁVEL (`oldest_processing_seconds` no health) de propósito, sem
consertá-la: mudança de máquina de estado não entra na mesma frente que
observabilidade. Frente própria, imediatamente depois desta.
"""

import asyncio
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import InstrumentedAttribute

from app.core.config import Settings, get_settings
from app.models.models import EmailOutbox, Notification, NotificationType, Ticket, User, UserStatus
from app.services import account_emails, account_tokens
from app.services.email import (
    EmailDeliveryResult,
    EmailDeliveryStatus,
    _resumo_do_erro,
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

            # Fase 3D (achado A1): a transição para `dead` deixou de ser
            # silenciosa. Dentro do `else` de propósito — só o caminho de FALHA
            # pode produzir `dead`, e assim um `sent` nunca paga a consulta.
            # Ver `classifica_dead`/`_loga_dead` na seção 4.1.
            if outbox.status == "dead":
                await _loga_dead(db, outbox, resultado.error_summary)

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
            EmailDeliveryResult(EmailDeliveryStatus.permanent_failure, _NOTIFICACAO_NAO_ENCONTRADA),
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
# Mesma família, na origem Notification. Era um literal solto dentro de
# `_processa_notification`; virou constante na Fase 3D porque agora ele também
# é consumido pela classificação de `dead` logo abaixo — e a lista de motivos
# e o produtor dos motivos NÃO podem morar em dois lugares (foi exatamente
# esse o buraco que a auditoria apontou em classificar `dead` por texto).
_NOTIFICACAO_NAO_ENCONTRADA = "NotificationNotFound"


# ══════════════════════════════════════════════════════════════
# 4.1 Classificação de `dead` (Fase 3D) — em memória, nunca persistida
# ══════════════════════════════════════════════════════════════
#
# Até a Fase 3D uma linha virava `dead` em SILÊNCIO: `_persiste_resultado`
# mudava o estado e commitava, sem uma linha de log. O e-mail definitivamente
# não entregue era o evento mais importante do subsistema e só existia como
# estado no banco — achado A1 da auditoria.
#
# Por que a classificação NÃO é persistida
# -----------------------------------------
# Um `failure_code` em coluna seria o desenho certo para MÉTRICA agregada, e
# foi deliberadamente adiado: sem consumidor, não se paga uma migration. O que
# a Fase 3D precisa é separar "terminal de negócio" de "falha real de entrega"
# no LOG, e para isso basta classificar em código, no momento em que o motivo
# ainda está na mão — sem segunda cópia, sem schema novo, sem backfill.
#
# `attempts` já é metade da resposta, de graça: veredito permanente vira `dead`
# na hora (`attempts` baixo), esgotamento vira `dead` com `attempts == 5`. O que
# ele NÃO separa é "usuário anonimizado" de "550 domínio não verificado" — os
# dois são permanentes na primeira tentativa. É essa metade que vem daqui.

_DEAD_NEGOCIO = frozenset(
    {_CONTA_USUARIO_ANONIMIZADO, _CONTA_USUARIO_INATIVO, _CONTA_VERIFICACAO_JA_CONCLUIDA}
)
_DEAD_DEFENSIVO = frozenset({_CONTA_USUARIO_NAO_ENCONTRADO, _NOTIFICACAO_NAO_ENCONTRADA})
_DEAD_CONFIGURACAO = frozenset({"SMTPNotConfigured"})

DEAD_NEGOCIO = "business"
DEAD_DEFENSIVO = "defensive"
DEAD_CONFIGURACAO = "configuration"
DEAD_ENTREGA = "delivery"

# Severidade por classe. Um terminal de negócio NÃO é incidente — o usuário
# anonimizou a conta, ou já confirmou o e-mail por outro caminho; logar isso
# como erro treinaria quem lê o log a ignorar a linha que importa.
_NIVEL_DO_DEAD = {
    DEAD_NEGOCIO: "INFO",
    DEAD_DEFENSIVO: "WARNING",
    DEAD_CONFIGURACAO: "ERROR",
    DEAD_ENTREGA: "ERROR",
}


def classifica_dead(motivo: str | None) -> str:
    """A que família pertence este `dead`. Pura, e o default é o pior caso.

    Motivo desconhecido cai em `delivery` de propósito: é a classe que gera
    `ERROR`. Um motivo novo que alguém esqueça de cadastrar aqui aparece como
    falha de entrega — alto demais, e não baixo demais. O inverso (default
    silencioso) esconderia exatamente o que este log existe para mostrar.
    """
    if motivo in _DEAD_NEGOCIO:
        return DEAD_NEGOCIO
    if motivo in _DEAD_DEFENSIVO:
        return DEAD_DEFENSIVO
    if motivo in _DEAD_CONFIGURACAO:
        return DEAD_CONFIGURACAO
    return DEAD_ENTREGA


async def _loga_dead(db: AsyncSession, outbox: EmailOutbox, motivo: str | None) -> None:
    """Fecha o A1: toda transição nova para `dead` deixa rastro, sem PII.

    O que PODE entrar nesta linha: origem, tipo do evento, número de
    tentativas, classe do `dead` e o motivo seguro (que por construção é uma
    das constantes acima ou a saída de `_resumo_do_erro` — nome de classe mais
    código SMTP numérico).

    O que NUNCA entra: `user_id`, `notification_id`, `ticket_id`, endereço,
    nome, título, assunto, corpo, token. `notification_type` entra porque é um
    valor de enum fechado (`ticket_created`, `chat_message`, …) — diz QUAL
    espécie de aviso está falhando sem apontar pessoa nenhuma.
    """
    if outbox.notification_id is not None:
        origem = "notification"
        notif = await db.get(Notification, outbox.notification_id)
        evento = notif.type.value if notif is not None else "unknown"
    else:
        origem = "account"
        evento = outbox.event_type or "unknown"

    classe = classifica_dead(motivo)
    logger.log(
        _NIVEL_DO_DEAD[classe],
        f"Outbox de e-mail: linha encerrada em dead — origin={origem} "
        f"event={evento} attempts={outbox.attempts} dead_kind={classe} "
        f"reason={motivo}",
    )


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


async def _contagens(db: AsyncSession) -> dict[str, int]:
    """Um `GROUP BY status` na sessão recebida. Só contagens e nomes de estado.

    Separada de `contadores_por_status` para que o snapshot da Fase 3D faça as
    TRÊS medições numa sessão só, em vez de abrir uma por consulta.
    """
    contagens = {"pending": 0, "processing": 0, "sent": 0, "dead": 0}
    resultado = await db.execute(
        select(EmailOutbox.status, func.count()).group_by(EmailOutbox.status)
    )
    for status, total in resultado.all():
        contagens[status] = total
    return contagens


async def contadores_por_status(db_factory: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    """`{"pending": N, "processing": N, "sent": N, "dead": N}` — só contagens

    e nomes de estado, nada que identifique um destinatário ou um evento.
    Desde a Fase 3D o corpo real é `_contagens`; esta função segue existindo
    com o mesmo contrato (abre a própria sessão) porque é o que os testes da
    Fase 3A exercitam.
    """
    async with db_factory() as db:
        return await _contagens(db)


@dataclass(frozen=True)
class SnapshotDaFila:
    """O que o worker mediu da fila, e QUANDO mediu.

    `as_of` não é enfeite: este objeto vive em memória entre rodadas e é o que
    o `/api/v1/health` devolve. Sem o carimbo, quem lê não tem como distinguir
    "a fila está vazia" de "o worker parou de medir há duas horas".

    As duas idades são `None` quando não há linha no estado correspondente —
    `None` significa "não há nada velho", nunca "não mediu".
    """

    as_of: datetime
    pending: int
    processing: int
    sent: int
    dead: int
    oldest_overdue_seconds: float | None
    oldest_processing_seconds: float | None


async def coleta_snapshot(
    db_factory: async_sessionmaker[AsyncSession], *, agora: datetime | None = None
) -> SnapshotDaFila:
    """Mede a fila inteira numa sessão só. Chamada pelo WORKER, nunca pelo
    endpoint de health — ver a seção "Fase 3D" no topo do módulo.

    `oldest_overdue_seconds` sai de `status='pending' AND next_attempt_at <=
    agora`, e o `AND` é a parte que importa: uma linha no meio da escada de
    backoff está `pending` e está EM DIA (`next_attempt_at` no futuro).
    Medir idade desde `created_at` confundiria "o worker parou" com "esta
    linha está cumprindo os 60 minutos dela". O predicado é também, letra por
    letra, o do índice parcial `ix_email_outbox_pending_next_attempt`, que já
    existe desde a Fase 3A — nenhum índice novo é necessário.

    `oldest_processing_seconds` mede `locked_at` do `processing` mais antigo. É
    o que torna a recuperação de linha travada observável, e com ela o achado
    A3: uma linha que o worker reivindica e devolve a cada `stale_minutes`, sem
    nunca avançar `attempts`, aparece aqui como idade que não baixa.
    """
    agora = agora or datetime.now(UTC)
    async with db_factory() as db:
        contagens = await _contagens(db)

        mais_velho_vencido = (
            await db.execute(
                select(func.min(EmailOutbox.next_attempt_at)).where(
                    EmailOutbox.status == "pending",
                    EmailOutbox.next_attempt_at <= agora,
                )
            )
        ).scalar_one_or_none()

        mais_velho_processando = (
            await db.execute(
                select(func.min(EmailOutbox.locked_at)).where(EmailOutbox.status == "processing")
            )
        ).scalar_one_or_none()

    return SnapshotDaFila(
        as_of=agora,
        pending=contagens["pending"],
        processing=contagens["processing"],
        sent=contagens["sent"],
        dead=contagens["dead"],
        oldest_overdue_seconds=(
            (agora - mais_velho_vencido).total_seconds() if mais_velho_vencido else None
        ),
        oldest_processing_seconds=(
            (agora - mais_velho_processando).total_seconds() if mais_velho_processando else None
        ),
    )


# ══════════════════════════════════════════════════════════════
# 5.1 Retenção (Fase 3D) — `sent` e `dead` expiram, fila viva nunca
# ══════════════════════════════════════════════════════════════

# Constante, não configuração: ninguém ajusta tamanho de lote de limpeza por
# ambiente. Mesmo critério (e mesmo precedente) do `_READINESS_TIMEOUT_S` do
# `main.py`. 100 seria pouco — com limpeza de hora em hora, drenar um acúmulo
# levaria dias; 1000 prenderia mais linhas por transação sem ganho real.
_LOTE_DA_LIMPEZA = 500


async def _apaga_lote(
    db: AsyncSession,
    *,
    status: str,
    coluna: InstrumentedAttribute[Any],
    cutoff: datetime,
) -> int:
    """Um lote de no máximo `_LOTE_DA_LIMPEZA` linhas, e nunca a tabela inteira.

    `FOR UPDATE SKIP LOCKED` dentro da subconsulta é o que faz dois processos
    limpando ao mesmo tempo pegarem lotes DISJUNTOS: o segundo pula o que o
    primeiro travou. Não é só eficiência — é o que dispensa lock de qualquer
    espécie, Redis ou advisory, mantendo o PostgreSQL como única fonte de
    verdade (ver o topo do módulo). Um advisory lock funcionaria; ele serializa
    onde a disjunção já resolve, e por isso foi descartado por desnecessário.
    """
    ids = (
        select(EmailOutbox.id)
        .where(EmailOutbox.status == status, coluna < cutoff)
        .order_by(coluna)
        .limit(_LOTE_DA_LIMPEZA)
        .with_for_update(skip_locked=True)
    )
    resultado = await db.execute(delete(EmailOutbox).where(EmailOutbox.id.in_(ids)))
    return resultado.rowcount or 0


async def limpa_expirados(
    db_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    agora: datetime | None = None,
) -> dict[str, int]:
    """Apaga `sent` e `dead` vencidos. `pending` e `processing`, NUNCA.

    Duas razões independentes impedem a limpeza de tocar fila viva, e é de
    propósito que sejam duas: o filtro de `status`, e o fato de `sent_at` ser
    `NULL` numa linha que nunca foi enviada (`NULL < cutoff` é `NULL`, nunca
    verdadeiro). Apagar um `pending` por retenção seria descartar e-mail em
    silêncio — o pior modo de falha possível para esta tabela.

    `dead` corta por `created_at`, não por `sent_at`: linha que morreu nunca
    teve `sent_at` preenchido.
    """
    agora = agora or datetime.now(UTC)
    corte_sent = agora - timedelta(days=settings.email_outbox_sent_retention_days)
    corte_dead = agora - timedelta(days=settings.email_outbox_dead_retention_days)

    async with db_factory() as db:
        apagados = {
            "sent": await _apaga_lote(
                db, status="sent", coluna=EmailOutbox.sent_at, cutoff=corte_sent
            ),
            "dead": await _apaga_lote(
                db, status="dead", coluna=EmailOutbox.created_at, cutoff=corte_dead
            ),
        }
        await db.commit()
    return apagados


# ══════════════════════════════════════════════════════════════
# 6. O laço
# ══════════════════════════════════════════════════════════════

# Três carimbos e um snapshot, todos na memória DESTE processo — mesma
# semântica declarada em `ticket_lifecycle`: com mais de um worker cada um tem
# os seus, e o /api/v1/health responde pelo worker que atendeu a requisição.
_inicio_do_worker: datetime | None = None
_ultima_rodada_iniciada: datetime | None = None
_ultima_rodada_sem_erro: datetime | None = None
_ultima_limpeza: datetime | None = None
_snapshot: SnapshotDaFila | None = None


def ultima_rodada_sem_erro() -> datetime | None:
    """Mesma semântica de `ticket_lifecycle.ultima_rodada_sem_erro` e

    `sla_alertas.ultima_rodada_sem_erro`: quando ESTE processo concluiu uma
    rodada sem levantar, não se a fila está em dia. `None` até a primeira
    rodada concluir.

    Desde a Fase 3D o "sem levantar" é explicitamente o do NÚCLEO — recuperar
    travadas, reivindicar, processar. Limpeza e coleta de métricas rodam depois
    e não podem transformar uma rodada de envio bem-sucedida em falha.
    """
    return _ultima_rodada_sem_erro


def ultima_rodada_iniciada() -> datetime | None:
    """Quando a rodada mais recente COMEÇOU, carimbado antes de qualquer SMTP.

    Existe separado de `ultima_rodada_sem_erro` porque os dois têm tetos
    diferentes: uma rodada cheia e lenta deixa `last_success` legitimamente
    velho, enquanto este carimbo é limitado pelo intervalo do laço. Um limiar
    único sobre o carimbo de sucesso ou mentiria (frouxo) ou daria falso alarme
    (apertado).
    """
    return _ultima_rodada_iniciada


def snapshot_da_fila() -> SnapshotDaFila | None:
    """O que a última rodada mediu. `None` até a primeira medição."""
    return _snapshot


def reinicia_estado_para_testes() -> None:
    """Zera os carimbos e o snapshot. Só para teste — estado de módulo vaza
    entre casos, e um health que herda o carimbo do teste anterior passa
    verde por acidente."""
    global _inicio_do_worker, _ultima_rodada_iniciada, _ultima_rodada_sem_erro
    global _ultima_limpeza, _snapshot
    _inicio_do_worker = None
    _ultima_rodada_iniciada = None
    _ultima_rodada_sem_erro = None
    _ultima_limpeza = None
    _snapshot = None


# ── Estado OK/degraded/error ──────────────────────────────────

ESTADO_DESLIGADO = "disabled"
ESTADO_INICIANDO = "starting"
ESTADO_OK = "ok"
ESTADO_DEGRADADO = "degraded"
ESTADO_ERRO = "error"

# Ordem de gravidade, para "o pior entre vários sinais".
_GRAVIDADE = {ESTADO_OK: 0, ESTADO_DEGRADADO: 1, ESTADO_ERRO: 2}


def _degrau(idade: float | None, limite_degradado: float, limite_erro: float) -> str:
    """`>` estrito nos dois limiares: exatamente NO limite ainda é o estado de
    baixo. Idade `None` é `ok` — não há nada velho para reclamar."""
    if idade is None:
        return ESTADO_OK
    if idade > limite_erro:
        return ESTADO_ERRO
    if idade > limite_degradado:
        return ESTADO_DEGRADADO
    return ESTADO_OK


def _idade(momento: datetime | None, agora: datetime) -> float | None:
    return None if momento is None else (agora - momento).total_seconds()


def classifica_estado(
    *,
    habilitado: bool,
    inicio: datetime | None,
    last_run: datetime | None,
    last_success: datetime | None,
    snapshot: SnapshotDaFila | None,
    intervalo_segundos: int,
    stale_processing_minutes: int,
    agora: datetime,
) -> str:
    """Pura, e inteiramente DERIVADA das configurações que já existem.

    Nenhum limiar é número solto: todos saem de `intervalo_segundos` e de
    `stale_processing_minutes`. Um limiar configurável à parte poderia sair de
    sincronia com o intervalo e passar a mentir; uma derivação não pode.

        last_run / last_success : degraded > 4 × intervalo · error > 20 × intervalo
        oldest_overdue          : degraded > 2 × intervalo · error > stale
        oldest_processing       : degraded > stale         · error > 3 × stale

    `pending > 0` e `dead > 0`, sozinhos, NUNCA degradam — pending é o estado
    normal entre o enqueue e a rodada seguinte, e `dead` nesta fase é
    informativo: sem classificação persistida, o health não tem como separar
    com robustez um `AccountAlreadyVerified` de uma falha real de entrega, e um
    número que mistura os dois viraria alarme que se aprende a ignorar. A
    distinção existe, com severidade, no LOG (ver `classifica_dead`).
    """
    if not habilitado:
        return ESTADO_DESLIGADO

    degradado_s = 4 * intervalo_segundos
    erro_s = 20 * intervalo_segundos
    stale_s = stale_processing_minutes * 60

    # Antes da primeira rodada não se afirma saúde: o laço espera
    # `min(30, intervalo)` antes de começar. `starting` dura enquanto a espera
    # é plausível; passado o limiar de degradação sem NENHUMA rodada, o laço
    # não subiu, e isso é um problema de verdade — não um boot em andamento.
    if last_run is None:
        idade_do_boot = _idade(inicio, agora)
        if idade_do_boot is None or idade_do_boot <= degradado_s:
            return ESTADO_INICIANDO
        return _degrau(idade_do_boot, degradado_s, erro_s)

    # Sem sucesso nenhum ainda, a idade que vale é a do processo: `last_run`
    # é atualizado a cada rodada e ficaria sempre novo, escondendo um worker
    # que levanta em TODA rodada desde o boot.
    referencia_do_sucesso = last_success if last_success is not None else inicio

    sinais = [
        _degrau(_idade(last_run, agora), degradado_s, erro_s),
        _degrau(_idade(referencia_do_sucesso, agora), degradado_s, erro_s),
    ]

    if snapshot is not None:
        sinais.append(_degrau(snapshot.oldest_overdue_seconds, 2 * intervalo_segundos, stale_s))
        sinais.append(_degrau(snapshot.oldest_processing_seconds, stale_s, 3 * stale_s))

    return max(sinais, key=lambda e: _GRAVIDADE[e])


def bloco_de_health(settings: Settings, *, agora: datetime | None = None) -> dict:
    """O bloco `email_outbox` do `/api/v1/health`. Lê MEMÓRIA, não o banco.

    Mesmo formato dos vizinhos (`auto_close`, `sla_warning`): um objeto
    chaveado pelo nome da rotina. Todas as chaves existem sempre, com `None`
    onde nada foi medido — `0` ali seria afirmar uma contagem que não houve.

    `sent` fica fora de propósito: é total cumulativo, cresce para sempre,
    ninguém alerta nele, e a retenção o torna um número sem significado.
    """
    agora = agora or datetime.now(UTC)
    habilitado = settings.email_outbox_interval_seconds > 0
    snap = _snapshot

    estado = classifica_estado(
        habilitado=habilitado,
        inicio=_inicio_do_worker,
        last_run=_ultima_rodada_iniciada,
        last_success=_ultima_rodada_sem_erro,
        snapshot=snap,
        intervalo_segundos=settings.email_outbox_interval_seconds,
        stale_processing_minutes=settings.email_outbox_stale_processing_minutes,
        agora=agora,
    )

    return {
        "enabled": habilitado,
        "state": estado,
        "last_run": _ultima_rodada_iniciada.isoformat() if _ultima_rodada_iniciada else None,
        "last_success": (_ultima_rodada_sem_erro.isoformat() if _ultima_rodada_sem_erro else None),
        "as_of": snap.as_of.isoformat() if snap else None,
        "pending": snap.pending if snap else None,
        "processing": snap.processing if snap else None,
        "dead": snap.dead if snap else None,
        "oldest_overdue_seconds": snap.oldest_overdue_seconds if snap else None,
        "oldest_processing_seconds": snap.oldest_processing_seconds if snap else None,
    }


# ── A rodada ──────────────────────────────────────────────────


def _deve_limpar(settings: Settings, agora: datetime) -> bool:
    """Carimbo de tempo, não contador de rodadas: um contador passaria a
    significar outro intervalo no instante em que alguém mudasse
    `EMAIL_OUTBOX_INTERVAL_SECONDS`."""
    if settings.email_outbox_cleanup_interval_seconds <= 0:
        return False
    if _ultima_limpeza is None:
        return True
    return (
        agora - _ultima_limpeza
    ).total_seconds() >= settings.email_outbox_cleanup_interval_seconds


async def _limpeza_protegida(
    db_factory: async_sessionmaker[AsyncSession], settings: Settings, agora: datetime
) -> None:
    """`except` PRÓPRIO, e é o ponto todo: uma limpeza que falhe não pode
    impedir o carimbo de `last_success` do núcleo — isso inventaria um alarme
    de worker parado a partir de um problema que não encostou no envio.

    O carimbo é da TENTATIVA, gravado antes do trabalho: assim uma falha
    recorrente espera o intervalo inteiro em vez de tentar a cada 30 s e
    encher o log.
    """
    global _ultima_limpeza
    if not _deve_limpar(settings, agora):
        return

    _ultima_limpeza = agora
    try:
        apagados = await limpa_expirados(db_factory, settings, agora=agora)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Outbox de e-mail: limpeza falhou; o envio segue: {_resumo_do_erro(exc)}")
        return

    if apagados["sent"] or apagados["dead"]:
        logger.info(
            f"Outbox de e-mail: limpeza apagou sent={apagados['sent']} " f"dead={apagados['dead']}"
        )


async def _snapshot_protegido(
    db_factory: async_sessionmaker[AsyncSession], agora: datetime
) -> None:
    """Mesmo contrato da limpeza: falhar aqui não é falhar a rodada de envio.
    O snapshot anterior fica de pé, com o `as_of` velho dizendo a verdade."""
    global _snapshot
    try:
        _snapshot = await coleta_snapshot(db_factory, agora=agora)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Outbox de e-mail: coleta de métricas falhou: {_resumo_do_erro(exc)}")


async def _run_once(worker_id: str) -> None:
    global _ultima_rodada_iniciada, _ultima_rodada_sem_erro

    from app.core.database import AsyncSessionLocal

    settings = get_settings()
    agora = datetime.now(UTC)
    _ultima_rodada_iniciada = agora

    try:
        await processa_lote(AsyncSessionLocal, settings, worker_id=worker_id)
        _ultima_rodada_sem_erro = datetime.now(UTC)
    except Exception as exc:  # noqa: BLE001
        # `_resumo_do_erro`, nunca `{exc}` (achado A2): o `str()` de um
        # `DBAPIError` do SQLAlchemy carrega o SQL e os `[parameters: ...]`, e
        # era por aqui que conteúdo de biblioteca de terceiro podia chegar ao
        # log sem ninguém ter escrito um campo sensível em lugar nenhum.
        logger.error(f"Falha na rodada da outbox de e-mail: {_resumo_do_erro(exc)}")

    # Depois do núcleo, e cada um com o seu próprio `except`.
    await _limpeza_protegida(AsyncSessionLocal, settings, agora)
    await _snapshot_protegido(AsyncSessionLocal, agora)


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
            # Mesma disciplina do `except` de dentro — ver o A2 ali.
            logger.error(f"Laço da outbox de e-mail levantou; o laço segue: {_resumo_do_erro(exc)}")

        await asyncio.sleep(intervalo)


def start_email_outbox_worker() -> asyncio.Task | None:
    """Sobe o laço em background. Devolve `None` quando a rotina está desligada."""
    global _inicio_do_worker

    settings = get_settings()
    if settings.email_outbox_interval_seconds <= 0:
        logger.info("Outbox de e-mail desligada (intervalo = 0)")
        return None

    # Carimbado aqui, e não dentro do laço: é a referência de "há quanto tempo
    # este processo deveria estar girando", que é o que separa `starting`
    # legítimo de um laço que nunca chegou a rodar.
    _inicio_do_worker = datetime.now(UTC)

    logger.info(
        f"Outbox de e-mail ativa: verificando a cada {settings.email_outbox_interval_seconds}s"
    )
    return asyncio.create_task(email_outbox_loop(), name="email-outbox")
