"""
Base de Conhecimento — CRUD de artigos.

Endpoints:
  GET    /kb/articles              — lista/busca (todos autenticados)
  POST   /kb/articles              — criar (admin/technician)
  GET    /kb/articles/{id}         — ver artigo (todos autenticados, incrementa view_count)
  PATCH  /kb/articles/{id}         — editar (admin/technician)
  DELETE /kb/articles/{id}         — arquivar (admin)
  POST   /kb/articles/{id}/feedback — helpful/not_helpful (todos autenticados)
  GET    /kb/articles/{id}/comments — listar comentários (todos autenticados)
  POST   /kb/articles/{id}/comments — comentar (todos autenticados)
  DELETE /kb/comments/{id}         — excluir (admin/technician qualquer um; cliente só o próprio)
"""

import re
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import authorize, get_current_user
from app.models.models import (
    Equipment,
    KBArticle,
    KBArticleStatus,
    KBComment,
    Product,
    Ticket,
    User,
    UserRole,
    kb_article_products,
)
from app.schemas.kb import (
    KBArticleCreate,
    KBArticleListResponse,
    KBArticleProduct,
    KBArticleResponse,
    KBArticleUpdate,
    KBCommentCreate,
    KBCommentListResponse,
    KBCommentResponse,
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
        products=[
            KBArticleProduct(id=p.id, name=p.name) for p in (article.products or [])
        ],
    )


async def _ticket_product_id(ticket: Ticket, db: AsyncSession) -> uuid.UUID | None:
    """Produto do ticket — o campo Produto ou, na falta dele, o do equipamento."""
    if ticket.product_id:
        return ticket.product_id
    if ticket.equipment_id:
        row = await db.execute(
            select(Equipment.product_id).where(Equipment.id == ticket.equipment_id)
        )
        return row.scalar_one_or_none()
    return None


async def _set_article_products(
    article: KBArticle, product_ids: list[uuid.UUID], db: AsyncSession
) -> None:
    """Vincula os produtos ao artigo. Lista vazia = vale para todos os produtos."""
    if not product_ids:
        article.products = []
        return

    unique_ids = list(dict.fromkeys(product_ids))
    rows = await db.execute(select(Product).where(Product.id.in_(unique_ids)))
    found = list(rows.scalars().all())
    if len(found) != len(unique_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Um ou mais produtos selecionados não existem mais.",
        )
    article.products = found


async def _get_article_or_404(article_id: uuid.UUID, db: AsyncSession) -> KBArticle:
    result = await db.execute(
        select(KBArticle).options(selectinload(KBArticle.author), selectinload(KBArticle.products)).where(KBArticle.id == article_id)
    )
    article = result.scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artigo não encontrado. Ele pode ter sido excluído ou arquivado.")
    return article


# ── Endpoints ─────────────────────────────────────────────────


