"""
A marca de SLA violado passa a ser carimbada no instante da resolução.

O DEFEITO QUE ISTO FECHA
-----------------------
`check_breaches` só testa o prazo de resolução quando o chamado **não** está em
estado terminal, e os dois caminhos que resolvem já colocaram o status em
`resolved` quando o chamam. Chamado que passou do prazo e ficou **quieto** até
ser resolvido chegava com `sla_resolve_breach = False`, e o indicador agregado
— que conta a marca — o dava como cumprido.

POR QUE ISTO NÃO FOI UM PR DE DECISÃO
-------------------------------------
Foi levantado como proposta ao SGI, porque mudar o que o indicador conta é
mudar número divulgado ao cliente. A medição contra produção (13 resolvidos com
prazo em 6 meses, 4 violados) mostrou que os chamados que passariam a contar
são **os mesmos quatro que já contam**: cumprimento 69,2% antes e depois, queda
de 0,0 ponto.

Sem mudança de número, sobrou correção técnica. A ressalva continua valendo: a
base é pequena, e diferença zero significa que o caso **ainda não ocorreu** —
não que o defeito fosse inofensivo.
"""

import inspect
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.models.models import Ticket, TicketStatus
from app.utils.sla import marca_violacao_ao_resolver

AGORA = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


def _chamado(
    *,
    resolve_due: datetime | None = None,
    response_due: datetime | None = None,
    primeira_resposta: datetime | None = AGORA,
    marca_resolucao: bool = False,
    marca_resposta: bool = False,
    pausado_ms: int = 0,
    status: TicketStatus = TicketStatus.resolved,
) -> MagicMock:
    t = MagicMock(spec=Ticket)
    t.id = uuid.uuid4()
    t.status = status
    t.sla_resolve_due_at = resolve_due
    t.sla_response_due_at = response_due
    t.sla_first_response = primeira_resposta
    t.sla_resolve_breach = marca_resolucao
    t.sla_response_breach = marca_resposta
    t.sla_total_paused_ms = pausado_ms
    return t


# ═══════════════════════════════════════════════════════════════
# O caso que o defeito deixava passar
# ═══════════════════════════════════════════════════════════════


def test_o_chamado_vencido_e_calado_passa_a_ser_marcado():
    """
    **O teste que justifica o PR inteiro.**

    Prazo vencido há uma semana, marca em `False` porque ninguém escreveu no
    chamado desde o vencimento, e o status já é `resolved` — exatamente o
    estado em que os dois caminhos de resolução chamam o carimbo.
    """
    chamado = _chamado(resolve_due=AGORA - timedelta(days=7), marca_resolucao=False)

    marca_violacao_ao_resolver(chamado, AGORA)

    assert chamado.sla_resolve_breach is True


def test_o_status_ja_terminal_nao_impede_a_marca():
    """
    O `check_breaches` pula quando o status é terminal. Este não pula — é toda
    a diferença entre os dois, e o motivo de existir uma função separada.
    """
    from app.utils.sla import check_breaches

    vencido = AGORA - timedelta(days=3)

    pelo_check = _chamado(resolve_due=vencido, status=TicketStatus.resolved)
    check_breaches(pelo_check, AGORA)
    assert pelo_check.sla_resolve_breach is False, "o check_breaches segue pulando terminal"

    pelo_carimbo = _chamado(resolve_due=vencido, status=TicketStatus.resolved)
    marca_violacao_ao_resolver(pelo_carimbo, AGORA)
    assert pelo_carimbo.sla_resolve_breach is True


def test_resolvido_dentro_do_prazo_nao_ganha_marca():
    chamado = _chamado(resolve_due=AGORA + timedelta(hours=3))

    marca_violacao_ao_resolver(chamado, AGORA)

    assert chamado.sla_resolve_breach is False
    assert chamado.sla_response_breach is False


def test_a_resposta_vencida_e_nao_dada_tambem_e_marcada():
    chamado = _chamado(
        response_due=AGORA - timedelta(hours=5),
        primeira_resposta=None,
        resolve_due=AGORA + timedelta(hours=3),
    )

    marca_violacao_ao_resolver(chamado, AGORA)

    assert chamado.sla_response_breach is True
    assert chamado.sla_resolve_breach is False


# ═══════════════════════════════════════════════════════════════
# Os três limites que a proposta assumiu
# ═══════════════════════════════════════════════════════════════


