"""
A cor da agenda vem do tipo, e de um lugar só.

Antes havia duas fontes para a mesma coisa, e elas já divergiam em produção:
o mapa por tipo no front só SUGERIA a cor na hora de criar, e o desenho lia a
coluna `color`, que guardava o que a pessoa tivesse clicado. Em 15/09/2026 os
seis eventos de produção tinham cinco cores diferentes das do tipo deles —
treinamento e reunião no mesmo azul, feriado em cinza.

Estes casos prendem o mapa. Os da API estão em `test_calendar.py`.
"""

import re

import pytest

from app.models.models import CalendarEventType
from app.utils.agenda import COR_POR_TIPO, cor_do_tipo


def test_todo_tipo_tem_cor():
    """Um sexto tipo que nasça sem cor reprova aqui, e não na tela.

    Sem este caso, o tipo novo chegaria à serialização e estouraria `KeyError`
    na primeira listagem que o contivesse — a agenda inteira fora do ar por um
    evento.
    """
    assert set(COR_POR_TIPO) == set(CalendarEventType)


def test_toda_cor_e_hexadecimal_de_seis_digitos():
    """O mesmo formato que a coluna `String(7)` e o schema antigo exigiam."""
    for tipo, cor in COR_POR_TIPO.items():
        assert re.fullmatch(r"#[0-9a-f]{6}", cor), f"{tipo.value}: {cor!r}"


def test_os_valores_sao_os_cinco_de_hoje():
    """Presos de propósito.

    Trocar a paleta é decisão de desenho, separada de trocar a FONTE da cor. Se
    alguém mudar um valor aqui, este caso vermelho é a pergunta "isto foi
    decidido?" chegando antes do deploy.
    """
    assert COR_POR_TIPO == {
        CalendarEventType.event: "#4f46e5",
        CalendarEventType.meeting: "#2563eb",
        CalendarEventType.training: "#047857",
        CalendarEventType.deadline: "#b45309",
        CalendarEventType.holiday: "#dc2626",
    }


def _luminancia(cor: str) -> float:
    """Luminância relativa da WCAG 2.1, do jeito que a norma define."""

    def canal(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    n = int(cor[1:], 16)
    return 0.2126 * canal(n >> 16 & 255) + 0.7152 * canal(n >> 8 & 255) + 0.0722 * canal(n & 255)


def _contraste(a: str, b: str) -> float:
    claro, escuro = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (claro + 0.05) / (escuro + 0.05)


def test_toda_cor_passa_o_contraste_com_o_texto_branco():
    """A régua que decidiu estes degraus, morando junto do mapa.

    A tela põe o título do evento por cima desta cor, em 10px — texto normal,
    que a WCAG cobra em 4,5:1. Os cinco valores anteriores eram o degrau 500 do
    Tailwind: quatro reprovavam, e o índigo reprovava com as duas cores de texto
    possíveis.

    Enquanto a cor era escolhida à mão, cada evento ruim era um evento ruim.
    Derivada do tipo, uma cor que reprova reprova TODOS os eventos daquele tipo,
    para sempre. Por isso a régua fica aqui: cor nova sem contraste deixa a
    suíte vermelha antes do deploy.

    O branco é a cor que o `readableTextColor` da tela escolhe para toda
    luminância abaixo de 0,45 — e as cinco estão bem abaixo disso.
    """
    reprovadas = {
        tipo.value: round(_contraste(cor, "#ffffff"), 2)
        for tipo, cor in COR_POR_TIPO.items()
        if _contraste(cor, "#ffffff") < 4.5
    }
    assert not reprovadas, f"texto branco ilegível sobre: {reprovadas}"


def test_a_regua_do_contraste_reprova_o_que_tem_de_reprovar():
    """Controle da régua acima: ela mede, ou só devolve verde?

    Sem este caso, um erro na conta — canal trocado, expoente errado — passaria
    despercebido, e `test_toda_cor_passa_o_contraste` viraria uma régua que
    aprova qualquer coisa. Os números são os medidos para os degraus 500 que
    saíram, e para o par clássico de preto no branco.
    """
    assert _contraste("#ffffff", "#000000") == pytest.approx(21.0, abs=0.01)
    assert _contraste("#f59e0b", "#ffffff") == pytest.approx(2.15, abs=0.01)
    assert _contraste("#6366f1", "#ffffff") == pytest.approx(4.47, abs=0.01)
    assert _contraste("#4f46e5", "#ffffff") == pytest.approx(6.29, abs=0.01)


def test_cor_do_tipo_le_o_mapa():
    for tipo in CalendarEventType:
        assert cor_do_tipo(tipo) == COR_POR_TIPO[tipo]


def test_os_tipos_tem_cores_distintas():
    """Duas cores iguais seria o defeito de produção reinstalado por constante.

    Em 15/09 havia treinamento e reunião no mesmo azul — divergência de dado.
    Se o mapa tivesse dois tipos com o mesmo valor, seria divergência de
    desenho, e nenhum outro caso notaria.
    """
    assert len(set(COR_POR_TIPO.values())) == len(COR_POR_TIPO)
