"""
O aviso de SLA contra PostgreSQL de verdade.

Por que este arquivo existe separado
------------------------------------
A garantia central da Fase 2A **é uma constraint de banco**. O worker só avisa
quem consegue inserir a linha de `sla_alert_events`, e quem decide isso é o
índice único `uq_sla_alert_events_identidade` junto com o
`INSERT ... ON CONFLICT DO NOTHING RETURNING id`.

Nada disso se prova com `AsyncMock`: um mock aceita duas inserções idênticas
sem reclamar e devolve o que você programou. A lição está no cabeçalho de
`tests/test_helo_base_postgres.py` e foi repetida em
`tests/test_audiencia_operacional_postgres.py` — mock não executa `WHERE`, e
também não executa `UNIQUE`.

O que fica provado aqui
-----------------------
1. a identidade do evento: mesmo prazo e mesmo limiar nunca repetem;
2. o que MUDA o prazo (extensão, reabertura) ou o limiar habilita aviso novo;
3. duas sessões independentes não duplicam;
4. rollback na criação das notificações não deixa evento órfão;
5. a audiência é a cláusula `WHERE` de verdade — cliente, inativo e anonimizado
   ficam fora;
6. não há N+1: uma consulta de `sla_configs` e uma de `users` por rodada,
   independentemente de quantos chamados entram na faixa.

Nenhum e-mail é enviado: `_disparar` é substituído em todos os testes que
chegam a commitar, e há contraprova disso no fim do arquivo.
"""

import shutil
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.models.models import (
    Base,
    Notification,
    NotificationType,
    SlaAlertEvent,
    SLAConfig,
    SLALevel,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
)
from app.services import notifications as servico_notificacoes
from app.services.sla_alertas import (
    ALERTA_RESOLUCAO,
    avisa_sla_proximo,
    candidatos,
    reivindica_evento,
)
from app.utils.sla import add_business_minutes, business_minutes_between
from tests.test_dashboard_postgres import _sobe_postgres

_ABERTURA = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)  # terça, 09:00 BRT


@pytest.fixture(scope="module")
def url_do_banco():
    import asyncio

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
async def db(url_do_banco):
    """Sessão dentro de uma transação externa que é sempre descartada.

    `join_transaction_mode="create_savepoint"` é obrigatório aqui, e não
    estilo: o código sob teste **commita** (`commit_e_notificar`). Sem isso, o
    `commit()` dele fecharia a transação externa e o `rollback()` do teardown
    não desfaria nada — no CI, onde `TEST_POSTGRES_URL` aponta para um banco
    COMPARTILHADO, cada rodada deixaria lixo para a seguinte.
    """
    motor = create_async_engine(url_do_banco)
    async with motor.connect() as conn:
        transacao = await conn.begin()
        fabrica = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        async with fabrica() as sessao:
            yield sessao
        await transacao.rollback()
    await motor.dispose()


# ══════════════════════════════════════════════════════════════
# Fábricas
# ══════════════════════════════════════════════════════════════


def _pessoa(papel: UserRole, status: UserStatus = UserStatus.active, nome: str = "Ana") -> User:
    return User(
        id=uuid.uuid4(),
        name=nome,
        email=f"{uuid.uuid4().hex[:10]}@test.com",
        password="x",
        role=papel,
        status=status,
        phone="+5581999999999" if papel == UserRole.client else None,
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
        created_at=_ABERTURA,
        updated_at=_ABERTURA,
    )


def _config(nivel: SLALevel, threshold: int) -> SLAConfig:
    return SLAConfig(
        id=uuid.uuid4(),
        level=nivel,
        response_time_minutes=60,
        resolve_time_minutes=540,
        warning_threshold=threshold,
        is_active=True,
    )


