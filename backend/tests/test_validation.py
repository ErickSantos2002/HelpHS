"""
Tests for centralized validation middleware (T17).

Verifies:
- 422 errors have { "detail": [{ "field": "...", "message": "..." }] }
- String inputs are stripped of whitespace
- pt-BR validator messages surface correctly
- HTTP errors keep { "detail": "..." } format
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

# ── Minimal fixture: no auth needed for validation tests ─────


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


# ── Error format tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_required_field_returns_standardized_422():
    """POST /auth/login with missing password → structured 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/auth/login", json={"email": "a@b.com"})
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body
    assert isinstance(body["detail"], list)
    first = body["detail"][0]
    assert "field" in first
    assert "message" in first
    assert first["field"] == "password"
    assert first["message"] == "Campo obrigatório"


@pytest.mark.asyncio
async def test_invalid_email_returns_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/auth/login", json={"email": "not-an-email", "password": "Secret1"}
        )
    assert resp.status_code == 422
    body = resp.json()
    assert any(e["field"] == "email" for e in body["detail"])


@pytest.mark.asyncio
async def test_empty_body_returns_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/auth/login", json={})
    assert resp.status_code == 422
    body = resp.json()
    fields = [e["field"] for e in body["detail"]]
    assert "email" in fields
    assert "password" in fields


@pytest.mark.asyncio
async def test_http_exception_keeps_detail_string():
    """404s still return { "detail": "..." } (not a list)."""
    import uuid
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.core.database import get_db
    from app.core.security import get_current_user
    from app.models.models import UserRole, UserStatus

    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = UserRole.admin
    user.status = UserStatus.active
    user.email = "admin@test.com"

    async def _admin():
        return user

    async def _execute(*args, **kwargs):
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        r.scalar_one.return_value = 0
        r.scalars.return_value.all.return_value = []
        return r

    session = AsyncMock()
    session.execute = _execute

    async def _db():
        yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _admin

    with patch("app.core.security.get_redis"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"/api/v1/products/{uuid.uuid4()}")

    assert resp.status_code == 404
    body = resp.json()
    assert "detail" in body
    assert isinstance(body["detail"], str)


# ── Sanitization tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_whitespace_stripped_from_string_fields():
    """Input with leading/trailing spaces should be stripped before processing."""
    from app.schemas.auth import LoginRequest

    schema = LoginRequest(email="  user@test.com  ", password="Secret123")
    assert schema.email == "user@test.com"


@pytest.mark.asyncio
async def test_whitespace_stripped_from_name():
    from app.schemas.user import UserCreate

    schema = UserCreate(
        name="  John Doe  ",
        email="john@test.com",
        password="Secret123",
        lgpd_consent=True,
    )
    assert schema.name == "John Doe"


# ── pt-BR message tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_password_missing_uppercase_message_is_ptbr():
    from pydantic import ValidationError

    from app.schemas.user import UserCreate

    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            name="John",
            email="john@test.com",
            password="secret123",  # no uppercase
            lgpd_consent=True,
        )
    errors = exc_info.value.errors()
    messages = [e["msg"] for e in errors]
    assert any("maiúscula" in m for m in messages)


@pytest.mark.asyncio
async def test_password_missing_digit_message_is_ptbr():
    from pydantic import ValidationError

    from app.schemas.user import UserCreate

    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            name="John",
            email="john@test.com",
            password="SecretOnly",  # no digit
            lgpd_consent=True,
        )
    errors = exc_info.value.errors()
    messages = [e["msg"] for e in errors]
    assert any("número" in m for m in messages)


@pytest.mark.asyncio
async def test_validation_error_handler_translates_missing():
    """The handler maps 'missing' → 'Campo obrigatório'."""
    from app.core.exceptions import _translate_error

    result = _translate_error(
        {"type": "missing", "loc": ["body", "email"], "msg": "Field required", "ctx": {}}
    )
    assert result["field"] == "email"
    assert result["message"] == "Campo obrigatório"


@pytest.mark.asyncio
async def test_validation_error_handler_translates_string_too_short():
    from app.core.exceptions import _translate_error

    result = _translate_error(
        {
            "type": "string_too_short",
            "loc": ["body", "name"],
            "msg": "String should have at least 2 characters",
            "ctx": {"min_length": 2},
        }
    )
    assert result["field"] == "name"
    assert "2" in result["message"]
