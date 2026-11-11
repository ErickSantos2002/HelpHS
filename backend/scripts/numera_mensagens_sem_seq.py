"""
Numera as mensagens do chat que ficaram SEM `seq` depois da migration
`n0i1j2k3l4m5` — as gravadas por uma imagem que não numera: a antiga, que
seguiu atendendo durante a troca, ou a imagem de recuperação num recuo
(F1-B-04c).

**Avulso, rodado à mão.** Não é migration, não entra no boot do contêiner e
**não é backfill**: o histórico anterior à migration NUNCA é numerado (decisão
definitiva da Sessão 0, 04/11/2026). O corte não é argumento: é o marco que a
própria migration gravou em `chat_seq_corte`. Sem ele, o script não roda.

O que conta como "depois da migration":

- `created_at` a partir do marco: gravada depois, com certeza — numerada.
- `created_at` na JANELA de `MARGEM_DO_CORTE` antes do marco: ambígua. Pode ser
  histórico (gravada antes da migration) ou de uma imagem antiga que montou a
  mensagem antes e só gravou depois. Por padrão NÃO é numerada, e o chamado
  segue no histórico tradicional (`incremental_disponivel` o vê). Numerá-la
  exige `--incluir-janela`, decisão de quem implanta — ela passa a valer
  como mensagem nova para quem sincroniza.

Por que numerar AGORA, e não "no lugar" em que elas comitaram: a tela que
sincroniza por `after_seq` já passou daquele ponto. Um número depois do último
é o que a faz buscá-las; a exibição continua por `created_at`.

Cada chamado é uma transação, com o bloqueio do envio: a linha do chamado é
travada ANTES de reler as mensagens, e um envio simultâneo no mesmo chamado
espera ou é esperado — nunca recebe o mesmo número. Interromper no meio deixa
os chamados já feitos numerados e os outros intactos; rodar de novo continua.

Uso::

    cd backend
    export DATABASE_URL='postgresql+asyncpg://usuario:senha@host:porta/banco'
    python -m scripts.numera_mensagens_sem_seq            # só conta
    python -m scripts.numera_mensagens_sem_seq --aplicar  # grava
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.chat_sequencia import MARGEM_DO_CORTE  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_CORTE = text("SELECT migrada_em FROM chat_seq_corte WHERE id = 1")
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


class SemMarcoDoCorteError(RuntimeError):
    """`chat_seq_corte` vazia: a migration não rodou neste banco."""


async def _corte(motor: AsyncEngine) -> datetime:
    async with motor.connect() as conn:
        corte = (await conn.execute(_CORTE)).scalar_one_or_none()
    if corte is None:
        raise SemMarcoDoCorteError("chat_seq_corte sem a linha da migration n0i1j2k3l4m5.")
    return corte


async def pendentes(url: str) -> dict[str, dict[str, int]]:
    """Por chamado: quantas depois do marco, e quantas na janela ambígua."""
    motor = create_async_engine(url)
    try:
        corte = await _corte(motor)
        async with motor.connect() as conn:
            depois = (await conn.execute(_PENDENTES, {"desde": corte})).all()
            com_janela = (await conn.execute(_PENDENTES, {"desde": corte - MARGEM_DO_CORTE})).all()
    finally:
        await motor.dispose()
    resultado: dict[str, dict[str, int]] = {}
    for chamado, quantas in com_janela:
        resultado[str(chamado)] = {"depois": 0, "janela": int(quantas)}
    for chamado, quantas in depois:
        resultado[str(chamado)]["depois"] = int(quantas)
        resultado[str(chamado)]["janela"] -= int(quantas)
    return resultado


async def numera(url: str, *, incluir_janela: bool = False) -> dict[str, int]:
    """Numera e devolve {chamado: quantas}. Sem `incluir_janela`, só o que tem
    `created_at` a partir do marco."""
    motor = create_async_engine(url)
    resultado: dict[str, int] = {}
    try:
        corte = await _corte(motor)
        desde = corte - MARGEM_DO_CORTE if incluir_janela else corte
        async with motor.connect() as conn:
            chamados = [c for c, _ in (await conn.execute(_PENDENTES, {"desde": desde})).all()]
        for chamado in chamados:
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
    parser.add_argument("--aplicar", action="store_true", help="grava (sem isto, só conta)")
    parser.add_argument(
        "--incluir-janela",
        action="store_true",
        help="numera também a janela ambígua antes do marco (decisão de quem implanta)",
    )
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL não definida. Exporte-a antes de rodar.")
        return 2
    try:
        if not args.aplicar:
            por_chamado = await pendentes(url)
            for chamado, n in por_chamado.items():
                print(f"chamado {chamado}: {n['depois']} depois do marco, {n['janela']} na janela")
            depois = sum(n["depois"] for n in por_chamado.values())
            janela = sum(n["janela"] for n in por_chamado.values())
            print(f"total: {depois} a numerar, {janela} na janela (nada gravado)")
            return 0
        numeradas = await numera(url, incluir_janela=args.incluir_janela)
    except SemMarcoDoCorteError as exc:
        print(f"{exc} Nada foi feito.")
        return 2
    for chamado, quantas in numeradas.items():
        print(f"chamado {chamado}: {quantas} numeradas")
    print(f"total: {sum(numeradas.values())} numeradas em {len(numeradas)} chamado(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
