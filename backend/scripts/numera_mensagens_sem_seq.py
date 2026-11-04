"""
Numera as mensagens do chat que ficaram SEM `seq` depois da migration
`n0i1j2k3l4m5` — as gravadas por uma imagem antiga do backend durante um
rollback de aplicação que manteve a migration, ou por uma instância antiga
que ainda servia enquanto a nova subia (F1-B-04c).

**Avulso, rodado à mão.** Não é migration, não entra no boot do container e
não é backfill do legado: mensagem anterior à migration continua sem número,
de propósito (regra do projeto). O corte é `--desde`, o instante em que a
migration rodou em produção — o script recusa rodar sem ele.

Por que numerar AGORA, e não "no lugar" em que elas comitaram: a tela que
sincroniza por `after_seq` já passou daquele ponto. Um número novo, depois do
último que existe, é o que a faz buscá-las na próxima releitura; é também a
verdade sobre elas — do ponto de vista de quem sincroniza, elas ficaram
visíveis agora. A exibição continua por `created_at`, no lugar de sempre.

Cada chamado é uma transação, com o mesmo bloqueio do envio: o UPDATE relativo
do contador trava a linha do chamado, e um envio simultâneo no mesmo chamado
espera ou é esperado — nunca recebe o mesmo número.

Uso::

    cd backend
    export DATABASE_URL='postgresql+asyncpg://usuario:senha@host:porta/banco'
    python -m scripts.numera_mensagens_sem_seq --desde 2026-11-10T14:00:00+00:00
    python -m scripts.numera_mensagens_sem_seq --desde 2026-11-10T14:00:00+00:00 --aplicar

Sem `--aplicar` nada é escrito: o script só conta, por chamado, o que faria.
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_PENDENTES = text(
    "SELECT ticket_id, count(*) FROM chat_messages "
    "WHERE seq IS NULL AND created_at >= :desde GROUP BY ticket_id ORDER BY ticket_id"
)
# O contador primeiro: é ele que trava o chamado. As mensagens são relidas
# DEPOIS do bloqueio — uma que tenha chegado sem número entre a contagem e
# aqui entra no mesmo lote, e o incremento é do tamanho do que será numerado.
_TRAVA = text("SELECT chat_seq FROM tickets WHERE id = :t FOR NO KEY UPDATE")
_DO_CHAMADO = text(
    "SELECT id FROM chat_messages WHERE ticket_id = :t AND seq IS NULL "
    "AND created_at >= :desde ORDER BY created_at, id"
)
_AVANCA = text("UPDATE tickets SET chat_seq = chat_seq + :n WHERE id = :t RETURNING chat_seq")
_NUMERA = text("UPDATE chat_messages SET seq = :s WHERE id = :m")


async def numera(url: str, desde: datetime, *, aplicar: bool) -> dict[str, int]:
    """Devolve {chamado: quantas} — numeradas com `aplicar`, a numerar sem."""
    motor = create_async_engine(url)
    resultado: dict[str, int] = {}
    try:
        async with motor.connect() as conn:
            pendentes = (await conn.execute(_PENDENTES, {"desde": desde})).all()
        for chamado, quantas in pendentes:
            if not aplicar:
                resultado[str(chamado)] = int(quantas)
                continue
            async with motor.begin() as conn:
                await conn.execute(_TRAVA, {"t": chamado})
                ids = [
                    r[0] for r in (await conn.execute(_DO_CHAMADO, {"t": chamado, "desde": desde}))
                ]
                if not ids:
                    continue
                ultimo = (await conn.execute(_AVANCA, {"n": len(ids), "t": chamado})).scalar_one()
                for numero, mid in enumerate(ids, start=ultimo - len(ids) + 1):
                    await conn.execute(_NUMERA, {"s": numero, "m": mid})
            resultado[str(chamado)] = len(ids)
    finally:
        await motor.dispose()
    return resultado


async def principal() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--desde",
        required=True,
        help="instante ISO-8601 COM fuso em que a migration n0i1j2k3l4m5 rodou",
    )
    parser.add_argument("--aplicar", action="store_true", help="grava (sem isto, só conta)")
    args = parser.parse_args()

    desde = datetime.fromisoformat(args.desde)
    if desde.tzinfo is None:
        print("--desde precisa de fuso (ex.: 2026-11-10T14:00:00+00:00).")
        return 2
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL não definida. Exporte-a antes de rodar.")
        return 2

    por_chamado = await numera(url, desde, aplicar=args.aplicar)
    verbo = "numeradas" if args.aplicar else "a numerar (nada gravado)"
    for chamado, quantas in por_chamado.items():
        print(f"chamado {chamado}: {quantas} {verbo}")
    print(f"total: {sum(por_chamado.values())} {verbo} em {len(por_chamado)} chamado(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
