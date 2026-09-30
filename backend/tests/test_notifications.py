"""
Tests for the Notification service and endpoints.
DB and Redis are fully mocked.
"""

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from loguru import logger

from app.main import app
from app.models.models import EmailOutbox, Notification, NotificationType, UserRole, UserStatus

# ── Fake Redis ────────────────────────────────────────────────


class _FakeRedis:
    def __init__(self):
        self._store: dict = {}

    async def setex(self, k, t, v):
        self._store[k] = v

    async def get(self, k):
        return self._store.get(k)

    async def delete(self, k):
        self._store.pop(k, None)

    async def exists(self, k):
        return 1 if k in self._store else 0


_redis = _FakeRedis()


async def _get_redis():
    return _redis


# ── Constants ─────────────────────────────────────────────────

_NOW = datetime.now(UTC)
_USER_ID = uuid.uuid4()
_NOTIF_ID = uuid.uuid4()


# ── Mock builders ─────────────────────────────────────────────


def _mock_user(role=UserRole.client, user_id=None):
    u = MagicMock()
    u.id = user_id or _USER_ID
    u.email = "user@test.com"
    u.role = role
    u.status = UserStatus.active
    return u


def _mock_notif(read=False, user_id=None):
    n = MagicMock()
    n.id = _NOTIF_ID
    n.user_id = user_id or _USER_ID
    n.type = NotificationType.ticket_created
    n.title = "Ticket aberto"
    n.message = "Seu ticket foi registrado."
    n.data = {"ticket_id": str(uuid.uuid4())}
    n.read = read
    n.read_at = _NOW if read else None
    n.email_sent = False
    n.created_at = _NOW
    return n


# ── DB session factories ──────────────────────────────────────


def _db(lookup=None, count=0, unread=0):
    call_count = [0]

    async def _execute(*args, **kwargs):
        call_count[0] += 1
        result = MagicMock()
        # 1st call: total count, 2nd call: unread count, 3rd call: list
        if call_count[0] == 1:
            result.scalar_one.return_value = count
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = []
        elif call_count[0] == 2:
            result.scalar_one.return_value = unread
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = []
        else:
            result.scalar_one_or_none.return_value = lookup
            result.scalar_one.return_value = 0
            result.scalars.return_value.all.return_value = [lookup] if lookup else []
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


def _db_single(lookup=None):
    """Simple single-lookup mock."""

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = lookup
        result.scalar_one.return_value = 0
        result.scalars.return_value.all.return_value = [lookup] if lookup else []
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


def _db_override_custom(session):
    async def _gen():
        yield session

    return _gen


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def patch_redis():
    with patch("app.core.security.get_redis", new=_get_redis):
        yield


def _override_user(user):
    from app.core.security import get_current_user

    async def _u():
        return user

    app.dependency_overrides[get_current_user] = _u


# ═══════════════════════════════════════════════════════════════
# Notification service unit tests
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_notify_adds_notification_to_session():
    from app.services.notifications import notify

    db = MagicMock()
    db.add = MagicMock()

    async def _execute(*a, **kw):
        r = MagicMock()
        r.scalar_one_or_none.return_value = "user@test.com"
        return r

    db.execute = _execute

    await notify(
        db,
        _USER_ID,
        NotificationType.ticket_created,
        "Ticket aberto",
        "Protocolo HS-2026-0001",
    )

    db.add.assert_called_once()  # sem settings, só a Notification
    notif_obj = db.add.call_args[0][0]
    assert notif_obj.user_id == _USER_ID
    assert notif_obj.type == NotificationType.ticket_created
    assert notif_obj.read is False


@pytest.mark.asyncio
async def test_notify_enfileira_o_email_na_mesma_sessao():
    """Fase 3B: `notify()` não registra pendência nenhuma — ele ADICIONA a

    linha da outbox à sessão, junto com a `Notification`, as duas antes do
    commit. Nenhum envio acontece aqui: `commit_e_notificar` só commita, e
    quem manda de verdade é o worker, em outro módulo.
    """
    from app.core.config import get_settings
    from app.services import notifications

    db = _db_para_notify("user@test.com")
    settings = get_settings()

    await notifications.notify(
        db,
        _USER_ID,
        NotificationType.ticket_created,
        "Ticket aberto",
        "Protocolo HS-2026-0001",
        settings=settings,
    )

    assert db.add.call_count == 2, "Notification e EmailOutbox, a mesma sessão"
    notif_obj = db.add.call_args_list[0].args[0]
    outbox_obj = db.add.call_args_list[1].args[0]
    assert isinstance(notif_obj, Notification)
    assert isinstance(outbox_obj, EmailOutbox)
    assert outbox_obj.notification_id == notif_obj.id
    assert outbox_obj.status == "pending"

    await notifications.commit_e_notificar(db)
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_notify_no_email_task_without_settings():
    from app.services.notifications import notify

    db = MagicMock()
    db.add = MagicMock()

    async def _execute(*a, **kw):
        r = MagicMock()
        r.scalar_one_or_none.return_value = "user@test.com"
        return r

    db.execute = _execute

    await notify(db, _USER_ID, NotificationType.ticket_created, "Title", "Body")

    db.add.assert_called_once()  # sem settings, nenhuma linha de outbox


