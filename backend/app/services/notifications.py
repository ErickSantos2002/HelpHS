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
from app.models.models import Notification, NotificationType, User
from app.services.email import send_email

# Tipos que ficam SÓ no sininho, mesmo com SMTP configurado.
#
# A pesquisa de satisfação é respondida dentro do chamado, no painel abaixo do
# chat — o e-mail não levava a lugar nenhum, só pedia que a pessoa entrasse no
# sistema. Decidido com o cliente em 07/08/2026: convite apenas in-app.
_IN_APP_ONLY = frozenset({NotificationType.satisfaction_survey})


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

    # Look up user email to send the notification
    result = await db.execute(select(User.email).where(User.id == user_id))
    email_addr = result.scalar_one_or_none()

    if email_addr:
        _PENDENTES.setdefault(db, []).append(
            _EmailPendente(
                notif_id=notif.id,
                to_email=email_addr,
                subject=title,
                body=message,
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
