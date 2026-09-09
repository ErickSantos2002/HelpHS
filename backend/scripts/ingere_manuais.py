"""
Recorta os manuais em trechos e grava na base da Helô.

COMO RODAR
----------
    # relatório, sem tocar no banco (padrão — é o modo seguro)
    python scripts/ingere_manuais.py --pasta "C:/caminho/Memoria da Helo"

    # grava de verdade
    python scripts/ingere_manuais.py --pasta "..." --aplicar

O caminho também pode vir de `HELO_MANUAIS_DIR`. **Não há padrão apontando
para dentro do repositório**, e é deliberado: os manuais vivem fora de
qualquer repositório porque o do Phoebus traz senhas de configuração avançada
em texto aberto, e este repositório é público. Nenhum .txt de manual é
copiado, movido ou gravado para dentro da árvore — nem temporariamente. O
relatório sai por stdout pelo mesmo motivo.

O QUE ESTE SCRIPT NÃO FAZ
-------------------------
Não calcula embedding. A coluna nasce nula de propósito: recortar é barato e
determinístico, embutir custa e depende do modelo local. Separadas, trocar de
modelo é re-embutir o que já está recortado, sem reler arquivo nenhum.

Não resolve contradição. Ele lista o que achou e para — busca vetorial traz os
dois trechos contraditórios e o modelo escolhe um ou mistura, e a Helô responde
COM A FONTE CITADA, que é pior do que errar sem fonte porque parece conferível.
Quem decide qual número está certo é o suporte técnico.

DE ONDE VEM O PRODUTO
---------------------
Da tabela `products`, que é a autoridade sobre quais aparelhos existem — não
de uma lista escrita aqui. Cada arquivo é casado contra os produtos do banco
comparando os nomes normalizados dos DOIS lados: minúsculas, sem acento, sem
espaço, sem underscore, sem hífen. É o que faz `MarkX.txt` encontrar "Mark X"
e `Manual_Tecnico_iBlow10Pro.txt` encontrar "iBlow 10 Pro" sem ninguém tabelar
a exceção.

O casamento é por CONTENÇÃO, nunca por aproximação difusa, e documento técnico
precisa casar com **exatamente um** produto: zero ou dois interrompem a
ingestão inteira. Errar o produto é pior do que não indexar — manda o
procedimento do aparelho errado para quem está com um instrumento de medição
legal na mão.

O QUE CONTINUA DECLARADO
------------------------
O corte, o tipo e o título, por arquivo. Uma regex só não serve para o corte:
nos três manuais numerados ela casa 26, 19 e 59 linhas contra 16, 11 e 12
títulos reais, porque passo de procedimento e pergunta de FAQ têm a mesma
forma "N. texto" no começo da linha.
"""

import argparse
import asyncio
import hashlib
import os
import re
import sys
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.models.models import (  # noqa: E402
    HeloChunk,
    HeloDocType,
    HeloDocument,
    Product,
    helo_chunk_products,
)

# ── O corpus, declarado ───────────────────────────────────────


@dataclass(frozen=True)
class Fonte:
    """
    O que este script sabe sobre um arquivo — e repare no que NÃO está aqui.

    O produto não é declarado. Ele é resolvido contra a tabela `products` do
    banco, que é a autoridade sobre quais aparelhos existem. Declarar aqui
    duplicaria o seed em texto solto: no dia em que alguém renomeasse um
    produto, esta lista continuaria dizendo o nome antigo e a busca passaria a
    devolver nada, em silêncio.

    A inversão também é o que torna "casou com mais de um produto" um caso
    POSSÍVEL, e portanto detectável. Com o nome escrito à mão, sempre haveria
    exatamente um por construção — e a ambiguidade só apareceria como resposta
    errada na tela do cliente.
    """

    arquivo: str
    tipo: HeloDocType
    corte: str
    titulo: str


