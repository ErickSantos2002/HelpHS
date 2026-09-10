"""
O slug do artigo da Base de Conhecimento — um lugar só que o escreve.

Morava em `app/routers/kb.py`, e a importação dos manuais precisou dele. Script
não importa de router, e a alternativa era uma segunda cópia da regra: duas
versões de "slug único" divergem na primeira vez que alguém mexer em uma, e o
sintoma seria `IntegrityError` na importação ou dois artigos disputando a
mesma URL. Mesmo motivo do `app/utils/history.py`.
"""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import KBArticle


def slugifica(text: str) -> str:
    """Convert title to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[àáâãä]", "a", text)
    text = re.sub(r"[èéêë]", "e", text)
    text = re.sub(r"[ìíîï]", "i", text)
    text = re.sub(r"[òóôõö]", "o", text)
    text = re.sub(r"[ùúûü]", "u", text)
    text = re.sub(r"[ç]", "c", text)
    text = re.sub(r"[ñ]", "n", text)
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text)
    return text[:200].strip("-")


async def slug_unico(base: str, db: AsyncSession, exclude_id: uuid.UUID | None = None) -> str:
    """Ensure slug is unique by appending a counter if needed."""
    slug = base
    counter = 1
    while True:
        q = select(KBArticle).where(KBArticle.slug == slug)
        if exclude_id:
            q = q.where(KBArticle.id != exclude_id)
        result = await db.execute(q)
        if result.scalar_one_or_none() is None:
            return slug
        slug = f"{base}-{counter}"
        counter += 1
