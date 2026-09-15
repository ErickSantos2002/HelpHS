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


def _settings(modo, enabled=True):
    return MagicMock(helo_enabled=enabled, helo_modo=modo)


@pytest.fixture
def helo_ligada(monkeypatch):
    """
    Ligada e no modo COMPLETO — a Fase 2, que é o que a maioria deste arquivo testa.

    O modo vai explícito: um `MagicMock` sem `helo_modo` cai em triagem, que é
    o comportamento seguro, e os testes da Fase 2 passariam a afirmar silêncio
    ou encerramento pelo motivo errado.
    """
    monkeypatch.setattr(helo, "get_settings", lambda: _settings("completa"))


@pytest.fixture
def helo_em_triagem(monkeypatch):
    """Ligada e no modo de TRIAGEM — a recepcionista da Fase 1."""
    monkeypatch.setattr(helo, "get_settings", lambda: _settings("triagem"))


@pytest.fixture(params=["triagem", "completa"])
def em_cada_modo(request, monkeypatch):
    """Ligada, uma vez em cada modo — para o que tem de valer igual nos dois."""
    monkeypatch.setattr(helo, "get_settings", lambda: _settings(request.param))
    return request.param


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


def _ticket(ai_enabled=True, helo_saiu=False):
    t = MagicMock()
    t.ai_enabled = ai_enabled
    # Explícito pelo mesmo motivo do `assignee_id` mais abaixo: sem esta linha
    # o atributo nasce como filho auto-criado do MagicMock — truthy —, e a
    # guarda de "ela já saiu" calaria a Helô em TODO teste do arquivo.
    t.helo_saiu = helo_saiu
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


def test_depois_de_sair_ela_nao_volta(helo_ligada):
    """
    O campo novo cala a Helô sem ser um quarto interruptor.

    Os três níveis são de quem quer a IA fora; este é ela mesma tendo dito que
    acabou. Antes da separação, quem fazia esse trabalho era o `ai_enabled` —
    e junto com ele iam embora as ferramentas do técnico.
    """
    assert helo_pode_falar(_ticket(helo_saiu=True), _cliente()) is False


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
    # Mesmo motivo, e o mesmo perigo: truthy por acidente, ela nunca fala, e
    # dezenas de testes ficariam verdes afirmando silêncio pelo motivo errado.
    t.helo_saiu = False
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
async def test_escalar_encerra_a_conversa_dela(helo_ligada, modelo_diz):
    """
    A promessa que o desenho fazia desde a Fase 1 e o código não cumpria.

    Ali não fez falta: o teto de duas falas a calava de qualquer jeito. Com
    seis trocas de crédito, quem pediu um humano continuaria recebendo robô até
    o teto estourar — exatamente o que o desenho inteiro existe para evitar.
    """
    ticket = _chamado()
    modelo_diz("Vou passar para o time comercial.\nESCALAR: pergunta de garantia")

    await responde_triagem(_db_com_falas(1), ticket, _cliente(), "e a garantia?")

    assert ticket.helo_saiu is True


@pytest.mark.asyncio
async def test_escalada_do_modelo_nao_encosta_no_botao_do_tecnico(helo_ligada, modelo_diz):
    """
    A assimetria, e o lado que era defeito.

    `ai_enabled` fecha a sugestão de resposta e o resumo DO TÉCNICO. Desligá-lo
    porque o modelo desistiu tira a ferramenta dele justamente no chamado em
    que a IA já falhou — e sem ninguém ter pedido. Quem escreve aqui é gente,
    pela tela.
    """
    ticket = _chamado()
    modelo_diz("Vou passar para o time comercial.\nESCALAR: pergunta de garantia")

    await responde_triagem(_db_com_falas(1), ticket, _cliente(), "e a garantia?")

    assert ticket.ai_enabled is True