# `Perfil da IA Helo.txt` NÃO está aqui, e a ausência é a decisão. Ele é o
# system prompt v4.0 da Helô do WhatsApp — não descreve aparelho nenhum.
# Indexado, ela recuperaria as próprias regras de escalação como se fossem
# procedimento técnico, e ainda ocuparia 22% do índice.
FONTES = (
    Fonte(
        "manual_phoebus_completo.txt",
        HeloDocType.tecnico,
        "numerada",
        "Manual Técnico do Phoebus",
    ),
    Fonte(
        "Manual Tecnico Titan.txt",
        HeloDocType.tecnico,
        "numerada",
        "Manual Técnico do Titan",
    ),
    Fonte(
        "Manual_Tecnico_iBlow10Pro.txt",
        HeloDocType.tecnico,
        "numerada",
        "Manual Técnico do iBlow 10 Pro",
    ),
    Fonte("Deimos.txt", HeloDocType.comercial, "regua", "Ficha Comercial do Deimos"),
    Fonte("EBS-010.txt", HeloDocType.comercial, "markdown", "Ficha Comercial do EBS-010"),
    Fonte(
        "iblow10pro.txt",
        HeloDocType.comercial,
        "regua",
        "Ficha Comercial do iBlow 10 Pro",
    ),
    Fonte("MarkX.txt", HeloDocType.comercial, "regua", "Ficha Comercial do Mark X"),
    Fonte("Mercury.txt", HeloDocType.comercial, "emoji", "Ficha Comercial do Mercury"),
)

# ── Casar arquivo com produto ─────────────────────────────────


