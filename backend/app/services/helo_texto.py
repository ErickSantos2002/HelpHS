"""
O texto da base da Helô: como um documento vira trecho, e como a senha sai dele.

Funções puras — texto entra, texto sai — e por isso num módulo próprio. Moravam
em `scripts/ingere_manuais.py` enquanto a fonte da Helô era uma pasta de
manuais. Com a fonte passando a ser a Base de Conhecimento, dois caminhos
passam a precisar delas e não podem divergir: a IMPORTAÇÃO dos manuais para a
Base, que redige a senha antes de o artigo existir — artigo publicado é
visível para o cliente —, e a INDEXAÇÃO dos artigos para a busca.

Duas cópias do redator seriam o pior defeito possível aqui: uma aprende uma
forma nova de escrever senha e a outra não, e a senha escapa pelo caminho que
ficou para trás, sem erro nenhum.
"""

import re
from dataclasses import dataclass

# ── Redação: o que sai do texto antes de virar trecho ─────────

# As senhas de configuração avançada do Phoebus. O padrão casa o RÓTULO e
# captura o valor para substituir — a senha em si nunca aparece aqui, nem no
# relatório, nem no banco.
_SENHA = re.compile(
    r"((?:senha|c[óo]digo)[^:\n]{0,40}:\s*)([0-9]{4,8})\b",
    re.IGNORECASE,
)
_REDIGIDO = r"\1[REDIGIDO — senha de administrador]"

# Os seis links do Google Drive do manual do Phoebus. Saem até alguém
# confirmar que são públicos: a Helô mandando um link privado para um cliente
# externo é vazamento com a nossa assinatura.
_DRIVE = re.compile(r"https?://(?:drive|docs)\.google\.com/\S+")


def redige(texto: str) -> tuple[str, bool]:
    """Devolve (texto redigido, exigia credencial)."""
    limpo, quantas = _SENHA.subn(_REDIGIDO, texto)
    limpo = _DRIVE.sub("[link removido até confirmarem que é público]", limpo)
    return limpo, quantas > 0


# ── Detecção: larga de propósito, e separada da redação ───────
#
# O `_SENHA` acima é PRECISO: ele conhece a forma exata que o manual do Phoebus
# usa e substitui exatamente aquilo. Um padrão preciso erra por omissão, e a
# omissão aqui é muda — senha que escapa não é redigida E não marca o trecho,
# então o resultado fica indistinguível de "não havia senha nenhuma". É o
# controle de segurança do pior conteúdo do corpus falhando sem ruído.
#
# Por isso a detecção é outra função, e é exagerada de propósito. Ela não
# redige nada: ela só levanta a mão. Quando ela levanta a mão e a redação não
# fez nada, a ingestão PARA, dizendo arquivo e linha.
#
# A assimetria é o ponto. Falso positivo custa alguém olhar uma linha e ou
# ajustar o redator ou estreitar o detector — barato e visível. Falso negativo
# custa uma senha de administrador publicada na base que responde cliente.

_PALAVRA_DE_CREDENCIAL = re.compile(
    r"senha|senhas|c[óo]digo|pin\b|password|chave\s+de\s+acesso|credencial",
    re.IGNORECASE,
)
_DIGITOS = re.compile(r"\d{3,}")
# Número com separador de milhar, de decimal ou de moeda não é credencial: é
# "8.000 testes", "R$ 4.900,00", "12 meses". Senha vem crua.
_NUMERO_FORMATADO = re.compile(r"\d[.,]\d|R\$")


def suspeitas(bruto: str) -> list[tuple[int, str]]:
    """
    Linhas que PARECEM carregar credencial, com o número da linha no arquivo.

    Larga por desenho: basta a linha falar de senha/código/PIN e trazer três
    dígitos seguidos que não sejam número formatado. Não tenta entender a
    frase, não exige dois-pontos, não exige posição.
    """
    achadas: list[tuple[int, str]] = []
    for numero, linha in enumerate(bruto.splitlines(), start=1):
        if not _PALAVRA_DE_CREDENCIAL.search(linha):
            continue
        cruzinhos = [d for d in _DIGITOS.findall(linha) if not _NUMERO_FORMATADO.search(linha)]
        if cruzinhos:
            achadas.append((numero, linha.strip()))
    return achadas


