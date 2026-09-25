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
  8. teto por hora ......... DENTRO do lock, senão dois cliques passam juntos
  9. `pending` + COMMIT .... a tentativa fica durável ANTES de qualquer efeito

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
from typing import Any, cast

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import get_redis
from app.models.models import (
    Ticket,
    TicketCall,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
)
from app.services import api4com, telefonia
from app.utils.crud import get_or_404
from app.utils.history import registra_historico
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

# ⚠️ Aqui morava `STATUS_QUE_BLOQUEIAM_REPETICAO`, e com ela uma janela de 5
# minutos que recusava nova ligação para o mesmo chamado com 409.
#
# Saiu em 25/09/2026, por decisão de negócio: quem atende liga para o cliente
# quantas vezes for preciso, e não caiu do céu — a primeira ligação real do
# HelpHS precisou de DUAS tentativas (a primeira voltou 424 do fornecedor), e a
# janela teria transformado uma segunda tentativa legítima em erro se a primeira
# tivesse sido `confirmed`.
#
# O que NÃO saiu, e não pode ser confundido com isto:
#
#   - o lock do Redis, que impede DUAS ligações ao mesmo tempo no mesmo chamado;
#   - os tetos por hora, que são defesa contra laço e conta comprometida;
#   - a ausência de repetição automática — quem repete é gente, clicando.
#
# A distinção é: a janela olhava para o PASSADO ("já ligaram há pouco"), e o
# lock olha para o PRESENTE ("estão ligando agora"). Só a primeira contrariava
# a regra nova.

_PREFIXO_LOCK = "helphs:lock:telefonia:ticket:"
_PREFIXO_TETO_ATOR = "helphs:telefonia:ator:"

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


async def _recusa_excesso(ator: User) -> None:
    """Teto por hora, POR ATOR. Não existe mais teto por chamado.

    Consumido aqui, depois de todas as validações: um pedido recusado por
    chamado encerrado ou cliente sem telefone não gasta cota de ninguém. O
    contador anda quando a tentativa vai mesmo ser criada.

    ⚠️ Havia um segundo teto, de 3 por hora POR CHAMADO. Saiu em 25/09/2026
    junto com a antirrepetição temporal, e pelo mesmo motivo: ele dizia quantas
    vezes se pode ligar para o mesmo chamado, e a regra de negócio passou a ser
    "quantas vezes for preciso". A primeira ligação real gastou 2 das 3 cotas
    de uma vez, porque a primeira tentativa voltou 424 do fornecedor.

    O teto por ATOR fica, e é ele que cobre o risco que motivou os dois: laço
    de código, conta comprometida e volume anormal são propriedades de QUEM
    liga, não do chamado para onde se liga.
    """
    settings = get_settings()
    if not await _consome_teto(
        f"{_PREFIXO_TETO_ATOR}{ator.id}", settings.api4com_calls_per_actor_per_hour
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Você atingiu o limite de ligações por hora.",
        )


# ── As duas políticas do payload ─────────────────────────────


def _resolve_caller(extension: str) -> str:
    """De onde a ligação diz que parte. Hoje: o próprio ramal do ator.

    ⚠️ Isto é DECISÃO DE INTEGRAÇÃO, não regra universal do fornecedor. A
    documentação descreve `caller` como "o número que originará a chamada,
    **normalmente** o mesmo valor que `extension`" — e "normalmente" não é
    "sempre". Se um dia a conta precisar exibir um número de saída diferente do
    ramal (uma bina comercial, por exemplo), é esta função que muda, e só ela.

    Existe como função de uma linha exatamente para que a decisão tenha um
    lugar, um nome e um teste, em vez de virar uma repetição de variável dentro
    da montagem do payload.
    """
    return extension


