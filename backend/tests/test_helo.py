"""
Os interruptores da Helô.

A conversa dela ainda não existe; o desligamento sim, e vem primeiro por
escolha: uma IA que fala com cliente sem ter como ser calada é a parte disto
que não tem volta.

As settings são trocadas por um objeto de mentira em vez de mexer no cache do
`get_settings`. A primeira versão deste arquivo limpava esse cache num
`autouse`, e derrubou dois testes de seeds que dependem do valor cacheado —
teste que estraga o vizinho é pior que teste que falta.
"""

from unittest.mock import MagicMock

import pytest

from app.services import helo
from app.services.helo import helo_pode_falar


@pytest.fixture
def helo_ligada(monkeypatch):
    monkeypatch.setattr(helo, "get_settings", lambda: MagicMock(helo_enabled=True))


@pytest.fixture
def helo_desligada(monkeypatch):
    monkeypatch.setattr(helo, "get_settings", lambda: MagicMock(helo_enabled=False))


def _ticket(ai_enabled=True):
    t = MagicMock()
    t.ai_enabled = ai_enabled
    return t


def _cliente(ai_enabled=True):
    u = MagicMock()
    u.ai_enabled = ai_enabled
    return u


def test_com_tudo_ligado_ela_fala(helo_ligada):
    assert helo_pode_falar(_ticket(), _cliente()) is True


def test_o_padrao_e_desligada():
    """
    Sem `HELO_ENABLED` no ambiente, ela não fala.

    O padrão é o oposto do `LLM_ENABLED`, e de propósito: ali a mudança
    silenciosa seria apagar a classificação automática; aqui seria a IA
    começar a FALAR COM O CLIENTE no deploy seguinte, sem ninguém ter pedido.

    Lê a configuração de verdade — é o único teste do arquivo que faz isso,
    porque o que ele afirma é justamente o valor declarado no `config.py`.
    """
    from app.core.config import Settings

    assert Settings(database_url="postgresql+asyncpg://x/y").helo_enabled is False


def test_tecnico_desliga_no_chamado(helo_ligada):
    """O interruptor de quem entra na conversa e quer a Helô calada dali em diante."""
    assert helo_pode_falar(_ticket(ai_enabled=False), _cliente()) is False


def test_cliente_que_nao_quer_robo(helo_ligada):
    """Vale para todos os chamados dele, sem depender de alguém lembrar."""
    assert helo_pode_falar(_ticket(), _cliente(ai_enabled=False)) is False


def test_chamado_ligado_nao_reativa_cliente_desligado(helo_ligada):
    """
    A conjunção é o ponto: não existe religar num nível mais específico.

    Se o `ai_enabled` do chamado vencesse o do cliente, o técnico reativaria a
    IA para quem pediu para não ser atendido por robô — e quem desligou
    precisaria vigiar os outros níveis para sempre.
    """
    assert helo_pode_falar(_ticket(ai_enabled=True), _cliente(ai_enabled=False)) is False


def test_flag_global_vence_os_dois(helo_desligada):
    """O interruptor de emergência não negocia com nível nenhum."""
    assert helo_pode_falar(_ticket(ai_enabled=True), _cliente(ai_enabled=True)) is False
