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
        CalendarEventType.event: "#6366f1",
        CalendarEventType.meeting: "#3b82f6",
        CalendarEventType.training: "#10b981",
        CalendarEventType.deadline: "#f59e0b",
        CalendarEventType.holiday: "#ef4444",
    }


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
