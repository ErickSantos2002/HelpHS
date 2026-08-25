"""
Endpoints de autenticação: login, refresh, logout.
"""

import re
import uuid
from datetime import UTC, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    bearer_scheme,
    blacklist_token,
    create_access_token,
    create_refresh_token,
    decode_token,
    delete_refresh_token,
    get_current_user,
    get_stored_refresh_token,
    hash_password,
    store_refresh_token,
    verify_password,
)
from app.models.models import AuditAction, AuditLog, User, UserRole, UserStatus
from app.schemas.auth import (
    AccessTokenResponse,
    EmailRequest,
    LoginRequest,
    MessageResponse,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    TokenOnlyRequest,
    TokenResponse,
)
from app.schemas.user import UserResponse
from app.services import account_tokens
from app.services.account_emails import send_password_reset_email, send_verification_email

router = APIRouter(prefix="/auth", tags=["Auth"])
settings = get_settings()


def _audit(
    db: AsyncSession,
    action: AuditAction,
    user_id: uuid.UUID,
    request: Request,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type="user",
            entity_id=user_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent", ""),
        )
    )


# ── GET /auth/cnpj/{cnpj} ────────────────────────────────────


@router.get("/cnpj/{cnpj}")
async def lookup_cnpj(
    cnpj: str,
    _: Annotated[User, Depends(get_current_user)],
) -> dict:
    cnpj_clean = re.sub(r"\D", "", cnpj)
    if len(cnpj_clean) != 14:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CNPJ inválido")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_clean}")

    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CNPJ não encontrado")

    data = resp.json()
    return {
        "cnpj": cnpj_clean,
        "company_name": data.get("razao_social") or "",
        "trade_name": data.get("nome_fantasia") or "",
        "city": data.get("municipio") or "",
        "state": data.get("uf") or "",
    }


# ── GET /auth/cep/{cep} ──────────────────────────────────────


@router.get("/cep/{cep}")
async def lookup_cep(
    cep: str,
    _: Annotated[User, Depends(get_current_user)],
) -> dict:
    cep_clean = re.sub(r"\D", "", cep)
    if len(cep_clean) != 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CEP inválido")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"https://viacep.com.br/ws/{cep_clean}/json/")

    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CEP não encontrado")

    data = resp.json()
    if data.get("erro"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CEP não encontrado")

    return {
        "cep": f"{cep_clean[:5]}-{cep_clean[5:]}",
        "address": data.get("logradouro") or "",
        "neighborhood": data.get("bairro") or "",
        "city": data.get("localidade") or "",
        "state": data.get("uf") or "",
    }


# ── POST /auth/register ───────────────────────────────────────


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_login)
async def register(
    body: RegisterRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este e-mail já está cadastrado.",
        )

    now = datetime.now(UTC)
    # Sem SMTP configurado não há como enviar o link de confirmação; nesse caso
    # a conta já nasce liberada, senão o cliente ficaria esperando um e-mail
    # que nunca chega
    exige_confirmacao = settings.requires_email_verification()

    # bcrypt é síncrono e custa ~250 ms: na thread do event loop, cada cadastro
    # travaria todas as requisições em voo (mesmo motivo do login)
    senha_hash = await run_in_threadpool(hash_password, body.password)

    user = User(
        name=body.name,
        email=body.email,
        password=senha_hash,
        role=UserRole.client,
        status=UserStatus.active,
        phone=body.phone,
        department=body.department,
        lgpd_consent=True,
        lgpd_consent_at=now,
        email_verified=not exige_confirmacao,
        email_verified_at=None if exige_confirmacao else now,
    )
    db.add(user)
    await db.flush()

    _audit(db, AuditAction.create, user.id, request)
    await db.commit()
    await db.refresh(user)

    if exige_confirmacao:
        token = account_tokens.create_email_verification_token(
            user.id, user.email_verified, settings
        )
        await send_verification_email(user.email, user.name, token, settings)
        logger.info(f"New client registered (awaiting confirmation): {user.email}")
    else:
        logger.warning(
            f"New client registered without email confirmation (SMTP not configured): {user.email}"
        )

    return UserResponse.model_validate(user)