@router.get("/kb/articles/suggestions", response_model=KBArticleListResponse)
async def suggest_articles_for_ticket(
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    ticket_id: uuid.UUID = Query(...),
    limit: int = Query(default=5, ge=1, le=20),
) -> KBArticleListResponse:
    """
    Artigos publicados relevantes para o ticket, do mais específico ao mais amplo.

    O artigo entra por produto OU por categoria — basta um dos dois casar:
      1. produto do ticket + mesma categoria
      2. produto do ticket, em qualquer categoria
      3. mesma categoria, em qualquer produto (inclui os que valem para todos)
      4. palavra-chave do título (rede de segurança)

    O produto vem do campo Produto do ticket; se estiver vazio, do equipamento
    escolhido pelo cliente.
    """
    ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = ticket_result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket não encontrado. Ele pode ter sido excluído.",
        )

    # Cliente só recebe sugestões do próprio chamado
    if actor.role == UserRole.client and ticket.creator_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para acessar este ticket.",
        )

    product_id = await _ticket_product_id(ticket, db)

    words = [w for w in ticket.title.lower().split() if len(w) > 3]
    category_val = (
        ticket.category.value if hasattr(ticket.category, "value") else str(ticket.category)
    )

    base = (
        select(KBArticle)
        .options(selectinload(KBArticle.author), selectinload(KBArticle.products))
        .where(KBArticle.status == KBArticleStatus.published)
    )

    keyword_filter = None
    if words:
        keyword_filter = or_(*[KBArticle.title.ilike(f"%{w}%") for w in words[:5]])

    same_category = KBArticle.category == category_val
    same_product = (
        KBArticle.id.in_(
            select(kb_article_products.c.article_id).where(
                kb_article_products.c.product_id == product_id
            )
        )
        if product_id
        else None
    )

    # Camadas em ordem de relevância; cada uma completa o que faltar
    layers = []
    if same_product is not None:
        layers.append(and_(same_product, same_category))
        layers.append(same_product)
    layers.append(same_category)
    if keyword_filter is not None:
        layers.append(keyword_filter)

    results: list[KBArticle] = []
    seen_ids: set[uuid.UUID] = set()

    for condition in layers:
        needed = limit - len(results)
        if needed <= 0:
            break
        query = base.where(condition)
        if seen_ids:
            query = query.where(KBArticle.id.notin_(seen_ids))
        rows = await db.execute(query.limit(needed))
        found = list(rows.scalars().all())
        results.extend(found)
        seen_ids.update(a.id for a in found)

    return KBArticleListResponse(
        items=[_to_response(a) for a in results],
        total=len(results),
        limit=limit,
        offset=0,
    )


