"""
Tests for the Notification service and endpoints.
DB and Redis are fully mocked.
"""

import asyncio
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from loguru import logger

from app.main import app
from app.models.models import NotificationType, UserRole, UserStatus

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

    with patch("app.services.notifications.asyncio.create_task"):
        await notify(
            db,
            _USER_ID,
            NotificationType.ticket_created,
            "Ticket aberto",
            "Protocolo HS-2026-0001",
        )

    db.add.assert_called_once()
    notif_obj = db.add.call_args[0][0]
    assert notif_obj.user_id == _USER_ID
    assert notif_obj.type == NotificationType.ticket_created
    assert notif_obj.read is False


@pytest.mark.asyncio
async def test_notify_registra_o_email_como_pendencia_da_sessao():
    """
    Sucessor de `test_notify_schedules_email_task_when_settings_provided`, que
    afirmava o contrário: que notify() criava a task de envio na hora. Aquilo
    ERA o bug do M6 — o teste fixava como contrato o envio antes do commit.
    Agora notify() registra, e quem dispara é o commit_e_notificar.
    """
    from app.core.config import get_settings
    from app.services import notifications

    db = _db_para_notify("user@test.com")
    settings = get_settings()

    with patch.object(notifications, "send_email", new=AsyncMock(return_value=True)) as enviar:
        await notifications.notify(
            db,
            _USER_ID,
            NotificationType.ticket_created,
            "Ticket aberto",
            "Protocolo HS-2026-0001",
            settings=settings,
        )
        await _deixar_as_tarefas_rodarem()
        enviar.assert_not_awaited()

        await notifications.commit_e_notificar(db)
        await _deixar_as_tarefas_rodarem()
        assert enviar.await_count == 1


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

    with patch("app.services.notifications.asyncio.create_task") as mock_task:
        await notify(db, _USER_ID, NotificationType.ticket_created, "Title", "Body")
        mock_task.assert_not_called()


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

    with patch("app.services.notifications.asyncio.create_task") as mock_task:
        await notify(
            db,
            _USER_ID,
            NotificationType.satisfaction_survey,
            "Como foi o atendimento?",
            "O ticket HS-2026-0010 foi resolvido.",
            settings=get_settings(),
        )

    db.add.assert_called_once()  # a notificação no sininho continua existindo
    mock_task.assert_not_called()


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
async def test_log_de_falha_de_email_diz_o_destinatario_e_o_motivo():
    """
    Quando alguém reclama que não recebeu o email, a linha de log é a única
    pista que existe. Se ela sair com o placeholder literal, os argumentos são
    descartados e a linha não serve para nada.
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
        mock_fm.send_message = AsyncMock(side_effect=Exception("conexao recusada"))
        mock_client.return_value = mock_fm

        with _capturar_log() as linhas:
            enviado = await send_email("quem.reclamou@test.com", "Assunto", "Corpo", settings)

    assert enviado is False
    falhas = [linha for linha in linhas if "Failed to send email" in linha]
    assert falhas, f"a falha de entrega não foi registrada: {linhas}"
    assert "quem.reclamou@test.com" in falhas[0]
    assert "conexao recusada" in falhas[0]


@pytest.mark.asyncio
async def test_log_de_notificacao_nao_entregue_diz_o_destinatario():
    """Mesma dívida do lado da notificação: sem destinatário não há rastro."""
    from app.core.config import Settings
    from app.services import notifications
    from app.services.notifications import _send_and_log

    settings = Settings(database_url="postgresql+asyncpg://u:p@localhost/db")
    notif = MagicMock()
    notif.id = _NOTIF_ID

    pendente = notifications._EmailPendente(
        notif_id=notif.id,
        to_email="destino@test.com",
        subject="Assunto",
        body="Corpo",
        settings=settings,
    )

    with patch("app.services.notifications.send_email", new=AsyncMock(return_value=False)):
        with _capturar_log() as linhas:
            await _send_and_log(pendente)

    nao_entregues = [linha for linha in linhas if "NOT delivered" in linha]
    assert nao_entregues, f"a não-entrega não foi registrada: {linhas}"
    assert "destino@test.com" in nao_entregues[0]
    assert str(_NOTIF_ID) in nao_entregues[0]


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


def _db_para_notify(email="destino@test.com", papel=UserRole.client):
    """Sessão mockada que devolve o destinatário na busca do notify().

    Passou a carregar o PAPEL junto do e-mail em 04/09/2026: quem decide o
    envio deixou de ser só o tipo da notificação e passou a ser também quem
    recebe. O padrão é `client` porque é o único que continua recebendo.
    """

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.one_or_none.return_value = (email, papel)
        result.scalar_one_or_none.return_value = email
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


async def _deixar_as_tarefas_rodarem():
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_notify_sozinho_nao_dispara_email():
    """
    notify() é chamado ANTES do commit, de propósito: a notificação faz parte
    da transação. Por isso ele não pode disparar nada — só registrar.
    """
    from app.core.config import Settings
    from app.services import notifications

    settings = Settings(database_url="postgresql+asyncpg://u:p@localhost/db")
    db = _db_para_notify()

    with patch.object(notifications, "send_email", new=AsyncMock(return_value=True)) as enviar:
        await notifications.notify(
            db,
            _USER_ID,
            NotificationType.ticket_updated,
            "Assunto",
            "Corpo",
            settings=settings,
        )
        await _deixar_as_tarefas_rodarem()

    enviar.assert_not_awaited()


@pytest.mark.asyncio
async def test_commit_que_falha_nao_dispara_email():
    """
    O ponto do M6: qualquer commit que falhe depois do notify mandava e-mail
    sobre algo que não aconteceu.
    """
    from app.core.config import Settings
    from app.services import notifications

    settings = Settings(database_url="postgresql+asyncpg://u:p@localhost/db")
    db = _db_para_notify()
    db.commit = AsyncMock(side_effect=RuntimeError("deu ruim no commit"))

    with patch.object(notifications, "send_email", new=AsyncMock(return_value=True)) as enviar:
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
        await _deixar_as_tarefas_rodarem()

    enviar.assert_not_awaited()


@pytest.mark.asyncio
async def test_commit_que_passa_dispara_uma_vez_so():
    from app.core.config import Settings
    from app.services import notifications

    settings = Settings(database_url="postgresql+asyncpg://u:p@localhost/db")
    db = _db_para_notify()

    with patch.object(notifications, "send_email", new=AsyncMock(return_value=True)) as enviar:
        await notifications.notify(
            db,
            _USER_ID,
            NotificationType.ticket_updated,
            "Assunto",
            "Corpo",
            settings=settings,
        )
        await notifications.commit_e_notificar(db)
        await _deixar_as_tarefas_rodarem()

    assert enviar.await_count == 1
    assert enviar.await_args.args[0] == "destino@test.com"


@pytest.mark.asyncio
async def test_commit_seguinte_nao_reenvia_o_que_ja_saiu():
    """A pendência é consumida no primeiro commit, não reaproveitada."""
    from app.core.config import Settings
    from app.services import notifications

    settings = Settings(database_url="postgresql+asyncpg://u:p@localhost/db")
    db = _db_para_notify()

    with patch.object(notifications, "send_email", new=AsyncMock(return_value=True)) as enviar:
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
        await _deixar_as_tarefas_rodarem()

    assert enviar.await_count == 1


@pytest.mark.asyncio
async def test_cinco_tentativas_de_protocolo_mandam_um_email_so():
    """
    Reproduz o laço de `create_ticket`: até MAX_RETRIES tentativas, cada uma
    com o seu notify(), commit que falha por IntegrityError e rollback.

    Antes, cada tentativa descartada mandava o seu e-mail — cinco e-mails
    anunciando protocolos que não passaram a existir.
    """
    from sqlalchemy.exc import IntegrityError

    from app.core.config import Settings
    from app.services import notifications
    from app.utils.protocol import MAX_RETRIES

    settings = Settings(database_url="postgresql+asyncpg://u:p@localhost/db")
    db = _db_para_notify()

    falhas = [IntegrityError("insert", {}, Exception("protocolo repetido"))] * (MAX_RETRIES - 1)
    db.commit = AsyncMock(side_effect=[*falhas, None])

    with patch.object(notifications, "send_email", new=AsyncMock(return_value=True)) as enviar:
        for tentativa in range(MAX_RETRIES):
            await notifications.notify(
                db,
                _USER_ID,
                NotificationType.ticket_created,
                "Ticket aberto",
                f"Protocolo da tentativa {tentativa}",
                settings=settings,
            )
            try:
                await notifications.commit_e_notificar(db)
                break
            except IntegrityError:
                await db.rollback()
        await _deixar_as_tarefas_rodarem()

    assert enviar.await_count == 1, "cada tentativa descartada mandou o seu e-mail"
    assert "tentativa 4" in enviar.await_args.args[2]


@pytest.mark.asyncio
async def test_pendencias_nao_vazam_entre_sessoes():
    """Duas requisições simultâneas não podem herdar e-mail uma da outra."""
    from app.core.config import Settings
    from app.services import notifications

    settings = Settings(database_url="postgresql+asyncpg://u:p@localhost/db")
    db_a = _db_para_notify("a@test.com")
    db_b = _db_para_notify("b@test.com")

    with patch.object(notifications, "send_email", new=AsyncMock(return_value=True)) as enviar:
        await notifications.notify(
            db_a, _USER_ID, NotificationType.ticket_updated, "A", "corpo", settings=settings
        )
        await notifications.notify(
            db_b, _USER_ID, NotificationType.ticket_updated, "B", "corpo", settings=settings
        )
        await notifications.commit_e_notificar(db_a)
        await _deixar_as_tarefas_rodarem()

    assert enviar.await_count == 1
    assert enviar.await_args.args[0] == "a@test.com"


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
    """A notificação continua existindo no sininho; só o e-mail para de sair."""
    from app.core.config import get_settings
    from app.services import notifications

    db = _db_para_notify("tecnico@test.com", papel=papel)

    with patch.object(notifications, "send_email", new=AsyncMock(return_value=True)) as enviar:
        await notifications.notify(
            db,
            _USER_ID,
            NotificationType.ticket_updated,
            "Ticket atualizado",
            "O chamado HS-2026-0001 mudou de status.",
            settings=get_settings(),
        )
        await notifications.commit_e_notificar(db)
        await _deixar_as_tarefas_rodarem()

    db.add.assert_called_once()
    enviar.assert_not_awaited()


@pytest.mark.asyncio
async def test_cliente_continua_recebendo_notificacao_por_email():
    """Contraprova do teste acima: o que silencia é o PAPEL, e não o tipo.

    Se este par cair junto com o de cima, a mudança silenciou todo mundo em
    vez de silenciar só a equipe.
    """
    from app.core.config import get_settings
    from app.services import notifications

    db = _db_para_notify("cliente@test.com", papel=UserRole.client)

    with patch.object(notifications, "send_email", new=AsyncMock(return_value=True)) as enviar:
        await notifications.notify(
            db,
            _USER_ID,
            NotificationType.ticket_updated,
            "Ticket atualizado",
            "O chamado HS-2026-0001 mudou de status.",
            settings=get_settings(),
        )
        await notifications.commit_e_notificar(db)
        await _deixar_as_tarefas_rodarem()

    assert enviar.await_count == 1
    assert enviar.await_args.args[0] == "cliente@test.com"


@pytest.mark.asyncio
async def test_o_chat_para_de_encher_a_caixa_do_tecnico():
    """O caso que motivou a mudança: dez mensagens do cliente eram dez e-mails."""
    from app.core.config import get_settings
    from app.services import notifications

    db = _db_para_notify("tecnico@test.com", papel=UserRole.technician)

    with patch.object(notifications, "send_email", new=AsyncMock(return_value=True)) as enviar:
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
        await _deixar_as_tarefas_rodarem()

    assert db.add.call_count == 10, "as dez continuam no sininho"
    enviar.assert_not_awaited()


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

    with patch.object(notifications, "send_email", new=AsyncMock(return_value=True)) as enviar:
        await notifications.notify(
            db,
            _USER_ID,
            NotificationType.ticket_updated,
            "Ticket atualizado",
            "corpo",
            settings=get_settings(),
        )
        await notifications.commit_e_notificar(db)
        await _deixar_as_tarefas_rodarem()

    enviar.assert_not_awaited()


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


def _pega_email(enviar):
    """(destino, assunto, corpo) da única chamada de send_email."""
    args = enviar.await_args.args
    return args[0], args[1], args[2]


@pytest.mark.asyncio
async def test_o_email_leva_o_link_do_chamado():
    from app.core.config import get_settings
    from app.services import notifications

    db = _db_para_notify("cliente@test.com")
    settings = get_settings()
    ticket_id = str(uuid.uuid4())

    with patch.object(notifications, "send_email", new=AsyncMock(return_value=True)) as enviar:
        await notifications.notify(
            db,
            _USER_ID,
            NotificationType.ticket_updated,
            "Chamado resolvido",
            "O chamado HS-2026-0042 foi marcado como resolvido.",
            data={"ticket_id": ticket_id, "protocol": "HS-2026-0042"},
            settings=settings,
        )
        await notifications.commit_e_notificar(db)
        await _deixar_as_tarefas_rodarem()

    _, _, corpo = _pega_email(enviar)

    assert f"{settings.frontend_url.rstrip('/')}/tickets/{ticket_id}" in corpo
    assert (
        "O chamado HS-2026-0042 foi marcado como resolvido." in corpo
    ), "a mensagem original tem que continuar no corpo"


@pytest.mark.asyncio
async def test_o_assunto_diz_de_qual_chamado_se_trata():
    from app.core.config import get_settings
    from app.services import notifications

    db = _db_para_notify("cliente@test.com")

    with patch.object(notifications, "send_email", new=AsyncMock(return_value=True)) as enviar:
        await notifications.notify(
            db,
            _USER_ID,
            NotificationType.ticket_updated,
            "Chamado resolvido",
            "corpo qualquer",
            data={"ticket_id": str(uuid.uuid4()), "protocol": "HS-2026-0042"},
            settings=get_settings(),
        )
        await notifications.commit_e_notificar(db)
        await _deixar_as_tarefas_rodarem()

    _, assunto, _ = _pega_email(enviar)

    assert assunto.startswith("[HelpHS]"), f"sem o prefixo da casa: {assunto}"
    assert "HS-2026-0042" in assunto, f"o assunto não diz qual chamado: {assunto}"
    assert "Chamado resolvido" in assunto


@pytest.mark.asyncio
async def test_sem_protocolo_o_assunto_ainda_sai_util():
    """Cinco chamadas não carregam `protocol` no data — não podem quebrar."""
    from app.core.config import get_settings
    from app.services import notifications

    db = _db_para_notify("cliente@test.com")

    with patch.object(notifications, "send_email", new=AsyncMock(return_value=True)) as enviar:
        await notifications.notify(
            db,
            _USER_ID,
            NotificationType.ticket_updated,
            "Chamado reaberto",
            "corpo qualquer",
            data={"ticket_id": str(uuid.uuid4()), "new_status": "in_progress"},
            settings=get_settings(),
        )
        await notifications.commit_e_notificar(db)
        await _deixar_as_tarefas_rodarem()

    _, assunto, corpo = _pega_email(enviar)

    assert assunto == "[HelpHS] Chamado reaberto"
    assert "/tickets/" in corpo, "sem protocolo, o link ainda tem que sair"


@pytest.mark.asyncio
async def test_notificacao_sem_chamado_nao_inventa_link():
    """Contraprova: sem `ticket_id` no data, o corpo é a mensagem e nada mais."""
    from app.core.config import get_settings
    from app.services import notifications

    db = _db_para_notify("cliente@test.com")

    with patch.object(notifications, "send_email", new=AsyncMock(return_value=True)) as enviar:
        await notifications.notify(
            db,
            _USER_ID,
            NotificationType.system,
            "Aviso do sistema",
            "Manutenção programada para sábado.",
            data=None,
            settings=get_settings(),
        )
        await notifications.commit_e_notificar(db)
        await _deixar_as_tarefas_rodarem()

    _, _, corpo = _pega_email(enviar)

    assert corpo.strip() == "Manutenção programada para sábado."
    assert "/tickets/" not in corpo


@pytest.mark.asyncio
async def test_o_sininho_nao_muda():
    """O que a Notification grava continua sendo o título e a mensagem crus.

    O prefixo `[HelpHS]` e o link são coisa de e-mail. Se vazarem para a
    Notification, o sininho passa a mostrar "[HelpHS] Chamado resolvido" e uma
    URL no meio do texto.
    """
    from app.core.config import get_settings
    from app.services import notifications

    db = _db_para_notify("cliente@test.com")

    with patch.object(notifications, "send_email", new=AsyncMock(return_value=True)):
        await notifications.notify(
            db,
            _USER_ID,
            NotificationType.ticket_updated,
            "Chamado resolvido",
            "O chamado HS-2026-0042 foi marcado como resolvido.",
            data={"ticket_id": str(uuid.uuid4()), "protocol": "HS-2026-0042"},
            settings=get_settings(),
        )

    gravada = db.add.call_args.args[0]
    assert gravada.title == "Chamado resolvido"
    assert gravada.message == "O chamado HS-2026-0042 foi marcado como resolvido."