@pytest.mark.asyncio
async def test_pesquisa_de_satisfacao_nao_vai_por_email():
    """
    O convite para avaliar fica só no sininho: a avaliação é respondida dentro
    do chamado, e o e-mail apenas pedia que a pessoa entrasse no sistema.
    """
    from app.core.config import get_settings
    from app.services.notifications import notify

    db = MagicMock()
    db.add = MagicMock()

    async def _execute(*a, **kw):
        r = MagicMock()
        r.scalar_one_or_none.return_value = "user@test.com"
        return r

    db.execute = _execute

    await notify(
        db,
        _USER_ID,
        NotificationType.satisfaction_survey,
        "Como foi o atendimento?",
        "O ticket HS-2026-0010 foi resolvido.",
        settings=get_settings(),
    )

    db.add.assert_called_once()  # a notificação no sininho continua existindo, sem outbox


# ═══════════════════════════════════════════════════════════════
# Email service unit tests
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_send_email_skips_when_not_configured():
    from app.core.config import Settings
    from app.services.email import send_email

    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        smtp_from_email="",
        smtp_user="",
    )
    result = await send_email("user@test.com", "Subject", "Body", settings)
    assert result is False


@pytest.mark.asyncio
async def test_send_email_handles_smtp_failure():
    from app.core.config import Settings
    from app.services.email import send_email

    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        smtp_from_email="from@test.com",
        smtp_user="from@test.com",
        smtp_host="localhost",
        smtp_port=1025,
    )

    with patch("app.services.email._get_mail_client") as mock_client:
        mock_fm = AsyncMock()
        mock_fm.send_message = AsyncMock(side_effect=Exception("SMTP error"))
        mock_client.return_value = mock_fm

        result = await send_email("to@test.com", "Subject", "Body", settings)

    assert result is False


