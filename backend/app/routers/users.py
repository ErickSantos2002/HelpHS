"""
CRUD de usuários.

Permissões:
  POST   /users                   — admin | technician
  GET    /users                   — admin | technician
  GET    /users/me                — qualquer autenticado
  GET    /users/technicians       — admin | technician (lista técnicos ativos)
  GET    /users/{id}              — admin | technician (ou o próprio usuário)
  PATCH  /users/{id}              — admin | technician (ou o próprio usuário, só admin muda role)
  PATCH  /users/{id}/status       — admin | technician
  PATCH  /users/me/lgpd-consent   — qualquer autenticado (próprio consentimento)
  POST   /users/{id}/anonymize    — admin | technician (anonimiza PII — LGPD)
  DELETE /users/{id}              — admin | technician (exclusão, apenas sem tickets)
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import authorize, get_current_user, hash_password, verify_password
from app.models.models import (
    Attachment,
    AuditAction,
    AuditLog,
    ChatMessage,
    CompanyNote,
    GroupNote,
    KBArticle,
    SatisfactionSurvey,
    Ticket,
    TicketHistory,
    TicketNote,
    User,
    UserRole,
    UserStatus,
)
from app.schemas.ticket import InterruptorDaIA
from app.schemas.user import (
    LGPDConsentUpdate,
    OnboardingUpdate,
    PasswordChange,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserStatusUpdate,
    UserUpdate,
)
from app.services import storage
from app.utils.uploads import ler_ate_o_limite

router = APIRouter(prefix="/users", tags=["Users"])

# Foto de perfil tem teto próprio, menor que o de anexo: é imagem de tela,
# não documento de chamado.
_AVATAR_MAX_BYTES = 5 * 1024 * 1024


# ── Helpers ───────────────────────────────────────────────────


def _to_response(user: User) -> UserResponse:
    return UserResponse.model_validate(user)


def _audit(
    db: AsyncSession, action: AuditAction, actor_id: uuid.UUID, target_id: uuid.UUID
) -> None:
    db.add(
        AuditLog(
            user_id=actor_id,
            action=action,
            entity_type="user",
            entity_id=target_id,
        )
    )


# ── POST /users ───────────────────────────────────────────────


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> UserResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    ts = datetime.now(UTC)
    # bcrypt é síncrono e custa ~250 ms: na thread do event loop, cada cadastro
    # travaria todas as requisições em voo (mesmo motivo do login)
    senha_hash = await run_in_threadpool(hash_password, body.password)

    user = User(
        id=uuid.uuid4(),
        name=body.name,
        email=body.email,
        password=senha_hash,
        role=body.role,
        status=UserStatus.active,
        phone=body.phone,
        department=body.department,
        lgpd_consent=body.lgpd_consent,
        lgpd_consent_at=ts if body.lgpd_consent else None,
        # Explícito: o default da coluna só seria aplicado no INSERT, e a resposta
        # é montada a partir do objeto em memória
        onboarding_completed=False,
        # Mesmo motivo. E aqui a consequência ia além da resposta: a Helô lê
        # este campo antes do flush, e `bool(None)` a calaria para o cliente
        # inteiro — em silêncio, sem erro nenhum.
        ai_enabled=True,
        # Conta criada pelo admin não passa por confirmação de e-mail: quem
        # cadastrou já sabe quem é a pessoa, e travar o acesso só atrapalharia
        email_verified=True,
        email_verified_at=ts,
        created_at=ts,
        updated_at=ts,
    )
    db.add(user)
    _audit(db, AuditAction.create, actor.id, user.id)
    await db.commit()
    await db.refresh(user)
    return _to_response(user)


# ── GET /users ────────────────────────────────────────────────


@router.get("", response_model=UserListResponse)
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    role: UserRole | None = Query(default=None),
    status_filter: UserStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=100),
) -> UserListResponse:
    base = select(User)
    if role:
        base = base.where(User.role == role)
    if status_filter:
        base = base.where(User.status == status_filter)
    if search:
        pattern = f"%{search}%"
        base = base.where(User.name.ilike(pattern) | User.email.ilike(pattern))

    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()

    rows = await db.execute(base.order_by(User.created_at.desc()).offset(offset).limit(limit))
    users = rows.scalars().all()

    return UserListResponse(
        items=[_to_response(u) for u in users],
        total=total,
        limit=limit,
        offset=offset,
    )


# ── GET /users/me ─────────────────────────────────────────────


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserResponse:
    response = _to_response(current_user)
    if current_user.avatar_url and current_user.avatar_url.startswith("avatars/"):
        try:
            response.avatar_url = await storage.get_presigned_url(
                current_user.avatar_url, settings, expires=604800
            )
        except Exception:
            response.avatar_url = None
    return response


# ── GET /users/technicians ────────────────────────────────────


@router.get("/technicians", response_model=UserListResponse)
async def list_technicians(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> UserListResponse:
    """Active technicians — used by staff to populate assignee filter/dropdown."""
    rows = await db.execute(
        select(User)
        .where(User.role == UserRole.technician, User.status == UserStatus.active)
        .order_by(User.name)
    )
    users = rows.scalars().all()
    # Rota sem paginação de propósito: alimenta o filtro/dropdown de
    # responsável, que precisa da lista INTEIRA — paginar aqui esconderia
    # técnicos atrás de uma página que a tela não sabe pedir. Então limit
    # reflete o que a resposta traz, em vez do 100 fixo que sugeria uma
    # próxima página inexistente.
    return UserListResponse(
        items=[_to_response(u) for u in users],
        total=len(users),
        limit=len(users),
        offset=0,
    )


# ── GET /users/{user_id} ──────────────────────────────────────


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    # Only admin/technician can view any user; others only their own profile
    is_staff = current_user.role in (UserRole.admin, UserRole.technician)
    if not is_staff and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para acessar este item.",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    return _to_response(user)


# ── PATCH /users/me ───────────────────────────────────────────


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    update_data = body.model_dump(exclude_unset=True, exclude={"role"})
    for field, value in update_data.items():
        setattr(user, field, value)

    user.updated_at = datetime.now(UTC)
    _audit(db, AuditAction.update, current_user.id, user.id)
    await db.commit()
    await db.refresh(user)
    return _to_response(user)


# ── POST /users/me/avatar ────────────────────────────────────


@router.post("/me/avatar", response_model=UserResponse)
async def upload_avatar(
    file: Annotated[UploadFile, File(...)],
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserResponse:
    allowed_types = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Formato inválido. Use JPG, PNG, GIF ou WebP.",
        )

    # Lê por blocos e para no primeiro que cruza o limite: medir `len(data)`
    # depois de ler tudo aplicava o teto só quando os bytes já estavam na
    # memória — ver app/utils/uploads.py.
    data = await ler_ate_o_limite(file, max_bytes=_AVATAR_MAX_BYTES, rotulo="5 MB")

    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }
    key = f"avatars/{current_user.id}{ext_map[file.content_type]}"
    await storage.upload_file(data, key, file.content_type, settings)
    url = await storage.get_presigned_url(key, settings, expires=604800)

    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    user.avatar_url = key
    user.updated_at = datetime.now(UTC)
    _audit(db, AuditAction.update, current_user.id, user.id)
    await db.commit()
    await db.refresh(user)

    response = _to_response(user)
    response.avatar_url = url
    return response


# ── PATCH /users/me/onboarding ───────────────────────────────


@router.patch("/me/onboarding", response_model=UserResponse)
async def complete_onboarding(
    body: OnboardingUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    user.company_name = body.company_name
    user.cnpj = body.cnpj
    user.company_cep = body.company_cep
    user.company_address = body.company_address
    user.company_city = body.company_city
    user.company_state = body.company_state
    user.onboarding_completed = True
    user.updated_at = datetime.now(UTC)

    _audit(db, AuditAction.update, current_user.id, user.id)
    await db.commit()
    await db.refresh(user)
    return _to_response(user)


# ── POST /users/me/change-password ────────────────────────────


@router.post("/me/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChange,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    # Duas operações de bcrypt aqui — conferir a atual e hashear a nova —, as
    # duas fora da thread do event loop
    if not await run_in_threadpool(verify_password, body.current_password, user.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Senha atual incorreta",
        )

    user.password = await run_in_threadpool(hash_password, body.new_password)
    user.updated_at = datetime.now(UTC)
    _audit(db, AuditAction.update, current_user.id, user.id)
    await db.commit()


# ── PATCH /users/{user_id} ────────────────────────────────────


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    # Admin/technician can edit any user; others only themselves. Only admin can change role.
    is_staff = current_user.role in (UserRole.admin, UserRole.technician)
    if not is_staff and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para acessar este item.",
        )
    if current_user.role != UserRole.admin and body.role is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem alterar o tipo de usuário.",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    _audit(db, AuditAction.update, current_user.id, user.id)
    await db.commit()
    await db.refresh(user)
    return _to_response(user)


# ── PATCH /users/{user_id}/status ─────────────────────────────


@router.patch("/{user_id}/status", response_model=UserResponse)
async def update_user_status(
    user_id: uuid.UUID,
    body: UserStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> UserResponse:
    if actor.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot change their own status",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    user.status = body.status
    _audit(db, AuditAction.status_change, actor.id, user.id)
    await db.commit()
    await db.refresh(user)
    return _to_response(user)


@router.patch("/{user_id}/ai", response_model=UserResponse)
async def toggle_user_ai(
    user_id: uuid.UUID,
    body: InterruptorDaIA,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> UserResponse:
    """
    Liga ou desliga a IA para este cliente, em todos os chamados dele.

    Existe porque há empresa que não quer robô. A alternativa — pedir ao
    atendente para lembrar de calar a IA em cada chamado daquele cliente — não
    é alternativa.

    Vale daqui para a frente. Chamado que a Helô já triou continua com a fala
    dela no histórico: desligar não reescreve o passado.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    if user.ai_enabled != body.enabled:
        user.ai_enabled = body.enabled
        _audit(db, AuditAction.update, actor.id, user.id)
        await db.commit()
        await db.refresh(user)

    return _to_response(user)