def _chamado(
    criador: User,
    *,
    prioridade: TicketPriority = TicketPriority.medium,
    status: TicketStatus = TicketStatus.in_progress,
    extensao_min: int = 0,
    reaberturas: int = 0,
) -> Ticket:
    prazo = add_business_minutes(_ABERTURA, 540)
    efetivo = add_business_minutes(prazo, extensao_min) if extensao_min else prazo
    return Ticket(
        id=uuid.uuid4(),
        protocol=f"HS-SLA-{uuid.uuid4().hex[:8]}",
        title="Impressora da recepção sem conexão",
        description="corpo",
        priority=prioridade,
        category=TicketCategory.hardware,
        status=status,
        creator_id=criador.id,
        sla_resolve_due_at=prazo,
        sla_resolve_effective_due_at=efetivo,
        sla_total_paused_ms=0,
        sla_resolve_extension_total_min=extensao_min,
        sla_response_breach=False,
        sla_resolve_breach=False,
        auto_closed=False,
        reopen_count=reaberturas,
        created_at=_ABERTURA,
        updated_at=_ABERTURA,
    )


def _instante(ticket: Ticket, pct: int) -> datetime:
    from app.utils.sla import prazo_efetivo_de_resolucao

    prazo = prazo_efetivo_de_resolucao(ticket)
    assert prazo is not None
    total = business_minutes_between(ticket.created_at, prazo)
    return add_business_minutes(ticket.created_at, int(round(total * pct / 100)))


def _settings_sem_smtp() -> Settings:
    """Settings de verdade, com SMTP DESLIGADO.

    `model_construct` não roda `model_post_init`, então não há guarda de CVE nem
    exigência de revisão de LGPD para satisfazer — e `email_is_configured()`
    devolve False, o que faz `send_email` retornar no primeiro `if`.
    """
    return Settings.model_construct(
        smtp_from_email="",
        smtp_user="",
        frontend_url="https://helphs.example.test",
        sla_warning_interval_seconds=300,
    )


async def _conta_eventos(db, ticket: Ticket) -> int:
    resultado = await db.execute(
        select(func.count()).select_from(SlaAlertEvent).where(SlaAlertEvent.ticket_id == ticket.id)
    )
    return int(resultado.scalar_one())


async def _notificacoes(db, ticket: Ticket) -> list[Notification]:
    resultado = await db.execute(
        select(Notification).where(Notification.type == NotificationType.sla_warning)
    )
    todas = list(resultado.scalars().all())
    return [n for n in todas if (n.data or {}).get("ticket_id") == str(ticket.id)]


# ══════════════════════════════════════════════════════════════
# 1. A identidade do evento
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_a_unique_recusa_o_mesmo_prazo_e_o_mesmo_limiar(db):
    """A constraint, nua. É ela que sustenta tudo o mais neste arquivo."""
    criador = _pessoa(UserRole.client)
    db.add(criador)
    ticket = _chamado(criador)
    db.add(ticket)
    await db.flush()

    prazo = ticket.sla_resolve_effective_due_at
    assert prazo is not None

    assert await reivindica_evento(db, ticket, prazo, 80) is True
    assert await reivindica_evento(db, ticket, prazo, 80) is False
    assert await _conta_eventos(db, ticket) == 1


@pytest.mark.asyncio
async def test_limiar_diferente_e_outra_identidade(db):
    """Editar a `sla_configs` cria um aviso legítimo novo: o administrador mudou
    a régua, e o chamado cruzou a nova."""
    criador = _pessoa(UserRole.client)
    db.add(criador)
    ticket = _chamado(criador)
    db.add(ticket)
    await db.flush()
    prazo = ticket.sla_resolve_effective_due_at
    assert prazo is not None

    assert await reivindica_evento(db, ticket, prazo, 80) is True
    assert await reivindica_evento(db, ticket, prazo, 70) is True
    assert await _conta_eventos(db, ticket) == 2


