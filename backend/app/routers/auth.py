"""
Endpoints de autenticação: login, refresh, logout.
"""

import re
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import chave_por_usuario, limiter
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    authorize,
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
    MfaChallengeResponse,
    MfaCodeRequest,
    MfaDisableRequest,
    MfaSetupResponse,
    MfaStatusResponse,
    MfaVerifyRequest,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenOnlyRequest,
    TokenResponse,
)
from app.services import account_tokens, consulta_externa, mfa, mfa_challenge
from app.services.account_emails import (
    send_account_exists_email,
    send_password_reset_email,
    send_verification_email,
)

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
@limiter.limit(settings.rate_limit_consulta_externa, key_func=chave_por_usuario)
async def lookup_cnpj(
    cnpj: str,
    request: Request,
    _: Annotated[User, Depends(get_current_user)],
) -> dict:
    cnpj_clean = re.sub(r"\D", "", cnpj)
    if len(cnpj_clean) != 14:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CNPJ inválido")

    try:
        return await consulta_externa.consulta_cnpj(cnpj_clean)
    except consulta_externa.ConsultaNaoEncontradaError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CNPJ não encontrado")
    except consulta_externa.ConsultaIndisponivelError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A consulta de CNPJ está indisponível agora. Preencha os dados manualmente.",
        )


# ── GET /auth/cep/{cep} ──────────────────────────────────────


@router.get("/cep/{cep}")
@limiter.limit(settings.rate_limit_consulta_externa, key_func=chave_por_usuario)
async def lookup_cep(
    cep: str,
    request: Request,
    _: Annotated[User, Depends(get_current_user)],
) -> dict:
    cep_clean = re.sub(r"\D", "", cep)
    if len(cep_clean) != 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CEP inválido")

    try:
        return await consulta_externa.consulta_cep(cep_clean)
    except consulta_externa.ConsultaNaoEncontradaError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CEP não encontrado")
    except consulta_externa.ConsultaIndisponivelError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A consulta de CEP está indisponível agora. Preencha os dados manualmente.",
        )


# ── POST /auth/register ───────────────────────────────────────


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_account)
async def register(
    body: RegisterRequest,
    request: Request,
    background: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RegisterResponse:
    existing = await db.execute(select(User).where(User.email == body.email))
    ja_existe = existing.scalar_one_or_none()

    now = datetime.now(UTC)
    exige_confirmacao = settings.requires_email_verification()

    if ja_existe is not None:
        # #3.1 — a resposta deixa de contar quem tem conta.
        #
        # O 409 "Este e-mail já está cadastrado" era um oráculo: com uma lista
        # de endereços, dava para descobrir quem é cliente sem nunca acertar uma
        # senha. Agora o caminho devolve exatamente o que um cadastro novo
        # devolveria, e quem é dono do endereço recebe um e-mail explicando.
        #
        # A neutralidade DEPENDE de haver como avisar. Sem e-mail, responder 201
        # manda a pessoa ao login com uma senha que não vai funcionar e nenhuma
        # explicação — e aí o 409 volta a ser o mal menor. Foi por isso que este
        # achado ficou aprovado em agosto e adiado até o Resend existir.
        if not settings.email_is_configured():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este e-mail já está cadastrado.",
            )

        background.add_task(send_account_exists_email, body.email, settings)
        logger.info("Register attempt on existing account (neutral response)")
        return RegisterResponse(email=body.email, email_verified=not exige_confirmacao)

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
        # Agendado, não aguardado: era o único dos três fluxos de e-mail que
        # segurava o handler no SMTP, sem timeout. Servidor lento atrasava o
        # cadastro; servidor que não responde o segurava até o timeout do
        # proxy. O `forgot-password` e o `resend-verification` já faziam assim.
        background.add_task(send_verification_email, user.email, user.name, token, settings)
        logger.info(f"New client registered (awaiting confirmation): user_id={user.id}")
    else:
        logger.warning(
            f"New client registered without email confirmation (SMTP not configured): {user.email}"
        )

    return RegisterResponse(email=user.email, email_verified=user.email_verified)


