"""
Tests for Knowledge Base endpoints (T52 — Sprint 6 integration tests).
DB and Redis fully mocked.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import KBArticleStatus, TicketCategory, UserRole, UserStatus

# ── Fake Redis ────────────────────────────────────────────────


class _FakeRedis:
    def __init__(self):
        self._store: dict = {}

    async def setex(self, k, t, v):
        self._store[k] = v

    async def get(self, k):
        return self._store.get(k)

    async def delete(self, k):
        self._store.pop(k, None)

    async def exists(self, k):
        return 1 if k in self._store else 0


_redis = _FakeRedis()


async def _get_redis():
    return _redis


# ── Constants ─────────────────────────────────────────────────

_NOW = datetime.now(UTC)
_ARTICLE_ID = uuid.uuid4()
_AUTHOR_ID = uuid.uuid4()
_TICKET_ID = uuid.uuid4()
_CREATOR_ID = uuid.uuid4()
_PRODUCT_ID = uuid.uuid4()


# ── Mock builders ─────────────────────────────────────────────


def _mock_user(role=UserRole.technician, user_id=None):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.name = f"{role.value}_user"
    u.email = f"{role.value}@test.com"
    u.role = role
    u.status = UserStatus.active
    return u


def _mock_product(product_id=None, name="Titan"):
    p = MagicMock()
    p.id = product_id or _PRODUCT_ID
    p.name = name
    return p


def _mock_article(
    status=KBArticleStatus.published,
    category=TicketCategory.hardware,
    article_id=None,
    products=None,
):
    a = MagicMock()
    a.id = article_id or _ARTICLE_ID
    a.title = "Como resolver falha no bafômetro"
    a.content = "Verifique a conexão de energia e reinicie o dispositivo."
    a.slug = "como-resolver-falha-no-bafometro"
    a.category = category
    a.tags = ["bafômetro", "hardware"]
    a.status = status
    a.author_id = _AUTHOR_ID
    a.author = _mock_user(UserRole.technician, _AUTHOR_ID)
    a.view_count = 10
    a.helpful = 5
    a.not_helpful = 1
    a.created_at = _NOW
    a.updated_at = _NOW
    # Lista vazia = artigo vale para todos os produtos
    a.products = products if products is not None else []
    return a


def _mock_ticket(creator_id=None, product_id=None, equipment_id=None):
    t = MagicMock()
    t.id = _TICKET_ID
    t.title = "Bafômetro com defeito"
    t.category = TicketCategory.hardware
    t.creator_id = creator_id or _CREATOR_ID
    # Precisam ser explícitos: o MagicMock devolveria um objeto truthy e a
    # busca por produto usaria um id inválido
    t.product_id = product_id
    t.equipment_id = equipment_id
    return t


# ── DB helpers ────────────────────────────────────────────────


def _db_sequence(*responses):
    call_count = [0]

    async def _execute(*args, **kwargs):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        resp = responses[idx]

        result = MagicMock()
        if isinstance(resp, int):
            result.scalar_one.return_value = resp
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = []
        elif isinstance(resp, list):
            result.scalar_one_or_none.return_value = None
            result.scalar_one.return_value = len(resp)
            result.scalars.return_value.all.return_value = resp
        else:
            result.scalar_one_or_none.return_value = resp
            result.scalar_one.return_value = resp
            result.scalars.return_value.all.return_value = [resp] if resp else []
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _db_seq_override(*responses):
    session = _db_sequence(*responses)

    async def _gen():
        yield session

    return _gen


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def patch_redis():
    with patch("app.core.security.get_redis", new=_get_redis):
        yield


def _override_user(user):
    from app.core.security import get_current_user

    async def _u():
        return user

    app.dependency_overrides[get_current_user] = _u


# ═══════════════════════════════════════════════════════════════
# LIST ARTICLES
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_articles_returns_published(patch_redis):
    """GET /kb/articles returns published articles for clients."""
    client_user = _mock_user(UserRole.client)
    article = _mock_article()

    _override_user(client_user)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(1, [article])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/kb/articles")

    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == article.title


@pytest.mark.asyncio
async def test_list_articles_staff_sees_all_statuses(patch_redis):
    """Staff can filter by status including draft."""
    tech = _mock_user(UserRole.technician)
    draft = _mock_article(status=KBArticleStatus.draft)

    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(1, [draft])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/kb/articles?status=draft")

    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════
# CREATE ARTICLE
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_article_technician_success(patch_redis):
    """Technician can create a KB article."""
    tech = _mock_user(UserRole.technician, _AUTHOR_ID)
    article = _mock_article(status=KBArticleStatus.draft)

    _override_user(tech)
    from app.core.database import get_db

    # slug uniqueness check returns None (slug available), then article after creation
    app.dependency_overrides[get_db] = _db_seq_override(None, article)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/kb/articles",
            json={
                "title": "Como resolver falha no bafômetro",
                "content": "Verifique a conexão de energia.",
                "category": "hardware",
                "tags": ["bafômetro"],
                "status": "draft",
            },
        )

    assert r.status_code == 201
    assert r.json()["title"] == article.title


@pytest.mark.asyncio
async def test_create_article_client_forbidden(patch_redis):
    """Client cannot create KB articles (403)."""
    client_user = _mock_user(UserRole.client)
    _override_user(client_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/kb/articles",
            json={
                "title": "Teste",
                "content": "Conteúdo",
                "category": "general",
                "tags": [],
                "status": "draft",
            },
        )

    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_article_missing_title_rejected(patch_redis):
    """Missing title should fail validation (422)."""
    tech = _mock_user(UserRole.technician)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/kb/articles",
            json={"content": "Conteúdo sem título", "category": "general"},
        )

    assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════
# GET ARTICLE
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_article_increments_view_count(patch_redis):
    """GET /kb/articles/{id} returns the article and increments view_count."""
    tech = _mock_user(UserRole.technician)
    article = _mock_article()

    _override_user(tech)
    from app.core.database import get_db

    # O endpoint executa três queries: busca o artigo, incrementa o view_count e
    # recarrega o artigo depois do commit (a sessão expira os objetos no commit).
    reloaded = _make_result(article)
    reloaded.scalar_one.return_value = article

    session = _db_sequence(article)
    session.execute = AsyncMock(
        side_effect=[
            _make_result(article),
            _make_result(None),  # UPDATE do view_count
            reloaded,
        ]
    )

    async def _gen():
        yield session

    app.dependency_overrides[get_db] = _gen

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/kb/articles/{_ARTICLE_ID}")

    assert r.status_code == 200
    assert r.json()["id"] == str(_ARTICLE_ID)


def _make_result(obj):
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    result.scalar_one.return_value = 0
    result.scalars.return_value.all.return_value = [obj] if obj else []
    return result


@pytest.mark.asyncio
async def test_get_article_not_found(patch_redis):
    """Returns 404 for non-existent article."""
    tech = _mock_user(UserRole.technician)
    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/kb/articles/{uuid.uuid4()}")

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_draft_article_client_forbidden(patch_redis):
    """Client cannot see draft articles (404)."""
    client_user = _mock_user(UserRole.client)
    draft_article = _mock_article(status=KBArticleStatus.draft)

    _override_user(client_user)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(draft_article)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/kb/articles/{_ARTICLE_ID}")

    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# UPDATE ARTICLE
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_update_article_success(patch_redis):
    """Technician can update a KB article."""
    tech = _mock_user(UserRole.technician)
    article = _mock_article()

    _override_user(tech)
    from app.core.database import get_db

    # get article (scalar_one_or_none), then reload after update (scalar_one)
    # no title in payload → no slug check execute
    app.dependency_overrides[get_db] = _db_seq_override(article, article)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.patch(
            f"/api/v1/kb/articles/{_ARTICLE_ID}",
            json={"status": "published"},
        )

    assert r.status_code == 200


@pytest.mark.asyncio
async def test_update_article_client_forbidden(patch_redis):
    """Client cannot update KB articles (403)."""
    client_user = _mock_user(UserRole.client)
    _override_user(client_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.patch(
            f"/api/v1/kb/articles/{_ARTICLE_ID}",
            json={"status": "published"},
        )

    assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════
# DELETE (ARCHIVE) ARTICLE
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_delete_article_admin_archives(patch_redis):
    """Admin can archive (DELETE) a KB article — returns 204."""
    admin = _mock_user(UserRole.admin)
    article = _mock_article()

    _override_user(admin)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(article)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.delete(f"/api/v1/kb/articles/{_ARTICLE_ID}")

    assert r.status_code == 204


@pytest.mark.asyncio
async def test_delete_article_technician_forbidden(patch_redis):
    """Technician cannot archive articles (403)."""
    tech = _mock_user(UserRole.technician)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.delete(f"/api/v1/kb/articles/{_ARTICLE_ID}")

    assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════
# FEEDBACK
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_feedback_helpful(patch_redis):
    """POST /kb/articles/{id}/feedback with helpful=true returns 204."""
    client_user = _mock_user(UserRole.client)
    article = _mock_article()

    _override_user(client_user)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(article)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            f"/api/v1/kb/articles/{_ARTICLE_ID}/feedback",
            json={"helpful": True},
        )

    assert r.status_code == 204


@pytest.mark.asyncio
async def test_feedback_not_helpful(patch_redis):
    """POST /kb/articles/{id}/feedback with helpful=false returns 204."""
    client_user = _mock_user(UserRole.client)
    article = _mock_article()

    _override_user(client_user)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(article)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            f"/api/v1/kb/articles/{_ARTICLE_ID}/feedback",
            json={"helpful": False},
        )

    assert r.status_code == 204


# ═══════════════════════════════════════════════════════════════
# SUGGESTIONS
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cliente_ve_sugestoes_do_proprio_ticket(patch_redis):
    client_user = _mock_user(UserRole.client, _CREATOR_ID)
    ticket = _mock_ticket(creator_id=_CREATOR_ID)
    article = _mock_article(category=TicketCategory.hardware)

    _override_user(client_user)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, [article], [], [])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/kb/articles/suggestions?ticket_id={_TICKET_ID}")

    assert r.status_code == 200


@pytest.mark.asyncio
async def test_cliente_nao_ve_sugestoes_de_ticket_alheio(patch_redis):
    client_user = _mock_user(UserRole.client)  # id diferente do creator
    ticket = _mock_ticket(creator_id=_CREATOR_ID)

    _override_user(client_user)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/kb/articles/suggestions?ticket_id={_TICKET_ID}")

    assert r.status_code == 403


@pytest.mark.asyncio
async def test_suggestions_ticket_not_found(patch_redis):
    """Returns 404 when ticket does not exist."""
    tech = _mock_user(UserRole.technician)
    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/kb/articles/suggestions?ticket_id={uuid.uuid4()}")

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_suggestions_returns_articles(patch_redis):
    """Returns matching KB articles for a ticket's category."""
    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket()
    article = _mock_article(category=TicketCategory.hardware)

    _override_user(tech)
    from app.core.database import get_db

    # ticket lookup, then 3 suggestion queries
    app.dependency_overrides[get_db] = _db_seq_override(ticket, [article], [], [])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/kb/articles/suggestions?ticket_id={_TICKET_ID}")

    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) >= 1