# ── PATCH /users/me/lgpd-consent ──────────────────────────────


@router.patch("/me/lgpd-consent", response_model=UserResponse)
async def update_lgpd_consent(
    body: LGPDConsentUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    user.lgpd_consent = body.lgpd_consent
    user.lgpd_consent_at = datetime.now(UTC) if body.lgpd_consent else None
    user.updated_at = datetime.now(UTC)
    _audit(db, AuditAction.update, current_user.id, user.id)
    await db.commit()
    await db.refresh(user)
    return _to_response(user)


# ── POST /users/{user_id}/anonymize ───────────────────────────


@router.post("/{user_id}/anonymize", response_model=UserResponse)
async def anonymize_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> UserResponse:
    """Anonimiza os dados pessoais do usuário (LGPD — direito ao esquecimento)."""
    if actor.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot anonymize their own account",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    # Anonimizar é o único dos quatro que NÃO tem volta: reescreve nome e
    # e-mail e não existe caminho de desfazer. Editar e desativar são
    # reversíveis e fazem parte do dia a dia de uma equipe pequena; excluir já
    # é barrado pelas chaves estrangeiras. Só este precisa de guarda.
    #
    # Guarda de PAPEL, não de identidade: outro admin continua podendo. O que
    # se fecha é o clique errado do técnico e a conta de técnico comprometida
    # — não há MFA no sistema para segurar a segunda.
    if user.role == UserRole.admin and actor.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas um administrador pode anonimizar a conta de outro administrador.",
        )

    if user.status == UserStatus.anonymized:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="User is already anonymized"
        )

    ts = datetime.now(UTC)
    user.name = f"Usuário Anonimizado {str(user_id)[:8]}"
    user.email = f"anon_{str(user_id).replace('-', '')}@anonymized.invalid"
    user.phone = None
    user.department = None
    user.avatar_url = None
    user.lgpd_consent = False
    user.lgpd_consent_at = None
    user.status = UserStatus.anonymized
    user.updated_at = ts

    db.add(
        AuditLog(
            user_id=actor.id,
            action=AuditAction.anonymize,
            entity_type="user",
            entity_id=user_id,
            new_data={"anonymized_at": ts.isoformat()},
        )
    )
    await db.commit()
    await db.refresh(user)
    return _to_response(user)


