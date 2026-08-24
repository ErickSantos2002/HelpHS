"""
Backfill: normaliza `users.cnpj` e `companies.cnpj` para 14 dígitos crus.

**Avulso, rodado à mão, NUNCA em migration** — regra do projeto: dado
histórico se corrige em script, regra nova é prospectiva. As migrations rodam
sozinhas no boot do container no EasyPanel; este script não pode supor nada
disso e não é chamado por ninguém.

O validador de `app/utils/documents.py` cuida do futuro: depois dele, nenhuma
escrita nova grava pontuação. Este script cuida do passado — em especial de
`companies.cnpj`, que nasceu como texto livre e guarda o que o admin digitou
com a máscara que o próprio front sugeria.

Importa a normalização de `app.utils.documents` de propósito: se o script
tivesse a sua própria cópia da regra, gravaria linhas que a API recusaria
depois.

Uso::

    cd backend
    export DATABASE_URL='postgresql+asyncpg://usuario:senha@host:porta/banco'

    python -m scripts.normaliza_cnpj              # dry-run: só relata
    python -m scripts.normaliza_cnpj --aplicar    # grava

Sem `--aplicar` nada é escrito. O relatório sai igual nos dois modos, então dá
para conferir antes e comparar depois.

Linha que não dá para normalizar (não soma 14 dígitos) é **relatada e deixada
como está**. Nunca apagada: um script de limpeza que descarta o que não entende
é pior que o problema que veio consertar. Quem decide o que fazer com ela é
quem lê o relatório.
"""

import argparse
import asyncio
import os
import sys
from collections.abc import Iterable
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# O console do Windows abre em cp1252 e estoura em qualquer acento — e este
# script roda na máquina de quem administra, não no container. Sem isto o
# relatório morre com UnicodeEncodeError antes de mostrar a primeira linha.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.utils.documents import normaliza_cnpj_opcional  # noqa: E402

Mudanca = tuple[Any, str, str | None]
Problema = tuple[Any, str]


def planeja_normalizacao(
    linhas: Iterable[tuple[Any, str | None]],
) -> tuple[list[Mudanca], list[Problema]]:
    """
    Decide o que mudar, sem tocar no banco.

    Separada da parte que grava porque é aqui que mora o risco: é esta função
    que poderia, com um descuido, propor apagar CNPJ bom. Sendo pura, dá para
    prendê-la com teste.

    Args:
        linhas: pares ``(id, cnpj)`` como vieram do banco.

    Returns:
        ``(mudancas, problemas)`` — ``mudancas`` são triplas
        ``(id, antes, depois)`` só das linhas que realmente mudam (linha já
        normalizada não entra, para o script ser idempotente); ``problemas``
        são pares ``(id, valor)`` que não dá para normalizar.
    """
    mudancas: list[Mudanca] = []
    problemas: list[Problema] = []

    for linha_id, valor in linhas:
        if valor is None:
            continue
        try:
            novo = normaliza_cnpj_opcional(valor)
        except ValueError:
            problemas.append((linha_id, valor))
            continue
        if novo != valor:
            mudancas.append((linha_id, valor, novo))

    return mudancas, problemas


def _relata(tabela: str, mudancas: list[Mudanca], problemas: list[Problema]) -> None:
    print(f"\n── {tabela} " + "─" * (58 - len(tabela)))
    print(f"  a normalizar: {len(mudancas)}")
    print(f"  sem conserto automático: {len(problemas)}")

    for linha_id, antes, depois in mudancas:
        print(f"    {linha_id}  {antes!r} -> {depois!r}")

    if problemas:
        print("\n  Deixadas como estão (não somam 14 dígitos) — decida à mão:")
        for linha_id, valor in problemas:
            print(f"    {linha_id}  {valor!r}")


async def _processa(engine, tabela: str, aplicar: bool) -> int:
    async with engine.connect() as conn:
        linhas = (await conn.execute(text(f"SELECT id, cnpj FROM {tabela}"))).all()  # noqa: S608
        mudancas, problemas = planeja_normalizacao([(r.id, r.cnpj) for r in linhas])
        _relata(tabela, mudancas, problemas)

        if aplicar and mudancas:
            for linha_id, _antes, depois in mudancas:
                await conn.execute(
                    text(f"UPDATE {tabela} SET cnpj = :cnpj WHERE id = :id"),  # noqa: S608
                    {"cnpj": depois, "id": linha_id},
                )
            await conn.commit()
            print(f"  OK: {len(mudancas)} linha(s) gravada(s).")

    return len(mudancas)


async def _main(aplicar: bool) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Defina DATABASE_URL antes de rodar.")

    modo = "APLICANDO" if aplicar else "DRY-RUN (nada será gravado)"
    print(f"Normalização de CNPJ — {modo}")

    engine = create_async_engine(url)
    try:
        total = 0
        for tabela in ("users", "companies"):
            total += await _processa(engine, tabela, aplicar)
    finally:
        await engine.dispose()

    print()
    if not aplicar and total:
        print(f"{total} linha(s) mudariam. Rode de novo com --aplicar para gravar.")
    elif not total:
        print("Nada a fazer — tudo já está normalizado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="grava as mudanças; sem esta flag o script só relata",
    )
    asyncio.run(_main(parser.parse_args().aplicar))
