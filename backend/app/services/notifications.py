"""
Notification service — in-app + email.

Uso
---
Chame ``notify()`` dentro do handler **antes** do commit, e termine com
``commit_e_notificar(db)`` no lugar de ``db.commit()``::

    await notify(db, user_id, NotificationType.ticket_updated, "Ticket atualizado",
                 "Seu chamado HS-2026-0001 foi atualizado.", data={"ticket_id": str(tid)},
                 settings=settings)
    await commit_e_notificar(db)

``notify()`` NÃO envia nada. Ele adiciona a linha de notificação à sessão — ela
faz parte da transação, e é por isso que continua antes do commit — e registra
o e-mail como **pendência daquela sessão**. Quem dispara é o
``commit_e_notificar``, depois de o commit voltar.

Por que o registro é chaveado por sessão
----------------------------------------
Antes, o ``notify()`` criava a task de envio na hora. Qualquer commit que
falhasse depois mandava e-mail sobre um fato que não passou a existir — o caso
visível era o laço de protocolo do ``create_ticket``, que mandava um e-mail por
tentativa descartada, cada um anunciando um protocolo que não existe.

Duas alternativas foram descartadas por motivo prático, não por gosto:

* **BackgroundTasks do FastAPI.** Só existe onde existe request, e o
  ``ticket_lifecycle`` notifica de dentro do laço de fechamento automático, sem
  request nenhum. Precisaria de um segundo mecanismo para esse caminho — e o
  ``_auto_transition``, que notifica e é chamado de outro handler, teria de
  carregar o parâmetro por toda a cadeia.
* **Listener de ``after_commit`` do SQLAlchemy.** Seria automático e invisível,
  mas a suíte mocka o banco em TODOS os testes (``session = AsyncMock()``):
  o evento nunca dispararia, e o mecanismo inteiro ficaria fora do alcance dos
  testes. Mecanismo que a suíte não enxerga não entra.

O registro vive num ``WeakKeyDictionary`` chaveado pela sessão: funciona com a
sessão real e com a mockada, isola requisições simultâneas, e some sozinho se a
sessão morrer sem commit — handler que levanta no meio não deixa e-mail para
trás.

A pendência é **retirada antes** do commit. É isso que resolve o laço de
retentativa de graça: se o commit levanta, a pendência daquela tentativa já saiu
do registro e não sobra para a próxima. Nenhum ``rollback`` precisa saber que
notificações existem.

O que se perde de propósito: se alguém chamar ``db.commit()`` direto depois de
um ``notify()``, o e-mail não sai. É o lado seguro do erro — deixar de mandar
um aviso é recuperável, mandar aviso de algo que não aconteceu não é.

Falha de envio é registrada e ignorada — nunca desfaz a transação.
"""

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any
from weakref import WeakKeyDictionary

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.models import Notification, NotificationType, User, UserRole
from app.services.email import send_email

# Tipos que ficam SÓ no sininho, mesmo com SMTP configurado.
#
# A pesquisa de satisfação é respondida dentro do chamado, no painel abaixo do
# chat — o e-mail não levava a lugar nenhum, só pedia que a pessoa entrasse no
# sistema. Decidido com o cliente em 07/08/2026: convite apenas in-app.
_IN_APP_ONLY = frozenset({NotificationType.satisfaction_survey})

# Papéis que NÃO recebem notificação por e-mail — só pelo sininho.
#
# Decidido em 04/09/2026, a pedido da equipe: quem passa o dia dentro do
# sistema já é avisado pelo sininho, e o e-mail virava ruído.
#
# O que de fato chegava a staff eram DOIS eventos: `ticket_assigned`
# (routers/tickets.py:1029, ao ser designado) e `ticket_updated` na reabertura
# (routers/tickets.py:940, ao responsável).
#
# As outras notificações que apontam para staff — as duas do chat e a "Triagem
# concluída", que percorre TODOS os técnicos e admins ativos — nunca viraram
# e-mail, mas por acidente: elas não passam `settings` ao notify, e sem isso a
# função retorna antes de registrar envio. Este filtro por papel também fecha
# essa armadilha: hoje staff não recebe POR DESENHO, e não porque alguém
# esqueceu um argumento que um dia pode ser "consertado".
#
# O CLIENTE continua recebendo tudo o que recebia. Ele é justamente quem NÃO
# vive aqui dentro: para ele o e-mail é como fica sabendo que o chamado andou,
# e o aviso de encerramento é o que dispara o prazo de reabertura.
#
# Isto não toca os e-mails de conta — confirmação de cadastro e redefinição de
# senha saem por `services/account_emails.py`, que não passa por aqui.
_SEM_EMAIL_POR_PAPEL = frozenset({UserRole.admin, UserRole.technician})


@dataclass(frozen=True)
class _EmailPendente:
    """Tudo que o envio precisa, capturado no notify() e independente da sessão."""

    notif_id: uuid.UUID
    to_email: str
    subject: str
    body: str
    settings: Settings


