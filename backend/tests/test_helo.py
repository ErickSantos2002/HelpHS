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

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.services import helo
from app.services.helo import (
    helo_pode_falar,
    monta_encerramento,
    monta_saudacao,
    quer_humano,
)
from app.utils.sla import SP_TZ


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


# ── O que ela diz ─────────────────────────────────────────────


def test_saudacao_cita_o_aparelho_do_chamado():
    """
    O ganho que a Helô do WhatsApp nunca teve.

    Lá ela PEDIA modelo e número de série, porque não havia cadastro. Aqui o
    cliente já escolheu os dois no formulário — perguntar de novo faria o
    sistema parecer burro na primeira frase.
    """
    texto = monta_saudacao(
        cliente_nome="Suelen Fernandes",
        produto="Phoebus",
        series=["WATFR01-73041"],
    )

    assert texto.startswith("Olá, Suelen! Sou a Helô")
    assert "Phoebus (série WATFR01-73041)" in texto
    assert "1. O que exatamente está acontecendo com o aparelho?" in texto
    assert "3. Você já tentou alguma coisa?" in texto


def test_saudacao_com_varios_equipamentos():
    """Desde a v1.6.0 um chamado pode envolver mais de um aparelho."""
    texto = monta_saudacao(cliente_nome="Ana", produto="Titan", series=["SN-1", "SN-2"])

    assert "Titan (séries SN-1, SN-2)" in texto


def test_saudacao_sem_produto_vai_direto_as_perguntas():
    """
    Produto é opcional no chamado (`Ticket.product_id` é nullable).

    Inventar "seu equipamento" para não deixar buraco é pior do que ir direto
    ao ponto — e é o tipo de frase que denuncia o robô.
    """
    texto = monta_saudacao(cliente_nome="Ana", produto=None, series=[])

    assert "Vi que seu chamado" not in texto
    assert "Para adiantar o atendimento" in texto


def test_saudacao_sem_nome_nao_sauda_o_vazio():
    """`Olá, !` é pior do que não usar o nome."""
    texto = monta_saudacao(cliente_nome="   ", produto=None, series=[])

    assert texto.startswith("Olá! Sou a Helô")


def test_saudacao_nao_tem_markdown():
    """
    Sem asterisco, por regra do prompt.

    Um quarto do prompt da Helô do WhatsApp eram instruções sobre asterisco
    simples versus duplo. Aqui isso viraria asterisco literal na tela.
    """
    texto = monta_saudacao(cliente_nome="Ana", produto="Titan", series=["SN-1"])

    assert "*" not in texto
    assert "_" not in texto


def test_encerramento_dentro_do_horario():
    """Terça-feira, 10h: um atendente assume em seguida."""
    terca_10h = datetime(2026, 8, 25, 10, 0, tzinfo=SP_TZ)

    assert "já vai assumir" in monta_encerramento(terca_10h)


def test_encerramento_na_sexta_a_noite_diz_segunda():
    """
    O caso que o desenho manda não suavizar.

    Quem abre chamado na sexta à noite vai ler "segunda-feira", e não há frase
    bonita que conserte isso depois que o cliente esperou o fim de semana
    achando que era amanhã.
    """
    sexta_22h = datetime(2026, 8, 28, 22, 0, tzinfo=SP_TZ)

    texto = monta_encerramento(sexta_22h)

    assert "na segunda-feira" in texto.lower()
    assert "amanhã" not in texto.lower()


def test_encerramento_de_madrugada_diz_ainda_hoje():
    """Seis da manhã de uma terça é atendido na mesma terça."""
    terca_6h = datetime(2026, 8, 25, 6, 0, tzinfo=SP_TZ)

    assert "ainda hoje" in monta_encerramento(terca_6h).lower()


def test_encerramento_no_sabado_nao_promete_o_sabado():
    """O motor de SLA pula o fim de semana; a frase precisa acompanhar."""
    sabado = datetime(2026, 8, 29, 9, 0, tzinfo=SP_TZ)

    texto = monta_encerramento(sabado).lower()

    assert "na segunda-feira" in texto
    assert "sábado" not in texto


@pytest.mark.parametrize(
    "pedido",
    [
        "quero falar com um humano",
        "Me passa pro atendente por favor",
        "QUERO FALAR COM UMA PESSOA",
        "não quero robô",
        "prefiro atendimento humano, obrigado",
    ],
)
def test_pedido_de_humano_e_reconhecido(pedido):
    """
    Escalar de mais é barato; escalar de menos é o robô que não aceita "não".

    Por isso a lista é de trechos e a comparação ignora caixa: ninguém digita a
    frase que o programador imaginou.
    """
    assert quer_humano(pedido) is True


@pytest.mark.parametrize(
    "resposta",
    [
        "O aparelho não liga desde ontem",
        "Comecei a usar hoje e deu erro 3",
        "Já tentei trocar o cabo e não resolveu",
        "",
    ],
)
def test_resposta_normal_nao_escala(resposta):
    """A triagem não pode terminar por engano na primeira resposta útil."""
    assert quer_humano(resposta) is False
