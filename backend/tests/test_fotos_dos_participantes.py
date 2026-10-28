"""
Fase 3B — a foto dos participantes do chamado.

O que esta suíte prende:

- quem vê a foto de quem (`foto_visivel_no_chamado` e `foto_visivel_na_conversa`);
- que só a chave que o upload produz para AQUELA conta é assinada — a de outra
  pessoa, uma URL externa ou um caminho torto viram "sem foto";
- que o link sai com o TTL dos arquivos (1 h) e não com os 7 dias da própria foto;
- que a assinatura é por PESSOA, não por mensagem;
- que o detalhe do chamado, o histórico do chat e o WebSocket seguem a mesma
  regra — e que o WebSocket, que manda o mesmo payload a toda a sala, nunca
  carrega a foto de um cliente que não é o dono do chamado;
- que falhar ao assinar não derruba nada.

Usuários são `SimpleNamespace`, não `MagicMock`: um mock responde a qualquer
atributo, e é justamente "o objeto tem um atributo que não deveria" que alguns
destes casos precisam conseguir ver.
"""

import time
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from app.models.models import TicketCategory, TicketStatus, UserRole, UserStatus
from app.utils import avatar as av

# ── Montagem ──────────────────────────────────────────────────


def _pessoa(
    papel: UserRole, *, foto: str | bool | None = True, autoriza: bool = True, **extra
) -> SimpleNamespace:
    """Uma conta. `foto=True` grava a chave legítima dela; um texto grava o texto.

    `autoriza=True` aqui é ARRANJO, não padrão do sistema: os casos da matriz
    partem de quem permitiu, para que o que se teste seja a matriz. O padrão
    real é falso — e é o que a seção "A autorização individual" prova, com
    `autoriza=False` explícito e com a conta sem o atributo.
    """
    uid = uuid.uuid4()
    if foto is True:
        chave: str | None = f"avatars/{uid}.png"
    elif foto is False or foto is None:
        chave = None
    else:
        chave = foto
    base = {
        "id": uid,
        "name": f"Pessoa {papel.value}",
        "email": f"{uid.hex[:8]}@test.invalid",
        "phone": "+5581999999999",
        "company_name": "Empresa",
        "role": papel,
        "status": UserStatus.active,
        "avatar_url": chave,
        "avatar_visivel_a_terceiros": autoriza,
    }
    base.update(extra)
    return SimpleNamespace(**base)


def _chamado(criador, responsavel=None) -> MagicMock:
    from app.models.models import Ticket

    chamado = MagicMock(spec=Ticket)
    agora = datetime.now(UTC)
    for campo, valor in {
        "id": uuid.uuid4(),
        "protocol": "HS-2026-0001",
        "title": "Teste",
        "description": "d",
        "status": TicketStatus.open,
        "priority": None,
        "category": TicketCategory.hardware,
        "creator_id": criador.id,
        "assignee_id": responsavel.id if responsavel else None,
        "product_id": None,
        "equipments": [],
        "tags": [],
        "sla_response_due_at": None,
        "sla_resolve_due_at": None,
        "sla_response_breach": False,
        "sla_resolve_breach": False,
        "sla_first_response": None,
        "sla_resolve_extension_total_min": 0,
        "closed_at": None,
        "resolved_at": None,
        "auto_closed": False,
        "reopened_at": None,
        "reopen_count": 0,
        "ai_enabled": True,
        "technician_notes": None,
        "ai_classification": None,
        "ai_confidence": None,
        "ai_summary": None,
        "ai_conversation_summary": None,
        "client_observation": None,
        "resolution_note": None,
        "created_at": agora,
        "updated_at": agora,
    }.items():
        setattr(chamado, campo, valor)
    return chamado


async def _assina_de_mentira(chave, settings, expires=3600):
    return f"/api/v1/files/tok-{chave}"


@pytest.fixture(autouse=True)
def _limpa():
    yield
    app.dependency_overrides.clear()


# ── A regra: quem vê a foto de quem ───────────────────────────


@pytest.mark.parametrize("papel_do_ator", [UserRole.admin, UserRole.technician])
def test_equipe_ve_a_foto_de_qualquer_participante(papel_do_ator):
    ator = _pessoa(papel_do_ator)
    for alvo in (_pessoa(UserRole.client), _pessoa(UserRole.technician), _pessoa(UserRole.admin)):
        assert av.foto_visivel_no_chamado(alvo, ator)


def test_cliente_ve_a_propria_foto_e_a_da_equipe():
    cliente = _pessoa(UserRole.client)
    assert av.foto_visivel_no_chamado(cliente, cliente)
    assert av.foto_visivel_no_chamado(_pessoa(UserRole.technician), cliente)
    assert av.foto_visivel_no_chamado(_pessoa(UserRole.admin), cliente)


def test_cliente_nao_ve_a_foto_de_outro_cliente():
    assert not av.foto_visivel_no_chamado(_pessoa(UserRole.client), _pessoa(UserRole.client))


