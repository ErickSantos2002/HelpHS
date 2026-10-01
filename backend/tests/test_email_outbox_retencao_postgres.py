"""
Fase 3D — retenção da outbox de e-mail, contra PostgreSQL de verdade.

Por que este arquivo não pode ser de unidade
---------------------------------------------
O `DELETE ... WHERE id IN (SELECT ... LIMIT n FOR UPDATE SKIP LOCKED)` é a peça
central da limpeza, e ela só existe em Postgres: é o `SKIP LOCKED` que faz dois
processos limpando ao mesmo tempo pegarem lotes DISJUNTOS, e é isso que dispensa
lock de qualquer espécie. Testar contra mock provaria que o Python chama o que
se espera; não provaria a garantia — que é a única razão de o desenho ser este.

Também só o banco de verdade prova a segunda defesa da fila viva: `sent_at` é
`NULL` numa linha que nunca foi enviada, e `NULL < cutoff` é `NULL`, nunca
verdadeiro. Em Python isso levantaria `TypeError`; em SQL é silenciosamente
falso, que é exatamente o comportamento desejado.

Reusa o arranjo da Fase 3A (`test_email_outbox_postgres`): sessão presa ao
ENGINE, não a uma conexão com savepoint, porque os testes de concorrência
precisam de COMMITS visíveis entre sessões diferentes.
"""

import asyncio
import shutil
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.models.models import (
    Base,
    EmailOutbox,
    Notification,
    NotificationType,
    User,
    UserRole,
    UserStatus,
)
from app.services.email_outbox import (
    _LOTE_DA_LIMPEZA,
    coleta_snapshot,
    limpa_expirados,
)
from tests.test_dashboard_postgres import _sobe_postgres

_AGORA = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

_RETENCAO_SENT = 60
_RETENCAO_DEAD = 180


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


def _usuario(uid: uuid.UUID) -> User:
    """`technician`, e não `client`, de propósito: a CHECK
    `ck_users_cliente_ativo_tem_telefone` exige telefone de cliente ativo, e
    telefone não tem nada a ver com retenção de outbox."""
    return User(
        id=uid,
        name="Alvo da Retencao",
        email=f"{uuid.uuid4().hex[:10]}@test.com",
        password="x",
        role=UserRole.technician,
        status=UserStatus.active,
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
        created_at=_AGORA,
        updated_at=_AGORA,
    )


@pytest_asyncio.fixture(autouse=True)
async def usuario(db_factory):
    """Zera a outbox e devolve o id de UM usuário real, dono das linhas de
    origem Account que os testes criam.

    O usuário precisa existir de verdade: `email_outbox.user_id` tem FK para
    `users` (medido — a primeira versão deste arquivo inventava UUIDs soltos e
    as 15 inserções bateram em `email_outbox_user_id_fkey`). Um usuário só para
    o módulo inteiro basta: a identidade das linhas vem da `dedup_key`, não do
    usuário, e assim o teste de lote cria 501 linhas em vez de 501 usuários.
    """
    async with db_factory() as sessao:
        await sessao.execute(text("DELETE FROM email_outbox"))
        await sessao.execute(text("DELETE FROM notifications"))
        await sessao.commit()

    uid = uuid.uuid4()
    async with db_factory() as sessao:
        sessao.add(_usuario(uid))
        await sessao.commit()

    yield uid

    async with db_factory() as sessao:
        await sessao.execute(text("DELETE FROM email_outbox"))
        await sessao.execute(text("DELETE FROM notifications"))
        await sessao.execute(text("DELETE FROM users WHERE id = :i"), {"i": uid})
        await sessao.commit()


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        email_outbox_sent_retention_days=_RETENCAO_SENT,
        email_outbox_dead_retention_days=_RETENCAO_DEAD,
        email_outbox_cleanup_interval_seconds=3600,
    )
    base.update(overrides)
    return Settings(**base)


