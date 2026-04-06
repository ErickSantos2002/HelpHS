"""
MinIO / S3-compatible storage service.

Uses boto3 (sync) executed in the event-loop's default thread-pool so that
FastAPI async endpoints are not blocked.
"""

import asyncio
import io
from functools import partial

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from loguru import logger

from app.core.config import Settings


def _make_client(settings: Settings):
    protocol = "https" if settings.minio_use_ssl else "http"
    return boto3.client(
        "s3",
        endpoint_url=f"{protocol}://{settings.minio_endpoint}:{settings.minio_port}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        region_name="us-east-1",  # required by boto3 even for MinIO
    )


async def ensure_bucket(settings: Settings) -> None:
    """Create the attachments bucket if it does not exist (idempotent)."""
    loop = asyncio.get_event_loop()
    s3 = _make_client(settings)

    def _create():
        try:
            s3.head_bucket(Bucket=settings.minio_bucket_name)
        except ClientError:
            s3.create_bucket(Bucket=settings.minio_bucket_name)
            logger.info(f"Created MinIO bucket: {settings.minio_bucket_name}")

    await loop.run_in_executor(None, _create)


async def upload_file(
    data: bytes,
    key: str,
    content_type: str,
    settings: Settings,
) -> str:
    """Upload bytes to MinIO. Returns the s3_key on success."""
    loop = asyncio.get_event_loop()
    s3 = _make_client(settings)

    await loop.run_in_executor(
        None,
        partial(
            s3.upload_fileobj,
            io.BytesIO(data),
            settings.minio_bucket_name,
            key,
            ExtraArgs={"ContentType": content_type},
        ),
    )
    logger.info(f"Uploaded {key} ({len(data)} bytes) to MinIO")
    return key


async def delete_file(key: str, settings: Settings) -> None:
    """Delete an object from MinIO."""
    loop = asyncio.get_event_loop()
    s3 = _make_client(settings)

    try:
        await loop.run_in_executor(
            None,
            partial(s3.delete_object, Bucket=settings.minio_bucket_name, Key=key),
        )
        logger.info(f"Deleted {key} from MinIO")
    except (BotoCoreError, ClientError) as exc:
        logger.warning(f"Could not delete {key} from MinIO: {exc}")


async def get_presigned_url(key: str, settings: Settings, expires: int = 3600) -> str:
    """Return a pre-signed GET URL valid for `expires` seconds."""
    loop = asyncio.get_event_loop()
    s3 = _make_client(settings)

    url: str = await loop.run_in_executor(
        None,
        partial(
            s3.generate_presigned_url,
            "get_object",
            Params={"Bucket": settings.minio_bucket_name, "Key": key},
            ExpiresIn=expires,
        ),
    )
    return url
