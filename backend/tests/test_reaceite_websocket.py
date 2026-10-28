"""
O aceite obrigatório da Política no chat por WebSocket.

O 4428 só chega ao navegador DEPOIS do `accept()`: fechado antes do handshake,
o uvicorn responde HTTP 403 e o navegador vê 1006, sem código (medido em
28/10/2026 no Edge, com as versões de produção do uvicorn e do starlette). Por
isso estes testes exigem que a conexão ABRA e só então feche com 4428.

O handler abre `AsyncSessionLocal` na mão, então o banco é simulado aqui; a
regra do aceite em si está provada contra o PostgreSQL em
`test_reaceite_enforcement_postgres.py`.
"""

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings
from app.main import app
from app.models.models import UserRole
from app.routers.chat import WS_ACEITE_POLITICA_PENDENTE, ConnectionManager
from tests.test_chat import _CREATOR_ID, _TICKET_ID, _mock_ticket, _mock_user

_URL = f"/api/v1/ws/tickets/{_TICKET_ID}?token=x"


def _ambiente(user, *, pendente, gravadas=None):
    """Os patches do handler: sessão simulada, token aceito e o aceite.

    `pendente` é a sequência de respostas da verificação do aceite, uma por
    chamada (a da conexão e depois uma por mensagem recebida).
    """
    sessao = AsyncMock()

    async def _execute(*a, **k):
        r = MagicMock()
        r.scalar_one_or_none.return_value = _mock_ticket(creator_id=_CREATOR_ID)
        return r

    sessao.execute = _execute
    sessao.add = lambda o: gravadas.append(o) if gravadas is not None else None

    class _Ctx:
        async def __aenter__(self):
            return sessao

        async def __aexit__(self, *a):
            return False

    async def _auth(token, db):
        return user

    verificacao = AsyncMock(side_effect=list(pendente))
    return (
        patch("app.routers.chat.AsyncSessionLocal", lambda: _Ctx()),
        patch("app.routers.chat._authenticate_ws", _auth),
        patch("app.routers.chat._politica_pendente", verificacao),
    ), verificacao


@pytest.mark.parametrize("papel", [UserRole.client, UserRole.technician, UserRole.admin])
def test_aceite_pendente_abre_e_fecha_com_4428(papel):
    user = _mock_user(papel, user_id=_CREATOR_ID)
    patches, _ = _ambiente(user, pendente=[True])
    with patches[0], patches[1], patches[2]:
        # Entrar no `with` prova que o handshake aconteceu: fechado antes do
        # `accept`, o TestClient levantaria já aqui.
        with TestClient(app).websocket_connect(_URL) as ws:
            with pytest.raises(WebSocketDisconnect) as fechou:
                ws.receive_text()

    assert fechou.value.code == WS_ACEITE_POLITICA_PENDENTE == 4428
    assert fechou.value.reason == "aceite_politica_pendente"


def test_sem_mensagem_de_erro_antes_do_4428():
    """O código basta; nenhum frame antes do fechamento."""
    user = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    patches, _ = _ambiente(user, pendente=[True])
    with patches[0], patches[1], patches[2]:
        with TestClient(app).websocket_connect(_URL) as ws:
            primeira = ws.receive()
    assert primeira["type"] == "websocket.close"
    assert primeira["code"] == 4428


def test_com_o_aceite_em_dia_o_chat_segue_aberto():
    user = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    patches, verificacao = _ambiente(user, pendente=[False, False])
    with patches[0], patches[1], patches[2]:
        with TestClient(app).websocket_connect(_URL) as ws:
            ws.send_text(json.dumps({"library_file_id": str(uuid.uuid4())}))
            resposta = ws.receive_json()
    assert resposta["type"] == "error"
    assert verificacao.await_count == 2


def test_aceite_conferido_de_novo_a_cada_mensagem():
    """Revogou com o chat aberto: a próxima mensagem fecha com 4428 e NÃO é
    gravada."""
    user = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    gravadas: list = []
    patches, verificacao = _ambiente(user, pendente=[False, True], gravadas=gravadas)
    with patches[0], patches[1], patches[2]:
        with TestClient(app).websocket_connect(_URL) as ws:
            ws.send_text(json.dumps({"content": "ainda posso falar?"}))
            with pytest.raises(WebSocketDisconnect) as fechou:
                ws.receive_text()

    assert fechou.value.code == 4428
    assert verificacao.await_count == 2
    assert gravadas == []


