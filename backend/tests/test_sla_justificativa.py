"""
Justificativa obrigatória ao resolver chamado com SLA violado.

Resolver fora do prazo passa a exigir um motivo escrito. O motivo vai para o
chamado, para o histórico e para o relatório de SLA — que até aqui sabia
QUANTOS estouraram e nunca POR QUE.

O CASO QUE MOTIVA O DESENHO
---------------------------
A regra **não** pode se apoiar em `sla_resolve_breach`. Essa marca é gravada
por `check_breaches`, que pula o teste quando o chamado está em estado
terminal — e os dois caminhos que resolvem já colocaram o status em `resolved`
quando o chamam. Consequência: chamado que passou do prazo e ficou **quieto**
até ser resolvido chega com a marca em `False`.

São exatamente esses que a exigência existe para pegar: os que ninguém tocou.
Por isso a violação é calculada da DATA, e por isso o teste mais importante
deste arquivo é o do chamado vencido com a marca desligada.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.models.models import Ticket, TicketStatus
from app.routers.tickets import _justificativa_de_sla
from app.utils.sla import violacao_ao_resolver

_ROUTERS = Path(__file__).resolve().parent.parent / "app" / "routers" / "tickets.py"

AGORA = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def _chamado(
    *,
    resolve_due: datetime | None = None,
    response_due: datetime | None = None,
    primeira_resposta: datetime | None = AGORA,
    marca_resolucao: bool = False,
    marca_resposta: bool = False,
    pausado_ms: int = 0,
) -> MagicMock:
    t = MagicMock(spec=Ticket)
    t.status = TicketStatus.in_progress
    t.sla_resolve_due_at = resolve_due
    t.sla_response_due_at = response_due
    t.sla_first_response = primeira_resposta
    t.sla_resolve_breach = marca_resolucao
    t.sla_response_breach = marca_resposta
    t.sla_total_paused_ms = pausado_ms
    t.sla_breach_justification = None
    return t


# ═══════════════════════════════════════════════════════════════
# O cálculo da violação
# ═══════════════════════════════════════════════════════════════


def test_o_chamado_vencido_e_calado_e_detectado_mesmo_com_a_marca_desligada():
    """
    **O teste que justifica o desenho inteiro.**

    Prazo vencido há uma semana, `sla_resolve_breach` em `False` porque
    ninguém escreveu no chamado desde o vencimento. Ler a marca diria "não
    violou" e deixaria resolver sem justificativa — o furo exato que a regra
    existe para fechar.
    """
    chamado = _chamado(
        resolve_due=AGORA - timedelta(days=7),
        marca_resolucao=False,
    )

    _, resolucao_violada = violacao_ao_resolver(chamado, AGORA)

    assert resolucao_violada is True


def test_dentro_do_prazo_nao_e_violacao():
    chamado = _chamado(resolve_due=AGORA + timedelta(hours=3))

    assert violacao_ao_resolver(chamado, AGORA) == (False, False)


def test_a_marca_ja_ligada_e_respeitada():
    """Se outro caminho já concluiu que violou, não desfazemos a conclusão."""
    chamado = _chamado(resolve_due=None, marca_resolucao=True)

    _, resolucao_violada = violacao_ao_resolver(chamado, AGORA)

    assert resolucao_violada is True


def test_o_tempo_pausado_estica_o_prazo_tambem_aqui():
    """
    Mesma aritmética do `check_breaches`. Sem o deslocamento, chamado que ficou
    parado esperando o cliente apareceria violado por um tempo que não foi da
    equipe — e cobraria justificativa por atraso alheio.
    """
    vencido_por_2h = AGORA - timedelta(hours=2)

    sem_pausa = _chamado(resolve_due=vencido_por_2h)
    com_pausa = _chamado(resolve_due=vencido_por_2h, pausado_ms=3 * 60 * 60 * 1000)

    assert violacao_ao_resolver(sem_pausa, AGORA)[1] is True
    assert violacao_ao_resolver(com_pausa, AGORA)[1] is False


def test_a_resposta_ainda_nao_dada_e_vencida_conta_como_violacao():
    """
    Quando a própria nota de resolução é a primeira resposta e ela chega
    atrasada, quem marcaria é o `register_first_response` — que roda DEPOIS
    desta verificação. Ler a marca aqui veria o passado.
    """
    chamado = _chamado(
        response_due=AGORA - timedelta(hours=5),
        primeira_resposta=None,
        marca_resposta=False,
    )

    resposta_violada, _ = violacao_ao_resolver(chamado, AGORA)

    assert resposta_violada is True


def test_a_funcao_nao_escreve_nada_no_chamado():
    """
    Ela é consultada antes de qualquer mutação. Se escrevesse, a recusa
    deixaria rastro pela metade — chamado alterado e pedido rejeitado.
    """
    chamado = _chamado(resolve_due=AGORA - timedelta(days=1))
    antes = (
        chamado.sla_resolve_breach,
        chamado.sla_response_breach,
        chamado.sla_breach_justification,
    )

    violacao_ao_resolver(chamado, AGORA)

    assert (
        chamado.sla_resolve_breach,
        chamado.sla_response_breach,
        chamado.sla_breach_justification,
    ) == antes


# ═══════════════════════════════════════════════════════════════
# A recusa
# ═══════════════════════════════════════════════════════════════


def test_fora_do_prazo_sem_justificativa_e_recusado():
    chamado = _chamado(resolve_due=AGORA - timedelta(days=1))

    with pytest.raises(HTTPException) as erro:
        _justificativa_de_sla(chamado, AGORA, None)

    assert erro.value.status_code == 422
    assert "sla_breach_justification" in erro.value.detail


@pytest.mark.parametrize("vazia", ["", "   ", "\n\t "])
def test_justificativa_em_branco_conta_como_ausente(vazia):
    """Espaço em branco não é motivo. Sem isto, a exigência vira formalidade."""
    chamado = _chamado(resolve_due=AGORA - timedelta(days=1))

    with pytest.raises(HTTPException) as erro:
        _justificativa_de_sla(chamado, AGORA, vazia)

    assert erro.value.status_code == 422


def test_a_recusa_diz_qual_prazo_estourou():
    """
    Quem recebe o erro precisa saber o que aconteceu, não só que foi barrado.
    """
    so_resolucao = _chamado(resolve_due=AGORA - timedelta(days=1))
    with pytest.raises(HTTPException) as erro:
        _justificativa_de_sla(so_resolucao, AGORA, None)
    assert "resolução" in erro.value.detail
    assert "primeira resposta" not in erro.value.detail

    os_dois = _chamado(
        resolve_due=AGORA - timedelta(days=1),
        response_due=AGORA - timedelta(days=2),
        primeira_resposta=None,
    )
    with pytest.raises(HTTPException) as erro:
        _justificativa_de_sla(os_dois, AGORA, None)
    assert "primeira resposta" in erro.value.detail
    assert "resolução" in erro.value.detail


def test_fora_do_prazo_com_justificativa_passa_e_devolve_o_texto_limpo():
    chamado = _chamado(resolve_due=AGORA - timedelta(days=1))

    assert _justificativa_de_sla(chamado, AGORA, "  peça em falta no fornecedor  ") == (
        "peça em falta no fornecedor"
    )


def test_dentro_do_prazo_nao_exige_nada():
    chamado = _chamado(resolve_due=AGORA + timedelta(hours=3))

    assert _justificativa_de_sla(chamado, AGORA, None) is None


def test_justificativa_enviada_sem_violacao_e_guardada_mesmo_assim():
    """Quem explicou não perde o texto por ter entregado no prazo."""
    chamado = _chamado(resolve_due=AGORA + timedelta(hours=3))

    assert _justificativa_de_sla(chamado, AGORA, "atrasou por pouco") == "atrasou por pouco"


def test_chamado_sem_prazo_de_sla_nao_e_barrado():
    """
    Chamado antigo, anterior ao SLA, tem os dois prazos nulos. Barrar seria
    exigir justificativa por um prazo que nunca existiu.
    """
    chamado = _chamado(resolve_due=None, response_due=None)

    assert _justificativa_de_sla(chamado, AGORA, None) is None


# ═══════════════════════════════════════════════════════════════
# Os dois caminhos, e nenhum a menos
# ═══════════════════════════════════════════════════════════════


def test_os_dois_caminhos_que_resolvem_chamam_o_guarda():
    """
    Há DUAS formas de resolver: `POST /tickets/{id}/resolve` e
    `PATCH /tickets/{id}/status` com `resolved`. Uma regra em só um dos dois é
    um buraco — e o buraco seria invisível, porque a tela usa um caminho e a
    API pública aceita o outro.

    Este teste conta as chamadas ao guarda no roteador. Ao vê-lo falhar:
    caminho novo que resolve chamado precisa chamar `_justificativa_de_sla`
    antes de qualquer mutação.
    """
    fonte = _ROUTERS.read_text(encoding="utf-8")
    chamadas = re.findall(r"_justificativa_de_sla\(ticket, now,", fonte)

    assert len(chamadas) == 2, f"esperava 2 caminhos guardados, achei {len(chamadas)}"


def test_o_guarda_roda_antes_de_a_resolucao_mudar_o_status():
    """
    Ordem importa: recusar depois de mudar o status deixaria o chamado
    resolvido e o pedido rejeitado ao mesmo tempo.
    """
    fonte = _ROUTERS.read_text(encoding="utf-8")

    guarda = fonte.index("_justificativa_de_sla(ticket, now, body.sla_breach_justification)")
    mutacao = fonte.index("ticket.status = TicketStatus.resolved")

    assert guarda < mutacao, "o guarda precisa vir antes da mutação"


def test_a_justificativa_vai_para_o_historico():
    """
    O motivo precisa sobreviver a uma edição posterior do chamado. Só no campo
    ele seria sobrescrito sem deixar rastro.
    """
    fonte = _ROUTERS.read_text(encoding="utf-8")

    assert (
        fonte.count('"sla_breach_justification",\n            None,\n            justificativa,')
        == 2
    )


def test_o_relatorio_filtra_pela_justificativa_e_nao_pela_marca():
    """
    A marca `sla_resolve_breach` não é gravada ao resolver — ver o cabeçalho.
    Filtrar o relatório por ela deixaria de fora os chamados que venceram
    calados, que são os que mais interessam ao relatório.
    """
    dashboard = (
        Path(__file__).resolve().parent.parent / "app" / "routers" / "dashboard.py"
    ).read_text(encoding="utf-8")

    assert "Ticket.sla_breach_justification.is_not(None)" in dashboard


def test_o_item_do_relatorio_carrega_o_motivo_escrito():
    from app.schemas.dashboard import SlaJustificationItem

    item = SlaJustificationItem(
        ticket_id=str(uuid.uuid4()),
        protocol="HS-2026-0042",
        title="O aparelho travou",
        priority="high",
        resolved_at=AGORA,
        assignee_name="Fulano",
        justification="peça em falta no fornecedor",
    )

    assert item.justification == "peça em falta no fornecedor"
