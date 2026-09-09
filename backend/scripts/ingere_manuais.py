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

POR QUE UM MAPA EXPLÍCITO DE ARQUIVOS
-------------------------------------
Nada aqui é inferido do nome do arquivo, e não é preguiça: `MarkX.txt` é o
produto "Mark X" e `iblow10pro.txt` é "iBlow 10 Pro" — os nomes não batem, e
adivinhar por normalização daria certo hoje e erraria no primeiro arquivo
novo. Errar o produto é pior do que não indexar: manda o procedimento do
aparelho errado para quem está com um instrumento de medição legal na mão.

O corte também é declarado por arquivo. Uma regex só não serve: nos três
manuais numerados ela casa 26, 19 e 59 linhas contra 16, 11 e 12 títulos
reais, porque passo de procedimento e pergunta de FAQ têm a mesma forma
"N. texto" no começo da linha.
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
    arquivo: str
    produto: str
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
        "Phoebus",
        HeloDocType.tecnico,
        "numerada",
        "Manual Técnico do Phoebus",
    ),
    Fonte(
        "Manual Tecnico Titan.txt",
        "Titan",
        HeloDocType.tecnico,
        "numerada",
        "Manual Técnico do Titan",
    ),
    Fonte(
        "Manual_Tecnico_iBlow10Pro.txt",
        "iBlow 10 Pro",
        HeloDocType.tecnico,
        "numerada",
        "Manual Técnico do iBlow 10 Pro",
    ),
    Fonte("Deimos.txt", "Deimos", HeloDocType.comercial, "regua", "Ficha Comercial do Deimos"),
    Fonte(
        "EBS-010.txt", "EBS-010", HeloDocType.comercial, "markdown", "Ficha Comercial do EBS-010"
    ),
    Fonte(
        "iblow10pro.txt",
        "iBlow 10 Pro",
        HeloDocType.comercial,
        "regua",
        "Ficha Comercial do iBlow 10 Pro",
    ),
    Fonte("MarkX.txt", "Mark X", HeloDocType.comercial, "regua", "Ficha Comercial do Mark X"),
    Fonte("Mercury.txt", "Mercury", HeloDocType.comercial, "emoji", "Ficha Comercial do Mercury"),
)

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


def relatorio_de_conflitos(docs: list[Documento]) -> list[str]:
    linhas: list[str] = []

    # 1. Aplicativo citado por produto
    por_produto: dict[str, dict[str, set[str]]] = {}
    for d in docs:
        for t in d.trechos:
            for app in _APPS:
                if app.lower() in t.conteudo.lower():
                    por_produto.setdefault(d.fonte.produto, {}).setdefault(app, set()).add(
                        d.fonte.arquivo
                    )
    for produto, apps in sorted(por_produto.items()):
        if len(apps) > 1:
            linhas.append(f"APLICATIVO — {produto}: {len(apps)} nomes diferentes na documentação")
            for app, arquivos in sorted(apps.items()):
                linhas.append(f"    {app:18} em {', '.join(sorted(arquivos))}")

    # 2. Canal de contato, no corpus inteiro
    telefones, emails = set(), set()
    for d in docs:
        for t in d.trechos:
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
    for d in docs:
        for t in d.trechos:
            for rotulo, valor in _ESPEC.findall(t.conteudo):
                chave = (d.fonte.produto, _normaliza(rotulo))
                if not chave[1] or len(chave[1]) < 4:
                    continue
                especs.setdefault(chave, {}).setdefault(valor.strip(), set()).add(d.fonte.arquivo)
    for (produto, rotulo), valores in sorted(especs.items()):
        if len(valores) > 1 and len({a for s in valores.values() for a in s}) > 1:
            linhas.append(f"ESPECIFICAÇÃO — {produto} / '{rotulo}': {len(valores)} valores")
            for valor, arquivos in sorted(valores.items()):
                linhas.append(f"    {valor:40} em {', '.join(sorted(arquivos))}")

    return linhas


# ── Gravação ──────────────────────────────────────────────────


async def aplica(docs: list[Documento]) -> list[str]:
    settings = get_settings()
    motor = create_async_engine(settings.database_url)
    avisos: list[str] = []
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        produtos = {
            nome: pid for pid, nome in (await s.execute(select(Product.id, Product.name))).all()
        }
        for doc in docs:
            existente = (
                await s.execute(
                    select(HeloDocument).where(HeloDocument.filename == doc.fonte.arquivo)
                )
            ).scalar_one_or_none()

            if existente is not None and existente.content_hash == doc.hash:
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

            produto_id = produtos.get(doc.fonte.produto)
            if produto_id is None:
                avisos.append(
                    f"  ! {doc.fonte.arquivo}: produto '{doc.fonte.produto}' não existe no banco — "
                    "trechos ficam SEM vínculo, e trecho sem produto vale para TODOS. "
                    "Rode os seeds antes."
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
                if produto_id is not None:
                    await s.execute(
                        helo_chunk_products.insert().values(
                            chunk_id=chunk.id, product_id=produto_id
                        )
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
    print("CONFLITOS ENCONTRADOS — não resolvidos aqui, por decisão")
    print("=" * 72)
    conflitos = relatorio_de_conflitos(docs)
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
    for linha in asyncio.run(aplica(docs)):
        print(linha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
