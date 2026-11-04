"""
Chat em tempo real para tickets.

Endpoints REST:
  GET  /tickets/{ticket_id}/messages          — histórico paginado
  POST /tickets/{ticket_id}/messages          — criar mensagem (staff/sistema)
  POST /tickets/{ticket_id}/suggest-reply     — sugestão de resposta por IA (staff only)

WebSocket:
  WS   /ws/tickets/{ticket_id}?token=<jwt>    — canal de tempo real

Permissões:
  - Qualquer usuário autenticado com acesso ao ticket pode participar.
  - Acesso = requester do ticket OU qualquer admin/técnico.
"""

import base64
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from jose import JWTError
from loguru import logger
from sqlalchemy import func, literal, select, tuple_
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.websockets import WebSocketState

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.security import _is_blacklisted, authorize, decode_token, get_current_user
from app.models.models import (
    ChatMessage,
    LibraryFile,
    NotificationType,
    Ticket,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
)
from app.routers.tickets import _auto_transition
from app.schemas.chat import (
    LIMITE_CONTEUDO,
    ChatMessageCreate,
    ChatMessageListResponse,
    ChatMessageResponse,
    ConversationSummaryResponse,
    ImproveMessageRequest,
    ImproveMessageResponse,
    SuggestReplyResponse,
)
from app.services import chat_backplane, consentimento
from app.services.chat_sequencia import numera_mensagens_do_chat, perdeu_a_concorrencia
from app.services.helo import (
    FALAS_MAXIMAS,
    MOTIVO_PEDIU_HUMANO,
    MOTIVO_TRIAGEM_CONCLUIDA,
    TROCAS_MAXIMAS,
    FalaDaHelo,
    responde_triagem,
)
from app.services.llm import improve_message, suggest_reply, summarize_conversation
from app.services.notifications import audiencia_operacional, commit_e_notificar, notify
from app.utils.avatar import links_das_fotos, remetentes_com_foto
from app.utils.crud import get_or_404
from app.utils.library_access import ensure_pode_anexar_no_chat, visivel_para_cliente
from app.utils.sla import register_first_response
from app.utils.ticket_access import ensure_ticket_visible

router = APIRouter(tags=["Chat"])
settings = get_settings()

# Mesmo texto do 404 de id inexistente — ver `ensure_ticket_visible`. Vale
# também para o WebSocket, onde o vazamento sai como código de fechamento.
_CHAMADO_NAO_ENCONTRADO = "Ticket não encontrado. Ele pode ter sido excluído."


# ── ConnectionManager ─────────────────────────────────────────


class ConnectionManager:
    """Salas de WebSocket na memória DESTE processo, por chamado.

    A `origem` identifica este manager no backplane, e é atributo de
    **instância** — não global de módulo. Com um global, dois managers do mesmo
    processo dividiriam o carimbo, a supressão de eco descartaria a mensagem que
    deveria atravessar, e o backplane ficaria intestável exatamente na
    propriedade que o justifica.
    """

    def __init__(self) -> None:
        # ticket_id (str) → set of active WebSocket connections
        self._rooms: dict[str, set[WebSocket]] = {}
        # Quem é dono de cada socket. As salas são por chamado e o broadcast
        # não olha quem recebe; sem este índice não haveria como fechar os
        # chats de UMA pessoa — que é o que revogar o aceite da Política exige.
        self._por_usuario: dict[uuid.UUID, set[WebSocket]] = {}
        self.origem = uuid.uuid4().hex[:12]

    def connect(self, ticket_id: str, ws: WebSocket, user_id: uuid.UUID) -> None:
        self._rooms.setdefault(ticket_id, set()).add(ws)
        self._por_usuario.setdefault(user_id, set()).add(ws)

    def disconnect(self, ticket_id: str, ws: WebSocket, user_id: uuid.UUID) -> None:
        room = self._rooms.get(ticket_id)
        if room:
            room.discard(ws)
            if not room:
                del self._rooms[ticket_id]
        dele = self._por_usuario.get(user_id)
        if dele:
            dele.discard(ws)
            if not dele:
                del self._por_usuario[user_id]

    async def fecha_do_usuario(self, user_id: uuid.UUID, *, code: int, reason: str) -> int:
        """Fecha os sockets da pessoa NESTE processo; devolve quantos.

        Quem limpa as salas é o `finally` do handler de cada socket, quando o
        `receive` dele recebe o desconectar. Falha ao fechar um socket que já
        morreu não impede fechar os outros.

        ⚠️ Só este processo. Hoje há um worker (`start.sh`). Com vários, o
        socket da pessoa pode estar noutro processo, e fechá-lo exigiria uma
        mensagem de controle pelo backplane — não implementada.
        """
        fechados = 0
        for ws in list(self._por_usuario.get(user_id, ())):
            try:
                await ws.close(code=code, reason=reason)
                fechados += 1
            except Exception:  # noqa: BLE001 — socket já morto não é erro aqui
                pass
        return fechados

    async def entregar_local(self, ticket_id: str, payload: dict) -> None:
        """Entrega aos sockets deste processo, e só a eles.

        É também o que o backplane chama ao receber mensagem de outro worker —
        por isso é público e recebe o `ticket_id` como string: o assinante não
        sabe o que é uma sala, só repassa o que chegou.
        """
        room = self._rooms.get(ticket_id, set())
        dead: list[WebSocket] = []
        for ws in list(room):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            room.discard(ws)

    async def broadcast(self, ticket_id: str, payload: dict) -> None:
        """Entrega local PRIMEIRO, publica depois.

        A ordem não é estética: publicar antes faria a latência do Redis atrasar
        o socket que está no mesmo processo — o caso mais comum, ainda mais com
        um worker só. E `publicar` nunca levanta, então o Redis fora do ar deixa
        o chat exatamente como ele é hoje, que é sem Redis nenhum.
        """
        await self.entregar_local(ticket_id, payload)
        await chat_backplane.publicar(self.origem, ticket_id, payload)


manager = ConnectionManager()

# Fechamento por aceite da Política pendente. O código precisa chegar ao
# navegador, e por isso só é usado DEPOIS do `accept()`: fechar antes do
# handshake vira HTTP 403 no uvicorn e o navegador só vê 1006, sem código nem
# motivo (medido em 28/10/2026). O `ChatPanel` não reconecta com ele.
WS_ACEITE_POLITICA_PENDENTE = 4428
_MOTIVO_ACEITE_PENDENTE = "aceite_politica_pendente"


async def fecha_chats_do_usuario(user_id: uuid.UUID) -> int:
    """Fecha com 4428 os chats abertos da pessoa (quem revogou o aceite)."""
    return await manager.fecha_do_usuario(
        user_id, code=WS_ACEITE_POLITICA_PENDENTE, reason=_MOTIVO_ACEITE_PENDENTE
    )


async def _politica_pendente(db: AsyncSession, user: User) -> bool:
    situacao = await consentimento.situacao_do_aceite(
        db, user_id=user.id, role=user.role, settings=get_settings()
    )
    return situacao.politica_pendente


# ── Helpers ───────────────────────────────────────────────────


def _e_equipe(user: User) -> bool:
    return user.role in (UserRole.admin, UserRole.technician)


_SEM_ARQUIVO: dict = {
    "library_file_id": None,
    "library_file_name": None,
    "library_file_mime": None,
    "library_file_size": None,
    "library_file_unavailable": False,
}
_ARQUIVO_INDISPONIVEL: dict = {**_SEM_ARQUIVO, "library_file_unavailable": True}