@pytest.mark.asyncio
async def test_prazo_diferente_e_outra_identidade(db):
    """Prorrogação, reabertura e pausa mudam o prazo efetivo — e é o prazo que
    está na chave, não um contador de ciclo. Um campo só, três causas."""
    criador = _pessoa(UserRole.client)
    db.add(criador)
    ticket = _chamado(criador)
    db.add(ticket)
    await db.flush()
    prazo = ticket.sla_resolve_effective_due_at
    assert prazo is not None

    assert await reivindica_evento(db, ticket, prazo, 80) is True
    assert await reivindica_evento(db, ticket, prazo + timedelta(hours=4), 80) is True
    assert await _conta_eventos(db, ticket) == 2


@pytest.mark.asyncio
async def test_a_auditoria_nao_participa_da_identidade(db):
    """`priority` e `extension_total_min` são snapshot puro.

    ⚠️ `reopen_count` ERA snapshot e passou a integrar a identidade em
    25/09/2026 — ver `test_dois_ciclos_com_o_mesmo_prazo_sao_identidades_distintas`.
    Os outros dois ficaram de fora porque nenhum deles muda o ciclo: prorrogar
    muda o prazo, que já está na chave, e trocar a prioridade também. Incluí-los
    criaria uma segunda resposta para "é o mesmo aviso?".
    """
    criador = _pessoa(UserRole.client)
    db.add(criador)
    ticket = _chamado(criador)
    db.add(ticket)
    await db.flush()
    prazo = ticket.sla_resolve_effective_due_at
    assert prazo is not None

    assert await reivindica_evento(db, ticket, prazo, 80) is True

    # Muda só o que é auditoria — sem tocar em `reopen_count`.
    ticket.priority = TicketPriority.critical
    ticket.sla_resolve_extension_total_min = 123
    assert await reivindica_evento(db, ticket, prazo, 80) is False
    assert await _conta_eventos(db, ticket) == 1


@pytest.mark.asyncio
async def test_dois_ciclos_com_o_mesmo_prazo_sao_identidades_distintas(db):
    """A colisão medida em 25/09/2026, e a razão de `reopen_count` estar na chave.

    `add_business_minutes` primeiro avança o instante para dentro do expediente.
    Então DUAS reaberturas em momentos diferentes da mesma janela fechada — noite,
    fim de semana, feriado — colapsam no mesmo início de jornada e produzem
    **exatamente o mesmo prazo**:

        sábado  11:00 BRT  ->  prazo 2026-09-21T17:00-03:00
        domingo 19:30 BRT  ->  prazo 2026-09-21T17:00-03:00   (32 h depois)

    E a reabertura zera pausa e extensão, então o prazo do ciclo novo é
    independente do anterior e pode coincidir com ele.

    Sem `reopen_count` na chave, o segundo aviso seria **silenciado** — e o
    silêncio é o pior desfecho possível para um alerta.
    """
    criador = _pessoa(UserRole.client)
    db.add(criador)
    ticket = _chamado(criador)
    db.add(ticket)
    await db.flush()

    sabado = datetime(2026, 9, 19, 14, 0, tzinfo=UTC)
    domingo = datetime(2026, 9, 20, 22, 30, tzinfo=UTC)
    prazo_a = add_business_minutes(sabado, 540)
    prazo_b = add_business_minutes(domingo, 540)
    assert prazo_a == prazo_b, "a premissa deste teste: os dois ciclos colidem no prazo"

    ticket.reopen_count = 1
    ticket.reopened_at = sabado
    assert await reivindica_evento(db, ticket, prazo_a, 80) is True

    ticket.reopen_count = 2
    ticket.reopened_at = domingo
    assert await reivindica_evento(db, ticket, prazo_b, 80) is True

    assert await _conta_eventos(db, ticket) == 2


@pytest.mark.asyncio
async def test_mesmo_ciclo_mesmo_prazo_mesmo_limiar_continua_deduplicado(db):
    """O outro lado: `reopen_count` na chave não pode afrouxar a dedup."""
    criador = _pessoa(UserRole.client)
    db.add(criador)
    ticket = _chamado(criador, reaberturas=3)
    db.add(ticket)
    await db.flush()
    prazo = ticket.sla_resolve_effective_due_at
    assert prazo is not None

    assert await reivindica_evento(db, ticket, prazo, 80) is True
    assert await reivindica_evento(db, ticket, prazo, 80) is False
    assert await reivindica_evento(db, ticket, prazo, 80) is False
    assert await _conta_eventos(db, ticket) == 1


