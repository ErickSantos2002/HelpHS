"""
CRUD de usuários.

Permissões:
  POST   /users                   — admin | technician (só admin cria staff)
  GET    /users                   — admin | technician
  GET    /users/me                — qualquer autenticado
  GET    /users/technicians       — admin | technician (lista técnicos ativos)
  GET    /users/{id}              — admin | technician (ou o próprio usuário)
  PATCH  /users/{id}              — admin | technician (ou o próprio usuário, só admin muda role)
  PATCH  /users/{id}/status       — admin | technician
  PATCH  /users/me/lgpd-consent   — qualquer autenticado (próprio consentimento)
  GET    /users/me/avatar/exibicao — qualquer autenticado (a própria escolha)
  PUT    /users/me/avatar/exibicao — qualquer autenticado (só a própria foto para terceiros)
  POST   /users/{id}/anonymize    — admin | technician (anonimiza PII — LGPD)
  POST   /users/{id}/avatar/remove — admin (tira a foto de outra conta, com justificativa)
  DELETE /users/{id}              — admin | technician (exclusão, apenas sem tickets)
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
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
    LibraryFile,
    SatisfactionSurvey,
    Ticket,
    TicketHistory,
    TicketNote,
    TicketSlaExtension,
    User,
    UserRole,
    UserStatus,
)
from app.schemas.ticket import InterruptorDaIA
from app.schemas.user import (
    AvatarExibicaoStatus,
    AvatarExibicaoUpdate,
    AvatarRemovalByAdmin,
    AvisoDaExibicao,
    LGPDConsentStatus,
    LGPDConsentUpdate,
    OnboardingUpdate,
    PasswordChange,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserStatusUpdate,
    UserUpdate,
)
from app.services import consentimento, exibicao_da_foto, storage
from app.utils.avatar import (
    EXTENSOES_DO_AVATAR,
    chave_do_avatar,
    chave_legitima_do_avatar,
)
from app.utils.telefone import telefone_ausente
from app.utils.uploads import ler_ate_o_limite

router = APIRouter(prefix="/users", tags=["Users"])

# Foto de perfil tem teto próprio, menor que o de anexo: é imagem de tela,
# não documento de chamado.
_AVATAR_MAX_BYTES = 5 * 1024 * 1024

# A regra da chave legítima mora em `app/utils/avatar.py` desde a Fase 3B, que
# a usa também no chamado e no chat. Os nomes antigos ficam aqui como apelidos:
# o comportamento é o mesmo, e nenhum consumidor deste arquivo precisou mudar.
_AVATAR_EXTENSOES = EXTENSOES_DO_AVATAR
_chave_do_avatar = chave_do_avatar
_avatar_do_proprio_usuario = chave_legitima_do_avatar


# ── Helpers ───────────────────────────────────────────────────


def _to_response(user: User) -> UserResponse:
    response = UserResponse.model_validate(user)
    # Toda resposta de usuário passa por aqui: a referência indevida gravada
    # antes da correção não sai por nenhuma delas, nem crua.
    response.avatar_url = _avatar_do_proprio_usuario(user)
    return response


async def _trava_usuario(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Lê a linha do usuário com `FOR UPDATE`, que só solta no fim da transação.

    `populate_existing`: o `get_current_user` já carregou esta linha na mesma
    sessão, e sem ele o SQLAlchemy devolveria o objeto do mapa de identidade
    com os valores de ANTES da espera pela trava.
    """
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


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


_ERRO_REMOVER = "Não é possível remover o telefone de um cliente ativo."
_ERRO_EXIGE = "Cliente ativo precisa de um telefone válido."