@pytest.mark.asyncio
async def test_o_pedido_de_humano_desliga_os_dois(helo_ligada):
    """
    A exceção, e ela é deliberada.

    Aqui quem quis sair da IA foi o CLIENTE, e a vontade dele não se aplica só
    à Helô: vale para a sugestão de resposta e para o resumo também. Sem este
    teste, a simetria com os outros três motivos pareceria esquecimento — e
    alguém "consertaria" tirando a linha.
    """
    ticket = _chamado()

    await responde_triagem(_db_com_falas(1), ticket, _cliente(), "quero falar com uma pessoa")

    assert ticket.helo_saiu is True
    assert ticket.ai_enabled is False


@pytest.mark.asyncio
async def test_a_saida_dela_fica_no_historico_com_o_motivo(helo_ligada, modelo_diz):
    """
    Sem isto o técnico abre o chamado, vê a IA calada, e não tem onde ler por quê.

    O botão da tela já grava histórico desde sempre; o caminho da Helô não
    gravava, e o campo mudava sozinho. O motivo que o modelo escreveu na linha
    `ESCALAR:` é o melhor texto possível para essa linha: quem o redigiu tinha
    lido a conversa.
    """
    db = _db_com_falas(1)
    modelo_diz("Isso precisa de um técnico.\nESCALAR: dano físico no visor")

    await responde_triagem(db, _chamado(), _cliente(), "a tela quebrou")

    historico = [c.args[0] for c in db.add.call_args_list if hasattr(c.args[0], "field")]
    (linha,) = [h for h in historico if h.field == "helo_saiu"]
    assert linha.user_id is None, "quem agiu foi o sistema, não uma pessoa"
    assert linha.new_value == "True"
    assert linha.comment == "dano físico no visor"


@pytest.mark.asyncio
async def test_o_pedido_de_humano_grava_as_duas_mudancas(helo_ligada):
    """Dois campos mudaram, e o histórico do chamado mostra os dois."""
    db = _db_com_falas(1)

    await responde_triagem(db, _chamado(), _cliente(), "quero falar com um humano")

    campos = {h.field for h in (c.args[0] for c in db.add.call_args_list) if hasattr(h, "field")}
    assert campos == {"helo_saiu", "ai_enabled"}


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
    assert ticket.helo_saiu is False, "ela respondeu; a conversa continua"


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
    assert ticket.helo_saiu is True
    assert ticket.ai_enabled is True, "a IA falhou; o técnico não perde as ferramentas por isso"


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
async def test_o_pedido_de_humano_viaja_com_o_proprio_motivo(helo_ligada):
    """
    O motivo não é enfeite: é o que separa a fila.

    "Tem gente esperando gente" é a única informação da escalada que muda a
    ordem de atendimento. As outras três saídas chegam à equipe como trabalho
    normal; esta chega como alguém do outro lado esperando uma pessoa.
    """
    fala = await responde_triagem(
        _db_com_falas(1), _chamado(), _cliente(), "quero falar com um humano"
    )

    assert fala.motivo == helo.MOTIVO_PEDIU_HUMANO


@pytest.mark.asyncio
async def test_o_teto_de_trocas_diz_que_foi_o_teto(helo_ligada):
    """Escalada por esgotamento não é pedido do cliente, e a equipe lê a diferença."""
    fala = await responde_triagem(_db_com_falas(TROCAS_MAXIMAS), _chamado(), _cliente(), "e agora?")

    assert fala.motivo == helo.MOTIVO_TETO_DE_TROCAS
    assert str(TROCAS_MAXIMAS) in fala.motivo, "o número sai da constante, não de uma cópia"


@pytest.mark.asyncio
async def test_a_ia_muda_nao_se_disfarca_de_pedido_do_cliente(helo_ligada, monkeypatch):
    """
    Chave vencida às três da manhã não pode chegar como "o cliente pediu gente".

    É o caso em que o motivo honesto vale mais: a equipe atende o chamado do
    mesmo jeito, e alguém consegue perceber que TODOS os chamados da noite
    escalaram pelo mesmo motivo — que é o sintoma de a IA estar fora do ar.
    """
    monkeypatch.setattr(helo, "responde_como_helo", AsyncMock(return_value=None))

    fala = await responde_triagem(_db_com_falas(1), _chamado(), _cliente(), "não liga")

    assert fala.motivo == helo.MOTIVO_IA_MUDA