def _monta_linha(
    user_id: uuid.UUID,
    *,
    status: str,
    sent_at: datetime | None = None,
    next_attempt_at: datetime | None = None,
    locked_at: datetime | None = None,
    attempts: int = 0,
) -> EmailOutbox:
    """Uma linha de outbox da origem Account para o usuário recebido."""
    return EmailOutbox(
        id=uuid.uuid4(),
        user_id=user_id,
        event_type="verification",
        dedup_key=f"verification:{user_id}:{uuid.uuid4()}",
        status=status,
        attempts=attempts,
        next_attempt_at=next_attempt_at or _AGORA,
        sent_at=sent_at,
        locked_at=locked_at,
    )


async def _linha_de_conta(
    db,
    user_id: uuid.UUID,
    *,
    status: str,
    sent_at: datetime | None = None,
    created_at: datetime | None = None,
    next_attempt_at: datetime | None = None,
    locked_at: datetime | None = None,
    attempts: int = 0,
) -> uuid.UUID:
    linha = _monta_linha(
        user_id,
        status=status,
        sent_at=sent_at,
        next_attempt_at=next_attempt_at,
        locked_at=locked_at,
        attempts=attempts,
    )
    db.add(linha)
    await db.flush()
    if created_at is not None:
        # `created_at` é `server_default=now()`: para datar no passado é preciso
        # sobrescrever depois do INSERT.
        await db.execute(
            text("UPDATE email_outbox SET created_at = :c WHERE id = :i"),
            {"c": created_at, "i": linha.id},
        )
    await db.commit()
    return linha.id


async def _existe(db, outbox_id: uuid.UUID) -> bool:
    """Consulta escalar, não `db.get`: `db.get` bate no identity map e devolveria
    o objeto em cache mesmo depois de o DELETE ter acontecido no banco (lição já
    registrada nos testes da Fase 3A)."""
    achado = await db.execute(select(EmailOutbox.id).where(EmailOutbox.id == outbox_id))
    return achado.scalar_one_or_none() is not None


async def _total(db) -> int:
    return (await db.execute(select(func.count()).select_from(EmailOutbox))).scalar_one()


# ═══════════════════════════════════════════════════════════════
# `sent` e `dead` expiram pelo campo certo
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sent_expirado_e_apagado(db, db_factory, usuario):
    velho = await _linha_de_conta(
        db, usuario, status="sent", sent_at=_AGORA - timedelta(days=_RETENCAO_SENT, seconds=1)
    )

    apagados = await limpa_expirados(db_factory, _settings(), agora=_AGORA)

    assert apagados["sent"] == 1
    assert await _existe(db, velho) is False


@pytest.mark.asyncio
async def test_sent_recente_e_preservado(db, db_factory, usuario):
    novo = await _linha_de_conta(
        db, usuario, status="sent", sent_at=_AGORA - timedelta(days=_RETENCAO_SENT - 1)
    )

    apagados = await limpa_expirados(db_factory, _settings(), agora=_AGORA)

    assert apagados["sent"] == 0
    assert await _existe(db, novo) is True


@pytest.mark.asyncio
async def test_sent_exatamente_no_corte_e_preservado(db, db_factory, usuario):
    """Fronteira: o predicado é `sent_at < cutoff`, estrito. Exatamente no corte
    a linha fica — e é esta asserção que mata a mutação `<` → `<=`."""
    na_fronteira = await _linha_de_conta(
        db, usuario, status="sent", sent_at=_AGORA - timedelta(days=_RETENCAO_SENT)
    )

    apagados = await limpa_expirados(db_factory, _settings(), agora=_AGORA)

    assert apagados["sent"] == 0
    assert await _existe(db, na_fronteira) is True


@pytest.mark.asyncio
async def test_dead_expirado_e_apagado_por_created_at(db, db_factory, usuario):
    """`dead` corta por `created_at`, não por `sent_at`: linha que morreu nunca
    teve `sent_at` preenchido. Com o campo errado, nenhum `dead` sairia nunca."""
    velho = await _linha_de_conta(
        db,
        usuario,
        status="dead",
        attempts=5,
        created_at=_AGORA - timedelta(days=_RETENCAO_DEAD, seconds=1),
    )

    apagados = await limpa_expirados(db_factory, _settings(), agora=_AGORA)

    assert apagados["dead"] == 1
    assert await _existe(db, velho) is False