def _formata_called_api4com(telefone_e164: str) -> str:
    """Traduz o E.164 interno para a grafia que o fornecedor espera em `called`.

    ⚠️ **A GRAFIA CANÔNICA SEGUE EM ABERTO COM O FORNECEDOR.** A documentação
    oficial mostra as duas, para a MESMA rota e o MESMO campo (medido em
    24/09/2026):

        referência da API (Call.clickToCall)  ->  "called": "4833328530"
        guia do webphone próprio              ->  "called": "+554833328530"

    `docs/decisoes-e-regras.md` registra que o `+55` seria da rota morta
    `/dialer` — isso está INCOMPLETO: o `+55` aparece também no `/calls` atual.

    Por isso a escolha é CONFIGURÁVEL (`API4COM_CALLED_FORMAT`) e vive só aqui.
    Trocar de ideia é mudar uma variável de ambiente, não caçar concatenação
    espalhada. E o padrão (`nacional`) segue a REFERÊNCIA da rota, por ser
    especificação e não tutorial — mas é escolha de moeda até o suporte
    responder.

    Só sabe tirar o `+55` de número BRASILEIRO. Um E.164 de outro país volta
    como está: inventar regra de trunk para país que não temos seria pior que
    mandar o canônico.
    """
    canonico = telefone_e164.strip()
    if get_settings().api4com_called_format == "e164":
        return canonico
    if canonico.startswith("+55"):
        return canonico[3:]
    return canonico


async def inicia_ligacao(
    db: AsyncSession,
    *,
    ticket_id: uuid.UUID,
    ator: User,
) -> TicketCall:
    """Valida, reserva o chamado, fala com o fornecedor e persiste o desfecho.

    Devolve a linha de `ticket_calls` no estado FINAL, já commitada.

    O caminho inteiro, e cada passo está onde está por um motivo:

        flag → papel → chamado → situação → destinatário → telefone → ramal
        → LOCK → teto → `pending` + COMMIT
        → `dispatching` + COMMIT → create_call → estado final + COMMIT
        → libera o lock

    ⚠️ Esta função COMMITA, contra a convenção da casa de que o controle
    transacional é de quem chama. É deliberado e é o ponto inteiro do desenho:
    a tentativa precisa estar no banco antes que qualquer efeito externo possa
    começar. Um `flush` sem commit some no rollback, e aí o fornecedor teria
    recebido uma ligação da qual não haveria registro nenhum.

    ⚠️ O lock cobre a conversa inteira com o fornecedor, e não só a criação da
    linha: é entre o `dispatching` e a resposta que dois cliques fariam o
    telefone tocar duas vezes. Ele é liberado no `finally`, depois do estado
    final — e o TTL de 30s é a rede para o processo que morrer segurando.
    """
    if not get_settings().api4com_enabled:
        # Antes de QUALQUER escrita: desligada não cria tentativa, não reserva
        # chamado e não gasta cota. 503 é o que esta casa usa para dependência
        # externa indisponível — ver `/auth/cnpj` e `/auth/cep`.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A telefonia está indisponível no momento.",
        )

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
        await _recusa_excesso(ator)

        tentativa = await telefonia.registra_tentativa(
            db, ticket_id=ticket_id, initiated_by_id=ator.id
        )
        await db.commit()

        # ── A FRONTEIRA ──────────────────────────────────────
        #
        # `dispatching` é gravado e COMMITADO antes do POST. Daqui para a
        # frente, uma linha órfã significa "não sabemos se tocou", e é por isso
        # que este commit não pode ser adiado nem agrupado com o próximo: se o
        # processo morrer entre ele e a resposta, é este estado que REGISTRA
        # que houve uma zona cinzenta, para quem for reconciliar depois.
        #
        # ⚠️ Até 25/09/2026 esta linha dizia que o estado "impede alguém de
        # repetir por engano". Deixou de ser verdade quando a antirrepetição
        # temporal saiu: hoje `dispatching` órfã não barra nada além do que o
        # lock já barra enquanto vive. Ele continua sendo o que distingue
        # "nada saiu" de "não sei" — valor de auditoria, não de bloqueio.
        await telefonia.marca_em_despacho(db, tentativa)
        # O evento humano nasce AQUI, e não junto do `pending`: uma linha
        # `pending` não é contato — ninguém foi chamado ainda. A partir do
        # despacho, houve tentativa de verdade, e é isso que o histórico conta.
        #
        # Genérico de propósito: diz QUE houve tentativa, não como terminou. O
        # desfecho é máquina de estados e vive em `ticket_calls`; duplicá-lo
        # aqui criaria duas versões que divergem em silêncio — defeito que este
        # projeto já pagou caro.
        #
        # ⚠️ NÃO entra em `CAMPOS_INTERNOS`: o cliente recebeu a ligação, então
        # esconder dele que ela foi tentada seria opacidade sem ganho. E o
        # evento não carrega telefone, ramal, identificador do fornecedor nem
        # payload — só o fato.
        registra_historico(db, ticket_id, ator.id, "ligacao", None, "tentativa")
        await db.commit()

        await _executa_e_persiste(db, tentativa, destinatario=destinatario, ator=ator)
        await db.refresh(tentativa)
        return tentativa
    finally:
        await libera_lock(ticket_id, token)