@pytest.mark.asyncio
async def test_o_motivo_do_modelo_chega_inteiro_a_equipe(helo_ligada, modelo_diz):
    """
    O modelo escreve o motivo na linha `ESCALAR:`, e ele é bom.

    "dano físico no visor" dito por quem leu a conversa vale mais do que
    qualquer rótulo fixo que o backend soubesse inventar — e era informação que
    o `le_resposta` já extraía e o código jogava fora.
    """
    modelo_diz("Isso precisa de um técnico.\nESCALAR: dano físico no visor")

    fala = await responde_triagem(_db_com_falas(1), _chamado(), _cliente(), "a tela quebrou")

    assert fala.motivo == "dano físico no visor"


@pytest.mark.asyncio
async def test_escalada_sem_motivo_nao_manda_a_equipe_uma_frase_vazia(helo_ligada, modelo_diz):
    """
    O modelo pode escrever `ESCALAR:` e mais nada — e escreve.

    Sem o padrão, a notificação sairia com "o chamado está esperando
    atendimento: ." — que denuncia o defeito para a equipe inteira e não diz
    nada.
    """
    modelo_diz("Vou transferir.\nESCALAR:")

    fala = await responde_triagem(_db_com_falas(1), _chamado(), _cliente(), "e o preço?")

    assert fala.motivo == helo.MOTIVO_SEM_MOTIVO


@pytest.mark.asyncio
async def test_resposta_comum_nao_tem_motivo_nenhum(helo_ligada, modelo_diz):
    """`escalou` é derivado do motivo — não existe escalada sem por quê, nem o contrário."""
    modelo_diz("Segure o botão por três segundos.")

    fala = await responde_triagem(_db_com_falas(1), _chamado(), _cliente(), "não liga")

    assert fala.motivo is None
    assert fala.escalou is False


# ── Caminhos de falha ─────────────────────────────────────────
#
# A promessa do modulo, escrita como teste: nenhum chamado fica preso porque
# uma IA nao respondeu. Cada servico externo cai de um jeito diferente e todos
# terminam no mesmo lugar -- ela fala, escala, e a equipe e chamada com o
# motivo certo.


@pytest.mark.asyncio
async def test_pedido_de_humano_funciona_com_o_llm_fora_do_ar(helo_ligada, monkeypatch):
    """
    A regra mais importante do desenho não pode depender de serviço externo.

    Aqui o modelo não só está mudo: ele EXPLODE. Se a guarda de `quer_humano`
    estivesse depois da chamada — ou dentro do prompt, confiada ao modelo —,
    "quero falar com uma pessoa" viraria uma escalada genérica no melhor caso e
    um 500 no pior, justamente para o cliente que já disse que não quer robô.
    """

    async def _servico_fora(*_a, **_k):
        raise ConnectionError("DeepSeek fora do ar")

    monkeypatch.setattr(helo, "responde_como_helo", _servico_fora)
    monkeypatch.setattr(helo, "embute_um", _servico_fora)

    fala = await responde_triagem(
        _db_com_falas(1), _chamado(), _cliente(), "quero falar com um humano"
    )

    assert fala.motivo == helo.MOTIVO_PEDIU_HUMANO
    assert "passando seu chamado para um atendente" in fala.mensagem.content


@pytest.mark.asyncio
async def test_com_embedding_e_llm_fora_ela_escala_em_vez_de_prender(helo_ligada, monkeypatch):
    """
    Os dois serviços da Fase 2 fora ao mesmo tempo — o cenário de um deploy ruim.

    Sem embedding não há vetor, sem vetor não há busca, e sem modelo não há
    resposta. O que NÃO pode acontecer é o chamado ficar parado: o cliente
    escreveu e precisa de alguém, e a escalada é o que entrega isso.
    """
    monkeypatch.setattr(helo, "embute_um", AsyncMock(return_value=None))
    monkeypatch.setattr(helo, "responde_como_helo", AsyncMock(return_value=None))
    ticket = _chamado()

    fala = await responde_triagem(_db_com_falas(1), ticket, _cliente(), "não liga desde ontem")

    assert fala is not None
    assert fala.motivo == helo.MOTIVO_IA_MUDA
    assert ticket.helo_saiu is True
    helo.busca_trechos.assert_not_awaited()