def test_na_conversa_a_regra_nao_depende_de_quem_recebe():
    """Equipe e criador sim; outro cliente não — para qualquer destinatário."""
    criador = _pessoa(UserRole.client)
    chamado = SimpleNamespace(creator_id=criador.id)
    assert av.foto_visivel_na_conversa(criador, chamado)
    assert av.foto_visivel_na_conversa(_pessoa(UserRole.technician), chamado)
    assert av.foto_visivel_na_conversa(_pessoa(UserRole.admin), chamado)
    assert not av.foto_visivel_na_conversa(_pessoa(UserRole.client), chamado)


def test_helo_e_sistema_nao_entram_na_lista_de_fotos():
    tecnico = _pessoa(UserRole.technician)
    chamado = SimpleNamespace(creator_id=uuid.uuid4())
    msgs = [
        SimpleNamespace(is_ai=True, is_system=False, sender=None),
        SimpleNamespace(is_ai=False, is_system=True, sender=tecnico),
        SimpleNamespace(is_ai=False, is_system=False, sender=tecnico),
    ]
    assert av.remetentes_com_foto(msgs, chamado) == [tecnico]


# ── A chave: só a legítima é assinada ─────────────────────────


@pytest.mark.parametrize(
    "gravado",
    [
        "avatars/{outro}.png",  # a foto de OUTRA conta
        "https://evil.example/x.png",
        "avatars/../tickets/{dono}/laudo.pdf",
        "AVATARS/{dono}.png",
        "avatars/{dono}.svg",
        "tickets/{dono}/foto.png",
    ],
)
@pytest.mark.asyncio
async def test_referencia_indevida_nunca_e_assinada(gravado):
    dono = _pessoa(UserRole.technician, foto=None)
    dono.avatar_url = gravado.format(outro=uuid.uuid4(), dono=dono.id)
    assina = AsyncMock(side_effect=_assina_de_mentira)
    with patch.object(av.storage, "get_presigned_url", new=assina):
        links = await av.links_das_fotos([dono], get_settings())
    assert links == {}
    assina.assert_not_awaited()


@pytest.mark.parametrize("ext", [".jpg", ".png", ".gif", ".webp"])
@pytest.mark.asyncio
async def test_a_chave_legitima_e_assinada(ext):
    dono = _pessoa(UserRole.technician, foto=None)
    dono.avatar_url = f"avatars/{dono.id}{ext}"
    with patch.object(
        av.storage, "get_presigned_url", new=AsyncMock(side_effect=_assina_de_mentira)
    ):
        links = await av.links_das_fotos([dono], get_settings())
    assert links == {dono.id: f"/api/v1/files/tok-avatars/{dono.id}{ext}"}


@pytest.mark.asyncio
async def test_sem_foto_e_anonimizado_ficam_sem_link():
    sem_foto = _pessoa(UserRole.client, foto=None)
    anonimizado = _pessoa(UserRole.client, foto=None, status=UserStatus.anonymized)
    with patch.object(av.storage, "get_presigned_url", new=AsyncMock()) as assina:
        links = await av.links_das_fotos([sem_foto, anonimizado], get_settings())
    assert links == {}
    assina.assert_not_awaited()


@pytest.mark.asyncio
async def test_uma_assinatura_por_pessoa_e_nao_por_aparicao():
    a, b, c = (_pessoa(UserRole.technician) for _ in range(3))
    pessoas = [a, b, c] * 17  # 51 aparições de 3 pessoas
    assina = AsyncMock(side_effect=_assina_de_mentira)
    with patch.object(av.storage, "get_presigned_url", new=assina):
        links = await av.links_das_fotos(pessoas, get_settings())
    assert assina.await_count == 3
    assert set(links) == {a.id, b.id, c.id}


@pytest.mark.asyncio
async def test_o_link_usa_o_ttl_dos_arquivos_e_nao_os_sete_dias():
    settings = get_settings()
    dono = _pessoa(UserRole.technician)
    assina = AsyncMock(side_effect=_assina_de_mentira)
    with patch.object(av.storage, "get_presigned_url", new=assina):
        await av.links_das_fotos([dono], settings)
    assert assina.await_args.kwargs["expires"] == settings.file_url_expires_seconds
    assert settings.file_url_expires_seconds != 604800


@pytest.mark.asyncio
async def test_o_link_real_vence_dentro_do_ttl_e_autoriza_so_a_propria_chave(tmp_path):
    """Sem dublê: emite com a chave RS256 da suíte e lê de volta como o /files leria."""
    from app.services import storage

    settings = get_settings()
    dono = _pessoa(UserRole.technician)
    links = await av.links_das_fotos([dono], settings)
    token = links[dono.id].rsplit("/", 1)[-1]
    chave, exp = storage.ler_token_de_arquivo(token, settings)
    assert chave == f"avatars/{dono.id}.png"
    assert exp <= int(time.time()) + settings.file_url_expires_seconds


@pytest.mark.asyncio
async def test_falha_ao_assinar_vira_sem_foto_e_nao_derruba():
    ok, quebra = _pessoa(UserRole.technician), _pessoa(UserRole.technician)

    async def _assina(chave, settings, expires=3600):
        if str(quebra.id) in chave:
            raise RuntimeError("chave PEM ilegível")
        return "/api/v1/files/tok"

    with patch.object(av.storage, "get_presigned_url", new=_assina):
        links = await av.links_das_fotos([ok, quebra], get_settings())
    assert links == {ok.id: "/api/v1/files/tok"}