def _arquivo_da_mensagem(msg: ChatMessage, *, ve_arquivo_interno: bool) -> dict:
    """Os campos do arquivo da biblioteca, como quem lê pode vê-los.

    O relacionamento TEM de vir carregado por quem consultou
    (`selectinload(ChatMessage.library_file)`). Tocar nele sem isso, numa
    sessão assíncrona, levanta `MissingGreenlet` — era o 500 que derrubava o
    histórico inteiro de qualquer conversa com um arquivo. Se um caminho novo
    esquecer o carregamento, a mensagem sai com o arquivo "indisponível" e o
    aviso vai para o log: um arquivo a menos na tela, e não a conversa toda.

    Cliente só vê o que está aberto para cliente. O arquivo pode ter voltado a
    ser interno depois de anexado; aí nome, tipo, tamanho e até o id ficam de
    fora, porque o próprio nome de um manual interno pode ser o segredo.
    """
    if msg.library_file_id is None:
        return _SEM_ARQUIVO
    if "library_file" in sa_inspect(msg).unloaded:
        logger.warning(f"Chat: mensagem {msg.id} serializada sem o arquivo da biblioteca carregado")
        return _ARQUIVO_INDISPONIVEL
    arquivo = msg.library_file
    if arquivo is None:
        return _ARQUIVO_INDISPONIVEL
    if not ve_arquivo_interno and not visivel_para_cliente(arquivo):
        return _ARQUIVO_INDISPONIVEL
    return {
        "library_file_id": arquivo.id,
        "library_file_name": arquivo.original_name,
        "library_file_mime": arquivo.mime_type,
        "library_file_size": arquivo.size_bytes,
        "library_file_unavailable": False,
    }


def _msg_to_response(
    msg: ChatMessage,
    sender_avatar_url: str | None = None,
    *,
    ve_arquivo_interno: bool = False,
) -> ChatMessageResponse:
    """`ve_arquivo_interno` nasce falso: esquecer de passá-lo esconde um
    arquivo da equipe, e não mostra um interno ao cliente."""
    sender = msg.sender
    return ChatMessageResponse(
        id=msg.id,
        ticket_id=msg.ticket_id,
        sender_id=msg.sender_id,
        content=msg.content,
        is_system=msg.is_system,
        is_ai=msg.is_ai,
        read_at=msg.read_at,
        created_at=msg.created_at,
        sender_name=sender.name if sender else "",
        sender_role=sender.role.value if sender else "",
        **_arquivo_da_mensagem(msg, ve_arquivo_interno=ve_arquivo_interno),
        sender_avatar_url=sender_avatar_url,
        client_message_id=msg.client_message_id,
        seq=msg.seq,
    )


async def _fotos_da_conversa(
    mensagens: list[ChatMessage], ticket: Ticket
) -> dict[uuid.UUID, str | None]:
    """O link da foto de cada MENSAGEM, assinado uma vez por remetente.

    A regra de quem pode aparecer é `foto_visivel_na_conversa`, a mesma para o
    histórico, o POST e o WebSocket — recarregar a tela não pode mostrar uma
    foto que o tempo real não mostrou, nem o contrário. Helô e sistema ficam
    sem foto mesmo quando a mensagem carrega o id de alguém.
    """
    links = await links_das_fotos(remetentes_com_foto(mensagens, ticket), settings)
    return {
        m.id: (None if m.is_ai or m.is_system or m.sender_id is None else links.get(m.sender_id))
        for m in mensagens
    }


