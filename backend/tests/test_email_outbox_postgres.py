"""
Fase 3A — outbox de e-mail, contra PostgreSQL de verdade.

Por que este arquivo existe
----------------------------
`FOR UPDATE SKIP LOCKED`, `UNIQUE(notification_id)` e o `CASCADE` de
`notification_id` só têm semântica real em Postgres. O worker inteiro (
`app/services/email_outbox.py`) existe por causa de garantias que só o banco
de verdade oferece — testar contra mock provaria a lógica, nunca a garantia.

Sessão presa ao ENGINE, não a uma conexão+savepoint
------------------------------------------------------
Os testes de concorrência (SKIP LOCKED entre "dois workers") precisam de
COMMITS de verdade, visíveis entre sessões diferentes — um savepoint revertido
no fim do teste esconderia justamente o que este arquivo verifica (mesma
lição já registrada em `test_delete_usuario_ondelete_postgres.py`). Cada teste
é responsável por limpar o que criou: apagar o `User` já basta, porque o
CASCADE `user -> notification -> email_outbox` limpa o resto sozinho.
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
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.models.models import (
    Base,
    EmailOutbox,
    Notification,
    NotificationType,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
)
from app.services.email import EmailDeliveryResult, EmailDeliveryStatus
from app.services.email_outbox import (
    _assunto_reconstruido,
    _carrega_contexto,
    _persiste_resultado,
    _processa_um,
    contadores_por_status,
    enqueue_email,
    processa_lote,
    recupera_travados,
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
    """A própria `async_sessionmaker` que as funções de `email_outbox.py`

    esperam receber como `db_factory` — cada chamada abre e fecha a sua
    própria sessão/transação, do jeito que o worker real faz."""
    motor = create_async_engine(url_do_banco)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    yield fabrica
    await motor.dispose()


@pytest_asyncio.fixture
async def db(db_factory):
    async with db_factory() as sessao:
        yield sessao


def _usuario(nome: str = "Alvo") -> User:
    return User(
        id=uuid.uuid4(),
        name=nome,
        email=f"{uuid.uuid4().hex[:10]}@test.invalid",
        password="x",
        role=UserRole.technician,
        status=UserStatus.active,
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
        created_at=_AGORA,
        updated_at=_AGORA,
    )


def _notificacao(
    user: User,
    *,
    title: str = "Ticket aberto",
    message: str = "Seu ticket foi registrado com o protocolo HS-2026-0001.",
    data: dict | None = None,
) -> Notification:
    return Notification(
        id=uuid.uuid4(),
        user_id=user.id,
        type=NotificationType.ticket_created,
        title=title,
        message=message,
        data=data,
        read=False,
        email_sent=False,
    )


def _chamado(criador: User, *, titulo: str = "Impressora da recepção sem conexão") -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        protocol=f"HS-2026-{uuid.uuid4().hex[:6]}",
        title=titulo,
        description="corpo",
        priority=TicketPriority.medium,
        category=TicketCategory.hardware,
        status=TicketStatus.open,
        creator_id=criador.id,
        auto_closed=False,
        reopen_count=0,
        created_at=_AGORA,
        updated_at=_AGORA,
    )


def _outbox(
    notif: Notification, *, status: str = "pending", next_attempt_at=None, **overrides
) -> EmailOutbox:
    campos = dict(
        id=uuid.uuid4(),
        notification_id=notif.id,
        status=status,
        attempts=0,
        next_attempt_at=next_attempt_at or _AGORA,
    )
    campos.update(overrides)
    return EmailOutbox(**campos)


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        smtp_from_email="from@test.com",
        smtp_user="from@test.com",
        smtp_host="localhost",
        smtp_port=1025,
        email_outbox_batch_size=10,
        email_outbox_stale_processing_minutes=5,
    )
    base.update(overrides)
    return Settings(**base)


async def _limpa(db, *users: User) -> None:
    """Apagar o `User` cascateia por `notifications` até `email_outbox`.

    Lê o id via `InstanceState.identity`, não via `u.id`: depois de um
    `rollback()` — inclusive de uma transação ANTERIOR na mesma sessão —,
    `expire_on_commit=False` não protege o objeto, e tocar `.id` dispara um
    refresh lazy síncrono fora do greenlet (`MissingGreenlet`). `identity` lê
    a chave primária guardada no `InstanceState` no momento do flush original,
    sem tocar atributo nenhum do objeto.
    """
    for u in users:
        uid = sa_inspect(u).identity[0]
        alvo = await db.get(User, uid)
        if alvo is not None:
            await db.delete(alvo)
    await db.commit()


class _ErroComCodigoError(Exception):
    def __init__(self, code: int):
        super().__init__("mensagem crua do servidor")
        self.code = code


# ═══════════════════════════════════════════════════════════════
# Schema: UNIQUE, CASCADE, CHECK
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_unique_notification_id_impede_duas_linhas(db):
    user = _usuario()
    notif = _notificacao(user)
    db.add_all([user, notif])
    await db.commit()

    db.add(_outbox(notif))
    await db.commit()

    db.add(_outbox(notif))
    with pytest.raises(Exception):  # IntegrityError da UNIQUE
        await db.commit()
    await db.rollback()

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_cascade_apaga_outbox_quando_notification_some(db):
    user = _usuario()
    notif = _notificacao(user)
    db.add_all([user, notif])
    await db.commit()

    outbox = _outbox(notif)
    db.add(outbox)
    await db.commit()
    outbox_id = outbox.id
    notif_id = notif.id

    alvo = await db.get(Notification, notif_id)
    await db.delete(alvo)
    await db.commit()

    # `db.get()` consultaria o identity map primeiro e devolveria o `outbox`
    # em cache de ANTES do delete — o CASCADE aconteceu no Postgres, não pelo
    # unit of work, então a sessão não tem como saber sozinha. Um SELECT de
    # coluna escalar ignora o identity map e força a ida ao banco (mesma
    # técnica de `_existe` em test_delete_usuario_ondelete_postgres.py).
    resultado = await db.execute(select(EmailOutbox.id).where(EmailOutbox.id == outbox_id))
    assert resultado.scalar_one_or_none() is None

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_check_status_recusa_valor_desconhecido(db):
    user = _usuario()
    notif = _notificacao(user)
    db.add_all([user, notif])
    await db.commit()

    db.add(_outbox(notif, status="enviando"))
    with pytest.raises(Exception):  # CheckConstraint
        await db.commit()
    await db.rollback()

    await _limpa(db, user)


# ═══════════════════════════════════════════════════════════════
# Reivindicação: pending vencido entra, futuro fica de fora
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_claim_pega_pending_vencido(db, db_factory):
    user = _usuario()
    notif = _notificacao(user)
    db.add_all([user, notif])
    await db.commit()
    outbox = _outbox(notif, next_attempt_at=_AGORA - timedelta(minutes=1))
    db.add(outbox)
    await db.commit()

    ids = await reivindica_lote(db_factory, limite=10, worker_id="w1", agora=_AGORA)
    assert outbox.id in ids

    atualizado = await db.get(EmailOutbox, outbox.id)
    await db.refresh(atualizado)
    assert atualizado.status == "processing"
    assert atualizado.locked_by == "w1"
    assert atualizado.locked_at is not None

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_claim_pega_next_attempt_at_exatamente_agora(db, db_factory):
    """Alvo de mutação em `next_attempt_at <= agora`: virar `<` deixaria de

    fora uma linha vencida EXATAMENTE agora — "vencido" inclui o instante
    exato, não só o passado estrito."""
    user = _usuario()
    notif = _notificacao(user)
    db.add_all([user, notif])
    await db.commit()
    outbox = _outbox(notif, next_attempt_at=_AGORA)
    db.add(outbox)
    await db.commit()

    ids = await reivindica_lote(db_factory, limite=10, worker_id="w1", agora=_AGORA)
    assert outbox.id in ids

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_claim_nao_pega_next_attempt_at_futuro(db, db_factory):
    user = _usuario()
    notif = _notificacao(user)
    db.add_all([user, notif])
    await db.commit()
    outbox = _outbox(notif, next_attempt_at=_AGORA + timedelta(minutes=5))
    db.add(outbox)
    await db.commit()

    ids = await reivindica_lote(db_factory, limite=10, worker_id="w1", agora=_AGORA)
    assert outbox.id not in ids

    atualizado = await db.get(EmailOutbox, outbox.id)
    assert atualizado.status == "pending"

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_claim_ignora_linhas_ja_processing_ou_sent(db, db_factory):
    user = _usuario()
    n1 = _notificacao(user)
    n2 = _notificacao(user)
    db.add_all([user, n1, n2])
    await db.commit()
    ja_processando = _outbox(n1, status="processing", locked_by="outro", locked_at=_AGORA)
    ja_enviado = _outbox(n2, status="sent", sent_at=_AGORA)
    db.add_all([ja_processando, ja_enviado])
    await db.commit()

    ids = await reivindica_lote(db_factory, limite=10, worker_id="w1", agora=_AGORA)
    assert ids == []

    await _limpa(db, user)


# ═══════════════════════════════════════════════════════════════
# Dois workers concorrentes / SKIP LOCKED
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_dois_workers_concorrentes_nao_reivindicam_a_mesma_linha(db, db_factory):
    user = _usuario()
    notifs = [_notificacao(user) for _ in range(6)]
    db.add_all([user, *notifs])
    await db.commit()
    outboxes = [_outbox(n, next_attempt_at=_AGORA - timedelta(minutes=1)) for n in notifs]
    db.add_all(outboxes)
    await db.commit()

    lote_a, lote_b = await asyncio.gather(
        reivindica_lote(db_factory, limite=3, worker_id="w1", agora=_AGORA),
        reivindica_lote(db_factory, limite=3, worker_id="w2", agora=_AGORA),
    )

    assert set(lote_a).isdisjoint(set(lote_b))
    assert len(set(lote_a) | set(lote_b)) == 6  # todas as 6 foram reivindicadas, sem sobra

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_nenhum_lock_fica_aberto_durante_o_envio_smtp(db, db_factory):
    """Reivindica uma linha, e ENQUANTO o envio (mockado, lento) está em voo,

    uma segunda sessão consegue travar a MESMA linha com `FOR UPDATE NOWAIT`
    sem bloquear nem levantar. Se a transação da reivindicação ainda estivesse
    aberta durante o envio, este `NOWAIT` teria que falhar."""
    user = _usuario()
    notif = _notificacao(user)
    db.add_all([user, notif])
    await db.commit()
    outbox = _outbox(notif, next_attempt_at=_AGORA - timedelta(minutes=1))
    db.add(outbox)
    await db.commit()
    outbox_id = outbox.id

    ids = await reivindica_lote(db_factory, limite=1, worker_id="w1", agora=_AGORA)
    assert ids == [outbox_id]

    settings = _settings()

    async def _envio_lento(*args, **kwargs):
        await asyncio.sleep(0.3)
        return EmailDeliveryResult(EmailDeliveryStatus.success)

    with patch("app.services.email_outbox.send_email_detalhado", side_effect=_envio_lento):
        tarefa = asyncio.create_task(_processa_um(db_factory, settings, outbox_id))
        await asyncio.sleep(0.05)  # deixa o envio "em voo"

        # Consegue travar a linha sem bloquear: prova que a reivindicação já
        # tinha commitado e nenhuma sessão está segurando o lock enquanto o
        # "SMTP" está em andamento.
        async with db_factory() as outra_sessao:
            resultado = await outra_sessao.execute(
                text("SELECT id FROM email_outbox WHERE id = :id FOR UPDATE NOWAIT"),
                {"id": str(outbox_id)},
            )
            assert resultado.scalar_one() is not None
            await outra_sessao.rollback()

        await tarefa

    atualizado = await db.get(EmailOutbox, outbox_id)
    await db.refresh(atualizado)
    assert atualizado.status == "sent"

    await _limpa(db, user)


# ═══════════════════════════════════════════════════════════════
# Desfechos: sucesso, falha temporária, falha permanente, 5ª tentativa
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sucesso_marca_sent_com_sent_at(db, db_factory):
    user = _usuario()
    notif = _notificacao(user)
    db.add_all([user, notif])
    await db.commit()
    outbox = _outbox(notif, status="processing", locked_by="w1", locked_at=_AGORA)
    db.add(outbox)
    await db.commit()

    await _persiste_resultado(
        db_factory, outbox.id, EmailDeliveryResult(EmailDeliveryStatus.success), agora=_AGORA
    )

    atualizado = await db.get(EmailOutbox, outbox.id)
    await db.refresh(atualizado)
    assert atualizado.status == "sent"
    assert atualizado.sent_at == _AGORA
    assert atualizado.locked_by is None
    assert atualizado.locked_at is None

    notif_atualizada = await db.get(Notification, notif.id)
    await db.refresh(notif_atualizada)
    assert notif_atualizada.email_sent is True, "sent + email_sent precisam ser consistentes"

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_falha_temporaria_volta_a_pending_com_backoff_e_attempts(db, db_factory):
    user = _usuario()
    notif = _notificacao(user)
    db.add_all([user, notif])
    await db.commit()
    outbox = _outbox(notif, status="processing", attempts=0, locked_by="w1", locked_at=_AGORA)
    db.add(outbox)
    await db.commit()

    await _persiste_resultado(
        db_factory,
        outbox.id,
        EmailDeliveryResult(EmailDeliveryStatus.temporary_failure, "SMTPServerDisconnected"),
        agora=_AGORA,
    )

    atualizado = await db.get(EmailOutbox, outbox.id)
    await db.refresh(atualizado)
    assert atualizado.status == "pending"
    assert atualizado.attempts == 1
    assert atualizado.next_attempt_at == _AGORA + timedelta(minutes=1)
    assert atualizado.last_error == "SMTPServerDisconnected"
    assert atualizado.locked_by is None

    notif_atualizada = await db.get(Notification, notif.id)
    await db.refresh(notif_atualizada)
    assert notif_atualizada.email_sent is False, "falha temporária não marca como enviado"

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_quinta_falha_vai_para_dead(db, db_factory):
    user = _usuario()
    notif = _notificacao(user)
    db.add_all([user, notif])
    await db.commit()
    outbox = _outbox(notif, status="processing", attempts=4, locked_by="w1", locked_at=_AGORA)
    db.add(outbox)
    await db.commit()

    await _persiste_resultado(
        db_factory,
        outbox.id,
        EmailDeliveryResult(EmailDeliveryStatus.temporary_failure, "SMTPServerDisconnected"),
        agora=_AGORA,
    )

    atualizado = await db.get(EmailOutbox, outbox.id)
    await db.refresh(atualizado)
    assert atualizado.status == "dead"
    assert atualizado.attempts == 5

    notif_atualizada = await db.get(Notification, notif.id)
    await db.refresh(notif_atualizada)
    assert notif_atualizada.email_sent is False, "dead não marca como enviado"

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_falha_permanente_vai_direto_para_dead_sem_gastar_tentativas(db, db_factory):
    user = _usuario()
    notif = _notificacao(user)
    db.add_all([user, notif])
    await db.commit()
    outbox = _outbox(notif, status="processing", attempts=0, locked_by="w1", locked_at=_AGORA)
    db.add(outbox)
    await db.commit()

    await _persiste_resultado(
        db_factory,
        outbox.id,
        EmailDeliveryResult(
            EmailDeliveryStatus.permanent_failure, "SMTPRecipientRefused (code 550)"
        ),
        agora=_AGORA,
    )

    atualizado = await db.get(EmailOutbox, outbox.id)
    await db.refresh(atualizado)
    assert atualizado.status == "dead"
    assert atualizado.attempts == 1  # registrado, mas não usado para retry

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_processa_lote_ponta_a_ponta_sucesso(db, db_factory):
    user = _usuario(nome="Fulano de Tal")
    notif = _notificacao(
        user,
        title="Ticket aberto",
        message="Seu ticket foi registrado com o protocolo HS-2026-0001.",
        data={"ticket_id": str(uuid.uuid4()), "protocol": "HS-2026-0001"},
    )
    db.add_all([user, notif])
    await db.commit()
    outbox = _outbox(notif, next_attempt_at=_AGORA - timedelta(minutes=1))
    db.add(outbox)
    await db.commit()

    settings = _settings()
    with patch(
        "app.services.email_outbox.send_email_detalhado",
        new=AsyncMock(return_value=EmailDeliveryResult(EmailDeliveryStatus.success)),
    ) as mock_send:
        processados = await processa_lote(db_factory, settings, worker_id="w1", agora=_AGORA)

    assert processados == 1
    mock_send.assert_awaited_once()
    args, kwargs = mock_send.call_args
    destinatario, assunto, corpo, _settings_recebido = args
    assert destinatario == user.email
    assert "HS-2026-0001" in assunto  # reconstruído via _assunto_do_email/data
    assert kwargs["html"]  # veio de em_html(mensagem)

    atualizado = await db.get(EmailOutbox, outbox.id)
    await db.refresh(atualizado)
    assert atualizado.status == "sent"

    await _limpa(db, user)


# ═══════════════════════════════════════════════════════════════
# Recuperação de linha travada (crash / restart simulado)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_processing_stale_e_recuperado(db, db_factory):
    user = _usuario()
    notif = _notificacao(user)
    db.add_all([user, notif])
    await db.commit()
    velho = _AGORA - timedelta(minutes=10)
    outbox = _outbox(notif, status="processing", locked_by="worker-morto", locked_at=velho)
    db.add(outbox)
    await db.commit()

    recuperados = await recupera_travados(db_factory, stale_minutes=5, agora=_AGORA)
    assert recuperados == 1

    atualizado = await db.get(EmailOutbox, outbox.id)
    await db.refresh(atualizado)
    assert atualizado.status == "pending"
    assert atualizado.locked_by is None
    assert atualizado.locked_at is None

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_processing_recente_nao_e_recuperado(db, db_factory):
    user = _usuario()
    notif = _notificacao(user)
    db.add_all([user, notif])
    await db.commit()
    recente = _AGORA - timedelta(minutes=1)
    outbox = _outbox(notif, status="processing", locked_by="worker-vivo", locked_at=recente)
    db.add(outbox)
    await db.commit()

    recuperados = await recupera_travados(db_factory, stale_minutes=5, agora=_AGORA)
    assert recuperados == 0

    atualizado = await db.get(EmailOutbox, outbox.id)
    await db.refresh(atualizado)
    assert atualizado.status == "processing"

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_fronteira_exata_do_stale_nao_e_recuperada(db, db_factory):
    """Alvo de mutação em `locked_at < limite`: virar `<=` recuperaria uma

    linha travada há EXATAMENTE `stale_minutes`, cedo demais — o worker que a
    travou ainda pode estar dentro do prazo normal."""
    user = _usuario()
    notif = _notificacao(user)
    db.add_all([user, notif])
    await db.commit()
    exatamente_no_limite = _AGORA - timedelta(minutes=5)
    outbox = _outbox(notif, status="processing", locked_by="w1", locked_at=exatamente_no_limite)
    db.add(outbox)
    await db.commit()

    recuperados = await recupera_travados(db_factory, stale_minutes=5, agora=_AGORA)
    assert recuperados == 0

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_restart_simulado_linha_travada_e_reivindicada_de_novo(db, db_factory):
    """Nada no worker vive em memória entre chamadas — cada função abre e

    fecha sua própria sessão. Uma linha `processing` "esquecida" por um
    processo que morreu é indistinguível, para um `processa_lote` novo, de uma
    linha travada antes de um restart: os dois casos passam pelo mesmo
    caminho de recuperação."""
    user = _usuario()
    notif = _notificacao(user)
    db.add_all([user, notif])
    await db.commit()
    velho = _AGORA - timedelta(minutes=10)
    outbox = _outbox(notif, status="processing", locked_by="processo-que-morreu", locked_at=velho)
    db.add(outbox)
    await db.commit()

    settings = _settings()
    with patch(
        "app.services.email_outbox.send_email_detalhado",
        new=AsyncMock(return_value=EmailDeliveryResult(EmailDeliveryStatus.success)),
    ):
        processados = await processa_lote(db_factory, settings, worker_id="w-novo", agora=_AGORA)

    assert processados == 1
    atualizado = await db.get(EmailOutbox, outbox.id)
    await db.refresh(atualizado)
    assert atualizado.status == "sent"

    await _limpa(db, user)


# ═══════════════════════════════════════════════════════════════
# Redis indisponível não impede o funcionamento (zero dependência)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_redis_indisponivel_nao_impede_o_worker(db, db_factory):
    user = _usuario()
    notif = _notificacao(user)
    db.add_all([user, notif])
    await db.commit()
    outbox = _outbox(notif, next_attempt_at=_AGORA - timedelta(minutes=1))
    db.add(outbox)
    await db.commit()

    settings = _settings()

    async def _redis_fora_do_ar():
        raise ConnectionError("Redis indisponível")

    with (
        patch("app.core.redis.get_redis", side_effect=_redis_fora_do_ar),
        patch(
            "app.services.email_outbox.send_email_detalhado",
            new=AsyncMock(return_value=EmailDeliveryResult(EmailDeliveryStatus.success)),
        ),
    ):
        processados = await processa_lote(db_factory, settings, worker_id="w1", agora=_AGORA)

    assert processados == 1  # nenhum caminho deste módulo chama get_redis

    await _limpa(db, user)


# ═══════════════════════════════════════════════════════════════
# Logs sem PII no ciclo completo (claim -> envio -> persistência)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_logs_do_ciclo_completo_sem_pii(db, db_factory):
    from loguru import logger

    endereco = "cliente.real@empresa.com.br"
    titulo_do_chamado = "Impressora da recepcao sem conexao"

    user = _usuario(nome="Cliente Real")
    user.email = endereco
    notif = _notificacao(
        user,
        title="Ticket aberto",
        message=f"HS-2026-0099 — {titulo_do_chamado}",
        data={"ticket_id": str(uuid.uuid4()), "protocol": "HS-2026-0099"},
    )
    db.add_all([user, notif])
    await db.commit()
    outbox = _outbox(notif, next_attempt_at=_AGORA - timedelta(minutes=1))
    db.add(outbox)
    await db.commit()

    settings = _settings()
    linhas: list[str] = []
    sink = logger.add(lambda m: linhas.append(m.record["message"]), level="DEBUG")
    try:
        with patch("app.services.email._get_mail_client") as mock_client:
            mock_fm = AsyncMock()
            mock_fm.send_message = AsyncMock(side_effect=_ErroComCodigoError(550))
            mock_client.return_value = mock_fm
            await processa_lote(db_factory, settings, worker_id="w1", agora=_AGORA)
    finally:
        logger.remove(sink)

    texto = "\n".join(linhas)
    assert endereco not in texto
    assert titulo_do_chamado not in texto
    assert "mensagem crua do servidor" not in texto

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_sucesso_nao_vaza_endereco_so_o_outbox_id(db, db_factory):
    """A contraparte de sucesso: o `outbox_id` é o correlator que fica no log

    (papel que `notif_id` fazia no mecanismo antigo — ver
    `tests/test_log_sem_segredo.py`), o endereço nunca aparece."""
    from loguru import logger

    endereco = "outro.cliente@empresa.com.br"
    user = _usuario(nome="Outro Cliente")
    user.email = endereco
    notif = _notificacao(user, title="Ticket aberto")
    db.add_all([user, notif])
    await db.commit()
    outbox = _outbox(notif, next_attempt_at=_AGORA - timedelta(minutes=1))
    db.add(outbox)
    await db.commit()
    outbox_id = outbox.id

    settings = _settings()
    linhas: list[str] = []
    sink = logger.add(lambda m: linhas.append(m.record["message"]), level="DEBUG")
    try:
        with patch("app.services.email._get_mail_client") as mock_client:
            mock_fm = AsyncMock()
            mock_fm.send_message = AsyncMock()
            mock_client.return_value = mock_fm
            await processa_lote(db_factory, settings, worker_id="w1", agora=_AGORA)
    finally:
        logger.remove(sink)

    texto = "\n".join(linhas)
    assert endereco not in texto
    assert str(outbox_id) in texto, "o outbox_id saiu do log junto com o endereço"

    await _limpa(db, user)


# ═══════════════════════════════════════════════════════════════
# enqueue_email dentro da transação de negócio: rollback não deixa órfã
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_enqueue_com_rollback_nao_persiste_outbox(db):
    user = _usuario()
    db.add(user)
    await db.commit()

    notif = _notificacao(user)
    db.add(notif)
    enqueue_email(db, notif, agora=_AGORA)
    await db.rollback()

    resultado = await db.execute(select(EmailOutbox).where(EmailOutbox.notification_id == notif.id))
    assert resultado.scalar_one_or_none() is None
    # a própria Notification também não sobreviveu ao rollback
    resultado_notif = await db.execute(select(Notification).where(Notification.id == notif.id))
    assert resultado_notif.scalar_one_or_none() is None

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_enqueue_com_commit_persiste_outbox_junto_com_a_notification(db):
    user = _usuario()
    db.add(user)
    await db.commit()

    notif = _notificacao(user)
    db.add(notif)
    enqueue_email(db, notif, agora=_AGORA)
    await db.commit()

    resultado = await db.execute(select(EmailOutbox).where(EmailOutbox.notification_id == notif.id))
    outbox = resultado.scalar_one()
    assert outbox.status == "pending"
    assert outbox.notification_id == notif.id

    await _limpa(db, user)


@pytest.mark.asyncio
async def test_retry_de_protocolo_nao_deixa_outbox_duplicada(db):
    """Reproduz o laço de `create_ticket`: várias tentativas de `notify()`,

    cada uma seguida de rollback exceto a última, que commita. Antes da Fase
    3B, cada tentativa DESCARTADA já tinha mandado o seu e-mail — o motivo
    histórico do `_PENDENTES` (bug "M6"). Sem aquele mecanismo, a pergunta
    passa a ser: o `db.add()` de uma tentativa descartada sobrevive ao
    `rollback()`? A resposta é não — é o unit of work do SQLAlchemy que
    garante isso, não código deste módulo — e é exatamente isso que este
    teste prova contra Postgres de verdade.
    """
    from app.services.notifications import notify

    user = _usuario()
    db.add(user)
    await db.commit()
    # `user.id` é lido em CADA iteração, e um `rollback()` expira os atributos
    # de todo objeto da sessão (`expire_on_commit=False` só protege o lado do
    # commit) — tocar `user.id` depois disso dispara um refresh lazy síncrono
    # fora do greenlet. Capturado uma vez, em variável simples, nunca mais
    # toca o objeto ORM.
    user_id = user.id
    settings = _settings()

    for tentativa in range(5):
        await notify(
            db,
            user_id,
            NotificationType.ticket_created,
            "Ticket aberto",
            f"Protocolo da tentativa {tentativa}",
            settings=settings,
        )
        if tentativa < 4:
            await db.rollback()
        else:
            await db.commit()

    notifs = (
        (await db.execute(select(Notification).where(Notification.user_id == user_id)))
        .scalars()
        .all()
    )
    assert len(notifs) == 1, "só a tentativa que commitou sobrevive"
    assert notifs[0].message == "Protocolo da tentativa 4"

    outboxes = (
        (await db.execute(select(EmailOutbox).where(EmailOutbox.notification_id == notifs[0].id)))
        .scalars()
        .all()
    )
    assert len(outboxes) == 1, "uma outbox só, não uma por tentativa descartada"

    await _limpa(db, user)  # `_limpa` lê o id via `sa_inspect`, não `.id` — seguro pós-rollback


@pytest.mark.asyncio
async def test_retry_de_lote_nao_deixa_outbox_duplicada(db):
    """O mesmo teste acima, para o lado do `notifica_audiencia` — o laço real

    de `create_ticket` avisa o autor E a equipe a cada tentativa."""
    from types import SimpleNamespace

    from app.services.notifications import notifica_audiencia

    equipe_db = [_usuario(nome="Admin"), _usuario(nome="Tecnico")]
    for pessoa in equipe_db:
        pessoa.role = UserRole.admin if pessoa.name == "Admin" else UserRole.technician
    db.add_all(equipe_db)
    await db.commit()

    # `notifica_audiencia` lê `.id`/`.email`/`.role`/`.name` em CADA iteração,
    # e um `rollback()` expira os atributos de todo objeto da sessão. Um
    # `SimpleNamespace` capturado uma vez, fora da sessão, nunca expira —
    # mesma disciplina do teste irmão (`test_retry_de_protocolo_...`), aqui
    # aplicada a uma lista em vez de um id só.
    equipe = [SimpleNamespace(id=p.id, email=p.email, role=p.role, name=p.name) for p in equipe_db]
    ids_da_equipe = [p.id for p in equipe]
    settings = _settings()

    for tentativa in range(5):
        await notifica_audiencia(
            db,
            equipe,
            NotificationType.ticket_created,
            "Novo chamado",
            f"HS-2026-000{tentativa} — Impressora",
            settings=settings,
        )
        if tentativa < 4:
            await db.rollback()
        else:
            await db.commit()

    notifs = (
        (await db.execute(select(Notification).where(Notification.user_id.in_(ids_da_equipe))))
        .scalars()
        .all()
    )
    assert len(notifs) == 2, "um por destinatário, só da tentativa que commitou"

    outboxes = (
        (
            await db.execute(
                select(EmailOutbox).where(EmailOutbox.notification_id.in_([n.id for n in notifs]))
            )
        )
        .scalars()
        .all()
    )
    assert len(outboxes) == 2, "uma outbox por destinatário, não uma por tentativa descartada"

    await _limpa(db, *equipe_db)  # os objetos ORM reais, não os SimpleNamespace


@pytest.mark.asyncio
async def test_assunto_do_ticket_created_preserva_os_dois_formatos(db, db_factory):
    """`ticket_created` produz DOIS e-mails de formato diferente para o MESMO

    evento — a confirmação ao autor ("Ticket aberto", sem título) e o aviso à
    equipe ("Novo chamado", com título). Reproduz exatamente os dois
    `notify`/`notifica_audiencia` de `create_ticket`
    (`app/routers/tickets.py`) e confere que a reconstrução do worker produz
    byte a byte o mesmo assunto que o código de antes da Fase 3B montava
    inline."""
    from app.services.notifications import notifica_audiencia, notify

    autor = _usuario(nome="Cliente Autor")
    colega = _usuario(nome="Tecnico Colega")
    colega.role = UserRole.technician
    db.add_all([autor, colega])
    await db.commit()

    ticket = _chamado(autor, titulo="Impressora da recepção sem conexão")
    db.add(ticket)
    await db.flush()

    protocolo = ticket.protocol
    dados = {"ticket_id": str(ticket.id), "protocol": protocolo}

    await notify(
        db,
        autor.id,
        NotificationType.ticket_created,
        "Ticket aberto",
        f"Seu ticket foi registrado com o protocolo {protocolo}.",
        data=dados,
        settings=_settings(),
    )
    await notifica_audiencia(
        db,
        [colega],
        NotificationType.ticket_created,
        "Novo chamado",
        f"{protocolo} — {ticket.title}",
        data=dados,
        settings=_settings(),
        exclude_user_ids={autor.id},
    )
    await db.commit()

    notif_autor = (
        await db.execute(select(Notification).where(Notification.user_id == autor.id))
    ).scalar_one()
    notif_colega = (
        await db.execute(select(Notification).where(Notification.user_id == colega.id))
    ).scalar_one()

    contexto_autor = await _carrega_contexto(db, notif_autor.id)
    contexto_colega = await _carrega_contexto(db, notif_colega.id)
    assert contexto_autor is not None and contexto_colega is not None
    notif_a, _user_a, ticket_a = contexto_autor
    notif_c, _user_c, ticket_c = contexto_colega

    assunto_autor = _assunto_reconstruido(notif_a, ticket_a)
    assunto_colega = _assunto_reconstruido(notif_c, ticket_c)

    assert assunto_autor == f"[HelpHS] Ticket aberto — {protocolo}"
    assert ticket.title not in assunto_autor, "confirmação ao autor não leva título"

    assert assunto_colega == f"[HelpHS] Novo chamado {protocolo} — {ticket.title}"

    # O Ticket referencia `creator_id` sem CASCADE — apaga antes dos usuários.
    ticket_no_banco = await db.get(Ticket, ticket.id)
    if ticket_no_banco is not None:
        await db.delete(ticket_no_banco)
        await db.commit()
    await _limpa(db, autor, colega)


# ═══════════════════════════════════════════════════════════════
# Observabilidade — contagens por estado, sem PII
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_contadores_por_status(db, db_factory):
    user = _usuario()
    notifs = [_notificacao(user) for _ in range(3)]
    db.add_all([user, *notifs])
    await db.commit()
    db.add_all(
        [
            _outbox(notifs[0], status="pending"),
            _outbox(notifs[1], status="sent", sent_at=_AGORA),
            _outbox(notifs[2], status="dead"),
        ]
    )
    await db.commit()

    contagens = await contadores_por_status(db_factory)
    assert contagens["pending"] >= 1
    assert contagens["sent"] >= 1
    assert contagens["dead"] >= 1
    assert set(contagens.keys()) == {"pending", "processing", "sent", "dead"}

    await _limpa(db, user)


# ═══════════════════════════════════════════════════════════════
# Migration: sobe, desce, sobe de novo — contra um Postgres à parte
# ═══════════════════════════════════════════════════════════════


def test_migration_upgrade_downgrade_upgrade():
    """Roda `alembic` de verdade, num Postgres efêmero à parte (não o desta

    suíte — a migration precisa começar da BASE, e o `db_factory` acima já
    subiu o schema via `create_all`, que não deixa `alembic_version` para
    trás). `DATABASE_URL` é sobrescrita explicitamente no ambiente do
    subprocesso: é o que garante que isto nunca encosta no `.env` da árvore
    (que aponta para produção — ver docs/decisoes-e-regras.md)."""
    try:
        import pgserver
    except ImportError:
        pytest.skip("pgserver não instalado")

    pasta = tempfile.mkdtemp(prefix="helphs-testes-pg-migration-")
    servidor = pgserver.get_server(pasta, cleanup_mode=None)
    try:
        servidor.psql("CREATE DATABASE migracao_outbox;")
        url = servidor.get_uri(database="migracao_outbox")

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

        # A cadeia inteira de migrations sobe da BASE, e uma delas
        # (`a7v8w9x0y1z2`, base vetorial da Helô) exige a extensão `vector` já
        # criada — de propósito, para não pôr privilégio de superusuário no
        # caminho do boot do contêiner. Aqui quem cria é o teste, uma vez, como
        # o `_sobe_postgres()` compartilhado já faz para o resto da suíte.
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

        async def _tem_tabela() -> bool:
            # Motor novo, criado e descartado DENTRO deste `asyncio.run()`:
            # reaproveitar um engine entre chamadas separadas de `asyncio.run()`
            # quebra no Windows (ProactorEventLoop) — a conexão asyncpg fica
            # presa ao laço de eventos em que nasceu, e o laço seguinte não é o
            # mesmo.
            motor = create_async_engine(url_async)
            try:
                async with motor.connect() as conn:
                    r = await conn.execute(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                            "WHERE table_name = 'email_outbox')"
                        )
                    )
                    return bool(r.scalar())
            finally:
                await motor.dispose()

        assert asyncio.run(_tem_tabela()) is True

        # Alvo pela REVISION anterior a `ae3cf7068dd6` (a migration desta
        # fase), não por `-1`: `-1` é relativo ao head atual, e a Fase 3C
        # empilhou uma migration em cima (`c8b8d6994fae`) que só ALTERA a
        # tabela — não a cria. Descer só um passo relativo, hoje, reverteria
        # a 3C e deixaria a tabela inteira de pé, o que não prova nada sobre
        # esta migration. Descer até o revision explícito derruba as duas —
        # 3C depende de 3A — e é o que de fato prova que ESTA migration cria
        # a tabela (e a remove, de volta).
        _roda("downgrade", "f7a8b9c0d1e2")
        assert asyncio.run(_tem_tabela()) is False

        _roda("upgrade", "head")
        assert asyncio.run(_tem_tabela()) is True
    finally:
        try:
            servidor.cleanup()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(pasta, ignore_errors=True)