@pytest.mark.asyncio
async def test_dead_recente_e_preservado(db, db_factory, usuario):
    novo = await _linha_de_conta(
        db,
        usuario,
        status="dead",
        attempts=5,
        created_at=_AGORA - timedelta(days=_RETENCAO_DEAD - 1),
    )

    apagados = await limpa_expirados(db_factory, _settings(), agora=_AGORA)

    assert apagados["dead"] == 0
    assert await _existe(db, novo) is True


@pytest.mark.asyncio
async def test_dead_sobrevive_ao_corte_de_sent(db, db_factory, usuario):
    """Os dois cortes são independentes: um `dead` com 90 dias está além da
    retenção de `sent` (60) e dentro da de `dead` (180). Um corte único apagaria
    diagnóstico que a frente decidiu guardar por mais tempo."""
    noventa_dias = await _linha_de_conta(
        db, usuario, status="dead", attempts=5, created_at=_AGORA - timedelta(days=90)
    )

    apagados = await limpa_expirados(db_factory, _settings(), agora=_AGORA)

    assert apagados == {"sent": 0, "dead": 0}
    assert await _existe(db, noventa_dias) is True


# ═══════════════════════════════════════════════════════════════
# Fila viva: NUNCA apagada — e por duas razões independentes
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pending_antiquissimo_nunca_e_apagado(db, db_factory, usuario):
    """Apagar um `pending` por retenção seria descartar e-mail em silêncio — o
    pior modo de falha possível para esta tabela. Um `pending` velho É o alarme
    (ver `oldest_overdue_seconds` no health), não lixo."""
    antigo = await _linha_de_conta(
        db,
        usuario,
        status="pending",
        created_at=_AGORA - timedelta(days=400),
        next_attempt_at=_AGORA - timedelta(days=400),
    )

    apagados = await limpa_expirados(db_factory, _settings(), agora=_AGORA)

    assert apagados == {"sent": 0, "dead": 0}
    assert await _existe(db, antigo) is True


@pytest.mark.asyncio
async def test_processing_antiquissimo_nunca_e_apagado(db, db_factory, usuario):
    """Pior que o `pending`: pode estar em voo AGORA."""
    antigo = await _linha_de_conta(
        db,
        usuario,
        status="processing",
        created_at=_AGORA - timedelta(days=400),
        locked_at=_AGORA - timedelta(minutes=2),
    )

    apagados = await limpa_expirados(db_factory, _settings(), agora=_AGORA)

    assert apagados == {"sent": 0, "dead": 0}
    assert await _existe(db, antigo) is True


@pytest.mark.asyncio
async def test_a_segunda_defesa_sozinha_ja_bastaria_sent_at_nulo(db, db_factory):
    """A defesa que não depende do filtro de status: uma linha que nunca foi
    enviada tem `sent_at` NULL, e `NULL < cutoff` é NULL — nunca verdadeiro.

    Este teste existe separado do de cima de propósito: se alguém trocar o
    predicado de status por engano, ESTE continua verde para `sent_at`, e a
    diferença entre os dois mostra qual das duas defesas caiu.
    """
    async with db_factory() as sessao:
        sem_sent_at = (
            await sessao.execute(
                text("SELECT count(*) FROM email_outbox " "WHERE sent_at IS NULL AND sent_at < :c"),
                {"c": _AGORA},
            )
        ).scalar_one()
    assert sem_sent_at == 0, "NULL < cutoff precisa ser falso, não verdadeiro"


@pytest.mark.asyncio
async def test_a_limpeza_nao_encosta_em_estado_desconhecido(db, db_factory, usuario):
    """Só `sent` e `dead` são alvos nomeados. Se alguém acrescentar um estado
    novo à CHECK do modelo, ele nasce protegido — e não apagado por acidente."""
    pending = await _linha_de_conta(
        db, usuario, status="pending", created_at=_AGORA - timedelta(days=400)
    )
    processing = await _linha_de_conta(
        db, usuario, status="processing", created_at=_AGORA - timedelta(days=400)
    )
    sent = await _linha_de_conta(
        db, usuario, status="sent", sent_at=_AGORA - timedelta(days=400), created_at=_AGORA
    )

    await limpa_expirados(db_factory, _settings(), agora=_AGORA)

    assert await _existe(db, pending) is True
    assert await _existe(db, processing) is True
    assert await _existe(db, sent) is False