# ── POST /auth/verify-email ───────────────────────────────────


@router.post("/verify-email", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_token)
async def verify_email(
    body: TokenOnlyRequest,
    request: Request,
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

    logger.info(f"Email confirmed: user_id={user.id}")
    return MessageResponse(message="E-mail confirmado. Sua conta está ativa.")


# ── POST /auth/resend-verification ────────────────────────────


@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_account)
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
    logger.info(f"Verification email queued (resend): user_id={user.id}")
    return neutra


# ── POST /auth/forgot-password ────────────────────────────────


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_account)
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
    logger.info(f"Password reset queued: user_id={user.id}")
    return neutra


# ── POST /auth/reset-password ─────────────────────────────────


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_token)
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

    logger.info(f"Password reset completed: user_id={user.id}")
    return MessageResponse(message="Senha alterada. Você já pode entrar com a nova senha.")


# ── POST /auth/login ──────────────────────────────────────────


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    responses={403: {"model": MfaChallengeResponse, "description": "Falta o segundo fator"}},
)
@limiter.limit(settings.rate_limit_login)
async def login(
    body: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse | JSONResponse:
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
        # Sem o e-mail, de proposito. Esta linha registrava o que foi
        # DIGITADO numa tentativa falha: e-mail de quem nao tem conta, e
        # ocasionalmente a senha, quando a pessoa erra o campo. O que
        # importa aqui e a frequencia e a origem, e o request_id ja amarra
        # a linha ao resto da requisicao.
        logger.warning("Failed login attempt")
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

    # Daqui para baixo a senha já valeu e nenhuma credencial foi emitida ainda:
    # nada no Redis, nada no banco, nenhum commit. É por isso que a bifurcação
    # do segundo fator cabe exatamente aqui — interromper não deixa rastro.
    if user.mfa_enabled:
        return await _desafiar_segundo_fator(user)

    return await _emitir_sessao(user, request, db)


async def _emitir_sessao(user: User, request: Request, db: AsyncSession) -> TokenResponse:
    """Emite a sessão e registra o login.

    Extraída para que os dois caminhos — com e sem segundo fator — passem pelo
    mesmo código. Duas cópias divergiriam na primeira mudança, e a que
    divergisse seria a menos exercitada.
    """
    access_token = create_access_token(user.id, user.role.value, user.email)
    refresh_token = create_refresh_token(user.id)

    await store_refresh_token(user.id, refresh_token)

    _audit(db, AuditAction.login, user.id, request)
    await db.commit()

    logger.info(f"User logged in: user_id={user.id}")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expires_minutes * 60,
    )


async def _desafiar_segundo_fator(user: User) -> JSONResponse:
    """Interrompe o login e devolve o desafio, sem emitir credencial nenhuma.

    O `AuditAction.login` NÃO é gravado aqui: para quem tem segundo fator, ele
    passa a ser gravado no `/auth/mfa/verify`. Senha certa com código nunca
    digitado deixa de virar linha "login" na auditoria — "login" passa a
    significar que a sessão existiu de fato.
    """
    try:
        token = await mfa_challenge.abrir(user.id)
    except mfa_challenge.DesafioIndisponivelError as exc:
        # Sem onde guardar o desafio, não há como exigir o código. Recusar é a
        # única saída: emitir a sessão aqui desligaria o segundo fator toda vez
        # que o Redis piscasse.
        logger.error(f"MFA challenge unavailable for user_id={user.id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível iniciar a verificação em duas etapas. Tente de novo.",
        ) from exc

    logger.info(f"MFA challenge issued for user_id={user.id}")

    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content=MfaChallengeResponse(
            detail="Informe o código do seu aplicativo autenticador.",
            mfa_token=token,
            expires_in=mfa_challenge.TTL_DESAFIO,
        ).model_dump(),
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

    logger.info(f"User logged out: user_id={current_user.id}")


