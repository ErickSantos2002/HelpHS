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

``notify()`` NÃO envia nada — nunca enviou. Ele adiciona a linha de notificação
à sessão e, quando o tipo/papel liberam e-mail, adiciona TAMBÉM a linha da
outbox (``EmailOutbox``, via ``enqueue_email``) — as duas na MESMA transação.
``commit_e_notificar`` só commita; o envio de verdade é responsabilidade
exclusiva do worker da outbox (``app/services/email_outbox.py``), que roda em
outro ciclo, depois do commit ter voltado.

Fase 3B — o que mudou daqui
----------------------------
Até 29/09/2026 este módulo tinha um segundo mecanismo: um registro em
``WeakKeyDictionary`` chaveado pela sessão (a pendência de e-mail), disparado
via ``asyncio.create_task`` logo depois do commit — fire-and-forget, sem
durabilidade. Ele resolvia o mesmo problema que motiva esta seção agora
("não mandar e-mail sobre um commit que falhou"), mas por um caminho frágil:
se o processo morresse entre o commit e o envio, o e-mail se perdia sem deixar
rastro. A Fase 3A construiu a outbox durável para substituir exatamente isso; a
3B é o corte: ``Notification`` e ``EmailOutbox`` nascem na MESMA transação, o
commit é o único ponto de não-retorno para as duas, e o envio em si sai
inteiramente daqui.

