"""
Funde empresas que compartilham o mesmo CNPJ, deixando uma por documento.

**Avulso, rodado à mão, NUNCA em migration** — regra do projeto: dado
histórico se corrige em script, regra nova é prospectiva.

Existe porque o `UNIQUE (companies.cnpj)` não pode ser criado enquanto houver
duplicata: índice único falha na criação, e migration que falha aqui é API que
não sobe. O `diagnostico_empresa_aparelho.py` conta as duplicatas; este resolve.

Funde em vez de apagar, e a diferença não é acadêmica: `company_notes` tem
`ON DELETE CASCADE`. Apagar a empresa duplicada **apaga as notas dela junto**,
em silêncio. E `users.company_id` é `ON DELETE SET NULL`: os clientes seriam
soltos sem ninguém avisar. Movendo antes de apagar, nada se perde mesmo que a
duplicata "vazia" não estivesse tão vazia quanto o relatório sugeria.

Quem sobrevive: a empresa com mais conteúdo (clientes + notas); empatando, a
mais antiga. O critério é o que preserva mais história sem precisar de
julgamento humano linha a linha.

Uso::

    cd backend
    export DATABASE_URL='postgresql+asyncpg://usuario:senha@host:porta/banco'

    python -m scripts.funde_empresas_duplicadas              # dry-run
    python -m scripts.funde_empresas_duplicadas --aplicar    # grava

Sem `--aplicar` nada é escrito. O plano sai igual nos dois modos, então dá
para conferir antes e comparar depois.

Duplicatas em GRUPOS diferentes são relatadas com destaque e **não são
fundidas**: juntar empresas de grupos distintos muda a que grupo os clientes
pertencem, e isso é decisão de quem conhece a operação, não de um script.
"""

import argparse
import asyncio
import os
import sys
from collections.abc import Iterable, Sequence
from typing import Any, NamedTuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# O console do Windows abre em cp1252 e estoura em qualquer acento — e este
# script roda na máquina de quem administra, não no container.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class Empresa(NamedTuple):
    id: Any
    doc: str
    nome: str
    group_id: Any
    criada_em: Any
    clientes: int
    notas: int


class Fusao(NamedTuple):
    doc: str
    sobrevivente: Empresa
    absorvidas: list[Empresa]


_LEVANTAMENTO = r"""
    WITH duplicadas AS (
        SELECT regexp_replace(coalesce(cnpj, ''), '\D', '', 'g') AS doc
          FROM companies
         WHERE coalesce(cnpj, '') <> ''
         GROUP BY 1
        HAVING count(*) > 1
    )
    SELECT c.id,
           regexp_replace(coalesce(c.cnpj, ''), '\D', '', 'g')              AS doc,
           c.name                                                          AS nome,
           c.group_id,
           c.created_at                                                    AS criada_em,
           (SELECT count(*) FROM users u WHERE u.company_id = c.id)         AS clientes,
           (SELECT count(*) FROM company_notes n WHERE n.company_id = c.id) AS notas
      FROM companies c
      JOIN duplicadas d
        ON d.doc = regexp_replace(coalesce(c.cnpj, ''), '\D', '', 'g')
     ORDER BY doc, c.created_at
"""


def planeja_fusao(empresas: Iterable[Empresa]) -> tuple[list[Fusao], list[list[Empresa]]]:
    """
    Decide quem sobrevive em cada CNPJ, sem tocar no banco.

    Separada da parte que grava porque é aqui que mora o risco: é esta função
    que poderia, com um descuido, eleger a empresa errada e mandar as notas de
    um cliente real para o lugar errado. Sendo pura, dá para prendê-la com
    teste.

    Returns:
        ``(fusoes, recusadas)`` — ``recusadas`` são os grupos que abrangem mais
        de um `group_id` e por isso ficam de fora.
    """
    por_doc: dict[str, list[Empresa]] = {}
    for e in empresas:
        por_doc.setdefault(e.doc, []).append(e)

    fusoes: list[Fusao] = []
    recusadas: list[list[Empresa]] = []

    for doc, linhas in por_doc.items():
        if len(linhas) < 2:
            continue
        if len({e.group_id for e in linhas}) > 1:
            recusadas.append(linhas)
            continue
        # Mais conteúdo primeiro; empatando, a mais antiga.
        ordenadas = sorted(linhas, key=lambda e: (-(e.clientes + e.notas), e.criada_em))
        fusoes.append(Fusao(doc=doc, sobrevivente=ordenadas[0], absorvidas=ordenadas[1:]))

    return fusoes, recusadas


