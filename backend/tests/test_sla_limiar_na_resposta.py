"""
O `warning_threshold` chegando na resposta do chamado — Fase 2B.

Por que este arquivo existe
---------------------------
A barra de SLA do `TicketListPage` decidia cor com `pct >= 80` e `pct >= 60`
fixos no código, ao lado de um `warning_threshold` configurável por prioridade
que ninguém lia. A Fase 2A fez o e-mail respeitar o campo; sem esta fase, o
e-mail sairia em 70% enquanto a barra só ficaria vermelha em 80% — duas réguas
para a mesma pergunta.

O que este arquivo garante
--------------------------
Que o limiar que chega ao frontend é o da **prioridade atual** do chamado, e que
quem o decide é a MESMA função que o worker usa — não uma segunda cópia da regra.

Por que pela prioridade, e não por `sla_config_id`
--------------------------------------------------
O chamado tem `sla_config_id`, e seria tentador ler o limiar por ele. Mas essa
coluna é escrita SÓ por `apply_sla_config`, que a triagem chama apenas quando
existe config ativa e o chamado não está terminal. Então ela pode ficar
apontando para a config de uma prioridade ANTERIOR — e a barra mostraria o
limiar de um nível que o chamado já não tem, enquanto o worker (que resolve pela
prioridade atual) usaria outro. Resolver pela prioridade é o que mantém uma
resposta só.

Nada aqui envia e-mail, toca o worker ou altera cálculo de prazo.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from app.models.models import (
    SLAConfig,
    SLALevel,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    UserRole,
)
from app.routers.tickets import _serialize_ticket
from app.services.sla_alertas import threshold_da_prioridade
from app.utils.sla import add_business_minutes

_ABERTURA = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)  # terça, 09:00 BRT


def _config(nivel: SLALevel, limiar: int) -> SLAConfig:
    return SLAConfig(
        id=uuid.uuid4(),
        level=nivel,
        response_time_minutes=60,
        resolve_time_minutes=540,
        warning_threshold=limiar,
        is_active=True,
    )


def _chamado(prioridade: TicketPriority | None = TicketPriority.medium) -> Ticket:
    prazo = add_business_minutes(_ABERTURA, 540)
    return Ticket(
        id=uuid.uuid4(),
        protocol="HS-2026-0042",
        title="chamado sintético",
        description="corpo",
        priority=prioridade,
        category=TicketCategory.hardware,
        status=TicketStatus.in_progress,
        creator_id=uuid.uuid4(),
        sla_resolve_due_at=prazo if prioridade else None,
        sla_resolve_effective_due_at=prazo if prioridade else None,
        sla_total_paused_ms=0,
        sla_resolve_extension_total_min=0,
        sla_response_breach=False,
        sla_resolve_breach=False,
        auto_closed=False,
        reopen_count=0,
        ai_enabled=True,
        helo_saiu=False,
        created_at=_ABERTURA,
        updated_at=_ABERTURA,
    )


def _ator() -> MagicMock:
    ator = MagicMock()
    ator.role = UserRole.technician
    return ator


def _serializa(ticket: Ticket, configs: dict[SLALevel, SLAConfig]):
    return _serialize_ticket(ticket, _ABERTURA, actor=_ator(), limiares=configs)


# ══════════════════════════════════════════════════════════════
# 1. O campo na resposta
# ══════════════════════════════════════════════════════════════


def test_o_limiar_da_prioridade_atual_sai_na_resposta():
    ticket = _chamado(TicketPriority.medium)
    configs = {SLALevel.medium: _config(SLALevel.medium, 80)}

    assert _serializa(ticket, configs).sla_warning_threshold == 80


def test_cada_prioridade_recebe_o_proprio_limiar():
    configs = {
        SLALevel.critical: _config(SLALevel.critical, 50),
        SLALevel.low: _config(SLALevel.low, 95),
    }

    critico = _serializa(_chamado(TicketPriority.critical), configs)
    baixo = _serializa(_chamado(TicketPriority.low), configs)

    assert critico.sla_warning_threshold == 50
    assert baixo.sla_warning_threshold == 95


def test_o_limiar_nao_e_oitenta_fixo():
    """O defeito que esta fase fecha, em uma linha: se alguém devolver 80 no
    lugar do configurado, este teste cai."""
    ticket = _chamado(TicketPriority.medium)
    configs = {SLALevel.medium: _config(SLALevel.medium, 70)}

    assert _serializa(ticket, configs).sla_warning_threshold == 70


def test_chamado_sem_prioridade_devolve_nulo():
    """Chamado nasce sem prioridade — quem a define é a triagem. Sem ela não há
    nível por onde procurar limiar, e chutar um seria a divergência de novo."""
    ticket = _chamado(None)
    configs = {SLALevel.medium: _config(SLALevel.medium, 80)}

    assert _serializa(ticket, configs).sla_warning_threshold is None


def test_prioridade_sem_config_ativa_devolve_nulo():
    ticket = _chamado(TicketPriority.high)

    assert _serializa(ticket, {}).sla_warning_threshold is None


def test_o_limiar_e_int_no_dominio_percentual():
    ticket = _chamado(TicketPriority.medium)
    configs = {SLALevel.medium: _config(SLALevel.medium, 80)}

    limiar = _serializa(ticket, configs).sla_warning_threshold

    assert isinstance(limiar, int)
    assert 1 <= limiar <= 100


# ══════════════════════════════════════════════════════════════
# 2. Uma resposta só para "qual é o limiar deste chamado?"
# ══════════════════════════════════════════════════════════════


def test_a_resposta_usa_a_mesma_funcao_que_o_worker():
    """Não é uma segunda cópia da regra: é a mesma `threshold_da_prioridade`.

    Sem isto, a Fase 2B nasceria com o defeito que ela existe para corrigir —
    dois lugares decidindo o limiar, divergindo na primeira edição de um deles.
    """
    ticket = _chamado(TicketPriority.medium)
    configs = {SLALevel.medium: _config(SLALevel.medium, 65)}

    assert _serializa(ticket, configs).sla_warning_threshold == threshold_da_prioridade(
        ticket, configs
    )


def test_o_limiar_nao_vem_do_sla_config_id_desatualizado():
    """`sla_config_id` pode apontar para a config de uma prioridade ANTERIOR: ela
    é escrita só por `apply_sla_config`, que a triagem não chama quando não há
    config ativa para o nível novo nem quando o chamado está terminal.

    Aqui o chamado é `high` e carrega o `sla_config_id` de `medium`. A resposta
    tem de seguir a PRIORIDADE — e, sem config ativa para `high`, devolver nulo
    em vez do 80 do nível velho.
    """
    config_velha = _config(SLALevel.medium, 80)
    ticket = _chamado(TicketPriority.high)
    ticket.sla_config_id = config_velha.id

    assert _serializa(ticket, {SLALevel.medium: config_velha}).sla_warning_threshold is None


def test_o_limiar_nao_altera_os_outros_campos_de_sla():
    """Contraprova de escopo: esta fase não toca prazo, restante nem total."""
    ticket = _chamado(TicketPriority.medium)
    configs = {SLALevel.medium: _config(SLALevel.medium, 80)}

    com = _serializa(ticket, configs)
    sem = _serializa(ticket, {})

    assert com.sla_resolve_vence_em == sem.sla_resolve_vence_em
    assert com.sla_resolve_restante_min == sem.sla_resolve_restante_min
    assert com.sla_resolve_total_min == sem.sla_resolve_total_min
    assert com.sla_resolve_extension_total_min == sem.sla_resolve_extension_total_min


def test_o_parametro_e_obrigatorio():
    """Sem default, de propósito — mesma decisão do `actor` na Fase SEC.

    Com `limiares=None` por omissão, os treze pontos que serializam chamado
    devolveriam `null` em silêncio, e a barra cairia no fallback sem ninguém
    perceber. A lição é de 24/09: um default escondeu um call site sem ator, e só
    o AST na árvore mesclada pegou.
    """
    ticket = _chamado()

    with pytest.raises(TypeError):
        _serialize_ticket(ticket, _ABERTURA, actor=_ator())  # type: ignore[call-arg]
