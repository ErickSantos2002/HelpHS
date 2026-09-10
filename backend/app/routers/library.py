"""
Biblioteca de arquivos frequentes — manual, guia, formulário.

Permissões:
  GET    /library                  — admin, técnico (o cliente NÃO navega o acervo)
  POST   /library                  — admin
  PATCH  /library/{id}             — admin
  DELETE /library/{id}             — admin
  GET    /library/{id}/download    — autenticado; cliente só o que for de cliente

A listagem é de staff porque o acervo é ferramenta de atendimento, não catálogo
público: o cliente recebe o que o técnico manda, não escolhe da prateleira. O
download é aberto porque o anexo que chega na conversa precisa abrir — e ali a
visibilidade é o que decide.

O binário reaproveita o caminho dos anexos de chamado: mesma leitura por blocos
com limite, mesmo ClamAV, mesmo armazenamento em disco e mesmo link com
validade. O que muda é onde o arquivo mora (`library/`, não `tickets/{id}/`) e
o fato de ele ser guardado UMA vez e apontado por muitas mensagens.
"""

import os
import uuid
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import authorize, get_current_user
from app.models.models import (
    AuditAction,
    AuditLog,
    LibraryFile,
    LibraryVisibility,
    Product,
    User,
    UserRole,
)
from app.schemas.library import (
    LibraryDownloadResponse,
    LibraryFileListResponse,
    LibraryFileResponse,
    LibraryFileUpdate,
)
from app.services import antivirus, storage
from app.utils.crud import get_or_404
from app.utils.library_access import ensure_pode_baixar
from app.utils.uploads import ler_ate_o_limite

router = APIRouter(tags=["Biblioteca"])

# Uma constante só: a recusa por visibilidade precisa sair com EXATAMENTE o
# mesmo texto do id inexistente. Dois literais soltos divergem em silêncio, e a
# diferença entre eles é o que confirmaria a existência de um item interno.
_NAO_ENCONTRADO = "Arquivo não encontrado na biblioteca."


def _resposta(arquivo: LibraryFile) -> LibraryFileResponse:
    saida = LibraryFileResponse.model_validate(arquivo)
    saida.product_name = arquivo.product.name if arquivo.product else None
    return saida


async def _busca_ou_404(arquivo_id: uuid.UUID, db: AsyncSession) -> LibraryFile:
    resultado = await db.execute(
        select(LibraryFile)
        .options(selectinload(LibraryFile.product))
        .where(LibraryFile.id == arquivo_id)
    )
    arquivo = resultado.scalar_one_or_none()
    if arquivo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NAO_ENCONTRADO)
    return arquivo


