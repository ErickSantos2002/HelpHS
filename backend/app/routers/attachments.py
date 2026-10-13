"""
Upload e gestão de anexos de tickets.

Permissões:
  POST   /tickets/{id}/attachments   — qualquer autenticado com acesso ao ticket
  GET    /tickets/{id}/attachments   — qualquer autenticado com acesso ao ticket
  GET    /attachments/{id}           — qualquer autenticado com acesso ao ticket
  POST   /tickets/{id}/attachments/archive — qualquer autenticado com acesso ao ticket
         (o ZIP em si sai por GET /files/archive/{token}, ver files.py)
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
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.rate_limit import chave_por_usuario, limiter
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
    AttachmentArchiveResponse,
    AttachmentArchiveUnverified,
    AttachmentDownloadResponse,
    AttachmentListResponse,
    AttachmentResponse,
)
from app.services import antivirus, arquivo_zip, storage
from app.utils.crud import get_or_404
from app.utils.history import CAMPO_ANEXO_ADICIONADO, registra_historico
from app.utils.ticket_access import ensure_ticket_visible
from app.utils.uploads import ler_ate_o_limite

router = APIRouter(tags=["Attachments"])

_TERMINAL_STATUSES = frozenset({TicketStatus.closed, TicketStatus.cancelled})

# Uma constante por recurso: a recusa de item alheio precisa sair com
# EXATAMENTE o mesmo texto do id inexistente, e dois literais soltos divergem
# em silêncio.
_CHAMADO_NAO_ENCONTRADO = "Ticket not found"
_ANEXO_NAO_ENCONTRADO = "Attachment not found"


# ── Helpers ───────────────────────────────────────────────────


def _resposta(attachment: Attachment, autor: User) -> AttachmentResponse:
    """O anexo com nome e papel de quem enviou, lidos do cadastro AGORA.

    Lidos na hora, e não copiados para o anexo no envio: conta anonimizada
    depois do envio passa a aparecer anonimizada aqui também.

    `autor` vem de fora porque cada chamador já o tem sem ir ao banco: no envio
    é o próprio `actor`; na listagem, `attachment.user` carregado pelo
    `selectinload` — numa sessão assíncrona, carga preguiçosa é
    `MissingGreenlet`.
    """
    resposta = AttachmentResponse.model_validate(attachment)
    resposta.uploaded_by_name = autor.name
    resposta.uploaded_by_role = autor.role
    return resposta


async def _get_attachment_or_404(attachment_id: uuid.UUID, db: AsyncSession) -> Attachment:
    return await get_or_404(db, Attachment, attachment_id, _ANEXO_NAO_ENCONTRADO)


def _validate_extension(file: UploadFile, settings: Settings) -> None:
    """
    Confere a extensão ANTES de ler qualquer byte.

    O tamanho saiu daqui: media `len(data)` sobre um arquivo já inteiro na
    memória, o que aplicava o limite tarde demais. Quem mede agora é o
    `ler_ate_o_limite`, por blocos — ver app/utils/uploads.py.
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"O tipo de arquivo '{ext}' não é aceito.",
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
    ticket = await get_or_404(db, Ticket, ticket_id, _CHAMADO_NAO_ENCONTRADO)
    if actor.role == UserRole.client:
        ensure_ticket_visible(ticket, actor, _CHAMADO_NAO_ENCONTRADO)

    if ticket.status in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Não é possível anexar arquivos a um ticket fechado ou cancelado.",
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Ticket already has {existing_count} attachment(s). "
            f"Max {settings.upload_max_files_per_ticket} per ticket.",
        )

    # Guarda os objetos do ORM; a conversao para resposta acontece no return.
    created: list[Attachment] = []

    for file in files:
        # Extensão primeiro: recusar por tipo não precisa ler byte nenhum.
        _validate_extension(file, settings)
        data = await ler_ate_o_limite(
            file,
            max_bytes=settings.upload_max_file_size_mb * 1024 * 1024,
            rotulo=f"{settings.upload_max_file_size_mb} MB",
        )

        # ClamAV scan
        is_clean, scan_msg = await antivirus.scan_bytes(
            data,
            host=settings.clamav_host,
            port=settings.clamav_port,
            timeout=settings.clamav_timeout_seconds,
        )
        if scan_msg not in ("clean", "unavailable"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
        # O acontecimento que a conversa e a aba Atividade mostram. Na mesma
        # transação do anexo: se um arquivo do lote for recusado adiante, o
        # commit abaixo nunca acontece e não sobra evento de arquivo que não
        # existe. Grava só o id — nome de pessoa nenhum vai para o texto: quem
        # enviou é o `user_id`, e o nome é lido do cadastro na hora de mostrar.
        registra_historico(db, ticket_id, actor.id, CAMPO_ANEXO_ADICIONADO, None, attachment.id)
        created.append(attachment)

    await db.commit()
    for att in created:
        await db.refresh(att)

    return [_resposta(a, actor) for a in created]


@router.get("/tickets/{ticket_id}/attachments", response_model=AttachmentListResponse)
async def list_attachments(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> AttachmentListResponse:
    ticket = await get_or_404(db, Ticket, ticket_id, _CHAMADO_NAO_ENCONTRADO)
    if actor.role == UserRole.client:
        ensure_ticket_visible(ticket, actor, _CHAMADO_NAO_ENCONTRADO)

    result = await db.execute(
        select(Attachment)
        .options(selectinload(Attachment.user))
        .where(Attachment.ticket_id == ticket_id)
        .order_by(Attachment.created_at.asc())
    )
    attachments = result.scalars().all()

    return AttachmentListResponse(
        items=[_resposta(a, a.user) for a in attachments],
        total=len(attachments),
    )


@router.post("/tickets/{ticket_id}/attachments/archive", response_model=AttachmentArchiveResponse)
# O decorador do slowapi roda DEPOIS das dependências: o usuário já foi
# autenticado quando a chave é lida, e o 429 sai antes de qualquer consulta ao
# chamado — sem token, sem auditoria, sem temporário. Alheio, inexistente e
# próprio gastam o mesmo balde, então o 429 não diz nada sobre o chamado.
@limiter.limit(get_settings().rate_limit_zip_anexos, key_func=chave_por_usuario)
async def request_attachments_archive(
    request: Request,
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AttachmentArchiveResponse:
    """Autoriza baixar TODOS os anexos do chamado num ZIP, e devolve o link.

    O acesso é o da listagem: cliente só no chamado que é dele, com o mesmo 404
    do chamado inexistente. Os ids saem congelados num token assinado — o ZIP
    leva estes anexos e nenhum outro, nem os que chegarem depois.

    Registra o pedido na auditoria como `export` (o valor existe no enum desde
    o schema inicial), só com ids e contagens: nome de arquivo pode ser dado
    pessoal, e a trilha não precisa dele para dizer quem levou o quê.
    """
    ticket = await get_or_404(db, Ticket, ticket_id, _CHAMADO_NAO_ENCONTRADO)
    if actor.role == UserRole.client:
        ensure_ticket_visible(ticket, actor, _CHAMADO_NAO_ENCONTRADO)

    anexos = (
        (
            await db.execute(
                select(Attachment)
                .where(Attachment.ticket_id == ticket_id)
                .order_by(Attachment.created_at.asc(), Attachment.id.asc())
            )
        )
        .scalars()
        .all()
    )
    if not anexos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Este chamado não tem anexos para baixar.",
        )

    # Confere o disco JÁ no pedido: é aqui que a tela consegue mostrar o erro.
    # A entrega confere de novo, para o que sumir entre o pedido e o clique.
    _, sumidos = arquivo_zip.confere_no_disco(anexos, settings)
    if sumidos:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=arquivo_zip.mensagem_de_sumidos(sumidos),
        )

    ids = [str(a.id) for a in anexos]
    nao_verificados = [a for a in anexos if not a.virus_scanned]

    db.add(
        AuditLog(
            user_id=actor.id,
            action=AuditAction.export,
            entity_type="ticket",
            entity_id=ticket.id,
            new_data={
                "attachment_ids": ids,
                "total": len(ids),
                "nao_verificados": len(nao_verificados),
            },
        )
    )
    await db.commit()

    expira = settings.file_url_expires_seconds
    token = storage.create_archive_token(str(ticket.id), ids, settings, expira)
    return AttachmentArchiveResponse(
        url=f"{settings.api_prefix}/files/archive/{token}",
        expires_in=expira,
        total=len(ids),
        nao_verificados=[
            AttachmentArchiveUnverified(id=a.id, original_name=a.original_name)
            for a in nao_verificados
        ],
    )


@router.get("/attachments/{attachment_id}", response_model=AttachmentDownloadResponse)
async def get_attachment_url(
    attachment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AttachmentDownloadResponse:
    attachment = await _get_attachment_or_404(attachment_id, db)

    # O acesso é decidido pelo chamado pai, mas a recusa fala do ANEXO: quem
    # pediu o anexo e ouve "chamado não encontrado" já sabe que o anexo existe.
    # Para o cliente, os três casos — anexo inexistente, anexo de chamado
    # alheio e chamado inexistente — têm a mesma resposta.
    ticket = await get_or_404(db, Ticket, attachment.ticket_id, _ANEXO_NAO_ENCONTRADO)
    if actor.role == UserRole.client:
        ensure_ticket_visible(ticket, actor, _ANEXO_NAO_ENCONTRADO)

    # O arquivo sumiu do disco (volume trocado, limpeza manual): o mesmo 404 do
    # anexo inexistente, e não um link que leva a outro 404. Quem pede o link
    # é a TELA, e é aqui que ela consegue mostrar o aviso; o `<iframe>` do
    # visualizador não avisa erro HTTP e exibia o JSON cru do `/files`.
    if not storage.file_exists(attachment.s3_key, settings):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_ANEXO_NAO_ENCONTRADO)

    url = await storage.get_presigned_url(attachment.s3_key, settings)
    # Em disco o arquivo tem nome interno (uuid); sem isto o usuário baixaria
    # "a1b2c3.pdf" em vez de "laudo de calibração.pdf"
    url = f"{url}?filename={quote(attachment.original_name)}"
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
