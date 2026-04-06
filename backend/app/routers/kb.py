"""
Base de Conhecimento — CRUD de artigos.

Endpoints:
  GET    /kb/articles              — lista/busca (todos autenticados)
  POST   /kb/articles              — criar (admin/technician)
  GET    /kb/articles/{id}         — ver artigo (todos autenticados, incrementa view_count)
  PATCH  /kb/articles/{id}         — editar (admin/technician)
  DELETE /kb/articles/{id}         — arquivar (admin)
  POST   /kb/articles/{id}/feedback — helpful/not_helpful (todos autenticados)
"""

import re
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import authorize, get_current_user
from app.models.models import (
    KBArticle,
    KBArticleStatus,
    User,
    UserRole,
)
from app.schemas.kb import (
    KBArticleCreate,
    KBArticleListResponse,
    KBArticleResponse,
    KBArticleUpdate,
    KBFeedbackPayload,
)

router = APIRouter(tags=["Knowledge Base"])


# ── Helpers ───────────────────────────────────────────────────


def _slugify(text: str) -> str:
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


async def _unique_slug(base: str, db: AsyncSession, exclude_id: uuid.UUID | None = None) -> str:
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


def _to_response(article: KBArticle) -> KBArticleResponse:
    return KBArticleResponse(
        id=article.id,
        title=article.title,
        content=article.content,
        slug=article.slug,
        category=article.category,
        tags=article.tags or [],
        status=article.status,
        author_id=article.author_id,
        author_name=article.author.name if article.author else "",
        view_count=article.view_count,
        helpful=article.helpful,
        not_helpful=article.not_helpful,
        created_at=article.created_at,
        updated_at=article.updated_at,
    )


async def _get_article_or_404(article_id: uuid.UUID, db: AsyncSession) -> KBArticle:
    result = await db.execute(
        select(KBArticle).options(selectinload(KBArticle.author)).where(KBArticle.id == article_id)
    )
    article = result.scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return article


# ── Endpoints ─────────────────────────────────────────────────


@router.get("/kb/articles", response_model=KBArticleListResponse)
async def list_articles(
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None),
    status_filter: KBArticleStatus | None = Query(default=None, alias="status"),
) -> KBArticleListResponse:
    is_staff = actor.role in (UserRole.admin, UserRole.technician)

    base = select(KBArticle).options(selectinload(KBArticle.author))

    # Clients can only see published articles
    if not is_staff:
        base = base.where(KBArticle.status == KBArticleStatus.published)
    elif status_filter is not None:
        base = base.where(KBArticle.status == status_filter)

    if category:
        base = base.where(KBArticle.category == category)

    if search:
        term = f"%{search}%"
        base = base.where(or_(KBArticle.title.ilike(term), KBArticle.content.ilike(term)))

    base = base.order_by(KBArticle.updated_at.desc())

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = await db.execute(base.offset(offset).limit(limit))
    articles = rows.scalars().all()

    return KBArticleListResponse(
        items=[_to_response(a) for a in articles],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/kb/articles", response_model=KBArticleResponse, status_code=status.HTTP_201_CREATED)
async def create_article(
    body: KBArticleCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> KBArticleResponse:
    slug = await _unique_slug(_slugify(body.title), db)
    now = datetime.now(UTC)

    article = KBArticle(
        id=uuid.uuid4(),
        title=body.title,
        content=body.content,
        slug=slug,
        category=body.category,
        tags=body.tags,
        status=body.status,
        author_id=actor.id,
        view_count=0,
        helpful=0,
        not_helpful=0,
        created_at=now,
        updated_at=now,
    )
    db.add(article)
    await db.commit()

    result = await db.execute(
        select(KBArticle).options(selectinload(KBArticle.author)).where(KBArticle.id == article.id)
    )
    article = result.scalar_one()
    return _to_response(article)


@router.get("/kb/articles/{article_id}", response_model=KBArticleResponse)
async def get_article(
    article_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> KBArticleResponse:
    article = await _get_article_or_404(article_id, db)
    is_staff = actor.role in (UserRole.admin, UserRole.technician)

    if not is_staff and article.status != KBArticleStatus.published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    # Increment view count without loading the full object again
    await db.execute(
        update(KBArticle)
        .where(KBArticle.id == article_id)
        .values(view_count=KBArticle.view_count + 1)
    )
    await db.commit()

    article.view_count += 1
    return _to_response(article)


@router.patch("/kb/articles/{article_id}", response_model=KBArticleResponse)
async def update_article(
    article_id: uuid.UUID,
    body: KBArticleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> KBArticleResponse:
    article = await _get_article_or_404(article_id, db)
    changes = body.model_dump(exclude_unset=True)

    if "title" in changes:
        new_slug = await _unique_slug(_slugify(changes["title"]), db, exclude_id=article_id)
        article.slug = new_slug

    for field, value in changes.items():
        setattr(article, field, value)

    article.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(article)

    result = await db.execute(
        select(KBArticle).options(selectinload(KBArticle.author)).where(KBArticle.id == article_id)
    )
    article = result.scalar_one()
    return _to_response(article)


@router.delete("/kb/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_article(
    article_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin))],
) -> None:
    article = await _get_article_or_404(article_id, db)
    article.status = KBArticleStatus.archived
    article.updated_at = datetime.now(UTC)
    await db.commit()


@router.post("/kb/articles/{article_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def article_feedback(
    article_id: uuid.UUID,
    body: KBFeedbackPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> None:
    result = await db.execute(select(KBArticle).where(KBArticle.id == article_id))
    article = result.scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    if body.helpful:
        await db.execute(
            update(KBArticle)
            .where(KBArticle.id == article_id)
            .values(helpful=KBArticle.helpful + 1)
        )
    else:
        await db.execute(
            update(KBArticle)
            .where(KBArticle.id == article_id)
            .values(not_helpful=KBArticle.not_helpful + 1)
        )
    await db.commit()