async def _mensagem_com_remetente_atual(db: AsyncSession, msg_id: uuid.UUID) -> ChatMessage:
    """Relê a mensagem recém-gravada com o remetente como ele está no banco AGORA.

    `populate_existing` é o ponto: o remetente não vem do `user` que a conexão
    do WebSocket autenticou ao abrir. Quem revogou a foto com a sala aberta não
    pode continuar saindo com foto só porque o socket guardou um `User` de
    antes — e, sem a opção, o SQLAlchemy devolveria do mapa de identidade a
    cópia que outro passo da mesma sessão (a Helô lendo o criador, por exemplo)
    já tivesse carregado. É a consulta que já existia: nenhuma a mais.

    O arquivo da biblioteca vem junto, explícito: até aqui ele chegava ao
    `_msg_to_response` só porque o POST o deixara no mapa de identidade.
    """
    result = await db.execute(
        select(ChatMessage)
        .options(selectinload(ChatMessage.sender), selectinload(ChatMessage.library_file))
        .where(ChatMessage.id == msg_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


# ── Idempotência do envio (D4, F1-B-04a) ──────────────────────


_CHAVE_REUSADA = (
    "Este client_message_id já foi usado para outra mensagem neste chamado. "
    "Gere uma chave nova para cada mensagem nova."
)

# Deadlock ou falha de serialização no envio (F1-B-04c): o banco desfez tudo.
_ENVIO_NAO_GRAVADO = (
    "A mensagem não foi gravada: outra alteração no chamado aconteceu ao mesmo "
    "tempo. Envie de novo."
)


class _ChaveReusadaError(Exception):
    """A mesma chave de envio, da mesma pessoa, no mesmo chamado, com OUTRO
    conteúdo. Não é reenvio: é chave reaproveitada, e devolver a mensagem
    antiga como se fosse esta mentiria para quem enviou."""


def _impressao_do_envio(conteudo: str, library_file_id: uuid.UUID | None) -> str:
    """SHA-256 do que foi PEDIDO: o texto como é gravado e o arquivo.

    Só isto muda a mensagem gravada. Chamado e remetente já estão na chave do
    índice, e `is_ai`/`is_system` são sempre falsos para quem envia. O `v`
    deixa trocar a receita um dia sem que impressões antigas passem a bater
    por acaso com as novas.
    """
    canonico = json.dumps(
        {
            "v": 1,
            "content": conteudo,
            "library_file_id": str(library_file_id) if library_file_id else None,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


async def _envio_anterior(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    sender_id: uuid.UUID,
    chave: uuid.UUID | None,
    impressao: str | None,
) -> ChatMessage | None:
    """A mensagem que ESTA pessoa já gravou com esta chave NESTE chamado.

    O filtro por remetente e por chamado é o que impede a chave de virar
    consulta: quem conhece a chave de outra pessoa só encontra as próprias
    mensagens, e o chamado já passou por `_get_ticket_visivel`.
    """
    if chave is None:
        return None
    linha = (
        await db.execute(
            select(ChatMessage.id, ChatMessage.client_message_fingerprint).where(
                ChatMessage.ticket_id == ticket_id,
                ChatMessage.sender_id == sender_id,
                ChatMessage.client_message_id == chave,
            )
        )
    ).one_or_none()
    if linha is None:
        return None
    if linha.client_message_fingerprint != impressao:
        raise _ChaveReusadaError
    return await _mensagem_com_remetente_atual(db, linha.id)


async def _grava_uma_vez(db: AsyncSession, msg: ChatMessage) -> ChatMessage | None:
    """Grava `msg` JÁ, antes de qualquer efeito do envio. Devolve `None` quando
    gravou; a mensagem que já existia quando a chave chegou antes por outro
    caminho.

    O INSERT sai aqui, e não no commit, de propósito. Com ele feito, um reenvio
    simultâneo com a mesma chave PARA no índice único — o PostgreSQL o faz
    esperar a transação desta — antes de chamar a Helô, notificar ou mudar o
    status. Se esta comitar, ele recebe a violação e devolve esta mensagem; se
    esta desfizer, ele segue e grava. O índice decide, não a consulta prévia:
    dois reenvios simultâneos passam os dois por ela.

    O SAVEPOINT é para a violação não derrubar a transação inteira: sem ele, o
    PostgreSQL aborta tudo e a consulta seguinte, que busca a vencedora, morre
    com "current transaction is aborted".
    """
    ticket_id, sender_id = msg.ticket_id, msg.sender_id
    chave, impressao = msg.client_message_id, msg.client_message_fingerprint
    try:
        async with db.begin_nested():
            db.add(msg)
            await db.flush()
    except IntegrityError:
        # Sem remetente ou sem chave, ou sem a vencedora no banco: foi outra
        # regra (um arquivo excluído no meio do envio, por exemplo), não reenvio.
        if sender_id is None:
            raise
        anterior = await _envio_anterior(db, ticket_id, sender_id, chave, impressao)
        if anterior is None:
            raise
        return anterior
    return None


async def _get_ticket_visivel(
    ticket_id: uuid.UUID,
    actor: User,
    db: AsyncSession,
) -> Ticket:
    """
    Devolve o chamado se o ator puder vê-lo; senão, 404.

    Chamado alheio responde igual a id inexistente — o 403 anterior confirmava
    a existência. Staff passa direto porque já lê o sistema inteiro.
    """
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_CHAMADO_NAO_ENCONTRADO,
        )

    if actor.role not in (UserRole.admin, UserRole.technician):
        ensure_ticket_visible(ticket, actor, _CHAMADO_NAO_ENCONTRADO)

    return ticket


async def _authenticate_ws(token: str, db: AsyncSession) -> User | None:
    """Valida o token vindo do query param do WebSocket.

    Confere a blacklist, como o `get_current_user` do caminho HTTP. Sem isso o
    logout derrubava a sessão HTTP e deixava o WebSocket aberto: o token
    revogado continuava valendo aqui até vencer sozinho — até oito horas depois
    de a pessoa ter saído.
    """
    try:
        payload = decode_token(token)
    except JWTError:
        return None

    if payload.get("type") != "access":
        return None

    if await _is_blacklisted(token):
        return None

    user_id_str = payload.get("sub")
    if not user_id_str:
        return None

    try:
        uid = uuid.UUID(user_id_str)
    except ValueError:
        return None

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user is None or user.status != UserStatus.active:
        return None
    return user


# Quantas mensagens da conversa vão para a sugestão de resposta.
#
# Eram 10 fixos, e 10 bastava enquanto a Helô falava uma vez por chamado: a
# conversa inteira de um chamado triado tinha três mensagens. Com o teto de
# trocas, ela chega a 13 — a saudação mais seis idas e voltas —, e uma janela
# de 10 passa a cortar JUSTO O COMEÇO. O que fica de fora é a resposta do
# cliente às três perguntas da triagem, que é a mensagem mais útil que existe
# para sugerir uma resposta: o técnico receberia a sugestão feita a partir do
# meio da conversa, sem o sintoma.
#
# Por isso o número sai das constantes e não de um novo palpite: a janela tem
# que caber uma triagem inteira, e quem mudar o teto de trocas move as duas
# coisas juntas. Conversa longa DEPOIS da triagem continua saindo da janela, e
# isso é o certo — ali o contexto recente é o que vale.
_JANELA_DO_HISTORICO = FALAS_MAXIMAS + TROCAS_MAXIMAS


def _exige_ia_no_chamado(ticket: Ticket) -> None:
    """
    Recusa quando a IA foi desligada NESTE chamado.

    O guard acima é a chave geral; este é o botão do técnico. Sem ele, "Desligar
    IA neste chamado" calaria só a Helô e deixaria a sugestão de resposta e o
    resumo funcionando — a promessa da tela maior que a do código, que é
    exatamente o que o rótulo do botão não pode fazer.

    Não é dependência como o outro porque precisa do chamado carregado: só dá
    para saber depois de ler o banco, e o 404 de chamado alheio tem precedência.

    409, e não 403: não é falta de permissão, é um estado do chamado que alguém
    da equipe escolheu e qualquer um deles pode desfazer no mesmo botão.
    """
    if not ticket.ai_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A IA está desligada neste chamado.",
        )


def _exige_ia_ligada() -> None:
    """Recusa a chamada quando a IA está desligada — antes de tocar no banco.

    A mensagem é **diferente** da de provedor fora do ar, de propósito. Os três
    endpoints devolviam o mesmo "tente novamente mais tarde" nos dois casos, e
    com a flag desligada isso manda esperar por algo que não volta sozinho. Quem
    opera precisa distinguir "o provedor caiu" de "alguém desligou".

    Sendo dependência, roda antes do corpo do handler: com a IA desligada não há
    por que carregar chamado e mensagens do banco para no fim recusar.

    Lê a configuração na chamada, não no import — o `llm.py` faz o contrário, e
    por isso lá a flag só tem efeito depois de reiniciar o contêiner.
    """
    if not get_settings().llm_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O assistente de IA está desligado neste ambiente.",
        )


# ── REST endpoints ────────────────────────────────────────────


_CURSOR_INVALIDO = "Cursor de paginação inválido. Peça a página de novo, sem `before`."
_PAGINA_PADRAO = 100
_PAGINA_PADRAO_LEGADA = 50


def _codifica_cursor(msg: ChatMessage) -> str:
    """O ponto exato de uma mensagem: chamado, `created_at` e `id`.

    Opaco para quem consome, mas não secreto nem assinado: alterá-lo só
    desloca a janela DENTRO do chamado já autorizado, porque a consulta filtra
    pelo chamado da URL de qualquer jeito. O `tk` existe para que um cursor
    trocado de chamado seja recusado, em vez de virar uma página silenciosa no
    lugar errado.
    """
    bruto = json.dumps(
        {"tk": str(msg.ticket_id), "t": msg.created_at.isoformat(), "id": str(msg.id)},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(bruto.encode()).decode().rstrip("=")


def _decodifica_cursor(cursor: str, ticket_id: uuid.UUID) -> tuple[datetime, uuid.UUID]:
    """O inverso de `_codifica_cursor`; qualquer coisa fora do formato é 422."""
    try:
        dados = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        if not isinstance(dados, dict):
            raise ValueError("cursor não é objeto")
        chamado = uuid.UUID(dados["tk"])
        instante = datetime.fromisoformat(dados["t"])
        mensagem = uuid.UUID(dados["id"])
    except (ValueError, KeyError, TypeError, AttributeError):
        # `binascii.Error`, `UnicodeDecodeError` e `JSONDecodeError` são
        # todos `ValueError`.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=_CURSOR_INVALIDO
        ) from None
    # Sem fuso, a comparação com `timestamptz` dependeria do fuso da sessão do
    # banco. O cursor que este módulo emite sempre tem.
    if instante.tzinfo is None or chamado != ticket_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=_CURSOR_INVALIDO
        )
    return instante, mensagem


