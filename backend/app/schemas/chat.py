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


class SuggestReplyResponse(AppBaseModel):
    suggestion: str


class ConversationSummaryResponse(AppBaseModel):
    summary: str


class ImproveMessageRequest(AppBaseModel):
    draft: str = Field(..., min_length=1, max_length=4000)


class ImproveMessageResponse(AppBaseModel):
    improved: str
