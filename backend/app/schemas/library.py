"""
Schemas da biblioteca de arquivos frequentes.

O envio é multipart — o arquivo vem junto dos campos —, então não há schema de
requisição para ele: os campos são declarados como `Form` no router. Aqui
moram só as respostas e o filtro de listagem.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict, Field

from app.models.models import LibraryVisibility
from app.schemas.base import AppBaseModel


class LibraryFileResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    product_id: uuid.UUID | None
    # Vem do relacionamento, para a lista não precisar de uma segunda consulta
    # por linha só para escrever o nome do aparelho.
    product_name: str | None = None
    visibility: LibraryVisibility

    original_name: str
    mime_type: str
    size_bytes: int
    virus_scanned: bool
    virus_clean: bool

    uploaded_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class LibraryFileListResponse(AppBaseModel):
    items: list[LibraryFileResponse]
    total: int
    limit: int
    offset: int


class LibraryDownloadResponse(AppBaseModel):
    """Link com validade, igual ao dos anexos de chamado.

    A permissão é conferida ANTES de o link ser gerado. Um link já emitido não
    volta atrás, então deixar a conferência para depois transformaria este
    endereço na rota de fuga da regra de visibilidade.
    """

    url: str


class LibraryFileUpdate(AppBaseModel):
    """Edição dos campos de catálogo. O binário não se troca — sobe outro item.

    `visibility` entra aqui porque promover um arquivo de interno para cliente
    é a operação que a regra prevê. Rebaixar também vale: o arquivo some da
    vista do cliente, embora mensagens que já o anexaram continuem existindo —
    o histórico da conversa não é reescrito.
    """

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    product_id: uuid.UUID | None = None
    visibility: LibraryVisibility | None = None