# Toda referência a `users.id` que NÃO tem ondelete no banco — são exatamente
# estas que fazem o DELETE falhar. As outras seis (SET NULL e CASCADE) se
# resolvem sozinhas e por isso não entram aqui.
#
# A guarda contava só `Ticket.creator_id`, então um técnico sem chamados
# próprios mas com chamados atribuídos passava e ia bater na chave estrangeira.
#
# São 11 COUNTs numa rota que um admin usa raramente: preferi a clareza de uma
# lista legível — que também alimenta a mensagem de erro — a uma query só,
# montada com UNION, que ninguém consegue reler depois.
_REFERENCIAS_QUE_BLOQUEIAM: tuple[tuple[str, type[Any], InstrumentedAttribute], ...] = (
    ("chamado(s) aberto(s)", Ticket, Ticket.creator_id),
    ("chamado(s) atribuído(s)", Ticket, Ticket.assignee_id),
    ("registro(s) de histórico", TicketHistory, TicketHistory.user_id),
    ("nota(s) em grupo", GroupNote, GroupNote.author_id),
    ("nota(s) em empresa", CompanyNote, CompanyNote.author_id),
    ("nota(s) interna(s) em chamado", TicketNote, TicketNote.author_id),
    ("anexo(s) enviado(s)", Attachment, Attachment.uploaded_by),
    ("mensagem(ns) de chat", ChatMessage, ChatMessage.sender_id),
    ("artigo(s) da base de conhecimento", KBArticle, KBArticle.author_id),
    ("avaliação(ões) de atendimento", SatisfactionSurvey, SatisfactionSurvey.user_id),
    ("registro(s) de auditoria", AuditLog, AuditLog.user_id),
)