@pytest.mark.asyncio
async def test_base_vazia_nao_escala_sozinha_e_isso_e_decisao(helo_ligada, modelo_diz):
    """
    `NADA ENCONTRADO` chega ao modelo, e é o PROMPT que manda escalar dali.

    O backend poderia escalar sozinho ao ver a base vazia, e não escala de
    propósito: "obrigada, resolveu!" e "era isso mesmo, valeu" também chegam com
    base vazia, e escalar ali mandaria para um humano uma conversa que acabou
    bem. O preço dessa escolha é que a regra "base vazia, única saída é
    escalar" vive no texto do prompt, não no código — por isso existe o teste
    que prende `NADA ENCONTRADO` dentro do `SISTEMA`, em `test_helo_prompt.py`.

    Este teste fixa a decisão: com base vazia, uma resposta comum do modelo
    PASSA. Se um dia o backend passar a escalar sozinho, ele quebra, e a
    conversa sobre o custo acontece de novo em vez de a mudança entrar calada.
    """
    espiao = modelo_diz("Que bom que resolveu! Precisando, é só chamar.")

    fala = await responde_triagem(_db_com_falas(3), _chamado(), _cliente(), "resolveu, obrigada!")

    assert fala.motivo is None
    assert "Que bom que resolveu" in fala.mensagem.content
    _sistema, contexto = espiao.await_args.args
    assert NADA_ENCONTRADO in contexto


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


# ── O modo: triagem até os manuais chegarem ───────────────────
#
# A Fase 2 dorme enquanto a base não tem manual; ela não morre. Os testes
# abaixo dividem-se em três: o que o modo É (configuração), o que vale IGUAL
# nos dois modos (as quatro guardas que não podem depender dele) e o que a
# triagem faz de diferente — a começar por não chamar coisa nenhuma.


def test_o_modo_padrao_e_triagem(monkeypatch):
    """
    Sem `HELO_MODO` no ambiente, ela é recepcionista.

    Lê a configuração de verdade, pelo mesmo motivo do teste do `HELO_ENABLED`:
    o que se afirma é o valor declarado no `config.py`. Por isso o ambiente e o
    `.env` de quem roda ficam de fora — um `HELO_MODO=completa` local derrubaria
    este teste sem o código ter mudado.
    """
    from app.core.config import Settings

    monkeypatch.delenv("HELO_MODO", raising=False)

    padrao = Settings(_env_file=None, database_url="postgresql+asyncpg://x/y").helo_modo
    assert padrao == "triagem"


def test_a_variavel_do_painel_se_chama_helo_modo(monkeypatch):
    """
    O nome que o Changelog manda pôr no painel é o nome que a configuração lê.

    Os outros testes passam o modo como argumento e não provam isto: um campo
    renomeado deixaria `HELO_MODO=completa` no painel sem efeito nenhum — e ela
    ficaria em triagem com todo mundo achando que acordou.
    """
    from app.core.config import Settings

    monkeypatch.setenv("HELO_MODO", "completa")

    lido = Settings(_env_file=None, database_url="postgresql+asyncpg://x/y").helo_modo
    assert lido == "completa"


@pytest.mark.parametrize("valor", ["completo", "fase2", "true", "triagem completa", "", "   "])
def test_modo_que_nao_se_reconhece_vira_triagem(valor):
    """
    O modo seguro é o que o sistema assume quando não sabe.

    `completo` está na lista de propósito: é o erro de digitação provável, e o
    que ele NÃO pode fazer é acordar a Fase 2 por aproximação.
    """
    from app.core.config import Settings

    assert Settings(database_url="postgresql+asyncpg://x/y", helo_modo=valor).helo_modo == "triagem"