@router.get("/kb/articles", response_model=KBArticleListResponse)
async def list_articles(
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None),
    product_id: uuid.UUID | None = Query(default=None),
    status_filter: KBArticleStatus | None = Query(default=None, alias="status"),
) -> KBArticleListResponse:
    is_staff = actor.role in (UserRole.admin, UserRole.technician)

    base = select(KBArticle).options(selectinload(KBArticle.author), selectinload(KBArticle.products))

    # Clients can only see published articles
    if not is_staff:
        base = base.where(KBArticle.status == KBArticleStatus.published)
    elif status_filter is not None:
        base = base.where(KBArticle.status == status_filter)

    if category:
        base = base.where(KBArticle.category == category)

    if product_id:
        # Artigos do produto + os que valem para todos (sem produto vinculado)
        base = base.where(
            or_(
                KBArticle.id.in_(
                    select(kb_article_products.c.article_id).where(
                        kb_article_products.c.product_id == product_id
                    )
                ),
                ~KBArticle.id.in_(select(kb_article_products.c.article_id)),
            )
        )

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
        tags=list(dict.fromkeys(body.tags)),
        status=body.status,
        author_id=actor.id,
        view_count=0,
        helpful=0,
        not_helpful=0,
        created_at=now,
        updated_at=now,
    )
    db.add(article)
    await _set_article_products(article, body.product_ids, db)
    await db.commit()

    result = await db.execute(
        select(KBArticle).options(selectinload(KBArticle.author), selectinload(KBArticle.products)).where(KBArticle.id == article.id)
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artigo não encontrado. Ele pode ter sido excluído ou arquivado.")

    await db.execute(
        update(KBArticle)
        .where(KBArticle.id == article_id)
        .values(view_count=KBArticle.view_count + 1)
    )
    await db.commit()

    # Reload after commit — session expires all objects on commit, and accessing
    # expired attributes in async context raises MissingGreenlet.
    result = await db.execute(
        select(KBArticle).options(selectinload(KBArticle.author), selectinload(KBArticle.products)).where(KBArticle.id == article_id)
    )
    return _to_response(result.scalar_one())


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

    # product_ids não é coluna: vira vínculo na tabela de ligação
    product_ids = changes.pop("product_ids", None)
    if product_ids is not None:
        await _set_article_products(article, product_ids, db)

    for field, value in changes.items():
        if field == "tags" and isinstance(value, list):
            value = list(dict.fromkeys(value))
        setattr(article, field, value)

    article.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(article)

    result = await db.execute(
        select(KBArticle).options(selectinload(KBArticle.author), selectinload(KBArticle.products)).where(KBArticle.id == article_id)
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


def _to_comment_response(
    comment: KBComment, replies: list[KBComment] | None = None
) -> KBCommentResponse:
    return KBCommentResponse(
        id=comment.id,
        article_id=comment.article_id,
        author_id=comment.author_id,
        author_name=comment.author.name if comment.author else "Usuário removido",
        author_role=comment.author.role.value if comment.author else "",
        content=comment.content,
        parent_id=comment.parent_id,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        replies=[_to_comment_response(r) for r in (replies or [])],
    )


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artigo não encontrado. Ele pode ter sido excluído ou arquivado.")

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


# ── Comments ──────────────────────────────────────────────────


@router.get("/kb/articles/{article_id}/comments", response_model=KBCommentListResponse)
async def list_comments(
    article_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> KBCommentListResponse:
    """Return all top-level comments (with nested replies) for an article."""
    await _get_article_or_404(article_id, db)

    rows = await db.execute(
        select(KBComment)
        .options(selectinload(KBComment.author))
        .where(KBComment.article_id == article_id)
        .order_by(KBComment.created_at.desc())
    )
    all_comments = list(rows.scalars().all())

    replies_map: dict[uuid.UUID, list[KBComment]] = {}
    top_level: list[KBComment] = []
    for c in all_comments:
        if c.parent_id is not None:
            replies_map.setdefault(c.parent_id, []).append(c)
        else:
            top_level.append(c)

    return KBCommentListResponse(
        items=[_to_comment_response(c, replies_map.get(c.id, [])) for c in top_level],
        total=len(top_level),
    )


@router.post(
    "/kb/articles/{article_id}/comments",
    response_model=KBCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(
    article_id: uuid.UUID,
    body: KBCommentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> KBCommentResponse:
    """Create a comment or reply on an article."""
    await _get_article_or_404(article_id, db)

    if body.parent_id is not None:
        parent_result = await db.execute(
            select(KBComment).where(
                KBComment.id == body.parent_id, KBComment.article_id == article_id
            )
        )
        if parent_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="O comentário que você está respondendo não existe mais."
            )
        # Only allow 1 level of nesting — replies cannot be replied to
        parent_check = await db.execute(select(KBComment).where(KBComment.id == body.parent_id))
        parent = parent_check.scalar_one()
        if parent.parent_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Não é possível responder a uma resposta. Comente na mensagem original.",
            )

    now = datetime.now(UTC)
    comment = KBComment(
        id=uuid.uuid4(),
        article_id=article_id,
        author_id=actor.id,
        content=body.content.strip(),
        parent_id=body.parent_id,
        created_at=now,
        updated_at=now,
    )
    db.add(comment)
    await db.commit()

    result = await db.execute(
        select(KBComment)
        .options(selectinload(KBComment.author))
        .where(KBComment.id == comment.id)
    )
    comment = result.scalar_one()
    return _to_comment_response(comment, replies=[])


@router.delete("/kb/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> None:
    """Delete a comment.

    Admin and technician moderam a base de conhecimento e podem excluir o
    comentário de qualquer autor. Cliente só exclui os próprios.
    """
    result = await db.execute(select(KBComment).where(KBComment.id == comment_id))
    comment = result.scalar_one_or_none()
    if comment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comentário não encontrado. Ele pode já ter sido excluído.",
        )

    can_moderate = actor.role in (UserRole.admin, UserRole.technician)
    is_own = comment.author_id == actor.id
    if not can_moderate and not is_own:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você só pode excluir os seus próprios comentários.",
        )

    await db.delete(comment)
    await db.commit()