# E-mails registrados por sessão, aguardando o commit que os torna verdade.
_PENDENTES: WeakKeyDictionary = WeakKeyDictionary()

# O asyncio só guarda referência fraca para a task em voo: sem isto, o coletor
# pode levar o envio no meio do caminho.
_EM_VOO: set[asyncio.Task] = set()


def _assunto_do_email(title: str, data: dict[str, Any] | None) -> str:
    """`[HelpHS] Chamado resolvido · HS-2026-0042`.

    O assunto era o título cru da notificação, e na lista da caixa isso é
    ilegível: cinco chamados abertos rendiam cinco "Ticket resolvido" idênticos,
    sem dizer qual. O protocolo entra quando existe — cinco das catorze chamadas
    não o carregam no `data`, e para elas o prefixo sozinho já é melhor do que
    nada.

    Não mexe no `title`: o sininho continua mostrando o texto cru.
    """
    protocolo = (data or {}).get("protocol")
    return f"[HelpHS] {title} · {protocolo}" if protocolo else f"[HelpHS] {title}"


def _corpo_do_email(message: str, data: dict[str, Any] | None, settings: Settings) -> str:
    """A mensagem, e o caminho de volta para o chamado.

    Levantado em 04/09/2026: DOZE dos catorze e-mails de notificação chegavam
    sem link. O `ticket_id` sempre esteve no `data` — as catorze chamadas o
    passam — e simplesmente não era usado. Avisar que o chamado andou sem dizer
    onde ele está obriga a pessoa a entrar no sistema e procurar.

    Sem `ticket_id` ou sem `FRONTEND_URL`, devolve a mensagem intacta: link
    inventado é pior que link ausente.
    """
    ticket_id = (data or {}).get("ticket_id")
    if not ticket_id or not settings.frontend_url:
        return message

    base = settings.frontend_url.rstrip("/")
    return f"{message}\n\nVeja o chamado:\n{base}/tickets/{ticket_id}"


async def notify(
    db: AsyncSession,
    user_id: uuid.UUID,
    notif_type: NotificationType,
    title: str,
    message: str,
    data: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> None:
    """
    Cria a notificação in-app e REGISTRA o e-mail como pendência da sessão.

    Não commita e não envia nada: o commit é do chamador, para que a
    notificação seja atômica com a operação que a provocou, e o envio só
    acontece no ``commit_e_notificar``.
    """
    notif = Notification(
        id=uuid.uuid4(),
        user_id=user_id,
        type=notif_type,
        title=title,
        message=message,
        data=data,
        read=False,
        email_sent=False,
    )
    db.add(notif)

    if settings is None or notif_type in _IN_APP_ONLY:
        return  # no email without settings

    # A busca traz o PAPEL junto do e-mail: desde 04/09/2026 quem decide o
    # envio não é só o tipo da notificação, é também quem recebe. Uma consulta
    # só — a coluna a mais não custa nada e evita uma segunda ida ao banco.
    result = await db.execute(select(User.email, User.role).where(User.id == user_id))
    destinatario = result.one_or_none()

    # Destinatário que sumiu entre a ação e a notificação não pode virar
    # exceção: quem chamou já fez o trabalho, e o e-mail é o acessório.
    if destinatario is None:
        return

    email_addr, papel = destinatario

    if email_addr and papel not in _SEM_EMAIL_POR_PAPEL:
        _PENDENTES.setdefault(db, []).append(
            _EmailPendente(
                notif_id=notif.id,
                to_email=email_addr,
                subject=_assunto_do_email(title, data),
                body=_corpo_do_email(message, data, settings),
                settings=settings,
            )
        )


async def commit_e_notificar(db: AsyncSession) -> None:
    """
    Commita e, só se o commit voltar, dispara os e-mails registrados na sessão.

    As pendências saem do registro ANTES do commit: se ele levantar, elas já não
    existem e a tentativa seguinte começa limpa.
    """
    pendentes = _PENDENTES.pop(db, [])
    await db.commit()

    for pendente in pendentes:
        _disparar(pendente)


def _disparar(pendente: _EmailPendente) -> None:
    """Envio best-effort: falha aqui não pode afetar quem já commitou."""
    tarefa = asyncio.create_task(
        _send_and_log(pendente),
        name=f"email-notif-{pendente.notif_id}",
    )
    _EM_VOO.add(tarefa)
    tarefa.add_done_callback(_EM_VOO.discard)


async def _send_and_log(pendente: _EmailPendente) -> None:
    sent = await send_email(pendente.to_email, pendente.subject, pendente.body, pendente.settings)
    if sent:
        logger.debug(f"Email notification {pendente.notif_id} delivered to {pendente.to_email}")
    else:
        logger.warning(
            f"Email notification {pendente.notif_id} NOT delivered to {pendente.to_email}"
        )
