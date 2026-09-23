"""
O endpoint que concede a extensão, e quem pode usá-lo.

Contrato e autorização com mocks; o que depende de banco de verdade — a
migration, a tabela de eventos e os números do painel — está em
`test_sla_extensao_postgres.py`.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import TicketPriority, TicketStatus, UserRole
from app.utils.sla import SP_TZ, minutos_uteis_de_dias
from tests.test_tickets import _mock_ticket, _mock_user, _override_user, patch_redis  # noqa: F401

_ABERTURA = SP_TZ.localize(datetime(2026, 9, 23, 9, 11))
_PRAZO = SP_TZ.localize(datetime(2026, 9, 24, 12, 11))


def _ticket_extensivel(**kwargs):
    """Chamado ativo, com prioridade e prazo de resolução no futuro."""
    t = _mock_ticket(status=TicketStatus.in_progress)
    t.priority = TicketPriority.medium
    t.created_at = _ABERTURA
    t.sla_resolve_due_at = _PRAZO
    t.sla_response_due_at = SP_TZ.localize(datetime(2026, 9, 23, 11, 11))
    t.sla_total_paused_ms = 0
    t.sla_resolve_extension_total_min = 0
    t.sla_resolve_effective_due_at = _PRAZO
    t.sla_extensions = []
    for k, v in kwargs.items():
        setattr(t, k, v)
    return t


def _db(ticket):
    """Sessão que devolve o chamado e coleciona o que foi adicionado."""
    adicionados = []

    async def _execute(*args, **kwargs):
        r = MagicMock()
        r.scalar_one_or_none.return_value = ticket
        r.scalar_one.return_value = 0
        r.scalars.return_value.all.return_value = []
        return r

    s = AsyncMock()
    s.execute = _execute
    s.add = MagicMock(side_effect=adicionados.append)
    s.commit = AsyncMock()
    s.refresh = AsyncMock()

    async def _gen():
        yield s

    return s, _gen, adicionados


def _corpo(days=3, justification="Aguardando peça de reposição do fabricante."):
    return {"days": days, "justification": justification}


async def _estende(papel, ticket, corpo=None):
    from app.core.database import get_db

    ator = _mock_user(papel)
    _, gen, adicionados = _db(ticket)
    app.dependency_overrides[get_db] = gen
    _override_user(ator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{ticket.id}/sla/extend",
            json=corpo or _corpo(),
        )
    return resp, ator, adicionados


# ══════════════════════════════════════════════════════════════
# QUEM PODE
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cliente_recebe_403(patch_redis):  # noqa: F811
    resp, _, _ = await _estende(UserRole.client, _ticket_extensivel())
    assert resp.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", [UserRole.technician, UserRole.admin])
async def test_staff_estende(patch_redis, papel):  # noqa: F811
    """Técnico e administrador têm a mesma permissão — quem atende, prorroga."""
    resp, _, _ = await _estende(papel, _ticket_extensivel())
    assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════
# O QUE É ACEITO
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("dias", [1, 3, 5, 15, 30])
async def test_os_cinco_valores_permitidos(patch_redis, dias):  # noqa: F811
    resp, _, _ = await _estende(UserRole.admin, _ticket_extensivel(), _corpo(days=dias))
    assert resp.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("dias", [0, 2, 7, -3, 31, 1000])
async def test_qualquer_outro_valor_e_recusado(patch_redis, dias):  # noqa: F811
    """A lista é fechada no SCHEMA, então a recusa vem antes do router.

    Não é validação escrita à mão em `if`: é `Literal`, e por isso vale
    igualmente para quem montar a requisição na unha.
    """
    resp, _, _ = await _estende(UserRole.admin, _ticket_extensivel(), _corpo(days=dias))
    assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("texto", ["", "   "])
async def test_justificativa_e_obrigatoria(patch_redis, texto):  # noqa: F811
    resp, _, _ = await _estende(UserRole.admin, _ticket_extensivel(), _corpo(justification=texto))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_justificativa_tem_teto_de_dois_mil(patch_redis):  # noqa: F811
    """O mesmo teto das outras justificativas do projeto."""
    resp, _, _ = await _estende(
        UserRole.admin, _ticket_extensivel(), _corpo(justification="x" * 2001)
    )
    assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════
# QUANDO NÃO DÁ
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status", [TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]
)
async def test_chamado_encerrado_nao_estende(patch_redis, status):  # noqa: F811
    resp, _, _ = await _estende(UserRole.admin, _ticket_extensivel(status=status))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_chamado_sem_prioridade_nao_estende(patch_redis):  # noqa: F811
    resp, _, _ = await _estende(UserRole.admin, _ticket_extensivel(priority=None))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_chamado_sem_prazo_de_resolucao_nao_estende(patch_redis):  # noqa: F811
    resp, _, _ = await _estende(
        UserRole.admin,
        _ticket_extensivel(sla_resolve_due_at=None, sla_resolve_effective_due_at=None),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_prazo_ja_vencido_nao_estende(patch_redis):  # noqa: F811
    """A extensão não serve para apagar violação depois do fato.

    E a recusa NÃO olha `sla_resolve_breach`: a flag só é recalculada em
    escrita, então um chamado vencido e intocado chega com ela falsa. Quem
    decide é a comparação de `now` com o prazo efetivo.
    """
    vencido = _ticket_extensivel(
        sla_resolve_due_at=SP_TZ.localize(datetime(2020, 1, 2, 10, 0)),
        sla_resolve_effective_due_at=SP_TZ.localize(datetime(2020, 1, 2, 10, 0)),
        sla_resolve_breach=False,
    )
    resp, _, _ = await _estende(UserRole.admin, vencido)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_vencido_com_violacao_registrada_continua_violado(patch_redis):  # noqa: F811
    """Recusar não pode, de quebra, limpar a marca que já existia."""
    vencido = _ticket_extensivel(
        sla_resolve_due_at=SP_TZ.localize(datetime(2020, 1, 2, 10, 0)),
        sla_resolve_effective_due_at=SP_TZ.localize(datetime(2020, 1, 2, 10, 0)),
        sla_resolve_breach=True,
    )
    resp, _, _ = await _estende(UserRole.admin, vencido)

    assert resp.status_code == 409
    assert vencido.sla_resolve_breach is True


# ══════════════════════════════════════════════════════════════
# O QUE A CONCESSÃO FAZ
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_o_prazo_original_nao_e_tocado(patch_redis):  # noqa: F811
    """A regra crítica: `sla_resolve_due_at` continua sendo o da prioridade."""
    t = _ticket_extensivel()
    antes = t.sla_resolve_due_at

    resp, _, _ = await _estende(UserRole.admin, t)

    assert resp.status_code == 200
    assert t.sla_resolve_due_at == antes


@pytest.mark.asyncio
async def test_o_acumulador_soma_em_minutos_uteis(patch_redis):  # noqa: F811
    t = _ticket_extensivel()

    await _estende(UserRole.admin, t, _corpo(days=3))

    assert t.sla_resolve_extension_total_min == minutos_uteis_de_dias(3)


@pytest.mark.asyncio
async def test_duas_concessoes_acumulam(patch_redis):  # noqa: F811
    """+3 e depois +1 dão +4 — e o prazo sai da base, não do prazo anterior."""
    t = _ticket_extensivel(sla_resolve_extension_total_min=minutos_uteis_de_dias(3))

    await _estende(UserRole.admin, t, _corpo(days=1))

    assert t.sla_resolve_extension_total_min == minutos_uteis_de_dias(4)


@pytest.mark.asyncio
async def test_a_coluna_materializada_acompanha(patch_redis):  # noqa: F811
    from app.utils.sla import prazo_efetivo_de_resolucao

    t = _ticket_extensivel()

    await _estende(UserRole.admin, t, _corpo(days=5))

    assert t.sla_resolve_effective_due_at == prazo_efetivo_de_resolucao(t)
    assert t.sla_resolve_effective_due_at > t.sla_resolve_due_at


@pytest.mark.asyncio
async def test_o_prazo_de_resposta_nao_muda(patch_redis):  # noqa: F811
    t = _ticket_extensivel()
    antes = t.sla_response_due_at

    await _estende(UserRole.admin, t, _corpo(days=30))

    assert t.sla_response_due_at == antes


@pytest.mark.asyncio
async def test_grava_o_evento_com_tudo_que_a_auditoria_precisa(patch_redis):  # noqa: F811
    """Quem, quantos dias, de que prazo para qual, e com que justificativa."""
    from app.models.models import TicketSlaExtension

    t = _ticket_extensivel()
    prazo_antes = t.sla_resolve_effective_due_at

    resp, ator, adicionados = await _estende(UserRole.admin, t, _corpo(days=3))

    assert resp.status_code == 200
    eventos = [o for o in adicionados if isinstance(o, TicketSlaExtension)]
    assert len(eventos) == 1
    e = eventos[0]
    assert e.user_id == ator.id
    assert e.days == 3
    assert e.business_minutes == minutos_uteis_de_dias(3)
    assert e.justification == "Aguardando peça de reposição do fabricante."
    assert e.previous_effective_due_at == prazo_antes
    assert e.new_effective_due_at == t.sla_resolve_effective_due_at


@pytest.mark.asyncio
async def test_grava_a_linha_do_historico_para_a_timeline(patch_redis):  # noqa: F811
    """A Atividade já existe e é por `ticket_history` — a extensão entra nela.

    A fonte auditável dos DADOS é a tabela própria; esta linha existe para a
    timeline não ficar com um buraco onde houve uma decisão de prazo.
    """
    from app.models.models import TicketHistory

    t = _ticket_extensivel()

    _, ator, adicionados = await _estende(UserRole.admin, t, _corpo(days=3))

    historico = [o for o in adicionados if isinstance(o, TicketHistory)]
    assert len(historico) == 1
    assert historico[0].field == "sla_extension"
    assert historico[0].user_id == ator.id
    assert historico[0].comment == "Aguardando peça de reposição do fabricante."


@pytest.mark.asyncio
async def test_avisa_o_cliente(patch_redis):  # noqa: F811
    """Quem abriu o chamado é notificado, com o prazo novo e o motivo."""
    from app.models.models import Notification

    t = _ticket_extensivel()

    _, _, adicionados = await _estende(UserRole.admin, t, _corpo(days=3))

    avisos = [o for o in adicionados if isinstance(o, Notification)]
    assert len(avisos) == 1
    assert avisos[0].user_id == t.creator_id
    assert "3 dias úteis" in avisos[0].message
    assert "Aguardando peça de reposição do fabricante." in avisos[0].message


@pytest.mark.asyncio
async def test_registra_auditoria(patch_redis):  # noqa: F811
    from app.models.models import AuditLog

    t = _ticket_extensivel()

    _, ator, adicionados = await _estende(UserRole.admin, t, _corpo())

    logs = [o for o in adicionados if isinstance(o, AuditLog)]
    assert len(logs) == 1
    assert logs[0].user_id == ator.id
    assert logs[0].entity_id == t.id


# ══════════════════════════════════════════════════════════════
# O PREVIEW
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_preview_devolve_os_dois_prazos_sem_gravar(patch_redis):  # noqa: F811
    from app.core.database import get_db
    from app.utils.sla import prazo_efetivo_de_resolucao

    t = _ticket_extensivel()
    antes = t.sla_resolve_extension_total_min
    _, gen, adicionados = _db(t)
    app.dependency_overrides[get_db] = gen
    _override_user(_mock_user(UserRole.technician))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{t.id}/sla/extend/preview", params={"days": 3})

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["days"] == 3
    assert corpo["business_minutes"] == minutos_uteis_de_dias(3)
    assert corpo["prazo_atual"] is not None
    assert corpo["novo_prazo"] > corpo["prazo_atual"]
    # E não escreveu nada.
    assert t.sla_resolve_extension_total_min == antes
    assert adicionados == []
    assert prazo_efetivo_de_resolucao(t) == t.sla_resolve_effective_due_at


@pytest.mark.asyncio
async def test_preview_recusa_valor_fora_da_lista(patch_redis):  # noqa: F811
    from app.core.database import get_db

    t = _ticket_extensivel()
    _, gen, _ = _db(t)
    app.dependency_overrides[get_db] = gen
    _override_user(_mock_user(UserRole.admin))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{t.id}/sla/extend/preview", params={"days": 7})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_preview_e_so_para_a_equipe(patch_redis):  # noqa: F811
    from app.core.database import get_db

    t = _ticket_extensivel()
    _, gen, _ = _db(t)
    app.dependency_overrides[get_db] = gen
    _override_user(_mock_user(UserRole.client))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{t.id}/sla/extend/preview", params={"days": 3})

    assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════
# CICLO DE VIDA
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_mudar_prioridade_mantem_a_extensao(patch_redis):  # noqa: F811
    """Recarimbar o prazo base não devolve o tempo já concedido.

    Sai de graça do desenho: `apply_sla_config` escreve a BASE, e a extensão
    vive num acumulador separado. O teste existe para que uma refatoração
    futura não junte os dois.
    """
    from app.utils.sla import apply_sla_config, prazo_efetivo_de_resolucao

    t = _ticket_extensivel(sla_resolve_extension_total_min=minutos_uteis_de_dias(3))
    config = MagicMock()
    config.id = uuid.uuid4()
    config.response_time_minutes = 30
    config.resolve_time_minutes = 120

    apply_sla_config(t, config, t.created_at)

    assert t.sla_resolve_extension_total_min == minutos_uteis_de_dias(3)
    assert t.sla_resolve_effective_due_at == prazo_efetivo_de_resolucao(t)
    # E o efetivo continua depois da base nova, por causa da extensão.
    assert t.sla_resolve_effective_due_at > t.sla_resolve_due_at


@pytest.mark.asyncio
async def test_extensao_nao_limpa_violacao_existente(patch_redis):  # noqa: F811
    """Prorrogar um chamado que JÁ tem a marca não apaga a marca.

    O prazo novo passa a valer daqui para a frente; o que aconteceu, aconteceu.
    """
    t = _ticket_extensivel(sla_resolve_breach=True)

    resp, _, _ = await _estende(UserRole.admin, t)

    assert resp.status_code == 200
    assert t.sla_resolve_breach is True


# ══════════════════════════════════════════════════════════════
# REABERTURA — o ciclo novo não herda o bônus do anterior
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_reabrir_zera_a_extensao_do_ciclo_novo(patch_redis):  # noqa: F811
    """Passa pelo ENDPOINT de reabertura, e não por escrita à mão nos campos.

    A diferença não é estilo: a primeira versão deste arquivo provava o
    invariante da materialização simulando a reabertura — escrevendo os três
    campos direto — e por isso **a mutação que removia o zeramento do router
    passava verde**. Só o caminho de verdade prova o caminho de verdade.
    """
    from app.core.database import get_db
    from app.models.models import SLAConfig, SLALevel

    admin = _mock_user(UserRole.admin)
    t = _ticket_extensivel(
        status=TicketStatus.resolved,
        sla_resolve_extension_total_min=minutos_uteis_de_dias(5),
    )
    t.resolved_at = datetime.now(UTC) - timedelta(hours=1)
    t.closed_at = t.resolved_at
    t.reopen_count = 0

    config = MagicMock(spec=SLAConfig)
    config.id = uuid.uuid4()
    config.level = SLALevel.medium
    config.response_time_minutes = 120
    config.resolve_time_minutes = 720

    # A reabertura consulta a `SLAConfig` do nível depois de carregar o chamado.
    respostas = [t, config]
    indice = {"i": 0}

    async def _execute(*args, **kwargs):
        r = MagicMock()
        atual = respostas[min(indice["i"], len(respostas) - 1)]
        indice["i"] += 1
        r.scalar_one_or_none.return_value = atual
        r.scalar_one.return_value = 0
        r.scalars.return_value.all.return_value = []
        return r

    sessao = AsyncMock()
    sessao.execute = _execute
    sessao.add = MagicMock()
    sessao.commit = AsyncMock()
    sessao.refresh = AsyncMock()

    async def _gen():
        yield sessao

    app.dependency_overrides[get_db] = _gen
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{t.id}/reopen",
            json={"reason": "O problema voltou a acontecer hoje."},
        )

    assert resp.status_code == 200
    assert t.sla_resolve_extension_total_min == 0, "o ciclo novo herdou o bônus do anterior"
    # E a coluna materializada acompanha o prazo do ciclo novo.
    from app.utils.sla import prazo_efetivo_de_resolucao

    assert t.sla_resolve_effective_due_at == prazo_efetivo_de_resolucao(t)