@pytest.mark.parametrize("valor", ["completa", " COMPLETA ", "Completa"])
def test_completa_nao_depende_de_caixa_nem_de_espaco(valor):
    """Mesmo idioma do `APP_ENV`: a palavra é uma só, e a intenção não é ambígua."""
    from app.core.config import Settings

    assert (
        Settings(database_url="postgresql+asyncpg://x/y", helo_modo=valor).helo_modo == "completa"
    )


def test_modo_escrito_errado_deixa_rastro_no_log(monkeypatch):
    """
    Cair em triagem calado deixaria quem configurou achando que ela acordou.

    O aviso nomeia o valor que veio, porque é ele que alguém vai procurar no
    painel.
    """
    from app.core import config

    aviso = MagicMock()
    monkeypatch.setattr(config, "logger", aviso)

    config.Settings(database_url="postgresql+asyncpg://x/y", helo_modo="completo")

    aviso.warning.assert_called_once()
    assert "completo" in aviso.warning.call_args.args[0]


def test_modo_ausente_nao_e_erro_e_nao_avisa(monkeypatch):
    """Vazio é o estado padrão, e aviso que sai sempre deixa de ser lido."""
    from app.core import config

    aviso = MagicMock()
    monkeypatch.setattr(config, "logger", aviso)

    config.Settings(database_url="postgresql+asyncpg://x/y", helo_modo="")

    aviso.warning.assert_not_called()


def test_configuracao_sem_o_campo_tambem_e_triagem(monkeypatch):
    """
    A decisão final é do `helo.py`, e ela também não adivinha.

    Um objeto de configuração que nem tem o campo — o caso de todo `MagicMock`
    antigo desta suíte — não pode ser lido como "completa".
    """
    monkeypatch.setattr(helo, "get_settings", lambda: MagicMock(helo_enabled=True))

    assert helo.em_modo_completo() is False


# O que vale igual nos dois modos.


@pytest.mark.parametrize("desligado", ["chamado", "cliente", "saiu"])
@pytest.mark.asyncio
async def test_os_interruptores_calam_nos_dois_modos(em_cada_modo, desligado):
    """
    Nada religa num nível mais específico, e o modo não é um nível.

    O texto do cliente é o pedido de humano de propósito: é a entrada mais
    forte que existe, e nem ela passa por um interruptor desligado. E nenhuma
    consulta acontece — as chaves vêm antes de qualquer ida ao banco.
    """
    ticket = _chamado(ai_enabled=desligado != "chamado", helo_saiu=desligado == "saiu")
    cliente = _cliente(ai_enabled=desligado != "cliente")
    db = _db_com_falas(1)

    assert await responde_triagem(db, ticket, cliente, "quero falar com um humano") is None
    db.add.assert_not_called()
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_a_flag_global_cala_nos_dois_modos(em_cada_modo, monkeypatch):
    """Desligada é desligada em qualquer modo — na abertura e na resposta."""
    monkeypatch.setattr(helo, "get_settings", lambda: _settings(em_cada_modo, enabled=False))

    assert await abre_triagem(_db_com_produto(), _chamado(), _cliente(), []) is False
    db = _db_com_falas(1)
    assert await responde_triagem(db, _chamado(), _cliente(), "quero falar com um humano") is None
    db.add.assert_not_called()


@pytest.mark.parametrize("texto", ["quero falar com um humano", "O aparelho não liga desde ontem"])
@pytest.mark.parametrize("humano", ["equipe_falou", "tem_dono"])
@pytest.mark.asyncio
async def test_humano_na_conversa_cala_nos_dois_modos(em_cada_modo, humano, texto):
    """
    O chamado é de quem já está nele, e o modo não muda isso.

    Os dois textos são necessários. Com o pedido de humano, a guarda é testada
    contra a escalada; com a resposta comum, contra o encerramento na triagem —
    "um atendente já vai assumir", a mesma mentira da correção de 08/09 num
    chamado que já tem gente — e contra o modelo no modo completo. Só com o
    primeiro, uma guarda que rodasse apenas para pedido de humano passaria.
    """
    db = _db_com_falas(1, equipe_ja_falou=humano == "equipe_falou")
    ticket = _chamado(assignee_id=uuid.uuid4() if humano == "tem_dono" else None)

    assert await responde_triagem(db, ticket, _cliente(), texto) is None
    db.add.assert_not_called()
    assert ticket.helo_saiu is False