@pytest.mark.asyncio
async def test_o_evento_guarda_o_snapshot_de_auditoria(db):
    criador = _pessoa(UserRole.client)
    db.add(criador)
    ticket = _chamado(criador, prioridade=TicketPriority.high, extensao_min=60, reaberturas=2)
    db.add(ticket)
    await db.flush()
    prazo = ticket.sla_resolve_effective_due_at
    assert prazo is not None

    await reivindica_evento(db, ticket, prazo, 80)

    evento = (
        await db.execute(select(SlaAlertEvent).where(SlaAlertEvent.ticket_id == ticket.id))
    ).scalar_one()
    assert evento.alert_kind == ALERTA_RESOLUCAO
    assert evento.priority == "high"
    assert evento.reopen_count == 2
    assert evento.extension_total_min == 60
    assert evento.warning_threshold == 80


# ══════════════════════════════════════════════════════════════
# 2. A rodada inteira
# ══════════════════════════════════════════════════════════════


async def _monta_cenario(db, *, threshold: int = 80, quantos: int = 1) -> list[Ticket]:
    cliente = _pessoa(UserRole.client, nome="Cliente")
    admin = _pessoa(UserRole.admin, nome="Admin Um")
    tecnico = _pessoa(UserRole.technician, nome="Tecnico Um")
    db.add_all([cliente, admin, tecnico])
    db.add(_config(SLALevel.medium, threshold))
    tickets = [_chamado(cliente) for _ in range(quantos)]
    db.add_all(tickets)
    await db.flush()
    return tickets


@pytest.mark.asyncio
async def test_a_rodada_avisa_uma_vez_e_a_seguinte_nao_repete(db):
    """O comportamento que o worker existe para ter: com o mesmo prazo e o mesmo
    limiar, a segunda rodada não manda nada."""
    (ticket,) = await _monta_cenario(db)
    agora = _instante(ticket, 85)

    with patch.object(servico_notificacoes, "_disparar"):
        primeira = await avisa_sla_proximo(db, _settings_sem_smtp(), agora)
        segunda = await avisa_sla_proximo(db, _settings_sem_smtp(), agora)

    assert primeira == 1
    assert segunda == 0
    assert await _conta_eventos(db, ticket) == 1
    assert len(await _notificacoes(db, ticket)) == 2  # admin + técnico


@pytest.mark.asyncio
async def test_a_extensao_habilita_um_aviso_novo(db):
    """Prorrogar muda o prazo efetivo, e o chamado pode voltar à faixa depois.
    Com a chave presa só no `ticket_id`, este segundo aviso nunca sairia."""
    (ticket,) = await _monta_cenario(db)
    agora = _instante(ticket, 85)

    with patch.object(servico_notificacoes, "_disparar"):
        assert await avisa_sla_proximo(db, _settings_sem_smtp(), agora) == 1

        # +30 min úteis: o prazo muda, e um instante mais adiante volta à faixa.
        ticket.sla_resolve_extension_total_min = 30
        from app.utils.sla import atualiza_prazo_efetivo

        atualiza_prazo_efetivo(ticket)
        await db.flush()

        depois = _instante(ticket, 90)
        assert await avisa_sla_proximo(db, _settings_sem_smtp(), depois) == 1

    assert await _conta_eventos(db, ticket) == 2


