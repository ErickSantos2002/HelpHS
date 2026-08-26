"""
Pydantic schemas for authentication endpoints.
"""

from pydantic import EmailStr, Field, field_validator

from app.schemas.base import AppBaseModel


class LoginRequest(AppBaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("Senha não pode estar vazia")
        return v


class RegisterRequest(AppBaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=20)
    department: str | None = Field(default=None, max_length=100)
    lgpd_consent: bool

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("A senha deve conter ao menos uma letra maiúscula")
        if not any(c.isdigit() for c in v):
            raise ValueError("A senha deve conter ao menos um número")
        return v

    @field_validator("lgpd_consent")
    @classmethod
    def must_accept_lgpd(cls, v: bool) -> bool:
        if not v:
            raise ValueError("O consentimento LGPD é obrigatório para criar uma conta")
        return v


class TokenResponse(AppBaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # access token TTL in seconds


class RefreshRequest(AppBaseModel):
    refresh_token: str


class AccessTokenResponse(AppBaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ── Confirmação de e-mail e recuperação de senha ─────────────


class EmailRequest(AppBaseModel):
    """Usado no reenvio da confirmação e no 'esqueci minha senha'."""

    email: EmailStr


class TokenOnlyRequest(AppBaseModel):
    token: str = Field(..., min_length=10)


class PasswordResetRequest(AppBaseModel):
    token: str = Field(..., min_length=10)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("A senha deve conter ao menos uma letra maiúscula")
        if not any(c.isdigit() for c in v):
            raise ValueError("A senha deve conter ao menos um número")
        return v


class MessageResponse(AppBaseModel):
    """Resposta neutra: nunca revela se um e-mail existe na base."""

    message: str


# ── Segundo fator (TOTP) ──────────────────────────────────────


class MfaStatusResponse(AppBaseModel):
    """Estado do segundo fator de quem está pedindo.

    De propósito NÃO é campo do `UserResponse`: aquele schema é devolvido também
    na listagem de usuários do admin, e quem tem ou não segundo fator não
    precisa viajar em listagem nenhuma.
    """

    enabled: bool
    pending: bool  # segredo cadastrado, mas ainda não confirmado por código
    available: bool  # se o ambiente tem chave de cifra configurada


class MfaSetupResponse(AppBaseModel):
    """Sai uma vez, na tela de cadastro, e não é guardado em lugar nenhum.

    Carrega o segredo em claro — é o que o aplicativo autenticador precisa ler.
    Nunca logar, nunca cachear.
    """

    secret: str  # base32, agrupado de quatro em quatro para quem digita à mão
    otpauth_uri: str


class MfaCodeRequest(AppBaseModel):
    code: str = Field(..., min_length=6, max_length=9)


class MfaChallengeResponse(AppBaseModel):
    """O corpo do 403 que o login devolve quando falta o segundo fator.

    Sai como 403, e não como 200 com campos opcionais, para manter uma regra
    simples: **2xx no `/auth/login` significa sempre que a sessão existe**. Com
    um 200 de desafio, um front que fizesse `set(data.access_token,
    data.refresh_token)` sem conferir gravaria `undefined` — que é exatamente o
    defeito que acabamos de corrigir no interceptor. O status diferente torna
    esse erro impossível em vez de improvável.

    `detail` é irmão dos outros campos, e não o pai deles, para que qualquer
    tratamento genérico de erro do front continue achando uma mensagem legível.
    """

    detail: str
    mfa_required: bool = True
    mfa_token: str
    expires_in: int


class MfaVerifyRequest(AppBaseModel):
    mfa_token: str = Field(..., min_length=10)
    code: str = Field(..., min_length=6, max_length=9)


class MfaDisableRequest(AppBaseModel):
    """Desligar o segundo fator exige a senha atual.

    Sem isso, uma sessão sequestrada removeria a proteção sem nenhum atrito —
    justamente a proteção que existe para o caso de a sessão ser sequestrada.
    """

    password: str = Field(..., min_length=1)
