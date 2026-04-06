"""
Unit tests for MinIO storage service.
boto3 fully mocked — no real S3/MinIO required.
"""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.services import storage

# ── Helpers ───────────────────────────────────────────────────


def _settings():
    s = MagicMock()
    s.minio_endpoint = "localhost"
    s.minio_port = 9000
    s.minio_use_ssl = False
    s.minio_access_key = "minioadmin"
    s.minio_secret_key = "minioadmin"
    s.minio_bucket_name = "helphs"
    return s


def _client_error(code="NoSuchBucket"):
    err = ClientError(
        {"Error": {"Code": code, "Message": "test"}},
        "HeadBucket",
    )
    return err


# ═══════════════════════════════════════════════════════════════
# _make_client
# ═══════════════════════════════════════════════════════════════


def test_make_client_http():
    settings = _settings()
    settings.minio_use_ssl = False
    with patch("app.services.storage.boto3.client") as mock_boto:
        storage._make_client(settings)
        call_kwargs = mock_boto.call_args
        assert "http://" in call_kwargs.kwargs["endpoint_url"]


def test_make_client_https():
    settings = _settings()
    settings.minio_use_ssl = True
    with patch("app.services.storage.boto3.client") as mock_boto:
        storage._make_client(settings)
        call_kwargs = mock_boto.call_args
        assert "https://" in call_kwargs.kwargs["endpoint_url"]


# ═══════════════════════════════════════════════════════════════
# ensure_bucket
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ensure_bucket_already_exists():
    settings = _settings()
    mock_s3 = MagicMock()
    mock_s3.head_bucket.return_value = {}

    with patch("app.services.storage._make_client", return_value=mock_s3):
        await storage.ensure_bucket(settings)

    mock_s3.head_bucket.assert_called_once_with(Bucket="helphs")
    mock_s3.create_bucket.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_bucket_creates_if_missing():
    settings = _settings()
    mock_s3 = MagicMock()
    mock_s3.head_bucket.side_effect = _client_error("NoSuchBucket")

    with patch("app.services.storage._make_client", return_value=mock_s3):
        await storage.ensure_bucket(settings)

    mock_s3.create_bucket.assert_called_once_with(Bucket="helphs")


# ═══════════════════════════════════════════════════════════════
# upload_file
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_upload_file_returns_key():
    settings = _settings()
    mock_s3 = MagicMock()

    with patch("app.services.storage._make_client", return_value=mock_s3):
        result = await storage.upload_file(
            b"hello", "path/to/file.pdf", "application/pdf", settings
        )

    assert result == "path/to/file.pdf"
    mock_s3.upload_fileobj.assert_called_once()


@pytest.mark.asyncio
async def test_upload_file_passes_content_type():
    settings = _settings()
    mock_s3 = MagicMock()

    with patch("app.services.storage._make_client", return_value=mock_s3):
        await storage.upload_file(b"data", "key.png", "image/png", settings)

    _, call_kwargs = mock_s3.upload_fileobj.call_args
    assert call_kwargs["ExtraArgs"]["ContentType"] == "image/png"


# ═══════════════════════════════════════════════════════════════
# delete_file
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_delete_file_success():
    settings = _settings()
    mock_s3 = MagicMock()

    with patch("app.services.storage._make_client", return_value=mock_s3):
        await storage.delete_file("some/key.pdf", settings)

    mock_s3.delete_object.assert_called_once_with(Bucket="helphs", Key="some/key.pdf")


@pytest.mark.asyncio
async def test_delete_file_handles_client_error():
    settings = _settings()
    mock_s3 = MagicMock()
    mock_s3.delete_object.side_effect = _client_error("NoSuchKey")

    with patch("app.services.storage._make_client", return_value=mock_s3):
        # Should not raise
        await storage.delete_file("missing.pdf", settings)


# ═══════════════════════════════════════════════════════════════
# get_presigned_url
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_presigned_url_returns_url():
    settings = _settings()
    mock_s3 = MagicMock()
    mock_s3.generate_presigned_url.return_value = "http://localhost:9000/helphs/key?sig=abc"

    with patch("app.services.storage._make_client", return_value=mock_s3):
        url = await storage.get_presigned_url("key.pdf", settings, expires=600)

    assert url == "http://localhost:9000/helphs/key?sig=abc"
    mock_s3.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "helphs", "Key": "key.pdf"},
        ExpiresIn=600,
    )


@pytest.mark.asyncio
async def test_get_presigned_url_default_expiry():
    settings = _settings()
    mock_s3 = MagicMock()
    mock_s3.generate_presigned_url.return_value = "http://example.com/url"

    with patch("app.services.storage._make_client", return_value=mock_s3):
        await storage.get_presigned_url("file.txt", settings)

    _, call_kwargs = mock_s3.generate_presigned_url.call_args
    assert call_kwargs["ExpiresIn"] == 3600
