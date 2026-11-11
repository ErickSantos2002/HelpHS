"""
O socket fantasma do `ConnectionManager` (F1-B-04c).

Antes: um `send_json` que falhava tirava o socket da sala e PARAVA aí. Ele
continuava em `_por_usuario`, aberto — o navegador não recebia fechamento
nenhum e ficava num chat surdo, achando que estava ao vivo. E um quadro que
não vira JSON (defeito do servidor, não do socket) fazia TODOS falharem: a
sala inteira era esvaziada por um erro que não era de nenhum deles.

Agora:
- falha de envio tira o socket dos DOIS índices e manda fechamento 1011,
  que a tela entende como "reconecte" (e, ao reconectar, sincroniza);
- falha ao fechar não impede a limpeza;
- quadro inválido é registrado e recusado ANTES de tocar em qualquer socket.

Unitário, com sockets falsos: o que se prova é a contabilidade do manager.
"""

import asyncio
import uuid
from unittest.mock import patch

from app.routers.chat import ConnectionManager

_SALA = "sala-1"


class _Socket:
    def __init__(self, *, falha_ao_enviar=False, falha_ao_fechar=False):
        self.recebidos: list[dict] = []
        self.fechado_com: int | None = None
        self._falha_ao_enviar = falha_ao_enviar
        self._falha_ao_fechar = falha_ao_fechar

    async def send_json(self, payload):
        if self._falha_ao_enviar:
            raise RuntimeError("conexão caiu")
        self.recebidos.append(payload)

    async def close(self, code=1000, reason=None):
        if self._falha_ao_fechar:
            raise RuntimeError("já estava morto")
        self.fechado_com = code


def _manager_com(*sockets_e_donos):
    m = ConnectionManager()
    for ws, dono in sockets_e_donos:
        m.connect(_SALA, ws, dono)
    return m


def test_falha_de_envio_tira_dos_dois_indices_e_avisa_quem_caiu():
    a, b = uuid.uuid4(), uuid.uuid4()
    vivo, morto = _Socket(), _Socket(falha_ao_enviar=True)
    m = _manager_com((vivo, a), (morto, b))

    asyncio.run(m.entregar_local(_SALA, {"type": "message"}))

    assert vivo.recebidos == [{"type": "message"}]
    assert m._rooms == {_SALA: {vivo}}
    assert m._por_usuario == {a: {vivo}}, "o morto não pode sobrar no índice da pessoa"
    assert morto.fechado_com == 1011


def test_o_morto_nao_recebe_mais_nada_e_os_vivos_continuam():
    a = uuid.uuid4()
    vivo, morto = _Socket(), _Socket(falha_ao_enviar=True)
    m = _manager_com((vivo, a), (morto, a))

    asyncio.run(m.entregar_local(_SALA, {"n": 1}))
    morto._falha_ao_enviar = False  # mesmo que "volte", não está mais na sala
    asyncio.run(m.entregar_local(_SALA, {"n": 2}))

    assert vivo.recebidos == [{"n": 1}, {"n": 2}]
    assert morto.recebidos == []
    assert m._por_usuario == {a: {vivo}}


def test_falha_ao_fechar_nao_impede_a_limpeza():
    a = uuid.uuid4()
    morto = _Socket(falha_ao_enviar=True, falha_ao_fechar=True)
    m = _manager_com((morto, a))

    asyncio.run(m.entregar_local(_SALA, {"type": "message"}))

    assert m._rooms == {} and m._por_usuario == {}


def test_quadro_que_nao_vira_json_e_recusado_sem_derrubar_ninguem():
    a, b = uuid.uuid4(), uuid.uuid4()
    um, outro = _Socket(), _Socket()
    m = _manager_com((um, a), (outro, b))

    class _Estranho:
        pass

    with patch("app.routers.chat.logger") as registro:
        asyncio.run(m.entregar_local(_SALA, {"type": "message", "data": _Estranho()}))
    asyncio.run(m.entregar_local(_SALA, {"type": "message", "data": "ok"}))

    assert m._rooms == {_SALA: {um, outro}}
    assert m._por_usuario == {a: {um}, b: {outro}}
    assert um.fechado_com is None and outro.fechado_com is None
    assert um.recebidos == outro.recebidos == [{"type": "message", "data": "ok"}]
    [(mensagem,), _] = registro.error.call_args
    assert "não vira JSON" in mensagem


def test_quem_caiu_reconecta_e_volta_a_receber():
    a = uuid.uuid4()
    morto = _Socket(falha_ao_enviar=True)
    m = _manager_com((morto, a))
    asyncio.run(m.entregar_local(_SALA, {"n": 1}))

    novo = _Socket()
    m.connect(_SALA, novo, a)
    asyncio.run(m.entregar_local(_SALA, {"n": 2}))
    # O `finally` do handler do morto roda depois: não pode levar o novo junto.
    m.disconnect(_SALA, morto, a)
    asyncio.run(m.entregar_local(_SALA, {"n": 3}))

    assert novo.recebidos == [{"n": 2}, {"n": 3}]
    assert m._por_usuario == {a: {novo}}


def test_sala_vazia_depois_da_limpeza_some_do_indice():
    a = uuid.uuid4()
    m = _manager_com((_Socket(falha_ao_enviar=True), a))

    asyncio.run(m.entregar_local(_SALA, {"n": 1}))

    assert _SALA not in m._rooms
