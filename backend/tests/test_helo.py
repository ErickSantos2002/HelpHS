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
from sqlalchemy.exc import OperationalError

from app.models.models import TicketStatus
from app.services import helo
from app.services.helo import (
    FALAS_MAXIMAS,
    TROCAS_MAXIMAS,
    abre_triagem,
    helo_pode_falar,
    monta_encerramento,
    monta_saudacao,
    quer_humano,
    responde_triagem,
)
from app.services.helo_base import NADA_ENCONTRADO
from app.utils.sla import SP_TZ


@pytest.fixture
def helo_ligada(monkeypatch):
    monkeypatch.setattr(helo, "get_settings", lambda: MagicMock(helo_enabled=True))


@pytest.fixture
def helo_desligada(monkeypatch):
    monkeypatch.setattr(helo, "get_settings", lambda: MagicMock(helo_enabled=False))


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch):
    """
    A rede fica cortada no arquivo inteiro, e o modelo nasce mudo.

    Duas coisas de uma vez. A primeira é impedir que a suíte saia chamando a
    DeepSeek de verdade: bastaria uma guarda a menos no código para isso
    acontecer, e o sintoma seria lentidão, não erro. A segunda é dar nome à
    falha — quem chegar ao modelo sem ter dito o que ele responde lê a frase
    abaixo, e não um timeout.

    Isso também é o que faz "ela NÃO chamou o modelo" ser afirmado de graça em
    todo teste que não pede a fixture `modelo_diz`.

    Os três blocos de contexto saem daqui prontos. O que estes testes decidem é
    POR QUAL SAÍDA ela vai; o que vai escrito dentro dos blocos se prova onde
    pode ser provado — contra Postgres, em `test_helo_postgres.py`.
    """

    async def _nao_devia_chegar_aqui(*_args, **_kwargs):
        raise AssertionError(
            "o teste chegou ao modelo sem dizer o que ele responde: use a fixture modelo_diz"
        )

    monkeypatch.setattr(helo, "responde_como_helo", _nao_devia_chegar_aqui)
    monkeypatch.setattr(helo, "embute_um", AsyncMock(return_value=[0.1] * 8))
    monkeypatch.setattr(helo, "busca_trechos", AsyncMock(return_value=[]))
    monkeypatch.setattr(helo, "monta_cadastro", AsyncMock(return_value="[CADASTRO]"))
    monkeypatch.setattr(helo, "monta_conversa", AsyncMock(return_value="[CONVERSA]"))


@pytest.fixture
def modelo_diz(monkeypatch):
    """
    Põe uma fala na boca do modelo e devolve o espião da chamada.

    O espião importa tanto quanto a fala: metade do desenho da Fase 2 é sobre
    QUANDO não chamar o LLM, e sobre o que exatamente é entregue a ele.
    """

    def _diz(texto):
        espiao = AsyncMock(return_value=texto)
        monkeypatch.setattr(helo, "responde_como_helo", espiao)
        return espiao

    return _diz


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
    # Explícito, e não deixado por conta do MagicMock: sem esta linha o
    # atributo nasce como um filho auto-criado — truthy e diferente de None.
    # Todo cenário de "chamado sem dono" ficaria verde por acidente, e trocar
    # `is None` por `is not None` no código não derrubaria teste nenhum.
    t.assignee_id = None
    t.sla_first_response = None
    t.sla_response_due_at = None
    t.sla_response_breach = False
    t.sla_total_paused_ms = 0
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
async def test_a_fala_dela_carimba_primeira_resposta(helo_ligada):
    """
    Decisão do cliente em 28/08, revertendo o desenho original.

    O argumento dele: quando ela responde, o atendimento começou de fato, e
    mostrar "aguardando primeira resposta" a quem acabou de ser respondido é o
    indicador mentindo para o outro lado.

    Substitui `test_a_fala_dela_nao_carimba_primeira_resposta`, que prendia a
    regra oposta. O preço da troca está escrito em `register_first_response`:
    com a Helô ligada este indicador vira ~100% permanente.
    """
    db = _db_com_produto()
    ticket = _chamado()

    await abre_triagem(db, ticket, _cliente(), [])

    assert ticket.sla_first_response is not None


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