class CredencialNaoRedigidaError(RuntimeError):
    """O detector viu e o redator não redigiu. Não se grava assim."""


def confere_redacao(rotulo: str, bruto: str, trechos: list["Trecho"]) -> None:
    """
    Cruza o que o detector viu com o que sobrou no texto que iria para o banco.

    O teste não é "o redator rodou": é se os DÍGITOS da linha suspeita ainda
    existem no conteúdo final. É a única pergunta que importa, e ela não
    depende de o detector e o redator concordarem sobre a forma.
    """
    if not (achadas := suspeitas(bruto)):
        return

    final = "\n".join(t.conteudo for t in trechos)
    sobreviventes: list[str] = []
    for numero, linha in achadas:
        for digitos in _DIGITOS.findall(linha):
            if digitos in final:
                # A linha NÃO é transcrita: ela contém a senha.
                sobreviventes.append(f"    {rotulo}:{numero} — {len(digitos)} dígitos")
                break

    if sobreviventes:
        raise CredencialNaoRedigidaError(
            f"{rotulo}: o detector encontrou {len(achadas)} linha(s) com aparência de "
            f"credencial, e {len(sobreviventes)} continua(m) com os dígitos no texto que iria "
            "para o banco:\n" + "\n".join(sobreviventes) + "\n\n"
            "Isto para a ingestão de propósito. Ou o redator precisa aprender essa forma "
            "(`_SENHA`), ou a linha não é credencial e o detector precisa estreitar "
            "(`_PALAVRA_DE_CREDENCIAL`). O que não pode é a base receber o texto e ninguém "
            "ficar sabendo — senha que escapa também não marca o trecho, e o resultado fica "
            "igual a 'não havia senha'."
        )


# ── Os cortes ─────────────────────────────────────────────────


def _corta_numerada(linhas: list[str]) -> list[tuple[str, list[str]]]:
    """
    Título é `N. Texto` **com N na sequência esperada**.

    O contador crescente é o que separa título de passo de procedimento: a
    seção 9 vem depois da 8, mas o passo "3." de um procedimento aparece
    dentro da seção 7 e quebraria a sequência. Sem essa regra entram dez
    trechos-lixo no Titan e quarenta e sete no Phoebus.
    """
    padrao = re.compile(r"^(\d+)\.\s+(\S.*)$")
    esperado = 1
    passo_esperado: int | None = None
    inicios: list[tuple[int, str]] = []
    for i, linha in enumerate(linhas):
        m = padrao.match(linha.strip())
        if not m:
            continue
        n = int(m.group(1))

        # Um `1.` depois de a numeração já ter passado do 1 é REINÍCIO, e
        # reinício é enumeração nova: são os passos de um procedimento. A
        # partir dele, os números que continuam a contagem são passos, não
        # seções — mesmo quando calham de bater com a seção esperada.
        if n == 1 and esperado > 1:
            passo_esperado = 2
            continue
        if passo_esperado is not None and n == passo_esperado:
            passo_esperado += 1
            continue

        if n == esperado:
            inicios.append((i, _titulo_limpo(f"{n}. {m.group(2)}")))
            esperado += 1
            passo_esperado = None

    saida: list[tuple[str, list[str]]] = []
    for titulo, bloco in _fatia(linhas, inicios):
        saida.extend(_subdivide(titulo, bloco))
    return saida


# Uma subseção começa por `8.2 Alterar Idioma` (Titan) ou por um símbolo
# seguido de número, como no Phoebus. Os dois casos existem no corpus.
_SUB_NUMERADA = re.compile(r"^(\d+\.\d+)\.?\s+(\S.*)$")
_SUB_SIMBOLO = re.compile(r"^[^\w\s]\s*(\d+)\.\s+(\S.*)$")