@router.get("/tickets/{ticket_id}/messages", response_model=ChatMessageListResponse)
async def list_messages(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    limit: int | None = Query(default=None, ge=1, le=100),
    offset: int | None = Query(default=None, ge=0),
    before: str | None = Query(default=None, max_length=512),
    after_seq: int | None = Query(default=None, ge=0),
) -> ChatMessageListResponse:
    """Histórico da conversa, sempre em ordem cronológica no corpo.

    **Por cursor (padrão):** sem `offset`, devolve as `limit` (100) mensagens
    MAIS RECENTES; com `before`, as imediatamente anteriores ao cursor. A
    ordem é `(created_at, id)`: o `id` desempata mensagens do mesmo instante,
    e é isso que impede repetir ou pular uma mensagem na fronteira entre
    páginas.

    **Legado por `offset`:** com `offset` presente — mesmo `offset=0` —, o
    contrato antigo: do começo da conversa, 50 por página. Antes, sem
    parâmetro nenhum, este endpoint também lia do começo, e a tela pedia 100
    e mostrava as 100 MAIS ANTIGAS (FUN-30). Quem precisa da ordem antiga diz
    `offset` e continua tendo.

    ⚠️ `created_at` é carimbado antes do commit. Uma mensagem pode ficar
    visível depois de outra mais "nova", e então cair atrás de um cursor já
    usado: voltar com `before` não a traz. Quem a entrega é o WebSocket, ou
    reler a página mais recente — ver `test_chat_historico_postgres.py` —, ou
    o modo incremental abaixo.

    **Incremental por `after_seq` (F1-B-04c):** as mensagens com
    `seq > after_seq`, em ordem CRESCENTE de `seq` — a ordem de commit, não a
    de `created_at`. `has_more` diz que há mais depois da última, e
    `next_after_seq` é de onde continuar. Sozinho: com `before` ou `offset` é
    422. `after_seq` maior que o contador do chamado é 409 `ressincronizar` —
    o contador voltou (backup restaurado, numeração recriada) e a âncora de
    quem pediu não vale mais. Mensagem sem número (anterior à numeração)
    nunca volta por aqui: está no histórico por cursor. Um salto entre dois
    números não é erro: a mensagem pode ter sido removida por quem tem
    direito de remover.

    Toda resposta traz `ultima_seq`, lido ANTES das mensagens: tudo até ele
    já estava comitado, então uma página sem `after_seq` seguida de
    `after_seq=ultima_seq` não perde nada que comitar entre as duas.
    """
    if offset is not None and before is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Use `before` ou `offset`, não os dois.",
        )
    if after_seq is not None and (offset is not None or before is not None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Use `after_seq` sozinho, sem `before` nem `offset`.",
        )

    # A autorização vem ANTES de olhar o cursor: chamado alheio responde o
    # mesmo 404 com cursor válido, inválido ou sem cursor nenhum.
    ticket = await _get_ticket_visivel(ticket_id, actor, db)
    ponto = _decodifica_cursor(before, ticket_id) if before is not None else None

    # ANTES das mensagens, num comando à parte. Em READ COMMITTED cada comando
    # vê o banco do seu próprio instante; lido depois, o contador poderia
    # incluir um commit que a página não viu, e a âncora pularia a mensagem.
    ultima_seq = await _ultima_seq(db, ticket_id)
    if after_seq is not None and after_seq > ultima_seq:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ressincronizar",
                "detail": "A conversa foi renumerada. Recarregue o histórico.",
                "ultima_seq": ultima_seq,
            },
        )

    total_result = await db.execute(select(func.count()).where(ChatMessage.ticket_id == ticket_id))
    total = total_result.scalar_one()

    # O arquivo da biblioteca vem carregado, explícito — ver `_arquivo_da_mensagem`.
    consulta = (
        select(ChatMessage)
        .options(selectinload(ChatMessage.sender), selectinload(ChatMessage.library_file))
        .where(ChatMessage.ticket_id == ticket_id)
    )

    next_after_seq = None
    if after_seq is not None:
        limite = limit or _PAGINA_PADRAO
        # Teto em `ultima_seq`: o que comitou depois da leitura do contador
        # fica para a próxima página, e `next_after_seq` não passa por cima.
        rows = await db.execute(
            consulta.where(ChatMessage.seq > after_seq, ChatMessage.seq <= ultima_seq)
            .order_by(ChatMessage.seq.asc())
            .limit(limite + 1)
        )
        lote = list(rows.scalars().all())
        has_more = len(lote) > limite
        messages = lote[:limite]
        next_after_seq = messages[-1].seq if has_more else ultima_seq
        next_before = None
    elif offset is not None:
        limite = limit or _PAGINA_PADRAO_LEGADA
        rows = await db.execute(
            consulta.order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
            .offset(offset)
            .limit(limite)
        )
        messages = list(rows.scalars().all())
        has_more = offset + len(messages) < total
        next_before = None
    else:
        limite = limit or _PAGINA_PADRAO
        if ponto is not None:
            instante, mensagem = ponto
            # Comparação de linha do Postgres: `(created_at, id) < (t, id)` é
            # exatamente "vem antes na ordem da conversa", empate incluído.
            consulta = consulta.where(
                tuple_(ChatMessage.created_at, ChatMessage.id)
                < tuple_(
                    literal(instante, ChatMessage.created_at.type),
                    literal(mensagem, ChatMessage.id.type),
                )
            )
        # Uma a mais só para saber se há página anterior, sem outro COUNT.
        rows = await db.execute(
            consulta.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(
                limite + 1
            )
        )
        lote = list(rows.scalars().all())
        has_more = len(lote) > limite
        messages = list(reversed(lote[:limite]))
        next_before = _codifica_cursor(messages[0]) if has_more else None

    # Os remetentes já vieram no `selectinload` acima: a foto não custa uma
    # consulta por mensagem, só uma assinatura por pessoa.
    fotos = await _fotos_da_conversa(messages, ticket)
    ve_interno = _e_equipe(actor)

    return ChatMessageListResponse(
        items=[
            _msg_to_response(m, fotos.get(m.id), ve_arquivo_interno=ve_interno) for m in messages
        ],
        total=total,
        limit=limite,
        offset=offset or 0,
        has_more=has_more,
        next_before=next_before,
        ultima_seq=ultima_seq,
        next_after_seq=next_after_seq,
    )


