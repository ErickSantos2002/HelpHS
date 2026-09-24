"""
Orquestração da tentativa de ligação: tudo o que acontece ANTES do fornecedor.

Este módulo decide se uma ligação PODE sair e deixa a tentativa gravada e
durável. Ele não liga para ninguém — e, nesta fase, deliberadamente não tem
rota: a Fase 2C.2 termina no `pending` commitado.

POR QUE É UM MÓDULO NOVO, E NÃO O `telefonia.py`
-------------------------------------------------
`services/telefonia.py` é persistência pura, e há teste de AST provando que ele
não importa `httpx` nem `api4com.py`. A orquestração vai precisar importar o
transporte na fase seguinte; enfiá-la lá derrubaria aquela garantia. Aqui os
dois lados podem conviver quando chegar a hora.

A ORDEM É O DESENHO
-------------------
Cada passo está onde está por um motivo, e trocar a ordem reabre um buraco:

  1. papel do ator ......... barato, e nega antes de qualquer consulta
  2. chamado ............... 404 antes de falar em telefone
  3. situação do chamado ... não se liga sobre chamado encerrado
  4. destinatário .......... SELECT explícito, nunca lazy
  5. telefone .............. relido do banco, validado pelo helper oficial
  6. ramal do ator ......... sem ramal não há origem possível
  7. LOCK .................. só agora: não se toma lock para depois dar 422
  8. antirrepetição ........ DENTRO do lock, senão dois cliques passam juntos
  9. teto por hora ......... idem
 10. `pending` + COMMIT .... a tentativa fica durável ANTES de qualquer efeito

A fase seguinte acrescenta, sem mexer em nada acima: `dispatching` + COMMIT →
`create_call` → estado final + COMMIT. Tudo isso **dentro** do mesmo lock.

O QUE ESTE MÓDULO NÃO FAZ
-------------------------
Não chama o fornecedor, não importa `api4com`, não escreve `TicketHistory` (uma
linha `pending` não é contato: ninguém foi chamado ainda) e não repete nada
automaticamente.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import get_redis
from app.models.models import (
    CallCreationStatus,
    Ticket,
    TicketCall,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
)
from app.services import telefonia
from app.utils.crud import get_or_404
from app.utils.telefone import normaliza_telefone

_CHAMADO_NAO_ENCONTRADO = "Chamado não encontrado."

# Chamado encerrado não recebe ligação. A lista é do que PODE, e não do que não
# pode, para que um estado novo nasça bloqueado em vez de liberado por omissão.
STATUS_QUE_PERMITEM_LIGACAO = frozenset(
    {
        TicketStatus.open,
        TicketStatus.in_progress,
        TicketStatus.awaiting_client,
        TicketStatus.awaiting_technical,
        # `resolved` entra porque ligar para confirmar a solução é atendimento
        # real, e o chamado ainda está no ciclo (o fechamento automático age
        # sobre ele). `closed` e `cancelled` ficam de fora.
        TicketStatus.resolved,
    }
)

# Tentativas que PODEM ter feito um telefone tocar. `pending` não está aqui, e
# é a diferença que o estado `dispatching` comprou: uma linha `pending` órfã
# significa que nada saiu, então ela não impede uma nova tentativa.
STATUS_QUE_BLOQUEIAM_REPETICAO = frozenset(
    {
        CallCreationStatus.dispatching.value,
        CallCreationStatus.confirmed.value,
        CallCreationStatus.indeterminate.value,
    }
)

_PREFIXO_LOCK = "helphs:lock:telefonia:ticket:"
_PREFIXO_TETO_ATOR = "helphs:telefonia:ator:"
_PREFIXO_TETO_CHAMADO = "helphs:telefonia:chamado:"

# `redis.eval` é o comando de SCRIPT LUA do Redis — nada a ver com o `eval()` do
# Python. O script abaixo é constante literal; a chave e o token viajam como
# KEYS[1]/ARGV[1] parametrizados, e nenhuma entrada de usuário entra no texto.
#
# Compara e só então apaga, num passo atômico. Sem isto, um `DEL` cego apagaria
# o lock de OUTRA execução no caso em que o nosso já expirou por TTL e alguém
# reaquiriu no intervalo — cenário raro e silencioso, que é a pior combinação.
_LUA_LIBERA_SE_MEU = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


class LockDoChamadoOcupadoError(RuntimeError):
    """Outra execução está tratando uma ligação para este mesmo chamado."""


async def adquire_lock(ticket_id: uuid.UUID) -> str:
    """Toma o lock do chamado e devolve o token de posse.

    `SET ... NX EX` numa operação só: dois cliques simultâneos não conseguem
    ambos observar "livre" e ambos gravar. O token é de quem adquiriu, e só ele
    libera — ver `_LUA_LIBERA_SE_MEU`.

    O TTL é a rede de proteção para o processo que morre segurando o lock: sem
    ele, um crash prenderia o chamado para sempre.
    """
    redis = await get_redis()
    token = uuid.uuid4().hex
    pegou = await redis.set(
        f"{_PREFIXO_LOCK}{ticket_id}",
        token,
        nx=True,
        ex=get_settings().api4com_lock_ttl_seconds,
    )
    if not pegou:
        raise LockDoChamadoOcupadoError
    return token


async def libera_lock(ticket_id: uuid.UUID, token: str) -> None:
    """Libera apenas se o lock ainda for nosso. Nunca levanta."""
    try:
        redis = await get_redis()
        # O `cast` existe só por causa do stub do redis-py, que declara `eval`
        # devolvendo `Awaitable[str] | str` para servir ao cliente síncrono e ao
        # assíncrono com a mesma assinatura. Neste projeto o cliente é sempre o
        # assíncrono.
        await cast(
            "Awaitable[Any]",
            redis.eval(_LUA_LIBERA_SE_MEU, 1, f"{_PREFIXO_LOCK}{ticket_id}", token),
        )
    except Exception:  # noqa: BLE001 — falhar ao liberar não pode derrubar a requisição
        # O TTL resolve sozinho em segundos. Deixar a exceção subir trocaria um
        # atraso de 30s por um erro numa operação que já deu certo.
        pass


async def _consome_teto(chave: str, limite: int, janela_segundos: int = 3600) -> bool:
    """Contador por janela no Redis. Devolve `False` quando o teto estourou.

    `INCR` cria a chave em 1 se ela não existir, e o `EXPIRE` só é aplicado na
    primeira — senão cada nova ligação empurraria a janela para frente e o teto
    nunca fecharia.

    Conta no Redis, e não em memória, porque o limite precisa valer entre
    workers: o `start.sh` sobe um hoje, mas o número é estágio, não garantia.
    """
    redis = await get_redis()
    atual = await redis.incr(chave)
    if atual == 1:
        await redis.expire(chave, janela_segundos)
    return int(atual) <= limite


async def _destinatario(db: AsyncSession, ticket: Ticket) -> User:
    """Relê o cliente do chamado, sempre do banco.

    ⚠️ `SELECT` explícito, e não `ticket.creator`: o relacionamento é lazy, e
    tocá-lo fora de um contexto carregado estoura `MissingGreenlet` em sessão
    async. Mas o motivo principal não é técnico — é que o telefone para onde a
    ligação vai precisa vir do banco no instante da ação, num comando que se lê
    no código, e não de um objeto que passou por qualquer outro lugar.
    """
    resultado = await db.execute(select(User).where(User.id == ticket.creator_id))
    destinatario = resultado.scalar_one_or_none()
    if destinatario is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="O chamado não tem um cliente para receber a ligação.",
        )
    return destinatario


def _telefone_do_destinatario(destinatario: User) -> str:
    """Valida o telefone lido do banco e devolve o E.164 canônico.

    A telefonia do HelpHS é unidirecional: quem recebe é sempre o cliente que
    abriu o chamado. Chamado aberto por staff tem `creator` staff e fica de
    fora — dívida conhecida, não defeito desta fase.

    ⚠️ "Cadastrado e sintaticamente válido" não é "verificado": o próprio
    cliente edita o telefone em `PATCH /users/me`, sem prova de titularidade. O
    `CHECK` do banco garante PRESENÇA, não formato — por isso a validação
    acontece aqui, com o helper oficial, e não se confia na constraint.
    """
    if destinatario.role != UserRole.client:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A ligação só é feita para o cliente que abriu o chamado.",
        )
    if destinatario.status != UserStatus.active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="O cliente do chamado não está ativo.",
        )
    try:
        return normaliza_telefone(destinatario.phone or "")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="O cliente do chamado não tem um telefone válido cadastrado.",
        ) from None


def _ramal_do_ator(ator: User) -> str:
    """O ramal sai do cadastro do ator, e de nenhum outro lugar.

    Nunca do request, nunca de `GET /extensions` a cada clique, nunca de um
    padrão global e nunca do "primeiro disponível": qualquer um desses faria a
    ligação sair com a identidade de outra pessoa.

    Hoje ninguém tem ramal — os ramais do suporte ainda não existem na conta do
    fornecedor —, então este é o bloqueio que todo mundo encontra. É o
    comportamento correto: sem origem não há ligação.
    """
    ramal = (ator.api4com_extension or "").strip()
    if not ramal:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Você não tem ramal de telefonia configurado.",
        )
    return ramal


async def _recusa_repeticao(db: AsyncSession, ticket_id: uuid.UUID) -> None:
    """Recusa quando há tentativa recente que pode ter tocado um telefone."""
    settings = get_settings()
    desde = datetime.now(UTC) - timedelta(seconds=settings.api4com_repeat_window_seconds)
    resultado = await db.execute(
        select(TicketCall).where(
            TicketCall.ticket_id == ticket_id,
            TicketCall.creation_status.in_(STATUS_QUE_BLOQUEIAM_REPETICAO),
            TicketCall.created_at >= desde,
        )
    )
    if resultado.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já houve uma tentativa de ligação para este chamado há poucos minutos.",
        )


async def _recusa_excesso(db: AsyncSession, ticket_id: uuid.UUID, ator: User) -> None:
    """Tetos por hora, por ator e por chamado.

    Consumidos aqui, depois de todas as validações: um pedido recusado por
    chamado encerrado ou cliente sem telefone não gasta cota de ninguém. O
    contador anda quando a tentativa vai mesmo ser criada.
    """
    settings = get_settings()
    if not await _consome_teto(
        f"{_PREFIXO_TETO_ATOR}{ator.id}", settings.api4com_calls_per_actor_per_hour
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Você atingiu o limite de ligações por hora.",
        )
    if not await _consome_teto(
        f"{_PREFIXO_TETO_CHAMADO}{ticket_id}", settings.api4com_calls_per_ticket_per_hour
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Este chamado atingiu o limite de ligações por hora.",
        )


async def prepara_tentativa(
    db: AsyncSession,
    *,
    ticket_id: uuid.UUID,
    ator: User,
) -> TicketCall:
    """Valida tudo, reserva o chamado e deixa a tentativa `pending` DURÁVEL.

    Devolve a linha de `ticket_calls` já commitada. **Nenhuma requisição sai
    para o fornecedor** — nem daqui, nem de nada que este módulo chame.

    ⚠️ Esta função COMMITA, contra a convenção da casa de que o controle
    transacional é de quem chama. É deliberado e é o ponto inteiro do desenho:
    a tentativa precisa estar no banco antes que qualquer efeito externo possa
    começar. Um `flush` sem commit some no rollback, e aí o fornecedor teria
    recebido uma ligação da qual não haveria registro nenhum.

    ⚠️ O lock é liberado no fim desta função porque a fase termina aqui. Quando
    o `create_call` entrar, ele fica DENTRO deste bloco protegido, e a
    liberação passa para depois do estado final — senão a janela que o lock
    existe para cobrir fica descoberta justamente onde importa.
    """
    if ator.role not in (UserRole.admin, UserRole.technician):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para acessar este item.",
        )

    ticket = await get_or_404(db, Ticket, ticket_id, _CHAMADO_NAO_ENCONTRADO)

    if ticket.status not in STATUS_QUE_PERMITEM_LIGACAO:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Este chamado não aceita ligação no estado atual.",
        )

    destinatario = await _destinatario(db, ticket)
    # O telefone e o ramal são resolvidos e VALIDADOS aqui, antes do lock, para
    # que um cadastro incompleto não reserve o chamado. Os valores não são
    # usados nesta fase — quem os consome é o `create_call` da fase seguinte —,
    # mas a validação precisa acontecer antes de a tentativa existir.
    _telefone_do_destinatario(destinatario)
    _ramal_do_ator(ator)

    try:
        token = await adquire_lock(ticket_id)
    except LockDoChamadoOcupadoError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já há uma ligação em andamento para este chamado.",
        ) from None

    try:
        await _recusa_repeticao(db, ticket_id)
        await _recusa_excesso(db, ticket_id, ator)

        tentativa = await telefonia.registra_tentativa(
            db, ticket_id=ticket_id, initiated_by_id=ator.id
        )
        await db.commit()
        await db.refresh(tentativa)
        return tentativa
    finally:
        await libera_lock(ticket_id, token)


async def tentativas_do_chamado(db: AsyncSession, ticket_id: uuid.UUID) -> int:
    """Quantas tentativas o chamado já teve. Usado por teste e diagnóstico."""
    resultado = await db.execute(
        select(func.count()).select_from(TicketCall).where(TicketCall.ticket_id == ticket_id)
    )
    return int(resultado.scalar_one())