@pytest.mark.asyncio
async def test_pedido_de_humano_vem_antes_de_tudo_nos_dois_modos(em_cada_modo):
    """
    Na triagem, antes do encerramento; no modo completo, antes do embedding e do modelo.

    No completo, chegar ao modelo é falha deste teste pela fixture `sem_rede`;
    o embedding se afirma aqui, porque ele vem antes do modelo no turno.
    """
    fala = await responde_triagem(
        _db_com_falas(1), _chamado(), _cliente(), "quero falar com um humano"
    )

    assert fala.motivo == helo.MOTIVO_PEDIU_HUMANO
    assert "passando seu chamado para um atendente" in fala.mensagem.content
    assert "Registrei tudo aqui" not in fala.mensagem.content, "pediu gente, não é encerramento"
    helo.embute_um.assert_not_awaited()


@pytest.mark.asyncio
async def test_na_triagem_passado_o_teto_nem_o_pedido_de_humano_a_faz_falar(helo_em_triagem):
    """
    A borda que o teste acima não alcança, e ela é a da Fase 1.

    O teto vem antes do pedido de humano na ordem das guardas — nos dois modos.
    Com duas falas dela o chamado já passou pelo "um atendente já vai
    assumir", e uma terceira fala repetindo isso não acrescenta nada. Fica
    preso como decisão: se um dia o pedido de humano tiver de passar por cima
    do teto — para gravar a saída e avisar a equipe num chamado antigo —, este
    teste quebra e a conversa acontece, em vez de a ordem mudar calada.
    """
    ticket = _chamado()
    db = _db_com_falas(helo.FALAS_MAXIMAS_TRIAGEM)

    assert await responde_triagem(db, ticket, _cliente(), "quero falar com um humano") is None
    db.add.assert_not_called()
    assert ticket.ai_enabled is True


@pytest.mark.asyncio
async def test_no_modo_completo_o_pedido_de_humano_vence_o_teto(helo_ligada):
    """No turno em que o teto estouraria, quem pediu gente ainda chega como pedido de gente."""
    fala = await responde_triagem(
        _db_com_falas(TROCAS_MAXIMAS), _chamado(), _cliente(), "quero falar com um humano"
    )

    assert fala.motivo == helo.MOTIVO_PEDIU_HUMANO


@pytest.mark.asyncio
async def test_pedido_de_humano_grava_a_saida_e_derruba_o_botao_nos_dois_modos(em_cada_modo):
    """A exceção deliberada de 10/09 não é da Fase 2: vale para a recepcionista também."""
    ticket = _chamado()
    db = _db_com_falas(1)

    await responde_triagem(db, ticket, _cliente(), "quero falar com uma pessoa")

    assert ticket.helo_saiu is True
    assert ticket.ai_enabled is False
    campos = {h.field for h in (c.args[0] for c in db.add.call_args_list) if hasattr(h, "field")}
    assert campos == {"helo_saiu", "ai_enabled"}


@pytest.mark.asyncio
async def test_a_saudacao_sai_igual_nos_dois_modos(em_cada_modo):
    """A saudação nunca usou LLM; o modo não tem nada a dizer sobre ela."""
    db = _db_com_produto()
    cliente = _cliente()
    cliente.name = "Suelen Fernandes"

    assert await abre_triagem(db, _chamado(), cliente, [_equipamento("WATFR01-73041")]) is True
    (mensagem,) = [c.args[0] for c in db.add.call_args_list]
    assert mensagem.content == monta_saudacao(
        cliente_nome="Suelen Fernandes", produto="Phoebus", series=["WATFR01-73041"]
    )