# ═══════════════════════════════════════════════════════════════
# Notification endpoint tests
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_notifications(patch_redis):
    from app.core.database import get_db

    user = _mock_user()
    notif = _mock_notif()
    session = _db(lookup=notif, count=1, unread=1)

    # Override list query to return items
    call_count = [0]

    async def _patched_execute(*args, **kwargs):
        call_count[0] += 1
        result = MagicMock()
        if call_count[0] == 1:
            result.scalar_one.return_value = 1  # total
        elif call_count[0] == 2:
            result.scalar_one.return_value = 1  # unread
        else:
            result.scalars.return_value.all.return_value = [notif]
        return result

    session.execute = _patched_execute
    app.dependency_overrides[get_db] = _db_override_custom(session)
    _override_user(user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/notifications")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["unread"] == 1


@pytest.mark.asyncio
async def test_mark_read(patch_redis):
    from app.core.database import get_db

    user = _mock_user(user_id=_USER_ID)
    notif = _mock_notif(read=False, user_id=_USER_ID)
    session = _db_single(notif)
    app.dependency_overrides[get_db] = _db_override_custom(session)
    _override_user(user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/notifications/{_NOTIF_ID}/read")

    assert resp.status_code == 200
    assert notif.read is True


@pytest.mark.asyncio
async def test_mark_all_read(patch_redis):
    from app.core.database import get_db

    user = _mock_user(user_id=_USER_ID)
    session = _db_single()
    app.dependency_overrides[get_db] = _db_override_custom(session)
    _override_user(user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch("/api/v1/notifications/read-all")

    assert resp.status_code == 204
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_notification(patch_redis):
    from app.core.database import get_db

    user = _mock_user(user_id=_USER_ID)
    notif = _mock_notif(user_id=_USER_ID)
    session = _db_single(notif)
    app.dependency_overrides[get_db] = _db_override_custom(session)
    _override_user(user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/notifications/{_NOTIF_ID}")

    assert resp.status_code == 204
    session.delete.assert_called_once_with(notif)


@pytest.mark.asyncio
async def test_delete_notification_other_user(patch_redis):
    """Notification belonging to another user returns 404."""
    from app.core.database import get_db

    user = _mock_user(user_id=uuid.uuid4())  # different user
    session = _db_single(None)  # query filters by user_id → returns None
    app.dependency_overrides[get_db] = _db_override_custom(session)
    _override_user(user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/notifications/{_NOTIF_ID}")

    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════
# Diagnóstico: o log de email precisa dizer PARA QUEM e POR QUÊ
# ═══════════════════════════════════════════════════════════════


@contextmanager
def _capturar_log():
    """Coleta as linhas já formatadas que o loguru emite dentro do bloco."""
    linhas: list[str] = []
    sink_id = logger.add(linhas.append, format="{message}", level="DEBUG")
    try:
        yield linhas
    finally:
        logger.remove(sink_id)


@pytest.mark.asyncio
async def test_log_de_falha_de_email_diz_o_contexto_e_o_tipo_do_erro():
    """
    Quando alguém reclama que não recebeu o email, a linha de log é a única
    pista que existe. Se ela sair com o placeholder literal, os argumentos são
    descartados e a linha não serve para nada.

    ⚠️ ESTE TESTE MUDOU DE IDENTIFICADOR EM 25/09/2026, e a versão anterior
    exigia o contrário do que esta exige.

    Ele se chamava `..._diz_o_destinatario_e_o_motivo` e afirmava o endereço e a
    mensagem da exceção dentro da linha. A intenção era boa e continua valendo —
    "sem rastro a linha não serve" —, mas o rastro escolhido era dado pessoal:
    com SMTP ligado, cada falha punha o endereço do cliente no log de produção,
    e `str(exc)` de `SMTPRecipientRefused` põe o destinatário mesmo quando
    ninguém interpola `{to_email}`.

    A invariante que sobrevive é a do docstring original: a linha tem de estar
    INTERPOLADA e tem de dizer o suficiente para diagnosticar. O que mudou é o
    que conta como suficiente — contexto interno e classe do erro, em vez de
    endereço e texto de servidor.
    """
    from app.core.config import Settings
    from app.services.email import send_email

    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        smtp_from_email="from@test.com",
        smtp_user="from@test.com",
        smtp_host="localhost",
        smtp_port=1025,
        smtp_reply_to="noreply@test.com",
    )

    with patch("app.services.email._get_mail_client") as mock_client:
        mock_fm = AsyncMock()
        mock_fm.send_message = AsyncMock(side_effect=ValueError("conexao recusada"))
        mock_client.return_value = mock_fm

        with _capturar_log() as linhas:
            enviado = await send_email(
                "quem.reclamou@test.com",
                "Assunto",
                "Corpo",
                settings,
                contexto="notification abc-123",
            )

    assert enviado is False
    falhas = [linha for linha in linhas if "SMTP delivery failed" in linha]
    assert falhas, f"a falha de entrega não foi registrada: {linhas}"
    # Interpolada, não literal — a razão original deste teste existir.
    assert "{contexto}" not in falhas[0]
    assert "notification abc-123" in falhas[0]
    assert "ValueError" in falhas[0], "sem a classe do erro a linha não diagnostica nada"
    # E o que NÃO pode estar ali.
    assert "quem.reclamou@test.com" not in falhas[0]
    assert "conexao recusada" not in falhas[0]
    assert "Assunto" not in falhas[0]


# A dívida "log de não-entrega diz o id, não o destinatário" continua provada
# desde a Fase 3B — só que o id correlator passou a ser o `outbox_id` (não
# mais o `notif_id`, porque quem envia é o worker da outbox, não mais
# `notifications._send_and_log`, que não existe). O equivalente mora em
# `tests/test_email_outbox_postgres.py::test_logs_do_ciclo_completo_sem_pii` e
# `test_sucesso_nao_vaza_endereco_so_o_outbox_id`.


@pytest.mark.asyncio
async def test_email_sai_mesmo_sem_reply_to_configurado():
    """
    SMTP_REPLY_TO é opcional e nasce vazio. Passar reply_to=None para o
    MessageSchema derruba a montagem da mensagem ANTES de qualquer tentativa
    de entrega — todo email falharia no dia em que o SMTP for configurado,
    e o except engoliria o erro como se fosse falha de entrega.
    """
    from app.core.config import Settings
    from app.services.email import send_email

    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        smtp_from_email="from@test.com",
        smtp_user="from@test.com",
        smtp_host="localhost",
        smtp_port=1025,
        smtp_reply_to="",
    )

    with patch("app.services.email._get_mail_client") as mock_client:
        mock_fm = AsyncMock()
        mock_client.return_value = mock_fm
        enviado = await send_email("destino@test.com", "Assunto", "Corpo", settings)

    assert enviado is True
    mock_fm.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_reply_to_configurado_continua_indo_na_mensagem():
    """A correção acima não pode virar 'apagar o reply_to'."""
    from app.core.config import Settings
    from app.services.email import send_email

    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        smtp_from_email="from@test.com",
        smtp_user="from@test.com",
        smtp_host="localhost",
        smtp_port=1025,
        smtp_reply_to="suporte@test.com",
    )

    with patch("app.services.email._get_mail_client") as mock_client:
        mock_fm = AsyncMock()
        mock_client.return_value = mock_fm
        enviado = await send_email("destino@test.com", "Assunto", "Corpo", settings)

    assert enviado is True
    mensagem = mock_fm.send_message.await_args.args[0]
    assert mensagem.reply_to == ["suporte@test.com"]


# ═══════════════════════════════════════════════════════════════
# O e-mail não pode sair antes de o fato existir
# ═══════════════════════════════════════════════════════════════


def _db_para_notify(email="destino@test.com", papel=UserRole.client, nome="Welton Silva"):
    """Sessão mockada que devolve o destinatário na busca do notify().

    Passou a carregar o PAPEL junto do e-mail em 04/09/2026: quem decide o
    envio deixou de ser só o tipo da notificação e passou a ser também quem
    recebe. O padrão é `client` porque é o único que continua recebendo.
    """

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.one_or_none.return_value = (email, papel, nome)
        result.scalar_one_or_none.return_value = email
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_notify_e_commit_nunca_chamam_smtp():
    """A garantia central da Fase 3B: nenhuma chamada SMTP acontece antes,

    durante, ou logo depois do commit que cria a `Notification`. `notify()` e
    `commit_e_notificar()` não importam `send_email`/`send_email_detalhado` —
    quem manda é o worker da outbox, num ciclo separado. Patch no lugar onde a
    função REALMENTE mora (`app.services.email`), não em
    `app.services.notifications`, que não tem mais esse nome — é a prova de
    que o caminho de código nem passa por lá.
    """
    from app.core.config import Settings
    from app.services import notifications

    settings = Settings(database_url="postgresql+asyncpg://u:p@localhost/db")
    db = _db_para_notify()

    with patch("app.services.email.send_email_detalhado", new=AsyncMock()) as enviar:
        await notifications.notify(
            db,
            _USER_ID,
            NotificationType.ticket_updated,
            "Assunto",
            "Corpo",
            settings=settings,
        )
        await notifications.commit_e_notificar(db)

    enviar.assert_not_awaited()
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_commit_e_notificar_propaga_falha_do_commit():
    """O chamador (o laço de protocolo de `create_ticket`, por exemplo)

    depende de `commit_e_notificar` propagar a exceção do `db.commit()` para
    decidir se tenta de novo. `commit_e_notificar` não tem mais nada próprio
    para fazer além de commitar — a propagação é direta.
    """
    from app.core.config import Settings
    from app.services import notifications

    settings = Settings(database_url="postgresql+asyncpg://u:p@localhost/db")
    db = _db_para_notify()
    db.commit = AsyncMock(side_effect=RuntimeError("deu ruim no commit"))

    await notifications.notify(
        db,
        _USER_ID,
        NotificationType.ticket_updated,
        "Assunto",
        "Corpo",
        settings=settings,
    )
    with pytest.raises(RuntimeError):
        await notifications.commit_e_notificar(db)


@pytest.mark.asyncio
async def test_commit_e_notificar_so_commita():
    """Nenhum `asyncio.create_task`, nenhuma chamada a `send_email`: depois da

    Fase 3B, `commit_e_notificar` é `await db.commit()` e mais nada.
    """
    from app.core.config import Settings
    from app.services import notifications

    settings = Settings(database_url="postgresql+asyncpg://u:p@localhost/db")
    db = _db_para_notify()

    await notifications.notify(
        db,
        _USER_ID,
        NotificationType.ticket_updated,
        "Assunto",
        "Corpo",
        settings=settings,
    )
    await notifications.commit_e_notificar(db)
    await notifications.commit_e_notificar(db)

    assert db.commit.await_count == 2, "cada chamada commita de novo — nada é consumido"


@pytest.mark.asyncio
async def test_pendencias_nao_vazam_entre_sessoes():
    """Duas sessões independentes recebem cada uma só a SUA `Notification` +

    `EmailOutbox` — não existe mais estado global compartilhado entre
    requisições (o `_PENDENTES` chaveado por sessão que existia até a Fase 3A
    não existe mais: `enqueue_email` escreve direto na sessão recebida).
    """
    from app.core.config import Settings
    from app.services import notifications

    settings = Settings(database_url="postgresql+asyncpg://u:p@localhost/db")
    db_a = _db_para_notify("a@test.com")
    db_b = _db_para_notify("b@test.com")

    await notifications.notify(
        db_a, _USER_ID, NotificationType.ticket_updated, "A", "corpo", settings=settings
    )

    assert db_a.add.call_count == 2  # Notification + EmailOutbox
    db_b.add.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# Quem recebe e-mail, e quem só recebe no sininho
# ═══════════════════════════════════════════════════════════════
#
# Decidido em 04/09/2026. Técnico e admin vivem dentro do sistema o dia
# inteiro; o sininho já os avisa, e o e-mail virava ruído. O que chegava a
# eles eram dois eventos: ser designado a um chamado, e um cliente reabrir
# chamado sob sua responsabilidade.
#
# Para o CLIENTE nada muda, e o teste do cliente existe para prender isso.
# Sem ele, um engano que silenciasse TODO mundo passaria despercebido — e o
# cliente é justamente quem não vive aqui dentro e depende do e-mail para
# saber que o chamado andou.


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", [UserRole.technician, UserRole.admin])
async def test_staff_nao_recebe_notificacao_por_email(papel):
    """A notificação continua existindo no sininho; só a outbox para de nascer."""
    from app.core.config import get_settings
    from app.services import notifications

    db = _db_para_notify("tecnico@test.com", papel=papel)

    await notifications.notify(
        db,
        _USER_ID,
        NotificationType.ticket_updated,
        "Ticket atualizado",
        "O chamado HS-2026-0001 mudou de status.",
        settings=get_settings(),
    )
    await notifications.commit_e_notificar(db)

    db.add.assert_called_once()  # só a Notification, sem EmailOutbox


@pytest.mark.asyncio
async def test_cliente_continua_recebendo_notificacao_por_email():
    """Contraprova do teste acima: o que silencia é o PAPEL, e não o tipo.

    Se este par cair junto com o de cima, a mudança silenciou todo mundo em
    vez de silenciar só a equipe.
    """
    from app.core.config import get_settings
    from app.services import notifications

    db = _db_para_notify("cliente@test.com", papel=UserRole.client)

    await notifications.notify(
        db,
        _USER_ID,
        NotificationType.ticket_updated,
        "Ticket atualizado",
        "O chamado HS-2026-0001 mudou de status.",
        settings=get_settings(),
    )
    await notifications.commit_e_notificar(db)

    assert db.add.call_count == 2  # Notification + EmailOutbox
    outbox_obj = db.add.call_args_list[1].args[0]
    assert isinstance(outbox_obj, EmailOutbox)


@pytest.mark.asyncio
async def test_o_chat_para_de_encher_a_caixa_do_tecnico():
    """O caso que motivou a mudança: dez mensagens do cliente eram dez outbox."""
    from app.core.config import get_settings
    from app.services import notifications

    db = _db_para_notify("tecnico@test.com", papel=UserRole.technician)

    for i in range(10):
        await notifications.notify(
            db,
            _USER_ID,
            NotificationType.chat_message,
            "Nova mensagem",
            f"mensagem {i}",
            settings=get_settings(),
        )
    await notifications.commit_e_notificar(db)

    assert db.add.call_count == 10, "as dez continuam no sininho, nenhuma outbox"


@pytest.mark.asyncio
async def test_destinatario_que_nao_existe_mais_nao_derruba_o_notify():
    """Usuário apagado entre a ação e a notificação: não pode virar exceção."""
    from app.core.config import get_settings
    from app.services import notifications

    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.one_or_none.return_value = None
        return result

    db.execute = _execute

    await notifications.notify(
        db,
        _USER_ID,
        NotificationType.ticket_updated,
        "Ticket atualizado",
        "corpo",
        settings=get_settings(),
    )
    await notifications.commit_e_notificar(db)

    db.add.assert_called_once()  # só a Notification — sem destinatário, sem outbox


# ═══════════════════════════════════════════════════════════════
# O e-mail leva ao chamado, e o assunto diz qual é
# ═══════════════════════════════════════════════════════════════
#
# Levantado em 04/09/2026: doze dos catorze e-mails de notificação chegavam
# sem link. O `data` da notificação sempre carregou o `ticket_id` — as catorze
# chamadas passam —, mas ele não chegava ao e-mail. A pessoa lia que o chamado
# andou e tinha de entrar no sistema e procurar.
#
# O assunto tinha o mesmo defeito na lista da caixa: "Ticket resolvido" não diz
# QUAL. Com cinco chamados abertos, cinco e-mails idênticos.
#
# Nada disto muda o sininho: `title` e `message` continuam sendo gravados na
# Notification como sempre foram. O que muda é só o que sai por e-mail.
#
# Desde a Fase 3B, `_mensagem_do_email`/`_assunto_do_email` não são mais
# chamadas por `notify()` — são chamadas pelo worker da outbox, em tempo de
# envio (`app/services/email_outbox.py:_conteudo_do_email`). Os testes abaixo
# passaram a chamá-las DIRETO: são funções puras, e testá-las por trás de
# `notify()` + um mock de `send_email` só adicionava uma camada de indireção
# sem provar nada a mais.


@pytest.mark.asyncio
async def test_o_email_leva_o_link_do_chamado():
    from app.core.config import get_settings
    from app.services.email_layout import em_texto
    from app.services.notifications import _mensagem_do_email

    settings = get_settings()
    ticket_id = str(uuid.uuid4())

    mensagem = _mensagem_do_email(
        "Chamado resolvido",
        "O chamado HS-2026-0042 foi marcado como resolvido.",
        {"ticket_id": ticket_id, "protocol": "HS-2026-0042"},
        "Cliente",
        settings,
    )
    corpo = em_texto(mensagem)

    assert f"{settings.frontend_url.rstrip('/')}/tickets/{ticket_id}" in corpo
    assert (
        "O chamado HS-2026-0042 foi marcado como resolvido." in corpo
    ), "a mensagem original tem que continuar no corpo"


def test_o_assunto_diz_de_qual_chamado_se_trata():
    from app.services.notifications import _assunto_do_email

    assunto = _assunto_do_email("Chamado resolvido", {"protocol": "HS-2026-0042"})

    assert assunto.startswith("[HelpHS]"), f"sem o prefixo da casa: {assunto}"
    assert "HS-2026-0042" in assunto, f"o assunto não diz qual chamado: {assunto}"
    assert "Chamado resolvido" in assunto


def test_sem_protocolo_o_assunto_ainda_sai_util():
    """Cinco chamadas não carregam `protocol` no data — não podem quebrar."""
    from app.services.notifications import _assunto_do_email

    assunto = _assunto_do_email("Chamado reaberto", {"new_status": "in_progress"})

    assert assunto == "[HelpHS] Chamado reaberto"


@pytest.mark.asyncio
async def test_protocolo_ausente_nao_impede_o_link():
    from app.core.config import get_settings
    from app.services.email_layout import em_texto
    from app.services.notifications import _mensagem_do_email

    ticket_id = str(uuid.uuid4())
    mensagem = _mensagem_do_email(
        "Chamado reaberto",
        "corpo qualquer",
        {"ticket_id": ticket_id, "new_status": "in_progress"},
        None,
        get_settings(),
    )

    assert "/tickets/" in em_texto(mensagem), "sem protocolo, o link ainda tem que sair"


@pytest.mark.asyncio
async def test_notificacao_sem_chamado_nao_inventa_link():
    """Contraprova: sem `ticket_id` no data, o corpo é a mensagem e nada mais."""
    from app.core.config import get_settings
    from app.services.email_layout import em_texto
    from app.services.notifications import _mensagem_do_email

    mensagem = _mensagem_do_email(
        "Aviso do sistema",
        "Manutenção programada para sábado.",
        None,
        None,
        get_settings(),
    )
    corpo = em_texto(mensagem)

    assert "Manutenção programada para sábado." in corpo
    assert "/tickets/" not in corpo, "sem ticket_id, não pode inventar link"


@pytest.mark.asyncio
async def test_o_sininho_nao_muda():
    """O que a Notification grava continua sendo o título e a mensagem crus.

    O prefixo `[HelpHS]` e o link são coisa de e-mail, construída só pelo
    worker no momento do envio — nunca chegam perto da `Notification`.
    """
    from app.core.config import get_settings
    from app.services import notifications

    db = _db_para_notify("cliente@test.com")

    await notifications.notify(
        db,
        _USER_ID,
        NotificationType.ticket_updated,
        "Chamado resolvido",
        "O chamado HS-2026-0042 foi marcado como resolvido.",
        data={"ticket_id": str(uuid.uuid4()), "protocol": "HS-2026-0042"},
        settings=get_settings(),
    )

    gravada = db.add.call_args_list[0].args[0]  # a Notification, primeiro add
    assert gravada.title == "Chamado resolvido"
    assert gravada.message == "O chamado HS-2026-0042 foi marcado como resolvido."


# ═══════════════════════════════════════════════════════════════
# O FILTRO POR PAPEL, E A EXCEÇÃO POR TIPO
# ═══════════════════════════════════════════════════════════════
#
# Dois filtros independentes decidem se sai e-mail:
#
#   _IN_APP_ONLY          — por TIPO, vale para todo mundo
#   _SEM_EMAIL_POR_PAPEL  — por PAPEL, com exceções em _EMAIL_PARA_STAFF
#
# Estes testes batem direto na função de decisão, sem passar por sessão nem
# por endpoint: é regra de negócio pura, e um teste que precisasse de mock
# aqui estaria medindo o mock.


@pytest.mark.parametrize(
    "papel",
    [UserRole.client, UserRole.technician, UserRole.admin],
)
def test_chamado_novo_manda_email_para_todos_os_papeis(papel):
    """A exceção da Fase 1: staff volta a receber e-mail — SÓ de chamado novo."""
    from app.services.notifications import _pode_mandar_email

    assert _pode_mandar_email(NotificationType.ticket_created, papel) is True


def test_sem_destinatario_nao_enfileira_mesmo_com_tudo_mais_liberado():
    """`to_email` vazio barra o enfileiramento mesmo quando tipo e papel

    liberariam e-mail — cobre o `notify()` que encontrou o destinatário (a
    tupla não é `None`) mas o e-mail veio vazio, caso distinto de
    "destinatário sumiu" (que `notify()` já intercepta antes de chegar aqui)."""
    from app.core.config import get_settings
    from app.services.notifications import _deve_enfileirar_email

    assert (
        _deve_enfileirar_email(NotificationType.ticket_updated, UserRole.client, "", get_settings())
        is False
    )
    assert (
        _deve_enfileirar_email(
            NotificationType.ticket_updated, UserRole.client, None, get_settings()
        )
        is False
    )


@pytest.mark.parametrize("papel", [UserRole.technician, UserRole.admin])
@pytest.mark.parametrize(
    "tipo",
    [
        NotificationType.ticket_assigned,
        # A REABERTURA usa `ticket_updated`, e não um tipo próprio — o enum
        # agrega mais de um evento de domínio. Ver a dívida registrada em
        # docs/decisoes-e-regras.md.
        NotificationType.ticket_updated,
    ],
)
def test_staff_nao_recebe_email_dos_outros_tipos(tipo, papel):
    """A decisão de 04/09/2026 continua valendo fora do chamado novo."""
    from app.services.notifications import _pode_mandar_email

    assert _pode_mandar_email(tipo, papel) is False


@pytest.mark.parametrize(
    "tipo",
    [NotificationType.ticket_assigned, NotificationType.ticket_updated],
)
def test_cliente_recebe_email_de_tudo(tipo):
    """A CONTRAPROVA, e ela é o teste mais importante deste bloco.

    Sem ela, alargar o filtro por papel para incluir `client` — ou trocar a
    saída antecipada por um `return False` — silenciaria o cliente e nenhum
    outro teste reclamaria. O cliente é justamente quem não vive aqui dentro:
    para ele o e-mail é como fica sabendo que o chamado andou.
    """
    from app.services.notifications import _pode_mandar_email

    assert _pode_mandar_email(tipo, UserRole.client) is True


def test_a_pesquisa_de_satisfacao_nao_passa_pelo_filtro_de_papel():
    """`_IN_APP_ONLY` é decidido ANTES, no notify — nem o cliente recebe.

    Este teste existe para que a exceção por papel não seja confundida com um
    passe livre: acrescentar `satisfaction_survey` a `_EMAIL_PARA_STAFF` não
    faria e-mail de CSAT sair, porque o outro filtro já barrou.
    """
    from app.services.notifications import _IN_APP_ONLY

    assert NotificationType.satisfaction_survey in _IN_APP_ONLY


# ═══════════════════════════════════════════════════════════════
# NOTIFICAÇÃO EM LOTE — DEDUPLICAÇÃO E AUSÊNCIA DE N+1
# ═══════════════════════════════════════════════════════════════


def _pessoa(papel=UserRole.technician, nome="Tecnico", email=None, pid=None):
    """Destinatário já CARREGADO — é o que a audiência devolve."""
    u = MagicMock()
    u.id = pid or uuid.uuid4()
    u.email = email or f"{uuid.uuid4().hex[:6]}@test.com"
    u.name = nome
    u.role = papel
    u.status = UserStatus.active
    return u


def _db_de_lote():
    """Sessão que LEVANTA em `execute`: ida ao banco aqui é defeito de desenho."""
    sessao = AsyncMock()
    sessao.add = MagicMock()
    sessao.commit = AsyncMock()
    sessao.execute = AsyncMock(
        side_effect=AssertionError("o lote não deve consultar o banco por destinatário")
    )
    return sessao


@pytest.mark.asyncio
async def test_o_lote_cria_uma_notificacao_por_pessoa():
    from app.services import notifications

    db = _db_de_lote()
    equipe = [_pessoa(), _pessoa(UserRole.admin), _pessoa()]

    await notifications.notifica_audiencia(
        db, equipe, NotificationType.ticket_created, "Novo chamado", "corpo"
    )

    gravados = [c.args[0] for c in db.add.call_args_list]
    assert {n.user_id for n in gravados} == {p.id for p in equipe}
    assert len(gravados) == 3


@pytest.mark.asyncio
async def test_lista_com_repetido_gera_uma_notificacao_so():
    """Dedup por `user_id`, não importa de onde a repetição veio."""
    from app.services import notifications

    db = _db_de_lote()
    alguem = _pessoa()
    # O MESMO id chegando três vezes: dois objetos distintos e um repetido.
    equipe = [alguem, _pessoa(pid=alguem.id), alguem]

    avisados = await notifications.notifica_audiencia(
        db, equipe, NotificationType.ticket_created, "Novo chamado", "corpo"
    )

    assert len(db.add.call_args_list) == 1
    assert avisados == [alguem.id]


@pytest.mark.asyncio
async def test_exclude_user_ids_tira_a_pessoa_do_lote():
    from app.services import notifications

    db = _db_de_lote()
    autor = _pessoa(UserRole.technician, "Autor")
    colega = _pessoa(UserRole.admin, "Colega")

    avisados = await notifications.notifica_audiencia(
        db,
        [autor, colega],
        NotificationType.ticket_created,
        "Novo chamado",
        "corpo",
        exclude_user_ids={autor.id},
    )

    assert avisados == [colega.id]
    gravados = [c.args[0] for c in db.add.call_args_list]
    assert [n.user_id for n in gravados] == [colega.id]


@pytest.mark.asyncio
async def test_a_dedup_nao_depende_da_ordem_das_chamadas():
    """A exclusão é EXPLÍCITA, não efeito colateral da sequência.

    Se a dedup dependesse de "quem foi notificado primeiro", inverter a ordem
    das duas chamadas no `create_ticket` produziria duas notificações para o
    autor-staff e nada avisaria. Aqui a mesma exclusão dá o mesmo resultado com
    a audiência em qualquer ordem.
    """
    from app.services import notifications

    autor = _pessoa(UserRole.technician, "Autor")
    colega = _pessoa(UserRole.admin, "Colega")

    avisados_a = await notifications.notifica_audiencia(
        _db_de_lote(),
        [autor, colega],
        NotificationType.ticket_created,
        "Novo chamado",
        "corpo",
        exclude_user_ids={autor.id},
    )
    avisados_b = await notifications.notifica_audiencia(
        _db_de_lote(),
        [colega, autor],
        NotificationType.ticket_created,
        "Novo chamado",
        "corpo",
        exclude_user_ids={autor.id},
    )

    assert avisados_a == avisados_b == [colega.id]


@pytest.mark.asyncio
async def test_o_lote_nao_consulta_o_banco_nenhuma_vez():
    """A prova de que não há N+1 de e-mail.

    O `notify()` individual faz um SELECT do destinatário. Um laço de `notify`
    por pessoa faria N — com 15 técnicos, 15 consultas por chamado aberto. O
    lote recebe os destinatários JÁ CARREGADOS pela audiência: não é uma
    consulta em vez de N, é ZERO. `enqueue_email` também não consulta nada —
    só `db.add()`.

    A sessão deste teste LEVANTA em `execute`, então a afirmação não depende de
    contar chamadas: qualquer ida ao banco derruba o teste.
    """
    from app.core.config import get_settings
    from app.services import notifications

    db = _db_de_lote()
    equipe = [_pessoa() for _ in range(15)]  # technician — ticket_created libera e-mail

    await notifications.notifica_audiencia(
        db,
        equipe,
        NotificationType.ticket_created,
        "Novo chamado",
        "corpo",
        data={"ticket_id": str(uuid.uuid4()), "protocol": "HS-2026-0042"},
        settings=get_settings(),
    )

    db.execute.assert_not_called()
    assert len(db.add.call_args_list) == 30, "15 Notification + 15 EmailOutbox"


@pytest.mark.asyncio
async def test_o_lote_enfileira_uma_outbox_por_pessoa_na_mesma_sessao():
    from app.core.config import get_settings
    from app.services import notifications

    db = _db_de_lote()
    equipe = [_pessoa(email="a@test.com"), _pessoa(UserRole.admin, email="b@test.com")]

    await notifications.notifica_audiencia(
        db,
        equipe,
        NotificationType.ticket_created,
        "Novo chamado",
        "corpo",
        data={"ticket_id": str(uuid.uuid4()), "protocol": "HS-2026-0042"},
        settings=get_settings(),
    )

    adicionados = [c.args[0] for c in db.add.call_args_list]
    notifs = [obj for obj in adicionados if isinstance(obj, Notification)]
    outboxes = [obj for obj in adicionados if isinstance(obj, EmailOutbox)]
    assert len(notifs) == 2
    assert len(outboxes) == 2
    assert {o.notification_id for o in outboxes} == {n.id for n in notifs}

    await notifications.commit_e_notificar(db)
    db.commit.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# O ASSUNTO DO E-MAIL É SEPARADO DO TÍTULO DO SININHO
# ═══════════════════════════════════════════════════════════════


# `email_subject` foi removido de `notify`/`notifica_audiencia` na Fase 3B —
# o parâmetro não tinha mais função: o conteúdo do e-mail passou a ser
# reconstruído inteiramente pelo worker, a partir da `Notification`
# persistida (ver `email_outbox._assunto_reconstruido`, que cobre o caso
# `ticket_created` que motivava o parâmetro). Os dois testes que existiam
# aqui — "assunto explícito vence o título" e "sem assunto explícito, o
# fallback é o de sempre" — testavam justamente o parâmetro que não existe
# mais.


def test_o_separador_do_assunto_e_travessao():
    """`—`, não `·`. Decidido em 24/09/2026.

    O ponto médio some em fonte estreita de lista de caixa de entrada, e o
    travessão é o que o produto já usa para separar protocolo de título.
    """
    from app.services.notifications import _assunto_do_email

    assunto = _assunto_do_email("Chamado atribuido", {"protocol": "HS-2026-0042"})
    assert assunto == "[HelpHS] Chamado atribuido — HS-2026-0042"
    assert "·" not in assunto


# O equivalente do lote para `test_retry_de_protocolo_nao_deixa_outbox_duplicada`
# (o laço de `create_ticket` notifica o AUTOR e depois a EQUIPE — as tentativas
# descartadas não podem deixar nenhuma das duas outboxes para trás) mora em
# `tests/test_email_outbox_postgres.py::test_retry_de_lote_nao_deixa_outbox_duplicada`,
# contra Postgres de verdade: o que garante que um `db.add()` de uma tentativa
# descartada não sobrevive é o `rollback()` do SQLAlchemy, não código deste
# módulo — mock não tem como provar isso.