def _guarda_telefone_do_cliente(
    *,
    role_final: UserRole,
    status_final: UserStatus,
    telefone_final: str | None,
    telefone_anterior: str | None,
    mudou_papel_ou_situacao: bool,
) -> None:
    """Recusa as duas — e somente as duas — perdas de telefone que importam.

    A regra é PROSPECTIVA. Medido em produção em 18/09/2026: 14 contas
    `role=client` + `status=active` estão sem telefone. São contas de teste,
    mas existem fisicamente, e uma exigência genérica do tipo "cliente ativo
    sempre precisa de telefone" as deixaria incapazes de editar o próprio
    nome. Por isso o que se proíbe é a PERDA, não a ausência:

    P1  REMOÇÃO   — tinha telefone e a requisição o esvazia.
    P2  TRANSIÇÃO — virar cliente, ou voltar a `active`, sem telefone.

    Quem já estava sem telefone e não mexeu em papel nem em situação passa,
    de propósito. O saneamento dessas linhas é tarefa separada, e dado
    histórico se corrige em script avulso — nunca numa validação de entrada.

    `telefone_anterior` é `None` na criação: lá não há passado, e é sempre a
    transição (P2) que responde.
    """
    if role_final != UserRole.client or status_final != UserStatus.active:
        return
    if not telefone_ausente(telefone_final):
        return

    # Daqui para baixo o estado resultante é cliente ativo SEM telefone.
    if not telefone_ausente(telefone_anterior):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=_ERRO_REMOVER)
    if mudou_papel_ou_situacao:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=_ERRO_EXIGE)
    # Legado intocado: seguia sem telefone e segue, sem mudar papel nem
    # situação. Passa.


_ERRO_PAPEL = "Apenas administradores podem alterar o tipo de usuário."


def _guarda_de_atribuicao_de_papel(*, ator: User, papel_atribuido: UserRole | None) -> None:
    """Papel é atribuição de administrador — nas duas rotas em que se atribui.

    A regra já existia, e existia só em `update_user`. `create_user` deixava o
    `role` do corpo chegar ao `User()` sem perguntar quem estava criando: um
    técnico criava um administrador numa requisição e entrava nele em seguida,
    porque escolheu a senha. Não faltava a regra — faltava ela valer no único
    lugar onde a conta NASCE. Agora tem um autor só.

    `papel_atribuido` é `None` quando a requisição não atribui papel nenhum, e
    o que conta como atribuição muda com a rota. Por isso a tradução é de cada
    chamador, e a decisão é daqui:

    * `update_user` passa o papel do corpo **só quando ele DIFERE do atual**.
      Mandar de volta o papel que a pessoa já tem não move ninguém de lugar, e
      tratar isso como atribuição tinha uma consequência que ninguém quis:
      o formulário de edição manda `role` sempre, então o técnico levava 403
      ao salvar QUALQUER campo — nome, departamento, telefone. A regra que
      protegia a promoção estava, na prática, proibindo a edição inteira.
      Rebaixar alguém a cliente continua sendo atribuição, porque muda.
    * `create_user` passa `None` quando o papel pedido é `client`, o default do
      schema. O front manda `role` SEMPRE (`UsersPage.tsx` abre o formulário
      com `role: "client"`), então olhar a PRESENÇA do campo recusaria toda
      criação de cliente feita por técnico — que é o uso real da tela.

    O efeito somado é um só: quem não é admin não produz conta de staff nem
    move ninguém de papel. Criar técnico também é escalação, só que lateral —
    staff lê chamado alheio e nota interna.
    """
    if papel_atribuido is None or ator.role == UserRole.admin:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ERRO_PAPEL)


_ERRO_RAMAL = "Apenas administradores podem configurar o ramal da telefonia."
_ERRO_RAMAL_DE_CLIENTE = "Cliente não tem ramal de telefonia."
_ERRO_RAMAL_OCUPADO = "Este ramal já está vinculado a outro usuário."


