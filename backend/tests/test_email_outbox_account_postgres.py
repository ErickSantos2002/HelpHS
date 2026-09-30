"""
Fase 3C — outbox de e-mail de conta/autenticação, contra PostgreSQL de verdade.

Por que este arquivo existe
----------------------------
Mesma razão do irmão da Fase 3A/3B (`test_email_outbox_postgres.py`):
`FOR UPDATE SKIP LOCKED`, `UNIQUE(dedup_key)` e a CHECK de origem
(`ck_email_outbox_origem_valida`) só têm semântica real em Postgres — testar
contra mock provaria a lógica, nunca a garantia. Este arquivo cobre
especificamente a origem NOVA (`user_id`+`event_type`), deixando a origem
Notification para o arquivo já existente (só um teste aqui garante que as
DUAS origens convivem no mesmo lote — o resto é regressão do arquivo 3A/3B).

Sessão presa ao ENGINE, mesma disciplina do 3A/3B
----------------------------------------------------
Sem conexão+savepoint: os testes de concorrência precisam de COMMITS de
verdade, visíveis entre sessões diferentes.
"""

import asyncio
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from jose import jwt
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.models.models import Base, EmailOutbox, Notification, User, UserRole, UserStatus
from app.services import account_tokens
from app.services.email import EmailDeliveryResult, EmailDeliveryStatus
from app.services.email_outbox import (
    _CONTA_USUARIO_ANONIMIZADO,
    _CONTA_USUARIO_INATIVO,
    _CONTA_VERIFICACAO_JA_CONCLUIDA,
    _processa_conta,
    enqueue_account_email,
    enqueue_email,
    processa_lote,
    reivindica_lote,
)
from tests.test_dashboard_postgres import _sobe_postgres

_AGORA = datetime.now(UTC)


@pytest.fixture(scope="module")
def url_do_banco():
    url, recurso = _sobe_postgres()
    if url is None:
        pytest.skip("sem PostgreSQL à mão")

    async def _monta() -> None:
        motor = create_async_engine(url)
        async with motor.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        await motor.dispose()

    asyncio.run(_monta())
    yield url

    if recurso is not None:
        servidor, pasta = recurso
        try:
            servidor.cleanup()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(pasta, ignore_errors=True)


@pytest_asyncio.fixture
async def db_factory(url_do_banco):
    motor = create_async_engine(url_do_banco)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    yield fabrica
    await motor.dispose()


@pytest_asyncio.fixture
async def db(db_factory):
    async with db_factory() as sessao:
        yield sessao


def _usuario(
    nome: str = "Alvo",
    *,
    status: UserStatus = UserStatus.active,
    email_verified: bool = False,
    password: str = "hash-de-teste",
    role: UserRole = UserRole.client,
) -> User:
    return User(
        id=uuid.uuid4(),
        name=nome,
        # `.invalid` é rejeitado pelo `email-validator` (TLD reservado) assim
        # que uma mensagem real chega a `MessageSchema` — o que acontece nos
        # testes que exercitam o caminho de SMTP de verdade (via
        # `_get_mail_client`, não via `send_email_detalhado` mockado). `.com`
        # passa pela validação sem sair da máquina.
        email=f"{uuid.uuid4().hex[:10]}@test.com",
        password=password,
        role=role,
        status=status,
        # `ck_users_cliente_ativo_tem_telefone` (Fase 1C): cliente ATIVO
        # precisa de telefone — o `create_all` monta o schema pelo model,
        # então o fixture precisa nascer conforme a regra de domínio.
        phone=(
            "+5581999999999" if (role == UserRole.client and status == UserStatus.active) else None
        ),
        lgpd_consent=True,
        email_verified=email_verified,
        onboarding_completed=True,
        created_at=_AGORA,
        updated_at=_AGORA,
    )


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        smtp_from_email="from@test.com",
        smtp_user="from@test.com",
        smtp_host="localhost",
        smtp_port=1025,
        email_outbox_batch_size=10,
        email_outbox_stale_processing_minutes=5,
        frontend_url="https://helphs.exemplo.com",
    )
    base.update(overrides)
    return Settings(**base)


async def _limpa(db, *users: User) -> None:
    """Apagar o `User` cascateia por `email_outbox` (origem Account) e por

    `notifications`/`email_outbox` (origem Notification) — mesma técnica de
    `test_email_outbox_postgres.py`: lê o id via `InstanceState.identity`,
    nunca `.id`, porque pode ter havido `rollback()` nesta sessão.
    """
    for u in users:
        uid = sa_inspect(u).identity[0]
        alvo = await db.get(User, uid)
        if alvo is not None:
            await db.delete(alvo)
    await db.commit()