# ═══════════════════════════════════════════════════════════════
# DELETE /kb/comments/{id}
# ═══════════════════════════════════════════════════════════════


def _mock_comment(author_id=None):
    c = MagicMock()
    c.id = uuid.uuid4()
    c.article_id = _ARTICLE_ID
    c.author_id = author_id or uuid.uuid4()
    c.content = "Comentário do cliente"
    c.parent_id = None
    c.created_at = _NOW
    c.updated_at = _NOW
    return c


@pytest.mark.asyncio
async def test_tecnico_exclui_comentario_de_outro_usuario(patch_redis):
    """Técnico modera a KB: pode excluir comentário de qualquer autor."""
    tech = _mock_user(UserRole.technician)
    comment = _mock_comment()  # autor diferente do técnico
    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(comment)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.delete(f"/api/v1/kb/comments/{comment.id}")

    assert r.status_code == 204


@pytest.mark.asyncio
async def test_admin_exclui_comentario_de_outro_usuario(patch_redis):
    admin = _mock_user(UserRole.admin)
    comment = _mock_comment()
    _override_user(admin)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(comment)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.delete(f"/api/v1/kb/comments/{comment.id}")

    assert r.status_code == 204


@pytest.mark.asyncio
async def test_cliente_exclui_o_proprio_comentario(patch_redis):
    client_user = _mock_user(UserRole.client)
    comment = _mock_comment(author_id=client_user.id)
    _override_user(client_user)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(comment)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.delete(f"/api/v1/kb/comments/{comment.id}")

    assert r.status_code == 204