_COMO_RESOLVER = (
    "Não é possível excluir: o usuário deixou rastro que o sistema precisa "
    "manter. Use anonimizar (POST /users/{id}/anonymize), que apaga os dados "
    "pessoais e preserva o histórico."
)


# ── DELETE /users/{user_id} ───────────────────────────────────


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> None:
    """Exclui permanentemente um usuário sem tickets (LGPD)."""
    if actor.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot delete their own account",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    bloqueios: list[str] = []
    for rotulo, modelo, coluna in _REFERENCIAS_QUE_BLOQUEIAM:
        quantos = (
            await db.execute(select(func.count()).select_from(modelo).where(coluna == user_id))
        ).scalar_one()
        if quantos:
            bloqueios.append(f"{quantos} {rotulo}")

    if bloqueios:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{_COMO_RESOLVER} Encontrado: {', '.join(bloqueios)}.",
        )

    _audit(db, AuditAction.delete, actor.id, user_id)
    await db.delete(user)
    try:
        await db.commit()
    except IntegrityError:
        # Rede, não guarda principal: a lista acima é o que se espera cobrir,
        # mas uma tabela nova com FK para users nasceria fora dela. Sem este
        # except, essa tabela nova viraria 500 num DELETE — e 500 não diz ao
        # admin o que fazer.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_COMO_RESOLVER,
        ) from None
