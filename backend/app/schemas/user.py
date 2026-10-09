"""
Pydantic v2 schemas for User endpoints.
"""

import re
import uuid
from datetime import datetime

from pydantic import ConfigDict, Field, field_validator

from app.models.models import UserRole, UserStatus
from app.schemas.base import AppBaseModel
from app.utils.documents import CnpjObrigatorio, CnpjOpcional
from app.utils.email_normalizado import EmailNormalizado
from app.utils.telefone import TelefoneOpcional


class UserCreate(AppBaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailNormalizado
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole = UserRole.client
    # Só normaliza. A obrigatoriedade depende do ESTADO RESULTANTE, e quem o
    # conhece é o router — `create_user` fixa `status=active`, de modo que a
    # exigência recai sobre `role == client`. Pôr a regra aqui significaria
    # o schema afirmar sozinho qual status o router vai gravar.
    phone: TelefoneOpcional = Field(default=None, max_length=20)
    department: str | None = Field(default=None, max_length=100)
    lgpd_consent: bool = False

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("A senha deve conter ao menos uma letra maiúscula")
        if not any(c.isdigit() for c in v):
            raise ValueError("A senha deve conter ao menos um número")
        return v


class UserUpdate(AppBaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    # Este schema é COMPARTILHADO por `PATCH /users/me` e `PATCH /users/{id}`
    # e não decide domínio: ele não conhece o usuário alvo, o estado atual dele
    # nem o resultante. Aqui só valida e normaliza quando o campo vem, e o
    # `exclude_unset` do router continua distinguindo "não enviou" de "enviou
    # vazio" — distinção da qual a regra prospectiva depende inteiramente.
    phone: TelefoneOpcional = Field(default=None, max_length=20)
    department: str | None = Field(default=None, max_length=100)
    avatar_url: str | None = Field(default=None, max_length=500)
    role: UserRole | None = None
    # Provisionamento administrativo, não configuração de perfil. O schema é
    # compartilhado com `PATCH /users/me`, que o descarta pelo `exclude` — a
    # recusa explícita de quem não é admin vive em
    # `_guarda_de_atribuicao_de_ramal`, no router.
    #
    # `None` aqui é SIGNIFICATIVO, ao contrário de `role`: é assim que o admin
    # REMOVE um vínculo. Quem separa "não enviou" de "enviou nulo" é o
    # `exclude_unset` do router, como no telefone.
    api4com_extension: str | None = Field(default=None, max_length=20)
    company_name: str | None = Field(default=None, max_length=255)
    cnpj: CnpjOpcional = Field(default=None, max_length=18)
    company_cep: str | None = Field(default=None, max_length=9)
    company_address: str | None = Field(default=None, max_length=255)
    company_city: str | None = Field(default=None, max_length=100)
    company_state: str | None = Field(default=None, max_length=2)

    @field_validator("api4com_extension")
    @classmethod
    def ramal_vazio_e_ausencia(cls, v: str | None) -> str | None:
        """Campo limpo no formulário vira remoção, não string vazia.

        O `AppBaseModel` já apara as pontas; o que sobra aqui é o caso em que
        sobrou nada. Os formulários do projeto mandam `""`, não `null`, quando
        o usuário esvazia um campo — mesma razão do
        `normaliza_telefone_opcional`. Sem isto, esvaziar gravaria `''`, que o
        índice único trataria como valor de verdade e recusaria no segundo
        usuário que fizesse o mesmo.
        """
        return v or None


class PasswordChange(AppBaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("A senha deve conter ao menos uma letra maiúscula")
        if not any(c.isdigit() for c in v):
            raise ValueError("A senha deve conter ao menos um número")
        return v


class UserStatusUpdate(AppBaseModel):
    status: UserStatus


class LGPDConsentUpdate(AppBaseModel):
    lgpd_consent: bool


class LGPDConsentStatus(AppBaseModel):
    """O que a tela de re-aceite precisa saber sobre o aceite de quem está logado."""

    revisao_politica_vigente: str | None
    revisao_termos_vigente: str | None
    # Do último aceite não revogado; nulas quando não há nenhum registrado.
    revisao_politica_aceita: str | None
    revisao_termos_aceita: str | None
    precisa_reaceitar: bool


class OnboardingUpdate(AppBaseModel):
    company_name: str = Field(..., min_length=1, max_length=255)
    cnpj: CnpjObrigatorio = Field(..., max_length=18)
    company_cep: str = Field(..., max_length=9)
    company_address: str | None = Field(default=None, max_length=255)
    company_city: str | None = Field(default=None, max_length=100)
    company_state: str | None = Field(default=None, max_length=2)

    @field_validator("company_cep")
    @classmethod
    def cep_deve_ter_8_digitos(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        if len(digits) != 8:
            raise ValueError("O CEP deve conter 8 dígitos.")
        return digits


class UserResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    status: UserStatus
    phone: str | None
    department: str | None
    avatar_url: str | None
    last_login: datetime | None
    lgpd_consent: bool
    lgpd_consent_at: datetime | None
    email_verified: bool = True
    company_name: str | None
    cnpj: str | None
    company_cep: str | None
    company_address: str | None
    company_city: str | None
    company_state: str | None
    onboarding_completed: bool
    # O ramal não é segredo — a credencial da API4COM é o token e a senha SIP,
    # e nenhum dos dois passa perto do `User`. Sai aqui para o técnico saber
    # em `/users/me` por que a telefonia está indisponível para ele, e para o
    # admin conferir o provisionamento na listagem. Para cliente é sempre nulo.
    api4com_extension: str | None = None
    # Este cliente aceita ser atendido por IA. Default True para o caso do
    # objeto que ainda não passou pelo banco.
    ai_enabled: bool = True
    created_at: datetime
    updated_at: datetime


class UserListResponse(AppBaseModel):
    items: list[UserResponse]
    total: int
    limit: int
    offset: int