@pytest.mark.asyncio
async def test_a_reabertura_habilita_um_aviso_novo(db):
    """A reabertura recomeça o prazo de resolução de AGORA e zera pausa e
    extensão. É um ciclo novo, e ele merece avisar de novo."""
    (ticket,) = await _monta_cenario(db)
    agora = _instante(ticket, 85)

    with patch.object(servico_notificacoes, "_disparar"):
        assert await avisa_sla_proximo(db, _settings_sem_smtp(), agora) == 1

        from app.utils.sla import atualiza_prazo_efetivo

        reabertura = agora + timedelta(minutes=5)
        ticket.status = TicketStatus.in_progress
        ticket.sla_resolve_due_at = add_business_minutes(reabertura, 540)
        ticket.sla_resolve_breach = False
        ticket.sla_total_paused_ms = 0
        ticket.sla_resolve_extension_total_min = 0
        ticket.reopen_count = 1
        atualiza_prazo_efetivo(ticket)
        await db.flush()

        # O ciclo novo conta da abertura ORIGINAL para o total, como o motor faz.
        assert await avisa_sla_proximo(db, _settings_sem_smtp(), _instante(ticket, 95)) == 1

    assert await _conta_eventos(db, ticket) == 2


@pytest.mark.asyncio
async def test_mudar_o_limiar_habilita_um_aviso_novo(db):
    (ticket,) = await _monta_cenario(db, threshold=90)
    agora = _instante(ticket, 92)

    with patch.object(servico_notificacoes, "_disparar"):
        assert await avisa_sla_proximo(db, _settings_sem_smtp(), agora) == 1

        config = (await db.execute(select(SLAConfig))).scalars().first()
        assert config is not None
        config.warning_threshold = 70
        await db.flush()

        assert await avisa_sla_proximo(db, _settings_sem_smtp(), agora) == 1

    assert await _conta_eventos(db, ticket) == 2


# ══════════════════════════════════════════════════════════════
# 3. Concorrência e rollback
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_duas_sessoes_independentes_nao_duplicam(url_do_banco):
    """Duas instâncias da API, dois processos, o mesmo chamado.

    O que este teste prova: a sessão B, cuja transação COMEÇOU antes de A
    commitar, ainda assim recebe zero linhas — o `ON CONFLICT` enxerga o
    conflito já commitado, e não a foto do início da transação dela.

    O que ele NÃO prova, e por isso não promete: o caso de duas inserções
    simultâneas de verdade, em que o PostgreSQL bloqueia B no índice até A
    decidir. Esse caminho existe e é o mesmo código, mas encená-lo com dois
    laços de evento trocaria determinismo por tempo de espera.

    Commita de propósito, então limpa o que criou — no CI o banco é
    COMPARTILHADO.
    """
    motor = create_async_engine(url_do_banco)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    criador = _pessoa(UserRole.client)
    ticket = _chamado(criador)
    prazo = ticket.sla_resolve_effective_due_at
    assert prazo is not None

    try:
        async with fabrica() as preparo:
            preparo.add(criador)
            preparo.add(ticket)
            await preparo.commit()

        async with fabrica() as sessao_b:
            # B abre a transação ANTES de A gravar.
            await sessao_b.execute(select(func.count()).select_from(SlaAlertEvent))

            async with fabrica() as sessao_a:
                assert await reivindica_evento(sessao_a, ticket, prazo, 80) is True
                await sessao_a.commit()

            assert await reivindica_evento(sessao_b, ticket, prazo, 80) is False
            await sessao_b.commit()

        async with fabrica() as conferencia:
            total = await conferencia.execute(
                select(func.count())
                .select_from(SlaAlertEvent)
                .where(SlaAlertEvent.ticket_id == ticket.id)
            )
            assert int(total.scalar_one()) == 1
    finally:
        async with fabrica() as limpeza:
            await limpeza.execute(
                SlaAlertEvent.__table__.delete().where(SlaAlertEvent.ticket_id == ticket.id)
            )
            await limpeza.execute(Ticket.__table__.delete().where(Ticket.id == ticket.id))
            await limpeza.execute(User.__table__.delete().where(User.id == criador.id))
            await limpeza.commit()
        await motor.dispose()


