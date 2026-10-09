"""
Backfill: normaliza `users.email` para minúsculas.

**Avulso, rodado à mão, NUNCA em migration** — regra do projeto: dado
histórico se corrige em script, regra nova é prospectiva. Deve rodar ANTES do
deploy que traz o índice único em `lower(email)`: aquela migration roda no
boot e FALHA se encontrar duplicata por caixa.

O validador de `app/utils/email_normalizado.py` cuida do futuro: depois dele,
nenhuma escrita nova grava maiúscula. Este script cuida do passado — de quem
cadastrou `Fulano@empresa.com` e, com o login normalizando a entrada, não
conseguiria mais entrar se a linha do banco continuasse com o F maiúsculo.

Duplicata por caixa (`Fulano@` E `fulano@` existindo) é **relatada e deixada
como está** — nunca fundida nem apagada: as duas contas podem ter chamados, e
quem decide qual sobrevive é quem lê o relatório. Produção foi conferida em
15/09 e estava limpa; se este script relatar colisão, algo entrou depois.

Importa a normalização do próprio app de propósito: cópia própria da regra
gravaria linha que a API trataria diferente.

Uso::

    cd backend
    export DATABASE_URL='postgresql+asyncpg://usuario:senha@host:porta/banco'

    python -m scripts.normaliza_emails              # dry-run: só relata
    python -m scripts.normaliza_emails --aplicar    # grava

Sem `--aplicar` nada é escrito. O relatório sai igual nos dois modos.
"""

import argparse
import asyncio
import os
import sys
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# O console do Windows abre em cp1252 e estoura em qualquer acento — e este
# script roda na máquina de quem administra, não no container.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.utils.email_normalizado import normaliza_email  # noqa: E402

Mudanca = tuple[Any, str, str]
Colisao = tuple[str, list[str]]


def planeja_normalizacao(
    linhas: Iterable[tuple[Any, str]],
) -> tuple[list[Mudanca], list[Colisao]]:
    """
    Decide o que mudar, sem tocar no banco.

    Pura de propósito, como a irmã do CNPJ: é aqui que mora o risco de um
    descuido fundir contas — sendo pura, dá para prendê-la com teste.

    Returns:
        ``(mudancas, colisoes)`` — ``mudancas`` são triplas
        ``(id, antes, depois)`` só das linhas que realmente mudam (linha já
        minúscula não entra, para o script ser idempotente); ``colisoes`` são
        grupos cujo `lower()` coincide em mais de uma conta — esses NUNCA
        entram em ``mudancas``: normalizar um deles quebraria no índice único
        ou, pior, confundiria duas identidades. Decisão é humana.
    """
    por_minusculo: dict[str, list[tuple[Any, str]]] = defaultdict(list)
    for id_, email in linhas:
        por_minusculo[normaliza_email(email)].append((id_, email))

    mudancas: list[Mudanca] = []
    colisoes: list[Colisao] = []
    for minusculo, grupo in por_minusculo.items():
        if len(grupo) > 1:
            colisoes.append((minusculo, [email for _, email in grupo]))
            continue
        id_, email = grupo[0]
        if email != minusculo:
            mudancas.append((id_, email, minusculo))
    return mudancas, colisoes


async def _main(aplicar: bool) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL não definida — nada a fazer.")
        sys.exit(2)

    modo = "APLICANDO" if aplicar else "DRY-RUN (nada será gravado)"
    print(f"normaliza_emails — {modo}")

    engine = create_async_engine(url)
    try:
        async with engine.connect() as conexao:
            resultado = await conexao.execute(text("SELECT id, email FROM users"))
            linhas = resultado.all()

        mudancas, colisoes = planeja_normalizacao(linhas)

        for minusculo, variantes in colisoes:
            print(f"COLISÃO (não tocada): {minusculo} <- {variantes}")
        for id_, antes, depois in mudancas:
            print(f"normaliza: {antes} -> {depois}  (id={id_})")

        if aplicar and mudancas:
            async with engine.begin() as conexao:
                for id_, _, depois in mudancas:
                    await conexao.execute(
                        text("UPDATE users SET email = :email WHERE id = :id"),
                        {"email": depois, "id": id_},
                    )

        print(
            f"{len(mudancas)} linha(s) {'gravadas' if aplicar else 'a gravar'}, "
            f"{len(colisoes)} colisão(ões) deixadas para decisão humana."
        )
        if colisoes:
            print(
                "⚠️  Com colisão pendente, a migration do índice único vai "
                "FALHAR no boot — resolver antes do deploy."
            )
        if not aplicar and mudancas:
            print("Rode de novo com --aplicar para gravar.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true", help="grava as mudanças")
    argumentos = parser.parse_args()
    asyncio.run(_main(argumentos.aplicar))
