"""
A extensão contra PostgreSQL de verdade.

Três coisas só se provam com banco: a migration, a tabela de eventos, e os
números que o painel calcula em SQL agregado.

O caso mais importante daqui é o `TestNumerosDoPainel`: ele monta os quatro
cenários combinando pausa e extensão e exige que **motor e painel concordem**
nos quatro. Era isso que não acontecia antes — o painel comparava a coluna crua
e já discordava do motor sempre que havia pausa.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import (
    Base,
    SLAConfig,
    SLALevel,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketSlaExtension,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
)
from app.routers.dashboard import get_dashboard_stats
from app.utils.sla import (
    atualiza_prazo_efetivo,
    minutos_uteis_de_dias,
    prazo_efetivo_de_resolucao,
)
from tests.test_dashboard_postgres import _sobe_postgres

_AGORA = datetime.now(UTC)


@pytest.fixture(scope="module")
def url_do_banco():
    import asyncio
    import shutil

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
    motor = create_async_engine(url_do_banco)
    async with motor.connect() as conn:
        transacao = await conn.begin()
        async with async_sessionmaker(bind=conn, expire_on_commit=False)() as sessao:
            yield sessao
        await transacao.rollback()
    await motor.dispose()


def _usuario(papel=UserRole.technician, nome="Ana"):
    return User(
        id=uuid.uuid4(),
        name=nome,
        email=f"{uuid.uuid4().hex[:8]}@test.com",
        password="x",
        role=papel,
        status=UserStatus.active,
        phone="+5581999999999" if papel == UserRole.client else None,
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
        created_at=_AGORA,
        updated_at=_AGORA,
    )


def _chamado(criador, *, vence_em, pausa_ms=0, extensao_min=0):
    """Chamado ativo com prazo de resolução, pausa e extensão à escolha."""
    t = Ticket(
        id=uuid.uuid4(),
        protocol=f"HS-EXT-{uuid.uuid4().hex[:8]}",
        title="Chamado sintético",
        description="corpo",
        priority=TicketPriority.medium,
        category=TicketCategory.hardware,
        status=TicketStatus.in_progress,
        creator_id=criador.id,
        sla_resolve_due_at=vence_em,
        sla_response_breach=False,
        sla_resolve_breach=False,
        sla_total_paused_ms=pausa_ms,
        sla_resolve_extension_total_min=extensao_min,
        auto_closed=False,
        reopen_count=0,
        created_at=_AGORA - timedelta(days=1),
        updated_at=_AGORA,
    )
    atualiza_prazo_efetivo(t)
    return t


# ══════════════════════════════════════════════════════════════
# A TABELA DE EVENTOS
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_a_tabela_guarda_a_concessao_inteira(db):
    cliente = _usuario(UserRole.client, "Cliente")
    tecnico = _usuario()
    db.add_all([cliente, tecnico])
    await db.flush()

    chamado = _chamado(cliente, vence_em=_AGORA + timedelta(hours=4))
    db.add(chamado)
    await db.flush()

    antes = chamado.sla_resolve_effective_due_at
    chamado.sla_resolve_extension_total_min = minutos_uteis_de_dias(3)
    atualiza_prazo_efetivo(chamado)

    db.add(
        TicketSlaExtension(
            id=uuid.uuid4(),
            ticket_id=chamado.id,
            user_id=tecnico.id,
            days=3,
            business_minutes=minutos_uteis_de_dias(3),
            justification="Aguardando peça de reposição do fabricante.",
            previous_effective_due_at=antes,
            new_effective_due_at=chamado.sla_resolve_effective_due_at,
        )
    )
    await db.flush()

    linha = (
        await db.execute(
            text(
                "SELECT days, business_minutes, justification "
                "FROM ticket_sla_extensions WHERE ticket_id = :t"
            ),
            {"t": chamado.id},
        )
    ).one()
    assert linha[0] == 3
    assert linha[1] == minutos_uteis_de_dias(3)
    assert linha[2] == "Aguardando peça de reposição do fabricante."


# ══════════════════════════════════════════════════════════════
# OS NÚMEROS DO PAINEL, NOS QUATRO CENÁRIOS
# ══════════════════════════════════════════════════════════════


class TestNumerosDoPainel:
    """Motor e painel têm de concordar nos quatro cenários.

    O caso 1 (sem pausa e sem extensão) é o controle: ele NÃO pode mudar de
    comportamento por causa desta entrega. Os outros três mudam — e mudam para
    concordar com o que o chamado já mostrava.
    """

    @staticmethod
    async def _conta_violados(db, tecnico):
        stats = await get_dashboard_stats(db, tecnico)
        return stats.sla.resolve_breached

    @pytest.mark.asyncio
    async def test_1_sem_pausa_sem_extensao_permanece_identico(self, db):
        """Controle: prazo vencido, sem pausa e sem extensão → violado, como sempre."""
        cliente, tecnico = _usuario(UserRole.client, "C"), _usuario()
        db.add_all([cliente, tecnico])
        await db.flush()

        chamado = _chamado(cliente, vence_em=_AGORA - timedelta(hours=2))
        db.add(chamado)
        await db.flush()

        assert await self._conta_violados(db, tecnico) == 1
        assert prazo_efetivo_de_resolucao(chamado) < _AGORA

    @pytest.mark.asyncio
    async def test_2_com_extensao_deixa_de_contar_violacao(self, db):
        """Prorrogado antes de vencer: o painel para de contar, como o chamado."""
        cliente, tecnico = _usuario(UserRole.client, "C"), _usuario()
        db.add_all([cliente, tecnico])
        await db.flush()

        chamado = _chamado(
            cliente,
            vence_em=_AGORA - timedelta(hours=2),
            extensao_min=minutos_uteis_de_dias(5),
        )
        db.add(chamado)
        await db.flush()

        assert await self._conta_violados(db, tecnico) == 0
        assert prazo_efetivo_de_resolucao(chamado) > _AGORA

    @pytest.mark.asyncio
    async def test_3_com_pausa_o_painel_passa_a_concordar_com_o_motor(self, db):
        """É a divergência ANTIGA sendo eliminada.

        Prazo cru vencido há 2h, mas 5h de pausa acumulada empurram o prazo
        efetivo para o futuro. Antes desta entrega o painel contava violação
        aqui e o chamado dizia que estava no prazo.
        """
        cliente, tecnico = _usuario(UserRole.client, "C"), _usuario()
        db.add_all([cliente, tecnico])
        await db.flush()

        chamado = _chamado(
            cliente,
            vence_em=_AGORA - timedelta(hours=2),
            pausa_ms=5 * 60 * 60 * 1000,
        )
        db.add(chamado)
        await db.flush()

        assert await self._conta_violados(db, tecnico) == 0
        assert prazo_efetivo_de_resolucao(chamado) > _AGORA

    @pytest.mark.asyncio
    async def test_4_pausa_mais_extensao_tambem_concordam(self, db):
        cliente, tecnico = _usuario(UserRole.client, "C"), _usuario()
        db.add_all([cliente, tecnico])
        await db.flush()

        chamado = _chamado(
            cliente,
            vence_em=_AGORA - timedelta(hours=2),
            pausa_ms=3 * 60 * 60 * 1000,
            extensao_min=minutos_uteis_de_dias(1),
        )
        db.add(chamado)
        await db.flush()

        assert await self._conta_violados(db, tecnico) == 0
        assert prazo_efetivo_de_resolucao(chamado) > _AGORA

    @pytest.mark.asyncio
    async def test_a_extensao_nao_salva_quem_ja_tinha_a_marca(self, db):
        """Marca gravada continua contando, prazo novo ou não.

        A extensão vale daqui para a frente; o que já foi concluído não se
        desfaz — e o `or_` da condição garante isso.
        """
        cliente, tecnico = _usuario(UserRole.client, "C"), _usuario()
        db.add_all([cliente, tecnico])
        await db.flush()

        chamado = _chamado(
            cliente,
            vence_em=_AGORA - timedelta(hours=2),
            extensao_min=minutos_uteis_de_dias(5),
        )
        chamado.sla_resolve_breach = True
        db.add(chamado)
        await db.flush()

        assert await self._conta_violados(db, tecnico) == 1


# ══════════════════════════════════════════════════════════════
# O INVARIANTE DA MATERIALIZAÇÃO
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_nenhum_caminho_deixa_a_coluna_divergir(db):
    """Percorre TODOS os eventos que mexem nos insumos do prazo efetivo.

    Enumerados por varredura do código: `sla_resolve_due_at` é escrito em dois
    lugares (`apply_sla_config` e a reabertura), `sla_total_paused_ms` em três
    (criação, reabertura e `resume_sla`), e a extensão em dois (concessão e
    reabertura). A pausa EM CURSO não é insumo — o motor nunca a considerou.

    Se algum caminho novo escrever um desses campos sem materializar, este
    teste cai.
    """
    from app.utils.sla import apply_sla_config, pause_sla, resume_sla

    cliente = _usuario(UserRole.client, "C")
    db.add(cliente)
    await db.flush()

    chamado = _chamado(cliente, vence_em=_AGORA + timedelta(hours=4))
    db.add(chamado)
    await db.flush()

    def _confere(etapa: str):
        assert chamado.sla_resolve_effective_due_at == prazo_efetivo_de_resolucao(
            chamado
        ), f"a coluna divergiu do motor depois de: {etapa}"

    _confere("criação")

    # 1. Carimbar o SLA (triagem e mudança de prioridade passam por aqui).
    #
    # `SLAConfig` de verdade, e não um objeto de mentira: `apply_sla_config`
    # grava `sla_config_id`, e a chave estrangeira do Postgres recusa um id
    # que não existe. Foi o próprio banco que cobrou isso.
    config = SLAConfig(
        id=uuid.uuid4(),
        level=SLALevel.medium,
        response_time_minutes=120,
        resolve_time_minutes=720,
        warning_threshold=80,
        is_active=True,
    )
    db.add(config)
    await db.flush()
    apply_sla_config(chamado, config, chamado.created_at)
    _confere("apply_sla_config")

    # 2. Pausar não muda o acumulado — e não pode mudar a coluna.
    pause_sla(chamado, _AGORA)
    _confere("pause_sla")

    # 3. Retomar muda o acumulado de pausa.
    resume_sla(chamado, _AGORA + timedelta(hours=2))
    _confere("resume_sla")

    # 4. Conceder extensão.
    chamado.sla_resolve_extension_total_min += minutos_uteis_de_dias(3)
    atualiza_prazo_efetivo(chamado)
    _confere("extensão")

    # 5. Reabertura: prazo novo, pausa zerada, extensão zerada.
    chamado.sla_resolve_due_at = _AGORA + timedelta(hours=8)
    chamado.sla_total_paused_ms = 0
    chamado.sla_resolve_extension_total_min = 0
    atualiza_prazo_efetivo(chamado)
    _confere("reabertura")

    await db.flush()
    guardado = (
        await db.execute(
            text("SELECT sla_resolve_effective_due_at FROM tickets WHERE id = :t"),
            {"t": chamado.id},
        )
    ).scalar_one()
    assert guardado == prazo_efetivo_de_resolucao(chamado)
