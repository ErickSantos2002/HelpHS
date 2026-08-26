"""
Diagnóstico: mede o que impede as chaves novas de empresa e de aparelho.

**Somente leitura.** Não existe `--aplicar` aqui de propósito: este script não
decide nada, só conta. Roda à mão, na máquina de quem administra, contra o
banco de produção.

Por que ele existe antes das migrations: as duas mudanças combinadas na rodada
de 26/08 criam índices únicos onde hoje não há nenhum —
`UNIQUE (companies.cnpj)` e `UNIQUE (equipments.product_id, serial_number)`.
Índice único **falha na criação** se o banco já tiver duplicata. E migration que
falha, neste projeto, é API que não sobe: o `start.sh` roda
`alembic upgrade head` a cada boot do container. Descobrir a duplicata aqui
custa um relatório; descobrir na migration custa a produção fora do ar.

Uso::

    cd backend
    export DATABASE_URL='postgresql+asyncpg://usuario:senha@host:porta/banco'
    python -m scripts.diagnostico_empresa_aparelho

Os números que importam são os três primeiros blocos. Qualquer um deles maior
que zero significa que a migration correspondente precisa fundir duplicatas
antes de criar o índice — não que a decisão esteja errada.

A comparação de CNPJ é feita sobre os dígitos (`regexp_replace`), não sobre o
texto guardado, para o relatório valer mesmo antes de o `normaliza_cnpj` ter
rodado. Duas linhas com `11.222.333/0001-81` e `11222333000181` são a mesma
empresa e aparecem como duplicata aqui, embora nenhum `UNIQUE` de texto puro as
pegasse.
"""

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# O console do Windows abre em cp1252 e estoura em qualquer acento — e este
# script roda na máquina de quem administra, não no container.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


_SO_DIGITOS = r"regexp_replace(coalesce({col}, ''), '\D', '', 'g')"

_CNPJ_DUPLICADO = f"""
    SELECT {_SO_DIGITOS.format(col="cnpj")} AS doc,
           count(*)            AS quantas,
           array_agg(name)     AS nomes,
           array_agg(id::text) AS ids
      FROM companies
     WHERE coalesce(cnpj, '') <> ''
     GROUP BY 1
    HAVING count(*) > 1
     ORDER BY 2 DESC
"""

_SERIE_DUPLICADA = """
    SELECT p.name                       AS produto,
           upper(trim(e.serial_number)) AS serie,
           count(*)                     AS quantas,
           count(DISTINCT e.owner_id)   AS donos_distintos,
           array_agg(e.id::text)        AS ids
      FROM equipments e
      JOIN products p ON p.id = e.product_id
     WHERE coalesce(trim(e.serial_number), '') <> ''
     GROUP BY 1, 2
    HAVING count(*) > 1
     ORDER BY 3 DESC
"""

# Colisão que o índice atual (owner_id, serial_number) deixa passar e o novo
# também deixaria: mesmo serial em produtos diferentes. Não impede migration
# nenhuma — está aqui para dizer se a premissa "fabricantes repetem série entre
# linhas" é real neste banco ou era só precaução.
_SERIE_ENTRE_PRODUTOS = """
    SELECT upper(trim(serial_number))     AS serie,
           count(DISTINCT product_id)     AS produtos_distintos
      FROM equipments
     WHERE coalesce(trim(serial_number), '') <> ''
     GROUP BY 1
    HAVING count(DISTINCT product_id) > 1
     ORDER BY 2 DESC
"""

_PANORAMA_CLIENTES = f"""
    SELECT count(*)                                                  AS clientes,
           count(*) FILTER (WHERE coalesce(cnpj, '') <> '')          AS com_cnpj,
           count(*) FILTER (WHERE company_id IS NOT NULL)            AS com_empresa,
           count(*) FILTER (WHERE company_id IS NULL
                              AND coalesce(cnpj, '') <> '')          AS cnpj_sem_empresa,
           count(DISTINCT {_SO_DIGITOS.format(col="cnpj")})
                    FILTER (WHERE coalesce(cnpj, '') <> '')          AS cnpjs_distintos
      FROM users
     WHERE role = 'client'
"""

# O caso que motivou a rodada: mais de uma pessoa no mesmo CNPJ. É o número que
# diz quanta gente passa a enxergar chamado de colega quando a visibilidade por
# empresa entrar.
_COLEGAS_POR_CNPJ = f"""
    SELECT {_SO_DIGITOS.format(col="cnpj")} AS doc,
           count(*)                         AS pessoas,
           count(DISTINCT company_id)       AS empresas_vinculadas
      FROM users
     WHERE role = 'client'
       AND coalesce(cnpj, '') <> ''
     GROUP BY 1
    HAVING count(*) > 1
     ORDER BY 2 DESC
"""