async def _ultima_seq(db: AsyncSession, ticket_id: uuid.UUID) -> int:
    """O contador do chamado como está comitado agora. Função à parte para o
    teste poder comitar uma mensagem entre esta leitura e a da página."""
    valor = (await db.execute(select(Ticket.chat_seq).where(Ticket.id == ticket_id))).scalar_one()
    return int(valor)


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    ticket_id: uuid.UUID,
    payload: ChatMessageCreate,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> ChatMessageResponse:
    ticket = await _get_ticket_visivel(ticket_id, actor, db)
    ve_arquivo_interno = _e_equipe(actor)

    # O reenvio vem ANTES da conferência do arquivo: o que já foi aceito
    # devolve o que foi gravado, mesmo que o arquivo tenha virado interno
    # depois — a resposta o esconde de quem não pode vê-lo, como no histórico.
    conteudo = payload.content.strip()
    chave = payload.client_message_id
    impressao = _impressao_do_envio(conteudo, payload.library_file_id) if chave else None
    try:
        anterior = await _envio_anterior(db, ticket_id, actor.id, chave, impressao)
    except _ChaveReusadaError:
        raise HTTPException(status.HTTP_409_CONFLICT, _CHAVE_REUSADA) from None
    if anterior is not None:
        return await _repeticao(anterior, ticket, response, ve_arquivo_interno=ve_arquivo_interno)

    # Antes de gravar qualquer coisa: item interno nao entra em conversa. A
    # recusa e da API, e nao da tela -- a API e chamada por outros clientes
    # alem dela, e uma tela desatualizada bastaria para vazar.
    arquivo = None
    if payload.library_file_id is not None:
        arquivo = await get_or_404(
            db, LibraryFile, payload.library_file_id, "Arquivo nao encontrado na biblioteca."
        )
        ensure_pode_anexar_no_chat(arquivo)

    now = datetime.now(UTC)
    msg = ChatMessage(
        id=uuid.uuid4(),
        ticket_id=ticket_id,
        sender_id=actor.id,
        content=conteudo,
        is_system=False,
        is_ai=False,
        library_file_id=payload.library_file_id,
        created_at=now,
        client_message_id=chave,
        client_message_fingerprint=impressao,
    )
    # Evita um SELECT a mais na serializacao: o objeto ja esta em maos.
    if arquivo is not None:
        msg.library_file = arquivo
    # Gravada antes da Helô, da notificação e do status: um reenvio
    # simultâneo para no índice aqui e não repete nenhum deles.
    try:
        anterior = await _grava_uma_vez(db, msg)
    except _ChaveReusadaError:
        raise HTTPException(status.HTTP_409_CONFLICT, _CHAVE_REUSADA) from None
    if anterior is not None:
        return await _repeticao(anterior, ticket, response, ve_arquivo_interno=ve_arquivo_interno)

    try:
        # SLA: falar com o cliente é o que conta como primeira resposta
        register_first_response(
            ticket, now, responder_id=actor.id, is_ai=msg.is_ai, is_system=msg.is_system
        )

        # A Helô responde quando o cliente escreve. ANTES da notificação de
        # propósito: é ela quem decide se a equipe precisa ser chamada, e um
        # chamado que ela acabou de escalar é justamente o que precisa chegar à
        # equipe com o aviso certo — e ainda não tem dono.
        fala_da_helo = None
        if actor.id == ticket.creator_id:
            fala_da_helo = await _fala_da_helo_sem_derrubar(db, ticket, actor, msg.content)

        # Notify the other party
        await _notify_other_party(db, ticket, actor, msg)

        # SÓ na escalada. Ela fala a cada turno agora, e avisar a equipe a cada
        # fala mandaria seis notificações por chamado para todo técnico e
        # todo admin — cinco delas dizendo que a triagem acabou enquanto a
        # conversa seguia. Notificação que chega sempre deixa de ser lida.
        # `motivo is not None` em vez de `.escalou`: a guarda e o argumento passam
        # a olhar o MESMO campo. `escalou` é property, e property não estreita
        # tipo — o mypy via `str | None` chegando onde se espera `str`, e estava
        # certo: a property pode divergir do campo num refactor, o `is not None`
        # não pode.
        if fala_da_helo is not None and fala_da_helo.motivo is not None:
            await _avisa_equipe_da_helo(db, ticket, motivo=fala_da_helo.motivo)

        # Auto status transition based on who is sending
        new_status_value = await _apply_chat_transition(db, ticket, actor)

        # O ÚLTIMO bloqueio do envio, e só depois da Helô: ver a ordem dos
        # bloqueios em `app/services/chat_sequencia.py`.
        await numera_mensagens_do_chat(db)
        await commit_e_notificar(db)
    except DBAPIError as exc:
        if not perdeu_a_concorrencia(exc):
            raise
        # Deadlock ou serialização: o banco desfez a transação INTEIRA — a
        # mensagem, o aviso, o status. Nada é repetido aqui: repetir chamaria
        # a Helô de novo. A resposta diz que não gravou, e quem enviou reenvia.
        await db.rollback()
        logger.warning(f"Chat: envio no chamado {ticket_id} perdeu a concorrência ({exc.orig})")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            _ENVIO_NAO_GRAVADO,
            headers={"Retry-After": "1"},
        ) from None

    # A mesma releitura do WebSocket: o remetente sai do banco, não do `actor`
    # que o `get_current_user` carregou no início da requisição.
    msg = await _mensagem_com_remetente_atual(db, msg.id)

    fotos = await _fotos_da_conversa([msg], ticket)
    resposta = _msg_to_response(msg, fotos.get(msg.id), ve_arquivo_interno=ve_arquivo_interno)

    # O quadro vai igual para a sala inteira, e na sala pode haver cliente:
    # ele é montado com o olhar do cliente. Não esconde nada da equipe na
    # prática — só entra em conversa o arquivo aberto para cliente
    # (`ensure_pode_anexar_no_chat`, acima).
    quadro = _msg_to_response(msg, fotos.get(msg.id))
    await manager.broadcast(
        str(ticket_id),
        {"type": "message", "data": _response_to_dict(quadro)},
    )

    # Broadcast status change if a transition occurred
    if new_status_value:
        await manager.broadcast(
            str(ticket_id),
            {"type": "status_update", "data": {"status": new_status_value}},
        )

    return resposta


async def _repeticao(
    anterior: ChatMessage, ticket: Ticket, response: Response, *, ve_arquivo_interno: bool
) -> ChatMessageResponse:
    """O reenvio de uma mensagem já gravada: 200 em vez de 201, e só isso.

    Nada de sala, nem de Helô, nem de aviso, nem de status: tudo isso já
    aconteceu com a original. Transmitir de novo mostraria a mensagem duas
    vezes a quem já a recebeu; quem a perdeu a acha no histórico.
    """
    response.status_code = status.HTTP_200_OK
    logger.info(f"Chat: reenvio da mensagem {anterior.id} devolvido sem gravar de novo")
    fotos = await _fotos_da_conversa([anterior], ticket)
    return _msg_to_response(anterior, fotos.get(anterior.id), ve_arquivo_interno=ve_arquivo_interno)