# ── POST /auth/verify-email ───────────────────────────────────


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    body: TokenOnlyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """Ativa a conta a partir do link enviado no cadastro."""
    link_invalido = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=("Este link de confirmação não é mais válido. Peça um novo na tela de acesso."),
    )

    # O `peek` confere assinatura, tipo e validade, mas ainda não o uso único:
    # para isso é preciso o estado atual do usuário, e para buscá-lo é preciso
    # o id primeiro. Mesmo desenho do fluxo de senha.
    try:
        user_id = account_tokens.peek_email_verification_subject(body.token, settings)
    except account_tokens.InvalidTokenError as exc:
        raise link_invalido from exc

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta não encontrada. Ela pode ter sido removida.",
        )

    # Clicar de novo num link já usado continua sendo tratado com uma frase
    # amigável, e não com erro: a conta já está ativa, não há nada a conceder.
    # Esta resposta vem ANTES da checagem de uso único de propósito — senão o
    # segundo clique legítimo viraria "link inválido" sem motivo.
    if user.email_verified:
        return MessageResponse(message="Este e-mail já estava confirmado. Pode entrar normalmente.")

    try:
        account_tokens.read_email_verification_token(body.token, user.email_verified, settings)
    except account_tokens.InvalidTokenError as exc:
        raise link_invalido from exc

    user.email_verified = True
    user.email_verified_at = datetime.now(UTC)
    user.updated_at = datetime.now(UTC)
    await db.commit()

    logger.info(f"Email confirmed: {user.email}")
    return MessageResponse(message="E-mail confirmado. Sua conta está ativa.")


# ── POST /auth/resend-verification ────────────────────────────


@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_login)
async def resend_verification(
    body: EmailRequest,
    request: Request,
    background: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """
    Reenvia o link de confirmação.

    A resposta é sempre a mesma, exista ou não a conta: caso contrário qualquer
    pessoa poderia descobrir quais e-mails estão cadastrados.

    Mesma mensagem não basta: o envio vai para segundo plano porque só o ramo
    da conta existente manda e-mail, e aguardá-lo aqui faria o RELÓGIO dizer o
    que a mensagem cala. Ver `forgot_password`.
    """
    neutra = MessageResponse(
        message="Se este e-mail estiver cadastrado e ainda não confirmado, você receberá o link."
    )

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or user.email_verified or not settings.requires_email_verification():
        return neutra

    token = account_tokens.create_email_verification_token(user.id, user.email_verified, settings)
    background.add_task(send_verification_email, user.email, user.name, token, settings)
    logger.info(f"Verification email queued (resend): {user.email}")
    return neutra


# ── POST /auth/forgot-password ────────────────────────────────


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_login)
async def forgot_password(
    body: EmailRequest,
    request: Request,
    background: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """
    Envia o link de redefinição de senha.

    Também responde igual para e-mail inexistente — a mensagem nunca confirma
    se alguém tem conta no sistema.

    E também não pode confirmar pelo RELÓGIO. O SMTP só é chamado no ramo da
    conta existente, então enquanto o envio fosse aguardado aqui dentro os dois
    ramos respondiam em tempos diferentes: o mesmo oráculo de enumeração que o
    `f8e6013` fechou no login, renascendo ao lado dele. Com `BackgroundTasks` a
    resposta sai antes de o envio começar e os dois ramos custam o mesmo.

    Hoje isso não é mensurável em produção porque não há SMTP configurado — o
    oráculo nasceria pronto no dia em que ligassem.
    """
    # Sem SMTP, prometer um e-mail que não vai sair só faria a pessoa esperar.
    # Isto revela configuração do sistema, não dados de usuário.
    if not settings.email_is_configured():
        logger.error(
            "Pedido de recuperação de senha sem SMTP configurado — o e-mail não foi enviado."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "A recuperação de senha por e-mail ainda não está disponível. "
                "Fale com o administrador para redefinir sua senha."
            ),
        )

    neutra = MessageResponse(
        message="Se este e-mail estiver cadastrado, você receberá as instruções em instantes."
    )

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or user.status != UserStatus.active:
        return neutra

    token = account_tokens.create_password_reset_token(user.id, user.password, settings)
    background.add_task(send_password_reset_email, user.email, user.name, token, settings)
    logger.info(f"Password reset queued: {user.email}")
    return neutra