Falha de envio SMTP nunca chega a este módulo — pertence só ao worker.
"""

import uuid
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.models import Notification, NotificationType, User, UserRole, UserStatus
from app.services.email_layout import Mensagem

# Import tardio de propósito: `email_outbox.py` importa `_assunto_do_email` e
# `_mensagem_do_email` DESTE módulo (para reconstruir o e-mail em tempo de
# envio, sem persistir conteúdo na outbox) — um `import` no topo aqui criaria
# um ciclo. `enqueue_email` só é chamado dentro de função, depois que os dois
# módulos já terminaram de carregar, então o import correspondente também vive
# ali dentro.

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

# Tipos em que o filtro por PAPEL não se aplica: staff recebe e-mail APESAR de
# ser staff.
#
# `ticket_created` entrou em 24/09/2026. Chamado novo é o único evento em que a
# equipe precisa ser alcançada FORA do sistema: é ele que dispara o atendimento,
# e esperar alguém olhar o sininho é justamente o atraso que esta frente existe
# para cortar.
#
# Isto NÃO enfraquece a decisão de 04/09: o `_SEM_EMAIL_POR_PAPEL` acima segue
# valendo para todos os outros tipos. Atribuição e reabertura continuam sem
# e-mail para staff, como a equipe pediu — o ruído que motivou aquele pedido era
# desses eventos, que acontecem muitas vezes no mesmo chamado. Chamado novo
# acontece uma vez.
#
# É o espelho do `_IN_APP_ONLY`: um conjunto de tipos que SILENCIA o e-mail,
# outro que o DESTRAVA. Mesma forma, mesmo arquivo, mesmo idioma.
#
# `sla_warning` entrou em 25/09/2026, na Fase 2A, e exatamente como estava
# previsto: um membro a mais, não uma condição espalhada por router.
#
# Ele honra o critério de `ticket_created` — "acontece uma vez" — por construção,
# e não por sorte: `sla_alert_events` tem índice único em
# `(ticket_id, alert_kind, effective_due_at, warning_threshold)`, e só quem
# consegue inserir a linha manda o aviso. Sem essa garantia ele seria justamente
# o tipo de evento repetido que o filtro de 04/09 existe para barrar — e é por
# isso que a dedup e esta linha são o mesmo assunto.
#
# `sla_breached` NÃO entra: ele não tem produtor nenhum hoje, e criá-lo mexe em
# indicador publicado.
_EMAIL_PARA_STAFF = frozenset({NotificationType.ticket_created, NotificationType.sla_warning})

# Os papéis que formam a OPERAÇÃO: quem atende chamado.
#
# `frozenset` próprio, e NÃO o `_SEM_EMAIL_POR_PAPEL` acima — que hoje tem
# exatamente os mesmos dois membros. São perguntas diferentes: este diz "quem é
# a equipe", o outro diz "quem não recebe e-mail". Reaproveitar um pelo outro
# faria a Fase 2, ao mexer num, mudar o outro em silêncio — e o sintoma seria
# alguém sumir da audiência por causa de uma decisão sobre e-mail.
_PAPEIS_OPERACIONAIS = frozenset({UserRole.admin, UserRole.technician})


def _pode_mandar_email(notif_type: NotificationType, papel: UserRole) -> bool:
    """O filtro por PAPEL, com a lista de exceções por TIPO.

    Uma função com nome em vez de uma condição composta na linha do envio: a
    regra tem duas metades que se leem ao contrário uma da outra, e escrita
    inline ela virava `papel not in A or tipo in B`, que ninguém confere de
    relance.

    O `return True` antecipado é a garantia do CLIENTE: ele nunca é filtrado,
    em nenhum tipo. Não é economia de linha — é o que impede que uma decisão
    sobre ruído interno silencie quem está do lado de fora.

    NÃO decide sobre `_IN_APP_ONLY`: aquele filtro vale para todo mundo e é
    resolvido antes, no `notify`. Acrescentar um tipo a `_EMAIL_PARA_STAFF` não
    fura o `_IN_APP_ONLY`.
    """
    if papel not in _SEM_EMAIL_POR_PAPEL:
        return True
    return notif_type in _EMAIL_PARA_STAFF


async def audiencia_operacional(db: AsyncSession) -> Sequence[User]:
    """Todos os técnicos e administradores ATIVOS — a definição única de "a equipe".

    A consulta existia inline em `_avisa_equipe_da_helo`, e era o único lugar do
    sistema que respondia "quem é a operação". Com o chamado novo passando a
    avisar a equipe, ela viraria o SEGUNDO lugar — e duas consultas com a mesma
    intenção divergem no primeiro técnico desativado, sem nada avisando.

    `status == active`, e não `!= inactive`: existe um terceiro valor,
    `anonymized`, que é conta apagada pela LGPD. O e-mail dela não é mais de
    ninguém, e a comparação por desigualdade a deixaria entrar.

    Sem `ORDER BY` de propósito: a ordem não muda nada: cada notificação tem id
    e carimbo próprios, e ordenar custaria uma varredura a cada chamado aberto.

    O filtro é uma cláusula `WHERE`, então quem o prova é
    `tests/test_audiencia_operacional_postgres.py`, contra Postgres de verdade.
    Mock não executa `WHERE` — a lição está registrada no cabeçalho de
    `tests/test_helo_base_postgres.py`.
    """
    resultado = await db.execute(
        select(User).where(
            User.role.in_(_PAPEIS_OPERACIONAIS),
            User.status == UserStatus.active,
        )
    )
    return resultado.scalars().all()


def _assunto_do_email(title: str, data: dict[str, Any] | None) -> str:
    """`[HelpHS] Chamado resolvido — HS-2026-0042`.

    O assunto era o título cru da notificação, e na lista da caixa isso é
    ilegível: cinco chamados abertos rendiam cinco "Ticket resolvido" idênticos,
    sem dizer qual. O protocolo entra quando existe — cinco das catorze chamadas
    não o carregam no `data`, e para elas o prefixo sozinho já é melhor do que
    nada.

    Não mexe no `title`: o sininho continua mostrando o texto cru.

    O separador é TRAVESSÃO desde 24/09/2026. Era ponto médio: ele some em fonte
    estreita de lista de caixa de entrada, e o travessão é o que o produto já usa
    para separar protocolo de título.

    É o FALLBACK GERAL, e desde a Fase 3B o ÚNICO caminho para a maioria dos
    tipos: o `email_subject` que `notify`/`notifica_audiencia` aceitavam foi
    removido junto com o envio eager — o worker da outbox reconstrói o assunto
    inteiramente a partir da `Notification` persistida, e não há mais lugar
    para computar um assunto "melhor" no momento do enqueue. O único tipo que
    precisava de mais que isto (`ticket_created`, para a equipe, que embute o
    título do chamado) ganhou reconstrução própria em
    `app/services/email_outbox.py:_assunto_reconstruido` — o resto passa por
    aqui.
    """
    protocolo = (data or {}).get("protocol")
    return f"[HelpHS] {title} — {protocolo}" if protocolo else f"[HelpHS] {title}"


def _mensagem_do_email(
    title: str,
    message: str,
    data: dict[str, Any] | None,
    nome: str | None,
    settings: Settings,
) -> Mensagem:
    """A notificação virando e-mail — a mesma fonte para o texto e para o HTML.

    O `rotulo` distingue o que tem chamado do que não tem: hoje as catorze
    chamadas carregam `ticket_id`, mas o `notify` é genérico e um aviso de
    sistema não pode ganhar um cartão de protocolo que não existe.
    """
    ticket_id = (data or {}).get("ticket_id")
    protocolo = (data or {}).get("protocol")
    link = _link_do_chamado(ticket_id, settings)

    return Mensagem(
        rotulo="seu chamado" if link else "aviso do sistema",
        titulo=title,
        saudacao=f"Olá, {nome.split()[0]}." if nome else None,
        paragrafos=(message,),
        acao=("Ver o chamado", link) if link else None,
        dados=(("protocolo", str(protocolo)),) if protocolo else (),
    )


def _link_do_chamado(ticket_id: Any, settings: Settings) -> str | None:
    """A mensagem, e o caminho de volta para o chamado.

    Levantado em 04/09/2026: DOZE dos catorze e-mails de notificação chegavam
    sem link. O `ticket_id` sempre esteve no `data` — as catorze chamadas o
    passam — e simplesmente não era usado. Avisar que o chamado andou sem dizer
    onde ele está obriga a pessoa a entrar no sistema e procurar.

    Sem `ticket_id` ou sem `FRONTEND_URL`, devolve a mensagem intacta: link
    inventado é pior que link ausente.
    """
    if not ticket_id or not settings.frontend_url:
        return None
    return f"{settings.frontend_url.rstrip('/')}/tickets/{ticket_id}"


def _grava_notificacao(
    db: AsyncSession,
    user_id: uuid.UUID,
    notif_type: NotificationType,
    title: str,
    message: str,
    data: dict[str, Any] | None,
) -> Notification:
    """A linha do sininho, adicionada à sessão. Não commita."""
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
    return notif


def _deve_enfileirar_email(
    notif_type: NotificationType,
    papel: UserRole,
    to_email: str | None,
    settings: Settings | None,
) -> bool:
    """A MESMA decisão de sempre — só que agora decide "cria linha de

    outbox?" em vez de "registra pendência de envio?". Extraída para que o
    envio individual (`notify`) e o em lote (`notifica_audiencia`) tomem a
    mesma condição; duas cópias da mesma regra é o que já divergiu uma vez,
    entre `_IN_APP_ONLY` e o filtro por papel, antes de existir
    `_pode_mandar_email`.

    `settings is None` continua sendo o sinal de "este call site não quer
    e-mail" — não é config de SMTP (o worker resolve isso sozinho, na hora do
    envio): é a marca histórica de quem chama `notify`/`notifica_audiencia`
    sem passar `settings=`, e dois eventos hoje fazem isso de propósito (ver
    `_SEM_EMAIL_POR_PAPEL`).
    """
    if settings is None or notif_type in _IN_APP_ONLY:
        return False
    if not to_email:
        return False
    return _pode_mandar_email(notif_type, papel)


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
    Cria a notificação in-app e, quando o tipo/papel liberam e-mail, a linha
    da outbox — as duas na MESMA transação.

    Não commita e não envia nada: o commit é do chamador, para que
    `Notification` e `EmailOutbox` sejam atômicas com a operação que as
    provocou. Quem envia de fato é o worker da outbox, depois do commit ter
    voltado, em outro ciclo.

    Para vários destinatários use ``notifica_audiencia``: um laço de ``notify``
    aqui faz um SELECT por pessoa.
    """
    notif = _grava_notificacao(db, user_id, notif_type, title, message, data)

    if settings is None or notif_type in _IN_APP_ONLY:
        return  # no email without settings

    # A busca traz o PAPEL junto do e-mail: desde 04/09/2026 quem decide o
    # envio não é só o tipo da notificação, é também quem recebe. Uma consulta
    # só — a coluna a mais não custa nada e evita uma segunda ida ao banco.
    result = await db.execute(select(User.email, User.role, User.name).where(User.id == user_id))
    destinatario = result.one_or_none()

    # Destinatário que sumiu entre a ação e a notificação não pode virar
    # exceção: quem chamou já fez o trabalho, e o e-mail é o acessório.
    if destinatario is None:
        return

    email_addr, papel, _nome = destinatario
    if _deve_enfileirar_email(notif_type, papel, email_addr, settings):
        from app.services.email_outbox import enqueue_email

        enqueue_email(db, notif)