_CNPJ_INVALIDO = f"""
    SELECT 'users' AS tabela, id::text, cnpj
      FROM users
     WHERE coalesce(cnpj, '') <> ''
       AND length({_SO_DIGITOS.format(col="cnpj")}) <> 14
     UNION ALL
    SELECT 'companies', id::text, cnpj
      FROM companies
     WHERE coalesce(cnpj, '') <> ''
       AND length({_SO_DIGITOS.format(col="cnpj")}) <> 14
"""


def _titulo(texto: str) -> None:
    print(f"\n── {texto} " + "─" * max(4, 60 - len(texto)))


async def _main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Defina DATABASE_URL antes de rodar.")

    print("Diagnóstico de empresa e aparelho — SOMENTE LEITURA")

    engine = create_async_engine(url)
    bloqueios = 0
    try:
        async with engine.connect() as conn:
            _titulo("1. CNPJ duplicado entre empresas")
            linhas = (await conn.execute(text(_CNPJ_DUPLICADO))).all()
            if linhas:
                bloqueios += len(linhas)
                print(f"  {len(linhas)} CNPJ(s) em mais de uma empresa — BLOQUEIA o UNIQUE:")
                for r in linhas:
                    print(f"    {r.doc}  ({r.quantas}x)  {r.nomes}")
                    print(f"      ids: {r.ids}")
            else:
                print("  nenhum ✅  o UNIQUE(cnpj) sobe limpo")

            _titulo("2. (produto, série) duplicado")
            linhas = (await conn.execute(text(_SERIE_DUPLICADA))).all()
            if linhas:
                bloqueios += len(linhas)
                print(f"  {len(linhas)} par(es) repetido(s) — BLOQUEIA o UNIQUE:")
                for r in linhas:
                    print(
                        f"    {r.produto} / {r.serie}  ({r.quantas} linhas, "
                        f"{r.donos_distintos} dono(s) distinto(s))"
                    )
                    print(f"      ids: {r.ids}")
                print(
                    "\n  Dono distinto > 1 é o caso real de aparelho compartilhado:\n"
                    "  as linhas viram uma só e as pessoas viram usuárias dela.\n"
                    "  Dono distinto = 1 é cadastro repetido do mesmo cliente."
                )
            else:
                print("  nenhum ✅  o UNIQUE(product_id, serial_number) sobe limpo")

            _titulo("3. Mesma série em produtos diferentes")
            linhas = (await conn.execute(text(_SERIE_ENTRE_PRODUTOS))).all()
            if linhas:
                print(f"  {len(linhas)} série(s) usada(s) por mais de um produto:")
                for r in linhas:
                    print(f"    {r.serie}  em {r.produtos_distintos} produtos")
                print("\n  Não bloqueia nada — confirma que a chave composta é a certa.")
            else:
                print("  nenhuma — neste banco a série nunca se repete entre produtos")

            _titulo("4. Panorama dos clientes")
            r = (await conn.execute(text(_PANORAMA_CLIENTES))).one()
            print(f"  clientes ................. {r.clientes}")
            print(f"  com CNPJ preenchido ...... {r.com_cnpj}")
            print(f"  já vinculados a empresa .. {r.com_empresa}")
            print(f"  com CNPJ e SEM empresa ... {r.cnpj_sem_empresa}  ← o backfill resolve")
            print(f"  CNPJs distintos .......... {r.cnpjs_distintos}")

            _titulo("5. Colegas — pessoas no mesmo CNPJ")
            linhas = (await conn.execute(text(_COLEGAS_POR_CNPJ))).all()
            if linhas:
                print(f"  {len(linhas)} CNPJ(s) com mais de uma pessoa:")
                for r in linhas:
                    print(
                        f"    {r.doc}  {r.pessoas} pessoas, "
                        f"{r.empresas_vinculadas} empresa(s) vinculada(s)"
                    )
                print(
                    "\n  É esta gente que passa a ver o chamado do colega na listagem\n"
                    "  quando a visibilidade por empresa entrar."
                )
            else:
                print("  nenhum — hoje ninguém compartilha CNPJ com outra pessoa")

            _titulo("6. CNPJ que não soma 14 dígitos")
            linhas = (await conn.execute(text(_CNPJ_INVALIDO))).all()
            if linhas:
                print(f"  {len(linhas)} linha(s) — o normaliza_cnpj relata e não conserta:")
                for r in linhas:
                    print(f"    {r.tabela}  {r.id}  {r.cnpj!r}")
            else:
                print("  nenhuma ✅")
    finally:
        await engine.dispose()

    print()
    if bloqueios:
        print(
            f"{bloqueios} duplicata(s) precisam de fusão ANTES das migrations.\n"
            "Sem isso o índice único falha na criação e o container não sobe."
        )
    else:
        print("Nenhum bloqueio: as duas migrations podem criar os índices direto.")


if __name__ == "__main__":
    asyncio.run(_main())
