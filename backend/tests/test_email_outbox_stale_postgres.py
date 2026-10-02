"""
Frente A3 — stale consome tentativa, e só o dono da claim escreve.

Dois defeitos, o mesmo caminho de código
-----------------------------------------
1. `recupera_travados` devolvia a linha para `pending` sem registrar desfecho:
   era a única transição que não avançava a máquina, e uma mensagem que travasse
   a cada reivindicação circularia para sempre sem alcançar `MAX_ATTEMPTS`.

2. `_persiste_resultado` não tinha guarda nenhuma. Um worker lento que
   concluísse DEPOIS de a linha ter sido recuperada e reivindicada por outro
   limpava o lock do novo dono e sobrescrevia o estado — terminando em
   `status='pending'` com `sent_at` preenchido.

Por que PostgreSQL de verdade, e não mock
------------------------------------------
O segundo defeito é uma corrida, e o conserto é um compare-and-set no banco
(`UPDATE ... WHERE status='processing' AND locked_by=:worker_id`, conferindo
`rowcount`). Mock provaria que o Python chama o que se espera; só o banco prova
que a escrita do worker que perdeu a claim **não acontece**. E a idempotência do
incremento sob dois recoverers concorrentes é comportamento de MVCC — não existe
fora do Postgres.
"""

import asyncio
import shutil
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from loguru import logger
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import (
    Base,
    EmailOutbox,
    Notification,
    NotificationType,
    User,
    UserRole,
    UserStatus,
)
from app.services.email import EmailDeliveryResult, EmailDeliveryStatus
from app.services.email_outbox import (
    MAX_ATTEMPTS,
    PROCESSING_STALE,
    PROCESSING_STALE_EXCEDIDO,
    _persiste_resultado,
    recupera_travados,
)
from tests.test_dashboard_postgres import _sobe_postgres

_AGORA = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
_STALE_MIN = 5
_VELHO = _AGORA - timedelta(minutes=10)

#: A escada de `_BACKOFF_MINUTOS_APOS_TENTATIVA`, escrita aqui em número
#: fechado de propósito: se alguém mexer na escada do módulo, estes testes caem.
_BACKOFF = {1: 1, 2: 5, 3: 15, 4: 60}


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


@pytest_asyncio.fixture(autouse=True)
async def usuario(db_factory):
    """Zera a outbox e devolve um usuário real — `email_outbox.user_id` tem FK."""
    async with db_factory() as s:
        await s.execute(text("DELETE FROM email_outbox"))
        await s.execute(text("DELETE FROM notifications"))
        await s.commit()

    uid = uuid.uuid4()
    async with db_factory() as s:
        s.add(
            User(
                id=uid,
                name="Alvo do A3",
                email=f"{uuid.uuid4().hex[:10]}@test.com",
                password="hash",
                role=UserRole.technician,
                status=UserStatus.active,
                lgpd_consent=True,
                email_verified=True,
                onboarding_completed=True,
                created_at=_AGORA,
                updated_at=_AGORA,
            )
        )
        await s.commit()

    yield uid

    async with db_factory() as s:
        await s.execute(text("DELETE FROM email_outbox"))
        await s.execute(text("DELETE FROM notifications"))
        await s.execute(text("DELETE FROM users WHERE id = :i"), {"i": uid})
        await s.commit()


async def _linha(
    db_factory,
    user_id,
    *,
    status: str = "processing",
    attempts: int = 0,
    locked_by: str | None = "worker-A",
    locked_at: datetime | None = None,
    sent_at: datetime | None = None,
) -> uuid.UUID:
    lid = uuid.uuid4()
    async with db_factory() as s:
        s.add(
            EmailOutbox(
                id=lid,
                user_id=user_id,
                event_type="verification",
                dedup_key=f"verification:{user_id}:{uuid.uuid4()}",
                status=status,
                attempts=attempts,
                next_attempt_at=_AGORA - timedelta(hours=1),
                locked_by=locked_by,
                locked_at=locked_at if locked_at is not None else _VELHO,
                sent_at=sent_at,
            )
        )
        await s.commit()
    return lid


async def _estado(db_factory, lid):
    async with db_factory() as s:
        return (
            await s.execute(
                select(
                    EmailOutbox.status,
                    EmailOutbox.attempts,
                    EmailOutbox.locked_by,
                    EmailOutbox.locked_at,
                    EmailOutbox.next_attempt_at,
                    EmailOutbox.last_error,
                    EmailOutbox.sent_at,
                ).where(EmailOutbox.id == lid)
            )
        ).first()