def chave(texto: str) -> str:
    """
    A forma comparável de um nome, dos DOIS lados.

    O seed grava "iBlow 10 Pro" e "Mark X"; os arquivos são
    `Manual_Tecnico_iBlow10Pro.txt` e `MarkX.txt`. Comparação literal falha nos
    dois, e tabelar a exceção à mão só adia o problema para o próximo arquivo.

    Minúsculas, sem acento, sem espaço, sem underscore e sem hífen. O acento
    entra porque nome de produto com acento é questão de tempo, e é barato
    resolver antes.
    """
    s = unicodedata.normalize("NFKD", texto.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[\s_\-]+", "", s)


class CorpusInconsistenteError(RuntimeError):
    """O mapa entre arquivo e produto não fecha. Não há palpite bom aqui."""


def casa_produtos(fonte: Fonte, produtos: dict[str, uuid.UUID]) -> list[uuid.UUID]:
    """
    Quais produtos este documento cobre, decidido por CONTENÇÃO do nome.

    Nada de aproximação difusa. Distância de edição acertaria "Mark X" em
    "MarkX.txt" e também acertaria "Mercury" em "MarkX.txt" se o limiar
    escorregasse — e o erro sairia como procedimento do aparelho errado na mão
    de quem opera um instrumento de medição legal. Contenção é binária: ou o
    nome normalizado do produto está no nome normalizado do arquivo, ou não
    está.

    **Documento técnico precisa casar com exatamente um.** Zero ou dois é
    defeito do mapa, e defeito de mapa para quando é barato — aqui — e não
    depois, na resposta ao cliente.

    Ficha comercial é mais frouxa de propósito, e a assimetria tem motivo: uma
    ficha sem produto nenhum pode ser um catálogo que vale para todos, e
    trecho sem vínculo é exatamente isso. Um procedimento técnico sem produto,
    não: é o passo do Phoebus aparecendo para quem tem um Titan na mão.
    """
    base = chave(Path(fonte.arquivo).stem)
    achados = [pid for nome, pid in produtos.items() if chave(nome) in base]

    if fonte.tipo is HeloDocType.tecnico and len(achados) != 1:
        nomes = sorted(n for n in produtos if chave(n) in base)
        raise CorpusInconsistenteError(
            f"{fonte.arquivo}: documento técnico casou com {len(achados)} produtos "
            f"({', '.join(nomes) or 'nenhum'}). Técnico precisa de exatamente um — "
            "zero manda o procedimento para todos os aparelhos, e dois mandam o "
            "procedimento errado. Corrija o nome do arquivo ou o cadastro do produto."
        )
    return achados


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

    partes: list[tuple[str, list[str]]] = []
    # O que vem antes da primeira subseção é o preâmbulo da seção, e vale como
    # trecho próprio quando tem corpo — nele costuma estar o para que serve.
    if inicios[0][0] > 0:
        partes.append((titulo, bloco[: inicios[0][0]]))
    partes.extend(_fatia(bloco, inicios))
    return partes


def _corta_regua(linhas: list[str]) -> list[tuple[str, list[str]]]:
    """Blocos separados por uma linha de três ou mais hifens."""
    regua = re.compile(r"^-{3,}\s*$")
    inicios: list[tuple[int, str]] = []
    comeco = 0
    for i, linha in enumerate(linhas):
        if regua.match(linha):
            if i > comeco:
                inicios.append((comeco, _primeiro_titulo(linhas[comeco:i])))
            comeco = i + 1
    if comeco < len(linhas):
        inicios.append((comeco, _primeiro_titulo(linhas[comeco:])))
    return _fatia(linhas, inicios)


def _corta_markdown(linhas: list[str]) -> list[tuple[str, list[str]]]:
    padrao = re.compile(r"^#{1,3}\s+(\S.*)$")
    inicios = [
        (i, _titulo_limpo(padrao.match(linha.strip()).group(1)))
        for i, linha in enumerate(linhas)
        if padrao.match(linha.strip())
    ]
    return _fatia(linhas, inicios)


def _corta_emoji(linhas: list[str]) -> list[tuple[str, list[str]]]:
    """Título é linha que começa com símbolo — o Mercury não usa régua nem ##."""
    inicios: list[tuple[int, str]] = []
    for i, linha in enumerate(linhas):
        t = linha.strip()
        if not t or len(t) < 4:
            continue
        if unicodedata.category(t[0]) in {"So", "Sk", "Sm"}:
            inicios.append((i, t))
    return _fatia(linhas, inicios)


def _quebra(texto: str, largura: int) -> list[str]:
    """Quebra em linhas para o relatório caber num terminal."""
    linhas, atual = [], ""
    for palavra in texto.split():
        if len(atual) + len(palavra) + 1 > largura:
            linhas.append(atual)
            atual = palavra
        else:
            atual = f"{atual} {palavra}".strip()
    if atual:
        linhas.append(atual)
    return linhas


def _titulo_limpo(bruto: str) -> str:
    """Tira a pontuacao de fim que o titulo do manual carrega ('1. Introducao:')."""
    return bruto.strip().rstrip(":;-—– ").strip()


def _primeiro_titulo(bloco: list[str]) -> str:
    for linha in bloco:
        if linha.strip():
            return _titulo_limpo(linha)
    return "(sem título)"


def _fatia(linhas: list[str], inicios: list[tuple[int, str]]) -> list[tuple[str, list[str]]]:
    if not inicios:
        return []
    saida = []
    for pos, (i, titulo) in enumerate(inicios):
        fim = inicios[pos + 1][0] if pos + 1 < len(inicios) else len(linhas)
        saida.append((titulo, linhas[i:fim]))
    return saida


_CORTES = {
    "numerada": _corta_numerada,
    "regua": _corta_regua,
    "markdown": _corta_markdown,
    "emoji": _corta_emoji,
}

# Um trecho menor que isto não carrega procedimento nenhum: é cabeçalho,
# rodapé de contato ou linha de preço solta. Vira ruído no ranking vetorial,
# porque casa com qualquer pergunta curta.
_MINIMO = 120


@dataclass
class Trecho:
    secao: str
    conteudo: str
    exige_credencial: bool
    ordem: int


@dataclass
class Documento:
    fonte: Fonte
    hash: str
    trechos: list[Trecho] = field(default_factory=list)


@dataclass
class Passo:
    """Um documento e o que a gravação faria com ele."""

    doc: Documento
    acao: str  # "novo" | "refaz" | "inalterado"
    produtos: list[str]
    produto_ids: list[uuid.UUID]


def recorta(fonte: Fonte, caminho: Path) -> Documento:
    bruto = caminho.read_text(encoding="utf-8")
    digest = hashlib.sha256(bruto.encode("utf-8")).hexdigest()
    doc = Documento(fonte=fonte, hash=digest)

    ordem = 0
    for titulo, bloco in _CORTES[fonte.corte](bruto.splitlines()):
        conteudo = "\n".join(bloco).strip()
        if len(conteudo) < _MINIMO:
            continue
        conteudo, exigia = redige(conteudo)
        doc.trechos.append(
            Trecho(
                secao=titulo[:255],
                conteudo=conteudo,
                exige_credencial=exigia,
                ordem=ordem,
            )
        )
        ordem += 1
    return doc


# ── Relatório de contradições ─────────────────────────────────

_APPS = ("Health App", "i-SOBER", "iSOBER", "Alcovisor Elite")
_TELEFONE = re.compile(r"\(\d{2}\)\s*\d?\s?\d{4}[-\s]?\d{4}")
_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
_ESPEC = re.compile(
    r"^\s*[-•*]?\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s/()]{3,40}?)\s*:\s*(.{1,60}?)\s*$",
    re.MULTILINE,
)


def _normaliza(rotulo: str) -> str:
    s = unicodedata.normalize("NFKD", rotulo.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z]+", " ", s).strip()


# Conflitos já levantados a olho, que a detecção automática NÃO pega.
#
# O detector compara o MESMO rótulo entre documentos diferentes. Os de baixo
# escapam por três motivos distintos, e vale saber quais para não confiar
# demais no automático: dois rótulos diferentes dizendo a mesma coisa
# ("Tempo de Análise" e "Resultados em até"), dois rótulos diferentes DENTRO
# do mesmo arquivo (memória e autonomia do Titan), e um número que só é
# suspeito à luz de outro campo (8.000 testes por carga com bateria de
# 400 mAh). Nenhum dos três se resolve com regex; os três se resolvem com
# alguém do suporte olhando.
_CONHECIDOS = (
    (
        "Titan — memória e autonomia",
        "'Memória: até 8.000 testes' e 'Autonomia: até 8.000 testes por carga', "
        "num aparelho com bateria Ni-MH de 400 mAh. O segundo número parece cópia "
        "do primeiro. Enquanto não houver resposta, a Helô pode prometer autonomia "
        "que o aparelho não tem.",
    ),
    (
        "iBlow 10 Pro — tempo de resposta",
        "A ficha comercial diz 'resultados em até 5 segundos'; o manual técnico diz "
        "'Tempo de Análise: até 2 segundos'. Rótulos diferentes, mesmo fato.",
    ),
    (
        "Calibração — intervalo",
        "Titan, Phoebus e iBlow 10 Pro dizem '12 meses ou 5.000 testes'; o Phoebus "
        "armazena 20.000 testes; as fichas de Deimos, EBS-010, Mark X e Mercury não "
        "citam intervalo nenhum.",
    ),
)


def relatorio_de_conflitos(plano: list[Passo]) -> list[str]:
    linhas: list[str] = []

    # 1. Aplicativo citado por produto
    por_produto: dict[str, dict[str, set[str]]] = {}
    for passo in plano:
        # Um documento sem produto resolvido entra como "(sem produto)": some
        # do agrupamento por aparelho, mas não some do relatório.
        rotulos = passo.produtos or ["(sem produto)"]
        for t in passo.doc.trechos:
            for app in _APPS:
                if app.lower() in t.conteudo.lower():
                    for rotulo in rotulos:
                        por_produto.setdefault(rotulo, {}).setdefault(app, set()).add(
                            passo.doc.fonte.arquivo
                        )
    for produto, apps in sorted(por_produto.items()):
        if len(apps) > 1:
            linhas.append(f"APLICATIVO — {produto}: {len(apps)} nomes diferentes na documentação")
            for app, arquivos in sorted(apps.items()):
                linhas.append(f"    {app:18} em {', '.join(sorted(arquivos))}")

    # 2. Canal de contato, no corpus inteiro
    telefones, emails = set(), set()
    for passo in plano:
        for t in passo.doc.trechos:
            telefones.update(x.strip() for x in _TELEFONE.findall(t.conteudo))
            emails.update(x.lower() for x in _EMAIL.findall(t.conteudo))
    if len(telefones) > 1 or len(emails) > 1:
        linhas.append(f"CONTATO — {len(telefones)} telefones e {len(emails)} e-mails no corpus")
        for x in sorted(telefones):
            linhas.append(f"    tel  {x}")
        for x in sorted(emails):
            linhas.append(f"    mail {x}")

    # 3. Mesmo rótulo de especificação com valores diferentes, no mesmo produto
    especs: dict[tuple[str, str], dict[str, set[str]]] = {}
    for passo in plano:
        for rotulo_produto in passo.produtos or ["(sem produto)"]:
            for t in passo.doc.trechos:
                for rotulo, valor in _ESPEC.findall(t.conteudo):
                    ch = (rotulo_produto, _normaliza(rotulo))
                    if not ch[1] or len(ch[1]) < 4:
                        continue
                    especs.setdefault(ch, {}).setdefault(valor.strip(), set()).add(
                        passo.doc.fonte.arquivo
                    )
    for (produto, rotulo), valores in sorted(especs.items()):
        if len(valores) > 1 and len({a for s in valores.values() for a in s}) > 1:
            linhas.append(f"ESPECIFICAÇÃO — {produto} / '{rotulo}': {len(valores)} valores")
            for valor, arquivos in sorted(valores.items()):
                linhas.append(f"    {valor:40} em {', '.join(sorted(arquivos))}")

    return linhas


# ── O plano: o que a gravação FARIA ───────────────────────────


async def planeja(docs: list[Documento]) -> list[Passo]:
    """
    Resolve produto e decide a ação, SEM escrever nada.

    Existe separado da gravação para o `--aplicar` poder ser conferido antes de
    rodar: a mesma função monta o que se vê no relatório e o que a gravação
    executa, então o relatório não é uma descrição do plano — é o plano.

    A inconsistência de corpus estoura AQUI, antes de qualquer INSERT: um
    documento técnico sem produto, ou com dois, para a ingestão inteira em vez
    de gravar sete arquivos certos e um errado.
    """
    motor = create_async_engine(get_settings().database_url)
    plano: list[Passo] = []
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        produtos = {
            nome: pid for pid, nome in (await s.execute(select(Product.id, Product.name))).all()
        }
        if not produtos:
            raise CorpusInconsistenteError(
                "A tabela `products` está vazia. Sem produto, todo trecho ficaria sem "
                "vínculo — e trecho sem vínculo vale para TODOS os aparelhos, que é o "
                "oposto do que a busca precisa. Rode os seeds antes."
            )

        for doc in docs:
            ids = casa_produtos(doc.fonte, produtos)
            nomes = sorted(n for n, pid in produtos.items() if pid in set(ids))

            existente = (
                await s.execute(
                    select(HeloDocument.content_hash).where(
                        HeloDocument.filename == doc.fonte.arquivo
                    )
                )
            ).scalar_one_or_none()

            if existente is None:
                acao = "novo"
            elif existente == doc.hash:
                acao = "inalterado"
            else:
                acao = "refaz"

            plano.append(Passo(doc=doc, acao=acao, produtos=nomes, produto_ids=ids))
    await motor.dispose()
    return plano


# ── Gravação ──────────────────────────────────────────────────


async def aplica(plano: list[Passo]) -> list[str]:
    settings = get_settings()
    motor = create_async_engine(settings.database_url)
    avisos: list[str] = []
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        for passo in plano:
            doc = passo.doc
            existente = (
                await s.execute(
                    select(HeloDocument).where(HeloDocument.filename == doc.fonte.arquivo)
                )
            ).scalar_one_or_none()

            if passo.acao == "inalterado":
                avisos.append(f"  = {doc.fonte.arquivo}: inalterado, nada a fazer")
                continue

            if existente is not None:
                # Refaz os trechos daquele documento, e só os dele. O CASCADE
                # da FK leva os vínculos com produto junto.
                await s.execute(delete(HeloChunk).where(HeloChunk.document_id == existente.id))
                existente.content_hash = doc.hash
                existente.title = doc.fonte.titulo
                existente.doc_type = doc.fonte.tipo
                alvo = existente
                avisos.append(
                    f"  ~ {doc.fonte.arquivo}: mudou, {len(doc.trechos)} trechos refeitos"
                )
            else:
                alvo = HeloDocument(
                    id=uuid.uuid4(),
                    filename=doc.fonte.arquivo,
                    title=doc.fonte.titulo,
                    doc_type=doc.fonte.tipo,
                    content_hash=doc.hash,
                )
                s.add(alvo)
                avisos.append(f"  + {doc.fonte.arquivo}: {len(doc.trechos)} trechos novos")
            await s.flush()

            if not passo.produto_ids:
                avisos.append(
                    f"  ! {doc.fonte.arquivo}: sem produto vinculado — os trechos valem "
                    "para TODOS os aparelhos. É o comportamento certo para catálogo, "
                    "e só chega aqui porque é ficha comercial (técnico sem produto é erro fatal)."
                )

            for t in doc.trechos:
                chunk = HeloChunk(
                    id=uuid.uuid4(),
                    document_id=alvo.id,
                    secao=t.secao,
                    ordem=t.ordem,
                    conteudo=t.conteudo,
                    exige_credencial_admin=t.exige_credencial,
                )
                s.add(chunk)
                await s.flush()
                for pid in passo.produto_ids:
                    await s.execute(
                        helo_chunk_products.insert().values(chunk_id=chunk.id, product_id=pid)
                    )
        await s.commit()
    await motor.dispose()
    return avisos


# ── Linha de comando ──────────────────────────────────────────


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--pasta",
        default=os.environ.get("HELO_MANUAIS_DIR"),
        help="pasta dos manuais, FORA de qualquer repositório",
    )
    p.add_argument(
        "--aplicar",
        action="store_true",
        help="grava no banco; sem esta flag o script só relata",
    )
    args = p.parse_args()

    if not args.pasta:
        print(
            "ERRO: informe --pasta ou HELO_MANUAIS_DIR.\n"
            "Não há padrão de propósito: os manuais ficam fora do repositório, "
            "porque o do Phoebus traz senhas em texto aberto e este repo é público.",
            file=sys.stderr,
        )
        return 2

    pasta = Path(args.pasta)
    if not pasta.is_dir():
        print(f"ERRO: {pasta} não é uma pasta.", file=sys.stderr)
        return 2

    docs, faltando = [], []
    for fonte in FONTES:
        caminho = pasta / fonte.arquivo
        if not caminho.is_file():
            faltando.append(fonte.arquivo)
            continue
        docs.append(recorta(fonte, caminho))

    if faltando:
        print(f"AUSENTES: {', '.join(faltando)}\n", file=sys.stderr)

    try:
        plano = asyncio.run(planeja(docs))
    except CorpusInconsistenteError as erro:
        print(f"\nCORPUS INCONSISTENTE — nada foi gravado.\n\n{erro}\n", file=sys.stderr)
        return 1

    print("=" * 72)
    print("RECORTE")
    print("=" * 72)
    total = marcados = 0
    for d in docs:
        maior = max((len(t.conteudo) for t in d.trechos), default=0)
        marca = sum(1 for t in d.trechos if t.exige_credencial)
        total += len(d.trechos)
        marcados += marca
        print(
            f"  {d.fonte.arquivo:32} {d.fonte.tipo.value:9} "
            f"{len(d.trechos):3} trechos  maior={maior:5}  "
            f"credencial={marca}  hash={d.hash[:8]}"
        )
    print(f"\n  TOTAL: {total} trechos, {marcados} exigindo credencial de administrador")

    print()
    print("=" * 72)
    print("O QUE O --aplicar FARIA")
    print("=" * 72)
    rotulo_da_acao = {"novo": "CRIA  ", "refaz": "REFAZ ", "inalterado": "pula  "}
    for passo in plano:
        vinculo = ", ".join(passo.produtos) if passo.produtos else "SEM PRODUTO (vale para todos)"
        print(
            f"  {rotulo_da_acao[passo.acao]} {passo.doc.fonte.arquivo:32} "
            f"{len(passo.doc.trechos):3} trechos → {vinculo}"
        )
    novos = sum(len(p.doc.trechos) for p in plano if p.acao != "inalterado")
    vinculos = sum(len(p.doc.trechos) * len(p.produto_ids) for p in plano if p.acao != "inalterado")
    print(f"\n  {novos} trechos gravados, {vinculos} vínculos trecho→produto")

    print()
    print("=" * 72)
    print("CONFLITOS ENCONTRADOS — não resolvidos aqui, por decisão")
    print("=" * 72)
    conflitos = relatorio_de_conflitos(plano)
    if conflitos:
        for linha in conflitos:
            print(linha)
    else:
        print("  (nenhum)")

    print()
    print("-" * 72)
    print("LEVANTADOS A OLHO — a detecção automática NÃO pega estes")
    print("-" * 72)
    print("  O detector acima compara o mesmo RÓTULO entre documentos. Não")
    print("  alcança rótulo diferente para o mesmo fato, nem dois campos do")
    print("  mesmo arquivo, nem número que só fica suspeito à luz de outro.")
    print("  Ou seja: a lista de cima é um piso, não um inventário.")
    print()
    for titulo, texto in _CONHECIDOS:
        print(f"  * {titulo}")
        for pedaco in _quebra(texto, 66):
            print(f"      {pedaco}")

    if not args.aplicar:
        print("\n>>> MODO RELATÓRIO: nada foi gravado. Use --aplicar para gravar.")
        return 0

    print()
    print("=" * 72)
    print("GRAVANDO")
    print("=" * 72)
    for linha in asyncio.run(aplica(plano)):
        print(linha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