# O que a triagem faz de diferente.


class _SextaAsDezDaNoite(datetime):
    """Relógio parado: o encerramento depende da hora, e o teste compara o texto inteiro."""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 8, 28, 22, 0, tzinfo=SP_TZ)


@pytest.mark.asyncio
async def test_na_triagem_a_resposta_do_cliente_encerra(helo_em_triagem, monkeypatch):
    """
    As três mensagens da Fase 1: a resposta às perguntas recebe o encerramento.

    O texto é comparado INTEIRO com `monta_encerramento` — é a função que ficou
    sem chamador na Fase 2 e volta a ter um aqui. Uma frase parecida montada em
    outro lugar passaria num `in`, e perderia o cálculo do dia útil.
    """
    monkeypatch.setattr(helo, "datetime", _SextaAsDezDaNoite)

    fala = await responde_triagem(
        _db_com_falas(1), _chamado(), _cliente(), "O aparelho não liga desde ontem"
    )

    assert fala.mensagem.content == monta_encerramento(_SextaAsDezDaNoite.now())
    assert "segunda-feira" in fala.mensagem.content
    assert fala.mensagem.is_ai is True
    assert fala.mensagem.sender_id is None


@pytest.mark.asyncio
async def test_o_encerramento_e_uma_saida_de_cena(helo_em_triagem):
    """
    Encerrar grava `helo_saiu` — e é isso que deixa o modo virar sem acordar ninguém.

    Sem o campo, o chamado triado continuaria com duas falas e crédito até
    sete no modo completo: no dia em que os manuais chegarem e o modo virar,
    ela voltaria a falar num chamado em que já disse "um atendente já vai
    assumir". O botão do técnico fica onde está — ninguém pediu para sair da IA.
    """
    ticket = _chamado()
    db = _db_com_falas(1)

    fala = await responde_triagem(db, ticket, _cliente(), "O aparelho não liga desde ontem")

    assert fala.motivo == helo.MOTIVO_TRIAGEM_CONCLUIDA
    assert ticket.helo_saiu is True
    assert ticket.ai_enabled is True
    historico = [c.args[0] for c in db.add.call_args_list if hasattr(c.args[0], "field")]
    (linha,) = historico
    assert linha.field == "helo_saiu"
    assert linha.comment == helo.MOTIVO_TRIAGEM_CONCLUIDA


@pytest.mark.asyncio
async def test_na_triagem_o_teto_e_de_duas_falas(helo_em_triagem):
    """
    O número da Fase 1: saudação e encerramento, e silêncio depois.

    Vale também para os chamados triados ANTES de o `helo_saiu` existir — duas
    falas e o campo em `False`. Com o teto do modo completo eles ganhariam
    cinco falas de crédito.
    """
    assert helo.FALAS_MAXIMAS_TRIAGEM == 2
    db = _db_com_falas(helo.FALAS_MAXIMAS_TRIAGEM)

    assert await responde_triagem(db, _chamado(), _cliente(), "alguém vai ver?") is None
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_na_triagem_nada_de_embedding_nem_modelo_e_chamado(helo_em_triagem, monkeypatch):
    """
    Não usar é diferente de usar e jogar fora, e só o primeiro é standby.

    Cada peça da Fase 2 vira um espião que NÃO levanta exceção: um espião que
    levantasse seria engolido por qualquer `try` no caminho, e o teste passaria
    com a chamada acontecendo. E as consultas ao banco são só as duas guardas
    — nenhum bloco de cadastro, nenhuma busca.
    """
    espioes = {
        nome: AsyncMock(return_value=None)
        for nome in (
            "embute_um",
            "busca_trechos",
            "responde_como_helo",
            "monta_cadastro",
            "monta_conversa",
        )
    }
    for nome, espiao in espioes.items():
        monkeypatch.setattr(helo, nome, espiao)
    db = _db_com_falas(1)

    fala = await responde_triagem(db, _chamado(), _cliente(), "O aparelho não liga desde ontem")

    assert fala.motivo == helo.MOTIVO_TRIAGEM_CONCLUIDA
    for nome, espiao in espioes.items():
        assert espiao.call_count == 0, f"{nome} foi chamado em modo triagem"
    consultas = [str(c.args[0]).upper() for c in db.execute.await_args_list]
    assert consultas, "as guardas consultam o banco; sem consulta nenhuma o teste não afirma nada"
    assert all("EXISTS" in q or "COUNT" in q for q in consultas), consultas