@pytest.mark.asyncio
async def test_cliente_nao_exclui_comentario_de_outro(patch_redis):
    client_user = _mock_user(UserRole.client)
    comment = _mock_comment()  # de outra pessoa
    _override_user(client_user)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(comment)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.delete(f"/api/v1/kb/comments/{comment.id}")

    assert r.status_code == 403
    assert "próprios comentários" in r.json()["detail"]


# ═══════════════════════════════════════════════════════════════
# PRODUTOS DO ARTIGO
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_artigo_sem_produto_vale_para_todos(patch_redis):
    """Sem vínculo, o artigo é geral — a resposta traz a lista vazia."""
    tech = _mock_user(UserRole.technician)
    article = _mock_article(products=[])
    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(None, article)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/kb/articles",
            json={"title": "Como abrir um chamado", "content": "Passo a passo.", "product_ids": []},
        )

    assert r.status_code == 201
    assert r.json()["products"] == []


@pytest.mark.asyncio
async def test_criar_artigo_com_produtos(patch_redis):
    tech = _mock_user(UserRole.technician)
    produto = _mock_product()
    article = _mock_article(products=[produto])
    _override_user(tech)
    from app.core.database import get_db

    # slug livre · produtos encontrados · artigo recarregado
    app.dependency_overrides[get_db] = _db_seq_override(None, [produto], article)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/kb/articles",
            json={
                "title": "Calibração do Titan",
                "content": "Procedimento de calibração.",
                "product_ids": [str(_PRODUCT_ID)],
            },
        )

    assert r.status_code == 201
    body = r.json()
    assert len(body["products"]) == 1
    assert body["products"][0]["name"] == "Titan"