@router.post(
    "/tickets/{ticket_id}/suggest-reply",
    response_model=SuggestReplyResponse,
    dependencies=[Depends(_exige_ia_ligada)],
)
async def suggest_ticket_reply(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> SuggestReplyResponse:
    """Generate an AI-suggested reply for a technician based on ticket and chat history."""
    ticket = await _get_ticket_visivel(ticket_id, actor, db)
    _exige_ia_no_chamado(ticket)

    rows = await db.execute(
        select(ChatMessage)
        .options(selectinload(ChatMessage.sender))
        .where(ChatMessage.ticket_id == ticket_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(_JANELA_DO_HISTORICO)
    )
    messages = list(reversed(rows.scalars().all()))

    history = [
        {
            "sender": m.sender.name if m.sender else "Sistema",
            "role": m.sender.role.value if m.sender else "system",
            "content": m.content,
        }
        for m in messages
    ]

    suggestion = await suggest_reply(
        title=ticket.title,
        description=ticket.description,
        category=(
            ticket.category.value if hasattr(ticket.category, "value") else str(ticket.category)
        ),
        # Chamado ainda não triado não tem prioridade, e o que ia para o prompt
        # era a string "None" — a LLM lendo "Prioridade: None" como se fosse um
        # nível. "sem prioridade definida" diz a verdade, em português.
        priority=(
            "sem prioridade definida"
            if ticket.priority is None
            else (
                ticket.priority.value if hasattr(ticket.priority, "value") else str(ticket.priority)
            )
        ),
        status=ticket.status.value if hasattr(ticket.status, "value") else str(ticket.status),
        history=history,
    )

    if suggestion is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O assistente de IA está indisponível no momento. Tente novamente mais tarde.",
        )

    return SuggestReplyResponse(suggestion=suggestion)


@router.post(
    "/tickets/{ticket_id}/improve-message",
    response_model=ImproveMessageResponse,
    dependencies=[Depends(_exige_ia_ligada)],
)
async def improve_ticket_message(
    ticket_id: uuid.UUID,
    body: ImproveMessageRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> ImproveMessageResponse:
    """Improve a technician's draft message using AI (grammar, clarity, professionalism)."""
    ticket = await _get_ticket_visivel(ticket_id, actor, db)
    _exige_ia_no_chamado(ticket)

    result = await improve_message(
        draft=body.draft,
        title=ticket.title,
        description=ticket.description,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O assistente de IA está indisponível no momento. Tente novamente mais tarde.",
        )

    return ImproveMessageResponse(improved=result)


@router.post(
    "/tickets/{ticket_id}/summarize",
    response_model=ConversationSummaryResponse,
    dependencies=[Depends(_exige_ia_ligada)],
)
async def summarize_ticket_conversation(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> ConversationSummaryResponse:
    """
    Generate an AI summary of the full ticket conversation and persist it in the ticket.
    Returns the summary text. Subsequent calls regenerate and overwrite the stored summary.
    """
    ticket = await _get_ticket_visivel(ticket_id, actor, db)
    _exige_ia_no_chamado(ticket)

    # Load all messages (up to 200 to keep context manageable)
    rows = await db.execute(
        select(ChatMessage)
        .options(selectinload(ChatMessage.sender))
        .where(ChatMessage.ticket_id == ticket_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(200)
    )
    messages = rows.scalars().all()

    if not messages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ainda não há mensagens nesta conversa para resumir.",
        )

    history = [
        {
            "sender": m.sender.name if m.sender else "Sistema",
            "role": m.sender.role.value if m.sender else "system",
            "content": m.content,
        }
        for m in messages
    ]

    summary = await summarize_conversation(
        title=ticket.title,
        category=(
            ticket.category.value if hasattr(ticket.category, "value") else str(ticket.category)
        ),
        status=ticket.status.value if hasattr(ticket.status, "value") else str(ticket.status),
        history=history,
    )

    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O assistente de IA está indisponível no momento. Tente novamente mais tarde.",
        )

    # Persist summary in the ticket
    ticket.ai_conversation_summary = summary
    ticket.updated_at = datetime.now(UTC)
    await commit_e_notificar(db)

    return ConversationSummaryResponse(summary=summary)


# ── WebSocket endpoint ────────────────────────────────────────


@router.websocket("/ws/tickets/{ticket_id}")
async def websocket_chat(
    websocket: WebSocket,
    ticket_id: uuid.UUID,
    token: str = Query(...),
) -> None:
    """
    WebSocket chat room for a ticket.

    Query params:
      token — JWT access token (browser WebSocket API doesn't support headers)
    """
    # Todo fechamento de recusa — 4001, 4428 e 4004 — vem DEPOIS do `accept()`.
    # Fechado antes do handshake, o uvicorn responde HTTP 403 e o navegador só
    # vê 1006, sem código nem motivo (medido em 28/10/2026): o 4001 e o 4004
    # nunca chegavam, e a tela tratava a recusa como queda de rede e
    # reconectava a cada 3 s, para sempre. Aceitar e fechar em seguida não
    # entrega nada a quem foi recusado: nenhum quadro sai antes do fechamento.
    async with AsyncSessionLocal() as db:
        user = await _authenticate_ws(token, db)
        if user is None:
            await websocket.accept()
            await websocket.close(code=4001, reason="Unauthorized")
            return

        # Aceite da Política pendente (ver `WS_ACEITE_POLITICA_PENDENTE`). Sem
        # mensagem de erro antes: o código basta.
        if await _politica_pendente(db, user):
            await websocket.accept()
            await websocket.close(code=WS_ACEITE_POLITICA_PENDENTE, reason=_MOTIVO_ACEITE_PENDENTE)
            return

        # A MESMA regra do REST (`_get_ticket_visivel`), em vez de uma cópia
        # dela aqui: chamado inexistente e chamado alheio fecham IGUAL — mesmo
        # código, mesmo motivo. O 4003 ("Forbidden") de antes dizia que o
        # chamado existe, e quem tivesse uma lista de ids enumerava o sistema
        # pelo WebSocket sem nunca receber um HTTP 403.
        try:
            await _get_ticket_visivel(ticket_id, user, db)
        except HTTPException:
            await websocket.accept()
            await websocket.close(code=4004, reason="Ticket not found")
            return

    await websocket.accept()
    tid_str = str(ticket_id)
    manager.connect(tid_str, websocket, user.id)
    logger.info(f"WS connected: user={user.id} ticket={ticket_id}")

    try:
        # Enquanto o socket estiver de pé do lado do servidor. Quem revoga o
        # aceite tem o socket fechado por outro pedido (`fecha_chats_do_usuario`);
        # se isso acontecer no meio do processamento de uma mensagem, o
        # `receive_text` seguinte levantaria RuntimeError em vez de desconectar.
        while websocket.application_state == WebSocketState.CONNECTED:
            raw = await websocket.receive_text()

            # O aceite é conferido de novo a cada mensagem recebida, antes de
            # qualquer outra coisa. Sozinho isto não basta — o socket parado só
            # recebe, e o broadcast não olha quem é o destinatário; por isso
            # revogar também fecha os chats da pessoa.
            async with AsyncSessionLocal() as db:
                if await _politica_pendente(db, user):
                    await websocket.close(
                        code=WS_ACEITE_POLITICA_PENDENTE, reason=_MOTIVO_ACEITE_PENDENTE
                    )
                    break
            try:
                data = json.loads(raw)
                content = str(data.get("content", "")).strip()
            except (json.JSONDecodeError, AttributeError):
                await websocket.send_json({"type": "error", "detail": "Invalid JSON"})
                continue

            # A chave de envio (D4) é opcional, como no POST. Inválida, a
            # mensagem é recusada inteira: gravar sem a chave que veio
            # transformaria o próximo reenvio numa duplicata.
            try:
                chave = _chave_do_quadro(data.get("client_message_id"))
            except ValueError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "detail": "client_message_id inválido: mande um UUID em texto, ou nada.",
                    }
                )
                continue

            # Anexo da biblioteca NÃO passa por aqui, e a recusa é ALTA.
            #
            # Este laço lê `content` e descarta o resto do payload. Um
            # `library_file_id` mandado pelo socket sumia em silêncio: a
            # mensagem era gravada sem o anexo, o cliente não recebia arquivo
            # nenhum e nada dizia por quê. E a mensagem que só tivesse anexo,
            # sem texto, caía no `if not content` logo abaixo e não existia —
            # sem erro, sem linha, sem nada para diagnosticar depois.
            #
            # Esta guarda **não liga** anexo no socket: liga o aviso. Quem um
            # dia quiser anexo por este caminho precisa trazer para cá o
            # `ensure_pode_anexar_no_chat`, que é a conferência de visibilidade
            # e hoje mora no REST — e é ela que decide, antes de gravar, se um
            # item interno pode entrar numa conversa que o cliente lê.
            #
            # Por isso a recusa diz PARA ONDE IR, em vez de só dizer "não":
            # quem integra por fora da tela não tem como saber que o recurso
            # existe noutro endereço.
            #
            # Vem ANTES do `if not content` de propósito. Depois dele, o caso
            # pior — só anexo, sem texto — continuaria sumindo calado, que é
            # justamente o que se está consertando.
            if data.get("library_file_id") is not None:
                await websocket.send_json(
                    _quadro_de_erro(
                        "Este canal não aceita anexo da biblioteca. Envie a "
                        "mensagem por POST /tickets/{id}/messages, que confere "
                        "a visibilidade do arquivo antes de gravar.",
                        chave,
                    )
                )
                continue

            if not content:
                continue

            # O mesmo teto do schema REST. Aqui é preciso conferir à mão porque
            # este caminho não passa por Pydantic nenhum — e é justamente por
            # isso que ele seria o escolhido por quem quisesse abusar.
            if len(content) > LIMITE_CONTEUDO:
                await websocket.send_json(
                    _quadro_de_erro(
                        f"Mensagem longa demais (máximo {LIMITE_CONTEUDO} caracteres). "
                        "Para textos maiores, use um anexo.",
                        chave,
                    )
                )
                continue

            async with AsyncSessionLocal() as db:
                ticket_res = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
                ticket = ticket_res.scalar_one_or_none()
                if ticket is None:
                    # Excluído com a sala aberta: o mesmo 4004 da entrada, para
                    # a tela parar de tentar em vez de ver uma queda comum.
                    await websocket.close(code=4004, reason="Ticket not found")
                    break

                impressao = _impressao_do_envio(content, None) if chave else None
                now = datetime.now(UTC)
                msg = ChatMessage(
                    id=uuid.uuid4(),
                    ticket_id=ticket_id,
                    sender_id=user.id,
                    content=content,
                    is_system=False,
                    is_ai=False,
                    created_at=now,
                    client_message_id=chave,
                    client_message_fingerprint=impressao,
                )
                # Igual ao POST: a repetição é conferida antes de gravar, e a
                # gravação sai antes de qualquer efeito, para que um reenvio
                # simultâneo — por aqui ou pelo POST — pare no índice único.
                try:
                    anterior = await _envio_anterior(db, ticket_id, user.id, chave, impressao)
                    if anterior is None:
                        anterior = await _grava_uma_vez(db, msg)
                except _ChaveReusadaError:
                    await websocket.send_json(
                        _quadro_de_erro(_CHAVE_REUSADA, chave, code="client_message_id_conflict")
                    )
                    continue
                if anterior is not None and chave is not None:
                    # Só para este socket: a sala já recebeu a original. (Sem
                    # chave não há anterior; o `chave is not None` é para o tipo.)
                    foto = (await _fotos_da_conversa([anterior], ticket)).get(anterior.id)
                    await websocket.send_json(
                        _confirmacao(_msg_to_response(anterior, foto), chave, repetida=True)
                    )
                    continue

                try:
                    register_first_response(
                        ticket, now, responder_id=user.id, is_ai=msg.is_ai, is_system=msg.is_system
                    )

                    await _notify_other_party(db, ticket, user, msg)

                    # O chat do front conversa por WebSocket, entao ESTE e o
                    # caminho pelo qual a resposta do cliente chega de verdade. O
                    # POST existe, mas fica de reserva -- ligar a Helo so la a
                    # deixaria muda na tela onde ela aparece.
                    fala_da_helo = None
                    if user.id == ticket.creator_id:
                        fala_da_helo = await _fala_da_helo_sem_derrubar(
                            db, ticket, user, msg.content
                        )
                        # Só na escalada — ver o mesmo trecho no caminho do POST.
                        if fala_da_helo is not None and fala_da_helo.motivo is not None:
                            await _avisa_equipe_da_helo(db, ticket, motivo=fala_da_helo.motivo)

                    new_status_value = await _apply_chat_transition(db, ticket, user)

                    # O ÚLTIMO bloqueio do envio — ver o POST acima.
                    await numera_mensagens_do_chat(db)
                    await commit_e_notificar(db)
                except DBAPIError as exc:
                    if not perdeu_a_concorrencia(exc):
                        raise
                    # Igual ao POST: nada gravado, nada repetido. A chave volta no
                    # erro, e a tela sabe QUAL envio não entrou; o socket segue.
                    await db.rollback()
                    logger.warning(
                        f"Chat: envio no chamado {ticket_id} perdeu a concorrência ({exc.orig})"
                    )
                    await websocket.send_json(
                        _quadro_de_erro(_ENVIO_NAO_GRAVADO, chave, code="envio_nao_gravado")
                    )
                    continue

                msg = await _mensagem_com_remetente_atual(db, msg.id)
                # A foto também sai aqui dentro, com o remetente carregado. O
                # payload vai igual para toda a sala, e é por isso que a regra
                # não olha quem recebe — ver `foto_visivel_na_conversa`.
                foto_do_remetente = (await _fotos_da_conversa([msg], ticket)).get(msg.id)

                # O payload dela é montado AQUI DENTRO, com a sessão ainda
                # aberta. Montá-lo depois do `async with` significa mexer num
                # objeto desanexado, e `_msg_to_response` toca em `msg.sender`:
                # a exceção sobe, mata o laço do WebSocket e a fala dela nunca
                # é transmitida. Ela fica gravada, e só aparece num F5 — que
                # foi exatamente o sintoma relatado.
                dados_da_helo = (
                    _response_to_dict(_msg_to_response(fala_da_helo.mensagem))
                    if fala_da_helo is not None
                    else None
                )

            response = _msg_to_response(msg, foto_do_remetente)
            await manager.broadcast(
                tid_str,
                {"type": "message", "data": _response_to_dict(response)},
            )
            # A fala dela vai num broadcast proprio, DEPOIS da do cliente: e a
            # ordem em que a conversa aconteceu, e e a ordem em que a tela
            # precisa mostrar.
            if dados_da_helo is not None:
                await manager.broadcast(tid_str, {"type": "message", "data": dados_da_helo})
            if new_status_value:
                await manager.broadcast(
                    tid_str,
                    {"type": "status_update", "data": {"status": new_status_value}},
                )
            # A confirmação vai depois da sala: quem a recebe já tem tudo o que
            # o envio produziu. Sem chave, nada muda para o cliente antigo.
            if chave is not None:
                await websocket.send_json(_confirmacao(response, chave, repetida=False))

    except WebSocketDisconnect:
        logger.info(f"WS disconnected: user={user.id} ticket={ticket_id}")
    finally:
        manager.disconnect(tid_str, websocket, user.id)