def test_so_acrescenta_e_nunca_desmarca():
    """
    Limite declarado na proposta: marca já ligada por outro caminho fica ligada,
    mesmo quando a conta pela data discorda. Desmarcar é outra decisão.
    """
    chamado = _chamado(
        resolve_due=AGORA + timedelta(days=1),  # dentro do prazo
        marca_resolucao=True,  # mas já marcado
        marca_resposta=True,
    )

    marca_violacao_ao_resolver(chamado, AGORA)

    assert chamado.sla_resolve_breach is True
    assert chamado.sla_response_breach is True


def test_o_tempo_pausado_estica_o_prazo_aqui_tambem():
    """
    Mesma aritmética do `check_breaches` e da exigência de justificativa. Sem o
    deslocamento, chamado parado esperando o cliente seria marcado por atraso
    que não foi da equipe.
    """
    vencido_por_2h = AGORA - timedelta(hours=2)

    sem_pausa = _chamado(resolve_due=vencido_por_2h)
    com_pausa = _chamado(resolve_due=vencido_por_2h, pausado_ms=3 * 60 * 60 * 1000)

    marca_violacao_ao_resolver(sem_pausa, AGORA)
    marca_violacao_ao_resolver(com_pausa, AGORA)

    assert sem_pausa.sla_resolve_breach is True
    assert com_pausa.sla_resolve_breach is False


def test_chamado_sem_prazo_de_sla_nao_e_marcado():
    """Chamado anterior ao SLA tem os dois prazos nulos. Marcar seria inventar."""
    chamado = _chamado(resolve_due=None, response_due=None)

    marca_violacao_ao_resolver(chamado, AGORA)

    assert chamado.sla_resolve_breach is False
    assert chamado.sla_response_breach is False


# ═══════════════════════════════════════════════════════════════
# Estrutura: os dois caminhos, e a coerência com a justificativa
# ═══════════════════════════════════════════════════════════════


def test_os_dois_caminhos_que_resolvem_carimbam():
    """
    Há duas formas de resolver — `POST /tickets/{id}/resolve` e
    `PATCH /tickets/{id}/status` com `resolved`. Carimbar só num deles deixaria
    metade dos chamados fora da contagem, e a metade seria decidida por qual
    tela o técnico usou.
    """
    from app.routers import tickets

    fonte = inspect.getsource(tickets)
    chamadas = fonte.count("marca_violacao_ao_resolver(ticket, now)")

    assert chamadas == 2, f"esperava 2 caminhos carimbando, achei {chamadas}"


def test_a_marca_e_a_exigencia_de_justificativa_usam_a_mesma_conta():
    """
    O que garante que exigir o motivo e contar a violação nunca discordem: as
    duas perguntas passam por `violacao_ao_resolver`.

    Se uma delas passar a calcular por conta própria, volta a inconsistência
    que o levantamento registrou — chamado obrigado a justificar o atraso e
    ausente da contagem de violados.
    """
    from app.utils import sla

    corpo = inspect.getsource(sla.marca_violacao_ao_resolver)

    assert "violacao_ao_resolver(ticket, now)" in corpo
    # E não uma reimplementação da aritmética.
    assert "sla_resolve_due_at" not in corpo
    assert "timedelta" not in corpo


def test_o_check_breaches_nao_foi_afrouxado():
    """
    A guarda de terminal do `check_breaches` precisa continuar lá: ela existe
    para que chamado encerrado pare de acumular violação a cada escrita futura.
    Tirá-la resolveria este defeito criando um maior.
    """
    from app.utils import sla

    corpo = inspect.getsource(sla.check_breaches)

    assert "_TERMINAL_STATUSES" in corpo


@pytest.mark.parametrize("caminho", ["resolve", "status"])
def test_o_carimbo_vem_depois_do_guarda_de_justificativa(caminho):
    """
    Ordem: primeiro recusar quem não justificou, depois carimbar. Carimbar
    antes deixaria a marca gravada num pedido que foi rejeitado.
    """
    from app.routers import tickets

    fonte = inspect.getsource(tickets)
    trecho = (
        fonte[fonte.index("async def update_ticket_status(") :]
        if caminho == "status"
        else fonte[fonte.index("async def resolve_ticket(") :]
    )

    guarda = trecho.index("_justificativa_de_sla(ticket, now")
    carimbo = trecho.index("marca_violacao_ao_resolver(ticket, now)")

    assert guarda < carimbo
