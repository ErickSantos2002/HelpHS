"""
O ZIP com os anexos de um chamado: nomes seguros e montagem em disco.

Sem rede e sem banco aqui de propósito — quem decide QUAIS anexos entram é o
router, com o acesso já conferido. Este módulo só recebe a lista pronta.

── Por que montar num temporário, e não enviar enquanto monta ─────────────

Um ZIP montado durante o envio já teria mandado o 200 quando o terceiro
arquivo sumisse, e quem baixou ficaria com um ZIP parcial sem saber. Montando
antes, a falha vira um erro de verdade, e o ZIP só sai inteiro.

O custo é disco, não memória: `ZipFile.write` lê cada arquivo em blocos, e
`ZIP_STORED` não comprime (anexo típico — PDF, imagem, .docx — já é
comprimido; recomprimir gastaria CPU para ganhar quase nada). O teto é o do
upload: 10 arquivos de 25 MB.
"""

import os
import re
import tempfile
import unicodedata
import zipfile
from collections.abc import Sequence
from pathlib import Path

from app.core.config import Settings
from app.models.models import Attachment
from app.services import storage

# Proibidos em nome de arquivo no Windows. Trocados por "_" e não apagados: o
# nome continua legível ("a_b.txt" em vez de "ab.txt").
_PROIBIDOS = re.compile(r'[<>:"|?*]')

# Nomes que o Windows reserva para dispositivo, com ou sem extensão.
_RESERVADOS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)

_TAMANHO_MAXIMO = 180
"""Caracteres. Folga para o " (12)" da deduplicação e para a pasta de destino."""


def nome_seguro(original: str | None, reserva: str) -> str:
    """O nome com que o arquivo vai ser gravado no disco de quem descompactar.

    O `original_name` é gravado CRU no upload (`attachments.py`), então pode
    trazer caminho (`../../etc/passwd`, `C:\\...`), caractere de controle ou
    marca invisível de direção de texto. Fica só o último pedaço do caminho,
    sem nada disso. Se não sobrar nome que preste, vale a `reserva` — o nome
    interno do anexo (uuid + extensão), que é sempre seguro.
    """
    nome = re.split(r"[\\/]", original or "")[-1]
    # Categoria "C": controle, formatação (inclui o U+202E, que inverte o texto
    # e disfarça "fdp.exe" de "exe.pdf"), substitutos e não atribuídos.
    nome = "".join(ch for ch in nome if not unicodedata.category(ch).startswith("C"))
    nome = _PROIBIDOS.sub("_", nome)
    nome = nome.strip(" .")
    if not nome:
        return reserva

    base, ext = os.path.splitext(nome)
    if base.upper() in _RESERVADOS:
        base = f"_{base}"
    if len(base) + len(ext) > _TAMANHO_MAXIMO:
        base = base[: max(1, _TAMANHO_MAXIMO - len(ext))]
    return f"{base}{ext}"


def nomes_unicos(nomes: list[str]) -> list[str]:
    """Dá a cada nome repetido um " (2)", " (3)"... na ordem em que aparecem.

    A comparação ignora caixa: "laudo.pdf" e "LAUDO.pdf" são o mesmo arquivo no
    Windows e no macOS, e o segundo sobrescreveria o primeiro ao descompactar.
    """
    vistos: set[str] = set()
    saida: list[str] = []
    for nome in nomes:
        base, ext = os.path.splitext(nome)
        candidato, n = nome, 2
        while candidato.casefold() in vistos:
            candidato = f"{base} ({n}){ext}"
            n += 1
        vistos.add(candidato.casefold())
        saida.append(candidato)
    return saida


def confere_no_disco(
    anexos: Sequence[Attachment], settings: Settings
) -> tuple[list[tuple[Path, str]], list[str]]:
    """Separa o que está em disco do que sumiu, já com o nome que vai no ZIP.

    Devolve (itens prontos para o `monta_zip`, nomes dos que sumiram). Uma
    função só para o pedido e para a entrega: os dois conferem o disco, e duas
    cópias da mesma conferência acabariam discordando sobre o que é "sumiu".
    """
    nomes = nomes_unicos([nome_seguro(a.original_name, a.stored_name) for a in anexos])
    itens: list[tuple[Path, str]] = []
    sumidos: list[str] = []
    for anexo, nome in zip(anexos, nomes, strict=True):
        try:
            caminho = storage.resolve_path(anexo.s3_key, settings)
        except storage.StorageError:
            sumidos.append(nome)
            continue
        if caminho.is_file():
            itens.append((caminho, nome))
        else:
            sumidos.append(nome)
    return itens, sumidos


def mensagem_de_sumidos(sumidos: list[str]) -> str:
    return f"Arquivo(s) não encontrado(s) no servidor: {', '.join(sumidos)}. Nenhum ZIP foi gerado."


def monta_zip(itens: list[tuple[Path, str]]) -> Path:
    """Grava o ZIP num temporário e devolve o caminho. Síncrono: rode em thread.

    `itens` são pares (arquivo em disco, nome dentro do ZIP), já deduplicados.
    Em qualquer falha o temporário é apagado antes de a exceção subir — quem
    chama nunca herda um ZIP pela metade.
    """
    descritor, caminho = tempfile.mkstemp(prefix="helphs-anexos-", suffix=".zip")
    destino = Path(caminho)
    try:
        with (
            os.fdopen(descritor, "wb") as saida,
            zipfile.ZipFile(saida, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf,
        ):
            for arquivo, nome in itens:
                zf.write(arquivo, arcname=nome)
    except BaseException:
        destino.unlink(missing_ok=True)
        raise
    return destino