async def _executa_e_persiste(
    db: AsyncSession,
    tentativa: TicketCall,
    *,
    destinatario: User,
    ator: User,
) -> None:
    """A única chamada externa do HelpHS, e a leitura do que ela devolveu.

    Cada `except` aqui traduz uma afirmação do transporte sobre o EFEITO, não
    sobre o erro. A classificação inteira mora em `services/api4com.py` e este
    módulo não a reinterpreta — só persiste.

    ⚠️ Não há retry. Nenhum caminho abaixo chama `create_call` de novo, e o
    `httpx` do transporte roda com `retries=0` e sem seguir redirect. Repetir
    aqui faria o telefone do cliente tocar duas vezes por uma decisão que
    ninguém tomou.
    """
    try:
        resultado = await api4com.create_call(
            caller=_resolve_caller(_ramal_do_ator(ator)),
            called=_formata_called_api4com(_telefone_do_destinatario(destinatario)),
            extension=_ramal_do_ator(ator),
        )
    except api4com.Api4ComRecusadaError as erro:
        # 4xx: o fornecedor respondeu recusando a REQUISIÇÃO. Nada tocou.
        await telefonia.marca_recusada(db, tentativa, provider_http_status=erro.status_code)
        await db.commit()
        return
    except api4com.Api4ComIndisponivelError:
        # A conexão falhou antes de a requisição ser escrita: é a única
        # categoria em que se pode afirmar que não houve efeito externo.
        await telefonia.marca_indisponivel(db, tentativa)
        await db.commit()
        return
    except api4com.Api4ComDesligadaError:
        # A flag é conferida no início de `inicia_ligacao`; chegar aqui
        # significa que ela mudou no meio do caminho. Sem efeito externo.
        await telefonia.marca_indisponivel(db, tentativa)
        await db.commit()
        return
    except Exception:
        # ⚠️ Inclui `Api4ComResultadoIndeterminadoError` e QUALQUER surpresa.
        # A regra é conservadora de propósito: entramos na zona de efeito
        # externo, e o que não se sabe explicar não pode ser tratado como "não
        # aconteceu". Deixar a tentativa em `dispatching` seria pior — ela
        # ficaria parecendo uma execução em curso para sempre.
        await telefonia.marca_indeterminada(db, tentativa)
        await db.commit()
        return

    await telefonia.confirma(
        db,
        tentativa,
        provider_call_id=resultado.provider_call_id,
        provider_http_status=resultado.status_code,
    )
    await db.commit()


async def tentativas_do_chamado(db: AsyncSession, ticket_id: uuid.UUID) -> int:
    """Quantas tentativas o chamado já teve. Usado por teste e diagnóstico."""
    resultado = await db.execute(
        select(func.count()).select_from(TicketCall).where(TicketCall.ticket_id == ticket_id)
    )
    return int(resultado.scalar_one())