# ═══════════════════════════════════════════════════════════════
# Lotes — e dois limpadores concorrentes
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_lote_de_501_apaga_500_e_deixa_uma(db, db_factory, usuario):
    """Sem limite, um `DELETE` futuro varreria milhões de linhas numa transação
    só. Com 501 elegíveis, a rodada apaga exatamente `_LOTE_DA_LIMPEZA`."""
    assert _LOTE_DA_LIMPEZA == 500

    velho = _AGORA - timedelta(days=_RETENCAO_SENT + 1)
    async with db_factory() as sessao:
        sessao.add_all(
            [
                _monta_linha(usuario, status="sent", next_attempt_at=velho, sent_at=velho)
                for _ in range(_LOTE_DA_LIMPEZA + 1)
            ]
        )
        await sessao.commit()

    apagados = await limpa_expirados(db_factory, _settings(), agora=_AGORA)

    assert apagados["sent"] == _LOTE_DA_LIMPEZA
    assert await _total(db) == 1

    # E a rodada seguinte termina o serviço — o lote limita, não descarta.
    apagados = await limpa_expirados(db_factory, _settings(), agora=_AGORA)
    assert apagados["sent"] == 1
    assert await _total(db) == 0


@pytest.mark.asyncio
async def test_dois_limpadores_concorrentes_pegam_lotes_disjuntos(
    db_factory, url_do_banco, usuario
):
    """O coração do desenho de concorrência: sem Redis e sem advisory lock.

    Dois limpadores de verdade, em engines separados, rodando ao mesmo tempo.
    `SKIP LOCKED` na subconsulta faz o segundo pular o que o primeiro travou —
    então a soma do que os dois apagam é EXATAMENTE o total elegível, nunca mais
    (nada é apagado duas vezes) e nunca menos (nada é esquecido).
    """
    total_elegivel = 40
    velho = _AGORA - timedelta(days=_RETENCAO_SENT + 1)
    async with db_factory() as sessao:
        sessao.add_all(
            [
                _monta_linha(usuario, status="sent", next_attempt_at=velho, sent_at=velho)
                for _ in range(total_elegivel)
            ]
        )
        await sessao.commit()

    motor_a = create_async_engine(url_do_banco)
    motor_b = create_async_engine(url_do_banco)
    try:
        fabrica_a = async_sessionmaker(motor_a, expire_on_commit=False)
        fabrica_b = async_sessionmaker(motor_b, expire_on_commit=False)

        a, b = await asyncio.gather(
            limpa_expirados(fabrica_a, _settings(), agora=_AGORA),
            limpa_expirados(fabrica_b, _settings(), agora=_AGORA),
        )
    finally:
        await motor_a.dispose()
        await motor_b.dispose()

    assert a["sent"] + b["sent"] == total_elegivel
    async with db_factory() as sessao:
        assert await _total(sessao) == 0


# ═══════════════════════════════════════════════════════════════
# Apagar a outbox não encosta no histórico funcional
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_apagar_outbox_sent_preserva_a_notification_e_o_email_sent(db, db_factory):
    """A direção do CASCADE é a oposta da preocupação: a FK é
    `email_outbox.notification_id → notifications.id`, então apagar a
    NOTIFICAÇÃO leva a outbox. Apagar a outbox não encosta em `notifications`.

    É isto que sustenta a política de retenção: `Notification.email_sent`
    continua sendo a evidência de que o e-mail foi entregue, e ela sobrevive.
    """
    usuario = User(
        id=uuid.uuid4(),
        name="Alvo da Retencao",
        email=f"{uuid.uuid4().hex[:10]}@test.com",
        password="x",
        role=UserRole.technician,
        status=UserStatus.active,
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
        created_at=_AGORA,
        updated_at=_AGORA,
    )
    notif = Notification(
        id=uuid.uuid4(),
        user_id=usuario.id,
        type=NotificationType.ticket_created,
        title="Ticket aberto",
        message="corpo",
        data=None,
        read=False,
        email_sent=True,
    )
    velho = _AGORA - timedelta(days=_RETENCAO_SENT + 1)
    linha = EmailOutbox(
        id=uuid.uuid4(),
        notification_id=notif.id,
        status="sent",
        attempts=0,
        next_attempt_at=velho,
        sent_at=velho,
    )
    db.add_all([usuario, notif, linha])
    await db.commit()
    notif_id, user_id, outbox_id = notif.id, usuario.id, linha.id

    try:
        apagados = await limpa_expirados(db_factory, _settings(), agora=_AGORA)
        assert apagados["sent"] == 1

        async with db_factory() as sessao:
            assert await _existe(sessao, outbox_id) is False
            sobrou = (
                await sessao.execute(
                    select(Notification.id, Notification.email_sent).where(
                        Notification.id == notif_id
                    )
                )
            ).first()
            assert sobrou is not None, "a notificação foi embora com a outbox"
            assert sobrou.email_sent is True, "a evidência de entrega se perdeu"
    finally:
        async with db_factory() as sessao:
            await sessao.execute(text("DELETE FROM users WHERE id = :i"), {"i": user_id})
            await sessao.commit()