@pytest.mark.asyncio
async def test_rollback_na_notificacao_nao_deixa_evento_orfao(db):
    """O estado irrecuperável que a transação única evita: evento gravado e
    ninguém avisado, para sempre.

    `notifica_audiencia` levanta; o evento tem de desaparecer com ela, e a
    rodada seguinte precisa poder tentar de novo.
    """
    (ticket,) = await _monta_cenario(db)
    agora = _instante(ticket, 85)
    settings = _settings_sem_smtp()

    async def _explode(*_args, **_kwargs):
        raise RuntimeError("banco recusou a notificação")

    ponto_seguro = await db.begin_nested()
    with patch.object(servico_notificacoes, "notifica_audiencia", new=_explode):
        with patch("app.services.sla_alertas.notifica_audiencia", new=_explode):
            with pytest.raises(RuntimeError):
                await avisa_sla_proximo(db, settings, agora)
    await ponto_seguro.rollback()

    assert await _conta_eventos(db, ticket) == 0

    # E a rodada seguinte, agora sem o defeito, avisa normalmente.
    with patch.object(servico_notificacoes, "_disparar"):
        assert await avisa_sla_proximo(db, settings, agora) == 1
    assert await _conta_eventos(db, ticket) == 1


# ══════════════════════════════════════════════════════════════
# 4. A audiência é uma cláusula WHERE
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_todos_os_tecnicos_e_admins_ativos_recebem_e_mais_ninguem(db):
    cliente = _pessoa(UserRole.client, nome="Cliente")
    admin = _pessoa(UserRole.admin, nome="Admin")
    tecnico_a = _pessoa(UserRole.technician, nome="Tec A")
    tecnico_b = _pessoa(UserRole.technician, nome="Tec B")
    inativo = _pessoa(UserRole.technician, status=UserStatus.inactive, nome="Tec Fora")
    anonimizado = _pessoa(UserRole.admin, status=UserStatus.anonymized, nome="Admin LGPD")
    db.add_all([cliente, admin, tecnico_a, tecnico_b, inativo, anonimizado])
    db.add(_config(SLALevel.medium, 80))
    ticket = _chamado(cliente)
    db.add(ticket)
    await db.flush()

    with patch.object(servico_notificacoes, "_disparar"):
        assert await avisa_sla_proximo(db, _settings_sem_smtp(), _instante(ticket, 85)) == 1

    avisados = {n.user_id for n in await _notificacoes(db, ticket)}

    assert avisados == {admin.id, tecnico_a.id, tecnico_b.id}
    assert cliente.id not in avisados
    assert inativo.id not in avisados
    assert anonimizado.id not in avisados


@pytest.mark.asyncio
async def test_o_data_da_notificacao_permite_navegar(db):
    (ticket,) = await _monta_cenario(db)

    with patch.object(servico_notificacoes, "_disparar"):
        await avisa_sla_proximo(db, _settings_sem_smtp(), _instante(ticket, 85))

    notificacao = (await _notificacoes(db, ticket))[0]
    dados = notificacao.data or {}

    assert dados["ticket_id"] == str(ticket.id)
    assert dados["protocol"] == ticket.protocol
    assert dados["sla_kind"] == "resolution"
    assert dados["warning_threshold"] == 80
    assert notificacao.type == NotificationType.sla_warning
    assert notificacao.read is False


@pytest.mark.asyncio
async def test_o_assunto_do_email_nao_leva_o_titulo_do_chamado(db):
    """O e-mail é registrado como pendência da sessão; aqui interceptamos o
    disparo e lemos o que teria saído. Nenhum socket é aberto."""
    (ticket,) = await _monta_cenario(db)
    disparados = []

    with patch.object(servico_notificacoes, "_disparar", new=disparados.append):
        await avisa_sla_proximo(db, _settings_sem_smtp(), _instante(ticket, 85))

    assert len(disparados) == 2, "admin e técnico"
    for pendente in disparados:
        assert pendente.subject == f"[HelpHS] SLA próximo do vencimento — {ticket.protocol}"
        assert ticket.title not in pendente.subject
        assert ticket.title not in pendente.body