# ── POST /auth/reset-password ─────────────────────────────────


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    body: PasswordResetRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """Grava a nova senha a partir do link recebido por e-mail."""
    link_invalido = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "Este link de redefinição não é mais válido. "
            "Ele vale por tempo limitado e só pode ser usado uma vez — peça um novo."
        ),
    )

    # Duas etapas: primeiro descobre de quem é o link (assinatura e tipo), e só
    # então confere se ele ainda vale para a senha atual do usuário
    try:
        user_id = account_tokens.peek_password_reset_subject(body.token, settings)
    except account_tokens.InvalidTokenError as exc:
        raise link_invalido from exc

    user = await db.get(User, user_id)
    if user is None:
        raise link_invalido

    try:
        account_tokens.read_password_reset_token(body.token, user.password, settings)
    except account_tokens.InvalidTokenError as exc:
        raise link_invalido from exc

    user.password = await run_in_threadpool(hash_password, body.password)
    user.updated_at = datetime.now(UTC)
    # Quem redefine a senha pelo e-mail comprova ser dono da caixa
    if not user.email_verified:
        user.email_verified = True
        user.email_verified_at = datetime.now(UTC)

    _audit(db, AuditAction.password_change, user.id, request)
    await db.commit()

    logger.info(f"Password reset completed: {user.email}")
    return MessageResponse(message="Senha alterada. Você já pode entrar com a nova senha.")


# ── POST /auth/login ──────────────────────────────────────────


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
@limiter.limit(settings.rate_limit_login)
async def login(
    body: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user: User | None = result.scalar_one_or_none()

    # Duas coisas acontecem nesta única verificação:
    #
    # 1. E-mail inexistente é conferido contra um hash descartável, para pagar o
    #    mesmo custo de bcrypt de um e-mail cadastrado — sem isso o tempo de
    #    resposta denuncia quais contas existem.
    # 2. O bcrypt roda numa thread separada. Ele é síncrono e custa ~250 ms:
    #    executado direto aqui, travaria o event loop e, com ele, todas as
    #    requisições em voo. Mesmo motivo do run_in_executor em
    #    app/services/storage.py.
    password_ok = await run_in_threadpool(
        verify_password,
        body.password,
        user.password if user else DUMMY_PASSWORD_HASH,
    )

    if user is None or not password_ok:
        logger.warning(f"Failed login attempt for email={body.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status != UserStatus.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta conta está inativa. Fale com um administrador.",
        )

    # Senha certa, mas e-mail ainda não confirmado: o motivo precisa ficar
    # claro, senão a pessoa fica tentando de novo achando que errou a senha
    if settings.requires_email_verification() and not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Confirme seu e-mail para ativar a conta. "
                "Procure a mensagem que enviamos ao criar o cadastro."
            ),
        )

    access_token = create_access_token(user.id, user.role.value, user.email)
    refresh_token = create_refresh_token(user.id)

    await store_refresh_token(user.id, refresh_token)

    _audit(db, AuditAction.login, user.id, request)
    await db.commit()

    logger.info(f"User logged in: {user.email}")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expires_minutes * 60,
    )


# ── POST /auth/refresh ────────────────────────────────────────


@router.post("/refresh", response_model=AccessTokenResponse, status_code=status.HTTP_200_OK)
async def refresh_token(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccessTokenResponse:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sua sessão expirou. Entre novamente para continuar.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(body.refresh_token)
    except JWTError:
        raise credentials_exc

    if payload.get("type") != "refresh":
        raise credentials_exc

    from uuid import UUID

    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError):
        raise credentials_exc

    stored = await get_stored_refresh_token(user_id)
    if stored != body.refresh_token:
        logger.warning(f"Refresh token mismatch for user_id={user_id}")
        raise credentials_exc

    result = await db.execute(select(User).where(User.id == user_id))
    user: User | None = result.scalar_one_or_none()

    if user is None or user.status != UserStatus.active:
        raise credentials_exc

    new_access_token = create_access_token(user.id, user.role.value, user.email)

    return AccessTokenResponse(
        access_token=new_access_token,
        expires_in=settings.jwt_access_token_expires_minutes * 60,
    )


# ── POST /auth/logout ─────────────────────────────────────────


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    if credentials:
        token = credentials.credentials
        try:
            payload = decode_token(token)
            exp = payload.get("exp", 0)
            now = int(datetime.now(UTC).timestamp())
            ttl = max(exp - now, 1)
            await blacklist_token(token, ttl)
        except JWTError:
            pass

    await delete_refresh_token(current_user.id)

    _audit(db, AuditAction.logout, current_user.id, request)
    await db.commit()

    logger.info(f"User logged out: {current_user.email}")