def _relata(fusoes: Sequence[Fusao], recusadas: Sequence[Sequence[Empresa]]) -> None:
    for f in fusoes:
        print(f"\n── CNPJ {f.doc} " + "─" * max(4, 44 - len(f.doc)))
        s = f.sobrevivente
        print(f"  FICA     {s.id}  {s.nome!r}  {s.clientes} cliente(s), {s.notas} nota(s)")
        for a in f.absorvidas:
            destino = ""
            if a.clientes or a.notas:
                destino = f"  -> move {a.clientes} cliente(s) e {a.notas} nota(s)"
            print(f"  APAGA    {a.id}  {a.nome!r}{destino}")

    for grupo in recusadas:
        print(f"\n⚠️  CNPJ {grupo[0].doc}: empresas em GRUPOS diferentes — não fundidas")
        for e in grupo:
            marca = "casca vazia" if not (e.clientes or e.notas) else "TEM CONTEUDO"
            print(f"     {e.id}  {e.nome!r}")
            print(
                f"        grupo {e.group_id}  |  "
                f"{e.clientes} cliente(s), {e.notas} nota(s)  -> {marca}"
            )
        print("     Juntar mudaria o grupo dos clientes. Decida à mão.")


async def _aplica(conn, fusoes: Sequence[Fusao]) -> None:
    for f in fusoes:
        alvos = [a.id for a in f.absorvidas]
        # Move ANTES de apagar: company_notes é ON DELETE CASCADE e users é
        # SET NULL. Na ordem inversa, nota vira lixo e cliente vira órfão.
        await conn.execute(
            text("UPDATE users SET company_id = :fica WHERE company_id = ANY(:alvos)"),
            {"fica": f.sobrevivente.id, "alvos": alvos},
        )
        await conn.execute(
            text("UPDATE company_notes SET company_id = :fica WHERE company_id = ANY(:alvos)"),
            {"fica": f.sobrevivente.id, "alvos": alvos},
        )
        await conn.execute(
            text("DELETE FROM companies WHERE id = ANY(:alvos)"),
            {"alvos": alvos},
        )
    await conn.commit()


async def _main(aplicar: bool) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Defina DATABASE_URL antes de rodar.")

    modo = "APLICANDO" if aplicar else "DRY-RUN (nada será gravado)"
    print(f"Fusão de empresas duplicadas — {modo}")

    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            linhas = (await conn.execute(text(_LEVANTAMENTO))).all()
            empresas = [
                Empresa(r.id, r.doc, r.nome, r.group_id, r.criada_em, r.clientes, r.notas)
                for r in linhas
            ]
            fusoes, recusadas = planeja_fusao(empresas)
            _relata(fusoes, recusadas)

            if not fusoes and not recusadas:
                print("\nNada a fazer — nenhum CNPJ repetido entre empresas.")
                return

            if aplicar and fusoes:
                await _aplica(conn, fusoes)
                apagadas = sum(len(f.absorvidas) for f in fusoes)
                print(f"\nOK: {apagadas} empresa(s) absorvida(s) em {len(fusoes)} CNPJ(s).")
            elif fusoes:
                apagadas = sum(len(f.absorvidas) for f in fusoes)
                print(
                    f"\n{apagadas} empresa(s) seriam apagadas. "
                    "Rode de novo com --aplicar para gravar."
                )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="grava as mudanças; sem esta flag o script só relata",
    )
    asyncio.run(_main(parser.parse_args().aplicar))