def _guarda_de_atribuicao_de_ramal(*, ator: User, ramal_enviado: bool) -> None:
    """Ramal é provisionamento administrativo, não configuração de perfil.

    Nem o próprio técnico mexe no seu: quem pudesse escolher o próprio ramal
    poderia reivindicar o de outra pessoa, e passaria a originar ligações com a
    identidade dela. É a mesma família de problema que
    `_guarda_de_atribuicao_de_papel` fecha, e por isso tem a mesma forma.

    ⚠️ O sinal aqui é **se o campo veio**, não o valor — ao contrário do papel.
    `api4com_extension = null` é uma operação legítima e significativa: é assim
    que o admin REMOVE um vínculo. Olhar o valor confundiria remover com não
    pedir nada, e um não-admin conseguiria apagar o ramal alheio mandando nulo.
    """
    if not ramal_enviado or ator.role == UserRole.admin:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ERRO_RAMAL)


def _guarda_de_ramal_do_cliente(*, papel_final: UserRole, ramal_final: str | None) -> None:
    """Cliente não origina ligação, logo não tem ramal.

    A regra olha o ESTADO RESULTANTE, e não o campo enviado — mesma escolha do
    `_guarda_telefone_do_cliente`. Isso cobre os dois caminhos com uma frase
    só: dar ramal a quem é cliente, e rebaixar a cliente quem tem ramal. O
    segundo passaria despercebido por uma guarda que só olhasse o campo.
    """
    if ramal_final is not None and papel_final == UserRole.client:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_ERRO_RAMAL_DE_CLIENTE,
        )