# ── Segundo fator (TOTP) — adesão ─────────────────────────────
#
# Nada aqui pode ser logado: nem segredo, nem código, nem a URI do QR. As linhas
# de log destas rotas dizem o que aconteceu e para quem, nunca com o quê.

_StaffDep = Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))]

# Mensagem única para desafio vencido, já usado e queimado por excesso de erros.
# Distinguir os três diria a quem tem o token qual deles aconteceu, e nenhum
# desses fatos ajuda quem é dono da conta — só quem está tentando adivinhar.
_DESAFIO_MORTO = "Sua verificação expirou. Entre novamente."


@router.post("/mfa/verify", response_model=TokenResponse)
@limiter.limit(settings.rate_limit_login)
async def mfa_verify(
    body: MfaVerifyRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Troca o desafio por uma sessão, se o código conferir.

    A ordem das operações é o desenho todo:

    1. o desafio existe?           (senão, 401 — não diz por quê)
    2. de quem ele é               (o id vive no Redis, nunca no token)
    3. a conta ainda pode entrar?  (relida do banco, não confiada ao desafio)
    4. o código casa?              (erra → conta o erro e devolve 401)
    5. este passo já foi usado?    (replay → 401)
    6. reivindica o desafio        (o DEL atômico: só um ganha)
    7. marca o passo como gasto
    8. emite a sessão
    """
    indisponivel = HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Não foi possível concluir a verificação. Tente de novo.",
    )
    morto = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_DESAFIO_MORTO)

    try:
        user_id = await mfa_challenge.dono(body.mfa_token)
    except mfa_challenge.DesafioIndisponivelError as exc:
        logger.error(f"MFA verify unavailable: {exc}")
        raise indisponivel from exc

    if user_id is None:
        raise morto

    user = await db.get(User, user_id)
    if user is None or user.status != UserStatus.active or not user.mfa_enabled:
        # Conta desativada, apagada ou com o segundo fator desligado no meio do
        # caminho: o desafio perdeu o sentido junto.
        raise morto

    if not user.mfa_secret:
        # O CHECK do banco impede este par, mas a checagem custa uma linha e o
        # alternativo seria decifrar `None`.
        logger.error(f"MFA enabled without secret for user_id={user.id}")
        raise indisponivel

    try:
        passo = mfa.casar_codigo(mfa.decifrar_segredo(user.mfa_secret), body.code)
    except mfa.SegredoIlegivelError as exc:
        # Chave de cifra trocada depois do cadastro: ninguém entra até o segredo
        # ser recadastrado. É o preço de a chave morar fora do banco.
        logger.error(f"MFA secret unreadable for user_id={user.id}")
        raise indisponivel from exc

    try:
        if passo is None:
            await mfa_challenge.registrar_erro(body.mfa_token)
            logger.warning(f"MFA code rejected for user_id={user.id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Código inválido. Tente novamente.",
            )

        if await mfa_challenge.passo_ja_usado(user.id, passo):
            # O código ainda é matematicamente válido, mas já entregou uma
            # sessão. Sem isto, quem interceptasse o código teria ~90 s para
            # usá-lo de novo.
            logger.warning(f"MFA code replayed for user_id={user.id}")
            raise morto

        if not await mfa_challenge.consumir(body.mfa_token):
            # Outra requisição reivindicou o mesmo desafio primeiro.
            raise morto

        await mfa_challenge.marcar_passo(user.id, passo)
    except mfa_challenge.TentativasEsgotadasError as exc:
        logger.warning(f"MFA challenge burned after too many errors for user_id={user.id}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas. Entre novamente.",
        ) from exc
    except mfa_challenge.DesafioIndisponivelError as exc:
        logger.error(f"MFA verify unavailable: {exc}")
        raise indisponivel from exc

    logger.info(f"MFA verified for user_id={user.id}")
    return await _emitir_sessao(user, request, db)


async def _despeja_sessoes(user_id: uuid.UUID) -> None:
    """Apaga o refresh, derrubando as sessões abertas dessa conta.

    Existe uma única chave `token:refresh:{uid}` por usuário, então apagá-la
    despeja todas de uma vez.

    Por que é obrigatório aqui: `/auth/refresh` confere tipo, correspondência e
    status da conta — **nunca `mfa_enabled`**. Sem esta linha, quem já tivesse a
    senha e uma sessão aberta seguiria renovando access tokens por até sete dias
    sem jamais ver um código, e o recurso falharia exatamente no caso em que
    alguém liga o segundo fator por desconfiar que foi comprometido.

    O que ela NÃO resolve: os access tokens já emitidos continuam valendo até o
    próprio vencimento. A exposição cai de sete dias para o TTL do access, não
    para zero.
    """
    await delete_refresh_token(user_id)


@router.get("/mfa", response_model=MfaStatusResponse)
async def mfa_status(current_user: _StaffDep) -> MfaStatusResponse:
    return MfaStatusResponse(
        enabled=current_user.mfa_enabled,
        pending=bool(current_user.mfa_secret) and not current_user.mfa_enabled,
        available=mfa.mfa_disponivel(),
    )


@router.post("/mfa/setup", response_model=MfaSetupResponse)
async def mfa_setup(
    response: Response,
    current_user: _StaffDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MfaSetupResponse:
    """Gera um segredo e o guarda cifrado, **sem ligar o segundo fator**.

    Ligar só acontece em `/mfa/activate`, depois de o código provar que o
    aplicativo pareou. Ligar aqui trancaria a conta de quem lesse o QR errado.
    """
    if not mfa.mfa_disponivel():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O segundo fator não está disponível neste ambiente.",
        )

    if current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O segundo fator já está ativo. Desligue antes de cadastrar outro.",
        )

    segredo = mfa.gerar_segredo()
    current_user.mfa_secret = mfa.cifrar_segredo(segredo)
    current_user.mfa_confirmed_at = None
    await db.commit()

    # A resposta carrega o segredo em claro — cache intermediário é vazamento.
    response.headers["Cache-Control"] = "no-store"
    logger.info(f"MFA secret issued for user_id={current_user.id}")

    return MfaSetupResponse(
        secret=mfa.normalizar_segredo_para_exibicao(segredo),
        otpauth_uri=mfa.uri_de_provisionamento(segredo, current_user.email),
    )


@router.post("/mfa/activate", status_code=status.HTTP_204_NO_CONTENT)
async def mfa_activate(
    body: MfaCodeRequest,
    request: Request,
    current_user: _StaffDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    if not current_user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nenhum segredo pendente. Cadastre o aplicativo primeiro.",
        )

    if not mfa.verificar_codigo(mfa.decifrar_segredo(current_user.mfa_secret), body.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código inválido. Confira o aplicativo e tente de novo.",
        )

    current_user.mfa_enabled = True
    current_user.mfa_confirmed_at = datetime.now(UTC)
    _audit(db, AuditAction.update, current_user.id, request)
    await db.commit()

    await _despeja_sessoes(current_user.id)
    logger.info(f"MFA activated for user_id={current_user.id}")


@router.delete("/mfa", status_code=status.HTTP_204_NO_CONTENT)
async def mfa_disable(
    body: MfaDisableRequest,
    request: Request,
    current_user: _StaffDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Desligar exige a senha atual.

    Sem esse atrito, uma sessão sequestrada removeria a proteção que existe
    justamente para o caso de a sessão ser sequestrada.
    """
    senha_ok = await run_in_threadpool(verify_password, body.password, current_user.password)
    if not senha_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Senha incorreta.",
        )

    # Os três juntos: `mfa_enabled` verdadeiro com segredo nulo é o par que o
    # CHECK do banco recusa, e o inverso deixaria segredo órfão para trás.
    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    current_user.mfa_confirmed_at = None
    _audit(db, AuditAction.update, current_user.id, request)
    await db.commit()

    await _despeja_sessoes(current_user.id)
    logger.info(f"MFA disabled for user_id={current_user.id}")
