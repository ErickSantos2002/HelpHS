"""Backplane do chat: uma mensagem publicada num worker chega aos outros.

O modo de falha que este arquivo existe para impedir é silencioso. Sem
backplane, subir `--workers 2` não estoura nada: as mensagens continuam sendo
gravadas corretamente, e duas pessoas no mesmo chamado apenas param de se ver em
tempo real — descobrindo só ao recarregar a página.

Um "processo", para efeito deste código, é um `ConnectionManager` com a sua
própria identidade. É por isso que a origem é atributo de INSTÂNCIA e não global
de módulo: com um global, os dois managers de um teste compartilhariam o mesmo
carimbo, a supressão de eco descartaria tudo, e o teste de entrega entre
processos não teria como ser escrito.
"""

import asyncio

import pytest

from app.routers.chat import ConnectionManager
from app.services import chat_backplane

_TICKET = "11111111-2222-3333-4444-555555555555"
_PAYLOAD = {"type": "message", "data": {"content": "oi"}}


class _Socket:
    """WebSocket de mentira que anota o que recebeu."""

    def __init__(self, ordem: list[str] | None = None) -> None:
        self.recebidos: list[dict] = []
        self.chegou = asyncio.Event()
        self._ordem = ordem

    async def send_json(self, payload: dict) -> None:
        if self._ordem is not None:
            self._ordem.append("local")
        self.recebidos.append(payload)
        self.chegou.set()


class _Broker:
    """Pub/sub de mentira: entrega a TODOS os inscritos, inclusive a quem publicou.

    Entregar de volta a quem publicou é fiel ao Redis, e é o que dá sentido ao
    carimbo de origem — sem ele, o socket local receberia a mensagem duas vezes.
    """

    def __init__(self, ordem: list[str] | None = None) -> None:
        self.filas: list[asyncio.Queue] = []
        self.quebrado = False
        self.publicados: list[tuple[str, str]] = []
        self._ordem = ordem

    async def publish(self, canal: str, dado: str) -> None:
        if self._ordem is not None:
            self._ordem.append("publish")
        await asyncio.sleep(0)
        if self.quebrado:
            raise ConnectionError("redis fora do ar")
        self.publicados.append((canal, dado))
        for fila in self.filas:
            fila.put_nowait({"type": "message", "channel": canal, "data": dado})

    def pubsub(self):
        broker = self

        class _PubSub:
            def __init__(self) -> None:
                self.fila: asyncio.Queue = asyncio.Queue()

            async def __aenter__(self):
                if broker.quebrado:
                    raise ConnectionError("redis fora do ar")
                broker.filas.append(self.fila)
                return self

            async def __aexit__(self, *a):
                if self.fila in broker.filas:
                    broker.filas.remove(self.fila)
                return False

            async def subscribe(self, *canais):
                await asyncio.sleep(0)

            async def listen(self):
                while True:
                    yield await self.fila.get()

        return _PubSub()


def _usando(broker):
    async def _get_redis():
        return broker

    return _get_redis


async def _ate(condicao, limite: float = 1.0) -> None:
    """Espera a condição virar verdadeira, cedendo o event loop."""
    fim = asyncio.get_running_loop().time() + limite
    while not condicao():
        if asyncio.get_running_loop().time() > fim:
            raise AssertionError("a condição não se cumpriu no tempo")
        await asyncio.sleep(0.001)


async def _encerrar(tarefa: asyncio.Task) -> None:
    tarefa.cancel()
    try:
        await tarefa
    except asyncio.CancelledError:
        pass


# ── A identidade é por instância ──────────────────────────────


def test_cada_manager_tem_a_propria_origem():
    """O achado do painel, virado teste.

    Com a origem em variável de módulo, os dois managers de qualquer teste
    dividiriam o mesmo carimbo — a supressão de eco descartaria a mensagem que
    deveria atravessar, e o desenho ficaria intestável exatamente na propriedade
    que justifica o backplane.
    """
    a, b = ConnectionManager(), ConnectionManager()

    assert a.origem and b.origem
    assert a.origem != b.origem


# ── Entrega entre "processos" ─────────────────────────────────


@pytest.mark.asyncio
async def test_mensagem_publicada_num_manager_chega_ao_outro(monkeypatch):
    """O teste que justifica a fase inteira."""
    broker = _Broker()
    monkeypatch.setattr(chat_backplane, "get_redis", _usando(broker))

    a, b = ConnectionManager(), ConnectionManager()
    socket = _Socket()
    b.connect(_TICKET, socket)

    tarefa = chat_backplane.start_chat_backplane(b.entregar_local, b.origem)
    try:
        await _ate(chat_backplane.assinatura_ativa)
        await a.broadcast(_TICKET, _PAYLOAD)
        await asyncio.wait_for(socket.chegou.wait(), timeout=1)
    finally:
        await _encerrar(tarefa)

    assert socket.recebidos == [_PAYLOAD]


