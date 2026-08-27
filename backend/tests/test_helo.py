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

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.models import TicketStatus
from app.services import helo
from app.services.helo import (
    abre_triagem,
    helo_pode_falar,
    monta_encerramento,
    monta_saudacao,
    quer_humano,
    responde_triagem,
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


# ── A triagem que ela abre ────────────────────────────────────


def _db_com_produto(nome="Phoebus"):
    """Sessão que responde ao SELECT do nome do produto e guarda o que foi add."""
    sessao = AsyncMock()
    resultado = MagicMock()
    resultado.scalar_one_or_none.return_value = nome
    sessao.execute = AsyncMock(return_value=resultado)
    sessao.add = MagicMock()
    return sessao


def _chamado(**kwargs):
    t = MagicMock()
    t.id = uuid.uuid4()
    t.product_id = uuid.uuid4()
    t.status = TicketStatus.open
    t.ai_enabled = True
    t.sla_first_response = None
    for k, v in kwargs.items():
        setattr(t, k, v)
    return t


def _equipamento(serial):
    e = MagicMock()
    e.serial_number = serial
    return e


@pytest.mark.asyncio
async def test_triagem_grava_a_fala_dela_e_move_para_em_andamento(helo_ligada):
    db = _db_com_produto()
    ticket = _chamado()
    cliente = _cliente()
    cliente.name = "Suelen Fernandes"

    falou = await abre_triagem(db, ticket, cliente, [_equipamento("WATFR01-73041")])

    assert falou is True
    (mensagem,) = [m for m in (c.args[0] for c in db.add.call_args_list)]
    assert mensagem.is_ai is True
    assert mensagem.is_system is False
    assert mensagem.sender_id is None, "remetente da Helô é nulo, não um usuário no banco"
    assert "Sou a Helô" in mensagem.content
    assert "WATFR01-73041" in mensagem.content
    assert ticket.status is TicketStatus.in_progress


@pytest.mark.asyncio
async def test_a_fala_dela_nao_carimba_primeira_resposta(helo_ligada):
    """
    O relógio do SLA continua correndo até um humano falar.

    Se a resposta dela zerasse o relógio, TODO chamado teria primeira resposta
    em segundos e o indicador viraria 100% permanente — mediria a velocidade de
    um robô, que é sempre a mesma, em vez do atendimento da equipe.
    """
    db = _db_com_produto()
    ticket = _chamado()

    await abre_triagem(db, ticket, _cliente(), [])

    assert ticket.sla_first_response is None


@pytest.mark.asyncio
async def test_com_a_helo_desligada_o_chamado_segue_aberto(helo_desligada):
    """Sem ela, tudo se comporta exatamente como antes de ela existir."""
    db = _db_com_produto()
    ticket = _chamado()

    falou = await abre_triagem(db, ticket, _cliente(), [])

    assert falou is False
    db.add.assert_not_called()
    assert ticket.status is TicketStatus.open


@pytest.mark.asyncio
async def test_chamado_com_a_ia_desligada_nao_recebe_saudacao(helo_ligada):
    """O interruptor do técnico vale desde a abertura."""
    db = _db_com_produto()
    ticket = _chamado(ai_enabled=False)

    assert await abre_triagem(db, ticket, _cliente(), []) is False
    assert ticket.status is TicketStatus.open


@pytest.mark.asyncio
async def test_chamado_sem_produto_nao_consulta_o_banco(helo_ligada):
    """
    Sem `product_id` não há nome de produto para buscar.

    Consultar assim mesmo devolveria None e a saudação sairia igual — o teste
    existe porque a consulta inútil só apareceria como lentidão, nunca como
    erro.
    """
    db = _db_com_produto()
    ticket = _chamado(product_id=None)

    await abre_triagem(db, ticket, _cliente(), [])

    db.execute.assert_not_called()


# ── O segundo turno: ela encerra e sai de cena ────────────────


def _db_com_falas(quantas):
    """Sessão que responde ao COUNT de mensagens dela."""
    sessao = AsyncMock()
    resultado = MagicMock()
    resultado.scalar_one.return_value = quantas
    sessao.execute = AsyncMock(return_value=resultado)
    sessao.add = MagicMock()
    return sessao


@pytest.mark.asyncio
async def test_resposta_do_cliente_encerra_a_triagem(helo_ligada):
    db = _db_com_falas(1)  # só a saudação até aqui
    ticket = _chamado()

    fala = await responde_triagem(db, ticket, _cliente(), "O aparelho não liga desde ontem")

    assert fala is not None
    assert fala.is_ai is True
    assert fala.sender_id is None
    assert "Registrei tudo aqui" in fala.content


@pytest.mark.asyncio
async def test_pedido_de_humano_escala_sem_insistir(helo_ligada):
    """
    Nem "posso ajudar com mais alguma coisa?", nem perguntar o motivo.

    Insistir aqui é o que transforma um atendimento ruim em reclamação — e o
    desenho chama o robô que não aceita "não" de pior que robô nenhum.
    """
    db = _db_com_falas(1)

    fala = await responde_triagem(db, _chamado(), _cliente(), "quero falar com um humano")

    assert fala is not None
    assert "passando seu chamado para um atendente" in fala.content
    assert "?" not in fala.content


@pytest.mark.asyncio
async def test_ela_nao_fala_uma_terceira_vez(helo_ligada):
    """
    Depois de encerrar, silêncio: o chamado é do humano.

    Sem este teto, cada mensagem nova do cliente ganharia outra despedida — a
    Helô se despedindo em loop enquanto ele tenta falar com alguém.
    """
    db = _db_com_falas(2)  # saudação + encerramento já ditos

    assert await responde_triagem(db, _chamado(), _cliente(), "e agora?") is None
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_ela_nao_entra_em_conversa_que_comecou_sem_ela(helo_ligada):
    """
    Chamado aberto antes dela existir, ou com ela desligada.

    Entrar agora seria se apresentar no meio de uma conversa em andamento — e o
    cliente veria a saudação depois de já ter falado com um técnico.
    """
    db = _db_com_falas(0)

    assert await responde_triagem(db, _chamado(), _cliente(), "oi") is None
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_com_a_ia_desligada_no_chamado_ela_nao_encerra(helo_ligada):
    """O técnico calou a IA no meio da triagem: ela não dá a última palavra."""
    db = _db_com_falas(1)

    assert await responde_triagem(db, _chamado(ai_enabled=False), _cliente(), "oi") is None