# ══════════════════════════════════════════════════════════════
# 5. Os filtros, na consulta de verdade
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_a_consulta_de_candidatos_exclui_terminal_pausado_vencido_e_sem_prazo(db):
    cliente = _pessoa(UserRole.client)
    db.add(cliente)
    agora = _instante(_chamado(cliente), 50)

    elegivel = _chamado(cliente)
    terminal = _chamado(cliente, status=TicketStatus.resolved)
    pausado = _chamado(cliente)
    pausado.sla_paused_at = agora
    sem_prazo = _chamado(cliente)
    sem_prazo.sla_resolve_effective_due_at = None
    sem_prioridade = _chamado(cliente)
    sem_prioridade.priority = None
    vencido = _chamado(cliente)
    vencido.sla_resolve_effective_due_at = agora - timedelta(minutes=1)

    db.add_all([elegivel, terminal, pausado, sem_prazo, sem_prioridade, vencido])
    await db.flush()

    encontrados = {t.id for t in await candidatos(db, agora)}

    assert elegivel.id in encontrados
    assert terminal.id not in encontrados
    assert pausado.id not in encontrados
    assert sem_prazo.id not in encontrados
    assert sem_prioridade.id not in encontrados
    assert vencido.id not in encontrados


@pytest.mark.asyncio
async def test_a_ordem_e_por_vencimento_mais_proximo(db):
    """Com o lote cheio, o que fica de fora tem de ser o que tem mais tempo."""
    cliente = _pessoa(UserRole.client)
    db.add(cliente)
    base = add_business_minutes(_ABERTURA, 540)
    longe = _chamado(cliente)
    longe.sla_resolve_effective_due_at = base + timedelta(hours=10)
    perto = _chamado(cliente)
    perto.sla_resolve_effective_due_at = base
    db.add_all([longe, perto])
    await db.flush()

    ordem = [t.id for t in await candidatos(db, _ABERTURA)]

    assert ordem.index(perto.id) < ordem.index(longe.id)


# ══════════════════════════════════════════════════════════════
# 6. Sem N+1
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_a_rodada_nao_faz_n_mais_um_de_config_nem_de_usuario(db):
    """Três chamados na faixa: uma consulta de `sla_configs` e uma de `users`.

    O `notify` individual faz um SELECT por destinatário; um laço dele daria
    N×M. `notifica_audiencia` recebe a audiência já carregada e não vai ao banco
    nenhuma vez — este teste é o que impede alguém de trocar por um laço de
    `notify` sem perceber o custo.
    """
    tickets = await _monta_cenario(db, quantos=3)
    agora = _instante(tickets[0], 85)

    consultas: list[str] = []
    bruta = await db.connection()

    def _grava(_conn, _cursor, instrucao, *_resto):
        consultas.append(" ".join(instrucao.split()).lower())

    event.listen(bruta.sync_connection.engine, "before_cursor_execute", _grava)
    try:
        with patch.object(servico_notificacoes, "_disparar"):
            assert await avisa_sla_proximo(db, _settings_sem_smtp(), agora) == 3
    finally:
        event.remove(bruta.sync_connection.engine, "before_cursor_execute", _grava)

    de_config = [q for q in consultas if "from sla_configs" in q]
    de_usuario = [q for q in consultas if "from users" in q]

    assert len(de_config) == 1, f"N+1 de SLAConfig: {len(de_config)} consultas"
    assert len(de_usuario) == 1, f"N+1 de usuários: {len(de_usuario)} consultas"


# ══════════════════════════════════════════════════════════════
# 7. Contraprova de que nada saiu
# ══════════════════════════════════════════════════════════════


def test_o_settings_destes_testes_nao_tem_smtp():
    """Mesmo se alguém remover um `patch` de `_disparar`, `send_email` retorna no
    primeiro `if` — não há credencial nem host neste arquivo."""
    settings = _settings_sem_smtp()

    assert settings.email_is_configured() is False
    assert settings.smtp_from_email == ""
    assert settings.smtp_user == ""