@pytest.mark.asyncio
async def test_criar_artigo_com_produto_inexistente_retorna_404(patch_redis):
    tech = _mock_user(UserRole.technician)
    _override_user(tech)
    from app.core.database import get_db

    # slug livre · nenhum produto encontrado
    app.dependency_overrides[get_db] = _db_seq_override(None, [])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/kb/articles",
            json={
                "title": "Artigo órfão",
                "content": "Conteúdo.",
                "product_ids": [str(uuid.uuid4())],
            },
        )

    assert r.status_code == 404
    assert "produtos selecionados" in r.json()["detail"]


@pytest.mark.asyncio
async def test_listagem_aceita_filtro_de_produto(patch_redis):
    tech = _mock_user(UserRole.technician)
    article = _mock_article(products=[_mock_product()])
    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(1, [article])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/kb/articles?product_id={_PRODUCT_ID}")

    assert r.status_code == 200


@pytest.mark.asyncio
async def test_sugestao_usa_o_produto_do_ticket(patch_redis):
    """Ticket com produto: a primeira camada de busca é produto + categoria."""
    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket(product_id=_PRODUCT_ID)
    article = _mock_article(products=[_mock_product()])

    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, [article], [], [], [])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/kb/articles/suggestions?ticket_id={_TICKET_ID}")

    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) >= 1
    assert body["items"][0]["products"][0]["name"] == "Titan"


@pytest.mark.asyncio
async def test_sugestao_sem_produto_no_ticket_usa_categoria(patch_redis):
    """Ticket sem produto nem equipamento: sobra a categoria e a palavra-chave."""
    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket()
    article = _mock_article(category=TicketCategory.hardware)

    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, [article], [])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/kb/articles/suggestions?ticket_id={_TICKET_ID}")

    assert r.status_code == 200
    assert len(r.json()["items"]) >= 1


# ═══════════════════════════════════════════════════════════════
# Modelo: o default de tags não pode ser uma lista compartilhada
# ═══════════════════════════════════════════════════════════════


def test_default_de_tags_gera_lista_nova_a_cada_insercao():
    """
    `default=[]` guarda UMA lista, construída na importação do módulo e
    reusada em toda inserção que não informe tags. Quem mutar o valor que veio
    do default contamina todos os artigos inseridos depois no mesmo processo.

    `default=list` faz o SQLAlchemy chamar `list()` por inserção.
    """
    from app.models.models import KBArticle

    default = KBArticle.__table__.c.tags.default

    assert default.is_callable, (
        "o default de KBArticle.tags precisa ser chamável (default=list); "
        "um literal [] é um único objeto compartilhado entre inserções"
    )

    primeira = default.arg({})
    segunda = default.arg({})

    assert primeira == [] and segunda == []
    assert primeira is not segunda

    # A prova do estrago: mexer numa não pode aparecer na outra.
    primeira.append("seguranca-do-trabalho")
    assert segunda == []
