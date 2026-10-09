"""
A leitura do que o modelo devolveu, e o contrato escondido no prompt.

`le_resposta` é a fronteira entre o que é para o cliente e o que é para o
sistema. Ela erra de dois jeitos, e os dois aparecem do outro lado: deixar a
linha `ESCALAR:` passar mostra a mecânica interna na tela de quem está com um
aparelho quebrado na mão; não reconhecê-la deixa o cliente esperando uma
transferência que nunca foi pedida a ninguém.
"""

from app.services.helo_base import NADA_ENCONTRADO
from app.services.helo_prompt import MARCA_DE_ESCALADA, SISTEMA, le_resposta, monta_prompt


def test_resposta_comum_nao_escala():
    """O caso de sempre: o texto chega inteiro, sem sobra nem falta."""
    bruto = "1. Segure o botão por três segundos.\n\nFonte: Manual do Titan, seção 6."

    resposta = le_resposta(bruto)

    assert resposta.escalou is False
    assert resposta.texto == bruto
    assert resposta.motivo == ""


def test_a_linha_de_escalada_sai_do_texto_e_vira_motivo():
    """O motivo não é enfeite: é o que a equipe lê no aviso, antes de abrir o chamado."""
    resposta = le_resposta("Vou chamar um colega.\nESCALAR: pediu certificado de calibração")

    assert resposta.escalou is True
    assert resposta.texto == "Vou chamar um colega."
    assert resposta.motivo == "pediu certificado de calibração"


def test_a_marca_no_meio_do_texto_tambem_sai():
    """
    O modelo às vezes escreve a linha e emenda uma despedida embaixo.

    Olhar só a última linha deixaria a marca visível no meio da mensagem E
    faria a escalada passar despercebida — os dois defeitos de uma vez.
    """
    resposta = le_resposta("Vou passar para o time.\nESCALAR: garantia\nQualquer coisa, escreva.")

    assert resposta.escalou is True
    assert "ESCALAR" not in resposta.texto
    assert resposta.texto == "Vou passar para o time.\nQualquer coisa, escreva."


def test_caixa_e_espaco_nao_impedem_o_reconhecimento():
    """
    Modelo não é determinístico, e a marca precisa sobreviver à variação de forma.

    Errar aqui é caro de um lado só: uma escalada não reconhecida é o cliente
    esperando por alguém que nunca foi chamado.
    """
    resposta = le_resposta("Já chamo alguém.\n  escalar: aparelho molhado  ")

    assert resposta.escalou is True
    assert resposta.motivo == "aparelho molhado"
    assert resposta.texto == "Já chamo alguém."


def test_escalada_sem_motivo_nao_inventa_motivo():
    """Motivo vazio é informação; motivo inventado por padrão é ruído no aviso da equipe."""
    resposta = le_resposta("Vou transferir.\nESCALAR:")

    assert resposta.escalou is True
    assert resposta.motivo == ""


def test_so_a_marca_deixa_o_texto_vazio():
    """
    Quem chama precisa conseguir distinguir este caso.

    Se o texto vazio passasse adiante, a Helô publicaria um balão em branco na
    tela do cliente no exato instante em que ele foi transferido.
    """
    assert le_resposta("ESCALAR: fora da base técnica").texto == ""


def test_o_prompt_junta_os_blocos_na_ordem_em_que_o_sistema_os_descreve():
    """A ordem é a mesma da seção SUA MEMÓRIA: cadastro, base, conversa."""
    montado = monta_prompt("[CADASTRO]\nCliente: Ana", NADA_ENCONTRADO, "[CONVERSA]\nCliente: oi")

    assert montado.index("[CADASTRO]") < montado.index("[BASE TÉCNICA]")
    assert montado.index("[BASE TÉCNICA]") < montado.index("[CONVERSA]")
    assert NADA_ENCONTRADO in montado


def test_o_prompt_ensina_exatamente_a_marca_que_o_codigo_procura():
    """
    O acoplamento invisível entre um texto em português e um `startswith`.

    Se alguém editar o prompt e escrever "TRANSFERIR:" no lugar, o parser
    continuaria procurando "ESCALAR:" e nenhum teste dos dois lados quebraria:
    o modelo pediria escalada a vida toda e a equipe nunca seria avisada. Um
    defeito de produção que só aparece como cliente reclamando de abandono.
    """
    assert MARCA_DE_ESCALADA in SISTEMA


def test_o_prompt_usa_a_mesma_marca_de_base_vazia_que_a_busca_escreve():
    """
    O mesmo acoplamento, do outro lado.

    Quem escreve "NADA ENCONTRADO" é `monta_base_tecnica`; quem manda escalar
    ao ver isso é o prompt. Trocar a frase num lugar só faria a Helô responder
    de cabeça quando a busca não achasse nada — que é o defeito mais grave
    possível aqui, porque o cliente vai mexer num instrumento de medição legal
    seguindo o que ela escrever.
    """
    assert NADA_ENCONTRADO in SISTEMA