def _db_com_falas(quantas, equipe_ja_falou=False):
    """
    Sessão que responde às duas consultas de `responde_triagem`.

    Despacha pela CONSULTA, e não pela ordem das chamadas: a ordem é detalhe
    de implementação — hoje o EXISTS da equipe vem antes do COUNT, e ela muda
    no dia em que alguém inverter as guardas. Um mock preso à ordem quebraria
    ali sem que nada tivesse quebrado de verdade.
    """
    sessao = AsyncMock()

    def responde(consulta, *args, **kwargs):
        resultado = MagicMock()
        if "EXISTS" in str(consulta).upper():
            resultado.scalar.return_value = equipe_ja_falou
        else:
            resultado.scalar_one.return_value = quantas
        return resultado

    sessao.execute = AsyncMock(side_effect=responde)
    sessao.add = MagicMock()
    # `begin_nested` do AsyncSession é SÍNCRONO e devolve um gerenciador de
    # contexto assíncrono. No AsyncMock todo método vira corrotina, e o
    # `async with` do SAVEPOINT quebraria por defeito do mock, não do código.
    sessao.begin_nested = MagicMock(return_value=_SavepointDeMentira())
    return sessao


class _SavepointDeMentira:
    """O bastante para o `async with`: quem prova o SAVEPOINT de verdade é o Postgres."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_excecao):
        return False


@pytest.mark.asyncio
async def test_a_resposta_do_cliente_agora_e_respondida(helo_ligada, modelo_diz):
    """
    A mudança central da Fase 2: a resposta do cliente deixou de ENCERRAR.

    Na Fase 1 ela agradecia e saía — a triagem tinha acabado. Agora ela busca
    na base e responde o que está documentado. O encerramento fixo virou uma
    das saídas possíveis, não a única.
    """
    modelo_diz("1. Segure o botão por três segundos.\n\nFonte: Manual do Titan, seção 6.")
    db = _db_com_falas(1)  # só a saudação até aqui

    fala = await responde_triagem(db, _chamado(), _cliente(), "O aparelho não liga desde ontem")

    assert fala is not None
    assert fala.escalou is False
    assert fala.mensagem.is_ai is True
    assert fala.mensagem.sender_id is None
    assert "Segure o botão" in fala.mensagem.content
    assert "Fonte:" in fala.mensagem.content, "a resposta cita, e a citação viaja para o cliente"


@pytest.mark.asyncio
async def test_pedido_de_humano_escala_sem_insistir(helo_ligada):
    """
    Nem "posso ajudar com mais alguma coisa?", nem perguntar o motivo.

    Insistir aqui é o que transforma um atendimento ruim em reclamação — e o
    desenho chama o robô que não aceita "não" de pior que robô nenhum.

    E escala SEM chamar o modelo. A regra mais importante do desenho do ponto
    de vista de experiência não pode depender de um serviço externo estar de
    pé; quem afirma isso aqui é a fixture `sem_rede`, que faz de chegar ao LLM
    uma falha deste teste.
    """
    db = _db_com_falas(1)

    fala = await responde_triagem(db, _chamado(), _cliente(), "quero falar com um humano")

    assert fala is not None
    assert fala.escalou is True, "é o que faz a equipe ser chamada com o aviso certo"
    assert "passando seu chamado para um atendente" in fala.mensagem.content
    assert "?" not in fala.mensagem.content


@pytest.mark.asyncio
async def test_no_teto_de_trocas_ela_escala_em_vez_de_continuar(helo_ligada):
    """
    O teto deixou de ser de FALAS e virou de TROCAS — e ele escala, não emudece.

    Na Fase 1 eram duas falas e silêncio depois, porque a conversa não existia.
    Agora o prompt promete "se a conversa passar de seis trocas sem sair do
    lugar: escale", e o teto é a rede embaixo disso: modelo que não obedece é o
    caso comum, não a exceção.
    """
    db = _db_com_falas(TROCAS_MAXIMAS)

    fala = await responde_triagem(db, _chamado(), _cliente(), "e agora?")

    assert fala is not None
    assert fala.escalou is True
    assert "passando seu chamado para um atendente" in fala.mensagem.content


@pytest.mark.asyncio
async def test_depois_do_teto_ela_emudece(helo_ligada):
    """
    Passado o teto, silêncio: a despedida já foi dita e o chamado é do humano.

    Sem isto, cada mensagem nova ganharia outra despedida — a Helô se
    despedindo em loop enquanto o cliente tenta falar com alguém.
    """
    db = _db_com_falas(FALAS_MAXIMAS)

    assert await responde_triagem(db, _chamado(), _cliente(), "e agora?") is None
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_uma_troca_antes_do_teto_ela_ainda_tenta(helo_ligada, modelo_diz):
    """
    A borda de baixo do teto, e o motivo de ela existir como teste.

    Sem isto, adiantar o teto em uma troca não derrubaria nada: ela se
    despediria com crédito na mão, e o defeito apareceria como "a Helô desiste
    cedo demais" — reclamação de percepção, das mais difíceis de rastrear.
    """
    modelo_diz("Confere se o cabo está firme e me conta.")
    db = _db_com_falas(TROCAS_MAXIMAS - 1)

    fala = await responde_triagem(db, _chamado(), _cliente(), "continua igual")

    assert fala is not None
    assert fala.escalou is False


@pytest.mark.asyncio
async def test_a_linha_de_escalada_nao_vai_para_o_cliente(helo_ligada, modelo_diz):
    """
    `ESCALAR:` é para o sistema, e o cliente não vê a mecânica.

    Deixar a linha passar mostraria o funcionamento interno na tela de quem
    está com um aparelho quebrado na mão — e ainda pareceria erro do sistema
    justo no momento em que ele foi transferido.
    """
    modelo_diz("Isso precisa de um técnico olhando.\nESCALAR: dano físico no visor")

    fala = await responde_triagem(_db_com_falas(1), _chamado(), _cliente(), "a tela quebrou")

    assert fala.escalou is True
    assert "Isso precisa de um técnico olhando." in fala.mensagem.content
    assert "ESCALAR" not in fala.mensagem.content


@pytest.mark.asyncio
async def test_escalar_desliga_a_ia_no_chamado(helo_ligada, modelo_diz):
    """
    A promessa que o desenho fazia desde a Fase 1 e o código não cumpria.

    Ali não fez falta: o teto de duas falas a calava de qualquer jeito. Com
    seis trocas de crédito, quem pediu um humano continuaria recebendo robô até
    o teto estourar — exatamente o que o desenho inteiro existe para evitar.
    """
    ticket = _chamado()
    modelo_diz("Vou passar para o time comercial.\nESCALAR: pergunta de garantia")

    await responde_triagem(_db_com_falas(1), ticket, _cliente(), "e a garantia?")

    assert ticket.ai_enabled is False


@pytest.mark.asyncio
async def test_resposta_comum_nao_desliga_a_ia(helo_ligada, modelo_diz):
    """
    A guarda oposta, e a mais cara das duas.

    Desligar por engano cala a Helô naquele chamado para sempre: `ai_enabled`
    não volta sozinho, e ninguém vai à tela religar o que não sabe que
    desligou.
    """
    ticket = _chamado()
    modelo_diz("Segure o botão por três segundos.")

    await responde_triagem(_db_com_falas(1), ticket, _cliente(), "não liga")

    assert ticket.ai_enabled is True


@pytest.mark.parametrize("bruto", [None, "", "   \n  "])
@pytest.mark.asyncio
async def test_modelo_que_nao_responde_escala(helo_ligada, monkeypatch, bruto):
    """
    Timeout, chave inválida, serviço fora, resposta vazia — indistinguíveis daqui.

    O que não pode acontecer é o chamado ficar parado porque uma IA não
    respondeu. O cliente não precisa saber que ela caiu; ele precisa de um
    humano, e é isso que a escalada entrega.
    """
    monkeypatch.setattr(helo, "responde_como_helo", AsyncMock(return_value=bruto))
    ticket = _chamado()

    fala = await responde_triagem(_db_com_falas(1), ticket, _cliente(), "não liga")

    assert fala is not None
    assert fala.escalou is True
    assert "passando seu chamado para um atendente" in fala.mensagem.content
    assert ticket.ai_enabled is False


@pytest.mark.asyncio
async def test_modelo_que_so_pede_escalada_ainda_se_despede(helo_ligada, modelo_diz):
    """
    A linha some do texto; se ela era o texto inteiro, sobra vazio.

    Gravar mensagem vazia seria a Helô publicando um balão em branco na tela do
    cliente no exato instante em que ele foi transferido.
    """
    modelo_diz("ESCALAR: assunto fora da base técnica")

    fala = await responde_triagem(_db_com_falas(1), _chamado(), _cliente(), "quanto custa?")

    assert fala.escalou is True
    assert "passando seu chamado para um atendente" in fala.mensagem.content


@pytest.mark.asyncio
async def test_sem_embedding_ela_nao_busca_e_o_modelo_fica_sabendo(
    helo_ligada, monkeypatch, modelo_diz
):
    """
    Serviço de embedding fora: a busca nem é tentada, e a base vai vazia.

    Buscar com vetor nulo devolveria os quatro trechos mais próximos de coisa
    nenhuma — pior do que não buscar, porque o modelo os leria como
    pertinentes. Ele recebe NADA ENCONTRADO, e o prompt diz que dali a única
    saída é escalar.
    """
    monkeypatch.setattr(helo, "embute_um", AsyncMock(return_value=None))
    espiao = modelo_diz("Vou chamar um colega.\nESCALAR: sem base técnica")

    await responde_triagem(_db_com_falas(1), _chamado(), _cliente(), "não liga")

    helo.busca_trechos.assert_not_awaited()
    _sistema, contexto = espiao.await_args.args
    assert NADA_ENCONTRADO in contexto


@pytest.mark.asyncio
async def test_busca_quebrada_nao_impede_a_resposta(helo_ligada, monkeypatch, modelo_diz):
    """
    Extensão ausente, tabela não migrada, índice corrompido: base vazia.

    O que ela NÃO pode fazer é deixar de responder. A consequência mais grave
    dessa falha — a mensagem do próprio cliente ir junto — só aparece contra
    banco de verdade, e está em `test_helo_postgres.py`; aqui se afirma a parte
    barata: a exceção não sobe e o modelo é chamado sem base.
    """
    monkeypatch.setattr(
        helo,
        "busca_trechos",
        AsyncMock(side_effect=OperationalError("SELECT ...", {}, Exception("sem extensão"))),
    )
    espiao = modelo_diz("Vou chamar um colega.\nESCALAR: sem base técnica")

    fala = await responde_triagem(_db_com_falas(1), _chamado(), _cliente(), "não liga")

    assert fala is not None
    assert fala.escalou is True
    _sistema, contexto = espiao.await_args.args
    assert NADA_ENCONTRADO in contexto


@pytest.mark.asyncio
async def test_o_modelo_recebe_o_prompt_de_sistema_e_os_tres_blocos(helo_ligada, modelo_diz):
    """
    A fiação, afirmada uma vez: as regras como sistema, o caso como contexto.

    Trocar os dois argumentos de lugar mandaria o cadastro do cliente no lugar
    das regras — e o modelo responderia alguma coisa assim mesmo, sem erro
    nenhum no log. É o tipo de defeito que só aparece como "ela anda
    inventando procedimento", semanas depois.
    """
    espiao = modelo_diz("Testa aí e me conta se resolveu.")

    await responde_triagem(_db_com_falas(1), _chamado(), _cliente(), "não liga")

    sistema, contexto = espiao.await_args.args
    assert "Você é a Helô" in sistema
    assert "[CADASTRO]" in contexto
    assert "[BASE TÉCNICA]" in contexto
    assert "[CONVERSA]" in contexto


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


# ── Quando um humano já está na conversa ──────────────────────


@pytest.mark.asyncio
async def test_tecnico_falou_e_o_cliente_respondeu_ela_fica_calada(helo_ligada):
    """
    O caso que motivou a correção, hora a hora.

    Cliente abre às 3h e ela saúda (1ª fala). Técnico assume às 8h e escreve.
    Cliente responde às 9h. Pela contagem ela ainda tem uma fala de crédito —
    e gastaria dizendo "um atendente já vai assumir seu chamado" num chamado
    que já está sendo atendido.
    """
    db = _db_com_falas(1, equipe_ja_falou=True)

    fala = await responde_triagem(db, _chamado(), _cliente(), "consegui o número de série")

    assert fala is None
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_ela_cala_em_chamado_que_ja_tem_dono(helo_ligada):
    """
    Assumir não grava mensagem nenhuma no chat.

    O técnico que pega o chamado às 8h e ainda não digitou não aparece no
    histórico — só em `TicketHistory`. Sem olhar o responsável ela anunciaria
    que "um atendente já vai assumir" um chamado que já tem nome.
    """
    db = _db_com_falas(1, equipe_ja_falou=False)

    fala = await responde_triagem(
        db, _chamado(assignee_id=uuid.uuid4()), _cliente(), "o aparelho apitou"
    )

    assert fala is None
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_chamado_com_dono_nem_pergunta_pela_equipe(helo_ligada):
    """
    O responsável está na memória; a fala da equipe custa uma consulta.

    Perguntar as duas coisas sempre seria uma consulta a cada mensagem de
    cliente — e na Fase 2, em que ela fala muitas vezes por chamado, isso vira
    consulta por turno de conversa.
    """
    db = _db_com_falas(1)

    await responde_triagem(db, _chamado(assignee_id=uuid.uuid4()), _cliente(), "oi")

    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_sem_dono_e_sem_a_equipe_ela_ainda_responde(helo_ligada, modelo_diz):
    """
    A guarda oposta: calar de mais é tão defeito quanto falar de mais.

    Chamado triado de madrugada, sem responsável e sem ninguém da equipe tendo
    falado, é exatamente o caso em que ela deve atender.
    """
    modelo_diz("Vamos conferir a bateria primeiro.")
    db = _db_com_falas(1, equipe_ja_falou=False)

    fala = await responde_triagem(db, _chamado(), _cliente(), "não liga desde ontem")

    assert fala is not None
    assert "bateria" in fala.mensagem.content


@pytest.mark.asyncio
async def test_nem_o_pedido_de_humano_fala_por_cima_do_tecnico(helo_ligada):
    """
    Pedir uma pessoa quando a pessoa já está ali não escala nada.

    "Já estou passando seu chamado para um atendente" para quem acabou de ser
    respondido por um atendente é a mesma mentira, com a urgência trocada.
    """
    db = _db_com_falas(1, equipe_ja_falou=True)

    assert await responde_triagem(db, _chamado(), _cliente(), "quero falar com um humano") is None


@pytest.mark.asyncio
async def test_com_a_ia_desligada_no_chamado_ela_nao_encerra(helo_ligada):
    """O técnico calou a IA no meio da triagem: ela não dá a última palavra."""
    db = _db_com_falas(1)

    assert await responde_triagem(db, _chamado(ai_enabled=False), _cliente(), "oi") is None