def test_a_verificacao_real_consulta_o_aceite_com_o_interruptor_ligado(monkeypatch):
    """Sem o patch de `_politica_pendente`: o handler liga mesmo a regra do
    `consentimento` (aqui, sem aceite nenhum → pendente)."""
    s = get_settings()
    monkeypatch.setattr(s, "lgpd_exige_reaceite", True)
    monkeypatch.setattr(s, "lgpd_revisao_politica", "01")
    user = _mock_user(UserRole.technician)
    patches, _ = _ambiente(user, pendente=[])
    vazio = AsyncMock(return_value=[])
    with patches[0], patches[1], patch("app.services.consentimento.aceites_abertos", vazio):
        with TestClient(app).websocket_connect(_URL) as ws:
            with pytest.raises(WebSocketDisconnect) as fechou:
                ws.receive_text()
    assert fechou.value.code == 4428
    vazio.assert_awaited_once()


def test_interruptor_desligado_nao_consulta_nem_fecha():
    assert get_settings().lgpd_exige_reaceite is False
    user = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    patches, _ = _ambiente(user, pendente=[])
    consulta = AsyncMock(return_value=[])
    with patches[0], patches[1], patch("app.services.consentimento.aceites_abertos", consulta):
        with TestClient(app).websocket_connect(_URL) as ws:
            ws.send_text(json.dumps({"library_file_id": str(uuid.uuid4())}))
            assert ws.receive_json()["type"] == "error"
    consulta.assert_not_awaited()


def test_token_invalido_continua_4001():
    """O contrato antigo do 4001 não muda nesta frente (dívida registrada)."""

    async def _ninguem(token, db):
        return None

    with patch("app.routers.chat._authenticate_ws", _ninguem):
        with pytest.raises(WebSocketDisconnect) as fechou:
            with TestClient(app).websocket_connect(_URL):
                pass
    assert fechou.value.code == 4001


# ── Fechar os chats de quem revogou ───────────────────────────


class _Socket:
    def __init__(self, falha=False):
        self.fechado_com = None
        self.falha = falha

    async def close(self, code, reason):
        if self.falha:
            raise RuntimeError("já morreu")
        self.fechado_com = (code, reason)

    async def send_json(self, payload):
        pass


@pytest.mark.asyncio
async def test_fecha_so_os_sockets_da_pessoa():
    m = ConnectionManager()
    dela, dela_noutro_chamado, alheio = _Socket(), _Socket(), _Socket()
    pessoa, outra = uuid.uuid4(), uuid.uuid4()
    m.connect("t1", dela, pessoa)
    m.connect("t2", dela_noutro_chamado, pessoa)
    m.connect("t1", alheio, outra)

    fechados = await m.fecha_do_usuario(pessoa, code=4428, reason="aceite_politica_pendente")

    assert fechados == 2
    assert dela.fechado_com == dela_noutro_chamado.fechado_com == (4428, "aceite_politica_pendente")
    assert alheio.fechado_com is None


@pytest.mark.asyncio
async def test_socket_que_falha_ao_fechar_nao_impede_os_outros():
    m = ConnectionManager()
    morto, vivo = _Socket(falha=True), _Socket()
    pessoa = uuid.uuid4()
    m.connect("t1", morto, pessoa)
    m.connect("t2", vivo, pessoa)

    assert await m.fecha_do_usuario(pessoa, code=4428, reason="x") == 1
    assert vivo.fechado_com == (4428, "x")


def test_desconectar_esquece_o_dono():
    m = ConnectionManager()
    s, pessoa = _Socket(), uuid.uuid4()
    m.connect("t1", s, pessoa)
    m.disconnect("t1", s, pessoa)
    assert m._por_usuario == {} and m._rooms == {}


def test_revogar_com_o_chat_aberto_fecha_e_o_socket_para_de_receber():
    """Ponta a ponta no processo: o socket aberto, parado em `receive`, é
    fechado com 4428 por `fecha_chats_do_usuario` — que é o que o PATCH de
    revogar chama depois do commit."""
    from app.routers.chat import fecha_chats_do_usuario, manager

    user = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    patches, _ = _ambiente(user, pendente=[False])
    with patches[0], patches[1], patches[2]:
        tc = TestClient(app)
        with tc.websocket_connect(_URL) as ws:
            assert user.id in manager._por_usuario
            # O app roda noutra thread (a do TestClient); o fechamento entra pela
            # fila do transporte, como entraria vindo de outro pedido.
            assert asyncio.run(fecha_chats_do_usuario(user.id)) == 1
            with pytest.raises(WebSocketDisconnect) as fechou:
                ws.receive_text()
    assert fechou.value.code == 4428
    assert user.id not in manager._por_usuario
