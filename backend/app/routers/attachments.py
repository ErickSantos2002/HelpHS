"""
Upload e gestão de anexos de tickets.

Permissões:
  POST   /tickets/{id}/attachments   — qualquer autenticado com acesso ao ticket
  GET    /tickets/{id}/attachments   — qualquer autenticado com acesso ao ticket
  GET    /attachments/{id}           — qualquer autenticado com acesso ao ticket
  DELETE /attachments/{id}           — admin, technician

Regras de negócio:
  - Máx. 25 MB por arquivo
  - Máx. 10 arquivos por ticket (total, incluindo os já existentes)
  - Extensões permitidas: .pdf .doc .docx .xls .xlsx .png .jpg .jpeg .gif .txt .csv .zip .rar
  - Todo arquivo é escaneado pelo ClamAV antes de ser persistido
  - Se ClamAV estiver indisponível, o arquivo é salvo como virus_scanned=False
  - Arquivos infectados são rejeitados com 422
"""

import os
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import authorize, get_current_user
from app.models.models import (
    Attachment,
    AuditAction,
    AuditLog,
    Ticket,
    TicketStatus,
    User,
    UserRole,
)
from app.schemas.attachment import (
    AttachmentDownloadResponse,
    AttachmentListResponse,
    AttachmentResponse,
)
from app.services import antivirus, storage
from app.utils.crud import get_or_404

router = APIRouter(tags=["Attachments"])

_TERMINAL_STATUSES = frozenset({TicketStatus.closed, TicketStatus.cancelled})


# ── Helpers ───────────────────────────────────────────────────


async def _get_attachment_or_404(attachment_id: uuid.UUID, db: AsyncSession) -> Attachment:
    return await get_or_404(db, Attachment, attachment_id, "Attachment not found")


def _check_ticket_access(ticket: Ticket, actor: User) -> None:
    if actor.role == UserRole.client and ticket.creator_id != actor.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def _validate_file(
    file: UploadFile,
    data: bytes,
    settings: Settings,
) -> None:
    """Validate extension and size. Raises 422 on failure."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File type '{ext}' is not allowed",
        )
    max_bytes = settings.upload_max_file_size_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File '{file.filename}' exceeds the {settings.upload_max_file_size_mb} MB limit",
        )


# ═══════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════


@router.post(
    "/tickets/{ticket_id}/attachments",
    response_model=list[AttachmentResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachments(
    ticket_id: uuid.UUID,
    files: Annotated[list[UploadFile], File(...)],
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[AttachmentResponse]:
    ticket = await get_or_404(db, Ticket, ticket_id, "Ticket not found")
    _check_ticket_access(ticket, actor)

    if ticket.status in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot add attachments to a closed or cancelled ticket",
        )

    # Check total attachment count
    count_result = await db.execute(
        select(func.count()).select_from(
            select(Attachment).where(Attachment.ticket_id == ticket_id).subquery()
        )
    )
    existing_count = count_result.scalar_one()
    if existing_count + len(files) > settings.upload_max_files_per_ticket:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ticket already has {existing_count} attachment(s). "
            f"Max {settings.upload_max_files_per_ticket} per ticket.",
        )

    created: list[AttachmentResponse] = []

    for file in files:
        data = await file.read()
        _validate_file(file, data, settings)

        # ClamAV scan
        is_clean, scan_msg = await antivirus.scan_bytes(
            data,
            host=settings.clamav_host,
            port=settings.clamav_port,
            timeout=settings.clamav_timeout_seconds,
        )
        if scan_msg not in ("clean", "unavailable"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"File '{file.filename}' rejected: {scan_msg}",
            )

        virus_scanned = scan_msg == "clean"

        ext = os.path.splitext(file.filename or "")[1].lower()
        stored_name = f"{uuid.uuid4()}{ext}"
        s3_key = f"tickets/{ticket_id}/{stored_name}"
        mime = file.content_type or "application/octet-stream"

        await storage.upload_file(data, s3_key, mime, settings)

        attachment = Attachment(
            id=uuid.uuid4(),
            ticket_id=ticket_id,
            uploaded_by=actor.id,
            original_name=file.filename or stored_name,
            stored_name=stored_name,
            mime_type=mime,
            size_bytes=len(data),
            s3_key=s3_key,
            s3_bucket=settings.minio_bucket_name,
            virus_scanned=virus_scanned,
            virus_clean=virus_scanned,
            created_at=datetime.now(UTC),
        )
        db.add(attachment)
        db.add(
            AuditLog(
                user_id=actor.id,
                action=AuditAction.create,
                entity_type="attachment",
                entity_id=attachment.id,
            )
        )
        created.append(attachment)

    await db.commit()
    for att in created:
        await db.refresh(att)

    return [AttachmentResponse.model_validate(a) for a in created]


@router.get("/tickets/{ticket_id}/attachments", response_model=AttachmentListResponse)
async def list_attachments(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> AttachmentListResponse:
    ticket = await get_or_404(db, Ticket, ticket_id, "Ticket not found")
    _check_ticket_access(ticket, actor)

    result = await db.execute(
        select(Attachment)
        .where(Attachment.ticket_id == ticket_id)
        .order_by(Attachment.created_at.asc())
    )
    attachments = result.scalars().all()

    return AttachmentListResponse(
        items=[AttachmentResponse.model_validate(a) for a in attachments],
        total=len(attachments),
    )


@router.get("/attachments/{attachment_id}", response_model=AttachmentDownloadResponse)
async def get_attachment_url(
    attachment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AttachmentDownloadResponse:
    attachment = await _get_attachment_or_404(attachment_id, db)

    # Verify the actor has access to the parent ticket
    ticket = await get_or_404(db, Ticket, attachment.ticket_id, "Ticket not found")
    _check_ticket_access(ticket, actor)

    url = await storage.get_presigned_url(attachment.s3_key, settings)
    return AttachmentDownloadResponse(url=url)


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    attachment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    attachment = await _get_attachment_or_404(attachment_id, db)

    await storage.delete_file(attachment.s3_key, settings)

    db.add(
        AuditLog(
            user_id=actor.id,
            action=AuditAction.delete,
            entity_type="attachment",
            entity_id=attachment.id,
        )
    )
    await db.delete(attachment)
    await db.commit()
