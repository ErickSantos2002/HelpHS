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

This approach is correct for typical help-desk traffic. A dedicated PostgreSQL
sequence would be more efficient under extreme concurrency but adds migration
complexity that is not justified here.
"""

from datetime import UTC, datetime

from sqlalchemy import select
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
        .order_by(Ticket.protocol.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()

    if last:
        seq = int(last.rsplit("-", 1)[-1]) + 1
    else:
        seq = 1

    return f"{prefix}{seq:04d}"
