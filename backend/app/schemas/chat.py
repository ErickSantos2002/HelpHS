"""
Pydantic v2 schemas for Chat endpoints.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict, Field

from app.schemas.base import AppBaseModel


class ChatSenderInfo(AppBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    role: str


class ChatMessageResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    # Nulo na fala da Helo. Enquanto era obrigatorio, a primeira mensagem dela
    # derrubaria o GET de mensagens do chamado com ValidationError -- um 500
    # para todo mundo que abrisse aquele chat.
    sender_id: uuid.UUID | None
    content: str
    is_system: bool
    is_ai: bool
    read_at: datetime | None
    created_at: datetime

    # O bastante para a conversa desenhar o anexo sem uma segunda chamada. O
    # link nao vem aqui: ele tem validade e sai do /library/{id}/download, que
    # confere a visibilidade na hora de emitir.
    library_file_id: uuid.UUID | None = None
    library_file_name: str | None = None
    library_file_mime: str | None = None
    library_file_size: int | None = None

    # Flattened sender fields (populated manually)
    sender_name: str = ""
    sender_role: str = ""


class ChatMessageListResponse(AppBaseModel):
    items: list[ChatMessageResponse]
    total: int
    limit: int
    offset: int


# Teto do conteúdo de uma mensagem de chat, em caracteres.
#
# Antes não havia teto nenhum: o schema validava só `min_length=1` e a coluna é
# `Text`, então um cliente autenticado gravava megabytes numa mensagem só.
#
# O número é generoso de propósito. Técnico cola log e stack trace no chat o
# tempo todo, e um limite apertado viraria atrito diário para conter um abuso
# que ninguém cometeu. Vinte mil caracteres são cerca de dez páginas: o que
# passa disso não é mensagem, é anexo.
LIMITE_CONTEUDO = 20_000


class ChatMessageCreate(AppBaseModel):
    content: str = Field(..., min_length=1, max_length=LIMITE_CONTEUDO)
    # Aponta para um item da biblioteca; nao carrega arquivo. Item INTERNO e
    # recusado pela API antes de gravar -- a conversa e lida pelo cliente.
    library_file_id: uuid.UUID | None = None


class SuggestReplyResponse(AppBaseModel):
    suggestion: str


class ConversationSummaryResponse(AppBaseModel):
    summary: str


class ImproveMessageRequest(AppBaseModel):
    draft: str = Field(..., min_length=1, max_length=4000)


class ImproveMessageResponse(AppBaseModel):
    improved: str