def test_o_resumo_do_solicitante_nunca_le_a_chave_crua_do_usuario():
    """A trava do schema: validar um `User` direto não copia `avatar_url`."""
    from app.schemas.ticket import TicketRequesterBrief

    dono = _pessoa(UserRole.client)
    resumo = TicketRequesterBrief.model_validate(dono)
    assert resumo.avatar_url is None
    assert "avatars/" not in resumo.model_dump_json()


def test_a_regra_da_chave_continua_a_mesma_no_router_de_usuarios():
    """A extração não mudou o comportamento: os nomes antigos apontam para cá."""
    from app.routers import users

    assert users._avatar_do_proprio_usuario is av.chave_legitima_do_avatar
    assert users._AVATAR_EXTENSOES is av.EXTENSOES_DO_AVATAR


# ── O detalhe do chamado ──────────────────────────────────────


async def _detalhe(ator, chamado, pessoas, assina=None):
    from app.core.database import get_db
    from app.core.security import get_current_user

    por_id = {p.id: p for p in pessoas}

    class _Sessao:
        add = MagicMock()
        commit = AsyncMock()
        refresh = AsyncMock()

        async def get(self, modelo, chave, *a, **k):
            return por_id.get(chave) if modelo.__name__ == "User" else chamado

        async def execute(self, *a, **k):
            r = MagicMock()
            r.scalar_one_or_none.return_value = None
            r.scalars.return_value.all.return_value = []
            return r

    async def _db():
        yield _Sessao()

    async def _atual():
        return ator

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _atual
    assina = assina or AsyncMock(side_effect=_assina_de_mentira)
    with (
        patch("app.routers.tickets.get_or_404", new=AsyncMock(return_value=chamado)),
        patch.object(av.storage, "get_presigned_url", new=assina),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get(f"/api/v1/tickets/{chamado.id}")
    return r, assina


@pytest.mark.asyncio
async def test_cliente_ve_a_foto_do_tecnico_responsavel_e_a_propria():
    cliente = _pessoa(UserRole.client)
    tecnico = _pessoa(UserRole.technician)
    r, _ = await _detalhe(cliente, _chamado(cliente, tecnico), [cliente, tecnico])

    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["assignee_avatar_url"] == f"/api/v1/files/tok-avatars/{tecnico.id}.png"
    assert corpo["requester"]["avatar_url"] == f"/api/v1/files/tok-avatars/{cliente.id}.png"


@pytest.mark.asyncio
async def test_cliente_nao_recebe_a_foto_de_outro_cliente_como_responsavel():
    """Dado torto (troca de papel, registro antigo): a foto não sai."""
    cliente = _pessoa(UserRole.client)
    outro_cliente = _pessoa(UserRole.client)
    r, assina = await _detalhe(cliente, _chamado(cliente, outro_cliente), [cliente, outro_cliente])

    assert r.status_code == 200, r.text
    assert r.json()["assignee_avatar_url"] is None
    assinadas = [c.args[0] for c in assina.await_args_list]
    assert f"avatars/{outro_cliente.id}.png" not in assinadas


@pytest.mark.asyncio
async def test_equipe_ve_a_foto_do_solicitante_e_do_responsavel():
    cliente = _pessoa(UserRole.client)
    tecnico = _pessoa(UserRole.technician)
    admin = _pessoa(UserRole.admin)
    r, _ = await _detalhe(admin, _chamado(cliente, tecnico), [cliente, tecnico])

    corpo = r.json()
    assert corpo["requester"]["avatar_url"] == f"/api/v1/files/tok-avatars/{cliente.id}.png"
    assert corpo["assignee_avatar_url"] == f"/api/v1/files/tok-avatars/{tecnico.id}.png"


@pytest.mark.asyncio
async def test_chamado_alheio_continua_404_e_nao_assina_nada():
    dono = _pessoa(UserRole.client)
    intruso = _pessoa(UserRole.client)
    tecnico = _pessoa(UserRole.technician)
    r, assina = await _detalhe(intruso, _chamado(dono, tecnico), [dono, tecnico])

    assert r.status_code == 404
    assina.assert_not_awaited()


@pytest.mark.asyncio
async def test_sem_responsavel_e_sem_foto_o_detalhe_abre_com_nulos():
    cliente = _pessoa(UserRole.client, foto=None)
    r, assina = await _detalhe(_pessoa(UserRole.technician), _chamado(cliente), [cliente])

    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["assignee_avatar_url"] is None
    assert corpo["assignee_id"] is None
    assert corpo["requester"]["avatar_url"] is None
    assina.assert_not_awaited()


@pytest.mark.asyncio
async def test_chave_de_outra_pessoa_gravada_no_solicitante_nao_e_assinada():
    cliente = _pessoa(UserRole.client, foto=None)
    vitima = uuid.uuid4()
    cliente.avatar_url = f"avatars/{vitima}.png"
    r, assina = await _detalhe(_pessoa(UserRole.admin), _chamado(cliente), [cliente])

    assert r.json()["requester"]["avatar_url"] is None
    assina.assert_not_awaited()


@pytest.mark.asyncio
async def test_falha_ao_assinar_nao_impede_o_chamado_de_abrir():
    cliente = _pessoa(UserRole.client)
    tecnico = _pessoa(UserRole.technician)
    quebra = AsyncMock(side_effect=RuntimeError("storage fora"))
    r, _ = await _detalhe(cliente, _chamado(cliente, tecnico), [cliente, tecnico], assina=quebra)

    assert r.status_code == 200, r.text
    assert r.json()["assignee_avatar_url"] is None
    assert r.json()["requester"]["avatar_url"] is None


@pytest.mark.asyncio
async def test_responsavel_que_abriu_o_proprio_chamado_assina_uma_vez():
    tecnico = _pessoa(UserRole.technician)
    r, assina = await _detalhe(_pessoa(UserRole.admin), _chamado(tecnico, tecnico), [tecnico])

    assert r.status_code == 200, r.text
    assert assina.await_count == 1


# ── O histórico do chat (REST) ────────────────────────────────


def _mensagem(chamado, remetente, *, is_ai=False, is_system=False):
    return SimpleNamespace(
        id=uuid.uuid4(),
        ticket_id=chamado.id,
        sender_id=remetente.id if remetente else None,
        sender=remetente,
        content="oi",
        is_system=is_system,
        is_ai=is_ai,
        read_at=None,
        created_at=datetime.now(UTC),
        library_file_id=None,
        library_file=None,
    )


async def _historico(ator, chamado, mensagens):
    from app.core.database import get_db
    from app.core.security import get_current_user

    respostas = iter([chamado, len(mensagens), mensagens])
    consultas = []

    async def _execute(*a, **k):
        consultas.append(a)
        resp = next(respostas)
        r = MagicMock()
        r.scalar_one_or_none.return_value = resp
        r.scalar_one.return_value = resp
        r.scalars.return_value.all.return_value = resp
        return r

    sessao = AsyncMock()
    sessao.execute = _execute

    async def _db():
        yield sessao

    async def _atual():
        return ator

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _atual
    assina = AsyncMock(side_effect=_assina_de_mentira)
    with (
        patch("app.core.security.get_redis"),
        patch.object(av.storage, "get_presigned_url", new=assina),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get(f"/api/v1/tickets/{chamado.id}/messages")
    return r, assina, consultas


@pytest.mark.parametrize("papel_do_ator", [UserRole.client, UserRole.technician])
@pytest.mark.asyncio
async def test_historico_mostra_equipe_e_criador_mas_nunca_outro_cliente(papel_do_ator):
    criador = _pessoa(UserRole.client)
    tecnico = _pessoa(UserRole.technician)
    outro_cliente = _pessoa(UserRole.client)
    chamado = SimpleNamespace(id=uuid.uuid4(), creator_id=criador.id)
    ator = criador if papel_do_ator == UserRole.client else _pessoa(UserRole.technician)
    msgs = [
        _mensagem(chamado, tecnico),
        _mensagem(chamado, criador),
        _mensagem(chamado, outro_cliente),
        _mensagem(chamado, None, is_ai=True),
        _mensagem(chamado, tecnico, is_system=True),
    ]

    r, assina, _ = await _historico(ator, chamado, msgs)

    assert r.status_code == 200, r.text
    fotos = [i["sender_avatar_url"] for i in r.json()["items"]]
    assert fotos == [
        f"/api/v1/files/tok-avatars/{tecnico.id}.png",
        f"/api/v1/files/tok-avatars/{criador.id}.png",
        None,  # outro cliente
        None,  # Helô
        None,  # aviso do sistema, mesmo com o id do técnico
    ]
    assinadas = [c.args[0] for c in assina.await_args_list]
    assert f"avatars/{outro_cliente.id}.png" not in assinadas


@pytest.mark.asyncio
async def test_historico_assina_por_pessoa_e_nao_consulta_usuario_por_mensagem():
    criador = _pessoa(UserRole.client)
    tecnicos = [_pessoa(UserRole.technician) for _ in range(2)]
    chamado = SimpleNamespace(id=uuid.uuid4(), creator_id=criador.id)
    msgs = [_mensagem(chamado, p) for p in [criador, *tecnicos] * 17]

    r, assina, consultas = await _historico(criador, chamado, msgs)

    assert r.status_code == 200, r.text
    assert len(r.json()["items"]) == 51
    assert assina.await_count == 3
    # chamado + contagem + mensagens (com o remetente no selectinload): nada a mais.
    assert len(consultas) == 3


@pytest.mark.asyncio
async def test_historico_alheio_continua_404():
    dono = _pessoa(UserRole.client)
    chamado = SimpleNamespace(id=uuid.uuid4(), creator_id=dono.id)
    r, assina, _ = await _historico(_pessoa(UserRole.client), chamado, [])
    assert r.status_code == 404
    assina.assert_not_awaited()


def test_mensagem_continua_valida_sem_o_campo_novo():
    """Compatibilidade: quem monta a resposta sem foto continua funcionando."""
    from app.routers.chat import _msg_to_response, _response_to_dict

    chamado = SimpleNamespace(id=uuid.uuid4(), creator_id=uuid.uuid4())
    resposta = _msg_to_response(_mensagem(chamado, _pessoa(UserRole.technician)))
    assert resposta.sender_avatar_url is None
    assert _response_to_dict(resposta)["sender_avatar_url"] is None


# ── O POST de mensagem (o caminho do envio com anexo) ─────────


async def _posta(ator, chamado, recarregada):
    """POST /tickets/{id}/messages: devolve (resposta, frame transmitido à sala).

    `recarregada` é a mensagem que a rota relê depois do commit — é dela que
    sai o remetente. O frame é o argumento REAL de `manager.broadcast`, o mesmo
    que o WebSocket entrega a todos da sala.
    """
    from app.core.database import get_db
    from app.core.security import get_current_user

    respostas = iter([chamado, recarregada])

    async def _execute(*a, **k):
        resp = next(respostas)
        r = MagicMock()
        r.scalar_one_or_none.return_value = resp
        r.scalar_one.return_value = resp
        return r

    sessao = AsyncMock()
    sessao.execute = _execute
    sessao.add = MagicMock()

    async def _db():
        yield sessao

    async def _atual():
        return ator

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _atual
    broadcast = AsyncMock()
    with (
        patch("app.core.security.get_redis"),
        patch("app.routers.chat._notify_other_party", new=AsyncMock()),
        patch("app.routers.chat._fala_da_helo_sem_derrubar", new=AsyncMock(return_value=None)),
        patch("app.routers.chat._apply_chat_transition", new=AsyncMock(return_value=None)),
        patch("app.routers.chat.commit_e_notificar", new=AsyncMock()),
        patch("app.routers.chat.register_first_response"),
        patch("app.routers.chat.manager.broadcast", new=broadcast),
        patch.object(
            av.storage, "get_presigned_url", new=AsyncMock(side_effect=_assina_de_mentira)
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post(f"/api/v1/tickets/{chamado.id}/messages", json={"content": "oi"})
    frame = broadcast.await_args_list[0].args[1]
    return r, frame


@pytest.mark.asyncio
async def test_post_devolve_e_transmite_a_foto_do_tecnico():
    criador = _pessoa(UserRole.client)
    tecnico = _pessoa(UserRole.technician)
    chamado = SimpleNamespace(id=uuid.uuid4(), creator_id=criador.id)

    r, frame = await _posta(tecnico, chamado, _mensagem(chamado, tecnico))

    esperado = f"/api/v1/files/tok-avatars/{tecnico.id}.png"
    assert r.status_code == 201, r.text
    assert r.json()["sender_avatar_url"] == esperado
    assert frame["type"] == "message"
    assert frame["data"]["sender_avatar_url"] == esperado


@pytest.mark.asyncio
async def test_post_nunca_devolve_nem_transmite_foto_de_cliente_que_nao_e_o_dono():
    criador = _pessoa(UserRole.client)
    outro_cliente = _pessoa(UserRole.client)
    chamado = SimpleNamespace(id=uuid.uuid4(), creator_id=criador.id)

    r, frame = await _posta(
        _pessoa(UserRole.technician), chamado, _mensagem(chamado, outro_cliente)
    )

    assert r.status_code == 201, r.text
    assert r.json()["sender_avatar_url"] is None
    assert frame["data"]["sender_avatar_url"] is None


# ── O WebSocket ───────────────────────────────────────────────


def _manda_pelo_ws(usuario, chamado, recarregada):
    """Abre a sala, manda uma fala e devolve o payload que a SALA recebeu.

    `recarregada` é a mensagem que o handler relê do banco depois do commit —
    é dela que sai o remetente, e portanto a foto.
    """
    from starlette.testclient import TestClient

    sessao = AsyncMock()

    async def _execute(*a, **k):
        r = MagicMock()
        r.scalar_one_or_none.return_value = chamado
        r.scalar_one.return_value = recarregada
        return r

    sessao.execute = _execute
    sessao.add = MagicMock()

    class _Ctx:
        async def __aenter__(self):
            return sessao

        async def __aexit__(self, *args):
            return False

    async def _auth(token, db):
        return usuario

    with (
        patch("app.routers.chat.AsyncSessionLocal", lambda: _Ctx()),
        patch("app.routers.chat._authenticate_ws", _auth),
        patch("app.routers.chat._notify_other_party", new=AsyncMock()),
        patch("app.routers.chat._fala_da_helo_sem_derrubar", new=AsyncMock(return_value=None)),
        patch("app.routers.chat._apply_chat_transition", new=AsyncMock(return_value=None)),
        patch("app.routers.chat.commit_e_notificar", new=AsyncMock()),
        patch("app.routers.chat.register_first_response"),
        patch("app.routers.chat.chat_backplane.publicar", new=AsyncMock()),
        patch.object(
            av.storage, "get_presigned_url", new=AsyncMock(side_effect=_assina_de_mentira)
        ),
    ):
        tc = TestClient(app)
        with tc.websocket_connect(f"/api/v1/ws/tickets/{chamado.id}?token=x") as ws:
            ws.send_json({"content": "oi"})
            return ws.receive_json()


def test_ws_leva_a_foto_do_tecnico_sem_recarregar():
    criador = _pessoa(UserRole.client)
    tecnico = _pessoa(UserRole.technician)
    chamado = SimpleNamespace(id=uuid.uuid4(), creator_id=criador.id)

    payload = _manda_pelo_ws(tecnico, chamado, _mensagem(chamado, tecnico))

    assert payload["type"] == "message"
    assert payload["data"]["sender_avatar_url"] == f"/api/v1/files/tok-avatars/{tecnico.id}.png"


def test_ws_leva_a_foto_do_criador():
    criador = _pessoa(UserRole.client)
    chamado = SimpleNamespace(id=uuid.uuid4(), creator_id=criador.id)

    payload = _manda_pelo_ws(criador, chamado, _mensagem(chamado, criador))

    assert payload["data"]["sender_avatar_url"] == f"/api/v1/files/tok-avatars/{criador.id}.png"


def test_ws_nunca_leva_a_foto_de_um_cliente_que_nao_e_o_dono():
    """O payload vai igual para toda a sala, cliente incluído.

    Remetente cliente que não é o criador (dado torto, papel trocado): mesmo
    que quem mandou seja da equipe e veja tudo, o payload não pode carregar a
    foto, porque o dono do chamado está na mesma sala e recebe o mesmo frame.
    """
    criador = _pessoa(UserRole.client)
    outro_cliente = _pessoa(UserRole.client)
    chamado = SimpleNamespace(id=uuid.uuid4(), creator_id=criador.id)

    payload = _manda_pelo_ws(
        _pessoa(UserRole.technician), chamado, _mensagem(chamado, outro_cliente)
    )

    assert payload["data"]["sender_avatar_url"] is None


# ── A autorização individual ──────────────────────────────────
#
# A matriz acima parte de quem permitiu. Daqui para baixo, o contrário: sem a
# autorização do DONO da foto, nada de terceiro é assinado — no detalhe, no
# histórico, no POST e no WebSocket. E com ela, nada além do que a matriz já
# deixava.


@pytest.mark.parametrize("papel_do_ator", list(UserRole))
@pytest.mark.parametrize("papel_do_dono", list(UserRole))
def test_sem_autorizacao_ninguem_ve_a_foto_de_outra_pessoa(papel_do_ator, papel_do_dono):
    dono = _pessoa(papel_do_dono, autoriza=False)
    assert not av.foto_visivel_no_chamado(dono, _pessoa(papel_do_ator))


@pytest.mark.parametrize("papel", list(UserRole))
def test_a_propria_foto_no_chamado_nao_depende_da_autorizacao(papel):
    eu = _pessoa(papel, autoriza=False)
    assert av.foto_visivel_no_chamado(eu, eu)


@pytest.mark.parametrize(
    "conta",
    [
        SimpleNamespace(id=uuid.uuid4(), role=UserRole.technician),  # sem o atributo
        _pessoa(UserRole.technician, avatar_visivel_a_terceiros=None),
        _pessoa(UserRole.technician, avatar_visivel_a_terceiros="true"),
        _pessoa(UserRole.technician, avatar_visivel_a_terceiros=1),
        MagicMock(),  # responde a qualquer atributo com algo verdadeiro
    ],
)
def test_o_que_nao_for_o_booleano_gravado_vale_como_nao_autorizou(conta):
    assert not av.exibicao_autorizada(conta)


def test_autorizar_nao_abre_a_foto_de_um_cliente_alheio():
    cliente = _pessoa(UserRole.client)
    outro_cliente = _pessoa(UserRole.client, autoriza=True)
    chamado = SimpleNamespace(creator_id=cliente.id)
    assert not av.foto_visivel_no_chamado(outro_cliente, cliente)
    assert not av.foto_visivel_na_conversa(outro_cliente, chamado)


@pytest.mark.parametrize("papel", list(UserRole))
def test_na_conversa_sem_autorizacao_nem_o_proprio_autor_recebe_a_foto(papel):
    """O payload é um só para a sala: sem permissão, sai sem foto para todos."""
    autor = _pessoa(papel, autoriza=False)
    chamado = SimpleNamespace(creator_id=autor.id)
    assert not av.foto_visivel_na_conversa(autor, chamado)


@pytest.mark.asyncio
async def test_detalhe_sem_autorizacao_do_tecnico_so_assina_a_propria_foto_do_cliente():
    cliente = _pessoa(UserRole.client, autoriza=False)
    tecnico = _pessoa(UserRole.technician, autoriza=False)
    r, assina = await _detalhe(cliente, _chamado(cliente, tecnico), [cliente, tecnico])

    assert r.status_code == 200, r.text
    assert r.json()["assignee_avatar_url"] is None
    assert r.json()["requester"]["avatar_url"] == f"/api/v1/files/tok-avatars/{cliente.id}.png"
    assert [c.args[0] for c in assina.await_args_list] == [f"avatars/{cliente.id}.png"]


@pytest.mark.asyncio
async def test_detalhe_sem_autorizacao_do_cliente_a_equipe_ve_as_iniciais():
    cliente = _pessoa(UserRole.client, autoriza=False)
    tecnico = _pessoa(UserRole.technician, autoriza=False)
    admin = _pessoa(UserRole.admin)
    r, assina = await _detalhe(admin, _chamado(cliente, tecnico), [cliente, tecnico])

    assert r.status_code == 200, r.text
    assert r.json()["requester"]["avatar_url"] is None
    assert r.json()["assignee_avatar_url"] is None
    assina.assert_not_awaited()


@pytest.mark.asyncio
async def test_detalhe_o_responsavel_ve_a_propria_foto_sem_autorizar():
    cliente = _pessoa(UserRole.client, autoriza=False)
    tecnico = _pessoa(UserRole.technician, autoriza=False)
    r, _ = await _detalhe(tecnico, _chamado(cliente, tecnico), [cliente, tecnico])

    assert r.json()["assignee_avatar_url"] == f"/api/v1/files/tok-avatars/{tecnico.id}.png"
    assert r.json()["requester"]["avatar_url"] is None


@pytest.mark.parametrize("papel_do_ator", [UserRole.client, UserRole.technician])
@pytest.mark.asyncio
async def test_historico_sem_autorizacao_nao_assina_ninguem(papel_do_ator):
    criador = _pessoa(UserRole.client, autoriza=False)
    tecnico = _pessoa(UserRole.technician, autoriza=False)
    chamado = SimpleNamespace(id=uuid.uuid4(), creator_id=criador.id)
    ator = criador if papel_do_ator == UserRole.client else tecnico
    msgs = [_mensagem(chamado, tecnico), _mensagem(chamado, criador)]

    r, assina, consultas = await _historico(ator, chamado, msgs)

    assert r.status_code == 200, r.text
    assert [i["sender_avatar_url"] for i in r.json()["items"]] == [None, None]
    assina.assert_not_awaited()
    assert len(consultas) == 3


@pytest.mark.asyncio
async def test_historico_mistura_quem_autorizou_e_quem_nao():
    criador = _pessoa(UserRole.client, autoriza=False)
    tecnico = _pessoa(UserRole.technician, autoriza=True)
    chamado = SimpleNamespace(id=uuid.uuid4(), creator_id=criador.id)
    msgs = [_mensagem(chamado, tecnico), _mensagem(chamado, criador)] * 10

    r, assina, consultas = await _historico(criador, chamado, msgs)

    fotos = [i["sender_avatar_url"] for i in r.json()["items"]]
    assert fotos == [f"/api/v1/files/tok-avatars/{tecnico.id}.png", None] * 10
    assert assina.await_count == 1
    # A autorização é coluna do remetente que já veio no selectinload.
    assert len(consultas) == 3


@pytest.mark.asyncio
async def test_post_sem_autorizacao_nao_devolve_nem_transmite_foto():
    criador = _pessoa(UserRole.client)
    tecnico = _pessoa(UserRole.technician, autoriza=False)
    chamado = SimpleNamespace(id=uuid.uuid4(), creator_id=criador.id)

    r, frame = await _posta(tecnico, chamado, _mensagem(chamado, tecnico))

    assert r.status_code == 201, r.text
    assert r.json()["sender_avatar_url"] is None
    assert frame["data"]["sender_avatar_url"] is None


def test_ws_sem_autorizacao_nao_leva_a_foto():
    criador = _pessoa(UserRole.client, autoriza=False)
    chamado = SimpleNamespace(id=uuid.uuid4(), creator_id=criador.id)

    payload = _manda_pelo_ws(criador, chamado, _mensagem(chamado, criador))

    assert payload["data"]["sender_avatar_url"] is None


def _manda_varias_pelo_ws(usuario, chamado, recarregadas):
    """Uma sala aberta UMA vez, uma fala por mensagem relida.

    A conexão autentica `usuario` ao abrir e guarda esse objeto até fechar. Cada
    item de `recarregadas` é o que o banco devolve na releitura daquela fala —
    é como uma revogação feita no meio da conversa chega ao handler.
    """
    from starlette.testclient import TestClient

    atual: dict = {"msg": None}
    sessao = AsyncMock()

    async def _execute(*a, **k):
        r = MagicMock()
        r.scalar_one_or_none.return_value = chamado
        r.scalar_one.return_value = atual["msg"]
        return r

    sessao.execute = _execute
    sessao.add = MagicMock()

    class _Ctx:
        async def __aenter__(self):
            return sessao

        async def __aexit__(self, *args):
            return False

    async def _auth(token, db):
        return usuario

    recebidos = []
    with (
        patch("app.routers.chat.AsyncSessionLocal", lambda: _Ctx()),
        patch("app.routers.chat._authenticate_ws", _auth),
        patch("app.routers.chat._notify_other_party", new=AsyncMock()),
        patch("app.routers.chat._fala_da_helo_sem_derrubar", new=AsyncMock(return_value=None)),
        patch("app.routers.chat._apply_chat_transition", new=AsyncMock(return_value=None)),
        patch("app.routers.chat.commit_e_notificar", new=AsyncMock()),
        patch("app.routers.chat.register_first_response"),
        patch("app.routers.chat.chat_backplane.publicar", new=AsyncMock()),
        patch.object(
            av.storage, "get_presigned_url", new=AsyncMock(side_effect=_assina_de_mentira)
        ),
    ):
        tc = TestClient(app)
        with tc.websocket_connect(f"/api/v1/ws/tickets/{chamado.id}?token=x") as ws:
            for msg in recarregadas:
                atual["msg"] = msg
                ws.send_json({"content": "oi"})
                recebidos.append(ws.receive_json())
    return recebidos


def test_ws_aberto_antes_da_revogacao_nao_emite_foto_depois_dela():
    """A sala abriu com a pessoa autorizada; ela revogou; a fala seguinte sai sem foto.

    O `usuario` da conexão continua dizendo "autorizado" até o fim — é o objeto
    velho que o socket guardou. O que decide é o remetente relido do banco.
    """
    tecnico = _pessoa(UserRole.technician, autoriza=True)
    chamado = SimpleNamespace(id=uuid.uuid4(), creator_id=uuid.uuid4())
    antes = _mensagem(chamado, tecnico)
    depois_de_revogar = SimpleNamespace(**vars(tecnico))
    depois_de_revogar.avatar_visivel_a_terceiros = False
    depois = _mensagem(chamado, depois_de_revogar)

    recebidos = _manda_varias_pelo_ws(tecnico, chamado, [antes, depois])

    assert tecnico.avatar_visivel_a_terceiros is True  # a cópia da conexão
    assert recebidos[0]["data"]["sender_avatar_url"] == (
        f"/api/v1/files/tok-avatars/{tecnico.id}.png"
    )
    assert recebidos[1]["data"]["sender_avatar_url"] is None


def test_ws_aberto_antes_de_autorizar_passa_a_emitir_depois():
    criador = _pessoa(UserRole.client, autoriza=False)
    chamado = SimpleNamespace(id=uuid.uuid4(), creator_id=criador.id)
    autorizado = SimpleNamespace(**vars(criador))
    autorizado.avatar_visivel_a_terceiros = True

    recebidos = _manda_varias_pelo_ws(
        criador, chamado, [_mensagem(chamado, criador), _mensagem(chamado, autorizado)]
    )

    assert recebidos[0]["data"]["sender_avatar_url"] is None
    assert recebidos[1]["data"]["sender_avatar_url"] == (
        f"/api/v1/files/tok-avatars/{criador.id}.png"
    )


# ── Conta não ativa ───────────────────────────────────────────
#
# O dono da foto precisa estar ATIVO para ela sair para terceiros. Não é
# revogação: a escolha gravada fica como está.


@pytest.mark.parametrize("situacao", [UserStatus.inactive, UserStatus.anonymized])
@pytest.mark.parametrize("papel_do_ator", list(UserRole))
def test_conta_nao_ativa_nao_aparece_no_chamado_mesmo_autorizada(situacao, papel_do_ator):
    dono = _pessoa(UserRole.technician, autoriza=True, status=situacao)
    ator = _pessoa(papel_do_ator)

    assert av.foto_visivel_no_chamado(dono, ator) is False
    assert dono.avatar_visivel_a_terceiros is True


@pytest.mark.parametrize("situacao", [UserStatus.inactive, UserStatus.anonymized])
def test_conta_nao_ativa_nao_aparece_na_conversa_mesmo_autorizada(situacao):
    criador = _pessoa(UserRole.client, autoriza=True, status=situacao)
    tecnico = _pessoa(UserRole.technician, autoriza=True, status=situacao)
    chamado = SimpleNamespace(id=uuid.uuid4(), creator_id=criador.id)

    assert av.foto_visivel_na_conversa(criador, chamado) is False
    assert av.foto_visivel_na_conversa(tecnico, chamado) is False


@pytest.mark.parametrize("situacao", [None, "active", "desconhecido"])
def test_status_que_nao_e_o_ativo_de_verdade_cai_para_as_iniciais(situacao):
    dono = _pessoa(UserRole.technician, autoriza=True)
    dono.status = situacao
    assert av.foto_visivel_no_chamado(dono, _pessoa(UserRole.client)) is (situacao == "active")


def test_ws_aberto_antes_da_desativacao_nao_emite_foto_depois_dela():
    """A conexão abriu com a conta ativa e guarda esse objeto até o fim; a
    conta foi desativada; a fala seguinte é serializada pelo remetente RELIDO."""
    tecnico = _pessoa(UserRole.technician, autoriza=True)
    chamado = SimpleNamespace(id=uuid.uuid4(), creator_id=uuid.uuid4())
    desativado = SimpleNamespace(**vars(tecnico))
    desativado.status = UserStatus.inactive

    recebidos = _manda_varias_pelo_ws(
        tecnico, chamado, [_mensagem(chamado, tecnico), _mensagem(chamado, desativado)]
    )

    assert tecnico.status == UserStatus.active  # a cópia da conexão
    assert recebidos[0]["data"]["sender_avatar_url"] == (
        f"/api/v1/files/tok-avatars/{tecnico.id}.png"
    )
    assert recebidos[1]["data"]["sender_avatar_url"] is None
