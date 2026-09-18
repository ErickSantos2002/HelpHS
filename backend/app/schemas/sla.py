"""
Pydantic v2 schemas for SLA configuration endpoints.

A unidade canonica e o MINUTO. Ela substituiu a hora porque metade da resposta
do nivel critico e 30 minutos, e nenhum contrato em horas inteiras expressa
isso.

`*_hours` continua aqui como PONTE, e some quando a tela de SLA for refeita:

- **na escrita** e aceito e convertido (x60), para a tela de hoje continuar
  aplicando os sete prazos que sao hora cheia;
- **na leitura** so aparece quando o valor e hora exata. Quando nao for, vem
  `null` -- de proposito. Devolver "1 h" para um prazo de 30 minutos seria a
  tela mentindo com numero plausivel, que e pior do que nao mostrar: `null` a
  tela nao sabe desenhar e alguem pergunta; "1 h" ninguem questiona.

Mandar os dois na mesma requisicao e erro, e nao precedencia silenciosa: quem
faz isso nao sabe qual valor vale, e adivinhar por ele seria escolher no escuro.
"""

import uuid
from datetime import datetime
from typing import Any, Self

from pydantic import ConfigDict, Field, model_validator

from app.models.models import SLALevel
from app.schemas.base import AppBaseModel

MINUTOS_POR_HORA = 60


def _em_horas_exatas(minutos: int) -> int | None:
    """Horas quando o valor e hora cheia, `None` quando nao e."""
    return minutos // MINUTOS_POR_HORA if minutos % MINUTOS_POR_HORA == 0 else None


class SLAConfigUpdate(AppBaseModel):
    # `ge=1` num campo de minutos permite os 30 min do critico, que era o valor
    # impossivel no contrato antigo. O teto acompanha: 9999 h viram 599_940 min.
    response_time_minutes: int | None = Field(default=None, ge=1, le=599_940)
    resolve_time_minutes: int | None = Field(default=None, ge=1, le=599_940)
    warning_threshold: int | None = Field(default=None, ge=1, le=100)
    is_active: bool | None = None

    # ── Ponte com a tela antiga, que ainda fala em horas ──────
    response_time_hours: int | None = Field(default=None, ge=1, le=9999)
    resolve_time_hours: int | None = Field(default=None, ge=1, le=9999)

    @model_validator(mode="after")
    def _hora_vira_minuto(self) -> Self:
        for campo in ("response_time", "resolve_time"):
            em_horas = getattr(self, f"{campo}_hours")
            if em_horas is None:
                continue
            if getattr(self, f"{campo}_minutes") is not None:
                raise ValueError(
                    f"Envie {campo}_minutes ou {campo}_hours, nunca os dois: "
                    "com ambos preenchidos não há como saber qual vale."
                )
            setattr(self, f"{campo}_minutes", em_horas * MINUTOS_POR_HORA)
        return self

    def campos_para_gravar(self) -> dict[str, Any]:
        """O que o router aplica no registro, já sem os campos-ponte.

        Montado campo a campo, e não por `model_dump(exclude_unset=...)`: o
        validador acima PREENCHE `*_minutes` a partir de `*_hours`, e depender
        de "veio na requisição" faria a ponte gravar nada justamente quando ela
        é usada. Aqui a pergunta é outra e é a certa: tem valor?
        """
        return {
            campo: valor
            for campo in (
                "response_time_minutes",
                "resolve_time_minutes",
                "warning_threshold",
                "is_active",
            )
            if (valor := getattr(self, campo)) is not None
        }


class SLAConfigResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    level: SLALevel
    response_time_minutes: int
    resolve_time_minutes: int
    warning_threshold: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Derivados, só para a tela antiga. `None` quando o prazo não é hora cheia.
    response_time_hours: int | None = None
    resolve_time_hours: int | None = None

    @model_validator(mode="after")
    def _preenche_as_horas(self) -> Self:
        self.response_time_hours = _em_horas_exatas(self.response_time_minutes)
        self.resolve_time_hours = _em_horas_exatas(self.resolve_time_minutes)
        return self