async def _guarda_de_ramal_unico(db: AsyncSession, ramal: str, usuario_id: uuid.UUID) -> None:
    """Consulta antes de gravar, como o e-mail duplicado do `create_user`.

    O índice único é a invariante; esta consulta existe para o conflito virar
    409 com texto de domínio em vez de `IntegrityError` virando 500.

    Exclui o próprio usuário: regravar o mesmo ramal em quem já o tem é
    idempotente, não conflito.

    ⚠️ Resta a corrida entre a consulta e o INSERT — dois admins gravando o
    mesmo ramal no mesmo instante. O índice recusa o segundo de qualquer jeito;
    o que se perde é a mensagem boa. É a mesma janela que o cadastro por e-mail
    tem desde sempre, e o backend sobe com UM worker.
    """
    result = await db.execute(
        select(User).where(User.api4com_extension == ramal, User.id != usuario_id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_ERRO_RAMAL_OCUPADO)


# ── POST /users ───────────────────────────────────────────────


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> UserResponse:
    # Autorização antes de validação: o que decide é QUEM está criando.
    _guarda_de_atribuicao_de_papel(
        ator=actor,
        # `client` é o default do schema — pedi-lo não é atribuir papel.
        papel_atribuido=None if body.role == UserRole.client else body.role,
    )

    # `status=UserStatus.active` é literal logo abaixo, então o estado
    # resultante depende só do papel escolhido. Criar já é a transição.
    _guarda_telefone_do_cliente(
        role_final=body.role,
        status_final=UserStatus.active,
        telefone_final=body.phone,
        telefone_anterior=None,
        mudou_papel_ou_situacao=True,
    )

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
    if body.lgpd_consent:
        # Quem marcou foi a equipe, não o titular: a origem diz isso, e o IP
        # fica de fora porque seria o de quem criou a conta.
        consentimento.registra_aceite(
            db,
            user_id=user.id,
            origem=consentimento.ORIGEM_CRIADO_POR_TERCEIRO,
            ip=None,
            agora=ts,
        )
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
    # Só a chave do PRÓPRIO usuário é assinada. O link autoriza por posse do
    # token, não por dono: assinar `avatars/<id-de-outro>` entregaria a foto
    # de outra conta. `_to_response` já zerou o que não for legítimo.
    chave = response.avatar_url
    if chave:
        try:
            response.avatar_url = await storage.get_presigned_url(chave, settings, expires=604800)
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

    # `role` e `api4com_extension` saem aqui pelo mesmo motivo: o próprio
    # perfil não promove ninguém nem se dá um ramal. Ver
    # `tests/test_escalacao_por_users_me.py`, que trata este `exclude` como a
    # defesa de uma palavra só que ele é.
    update_data = body.model_dump(exclude_unset=True, exclude={"role", "api4com_extension"})
    # Aqui nem papel nem situação mudam (o `role` sai no `exclude`, e `status`
    # não existe neste schema): só a remoção (P1) pode acontecer.
    if "phone" in update_data:
        _guarda_telefone_do_cliente(
            role_final=user.role,
            status_final=user.status,
            telefone_final=update_data["phone"],
            telefone_anterior=user.phone,
            mudou_papel_ou_situacao=False,
        )

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
    if file.content_type not in _AVATAR_EXTENSOES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Formato inválido. Use JPG, PNG, GIF ou WebP.",
        )

    # Lê por blocos e para no primeiro que cruza o limite: medir `len(data)`
    # depois de ler tudo aplicava o teto só quando os bytes já estavam na
    # memória — ver app/utils/uploads.py.
    data = await ler_ate_o_limite(file, max_bytes=_AVATAR_MAX_BYTES, rotulo="5 MB")

    # A linha é travada ANTES de gravar o arquivo, e só solta no commit: a
    # remoção pelo admin trava a mesma linha, então as duas nunca se cruzam
    # no meio. Sem isto, o admin podia isolar e apagar o arquivo recém-gravado
    # aqui, e este commit apontaria a linha para um arquivo que já não existe.
    # A leitura do corpo fica FORA da trava — um upload lento não segura a
    # linha. Ver "A foto removida pelo administrador" em docs/decisoes-e-regras.md.
    user = await _trava_usuario(db, current_user.id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    # O `get_current_user` conferiu a situação ANTES da leitura do corpo. Se a
    # conta foi anonimizada ou desativada nesse meio-tempo, gravar a foto agora
    # devolveria dado pessoal a uma conta anonimizada.
    if user.status != UserStatus.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta conta está inativa. Fale com um administrador.",
        )

    key = _chave_do_avatar(current_user.id, _AVATAR_EXTENSOES[file.content_type])
    await storage.upload_file(data, key, file.content_type, settings)
    url = await storage.get_presigned_url(key, settings, expires=604800)

    # Só a chave LEGÍTIMA anterior é candidata a sair do disco: uma
    # referência gravada antes do PR #85 pode apontar para a foto de outra
    # conta, e trocar a minha não pode apagar a dela.
    anterior = _avatar_do_proprio_usuario(user)

    user.avatar_url = key
    user.updated_at = datetime.now(UTC)
    _audit(db, AuditAction.update, current_user.id, user.id)
    await db.commit()
    await db.refresh(user)

    # Depois do commit, e só se a extensão mudou: até aqui a linha ainda
    # apontava para o arquivo antigo, e apagá-lo antes deixaria a pessoa sem
    # foto se o banco falhasse. Mesma extensão é a mesma chave — o arquivo
    # acabou de ser sobrescrito, e apagá-lo seria apagar a foto nova.
    if anterior and anterior != key:
        await storage.delete_file(anterior, settings)

    response = _to_response(user)
    response.avatar_url = url
    return response


# ── DELETE /users/me/avatar ──────────────────────────────────