# ── Internal helpers ──────────────────────────────────────────


def _chave_do_quadro(bruta: object) -> uuid.UUID | None:
    """A `client_message_id` de um quadro do WebSocket. Ausente ou nula é
    "sem chave"; qualquer outra coisa que não seja UUID em texto é ValueError.
    Aqui não há Pydantic, e `uuid.UUID(123)` não falha com ValueError."""
    if bruta is None:
        return None
    if not isinstance(bruta, str):
        raise ValueError("client_message_id não é texto")
    return uuid.UUID(bruta)


def _quadro_de_erro(detalhe: str, chave: uuid.UUID | None, **extra: str) -> dict:
    """O erro, com a chave do envio quando havia uma: é por ela que a tela
    sabe QUAL rascunho falhou."""
    quadro: dict = {"type": "error", "detail": detalhe, **extra}
    if chave is not None:
        quadro["client_message_id"] = str(chave)
    return quadro


def _confirmacao(r: ChatMessageResponse, chave: uuid.UUID, *, repetida: bool) -> dict:
    """Só para quem enviou com chave: a mensagem gravada, inteira.

    `duplicate` diz se este envio gravou (falso) ou se a chave já tinha sido
    gravada antes (verdadeiro). A mensagem vem junto nos dois casos, porque
    quem reenvia pode ter perdido a original — foi por isso que reenviou.
    """
    return {
        "type": "ack",
        "client_message_id": str(chave),
        "duplicate": repetida,
        "data": _response_to_dict(r),
    }


def _response_to_dict(r: ChatMessageResponse) -> dict:
    return {
        "id": str(r.id),
        "ticket_id": str(r.ticket_id),
        # Nulo quando quem falou foi a Helô. Sem a guarda isto vira a STRING
        # "None", que o front compara com o id do usuário logado e nunca bate —
        # funcionaria por acidente, e mentiria no tipo declarado.
        "sender_id": str(r.sender_id) if r.sender_id else None,
        "sender_name": r.sender_name,
        "sender_role": r.sender_role,
        "content": r.content,
        "is_system": r.is_system,
        "is_ai": r.is_ai,
        "created_at": r.created_at.isoformat(),
        "sender_avatar_url": r.sender_avatar_url,
        # Sem estes campos, o arquivo enviado pelo POST chegava aos outros como
        # mensagem só de texto, e só um F5 o mostrava (FUN-31).
        "library_file_id": str(r.library_file_id) if r.library_file_id else None,
        "library_file_name": r.library_file_name,
        "library_file_mime": r.library_file_mime,
        "library_file_size": r.library_file_size,
        "library_file_unavailable": r.library_file_unavailable,
        # O eco da chave: quem enviou reconhece a própria mensagem na sala e
        # apaga o rascunho (B-04b). Não serve a mais ninguém — vale só com o
        # remetente dela (`_envio_anterior`).
        "client_message_id": str(r.client_message_id) if r.client_message_id else None,
        # A posição na ordem de commit (F1-B-04c): é por ela que a tela sabe se
        # perdeu alguma coisa entre dois quadros.
        "seq": r.seq,
    }


