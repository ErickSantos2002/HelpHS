"""
Tests for the Attachment endpoints and supporting services.

MinIO (storage) and ClamAV (antivirus) are fully mocked.
DB and Redis are also mocked, following the project pattern.
"""

import io
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import TicketCategory, TicketPriority, TicketStatus, UserRole, UserStatus

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
_TICKET_ID = uuid.uuid4()
_CREATOR_ID = uuid.uuid4()
_ATTACH_ID = uuid.uuid4()


# ── Mock builders ─────────────────────────────────────────────


def _mock_user(role=UserRole.technician, user_id=None):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.email = f"{role.value}@test.com"
    u.role = role
    u.status = UserStatus.active
    return u


def _mock_ticket(status=TicketStatus.open, creator_id=None):
    t = MagicMock()
    t.id = _TICKET_ID
    t.status = status
    t.creator_id = creator_id or _CREATOR_ID
    t.priority = TicketPriority.medium
    t.category = TicketCategory.hardware
    return t


def _mock_attachment():
    a = MagicMock()
    a.id = _ATTACH_ID
    a.ticket_id = _TICKET_ID
    a.uploaded_by = _CREATOR_ID
    a.original_name = "report.pdf"
    a.stored_name = f"{uuid.uuid4()}.pdf"
    a.mime_type = "application/pdf"
    a.size_bytes = 1024
    a.s3_key = f"tickets/{_TICKET_ID}/{a.stored_name}"
    a.s3_bucket = "helpdesk-attachments"
    a.virus_scanned = True
    a.virus_clean = True
    a.created_at = _NOW
    return a


# ── DB session factories ──────────────────────────────────────


def _db(lookup=None, count=0):
    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = lookup
        result.scalar_one.return_value = count
        result.scalars.return_value.all.return_value = [lookup] if lookup else []
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


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
            result.scalar_one.return_value = 0
            result.scalars.return_value.all.return_value = [resp] if resp else []
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


def _db_override(lookup=None, count=0):
    session = _db(lookup, count)

    async def _gen():
        yield session

    return _gen


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


# ── Service helpers ───────────────────────────────────────────

_CLEAN_SCAN = AsyncMock(return_value=(True, "clean"))
_VIRUS_SCAN = AsyncMock(return_value=(False, "Virus: EICAR-Test"))
_UNAVAIL_SCAN = AsyncMock(return_value=(False, "unavailable"))
_UPLOAD_OK = AsyncMock(return_value="tickets/abc/file.pdf")
_DELETE_OK = AsyncMock(return_value=None)
_PRESIGNED_OK = AsyncMock(return_value="https://minio.local/presigned-url")


def _pdf_file(name="report.pdf", size=1024):
    return (name, io.BytesIO(b"A" * size), "application/pdf")


# ═══════════════════════════════════════════════════════════════
# Antivirus service unit tests
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_scan_bytes_clean():
    """Simulate clamd returning OK."""
    from app.services.antivirus import scan_bytes

    with patch("asyncio.open_connection") as mock_conn:
        reader = AsyncMock()
        reader.read = AsyncMock(return_value=b"stream: OK\n")
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        mock_conn.return_value = (reader, writer)

        is_clean, msg = await scan_bytes(b"safe data", "localhost", 3310)
        assert is_clean is True
        assert msg == "clean"


@pytest.mark.asyncio
async def test_scan_bytes_virus_found():
    """Simulate clamd returning FOUND."""
    from app.services.antivirus import scan_bytes

    with patch("asyncio.open_connection") as mock_conn:
        reader = AsyncMock()
        reader.read = AsyncMock(return_value=b"stream: EICAR-Test FOUND\n")
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        mock_conn.return_value = (reader, writer)

        is_clean, msg = await scan_bytes(b"virus data", "localhost", 3310)
        assert is_clean is False
        assert "EICAR-Test" in msg


@pytest.mark.asyncio
async def test_scan_bytes_unavailable():
    """ClamAV connection refused → returns unavailable."""
    from app.services.antivirus import scan_bytes

    with patch("asyncio.open_connection", side_effect=ConnectionRefusedError):
        is_clean, msg = await scan_bytes(b"data", "localhost", 3310)
        assert is_clean is False
        assert msg == "unavailable"


# ═══════════════════════════════════════════════════════════════
# Upload endpoint tests
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_upload_attachment_success(patch_redis):
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket()

    # Sequence: get ticket, count existing (0)
    app.dependency_overrides[get_db] = _db_seq_override(ticket, 0)
    _override_user(tech)

    with (
        patch("app.routers.attachments.antivirus.scan_bytes", new=_CLEAN_SCAN),
        patch("app.routers.attachments.storage.upload_file", new=_UPLOAD_OK),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/tickets/{_TICKET_ID}/attachments",
                files={"files": _pdf_file()},
            )

    assert resp.status_code == 201
    data = resp.json()
    assert len(data) == 1
    assert data[0]["original_name"] == "report.pdf"
    assert data[0]["virus_clean"] is True