@router.get("/library", response_model=LibraryFileListResponse)
async def list_library_files(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    product_id: Annotated[uuid.UUID | None, Query()] = None,
    visibility: Annotated[LibraryVisibility | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=255)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LibraryFileListResponse:
    filtros = []
    if product_id is not None:
        filtros.append(LibraryFile.product_id == product_id)
    if visibility is not None:
        filtros.append(LibraryFile.visibility == visibility)
    if search:
        # Busca no título E no nome original: quem procura "phoebus" pode estar
        # lembrando do nome do arquivo, não do título que o admin escreveu.
        alvo = f"%{search}%"
        filtros.append(or_(LibraryFile.title.ilike(alvo), LibraryFile.original_name.ilike(alvo)))

    total = (
        await db.execute(
            select(func.count()).select_from(select(LibraryFile).where(*filtros).subquery())
        )
    ).scalar_one()

    linhas = (
        (
            await db.execute(
                select(LibraryFile)
                .options(selectinload(LibraryFile.product))
                .where(*filtros)
                .order_by(LibraryFile.title.asc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )

    return LibraryFileListResponse(
        items=[_resposta(a) for a in linhas], total=total, limit=limit, offset=offset
    )


@router.post("/library", response_model=LibraryFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_library_file(
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin))],
    settings: Annotated[Settings, Depends(get_settings)],
    file: Annotated[UploadFile, File(...)],
    title: Annotated[str, Form(min_length=1, max_length=255)],
    description: Annotated[str | None, Form(max_length=2000)] = None,
    product_id: Annotated[uuid.UUID | None, Form()] = None,
    # O default é `internal` e essa é a decisão inteira: abrir para o cliente é
    # ato explícito de quem envia, então esquecer falha do lado seguro.
    visibility: Annotated[LibraryVisibility, Form()] = LibraryVisibility.internal,
) -> LibraryFileResponse:
    if product_id is not None:
        await get_or_404(db, Product, product_id, "Produto não encontrado.")

    # Extensão primeiro: recusar por tipo não precisa ler byte nenhum.
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"O tipo de arquivo '{ext}' não é aceito.",
        )

    dados = await ler_ate_o_limite(
        file,
        max_bytes=settings.upload_max_file_size_mb * 1024 * 1024,
        rotulo=f"{settings.upload_max_file_size_mb} MB",
    )

    limpo, mensagem = await antivirus.scan_bytes(
        dados,
        host=settings.clamav_host,
        port=settings.clamav_port,
        timeout=settings.clamav_timeout_seconds,
    )
    if mensagem not in ("clean", "unavailable"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Arquivo '{file.filename}' recusado: {mensagem}",
        )
    escaneado = mensagem == "clean"

    stored_name = f"{uuid.uuid4()}{ext}"
    s3_key = f"library/{stored_name}"
    mime = file.content_type or "application/octet-stream"
    await storage.upload_file(dados, s3_key, mime, settings)

    arquivo = LibraryFile(
        id=uuid.uuid4(),
        title=title,
        description=description,
        product_id=product_id,
        visibility=visibility,
        original_name=file.filename or stored_name,
        stored_name=stored_name,
        mime_type=mime,
        size_bytes=len(dados),
        s3_key=s3_key,
        s3_bucket=settings.minio_bucket_name,
        virus_scanned=escaneado,
        virus_clean=escaneado and limpo,
        uploaded_by=actor.id,
        created_at=datetime.now(UTC),
    )
    db.add(arquivo)
    db.add(
        AuditLog(
            user_id=actor.id,
            action=AuditAction.create,
            entity_type="library_file",
            entity_id=arquivo.id,
            new_data={"title": title, "visibility": visibility.value},
        )
    )
    await db.commit()
    await db.refresh(arquivo, attribute_names=["product"])
    return _resposta(arquivo)


@router.patch("/library/{arquivo_id}", response_model=LibraryFileResponse)
async def update_library_file(
    arquivo_id: uuid.UUID,
    payload: LibraryFileUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin))],
) -> LibraryFileResponse:
    arquivo = await _busca_ou_404(arquivo_id, db)
    campos = payload.model_dump(exclude_unset=True)

    if "product_id" in campos and campos["product_id"] is not None:
        await get_or_404(db, Product, campos["product_id"], "Produto não encontrado.")

    antes = {"visibility": arquivo.visibility.value, "title": arquivo.title}
    for campo, valor in campos.items():
        setattr(arquivo, campo, valor)
    arquivo.updated_at = datetime.now(UTC)

    db.add(
        AuditLog(
            user_id=actor.id,
            action=AuditAction.update,
            entity_type="library_file",
            entity_id=arquivo.id,
            old_data=antes,
            # Mudança de visibilidade é a operação que a regra prevê, e por isso
            # o antes e o depois ficam registrados: abrir um manual para cliente
            # é decisão de alguém, com nome e hora.
            new_data={k: (v.value if hasattr(v, "value") else str(v)) for k, v in campos.items()},
        )
    )
    await db.commit()
    await db.refresh(arquivo, attribute_names=["product"])
    return _resposta(arquivo)


@router.delete("/library/{arquivo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_library_file(
    arquivo_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    arquivo = await _busca_ou_404(arquivo_id, db)

    await storage.delete_file(arquivo.s3_key, settings)
    db.add(
        AuditLog(
            user_id=actor.id,
            action=AuditAction.delete,
            entity_type="library_file",
            entity_id=arquivo.id,
            old_data={"title": arquivo.title, "original_name": arquivo.original_name},
        )
    )
    # As mensagens que anexaram este arquivo NÃO são apagadas: a coluna é
    # SET NULL. A conversa sobrevive sem o arquivo — ruim, mas recuperável;
    # apagar a fala do técnico não seria.
    await db.delete(arquivo)
    await db.commit()


@router.get("/library/{arquivo_id}/download", response_model=LibraryDownloadResponse)
async def get_library_file_url(
    arquivo_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LibraryDownloadResponse:
    arquivo = await _busca_ou_404(arquivo_id, db)

    # ANTES de gerar o link. Um link já emitido não volta atrás, então conferir
    # depois faria deste endereço a rota de fuga da regra de visibilidade.
    ensure_pode_baixar(arquivo, actor, _NAO_ENCONTRADO)

    url = await storage.get_presigned_url(arquivo.s3_key, settings)
    # Em disco o arquivo tem nome interno (uuid); sem isto o usuário baixaria
    # "a1b2c3.pdf" em vez de "Manual do Phoebus.pdf".
    return LibraryDownloadResponse(url=f"{url}?filename={quote(arquivo.original_name)}")