async def _apply_chat_transition(
    db: AsyncSession,
    ticket: Ticket,
    sender: User,
) -> str | None:
    """Auto-transition ticket status when a chat message is sent.

    Staff sending → awaiting_client (if in_progress or awaiting_technical).
    Client sending → awaiting_technical (if awaiting_client).

    Returns the new status value string if a transition occurred, else None.
    """
    is_staff = sender.role in (UserRole.admin, UserRole.technician)

    if is_staff and ticket.status in (TicketStatus.in_progress, TicketStatus.awaiting_technical):
        changed = await _auto_transition(
            db, ticket, TicketStatus.awaiting_client, sender.id, "Técnico respondeu"
        )
        return TicketStatus.awaiting_client.value if changed else None

    # "Aguardando técnico" só faz sentido quando existe um técnico esperando por
    # ele. Sem responsável o chamado ainda não é de ninguém, e mandá-lo para lá
    # anunciava um atendimento que não começou.
    #
    # Antes da Helô isso quase nunca aparecia: o cliente raramente escrevia
    # antes de alguém falar com ele. Agora ele responde a triagem em segundos, e
    # todo chamado triado caía nesse estado — inclusive pausando o relógio do
    # SLA, que é o que menos se quer enquanto ele espera um humano.
    if (
        not is_staff
        and ticket.assignee_id is not None
        and ticket.status in (TicketStatus.in_progress, TicketStatus.awaiting_client)
    ):
        changed = await _auto_transition(
            db, ticket, TicketStatus.awaiting_technical, sender.id, "Cliente respondeu"
        )
        return TicketStatus.awaiting_technical.value if changed else None

    return None


async def _fala_da_helo_sem_derrubar(
    db: AsyncSession, ticket: Ticket, cliente: User, texto: str
) -> FalaDaHelo | None:
    """
    A Helô inteira, embrulhada. Falha dela nunca custa a mensagem do cliente.

    Dentro de `responde_triagem` cada falha PREVISTA já tem destino: LLM mudo,
    embedding fora e busca quebrada terminam em escalada, e nenhuma delas sobe.
    O que sobe é o que não foi previsto — um `TypeError` num bloco de contexto,
    um campo nulo onde o código esperava texto. Sem esta guarda, esse defeito
    vira 500 no POST do cliente, e a mensagem que ele acabou de escrever some
    junto: ele digitou, apertou enviar, e viu um erro.

    A assimetria é o argumento. O pior que acontece engolindo aqui é o chamado
    seguir sem a fala dela — que é exatamente o estado de antes de ela existir,
    e o cliente nem percebe. O pior que acontece deixando subir é o cliente
    perder o que escreveu por causa de um defeito numa funcionalidade que é
    acessório do atendimento, não o atendimento.

    `logger.exception` e não `warning`: engolir é para proteger o cliente, não
    para esconder o defeito. Sem o traço no log isto vira exatamente o que o
    módulo da Helô recusa em todo lugar — bug virando silêncio.

    **O SAVEPOINT é metade da guarda, e a metade que não é óbvia.** Se a falha
    dela for de banco — uma consulta de contexto contra tabela que não existe,
    um tipo errado num parâmetro —, o `except` sozinho não salva nada: em
    PostgreSQL o erro aborta a transação INTEIRA, e o `commit` logo abaixo
    morre com "current transaction is aborted", levando junto a mensagem do
    cliente. O resultado seria idêntico ao de não ter guarda nenhuma, com o
    agravante de parecer protegido. A busca vetorial já roda no próprio
    SAVEPOINT lá dentro; este aqui cobre todo o resto dela.
    """
    try:
        async with db.begin_nested():
            return await responde_triagem(db, ticket, cliente, texto)
    except Exception:  # noqa: BLE001 — a mensagem do cliente vale mais que a fala dela
        logger.exception(f"Helô falhou no chamado {ticket.protocol}; seguindo sem a fala dela")
        return None


async def _avisa_equipe_da_helo(db: AsyncSession, ticket: Ticket, *, motivo: str) -> None:
    """
    Chama a equipe quando a Helô sai de cena — dizendo por quê.

    Sem isto o chamado fica em "Em andamento" sem dono e sem ninguém avisado: a
    notificação normal do chat vai para o RESPONSÁVEL, e a essa altura não há
    responsável nenhum. O chamado dependeria de alguém olhar o quadro.

    Vai para todos os técnicos e admins ativos, e não para um sorteado: sem
    dono, escolher um seria inventar uma atribuição que ninguém pediu — e o
    escolhido poderia estar de férias.

    **As duas saídas mandavam o mesmo texto, e uma delas era falsa.** Quando o
    cliente pede uma pessoa, a triagem não terminou: ela foi interrompida, com
    as perguntas ainda sem resposta. Dizer "a Helô terminou a triagem" ali
    manda a equipe procurar um resumo que não existe, e apaga a única
    informação que muda a ordem da fila — que tem alguém do outro lado
    esperando gente, não esperando atendimento.

    Na Fase 2 o mesmo defeito voltou por outro lado: as saídas viraram quatro,
    e três delas — modelo escalou, teto de trocas, IA muda — continuavam
    chegando à equipe como "o cliente pediu para falar com uma pessoa". O
    motivo agora vem pronto de `responde_triagem` e é escrito no texto; o
    título separa só o caso que muda a prioridade da fila.

    O tipo continua `ticket_updated` nos dois casos: `NotificationType` é enum
    nativo do Postgres, e um valor novo custa um `ALTER TYPE` em migration que
    roda sozinha no boot — o preço que o desenho já recusou pagar pelo
    `ai_handling`. A distinção vive no título e no texto, que é onde a equipe
    de fato lê.
    """
    # A consulta morava aqui, e este era o único lugar do sistema que respondia
    # "quem é a operação". Com o chamado novo passando a avisar a equipe também,
    # ela viraria o SEGUNDO — e duas consultas com a mesma intenção divergem no
    # primeiro técnico desativado, em silêncio. Agora a resposta é uma só, em
    # `services/notifications.py`, provada contra Postgres de verdade.
    equipe = await audiencia_operacional(db)

    if motivo == MOTIVO_PEDIU_HUMANO:
        titulo = f"Cliente pediu atendimento humano — {ticket.protocol}"
        texto = "O cliente pediu para falar com uma pessoa. A Helô parou na hora."
    elif motivo == MOTIVO_TRIAGEM_CONCLUIDA:
        # O aviso da Fase 1, de volta com o modo triagem. Não fura a fila como
        # o pedido de gente, e não é escalada genérica: as respostas do
        # cliente às três perguntas estão na conversa, e é isso que a equipe
        # vai ler.
        titulo = f"Triagem concluída — {ticket.protocol}"
        texto = "A Helô terminou a triagem e o chamado está esperando atendimento."
    else:
        titulo = f"Helô passou o chamado — {ticket.protocol}"
        texto = f"A Helô saiu da conversa e o chamado está esperando atendimento: {motivo}."

    for pessoa in equipe:
        await notify(
            db,
            pessoa.id,
            NotificationType.ticket_updated,
            titulo,
            texto,
            data={"ticket_id": str(ticket.id), "protocol": ticket.protocol},
        )


async def _notify_other_party(
    db: AsyncSession,
    ticket: Ticket,
    sender: User,
    msg: ChatMessage,
) -> None:
    """
    Notify the other party in the conversation:
    - If sender is the requester → notify assignee (if any)
    - If sender is staff → notify requester
    """
    is_requester = ticket.creator_id == sender.id

    if is_requester:
        # Notify assignee if assigned
        if ticket.assignee_id:
            await notify(
                db,
                ticket.assignee_id,
                NotificationType.chat_message,
                f"Nova mensagem no chamado {ticket.protocol}",
                f"{sender.name}: {msg.content[:120]}",
                data={"ticket_id": str(ticket.id), "protocol": ticket.protocol},
            )
    else:
        # Notify requester
        await notify(
            db,
            ticket.creator_id,
            NotificationType.chat_message,
            f"Nova mensagem no chamado {ticket.protocol}",
            f"{sender.name}: {msg.content[:120]}",
            data={"ticket_id": str(ticket.id), "protocol": ticket.protocol},
        )