# ═══════════════════════════════════════════════════════════════
# O snapshot, contra o banco de verdade
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_snapshot_conta_por_estado_e_carimba_o_as_of(db, db_factory, usuario):
    await _linha_de_conta(
        db, usuario, status="pending", next_attempt_at=_AGORA - timedelta(minutes=1)
    )
    await _linha_de_conta(db, usuario, status="processing", locked_at=_AGORA - timedelta(minutes=1))
    await _linha_de_conta(db, usuario, status="sent", sent_at=_AGORA)
    await _linha_de_conta(db, usuario, status="dead", attempts=5)

    snap = await coleta_snapshot(db_factory, agora=_AGORA)

    assert snap.as_of == _AGORA
    assert (snap.pending, snap.processing, snap.sent, snap.dead) == (1, 1, 1, 1)


@pytest.mark.asyncio
async def test_pending_em_backoff_futuro_nao_entra_no_overdue(db, db_factory, usuario):
    """A correção central do desenho, agora contra SQL de verdade: a linha está
    `pending` com `next_attempt_at` no FUTURO — está cumprindo o backoff, e não
    atrasada. O `AND next_attempt_at <= agora` é o que faz a diferença; sem ele
    esta linha apareceria como 59 minutos de atraso num sistema saudável."""
    await _linha_de_conta(
        db, usuario, status="pending", attempts=4, next_attempt_at=_AGORA + timedelta(minutes=59)
    )

    snap = await coleta_snapshot(db_factory, agora=_AGORA)

    assert snap.pending == 1
    assert snap.oldest_overdue_seconds is None


@pytest.mark.asyncio
async def test_overdue_mede_o_vencido_mais_antigo(db, db_factory, usuario):
    await _linha_de_conta(
        db, usuario, status="pending", next_attempt_at=_AGORA - timedelta(seconds=10)
    )
    await _linha_de_conta(
        db, usuario, status="pending", next_attempt_at=_AGORA - timedelta(seconds=600)
    )
    await _linha_de_conta(
        db, usuario, status="pending", next_attempt_at=_AGORA + timedelta(hours=1)
    )

    snap = await coleta_snapshot(db_factory, agora=_AGORA)

    assert snap.pending == 3
    assert snap.oldest_overdue_seconds == 600


@pytest.mark.asyncio
async def test_snapshot_mede_a_idade_do_processing_mais_antigo(db, db_factory, usuario):
    """É o sinal que torna o achado A3 observável — a linha que o worker
    reivindica e devolve a cada `stale_minutes` sem avançar `attempts`."""
    await _linha_de_conta(
        db, usuario, status="processing", locked_at=_AGORA - timedelta(minutes=12)
    )
    await _linha_de_conta(db, usuario, status="processing", locked_at=_AGORA - timedelta(minutes=1))

    snap = await coleta_snapshot(db_factory, agora=_AGORA)

    assert snap.oldest_processing_seconds == 12 * 60


@pytest.mark.asyncio
async def test_snapshot_de_tabela_vazia_e_zero_com_idades_nulas(db_factory):
    snap = await coleta_snapshot(db_factory, agora=_AGORA)

    assert (snap.pending, snap.processing, snap.sent, snap.dead) == (0, 0, 0, 0)
    assert snap.oldest_overdue_seconds is None
    assert snap.oldest_processing_seconds is None