@router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT)
async def remove_avatar(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Remove a própria foto. Sem foto, não há o que fazer: 204 do mesmo jeito.

    Não recebe chave nenhuma: tudo sai do usuário autenticado. O arquivo só é
    apagado se a referência for a chave legítima dele; uma referência indevida
    gravada antes do PR #85 é zerada (é a linha de quem pediu), mas nunca vira
    `delete_file` — ela pode apontar para a foto de outra conta.
    """
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    if not user.avatar_url:
        return

    chave = _avatar_do_proprio_usuario(user)

    user.avatar_url = None
    user.updated_at = datetime.now(UTC)
    _audit(db, AuditAction.update, current_user.id, user.id)
    await db.commit()

    # Depois do commit, como na troca: se o banco falhar, a linha ainda aponta
    # para um arquivo que continua lá. O `delete_file` não levanta — arquivo
    # já ausente é sucesso, e erro de disco vira aviso no log —, então a
    # remoção nunca fica travada por um volume que perdeu o arquivo.
    if chave:
        await storage.delete_file(chave, settings)


# ── GET/PUT /users/me/avatar/exibicao ────────────────────────
#
# A foto para OUTRAS pessoas nos chamados (Fase 3B). Rota própria, e só do
# titular: nenhum PATCH genérico, cadastro, onboarding ou edição pelo admin
# mexe nesta escolha — o campo não existe em `UserUpdate`, `UserCreate` nem
# `OnboardingUpdate`. Ver "A foto para outras pessoas" em docs/decisoes-e-regras.md.


def _status_da_exibicao(user: User, settings: Settings) -> AvatarExibicaoStatus:
    aviso = exibicao_da_foto.aviso_vigente(settings)
    return AvatarExibicaoStatus(
        autorizada=user.avatar_visivel_a_terceiros,
        disponivel=aviso is not None,
        aviso=(
            AvisoDaExibicao(
                versao=aviso.versao,
                rotulo=aviso.rotulo,
                explicacao=list(aviso.explicacao_para(user.role)),
            )
            if aviso is not None
            else None
        ),
    )


@router.get("/me/avatar/exibicao", response_model=AvatarExibicaoStatus)
async def get_avatar_exibicao(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AvatarExibicaoStatus:
    """A escolha atual de quem está logado, e o texto que a tela deve mostrar."""
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    return _status_da_exibicao(user, settings)


_AUTORIZACAO_INDISPONIVEL = (
    "A opção de mostrar a foto para outras pessoas ainda não está disponível."
)
_AVISO_DESATUALIZADO = (
    "O texto desta opção mudou desde que a página foi aberta. Recarregue a "
    "página e leia de novo antes de permitir."
)


@router.put("/me/avatar/exibicao", response_model=AvatarExibicaoStatus)
async def put_avatar_exibicao(
    body: AvatarExibicaoUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AvatarExibicaoStatus:
    """Autoriza ou revoga a foto para outras pessoas. Só a própria conta.

    A linha é travada (`FOR UPDATE`) antes de ler o estado: dois pedidos ao
    mesmo tempo se enfileiram, e o segundo vê o que o primeiro gravou. Por
    isso repetir a escolha — no duplo clique ou em duas abas — não grava um
    segundo evento, e estado e histórico nunca divergem. Estado e evento vão
    no mesmo commit; se ele falhar, nenhum dos dois fica.
    """
    user = await _trava_usuario(db, current_user.id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    # Conta não ativa nem chega aqui: o `get_current_user` a recusa com 403.
    # Esta conferência cobre só a corrida de a conta ser desativada entre a
    # autenticação e a trava — a mesma do upload. Nessa corrida, barra só
    # AUTORIZAR; e, de todo modo, a foto de conta não ativa não sai para
    # terceiros (`app/utils/avatar.py`), com ou sem autorização gravada.
    if body.autorizada and user.status != UserStatus.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta conta está inativa. Fale com um administrador.",
        )

    try:
        evento = exibicao_da_foto.altera_exibicao(
            db,
            usuario=user,
            autorizada=body.autorizada,
            versao_apresentada=body.versao_aviso,
            ip=request.client.host if request.client else None,
            agora=datetime.now(UTC),
            settings=settings,
        )
    except exibicao_da_foto.AutorizacaoIndisponivelError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=_AUTORIZACAO_INDISPONIVEL
        ) from None
    except exibicao_da_foto.AvisoDesatualizadoError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=_AVISO_DESATUALIZADO
        ) from None

    # A resposta sai da linha travada, ANTES do commit: depois dele o objeto
    # expira, e reler fora da sessão seria uma consulta a mais por nada.
    resposta = _status_da_exibicao(user, settings)
    if evento is None:
        # Nada mudou. Solta a trava já, em vez de esperar o fim da requisição.
        await db.rollback()
        return resposta

    # `updated_at` fica como estava (ver `altera_exibicao`): é o token de
    # versão da remoção da foto pelo admin.
    _audit(db, AuditAction.update, current_user.id, user.id)
    await db.commit()
    return resposta


# ── POST /users/{user_id}/avatar/remove ──────────────────────

_CONTA_MUDOU = (
    "A conta deste usuário mudou depois que você abriu a tela — pode ser uma "
    "foto nova. A lista foi atualizada: confira e tente de novo."
)


@router.post("/{user_id}/avatar/remove", response_model=UserResponse)
async def remove_user_avatar_by_admin(
    user_id: uuid.UUID,
    body: AvatarRemovalByAdmin,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserResponse:
    """O admin tira a foto de perfil de outra conta, com justificativa.

    Nada da requisição escolhe o arquivo: a chave sai da linha do alvo e só
    vale se for a legítima dele (`_avatar_do_proprio_usuario`). Referência
    indevida é zerada sem tocar em disco nenhum.

    Concorrência com o upload do próprio dono — ver "A foto removida pelo
    administrador" em docs/decisoes-e-regras.md:
      1. a linha é travada (`FOR UPDATE`), e o upload trava a mesma linha
         antes de gravar o arquivo;
      2. o pedido traz o `updated_at` da linha que o admin tinha na tela
         (`expected_updated_at`); se a linha travada não é mais essa — um
         upload terminou enquanto ele escrevia a justificativa, ou enquanto
         este pedido esperava a trava —, devolve 409 sem mexer em nada. A
         foto nova não é apagada por uma decisão tomada antes dela;
      3. o arquivo é ISOLADO antes do commit e só o nome isolado é apagado
         depois: um upload que entre logo após o commit grava a chave pública
         de novo, e nada daqui a alcança.
    """
    if actor.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Para remover a sua própria foto, use a opção do seu perfil.",
        )

    user = await _trava_usuario(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    if not user.avatar_url:
        # Nada a remover, nada a auditar — como na remoção da própria foto.
        return _to_response(user)

    # Igualdade, e não "mais novo que": é um token de versão, e o relógio de
    # quem escreveu a linha (a API, ou o banco pelo `onupdate`) não entra na
    # conta. Qualquer escrita na conta desde que a tela carregou dá 409.
    if user.updated_at != body.expected_updated_at:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONTA_MUDOU)

    chave = _avatar_do_proprio_usuario(user)

    user.avatar_url = None
    user.updated_at = datetime.now(UTC)
    auditoria = AuditLog(
        user_id=actor.id,
        action=AuditAction.update,
        entity_type="user",
        entity_id=user.id,
        old_data={"tinha_foto": True},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:500],
    )
    db.add(auditoria)

    # Isolar é a ÚLTIMA coisa antes do commit, e dentro do mesmo `try`: nada
    # que possa falhar fica entre o arquivo sair da chave e o caminho que o
    # devolve.
    isolado: str | None = None
    try:
        if chave:
            isolado = await storage.isola_arquivo(chave, settings)
        # O valor de uma referência indevida NÃO entra: pode ser URL de
        # terceiro. Só o fato de que ela existia.
        auditoria.new_data = {
            "operacao": "remocao_de_foto_pelo_admin",
            "justificativa": body.justification,
            "referencia_indevida": chave is None,
            "arquivo_encontrado": isolado is not None,
        }
        await db.commit()
    except BaseException:
        # `BaseException`: um cancelamento no meio do commit também tem de
        # devolver o arquivo. A linha continua apontando para a chave: o
        # arquivo volta para ela — antes do rollback, enquanto a trava ainda
        # pode estar de pé. A devolução nunca sobrescreve: se um upload já
        # gravou a chave, a foto dele fica.
        if isolado and chave:
            await storage.devolve_arquivo(isolado, chave, settings)
        await db.rollback()
        raise

    # Depois do commit, e só o nome isolado. `delete_file` não levanta: se o
    # disco falhar aqui, fica um arquivo órfão fora da chave pública (aviso no
    # log) — nunca uma linha apontando para o vazio.
    if isolado:
        await storage.delete_file(isolado, settings)

    await db.refresh(user)
    return _to_response(user)


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
    request: Request,
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
    # O mesmo rastro da redefinição por e-mail (`auth.py`): a Política de
    # Privacidade promete IP e navegador nos eventos de conta, e a troca de
    # senha é um deles.
    db.add(
        AuditLog(
            user_id=current_user.id,
            action=AuditAction.password_change,
            entity_type="user",
            entity_id=user.id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent", ""),
        )
    )
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
    # `model_fields_set` e não o valor: nulo aqui é remover, não "não pediu".
    _guarda_de_atribuicao_de_ramal(
        ator=current_user,
        ramal_enviado="api4com_extension" in body.model_fields_set,
    )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    # A guarda do papel desceu para DEPOIS da leitura, porque agora ela precisa
    # saber o papel atual para responder "isto muda alguma coisa?". Só chega
    # aqui quem é staff ou está editando a si mesmo — o 403 de acesso já foi
    # dado acima —, então trocar a ordem não revela existência de conta a
    # ninguém que já não pudesse listá-la.
    _guarda_de_atribuicao_de_papel(
        ator=current_user,
        papel_atribuido=body.role if body.role != user.role else None,
    )

    update_data = body.model_dump(exclude_unset=True)
    # O estado resultante só difere do atual nos campos realmente enviados —
    # é o `exclude_unset` que separa "não mandou" de "mandou vazio", e a regra
    # prospectiva depende dessa distinção para não travar conta legada.
    papel_final = update_data.get("role") or user.role
    if "phone" in update_data or papel_final != user.role:
        _guarda_telefone_do_cliente(
            role_final=papel_final,
            status_final=user.status,
            telefone_final=(update_data["phone"] if "phone" in update_data else user.phone),
            telefone_anterior=user.phone,
            mudou_papel_ou_situacao=papel_final != user.role,
        )

    mudou_o_ramal = "api4com_extension" in update_data
    if mudou_o_ramal or papel_final != user.role:
        ramal_final = update_data["api4com_extension"] if mudou_o_ramal else user.api4com_extension
        _guarda_de_ramal_do_cliente(papel_final=papel_final, ramal_final=ramal_final)
    if mudou_o_ramal and update_data["api4com_extension"] is not None:
        await _guarda_de_ramal_unico(db, update_data["api4com_extension"], user.id)

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

    # Reativar é o instante em que a conta volta a valer para a telefonia:
    # é aqui que um cliente sem telefone precisa ganhar um. Desativar nunca
    # é bloqueado — a regra guarda o estado ATIVO, não a saída dele.
    _guarda_telefone_do_cliente(
        role_final=user.role,
        status_final=body.status,
        telefone_final=user.phone,
        telefone_anterior=user.phone,
        mudou_papel_ou_situacao=body.status != user.status,
    )

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


@router.get("/me/lgpd-consent", response_model=LGPDConsentStatus)
async def get_lgpd_consent(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LGPDConsentStatus:
    """A situação do aceite de quem está logado — o que a tela de re-aceite lê."""
    ultimo = await consentimento.ultimo_aceite_vigente(db, current_user.id)
    return LGPDConsentStatus(
        revisao_politica_vigente=settings.lgpd_revisao_politica,
        revisao_termos_vigente=settings.lgpd_revisao_termos,
        revisao_politica_aceita=ultimo.revisao_politica if ultimo else None,
        revisao_termos_aceita=ultimo.revisao_termos if ultimo else None,
        precisa_reaceitar=consentimento.precisa_reaceitar(
            ultimo, role=current_user.role, settings=settings
        ),
    )


@router.patch("/me/lgpd-consent", response_model=UserResponse)
async def update_lgpd_consent(
    body: LGPDConsentUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    agora = datetime.now(UTC)
    user.lgpd_consent = body.lgpd_consent
    user.lgpd_consent_at = agora if body.lgpd_consent else None
    user.updated_at = agora
    # As colunas acima são a leitura rápida e seguem mutáveis. A prova fica no
    # histórico: conceder é linha nova, revogar fecha as abertas sem apagar.
    if body.lgpd_consent:
        consentimento.registra_aceite(
            db,
            user_id=user.id,
            origem=consentimento.ORIGEM_ALTERACAO_PROPRIA,
            ip=request.client.host if request.client else None,
            agora=agora,
        )
    else:
        await consentimento.revoga_aceites(db, user_id=user.id, agora=agora)
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
    settings: Annotated[Settings, Depends(get_settings)],
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

    # A foto é dado pessoal: zerar a referência e deixar o arquivo no volume
    # não anonimiza nada. Só a chave legítima da conta é apagada — e só depois
    # do commit, como na remoção pela própria pessoa.
    foto = _avatar_do_proprio_usuario(user)

    ts = datetime.now(UTC)
    user.name = f"Usuário Anonimizado {str(user_id)[:8]}"
    user.email = f"anon_{str(user_id).replace('-', '')}@anonymized.invalid"
    user.phone = None
    user.department = None
    user.avatar_url = None
    user.lgpd_consent = False
    user.lgpd_consent_at = None
    # O ramal tem índice ÚNICO (`uq_users_api4com_extension`), e nada aqui o
    # zerava até 29/09/2026 — a conta perdia nome, e-mail e telefone, mas
    # continuava "dona" do ramal para sempre, e nenhum outro técnico podia
    # recebê-lo. Não é dado pessoal (não entra na LGPD por isso), é recurso
    # operacional preso a uma conta morta.
    user.api4com_extension = None
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
    if foto:
        await storage.delete_file(foto, settings)
    return _to_response(user)


# Toda referência a `users.id` que NÃO tem ondelete no banco — são exatamente
# estas que fazem o DELETE falhar. As outras nove (SET NULL e CASCADE) se
# resolvem sozinhas e por isso não entram aqui.
#
# A guarda contava só `Ticket.creator_id`, então um técnico sem chamados
# próprios mas com chamados atribuídos passava e ia bater na chave estrangeira.
#
# São 13 COUNTs numa rota que um admin usa raramente: preferi a clareza de uma
# lista legível — que também alimenta a mensagem de erro — a uma query só,
# montada com UNION, que ninguém consegue reler depois.
#
# ⚠️ Esta lista é escrita à mão contra o SCHEMA, não gerada dele — e por isso
# ela já ficou desatualizada uma vez: nasceu em 25/08/2026 com 11 entradas, e
# duas tabelas com FK sem `ondelete` chegaram depois sem que ninguém voltasse
# aqui para acrescentá-las (`library_files` em 10/09, `ticket_sla_extensions`
# em 23/09 — auditado em 29/09/2026, contra `information_schema` real, não
# contra esta lista). O `except IntegrityError` de `delete_user` cobria a
# lacuna com um 409 genérico enquanto ela existiu; as duas entradas abaixo
# devolvem a contagem exata que faltava. Da próxima vez que uma migration
# criar uma FK para `users.id` sem `ondelete`, é AQUI que ela precisa entrar —
# não há teste que detecte a omissão por conta própria, e é por isso que este
# comentário existe.
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
    ("arquivo(s) da biblioteca", LibraryFile, LibraryFile.uploaded_by),
    ("extensão(ões) de SLA concedida(s)", TicketSlaExtension, TicketSlaExtension.user_id),
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