async def notifica_audiencia(
    db: AsyncSession,
    destinatarios: Iterable[User],
    notif_type: NotificationType,
    title: str,
    message: str,
    data: dict[str, Any] | None = None,
    settings: Settings | None = None,
    exclude_user_ids: set[uuid.UUID] | None = None,
) -> list[uuid.UUID]:
    """O mesmo evento para VÁRIAS pessoas. Devolve os `user_id` de fato avisados.

    Recebe destinatários JÁ CARREGADOS — é o que ``audiencia_operacional``
    devolve. Por isso não vai ao banco **nenhuma vez**: o `notify()` individual
    faz um SELECT por destinatário, e um laço dele faria N. Com quinze técnicos,
    quinze consultas por chamado aberto. Aqui é zero, não uma.

    ``exclude_user_ids`` é EXPLÍCITO, e não "quem já foi notificado antes". A
    diferença importa: o `create_ticket` avisa o autor e depois a equipe, e se a
    exclusão dependesse da ordem das duas chamadas, invertê-las produziria duas
    notificações para o autor-staff sem nada avisando. Passando o conjunto, a
    ordem deixa de ser parte da regra.

    A dedup por `user_id` é interna e independente disso: a mesma pessoa
    chegando duas vezes na lista recebe uma notificação. Hoje a audiência não
    repete — a consulta é por chave primária —, mas quem compuser duas listas um
    dia não deveria precisar saber disso.

    Não commita: quem consolida é ``commit_e_notificar``, como no `notify`.
    """
    from app.services.email_outbox import enqueue_email

    excluidos: set[uuid.UUID] = exclude_user_ids or set()
    vistos: set[uuid.UUID] = set()
    avisados: list[uuid.UUID] = []

    for pessoa in destinatarios:
        if pessoa.id in excluidos or pessoa.id in vistos:
            continue
        vistos.add(pessoa.id)

        notif = _grava_notificacao(db, pessoa.id, notif_type, title, message, data)
        if _deve_enfileirar_email(notif_type, pessoa.role, pessoa.email, settings):
            enqueue_email(db, notif)
        avisados.append(pessoa.id)

    return avisados


async def commit_e_notificar(db: AsyncSession) -> None:
    """
    Commita a transação.

    O nome sobrevive por compatibilidade com os ~20 call sites que já
    terminam seus handlers com ``await commit_e_notificar(db)`` — até a Fase
    3B esta função também disparava os e-mails registrados na sessão, logo
    depois do commit. Isso não existe mais: `Notification` e `EmailOutbox` já
    nasceram juntas, dentro da MESMA transação que este commit fecha, e quem
    envia de fato é o worker da outbox, em outro ciclo. Não há mais nada para
    disparar aqui.
    """
    await db.commit()