def _captura() -> tuple[list[tuple[str, str]], int]:
    linhas: list[tuple[str, str]] = []
    sink = logger.add(
        lambda m: linhas.append((m.record["level"].name, m.record["message"])), level="DEBUG"
    )
    return linhas, sink


# ═══════════════════════════════════════════════════════════════
# Stale registra desfecho: attempts, backoff, last_error, locks
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("antes", [0, 1, 2, 3])
async def test_stale_incrementa_attempts_e_paga_o_backoff(db_factory, usuario, antes):
    """O coração da A3. Antes desta frente `attempts` ficava parado aqui — e era
    exatamente isso que deixava a linha circular para sempre."""
    lid = await _linha(db_factory, usuario, attempts=antes)

    resultado = await recupera_travados(db_factory, stale_minutes=_STALE_MIN, agora=_AGORA)

    assert resultado.recuperadas == 1
    assert resultado.reenfileiradas == 1
    assert resultado.mortas == 0

    st = await _estado(db_factory, lid)
    assert st.status == "pending"
    assert st.attempts == antes + 1
    assert st.next_attempt_at == _AGORA + timedelta(minutes=_BACKOFF[antes + 1])
    assert st.last_error == PROCESSING_STALE
    assert st.locked_by is None
    assert st.locked_at is None


@pytest.mark.asyncio
async def test_a_quinta_passagem_abandonada_encerra_em_dead(db_factory, usuario):
    """Mesmo `MAX_ATTEMPTS` da falha SMTP, sem limite separado para stale."""
    lid = await _linha(db_factory, usuario, attempts=MAX_ATTEMPTS - 1)

    resultado = await recupera_travados(db_factory, stale_minutes=_STALE_MIN, agora=_AGORA)

    assert (resultado.recuperadas, resultado.reenfileiradas, resultado.mortas) == (1, 0, 1)

    st = await _estado(db_factory, lid)
    assert st.status == "dead"
    assert st.attempts == MAX_ATTEMPTS
    assert st.last_error == PROCESSING_STALE_EXCEDIDO
    assert st.locked_by is None
    assert st.locked_at is None


@pytest.mark.asyncio
async def test_o_dead_por_stale_usa_o_log_seguro_da_fase_3d(db_factory, usuario):
    await _linha(db_factory, usuario, attempts=MAX_ATTEMPTS - 1)

    capturado, sink = _captura()
    try:
        await recupera_travados(db_factory, stale_minutes=_STALE_MIN, agora=_AGORA)
    finally:
        logger.remove(sink)

    dead = [(n, m) for n, m in capturado if "dead" in m and "dead_kind" in m]
    assert len(dead) == 1
    nivel, mensagem = dead[0]
    # `delivery`, cadastrado EXPLICITAMENTE e não herdado do default.
    assert nivel == "ERROR"
    assert "dead_kind=delivery" in mensagem
    assert f"reason={PROCESSING_STALE_EXCEDIDO}" in mensagem
    assert f"attempts={MAX_ATTEMPTS}" in mensagem


@pytest.mark.asyncio
async def test_linha_viva_nao_gasta_tentativa(db_factory, usuario):
    """Fronteira do stale: `locked_at < limite` é estrito, e o worker que travou
    a linha há menos que isso ainda está dentro do prazo normal."""
    lid = await _linha(db_factory, usuario, locked_at=_AGORA - timedelta(minutes=1))

    resultado = await recupera_travados(db_factory, stale_minutes=_STALE_MIN, agora=_AGORA)

    assert resultado.recuperadas == 0
    st = await _estado(db_factory, lid)
    assert st.status == "processing"
    assert st.attempts == 0
    assert st.locked_by == "worker-A"


@pytest.mark.asyncio
async def test_fronteira_exata_do_stale_nao_recupera(db_factory, usuario):
    """Mata a mutação `<` → `<=`: exatamente NO limite a linha fica."""
    lid = await _linha(db_factory, usuario, locked_at=_AGORA - timedelta(minutes=_STALE_MIN))

    resultado = await recupera_travados(db_factory, stale_minutes=_STALE_MIN, agora=_AGORA)

    assert resultado.recuperadas == 0
    assert (await _estado(db_factory, lid)).attempts == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["sent", "dead"])
