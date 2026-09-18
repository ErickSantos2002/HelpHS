"""
Diagnóstico: quanto o indicador de SLA muda se a violação passar a ser marcada
no momento de resolver.

**Somente leitura.** Não existe `--aplicar` aqui de propósito: este script não
decide nada e não escreve nada. Roda à mão, contra o banco de produção.

O QUE ELE MEDE, E POR QUÊ
--------------------------
`check_breaches` pula o teste de resolução quando o chamado está em estado
terminal, e os dois caminhos que resolvem já colocaram o status em `resolved`
quando o chamam. Consequência: chamado que passou do prazo e ficou **quieto**
até ser resolvido nunca recebe `sla_resolve_breach = True`.

O indicador agregado de SLA conta essa marca. Então ele **subconta** — e
ninguém sabe por quanto. Este script responde exatamente isso, contra o dado
real, para que a proposta ao SGI leve número medido e não estimativa.

A conta de "violado pela data" usa o MESMO deslocamento de pausa que o resto do
sistema: prazo efetivo = `sla_resolve_due_at + sla_total_paused_ms`. Sem ele, o
tempo em que o chamado ficou parado esperando o cliente entraria como atraso da
equipe, e o número sairia inflado.

Uso::

    cd backend
    export DATABASE_URL='postgresql+asyncpg://usuario:senha@host:porta/banco'

    python -m scripts.diagnostico_sla_violado
    python -m scripts.diagnostico_sla_violado --meses 12

O padrão são 6 meses. A janela é sobre `resolved_at`, não sobre a abertura: o
que se mede é o instante da resolução, que é onde a marca deixa de ser gravada.

O QUE OS NÚMEROS SIGNIFICAM
----------------------------
- **marcados hoje**: o que o relatório mostra agora.
- **violados pela data**: o que o relatório mostraria com o conserto.
- **a diferença**: chamados resolvidos fora do prazo que hoje contam como
  dentro. Nenhum deles é erro de digitação — são os que venceram calados.
"""

import argparse
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


# `make_interval` a partir dos milissegundos guardados. A divisão é feita em
# ponto flutuante de propósito: pausa de meio segundo não pode virar zero.
_PRAZO_EFETIVO = (
    "sla_resolve_due_at + make_interval(secs => COALESCE(sla_total_paused_ms, 0) / 1000.0)"
)

_POR_PRIORIDADE = f"""
    SELECT
        priority::text                                              AS prioridade,
        count(*)                                                    AS resolvidos,
        count(*) FILTER (WHERE sla_resolve_breach)                  AS marcados_hoje,
        count(*) FILTER (WHERE resolved_at > {_PRAZO_EFETIVO})      AS violados_pela_data,
        count(*) FILTER (
            WHERE resolved_at > {_PRAZO_EFETIVO} AND NOT sla_resolve_breach
        )                                                           AS passariam_a_contar,
        count(*) FILTER (
            WHERE sla_resolve_breach AND resolved_at <= {_PRAZO_EFETIVO}
        )                                                           AS marcados_mas_no_prazo
    FROM tickets
    WHERE resolved_at IS NOT NULL
      AND resolved_at >= now() - make_interval(months => :meses)
      AND sla_resolve_due_at IS NOT NULL
    GROUP BY priority
    ORDER BY priority
"""

_SEM_PRAZO = """
    SELECT count(*) FROM tickets
    WHERE resolved_at IS NOT NULL
      AND resolved_at >= now() - make_interval(months => :meses)
      AND sla_resolve_due_at IS NULL
"""


def _pct(parte: int, total: int) -> str:
    return f"{parte / total * 100:5.1f}%" if total else "    —"


async def principal() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meses", type=int, default=6, help="janela sobre resolved_at (padrão 6)")
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL não definida. Exporte-a antes de rodar.")
        return 1

    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            linhas = (await conn.execute(text(_POR_PRIORIDADE), {"meses": args.meses})).all()
            sem_prazo = (await conn.execute(text(_SEM_PRAZO), {"meses": args.meses})).scalar_one()
    finally:
        await engine.dispose()

    if not linhas:
        print(f"Nenhum chamado resolvido com prazo de SLA nos últimos {args.meses} meses.")
        return 0

    print(f"Chamados resolvidos nos últimos {args.meses} meses, por prioridade\n")
    print(
        f"{'prioridade':<12} {'resolvidos':>10} {'marcados':>9} {'pela data':>10} "
        f"{'a mais':>7} {'cumprim. hoje':>14} {'cumprim. novo':>14}"
    )
    print("─" * 82)

    t_resolvidos = t_hoje = t_data = t_mais = t_falso = 0
    for r in linhas:
        t_resolvidos += r.resolvidos
        t_hoje += r.marcados_hoje
        t_data += r.violados_pela_data
        t_mais += r.passariam_a_contar
        t_falso += r.marcados_mas_no_prazo
        print(
            f"{r.prioridade:<12} {r.resolvidos:>10} {r.marcados_hoje:>9} "
            f"{r.violados_pela_data:>10} {r.passariam_a_contar:>7} "
            f"{_pct(r.resolvidos - r.marcados_hoje, r.resolvidos):>14} "
            f"{_pct(r.resolvidos - r.violados_pela_data, r.resolvidos):>14}"
        )

    print("─" * 82)
    print(
        f"{'TOTAL':<12} {t_resolvidos:>10} {t_hoje:>9} {t_data:>10} {t_mais:>7} "
        f"{_pct(t_resolvidos - t_hoje, t_resolvidos):>14} "
        f"{_pct(t_resolvidos - t_data, t_resolvidos):>14}"
    )

    print()
    print("O QUE ESTES NÚMEROS DIZEM")
    print()
    print(f"  Chamados resolvidos no período, com prazo de SLA .... {t_resolvidos}")
    print(f"  Contados como violados HOJE ......................... {t_hoje}")
    print(f"  Seriam contados COM O CONSERTO ...................... {t_data}")
    print(f"  Diferença (venceram calados) ........................ {t_mais}")
    if t_resolvidos:
        antes = (t_resolvidos - t_hoje) / t_resolvidos * 100
        depois = (t_resolvidos - t_data) / t_resolvidos * 100
        print()
        print(f"  Cumprimento de SLA divulgado hoje ................... {antes:.1f}%")
        print(f"  Cumprimento de SLA com o conserto ................... {depois:.1f}%")
        print(
            f"  QUEDA NO INDICADOR .................................. {antes - depois:.1f} pontos"
        )

    if t_falso:
        print()
        print(f"  ⚠ {t_falso} chamado(s) estão marcados como violados MAS foram resolvidos")
        print("    dentro do prazo efetivo. O conserto proposto NÃO os desmarca — ele só")
        print("    acrescenta. Vale investigar à parte: pode ser pausa registrada depois")
        print("    da marca, ou prazo editado no meio do atendimento.")

    if sem_prazo:
        print()
        print(f"  {sem_prazo} chamado(s) resolvidos no período não têm prazo de SLA e ficaram")
        print("    fora da conta. São anteriores ao SLA — nem hoje nem depois entram no")
        print("    indicador.")

    print()
    print("Nada foi escrito. Este script só lê.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
