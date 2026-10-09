"""
Pydantic schemas for Calendar endpoints.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict, Field, computed_field

from app.models.models import CalendarEventType
from app.schemas.base import AppBaseModel
from app.utils.agenda import cor_do_tipo


class CalendarEventCreate(AppBaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    event_type: CalendarEventType = CalendarEventType.event
    # `color` SAIU do contrato: a cor vem do tipo (`app/utils/agenda.py`).
    #
    # A tela no ar ainda manda o campo, e ele é IGNORADO — o `AppBaseModel` não
    # recusa chave extra. Recusar com 422 quebraria a criação de evento na tela
    # antiga até o round do frontend, que é a armadilha do #16. E ignorar não fica
    # escondido: a resposta da mesma requisição traz a cor que valeu.
    start_date: datetime
    end_date: datetime
    # Liga o modo data: a API descarta a hora recebida e grava as bordas do dia.
    # Default `False` para nao mudar o significado do que ja e mandado hoje.
    all_day: bool = False


class CalendarEventUpdate(AppBaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    event_type: CalendarEventType | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    all_day: bool | None = None


class CalendarEventResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    event_type: CalendarEventType
    start_date: datetime
    end_date: datetime
    all_day: bool
    created_by: uuid.UUID | None
    creator_name: str | None = None
    created_at: datetime
    updated_at: datetime

    # Campo CALCULADO, e não lido do objeto. Com `from_attributes`, um `color: str`
    # comum seria preenchido pela coluna — e a coluna guarda o que foi clicado
    # antes desta mudança. Calculado, a resposta não tem como ler a coluna, por
    # engano ou por esquecimento.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def color(self) -> str:
        return cor_do_tipo(self.event_type)


class CalendarEventTypeResponse(AppBaseModel):
    """Um tipo de evento e a cor dele. Sem rótulo: texto é da tela."""

    value: CalendarEventType
    color: str


class CalendarEventListResponse(AppBaseModel):
    items: list[CalendarEventResponse]
    total: int