async def test_estado_terminal_nunca_e_recuperado(db_factory, usuario, terminal):
    """O predicado exige `status='processing'`. Recuperar um `sent` seria
    reenviar o que já foi entregue; recuperar um `dead`, desfazer a desistência."""
    lid = await _linha(
        db_factory,
        usuario,
        status=terminal,
        attempts=2,
        locked_by=None,
        sent_at=_AGORA if terminal == "sent" else None,
    )

    resultado = await recupera_travados(db_factory, stale_minutes=_STALE_MIN, agora=_AGORA)

    assert resultado.recuperadas == 0
    st = await _estado(db_factory, lid)
    assert st.status == terminal
    assert st.attempts == 2


@pytest.mark.asyncio
async def test_recuperacao_loga_resumo_uma_vez_por_rodada(db_factory, usuario):
    """Resumo da RODADA, não uma linha por registro: stale é raro, e no caso
    patológico que esta frente conserta o log precisa seguir legível."""
    for _ in range(3):
        await _linha(db_factory, usuario)

    capturado, sink = _captura()
    try:
        resultado = await recupera_travados(db_factory, stale_minutes=_STALE_MIN, agora=_AGORA)
    finally:
        logger.remove(sink)

    assert resultado.recuperadas == 3
    resumos = [m for n, m in capturado if "processing stale" in m]
    assert len(resumos) == 1
    assert "recovered=3" in resumos[0]
    assert "requeued=3" in resumos[0]
    assert "dead=0" in resumos[0]


@pytest.mark.asyncio
async def test_rodada_sem_nada_a_recuperar_nao_loga(db_factory, usuario):
    await _linha(db_factory, usuario, locked_at=_AGORA - timedelta(minutes=1))

    capturado, sink = _captura()
    try:
        await recupera_travados(db_factory, stale_minutes=_STALE_MIN, agora=_AGORA)
    finally:
        logger.remove(sink)

    assert [m for n, m in capturado if "processing stale" in m] == []


# ═══════════════════════════════════════════════════════════════
# Concorrência: dois recoverers, um incremento
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_dois_recoverers_concorrentes_incrementam_uma_vez_so(
    db_factory, url_do_banco, usuario
):
    """`attempts` contaria 2 se a transição não fosse atômica — e uma linha
    pularia um degrau da escada a cada rodada em que dois workers coincidissem."""
    lid = await _linha(db_factory, usuario, attempts=0)

    motor_a = create_async_engine(url_do_banco)
    motor_b = create_async_engine(url_do_banco)
    try:
        a, b = await asyncio.gather(
            recupera_travados(
                async_sessionmaker(motor_a, expire_on_commit=False),
                stale_minutes=_STALE_MIN,
                agora=_AGORA,
            ),
            recupera_travados(
                async_sessionmaker(motor_b, expire_on_commit=False),
                stale_minutes=_STALE_MIN,
                agora=_AGORA,
            ),
        )
    finally:
        await motor_a.dispose()
        await motor_b.dispose()

    assert a.recuperadas + b.recuperadas == 1, "a mesma linha foi recuperada duas vezes"
    st = await _estado(db_factory, lid)
    assert st.attempts == 1
    assert st.status == "pending"


@pytest.mark.asyncio
async def test_dois_recoverers_pegam_lotes_disjuntos(db_factory, url_do_banco, usuario):
    """`SKIP LOCKED`: a soma é exatamente o total elegível — nada duas vezes,
    nada esquecido."""
    total = 20
    for _ in range(total):
        await _linha(db_factory, usuario)

    motor_a = create_async_engine(url_do_banco)
    motor_b = create_async_engine(url_do_banco)
    try:
        a, b = await asyncio.gather(
            recupera_travados(
                async_sessionmaker(motor_a, expire_on_commit=False),
                stale_minutes=_STALE_MIN,
                agora=_AGORA,
            ),
            recupera_travados(
                async_sessionmaker(motor_b, expire_on_commit=False),
                stale_minutes=_STALE_MIN,
                agora=_AGORA,
            ),
        )
    finally:
        await motor_a.dispose()
        await motor_b.dispose()

    assert a.recuperadas + b.recuperadas == total

    async with db_factory() as s:
        sobraram = (
            await s.execute(
                select(func.count())
                .select_from(EmailOutbox)
                .where(EmailOutbox.status == "processing")
            )
        ).scalar_one()
    assert sobraram == 0