@pytest.mark.asyncio
async def test_quem_publicou_nao_entrega_duas_vezes(monkeypatch):
    """Eco: quem publicou já entregou localmente."""
    broker = _Broker()
    monkeypatch.setattr(chat_backplane, "get_redis", _usando(broker))

    a = ConnectionManager()
    socket = _Socket()
    a.connect(_TICKET, socket)

    tarefa = chat_backplane.start_chat_backplane(a.entregar_local, a.origem)
    try:
        await _ate(chat_backplane.assinatura_ativa)
        await a.broadcast(_TICKET, _PAYLOAD)
        await asyncio.wait_for(socket.chegou.wait(), timeout=1)
        # Dá tempo de um eco indevido chegar, se ele existisse
        for _ in range(50):
            await asyncio.sleep(0)
    finally:
        await _encerrar(tarefa)

    assert socket.recebidos == [_PAYLOAD], f"entregou {len(socket.recebidos)} vezes"


@pytest.mark.asyncio
async def test_mensagem_de_sala_que_o_worker_nao_hospeda_e_descartada(monkeypatch):
    """Canal é único; o filtro por chamado acontece na chegada."""
    broker = _Broker()
    monkeypatch.setattr(chat_backplane, "get_redis", _usando(broker))

    a, b = ConnectionManager(), ConnectionManager()
    socket = _Socket()
    b.connect("outro-chamado", socket)

    tarefa = chat_backplane.start_chat_backplane(b.entregar_local, b.origem)
    try:
        await _ate(chat_backplane.assinatura_ativa)
        await a.broadcast(_TICKET, _PAYLOAD)
        for _ in range(50):
            await asyncio.sleep(0)
    finally:
        await _encerrar(tarefa)

    assert socket.recebidos == []


# ── Redis fora não pode piorar o que já funciona ──────────────


@pytest.mark.asyncio
async def test_redis_fora_nao_impede_a_entrega_local(monkeypatch):
    """A régua: com o Redis fora, o chat fica EXATAMENTE como está hoje.

    Hoje o chat não usa Redis nenhum. Uma dependência nova não pode piorar a
    disponibilidade do que já funciona.
    """
    broker = _Broker()
    broker.quebrado = True
    monkeypatch.setattr(chat_backplane, "get_redis", _usando(broker))

    a = ConnectionManager()
    socket = _Socket()
    a.connect(_TICKET, socket)

    await a.broadcast(_TICKET, _PAYLOAD)

    assert socket.recebidos == [_PAYLOAD]


@pytest.mark.asyncio
async def test_a_entrega_local_acontece_antes_do_publish(monkeypatch):
    """Ordem, não só resultado.

    Publicar primeiro faria a latência do Redis atrasar o socket que está no
    mesmo processo — o caso mais comum, ainda mais com um worker só.
    """
    ordem: list[str] = []
    broker = _Broker(ordem=ordem)
    monkeypatch.setattr(chat_backplane, "get_redis", _usando(broker))

    a = ConnectionManager()
    a.connect(_TICKET, _Socket(ordem=ordem))

    await a.broadcast(_TICKET, _PAYLOAD)

    assert ordem == ["local", "publish"], ordem


# ── Reassinatura ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_assinatura_volta_sozinha_depois_de_cair(monkeypatch):
    """Redis pisca e volta: o assinante tem de se reerguer sem ninguém mandar."""
    broker = _Broker()
    broker.quebrado = True
    monkeypatch.setattr(chat_backplane, "get_redis", _usando(broker))
    monkeypatch.setattr(chat_backplane, "ESPERA_RECONEXAO", 0.01)

    b = ConnectionManager()
    tarefa = chat_backplane.start_chat_backplane(b.entregar_local, b.origem)
    try:
        await asyncio.sleep(0.05)
        assert chat_backplane.assinatura_ativa() is False

        broker.quebrado = False
        await _ate(chat_backplane.assinatura_ativa, limite=2)
    finally:
        await _encerrar(tarefa)


@pytest.mark.asyncio
async def test_a_queda_nao_loga_a_cada_tentativa(monkeypatch):
    """Log só na TRANSIÇÃO.

    Uma linha por tentativa, a cada poucos segundos, transforma uma queda de
    Redis numa inundação — e o log que deveria denunciar o problema vira o
    problema.
    """
    from loguru import logger

    broker = _Broker()
    broker.quebrado = True
    monkeypatch.setattr(chat_backplane, "get_redis", _usando(broker))
    monkeypatch.setattr(chat_backplane, "ESPERA_RECONEXAO", 0.01)

    avisos: list[str] = []
    sink = logger.add(
        lambda m: avisos.append(m.record["message"]), level="WARNING", filter=lambda r: True
    )

    b = ConnectionManager()
    tarefa = chat_backplane.start_chat_backplane(b.entregar_local, b.origem)
    try:
        await asyncio.sleep(0.2)  # daria ~20 tentativas
    finally:
        await _encerrar(tarefa)
        logger.remove(sink)

    do_backplane = [a for a in avisos if "backplane" in a.lower()]
    assert len(do_backplane) <= 1, f"{len(do_backplane)} avisos para uma queda só"
