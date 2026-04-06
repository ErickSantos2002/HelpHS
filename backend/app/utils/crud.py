"""
Generic CRUD helpers shared across routers.
"""

import uuid
from typing import TypeVar

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


async def get_or_404(
    db: AsyncSession,
    model: type[T],
    obj_id: uuid.UUID,
    detail: str,
) -> T:
    """Fetch a single row by primary key or raise HTTP 404.

    Args:
        db: Active async database session.
        model: SQLAlchemy mapped model class with an ``id`` column.
        obj_id: UUID primary key to look up.
        detail: Human-readable error message included in the 404 response.

    Returns:
        The mapped model instance.

    Raises:
        HTTPException: 404 if no row matches ``obj_id``.
    """
    result = await db.execute(select(model).where(model.id == obj_id))  # type: ignore[union-attr]
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return obj