def _subdivide(titulo: str, bloco: list[str]) -> list[tuple[str, list[str]]]:
    """
    Quebra a seção nas subseções dela, quando existirem.

    Existe por dois motivos que se somam. O primeiro é recuperação: a seção 7
    do Phoebus tem 3.4 mil caracteres e reúne SEIS procedimentos diferentes —
    ajustar resultado, conectar à internet, data e hora, idioma, áudio e
    confiança facial. Um vetor só para tudo isso não se parece com nenhuma das
    seis perguntas que o cliente faria.

    O segundo é a marca de credencial. As duas senhas do Phoebus estão em
    sub-blocos DIFERENTES da mesma seção; sem quebrar, um trecho só carrega as
    duas e a marca deixa de dizer QUAL procedimento exige senha — a Helô
    escalaria em perguntas que não precisavam.

    Sem subseção, a seção volta inteira: é o caso das doze do Titan e das onze
    do iBlow, que já são do tamanho certo.
    """
    inicios: list[tuple[int, str]] = []
    for i, linha in enumerate(bloco):
        t = linha.strip()
        m = _SUB_NUMERADA.match(t) or _SUB_SIMBOLO.match(t)
        if m:
            numero = m.group(1)
            rotulo = numero if "." in numero else f"{numero}."
            inicios.append((i, f"{titulo} → {_titulo_limpo(rotulo + chr(32) + m.group(2))}"))

    if len(inicios) < 2:
        return [(titulo, bloco)]

    # O preâmbulo (o que vem antes da primeira subseção) sai pelo `_fatia`,
    # que trata isso uniformemente para todos os cortes.
    return _fatia(bloco, inicios, titulo_do_preambulo=titulo)


_REGUA = re.compile(r"^-{3,}\s*$")


def _titulo_limpo(bruto: str) -> str:
    """Tira a pontuacao de fim que o titulo do manual carrega ('1. Introducao:')."""
    return bruto.strip().rstrip(":;-—– ").strip()


def _primeiro_titulo(bloco: list[str]) -> str:
    for linha in bloco:
        if linha.strip():
            return _titulo_limpo(linha)
    return "(sem título)"


def _fatia(
    linhas: list[str],
    inicios: list[tuple[int, str]],
    titulo_do_preambulo: str | None = None,
) -> list[tuple[str, list[str]]]:
    """
    Corta em trechos, e **não joga fora o que vem antes do primeiro título**.

    O descarte silencioso do preâmbulo custava caro no EBS-010: o primeiro
    `##` está na linha 8, então o título do documento e o bloco de preço
    sumiam sem passar por filtro nenhum — a ficha comercial ficava sem o preço,
    que é justamente o que uma ficha comercial existe para responder.
    """
    if not inicios:
        return []

    saida: list[tuple[str, list[str]]] = []
    if inicios[0][0] > 0:
        cabeca = linhas[: inicios[0][0]]
        saida.append((titulo_do_preambulo or _primeiro_titulo(cabeca), cabeca))

    for pos, (i, titulo) in enumerate(inicios):
        fim = inicios[pos + 1][0] if pos + 1 < len(inicios) else len(linhas)
        saida.append((titulo, linhas[i:fim]))
    return saida


# O que desqualifica um trecho é ser CABEÇALHO, não ser curto.
#
# O piso por tamanho descartava "8.2 Alterar Idioma" (104 caracteres) e
# "8.3 Verificar Contador de Testes" (112) do Titan, com os vizinhos 8.1 (130)
# e 8.4 (137) indexados. A base respondia "como ajusto a data" e ficava muda em
# "como coloco em português" — buraco parcial, e por isso invisível.
#
# O que aqueles dois têm e um cabeçalho não tem é CORPO: linha de conteúdo além
# do título. É isso que se mede agora.
_CORPO_MINIMO = 40


def descarta(titulo: str, conteudo: str) -> str | None:
    """Devolve o motivo do descarte, ou None quando o trecho fica."""
    linhas = [x for x in conteudo.splitlines() if x.strip()]
    corpo = "\n".join(linhas[1:]).strip() if linhas else ""

    if not corpo:
        return "só o título, sem corpo"
    if len(corpo) < _CORPO_MINIMO:
        return f"corpo de {len(corpo)} caracteres, abaixo de {_CORPO_MINIMO}"
    return None


@dataclass
class Trecho:
    secao: str
    conteudo: str
    exige_credencial: bool
    ordem: int