def _rede_armada(monkeypatch):
    """
    O cenário do dia em que alguém preenche a chave para testar outra coisa.

    As funções de verdade de embedding e de LLM voltam para o lugar, com URL e
    chave configuradas: se o turno chegar a elas, elas VÃO construir um cliente
    HTTP. O construtor é o espião, e levanta — os dois clientes engolem a
    exceção e devolvem None, que é o destino de sempre.
    """
    import httpx

    from app.services import helo_embedding, llm

    monkeypatch.setattr(helo, "embute_um", helo_embedding.embute_um)
    monkeypatch.setattr(helo, "responde_como_helo", llm.responde_como_helo)
    monkeypatch.setattr(
        helo_embedding,
        "get_settings",
        lambda: MagicMock(
            helo_embedding_url="http://helphs-embedding:8080", helo_embedding_timeout_seconds=1
        ),
    )
    monkeypatch.setattr(
        llm,
        "settings",
        MagicMock(
            llm_enabled=True,
            deepseek_api_key="sk-chave-de-teste",
            deepseek_base_url="https://api.deepseek.com/v1",
            deepseek_model="deepseek-chat",
            llm_request_timeout_seconds=1,
            llm_temperature=0.3,
        ),
    )
    rede = MagicMock(side_effect=RuntimeError("a rede foi tocada"))
    monkeypatch.setattr(httpx, "AsyncClient", rede)
    return rede


@pytest.mark.asyncio
async def test_com_chave_e_url_preenchidas_a_triagem_nao_toca_a_rede(helo_em_triagem, monkeypatch):
    """
    A segurança do standby não depende de faltar configuração.

    Chave da DeepSeek e URL do embedding preenchidas, e nenhum cliente HTTP é
    sequer construído. O teste abaixo, no modo completo, é a prova de que esta
    armadilha dispara quando deveria — sem ele, este passaria até com a rede
    armada errado.
    """
    rede = _rede_armada(monkeypatch)

    fala = await responde_triagem(
        _db_com_falas(1), _chamado(), _cliente(), "O aparelho não liga desde ontem"
    )

    assert fala.motivo == helo.MOTIVO_TRIAGEM_CONCLUIDA
    rede.assert_not_called()


@pytest.mark.asyncio
async def test_a_armadilha_da_rede_dispara_no_modo_completo(helo_ligada, monkeypatch):
    """O controle do teste acima: com o mesmo cenário, o modo completo vai à rede."""
    rede = _rede_armada(monkeypatch)

    fala = await responde_triagem(
        _db_com_falas(1), _chamado(), _cliente(), "O aparelho não liga desde ontem"
    )

    assert rede.call_count == 2, "uma vez para o embedding, uma para o modelo"
    assert fala.motivo == helo.MOTIVO_IA_MUDA


@pytest.mark.asyncio
async def test_virar_para_completa_nao_ressuscita_quem_ja_foi_triado(monkeypatch):
    """
    O dia do gatilho, encenado: triado em triagem, respondido depois em completa.

    Ela fica calada. Chegar ao modelo aqui é falha pela fixture `sem_rede`.
    """
    ticket = _chamado()
    monkeypatch.setattr(helo, "get_settings", lambda: _settings("triagem"))
    await responde_triagem(_db_com_falas(1), ticket, _cliente(), "não liga desde ontem")

    monkeypatch.setattr(helo, "get_settings", lambda: _settings("completa"))
    db = _db_com_falas(2)

    assert await responde_triagem(db, ticket, _cliente(), "e aí, alguém vai ver?") is None
    db.add.assert_not_called()