@pytest.mark.asyncio
async def test_upload_attachment_virus_rejected(patch_redis):
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket()

    app.dependency_overrides[get_db] = _db_seq_override(ticket, 0)
    _override_user(tech)

    with (
        patch("app.routers.attachments.antivirus.scan_bytes", new=_VIRUS_SCAN),
        patch("app.routers.attachments.storage.upload_file", new=_UPLOAD_OK),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/tickets/{_TICKET_ID}/attachments",
                files={"files": _pdf_file()},
            )

    assert resp.status_code == 422
    assert "EICAR-Test" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_attachment_clamav_unavailable_allowed(patch_redis):
    """When ClamAV is unavailable the file is saved as virus_scanned=False."""
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket()

    app.dependency_overrides[get_db] = _db_seq_override(ticket, 0)
    _override_user(tech)

    with (
        patch("app.routers.attachments.antivirus.scan_bytes", new=_UNAVAIL_SCAN),
        patch("app.routers.attachments.storage.upload_file", new=_UPLOAD_OK),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/tickets/{_TICKET_ID}/attachments",
                files={"files": _pdf_file()},
            )

    assert resp.status_code == 201
    assert resp.json()[0]["virus_scanned"] is False


@pytest.mark.asyncio
async def test_upload_attachment_invalid_extension(patch_redis):
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket()

    app.dependency_overrides[get_db] = _db_seq_override(ticket, 0)
    _override_user(tech)

    with patch("app.routers.attachments.antivirus.scan_bytes", new=_CLEAN_SCAN):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/tickets/{_TICKET_ID}/attachments",
                files={"files": ("malware.exe", io.BytesIO(b"bad"), "application/octet-stream")},
            )

    assert resp.status_code == 422
    assert ".exe" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_attachment_file_too_large(patch_redis):
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket()

    app.dependency_overrides[get_db] = _db_seq_override(ticket, 0)
    _override_user(tech)

    big_file = _pdf_file(size=26 * 1024 * 1024)  # 26 MB

    with patch("app.routers.attachments.antivirus.scan_bytes", new=_CLEAN_SCAN):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/tickets/{_TICKET_ID}/attachments",
                files={"files": big_file},
            )

    assert resp.status_code == 422
    assert "MB" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_attachment_ticket_closed(patch_redis):
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket(status=TicketStatus.closed)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/attachments",
            files={"files": _pdf_file()},
        )

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_upload_attachment_max_count_exceeded(patch_redis):
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket()

    # 10 existing attachments (at the limit)
    app.dependency_overrides[get_db] = _db_seq_override(ticket, 10)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/attachments",
            files={"files": _pdf_file()},
        )

    assert resp.status_code == 422
    assert "Max 10" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_attachment_client_forbidden_other_ticket(patch_redis):
    from app.core.database import get_db

    other_client = _mock_user(UserRole.client)
    ticket = _mock_ticket(creator_id=_CREATOR_ID)  # owned by someone else

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(other_client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/attachments",
            files={"files": _pdf_file()},
        )

    assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════
# List / Get / Delete endpoint tests
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_attachments(patch_redis):
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket()
    attachment = _mock_attachment()

    app.dependency_overrides[get_db] = _db_seq_override(ticket, [attachment])
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}/attachments")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["original_name"] == "report.pdf"


@pytest.mark.asyncio
async def test_get_attachment_url(patch_redis):
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    attachment = _mock_attachment()
    ticket = _mock_ticket()

    app.dependency_overrides[get_db] = _db_seq_override(attachment, ticket)
    _override_user(tech)

    with patch("app.routers.attachments.storage.get_presigned_url", new=_PRESIGNED_OK):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"/api/v1/attachments/{_ATTACH_ID}")

    assert resp.status_code == 200
    assert "presigned-url" in resp.json()["url"]


@pytest.mark.asyncio
async def test_delete_attachment(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    attachment = _mock_attachment()

    app.dependency_overrides[get_db] = _db_override(attachment)
    _override_user(admin)

    with patch("app.routers.attachments.storage.delete_file", new=_DELETE_OK):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.delete(f"/api/v1/attachments/{_ATTACH_ID}")

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_attachment_client_forbidden(patch_redis):
    from app.core.database import get_db

    client = _mock_user(UserRole.client)
    attachment = _mock_attachment()

    app.dependency_overrides[get_db] = _db_override(attachment)
    _override_user(client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/attachments/{_ATTACH_ID}")

    assert resp.status_code == 403