@pytest.mark.asyncio
async def test_a_recuperacao_nao_espera_por_linha_travada(db_factory, url_do_banco, usuario):
    """`SKIP LOCKED`, e a lição que o `cleanup` da Fase 3D já tinha ensinado.

    O teste de lotes disjuntos passa igual SEM `SKIP LOCKED`: o segundo recoverer
    BLOQUEIA no `FOR UPDATE`, acorda depois do commit do primeiro, não encontra
    mais nada e recupera zero. A soma continua exata — aquele teste prova
    disjunção, que também existe com bloqueio.

    O que `SKIP LOCKED` garante além disso é NÃO ESPERAR. Para medir isso é
    preciso um lock que não se solta: uma terceira sessão segura uma das linhas
    com a transação ABERTA, e a recuperação tem de voltar depressa tendo pulado
    exatamente aquela. O `wait_for` é o detector — sem `SKIP LOCKED` a chamada
    fica presa até um `rollback` que só vem depois dela.
    """
    presa = await _linha(db_factory, usuario)
    livre = await _linha(db_factory, usuario)

    motor_travador = create_async_engine(url_do_banco)
    try:
        fabrica = async_sessionmaker(motor_travador, expire_on_commit=False)
        async with fabrica() as travador:
            travadas = (
                (
                    await travador.execute(
                        select(EmailOutbox.id).where(EmailOutbox.id == presa).with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            assert travadas == [presa]

            resultado = await asyncio.wait_for(
                recupera_travados(db_factory, stale_minutes=_STALE_MIN, agora=_AGORA),
                timeout=15,
            )
            await travador.rollback()
    finally:
        await motor_travador.dispose()

    assert resultado.recuperadas == 1, "a recuperação não pulou a linha travada"
    assert (await _estado(db_factory, presa)).status == "processing"
    assert (await _estado(db_factory, livre)).status == "pending"


# ═══════════════════════════════════════════════════════════════
# Ownership fencing — a corrida reproduzida, e fechada
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_worker_que_perdeu_a_claim_nao_escreve_nada(db_factory, usuario):
    """A corrida exata que a auditoria reproduziu, agora fechada.

        t0  processing, locked_by=A
        t1  recovery   -> pending, attempts=1
        t2  B reivindica -> processing, locked_by=B
        t3  A conclui com SUCESSO -> precisa ser DESCARTADO

    Antes da A3, t3 marcava `sent` e limpava o lock de B. O estado de B tem de
    sobreviver intacto.
    """
    lid = await _linha(db_factory, usuario, attempts=0, locked_by="worker-A")

    await recupera_travados(db_factory, stale_minutes=_STALE_MIN, agora=_AGORA)
    async with db_factory() as s:
        await s.execute(
            update(EmailOutbox)
            .where(EmailOutbox.id == lid)
            .values(status="processing", locked_by="worker-B", locked_at=_AGORA)
        )
        await s.commit()

    antes = await _estado(db_factory, lid)

    capturado, sink = _captura()
    try:
        # O worker A, lento, finalmente conclui — e já não é o dono.
        await _persiste_resultado(
            db_factory,
            lid,
            EmailDeliveryResult(EmailDeliveryStatus.success),
            worker_id="worker-A",
            agora=_AGORA,
        )
    finally:
        logger.remove(sink)

    depois = await _estado(db_factory, lid)
    assert depois == antes, "o worker que perdeu a claim alterou a linha"
    assert depois.status == "processing"
    assert depois.locked_by == "worker-B"
    assert depois.sent_at is None

    perdidas = [m for n, m in capturado if "claim was lost" in m]
    assert len(perdidas) == 1


@pytest.mark.asyncio
async def test_o_dono_legitimo_persiste_normalmente(db_factory, usuario):
    """O outro lado: o fencing não pode atrapalhar quem é dono de verdade."""
    lid = await _linha(db_factory, usuario, locked_by="worker-B", locked_at=_AGORA)

    await _persiste_resultado(
        db_factory,
        lid,
        EmailDeliveryResult(EmailDeliveryStatus.success),
        worker_id="worker-B",
        agora=_AGORA,
    )

    st = await _estado(db_factory, lid)
    assert st.status == "sent"
    assert st.sent_at == _AGORA
    assert st.locked_by is None


@pytest.mark.asyncio
async def test_falha_do_dono_legitimo_volta_a_pending_sem_sent_at(db_factory, usuario):
    lid = await _linha(db_factory, usuario, attempts=0, locked_by="w", locked_at=_AGORA)

    await _persiste_resultado(
        db_factory,
        lid,
        EmailDeliveryResult(EmailDeliveryStatus.temporary_failure, "SMTPServerDisconnected"),
        worker_id="w",
        agora=_AGORA,
    )

    st = await _estado(db_factory, lid)
    assert st.status == "pending"
    assert st.attempts == 1
    assert st.sent_at is None
    assert st.next_attempt_at == _AGORA + timedelta(minutes=1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal, desfecho",
    [
        ("sent", EmailDeliveryStatus.temporary_failure),
        ("dead", EmailDeliveryStatus.success),
    ],
)
async def test_worker_atrasado_nao_reverte_estado_terminal(db_factory, usuario, terminal, desfecho):
    """`sent` e `dead` são terminais POR CONSTRUÇÃO: o predicado do fencing
    exige `status='processing'`, que nenhum dos dois satisfaz. Sem isso, uma
    linha já entregue voltava para a fila."""
    lid = await _linha(
        db_factory,
        usuario,
        status=terminal,
        attempts=3,
        locked_by=None,
        sent_at=_AGORA if terminal == "sent" else None,
    )
    antes = await _estado(db_factory, lid)

    await _persiste_resultado(
        db_factory,
        lid,
        EmailDeliveryResult(desfecho, None if desfecho == EmailDeliveryStatus.success else "X"),
        worker_id="worker-atrasado",
        agora=_AGORA + timedelta(minutes=1),
    )

    assert await _estado(db_factory, lid) == antes


@pytest.mark.asyncio
async def test_a_invariante_pending_com_sent_at_nunca_acontece(db_factory, usuario):
    """O estado IMPOSSÍVEL que a auditoria produziu em PostgreSQL real.

    Sequência completa: A envia com sucesso depois de perder a claim, e B — o
    dono — falha. Antes da A3 isto terminava em `pending` com `sent_at`
    preenchido, e a mensagem saía uma terceira vez.
    """
    lid = await _linha(db_factory, usuario, attempts=0, locked_by="worker-A")

    await recupera_travados(db_factory, stale_minutes=_STALE_MIN, agora=_AGORA)
    async with db_factory() as s:
        await s.execute(
            update(EmailOutbox)
            .where(EmailOutbox.id == lid)
            .values(status="processing", locked_by="worker-B", locked_at=_AGORA)
        )
        await s.commit()

    # A, que perdeu a claim, "conclui com sucesso".
    await _persiste_resultado(
        db_factory,
        lid,
        EmailDeliveryResult(EmailDeliveryStatus.success),
        worker_id="worker-A",
        agora=_AGORA,
    )
    # B, o dono, falha temporariamente.
    await _persiste_resultado(
        db_factory,
        lid,
        EmailDeliveryResult(EmailDeliveryStatus.temporary_failure, "SMTPServerDisconnected"),
        worker_id="worker-B",
        agora=_AGORA,
    )

    st = await _estado(db_factory, lid)
    assert not (
        st.status == "pending" and st.sent_at is not None
    ), "estado impossível: linha na fila com sent_at preenchido"
    assert st.status == "pending"
    assert st.sent_at is None

    # E a invariante vale para a tabela inteira, não só para esta linha.
    async with db_factory() as s:
        impossiveis = (
            await s.execute(
                text(
                    "SELECT count(*) FROM email_outbox "
                    "WHERE status = 'pending' AND sent_at IS NOT NULL"
                )
            )
        ).scalar_one()
    assert impossiveis == 0


# ═══════════════════════════════════════════════════════════════
# Notification.email_sent segue o fencing
# ═══════════════════════════════════════════════════════════════


async def _com_notificacao(db_factory, usuario, *, locked_by: str) -> tuple[uuid.UUID, uuid.UUID]:
    nid = uuid.uuid4()
    lid = uuid.uuid4()
    async with db_factory() as s:
        s.add(
            Notification(
                id=nid,
                user_id=usuario,
                type=NotificationType.ticket_created,
                title="Ticket aberto",
                message="corpo",
                data=None,
                read=False,
                email_sent=False,
            )
        )
        await s.flush()
        s.add(
            EmailOutbox(
                id=lid,
                notification_id=nid,
                status="processing",
                attempts=0,
                next_attempt_at=_AGORA - timedelta(hours=1),
                locked_by=locked_by,
                locked_at=_AGORA,
            )
        )
        await s.commit()
    return lid, nid


async def _email_sent(db_factory, nid) -> bool:
    async with db_factory() as s:
        return (
            await s.execute(select(Notification.email_sent).where(Notification.id == nid))
        ).scalar_one()


@pytest.mark.asyncio
async def test_dono_legitimo_marca_email_sent(db_factory, usuario):
    lid, nid = await _com_notificacao(db_factory, usuario, locked_by="w")

    await _persiste_resultado(
        db_factory,
        lid,
        EmailDeliveryResult(EmailDeliveryStatus.success),
        worker_id="w",
        agora=_AGORA,
    )

    assert await _email_sent(db_factory, nid) is True


@pytest.mark.asyncio
async def test_falha_do_dono_legitimo_nao_marca_email_sent(db_factory, usuario):
    """`email_sent` descreve ENTREGA, não "o worker chegou até aqui".

    Sem a condição `novo_status == "sent"` no UPDATE da notificação, uma falha
    temporária marcaria a notificação como enviada por e-mail — e a linha
    continuaria tentando, com as duas fontes dizendo coisas opostas.
    """
    lid, nid = await _com_notificacao(db_factory, usuario, locked_by="w")

    await _persiste_resultado(
        db_factory,
        lid,
        EmailDeliveryResult(EmailDeliveryStatus.temporary_failure, "SMTPServerDisconnected"),
        worker_id="w",
        agora=_AGORA,
    )

    assert await _email_sent(db_factory, nid) is False
    st = await _estado(db_factory, lid)
    assert st.status == "pending"
    assert st.attempts == 1


@pytest.mark.asyncio
async def test_dead_do_dono_legitimo_nao_marca_email_sent(db_factory, usuario):
    """Mesma regra no outro desfecho terminal: desistir não é entregar."""
    lid, nid = await _com_notificacao(db_factory, usuario, locked_by="w")

    await _persiste_resultado(
        db_factory,
        lid,
        EmailDeliveryResult(
            EmailDeliveryStatus.permanent_failure, "SMTPRecipientRefused (code 550)"
        ),
        worker_id="w",
        agora=_AGORA,
    )

    assert await _email_sent(db_factory, nid) is False
    assert (await _estado(db_factory, lid)).status == "dead"


@pytest.mark.asyncio
async def test_quem_perdeu_a_claim_nao_marca_email_sent(db_factory, usuario):
    """O pior caso da origem Notification: `email_sent=True` numa notificação
    cujo e-mail este worker não tinha autoridade para declarar entregue."""
    lid, nid = await _com_notificacao(db_factory, usuario, locked_by="worker-B")

    await _persiste_resultado(
        db_factory,
        lid,
        EmailDeliveryResult(EmailDeliveryStatus.success),
        worker_id="worker-A",  # não é o dono
        agora=_AGORA,
    )

    assert await _email_sent(db_factory, nid) is False
    st = await _estado(db_factory, lid)
    assert st.status == "processing"
    assert st.locked_by == "worker-B"


# ═══════════════════════════════════════════════════════════════
# Nada de PII no log novo
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_logs_da_a3_nao_vazam_identificador_nem_pii(db_factory, usuario):
    """O log de claim perdida é mensagem FIXA, sem um campo variável: nem
    `worker_id`, nem id da linha, nem nada que cruze com destinatário."""
    lid = await _linha(db_factory, usuario, locked_by="worker-B", locked_at=_AGORA)

    capturado, sink = _captura()
    try:
        await _persiste_resultado(
            db_factory,
            lid,
            EmailDeliveryResult(EmailDeliveryStatus.success),
            worker_id="worker-A-com-pid-12345",
            agora=_AGORA,
        )
        await recupera_travados(db_factory, stale_minutes=_STALE_MIN, agora=_AGORA)
    finally:
        logger.remove(sink)

    texto = "\n".join(m for _, m in capturado)
    assert "claim was lost" in texto
    for proibido in (str(lid), str(usuario), "worker-A-com-pid-12345", "worker-B", "@"):
        assert proibido not in texto, proibido
