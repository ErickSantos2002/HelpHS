"""
Automatic ticket protocol generator.

Format: HS-YYYY-NNNN  (e.g., HS-2026-0001)

Strategy:
  1. SELECT the last protocol for the current year (ORDER BY protocol DESC LIMIT 1)
     to derive the next sequence number.
  2. The Ticket.protocol column has a UNIQUE constraint, so concurrent inserts that
     land on the same sequence will raise IntegrityError on exactly one of them.
  3. The caller (create_ticket) retries up to MAX_RETRIES times on IntegrityError,
     re-generating the protocol on each attempt.

This approach is correct for typical help-desk traffic.

Melhoria futura, com gatilho
----------------------------
Uma SEQUENCE do PostgreSQL resolveria também a corrida entre inserções
simultâneas, sem depender da retentativa. Não entrou porque exige migration e
lógica de virada de ano, e a retentativa dá conta do volume de hoje.

**O gatilho é o log:** se colisão de protocolo começar a aparecer — o
`IntegrityError` do laço em `create_ticket` —, é hora de trocar.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Ticket

MAX_RETRIES = 5


async def generate_protocol(db: AsyncSession) -> str:
    """Return the next unused protocol string for the current calendar year."""
    year = datetime.now(UTC).year
    prefix = f"HS-{year}-"

    result = await db.execute(
        select(Ticket.protocol)
        .where(Ticket.protocol.like(f"{prefix}%"))
        # Comprimento primeiro, texto depois — NÃO só o texto.
        #
        # A sequência tem 4 dígitos, então a partir do 10.000º chamado do ano o
        # texto e o número discordam: 'HS-2026-9999' > 'HS-2026-10000' é
        # verdade em ordenação de texto. O máximo voltaria a ser 9999 para
        # sempre, o gerador proporia 10000 de novo, as cinco tentativas
        # colidiriam no índice único e nenhum chamado novo poderia ser aberto.
        #
        # Com o comprimento na frente: sufixo mais longo é número maior, e
        # entre sufixos de mesmo comprimento a ordem de texto já é a numérica.
        # Vale nos dois bancos e não levanta em nenhum — um CAST do sufixo para
        # inteiro seria mais direto, mas estouraria no Postgres se uma linha
        # com sufixo não-numérico entrasse por fora do gerador.
        .order_by(func.length(Ticket.protocol).desc(), Ticket.protocol.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()

    if last:
        seq = int(last.rsplit("-", 1)[-1]) + 1
    else:
        seq = 1

    return f"{prefix}{seq:04d}"
