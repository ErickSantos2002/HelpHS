"""
Numeração das mensagens do chat na ORDEM DE COMMIT (F1-B-04c).

O problema: `created_at` é carimbado antes do commit — antes da Helô, que pode
levar até 40 s. Uma mensagem carimbada às 10:00:00 pode ficar visível depois
de outra carimbada às 10:00:05, e quem relê "o que veio depois do que eu já
vi" por `created_at` nunca mais a encontra. `seq` é a ordem em que elas ficam
VISÍVEIS, e é por ela que a tela recupera (`GET ...?after_seq=k`).

COMO A ORDEM É GARANTIDA
------------------------
`numera_mensagens_do_chat` roda no fim da transação, logo antes do COMMIT:

    UPDATE tickets SET chat_seq = chat_seq + n WHERE id = :chamado RETURNING chat_seq

O UPDATE trava a linha do chamado até o fim da transação. Outra transação do
mesmo chamado que chegar a esse ponto espera; quando a primeira comita, o
UPDATE da segunda reavalia sobre a linha JÁ COMITADA (READ COMMITTED) e
recebe o número seguinte. Logo, número maior = commit depois. Rollback desfaz
o incremento junto com as mensagens: sem buraco. (Prova de conceito de
04/11/2026, PostgreSQL 16.2, com `pg_xact_commit_timestamp` conferindo a ordem
real dos commits; e `tests/test_chat_sequencia_postgres.py`.)

Não é SEQUENCE/BIGSERIAL: o número de uma SEQUENCE sai quando é pedido, não
quando a transação comita, e rollback deixa buraco.

ORDEM GLOBAL DOS BLOQUEIOS — leia antes de mexer em transação que toca chamado
------------------------------------------------------------------------------
1. Usuários antes de chamados. Quem trava usuário (`_trava_usuario`,
   `_trava_para_alterar_conta`, ambos `FOR UPDATE`) faz isso no começo da
   transação. Uma transação que trave um CHAMADO e DEPOIS peça `FOR UPDATE`,
   `DELETE` ou troca de e-mail de um usuário fecha ciclo com o envio de
   mensagem: o envio segura `FOR KEY SHARE` no usuário (FK da notificação e do
   remetente) e, no fim, pede o chamado. Reproduzido: deadlock em 6 de 6
   rodadas (prova de conceito), e preso em teste.
2. O contador é o ÚLTIMO bloqueio do envio. Nada depois dele pede bloqueio
   novo — só o COMMIT. Em particular, ele NUNCA é pedido antes da Helô: a
   chamada ao modelo de linguagem dura até 40 s, e o contador travado nesse
   tempo poria em fila todo envio do chamado e toda escrita da equipe nele.
3. Entre chamados, a ordem do id (`sorted`). Hoje nenhuma transação numera
   mais de um chamado; a regra existe para a primeira que vier.

Quem perde um deadlock (40P01) ou uma falha de serialização (40001) não é
repetido automaticamente: a transação inteira foi desfeita, e repetir
chamaria a Helô de novo — efeito externo que rollback nenhum desfaz. O envio
volta como NÃO GRAVADO, e quem enviou reenvia (`perdeu_a_concorrencia`).

QUAIS MENSAGENS SÃO NUMERADAS
-----------------------------
As que ESTA transação gravou, e só elas: o módulo anota cada `ChatMessage` no
instante em que o flush a grava (`pending_to_persistent`) e esquece tudo no
fim da transação. Quem chama não precisa listar — a fala da Helô entra sozinha
no mesmo envio do cliente, na ordem em que foi gravada. Mensagem carregada do
banco (legado, histórico lido pela Helô) nunca é anotada; mensagem desfeita
por SAVEPOINT (o reenvio que parou no índice único) deixa de ser persistente e
fica de fora; mensagem que já tem número não é renumerada.

Os escritores de `chat_messages` e quem é dono de cada transação estão
inventariados em `tests/test_chat_escritores_de_mensagem.py`: um escritor
novo, ou um dono que comite sem chamar `numera_mensagens_do_chat`, derruba o
teste.

QUANDO O MODO INCREMENTAL É ANUNCIADO
-------------------------------------
`incremental_disponivel`: só quando TUDO o que existe no chamado desde o corte
tem número. Mensagem sem número a partir do corte (menos a margem) é de uma
imagem que não numera — troca de instâncias ou recuo —, e `after_seq` não a
devolveria: o chamado fica no histórico tradicional até o script de
recuperação numerá-la. Sem o marco do corte no banco, não é anunciado. A
variável de ambiente só LIGA a possibilidade; quem afirma que é seguro é o
banco.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import event, inspect, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction
from sqlalchemy.orm.attributes import set_committed_value

from app.models.models import ChatMessage, ChatSeqCorte, Ticket

_ANOTADAS = "chat_mensagens_gravadas_na_transacao"

# deadlock_detected e serialization_failure. A segunda só existe fora do READ
# COMMITTED (o padrão do app); está aqui para quem um dia subir o isolamento.
_PERDEU_A_CORRIDA = frozenset({"40P01", "40001"})

# Quanto antes do corte uma mensagem gravada DEPOIS dele pode ter sido
# carimbada. `created_at` sai do relógio da aplicação quando a mensagem é
# montada; numa imagem antiga o INSERT pode ficar para depois da Helô (até
# 40 s) e da espera pela própria migration. Quinze minutos cobrem isso com
# folga, e também uma diferença razoável entre o relógio da aplicação e o do
# banco. Errar para mais só deixa o chamado no histórico tradicional; errar para
# menos perde mensagem. Por isso é constante, e não configuração.
MARGEM_DO_CORTE = timedelta(minutes=15)


@event.listens_for(Session, "pending_to_persistent")
def _anota(session: Session, instancia: object) -> None:
    if isinstance(instancia, ChatMessage):
        session.info.setdefault(_ANOTADAS, []).append(instancia)


@event.listens_for(Session, "after_transaction_end")
def _esquece(session: Session, transacao: SessionTransaction) -> None:
    # Só a transação de verdade. O fim de um SAVEPOINT não apaga a anotação: a
    # mensagem gravada dentro dele e mantida continua sendo desta transação.
    if transacao.parent is None:
        session.info.pop(_ANOTADAS, None)


async def numera_mensagens_do_chat(db: AsyncSession) -> None:
    """Numera, na ordem de gravação, as mensagens que esta transação gravou.

    Chamar IMEDIATAMENTE antes do commit, depois de tudo o que o envio faz —
    Helô, notificações, transição de status. Ver a ordem dos bloqueios no
    topo do módulo. Chamar duas vezes não renumera.
    """
    await db.flush()
    por_chamado: dict[uuid.UUID, list[ChatMessage]] = {}
    for msg in db.sync_session.info.get(_ANOTADAS, []):
        estado = inspect(msg)
        if estado.persistent and msg.seq is None:
            por_chamado.setdefault(msg.ticket_id, []).append(msg)
    if not por_chamado:
        return

    for chamado_id in sorted(por_chamado):
        mensagens = por_chamado[chamado_id]
        ultimo = (
            await db.execute(
                update(Ticket)
                .where(Ticket.id == chamado_id)
                .values(chat_seq=Ticket.chat_seq + len(mensagens))
                .returning(Ticket.chat_seq)
                .execution_options(synchronize_session=False)
            )
        ).scalar_one()
        for numero, msg in enumerate(mensagens, start=ultimo - len(mensagens) + 1):
            msg.seq = numero
        # O chamado que já está na sessão passa a refletir o banco, sem marcar
        # nada como alterado: um flush depois não regrava o contador velho.
        carregado = db.sync_session.identity_map.get(
            db.sync_session.identity_key(Ticket, chamado_id)
        )
        if carregado is not None:
            set_committed_value(carregado, "chat_seq", ultimo)
    await db.flush()


async def corte_da_numeracao(db: AsyncSession) -> datetime | None:
    """O instante gravado pela migration, ou `None` se a linha não existe."""
    return (
        await db.execute(select(ChatSeqCorte.migrada_em).where(ChatSeqCorte.id == 1))
    ).scalar_one_or_none()


async def incremental_disponivel(db: AsyncSession, ticket_id: uuid.UUID) -> bool:
    """O chamado pode ser sincronizado por `after_seq` sem perder nada?

    Não, quando falta o marco do corte, ou quando existe no chamado mensagem
    sem número com `created_at` a partir do corte menos a margem. Na dúvida, não.
    """
    corte = await corte_da_numeracao(db)
    if corte is None:
        return False
    sem_numero = await db.execute(
        select(ChatMessage.id)
        .where(
            ChatMessage.ticket_id == ticket_id,
            ChatMessage.seq.is_(None),
            ChatMessage.created_at >= corte - MARGEM_DO_CORTE,
        )
        .limit(1)
    )
    return sem_numero.first() is None


def perdeu_a_concorrencia(exc: BaseException) -> bool:
    """Deadlock ou falha de serialização — a transação foi desfeita pelo banco
    e o envio NÃO foi gravado. Qualquer outro erro de banco não é isto."""
    if not isinstance(exc, DBAPIError):
        return False
    origem = exc.orig
    codigo = getattr(origem, "sqlstate", None) or getattr(origem, "pgcode", None)
    return codigo in _PERDEU_A_CORRIDA