def _outbox_conta(
    user: User,
    event_type: str,
    *,
    intent_id: uuid.UUID | None = None,
    status: str = "pending",
    next_attempt_at=None,
    **overrides,
) -> EmailOutbox:
    intent_id = intent_id or uuid.uuid4()
    campos = dict(
        id=uuid.uuid4(),
        user_id=user.id,
        event_type=event_type,
        dedup_key=f"{event_type}:{user.id}:{intent_id}",
        status=status,
        attempts=0,
        next_attempt_at=next_attempt_at or _AGORA,
    )
    campos.update(overrides)
    return EmailOutbox(**campos)


class _ErroComCodigoError(Exception):
    def __init__(self, code: int):
        super().__init__("mensagem crua do servidor")
        self.code = code


# ═══════════════════════════════════════════════════════════════
# Migration: upgrade / downgrade / upgrade, contra Postgres à parte
# ═══════════════════════════════════════════════════════════════


def test_migration_upgrade_downgrade_upgrade():
    """Roda `alembic` de verdade contra um Postgres efêmero à parte — mesmo

    padrão de `test_email_outbox_postgres.py::test_migration_upgrade_downgrade_upgrade`.
    """
    try:
        import pgserver
    except ImportError:
        pytest.skip("pgserver não instalado")

    pasta = tempfile.mkdtemp(prefix="helphs-testes-pg-migration-3c-")
    servidor = pgserver.get_server(pasta, cleanup_mode=None)
    try:
        servidor.psql("CREATE DATABASE migracao_outbox_conta;")
        url = servidor.get_uri(database="migracao_outbox_conta")

        from sqlalchemy.engine import make_url

        alvo = make_url(url)
        assert alvo.host in (
            None,
            "",
            "localhost",
            "127.0.0.1",
            "::1",
        ), "alvo da migration de teste não é local — abortando por segurança"

        url_async = url.replace("postgresql://", "postgresql+asyncpg://")

        async def _cria_extensao_vector() -> None:
            motor = create_async_engine(url_async)
            async with motor.begin() as conn:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await motor.dispose()

        asyncio.run(_cria_extensao_vector())

        import os

        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = os.environ.copy()
        env["DATABASE_URL"] = url_async
        env.pop("ALEMBIC_ALVO_REMOTO_LIBERADO", None)

        def _roda(*args):
            resultado = subprocess.run(
                [sys.executable, "-m", "alembic", *args],
                cwd=backend_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
            assert resultado.returncode == 0, resultado.stdout + resultado.stderr
            return resultado

        _roda("upgrade", "head")

        async def _tem_colunas() -> bool:
            motor = create_async_engine(url_async)
            try:
                async with motor.connect() as conn:
                    r = await conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'email_outbox' AND column_name IN "
                            "('user_id', 'event_type', 'dedup_key')"
                        )
                    )
                    return {row[0] for row in r.all()} == {"user_id", "event_type", "dedup_key"}
            finally:
                await motor.dispose()

        assert asyncio.run(_tem_colunas()) is True

        _roda("downgrade", "-1")
        assert asyncio.run(_tem_colunas()) is False

        _roda("upgrade", "head")
        assert asyncio.run(_tem_colunas()) is True
    finally:
        try:
            servidor.cleanup()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(pasta, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# Schema: CHECK de origem, event_type, dedup_key, linhas antigas
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_linha_notification_antiga_continua_valida(db):
    """A CHECK aceita o formato ANTIGO (só `notification_id`) sem exigir

    nada novo — é o que garante que produção, com linhas só de Notification,
    nunca quebra com esta migration."""
    user = _usuario()
    notif = Notification(
        id=uuid.uuid4(),
        user_id=user.id,
        type="ticket_created",
        title="Ticket aberto",
        message="msg",
        data=None,
        read=False,
        email_sent=False,
    )
    db.add_all([user, notif])
    await db.commit()

    outbox = enqueue_email(db, notif, agora=_AGORA)
    await db.commit()

    atualizado = await db.get(EmailOutbox, outbox.id)
    assert atualizado.notification_id == notif.id
    assert atualizado.user_id is None
    assert atualizado.event_type is None
    assert atualizado.dedup_key is None

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_check_recusa_as_duas_origens_juntas(db):
    user = _usuario()
    notif = Notification(
        id=uuid.uuid4(),
        user_id=user.id,
        type="ticket_created",
        title="t",
        message="m",
        data=None,
        read=False,
        email_sent=False,
    )
    db.add_all([user, notif])
    await db.commit()

    misturada = EmailOutbox(
        id=uuid.uuid4(),
        notification_id=notif.id,
        user_id=user.id,
        event_type="verification",
        dedup_key=f"verification:{user.id}:{uuid.uuid4()}",
        status="pending",
        attempts=0,
        next_attempt_at=_AGORA,
    )
    db.add(misturada)
    with pytest.raises(Exception):  # ck_email_outbox_origem_valida
        await db.commit()
    await db.rollback()

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_check_recusa_nenhuma_origem(db):
    user = _usuario()
    db.add(user)
    await db.commit()

    vazia = EmailOutbox(
        id=uuid.uuid4(),
        status="pending",
        attempts=0,
        next_attempt_at=_AGORA,
    )
    db.add(vazia)
    with pytest.raises(Exception):  # ck_email_outbox_origem_valida
        await db.commit()
    await db.rollback()

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_event_type_invalido_e_recusado(db):
    user = _usuario()
    db.add(user)
    await db.commit()

    invalida = EmailOutbox(
        id=uuid.uuid4(),
        user_id=user.id,
        event_type="evento_que_nao_existe",
        dedup_key=f"evento_que_nao_existe:{user.id}:{uuid.uuid4()}",
        status="pending",
        attempts=0,
        next_attempt_at=_AGORA,
    )
    db.add(invalida)
    with pytest.raises(Exception):  # ck_email_outbox_event_type_conhecido
        await db.commit()
    await db.rollback()

    await _limpa(db, user)


def test_enqueue_account_email_recusa_event_type_desconhecido():
    """A validação em Python é a primeira linha de defesa — a CHECK do banco

    é a segunda, provada acima. Não precisa de sessão real."""
    db_fake = AsyncMock()
    with pytest.raises(ValueError):
        enqueue_account_email(
            db_fake, user_id=uuid.uuid4(), event_type="invalido", intent_id=uuid.uuid4()
        )


# ═══════════════════════════════════════════════════════════════
# Enqueue dos três eventos — conteúdo mínimo, nada de PII
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", ["verification", "password_reset", "account_exists"])
async def test_enqueue_dos_tres_eventos(db, event_type):
    user = _usuario()
    db.add(user)
    await db.commit()

    outbox = enqueue_account_email(
        db, user_id=user.id, event_type=event_type, intent_id=uuid.uuid4()
    )
    await db.commit()

    atualizado = await db.get(EmailOutbox, outbox.id)
    assert atualizado.status == "pending"
    assert atualizado.user_id == user.id
    assert atualizado.event_type == event_type
    assert atualizado.notification_id is None

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_nenhum_jwt_email_subject_ou_corpo_no_banco(db):
    """A outbox só tem as colunas operacionais — não há ONDE um JWT, um

    e-mail, um assunto ou um corpo poderiam ir parar, mesmo por engano.
    Verificação estrutural: lista as colunas de `email_outbox` e confirma
    que nenhuma tem nome/propósito de conteúdo."""
    user = _usuario()
    db.add(user)
    await db.commit()
    enqueue_account_email(db, user_id=user.id, event_type="verification", intent_id=uuid.uuid4())
    await db.commit()

    colunas = {c.name for c in EmailOutbox.__table__.columns}
    proibidas = {"email", "subject", "body", "token", "jwt", "password", "name", "html"}
    assert not (colunas & proibidas), f"coluna suspeita encontrada: {colunas & proibidas}"

    await _limpa(db, user)


# ═══════════════════════════════════════════════════════════════
# Dedup — mesmo intent_id vs. intent_id novo
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_mesmo_intent_id_e_duplicacao_tecnica(db):
    user = _usuario()
    db.add(user)
    await db.commit()
    intent_id = uuid.uuid4()

    enqueue_account_email(db, user_id=user.id, event_type="password_reset", intent_id=intent_id)
    await db.commit()

    enqueue_account_email(db, user_id=user.id, event_type="password_reset", intent_id=intent_id)
    with pytest.raises(Exception):  # UNIQUE(dedup_key)
        await db.commit()
    await db.rollback()

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_intent_id_novo_e_pedido_legitimo_permitido(db):
    user = _usuario()
    db.add(user)
    await db.commit()

    enqueue_account_email(db, user_id=user.id, event_type="password_reset", intent_id=uuid.uuid4())
    await db.commit()
    enqueue_account_email(db, user_id=user.id, event_type="password_reset", intent_id=uuid.uuid4())
    await db.commit()

    total = await db.execute(
        select(EmailOutbox).where(
            EmailOutbox.user_id == user.id, EmailOutbox.event_type == "password_reset"
        )
    )
    assert len(total.scalars().all()) == 2, "dois pedidos legítimos, duas linhas"

    await _limpa(db, user)


# ═══════════════════════════════════════════════════════════════
# Token — só nasce no worker, TTL a partir do processamento
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_token_so_e_gerado_no_worker(db, db_factory):
    """Cria a intenção, confirma que NENHUM token existe em lugar nenhum

    até o worker processar — e que `account_tokens.create_*` só é chamado
    dentro de `_processa_conta`, nunca no enqueue."""
    user = _usuario(email_verified=False)
    db.add(user)
    await db.commit()
    outbox = enqueue_account_email(
        db, user_id=user.id, event_type="verification", intent_id=uuid.uuid4()
    )
    await db.commit()
    outbox_id = outbox.id

    with patch(
        "app.services.email_outbox.account_tokens.create_email_verification_token"
    ) as criar_token:
        criar_token.return_value = "token-fake"
        settings = _settings()
        with patch(
            "app.services.email_outbox.send_email_detalhado",
            new=AsyncMock(return_value=EmailDeliveryResult(EmailDeliveryStatus.success)),
        ):
            criar_token.assert_not_called()  # nada até aqui
            await _processa_conta(db_factory, settings, outbox_id, user.id, "verification")

    criar_token.assert_called_once()

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_ttl_conta_a_partir_do_processamento(db, db_factory):
    """O `iat` do token reflete o momento em que o WORKER processou, não o

    momento em que a intenção foi enfileirada."""
    user = _usuario(email_verified=False)
    db.add(user)
    await db.commit()
    momento_enqueue = _AGORA - timedelta(hours=2)
    outbox = enqueue_account_email(
        db,
        user_id=user.id,
        event_type="verification",
        intent_id=uuid.uuid4(),
        agora=momento_enqueue,
    )
    await db.commit()
    outbox_id = outbox.id

    settings = _settings()
    tokens_capturados = []

    async def _envio_capturando(destinatario, assunto, texto, settings_, *, html, contexto):
        return EmailDeliveryResult(EmailDeliveryStatus.success)

    momento_processamento = datetime.now(UTC)
    with patch(
        "app.services.email_outbox.send_email_detalhado",
        new=AsyncMock(side_effect=_envio_capturando),
    ):
        real_create = account_tokens.create_email_verification_token

        def _create_e_captura(user_id, email_verified, settings_):
            token = real_create(user_id, email_verified, settings_)
            tokens_capturados.append(token)
            return token

        with patch(
            "app.services.email_outbox.account_tokens.create_email_verification_token",
            side_effect=_create_e_captura,
        ):
            await _processa_conta(db_factory, settings, outbox_id, user.id, "verification")

    assert len(tokens_capturados) == 1
    payload = jwt.decode(
        tokens_capturados[0],
        settings.get_public_key(),
        algorithms=[settings.jwt_algorithm],
        issuer=settings.jwt_issuer,
    )
    iat = datetime.fromtimestamp(payload["iat"], tz=UTC)
    # iat está perto do PROCESSAMENTO (agora), não do enqueue (2h atrás).
    assert abs((iat - momento_processamento).total_seconds()) < 30
    assert abs((iat - momento_enqueue).total_seconds()) > 3600

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_verification_token_gerado_pelo_worker_e_valido(db, db_factory):
    user = _usuario(email_verified=False)
    db.add(user)
    await db.commit()
    outbox = enqueue_account_email(
        db, user_id=user.id, event_type="verification", intent_id=uuid.uuid4()
    )
    await db.commit()
    outbox_id = outbox.id

    settings = _settings()
    capturado = {}

    async def _envio(destinatario, assunto, texto, settings_, *, html, contexto):
        capturado["texto"] = texto
        return EmailDeliveryResult(EmailDeliveryStatus.success)

    with patch("app.services.email_outbox.send_email_detalhado", new=AsyncMock(side_effect=_envio)):
        await _processa_conta(db_factory, settings, outbox_id, user.id, "verification")

    # O link está no corpo — extrai o token e valida de verdade.
    assert "confirmar-email?token=" in capturado["texto"]
    token = capturado["texto"].split("token=")[1].split()[0].split(")")[0]
    user_id_do_token = account_tokens.read_email_verification_token(token, False, settings)
    assert user_id_do_token == user.id

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_password_reset_token_gerado_pelo_worker_e_valido(db, db_factory):
    user = _usuario(email_verified=True, password="hash-atual")
    db.add(user)
    await db.commit()
    outbox = enqueue_account_email(
        db, user_id=user.id, event_type="password_reset", intent_id=uuid.uuid4()
    )
    await db.commit()
    outbox_id = outbox.id

    settings = _settings()
    capturado = {}

    async def _envio(destinatario, assunto, texto, settings_, *, html, contexto):
        capturado["texto"] = texto
        return EmailDeliveryResult(EmailDeliveryStatus.success)

    with patch("app.services.email_outbox.send_email_detalhado", new=AsyncMock(side_effect=_envio)):
        await _processa_conta(db_factory, settings, outbox_id, user.id, "password_reset")

    assert "redefinir-senha?token=" in capturado["texto"]
    token = capturado["texto"].split("token=")[1].split()[0].split(")")[0]
    user_id_do_token = account_tokens.read_password_reset_token(token, "hash-atual", settings)
    assert user_id_do_token == user.id

    await _limpa(db, user)


# ═══════════════════════════════════════════════════════════════
# SMTP sucesso / falha temporária / permanente — via processa_lote
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_smtp_sucesso_marca_sent(db, db_factory):
    user = _usuario(email_verified=False)
    db.add(user)
    await db.commit()
    outbox = enqueue_account_email(
        db,
        user_id=user.id,
        event_type="account_exists",
        intent_id=uuid.uuid4(),
        agora=_AGORA - timedelta(minutes=1),
    )
    await db.commit()
    outbox_id = outbox.id

    settings = _settings()
    with patch("app.services.email._get_mail_client") as mock_client:
        mock_fm = AsyncMock()
        mock_fm.send_message = AsyncMock()
        mock_client.return_value = mock_fm
        await processa_lote(db_factory, settings, worker_id="w1", agora=_AGORA)

    atualizado = await db.get(EmailOutbox, outbox_id)
    await db.refresh(atualizado)
    assert atualizado.status == "sent"
    assert atualizado.sent_at is not None

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_smtp_falha_temporaria_retenta(db, db_factory):
    user = _usuario()
    db.add(user)
    await db.commit()
    outbox = enqueue_account_email(
        db,
        user_id=user.id,
        event_type="account_exists",
        intent_id=uuid.uuid4(),
        agora=_AGORA - timedelta(minutes=1),
    )
    await db.commit()
    outbox_id = outbox.id

    settings = _settings()
    with patch("app.services.email._get_mail_client") as mock_client:
        mock_fm = AsyncMock()
        mock_fm.send_message = AsyncMock(side_effect=_ErroComCodigoError(421))
        mock_client.return_value = mock_fm
        await processa_lote(db_factory, settings, worker_id="w1", agora=_AGORA)

    atualizado = await db.get(EmailOutbox, outbox_id)
    await db.refresh(atualizado)
    assert atualizado.status == "pending"
    assert atualizado.attempts == 1
    assert atualizado.next_attempt_at > _AGORA

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_smtp_falha_permanente_vai_para_dead(db, db_factory):
    user = _usuario()
    db.add(user)
    await db.commit()
    outbox = enqueue_account_email(
        db,
        user_id=user.id,
        event_type="account_exists",
        intent_id=uuid.uuid4(),
        agora=_AGORA - timedelta(minutes=1),
    )
    await db.commit()
    outbox_id = outbox.id

    settings = _settings()
    with patch("app.services.email._get_mail_client") as mock_client:
        mock_fm = AsyncMock()
        mock_fm.send_message = AsyncMock(side_effect=_ErroComCodigoError(550))
        mock_client.return_value = mock_fm
        await processa_lote(db_factory, settings, worker_id="w1", agora=_AGORA)

    atualizado = await db.get(EmailOutbox, outbox_id)
    await db.refresh(atualizado)
    assert atualizado.status == "dead"

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_retry_gera_token_valido_de_novo(db, db_factory):
    """Depois de uma falha temporária, a PRÓXIMA tentativa gera outro token —

    diferente do primeiro (iat mudou), mas igualmente válido: a auditoria da
    Fase 3C confirmou que a validação compara ESTADO, não identidade do
    token."""
    user = _usuario(email_verified=False)
    db.add(user)
    await db.commit()
    outbox = enqueue_account_email(
        db,
        user_id=user.id,
        event_type="verification",
        intent_id=uuid.uuid4(),
        agora=_AGORA - timedelta(minutes=1),
    )
    await db.commit()
    outbox_id = outbox.id

    settings = _settings()
    tokens: list[str] = []

    async def _captura_token(destinatario, assunto, texto, settings_, *, html, contexto):
        link_token = texto.split("token=")[1].split()[0].split(")")[0]
        tokens.append(link_token)
        return EmailDeliveryResult(EmailDeliveryStatus.temporary_failure, "SMTPServerDisconnected")

    with patch(
        "app.services.email_outbox.send_email_detalhado", new=AsyncMock(side_effect=_captura_token)
    ):
        await processa_lote(db_factory, settings, worker_id="w1", agora=_AGORA)

    atualizado = await db.get(EmailOutbox, outbox_id)
    await db.refresh(atualizado)
    assert atualizado.status == "pending"

    async def _sucesso(destinatario, assunto, texto, settings_, *, html, contexto):
        link_token = texto.split("token=")[1].split()[0].split(")")[0]
        tokens.append(link_token)
        return EmailDeliveryResult(EmailDeliveryStatus.success)

    with patch(
        "app.services.email_outbox.send_email_detalhado", new=AsyncMock(side_effect=_sucesso)
    ):
        await processa_lote(db_factory, settings, worker_id="w1", agora=atualizado.next_attempt_at)

    assert len(tokens) == 2
    # Os DOIS continuam válidos — nenhum invalida o outro. (Não afirmamos
    # `tokens[0] != tokens[1]`: `iat` tem granularidade de segundo, e as duas
    # tentativas deste teste podem cair no mesmo segundo de relógio — a
    # garantia real, e a única que importa, é que retry nunca invalida o
    # token anterior nem produz um token inválido.)
    assert account_tokens.read_email_verification_token(tokens[0], False, settings) == user.id
    assert account_tokens.read_email_verification_token(tokens[1], False, settings) == user.id

    await _limpa(db, user)


# ═══════════════════════════════════════════════════════════════
# Elegibilidade: usuário removido, anonymized, inactive, já verificado
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_delete_user_cascade_remove_outbox_de_conta(db):
    user = _usuario()
    db.add(user)
    await db.commit()
    outbox = enqueue_account_email(
        db, user_id=user.id, event_type="verification", intent_id=uuid.uuid4()
    )
    await db.commit()
    outbox_id = outbox.id

    alvo = await db.get(User, user.id)
    await db.delete(alvo)
    await db.commit()

    resultado = await db.execute(select(EmailOutbox.id).where(EmailOutbox.id == outbox_id))
    assert resultado.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_usuario_anonymized_vai_para_dead_sem_smtp(db, db_factory):
    user = _usuario(status=UserStatus.anonymized)
    db.add(user)
    await db.commit()
    outbox = enqueue_account_email(
        db, user_id=user.id, event_type="verification", intent_id=uuid.uuid4()
    )
    await db.commit()
    outbox_id = outbox.id

    settings = _settings()
    with patch("app.services.email_outbox.send_email_detalhado", new=AsyncMock()) as smtp:
        await _processa_conta(db_factory, settings, outbox_id, user.id, "verification")

    smtp.assert_not_awaited()
    atualizado = await db.get(EmailOutbox, outbox_id)
    await db.refresh(atualizado)
    assert atualizado.status == "dead"
    assert atualizado.last_error == _CONTA_USUARIO_ANONIMIZADO

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_password_reset_para_inactive_vai_para_dead(db, db_factory):
    user = _usuario(status=UserStatus.inactive)
    db.add(user)
    await db.commit()
    outbox = enqueue_account_email(
        db, user_id=user.id, event_type="password_reset", intent_id=uuid.uuid4()
    )
    await db.commit()
    outbox_id = outbox.id

    settings = _settings()
    with patch("app.services.email_outbox.send_email_detalhado", new=AsyncMock()) as smtp:
        await _processa_conta(db_factory, settings, outbox_id, user.id, "password_reset")

    smtp.assert_not_awaited()
    atualizado = await db.get(EmailOutbox, outbox_id)
    await db.refresh(atualizado)
    assert atualizado.status == "dead"
    assert atualizado.last_error == _CONTA_USUARIO_INATIVO

    await _limpa(db, user)


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", ["verification", "account_exists"])
async def test_inactive_permitido_para_verification_e_account_exists(db, db_factory, event_type):
    user = _usuario(status=UserStatus.inactive, email_verified=False)
    db.add(user)
    await db.commit()
    outbox = enqueue_account_email(
        db, user_id=user.id, event_type=event_type, intent_id=uuid.uuid4()
    )
    await db.commit()
    outbox_id = outbox.id

    settings = _settings()
    with patch("app.services.email._get_mail_client") as mock_client:
        mock_fm = AsyncMock()
        mock_fm.send_message = AsyncMock()
        mock_client.return_value = mock_fm
        await _processa_conta(db_factory, settings, outbox_id, user.id, event_type)

    atualizado = await db.get(EmailOutbox, outbox_id)
    await db.refresh(atualizado)
    assert atualizado.status == "sent"

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_verificacao_ja_concluida_antes_do_worker_nao_envia(db, db_factory):
    """Entre o enqueue e o processamento, o usuário confirmou o e-mail por

    outro caminho (ex.: clicou num link mais recente). Mandar a confirmação
    de novo seria ruído — vai para `dead` com motivo operacional seguro."""
    user = _usuario(email_verified=False)
    db.add(user)
    await db.commit()
    outbox = enqueue_account_email(
        db, user_id=user.id, event_type="verification", intent_id=uuid.uuid4()
    )
    await db.commit()
    outbox_id = outbox.id

    # O estado muda DEPOIS do enqueue, antes do processamento.
    alvo = await db.get(User, user.id)
    alvo.email_verified = True
    await db.commit()

    settings = _settings()
    with patch("app.services.email_outbox.send_email_detalhado", new=AsyncMock()) as smtp:
        await _processa_conta(db_factory, settings, outbox_id, user.id, "verification")

    smtp.assert_not_awaited()
    atualizado = await db.get(EmailOutbox, outbox_id)
    await db.refresh(atualizado)
    assert atualizado.status == "dead"
    assert atualizado.last_error == _CONTA_VERIFICACAO_JA_CONCLUIDA

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_email_alterado_usa_endereco_atual(db, db_factory):
    user = _usuario()
    db.add(user)
    await db.commit()
    outbox = enqueue_account_email(
        db, user_id=user.id, event_type="account_exists", intent_id=uuid.uuid4()
    )
    await db.commit()
    outbox_id = outbox.id

    # E-mail muda DEPOIS do enqueue.
    alvo = await db.get(User, user.id)
    novo_email = f"trocado-{uuid.uuid4().hex[:8]}@test.invalid"
    alvo.email = novo_email
    await db.commit()

    settings = _settings()
    destinatarios = []

    async def _envio(destinatario, assunto, texto, settings_, *, html, contexto):
        destinatarios.append(destinatario)
        return EmailDeliveryResult(EmailDeliveryStatus.success)

    with patch("app.services.email_outbox.send_email_detalhado", new=AsyncMock(side_effect=_envio)):
        await _processa_conta(db_factory, settings, outbox_id, user.id, "account_exists")

    assert destinatarios == [novo_email]

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_usuario_nao_encontrado_nao_tenta_smtp(db_factory):
    """Defensivo: o CASCADE já deveria ter removido a linha junto com o

    usuário — chegar aqui com `user_id` órfão não deveria acontecer (por
    isso não há um `outbox_id` real: `_persiste_resultado` simplesmente não
    encontra a linha e retorna, o que já é coberto em
    `test_email_outbox_postgres.py`). O que este teste prova é que
    `_processa_conta`, sozinha, nunca chega perto de SMTP quando o usuário
    não existe."""
    settings = _settings()
    with patch("app.services.email_outbox.send_email_detalhado", new=AsyncMock()) as smtp:
        await _processa_conta(db_factory, settings, uuid.uuid4(), uuid.uuid4(), "verification")

    smtp.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════
# Duas origens no mesmo lote — Notification (3B) continua funcionando
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_lote_processa_as_duas_origens_juntas(db, db_factory):
    """Notification e Account no MESMO `processa_lote` — prova que o worker

    único (`FOR UPDATE SKIP LOCKED`, retry, backoff) serve as duas origens
    sem regressão."""
    user = _usuario(email_verified=False)
    db.add(user)
    await db.commit()

    notif = Notification(
        id=uuid.uuid4(),
        user_id=user.id,
        type="ticket_created",
        title="Ticket aberto",
        message="Seu ticket foi registrado com o protocolo HS-2026-0001.",
        data=None,
        read=False,
        email_sent=False,
    )
    db.add(notif)
    await db.commit()
    outbox_notif = enqueue_email(db, notif, agora=_AGORA - timedelta(minutes=1))
    outbox_conta = enqueue_account_email(
        db,
        user_id=user.id,
        event_type="account_exists",
        intent_id=uuid.uuid4(),
        agora=_AGORA - timedelta(minutes=1),
    )
    await db.commit()

    settings = _settings()
    with patch("app.services.email._get_mail_client") as mock_client:
        mock_fm = AsyncMock()
        mock_fm.send_message = AsyncMock()
        mock_client.return_value = mock_fm
        processados = await processa_lote(db_factory, settings, worker_id="w1", agora=_AGORA)

    assert processados == 2

    outbox_notif_atualizado = await db.get(EmailOutbox, outbox_notif.id)
    await db.refresh(outbox_notif_atualizado)
    assert outbox_notif_atualizado.status == "sent"

    outbox_conta_atualizado = await db.get(EmailOutbox, outbox_conta.id)
    await db.refresh(outbox_conta_atualizado)
    assert outbox_conta_atualizado.status == "sent"

    notif_atualizada = await db.get(Notification, notif.id)
    await db.refresh(notif_atualizada)
    assert notif_atualizada.email_sent is True, "regressão 3B: email_sent continua funcionando"

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_email_sent_nao_e_tocado_para_origem_account(db, db_factory):
    """`Notification.email_sent` só é tocado quando `notification_id IS NOT

    NULL` — uma linha de origem Account não tem `Notification` para tocar, e
    a implementação não pode tentar (ou levantar tentando)."""
    user = _usuario()
    db.add(user)
    await db.commit()
    outbox = enqueue_account_email(
        db,
        user_id=user.id,
        event_type="account_exists",
        intent_id=uuid.uuid4(),
        agora=_AGORA - timedelta(minutes=1),
    )
    await db.commit()
    outbox_id = outbox.id

    settings = _settings()
    with patch("app.services.email._get_mail_client") as mock_client:
        mock_fm = AsyncMock()
        mock_fm.send_message = AsyncMock()
        mock_client.return_value = mock_fm
        await processa_lote(db_factory, settings, worker_id="w1", agora=_AGORA)

    atualizado = await db.get(EmailOutbox, outbox_id)
    await db.refresh(atualizado)
    assert atualizado.status == "sent"  # não levantou

    await _limpa(db, user)


# ═══════════════════════════════════════════════════════════════
# Concorrência — dois workers, restart, dedup por SKIP LOCKED
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_dois_workers_nao_reivindicam_a_mesma_linha_de_conta(db, db_factory):
    user = _usuario()
    db.add(user)
    await db.commit()
    for _ in range(6):
        enqueue_account_email(
            db,
            user_id=user.id,
            event_type="account_exists",
            intent_id=uuid.uuid4(),
            agora=_AGORA - timedelta(minutes=1),
        )
    await db.commit()

    lote_a, lote_b = await asyncio.gather(
        reivindica_lote(db_factory, limite=3, worker_id="w1", agora=_AGORA),
        reivindica_lote(db_factory, limite=3, worker_id="w2", agora=_AGORA),
    )

    assert set(lote_a).isdisjoint(set(lote_b))
    assert len(set(lote_a) | set(lote_b)) == 6

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_restart_de_linha_de_conta_travada_e_recuperada(db, db_factory):
    from app.services.email_outbox import recupera_travados

    user = _usuario()
    db.add(user)
    await db.commit()
    outbox = _outbox_conta(
        user,
        "account_exists",
        status="processing",
        locked_by="worker-morto",
        locked_at=_AGORA - timedelta(minutes=10),
    )
    db.add(outbox)
    await db.commit()

    recuperados = await recupera_travados(db_factory, stale_minutes=5, agora=_AGORA)
    assert recuperados == 1

    atualizado = await db.get(EmailOutbox, outbox.id)
    await db.refresh(atualizado)
    assert atualizado.status == "pending"

    await _limpa(db, user)


# ═══════════════════════════════════════════════════════════════
# Logs sem PII nem token
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_logs_sem_pii_nem_token(db, db_factory):
    from loguru import logger

    user = _usuario(email_verified=False, nome="Cliente Real")
    endereco = user.email
    db.add(user)
    await db.commit()
    outbox = enqueue_account_email(
        db, user_id=user.id, event_type="verification", intent_id=uuid.uuid4()
    )
    await db.commit()
    outbox_id = outbox.id

    settings = _settings()
    linhas: list[str] = []
    sink = logger.add(lambda m: linhas.append(m.record["message"]), level="DEBUG")
    try:
        with patch("app.services.email._get_mail_client") as mock_client:
            mock_fm = AsyncMock()
            mock_fm.send_message = AsyncMock(side_effect=_ErroComCodigoError(550))
            mock_client.return_value = mock_fm
            await _processa_conta(db_factory, settings, outbox_id, user.id, "verification")
    finally:
        logger.remove(sink)

    texto = "\n".join(linhas)
    assert endereco not in texto
    assert "Cliente Real" not in texto
    assert "mensagem crua do servidor" not in texto
    assert str(outbox_id) in texto, "o outbox_id é o correlator, e deve ficar"

    await _limpa(db, user)
