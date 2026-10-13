"""
CRUD de Produtos e Equipamentos.

Permissões:
  Products:
    POST   /products            — admin | technician
    GET    /products            — qualquer autenticado
    GET    /products/{id}       — qualquer autenticado
    PATCH  /products/{id}       — admin | technician
    DELETE /products/{id}       — admin | technician (soft-delete: is_active=False)

  Equipments (sub-resource de produto):
    POST   /products/{id}/equipments        — admin | technician
    GET    /products/{id}/equipments        — staff vê tudo; cliente só os próprios
    GET    /equipments                      — admin | technician (todos os produtos)
    GET    /equipments/{id}                 — staff vê tudo; cliente só o próprio (404)
    PATCH  /equipments/{id}                 — admin | technician
    DELETE /equipments/{id}                 — admin | technician (soft-delete)

  Equipments do próprio cliente (self-service):
    POST   /equipment/my              — client
    GET    /equipment/my              — qualquer autenticado
    PATCH  /equipment/my/{id}         — client (e só o próprio)
    DELETE /equipment/my/{id}         — client (e só o próprio)

  O escopo por dono vale para o perfil cliente: equipamento de outro cliente —
  ou sem dono — é negado, porque o número de série é dado do cliente. A recusa
  sai como 404, indistinguível de um id inexistente.

  Os verbos que ESCREVEM em /equipment/my* exigem perfil client: com qualquer
  autenticado, staff criava equipamento pertencente a staff — o mesmo estado
  que o `_valida_dono` recusa com 400 nos endpoints acima, e que não aparece
  para cliente nenhum nem pode virar chamado. A LEITURA fica aberta de
  propósito: se alguém virou staff depois de ter sido cliente, o equipamento
  antigo continua existindo, e negar o GET esconderia dele o que já era seu.

  Quem atribui o dono é o staff, no POST e no PATCH acima (campo `owner_id`,
  opcional). É o que impede o equipamento cadastrado pela tela de Produtos de
  nascer órfão e ficar assim: sem dono ele não aparece para cliente nenhum, e
  recadastrar esbarra no número de série já usado. O campo NÃO existe nos
  corpos aceitos pelos /equipment/my*, senão o cliente escolheria o dono.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import authorize, get_current_user
from app.models.models import (
    AuditAction,
    AuditLog,
    Company,
    Equipment,
    Product,
    User,
    UserRole,
    equipment_users,
)
from app.schemas.product import (
    EquipmentCreate,
    EquipmentListResponse,
    EquipmentResponse,
    EquipmentStaffCreate,
    EquipmentStaffUpdate,
    EquipmentUpdate,
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
)
from app.utils.crud import get_or_404

router = APIRouter(tags=["Products & Equipments"])

# Uma constante só para os dois caminhos que devolvem 404 de equipamento: o id
# que não existe e o equipamento de outro cliente. Se os textos divergissem, a
# mensagem voltaria a denunciar qual dos dois casos é — o oráculo que o status
# igual acabou de fechar.
_EQUIPAMENTO_NAO_ENCONTRADO = "Equipment not found"


# ── Helpers ───────────────────────────────────────────────────


def _audit(
    db: AsyncSession,
    action: AuditAction,
    actor_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
) -> None:
    db.add(
        AuditLog(
            user_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    )


def _check_equipment_owner(equipment: Equipment, actor: User) -> None:
    """
    Recusa o equipamento que não pertence ao ator.

    Ponto único da recusa por dono, no espírito do `ensure_ticket_visible` de
    chamados e anexos: o mesmo "não é seu" chegava ao usuário com dois textos
    diferentes, porque a checagem estava copiada inline em três endpoints.

    A recusa sai como 404, idêntica à de um id que não existe. O 403 que havia
    antes confirmava que aquele equipamento existe — oráculo de existência
    justamente na mudança feita para fechar oráculos.

    Só chega aqui quem é cliente: os `/equipment/my*` que escrevem exigem o
    perfil, e o `GET /equipments/{id}` chama esta função apenas nesse caso.
    Existiu aqui um ramo devolvendo 403 para staff — virou código morto quando
    os verbos de escrita passaram a exigir perfil client, e ficar mantendo um
    ramo que nenhum teste consegue alcançar é pior do que não tê-lo.
    """
    if equipment.owner_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_EQUIPAMENTO_NAO_ENCONTRADO,
        )


async def _valida_dono(db: AsyncSession, owner_id: uuid.UUID) -> None:
    """
    Recusa dono que não existe ou que não é cliente.

    Equipamento é do cliente. Apontar o dono para um técnico ou admin faria o
    aparelho sumir do parque de todo mundo: a listagem filtra por dono quando
    quem olha é cliente, e staff nenhum abre a tela de "meus equipamentos".

    As duas recusas têm a mesma resposta porque, para quem preenche o
    formulário, o problema é o mesmo — o dono escolhido não serve.
    """
    result = await db.execute(select(User).where(User.id == owner_id))
    dono = result.scalar_one_or_none()
    if dono is None or dono.role != UserRole.client:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O dono informado precisa ser um cliente cadastrado.",
        )


_SERIE_DUPLICADA = "Este número de série já está cadastrado em outro equipamento."


async def _recusa_serie_do_produto(
    db: AsyncSession,
    product_id: uuid.UUID,
    serial: str | None,
    *,
    ignorando: uuid.UUID | None = None,
) -> None:
    """
    409 quando `(produto, série)` já existe.

    Substitui a `_recusa_serie_duplicada`, que escopava por dono. O dono deixou
    de fazer parte da chave em 26/08: a mesma série do mesmo produto é o MESMO
    aparelho, de quem quer que seja. Vale para a tela de staff, as edições e o
    `/equipment/my` — que não anexa mais o cliente ao aparelho existente.

    Só consulta o id: quem chama nunca recebe o aparelho que já existe, então
    nenhum dado dele tem como chegar à resposta.

    `ignorando` tira o próprio equipamento da busca ao editar: sem isso,
    salvar sem mexer no serial esbarraria nele mesmo.
    """
    if not serial:
        return
    consulta = select(Equipment.id).where(
        Equipment.product_id == product_id,
        Equipment.serial_number == serial,
    )
    if ignorando is not None:
        consulta = consulta.where(Equipment.id != ignorando)
    if (await db.execute(consulta)).scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_SERIE_DUPLICADA)


async def _enriquece(
    db: AsyncSession, equipamentos: Sequence[Equipment], *, para_equipe: bool
) -> list[EquipmentResponse]:
    """
    Junta a cada equipamento o responsável e, para a equipe, produto e empresa.

    Uma consulta por tabela (responsáveis, produtos, empresas), qualquer que
    seja o tamanho da página — e não uma por linha.

    Duas empresas, em campos separados, porque são coisas diferentes:

    - `company_name`/`company_cnpj`: o que o responsável DIGITOU no cadastro.
      Já saía assim antes e continua saindo para quem já recebia.
    - `linked_company_*`: o vínculo oficial (`users.company_id`), feito por um
      admin na tela de Grupos. Só para a equipe — o cliente não lê o próprio
      vínculo em lugar nenhum da API, e não é aqui que vai começar.

    `para_equipe=False` devolve exatamente o que a listagem por produto já
    devolvia ao cliente: responsável e empresa declarada, nada além.
    """
    ids_de_responsavel = {e.owner_id for e in equipamentos if e.owner_id}
    responsaveis: dict[uuid.UUID, User] = {}
    if ids_de_responsavel:
        linhas = await db.execute(select(User).where(User.id.in_(ids_de_responsavel)))
        responsaveis = {u.id: u for u in linhas.scalars().all()}

    produtos: dict[uuid.UUID, str] = {}
    empresas: dict[uuid.UUID, str] = {}
    if para_equipe:
        ids_de_produto = {e.product_id for e in equipamentos}
        if ids_de_produto:
            linhas_p = await db.execute(
                select(Product.id, Product.name).where(Product.id.in_(ids_de_produto))
            )
            produtos = {pid: nome for pid, nome in linhas_p.all()}
        ids_de_empresa = {u.company_id for u in responsaveis.values() if u.company_id}
        if ids_de_empresa:
            linhas_c = await db.execute(
                select(Company.id, Company.name).where(Company.id.in_(ids_de_empresa))
            )
            empresas = {cid: nome for cid, nome in linhas_c.all()}

    respostas = []
    for e in equipamentos:
        dado = EquipmentResponse.model_validate(e)
        responsavel = responsaveis.get(e.owner_id) if e.owner_id else None
        if responsavel:
            dado.owner_name = responsavel.name
            dado.owner_email = responsavel.email
            dado.company_name = responsavel.company_name
            dado.company_cnpj = responsavel.cnpj
        if para_equipe:
            dado.product_name = produtos.get(e.product_id)
            if responsavel and responsavel.company_id in empresas:
                dado.linked_company_id = responsavel.company_id
                dado.linked_company_name = empresas[responsavel.company_id]
        respostas.append(dado)
    return respostas


async def _anexa_usuario(db: AsyncSession, equipment_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """
    Liga a pessoa ao aparelho, sem estourar se ela já estiver ligada.

    `ON CONFLICT DO NOTHING` em vez de consultar antes: o par é a chave
    primária da tabela, então o banco já sabe responder isso, e a consulta
    extra só abriria uma janela entre o SELECT e o INSERT.
    """
    await db.execute(
        pg_insert(equipment_users)
        .values(equipment_id=equipment_id, user_id=user_id)
        .on_conflict_do_nothing()
    )


# ═══════════════════════════════════════════════════════════════
# PRODUCTS
# ═══════════════════════════════════════════════════════════════


@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    body: ProductCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> ProductResponse:
    result = await db.execute(select(Product).where(Product.name == body.name))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Já existe um produto com esse nome."
        )

    ts = datetime.now(UTC)
    product = Product(
        id=uuid.uuid4(),
        name=body.name,
        description=body.description,
        version=body.version,
        is_active=True,
        created_at=ts,
        updated_at=ts,
    )
    db.add(product)
    _audit(db, AuditAction.create, actor.id, "product", product.id)
    await db.commit()
    await db.refresh(product)
    return ProductResponse.model_validate(product)


@router.get("/products", response_model=ProductListResponse)
async def list_products(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(get_current_user)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
) -> ProductListResponse:
    base = select(Product)
    if is_active is not None:
        base = base.where(Product.is_active == is_active)
    if search:
        base = base.where(Product.name.ilike(f"%{search}%"))

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = await db.execute(base.order_by(Product.name).offset(offset).limit(limit))
    products = rows.scalars().all()

    return ProductListResponse(
        items=[ProductResponse.model_validate(p) for p in products],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> ProductResponse:
    return ProductResponse.model_validate(
        await get_or_404(db, Product, product_id, "Product not found")
    )


@router.patch("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: uuid.UUID,
    body: ProductUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> ProductResponse:
    product = await get_or_404(db, Product, product_id, "Product not found")

    if body.name and body.name != product.name:
        dup = await db.execute(select(Product).where(Product.name == body.name))
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Já existe um produto com esse nome."
            )

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(product, field, value)

    _audit(db, AuditAction.update, actor.id, "product", product.id)
    await db.commit()
    await db.refresh(product)
    return ProductResponse.model_validate(product)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> None:
    product = await get_or_404(db, Product, product_id, "Product not found")
    product.is_active = False
    _audit(db, AuditAction.delete, actor.id, "product", product.id)
    await db.commit()


# ═══════════════════════════════════════════════════════════════
# EQUIPMENTS
# ═══════════════════════════════════════════════════════════════


@router.post(
    "/products/{product_id}/equipments",
    response_model=EquipmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_equipment(
    product_id: uuid.UUID,
    body: EquipmentStaffCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> EquipmentResponse:
    await get_or_404(db, Product, product_id, "Product not found")

    if body.owner_id:
        await _valida_dono(db, body.owner_id)

    # Pela tela de Produtos quem cadastra é staff, que já enxerga o parque
    # inteiro: aqui o 409 não conta nada que a listagem não conte, e recusar é
    # melhor do que anexar em silêncio um aparelho ao dono errado. É o oposto
    # do /equipment/my — a mesma chave, tratada conforme quem está do outro
    # lado.
    await _recusa_serie_do_produto(db, product_id, body.serial_number)

    ts = datetime.now(UTC)
    equipment = Equipment(
        id=uuid.uuid4(),
        product_id=product_id,
        owner_id=body.owner_id,
        name=body.name,
        serial_number=body.serial_number,
        model=body.model,
        description=body.description,
        location=body.location,
        is_active=True,
        created_at=ts,
        updated_at=ts,
    )
    db.add(equipment)
    # Cadastro pela tela de Produtos: o dono, quando o staff informa um, entra
    # na associação junto. Aparelho órfão não gera vínculo nenhum — não há
    # usuário para vincular, e inventar um seria pior que o buraco.
    if body.owner_id is not None:
        await db.flush()
        await _anexa_usuario(db, equipment.id, body.owner_id)
    _audit(db, AuditAction.create, actor.id, "equipment", equipment.id)
    await db.commit()
    await db.refresh(equipment)
    return EquipmentResponse.model_validate(equipment)


@router.get("/products/{product_id}/equipments", response_model=EquipmentListResponse)
async def list_equipments(
    product_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    without_owner: bool = Query(default=False),
) -> EquipmentListResponse:
    await get_or_404(db, Product, product_id, "Product not found")
    para_equipe = actor.role != UserRole.client

    base = select(Equipment).where(Equipment.product_id == product_id)
    # Cliente só enxerga o próprio parque; staff precisa ver tudo para dar
    # suporte. Sem este filtro a listagem entregava o número de série do
    # equipamento de qualquer outro cliente.
    if actor.role == UserRole.client:
        base = base.where(Equipment.owner_id == actor.id)
    # Achar o equipamento órfão para atribuir dono. Precisa ser filtro de
    # servidor: a listagem é paginada, então filtrar no navegador só varreria a
    # página aberta e o órfão da página 7 nunca apareceria.
    #
    # Um `without_owner` booleano e não um filtro de dono genérico porque as
    # duas coisas são ortogonais, não alternativas: "sem dono" é a ausência de
    # owner_id e não caberia num `owner_id=<uuid>` sem inventar um valor
    # sentinela. Um filtro por dono específico, se um dia fizer falta, entra ao
    # lado deste sem conflito.
    #
    # Somado ao escopo do cliente acima, nunca no lugar dele: para o cliente a
    # combinação não casa com nada, que é o resultado certo.
    if without_owner:
        base = base.where(Equipment.owner_id.is_(None))
    if is_active is not None:
        base = base.where(Equipment.is_active == is_active)
    if search:
        base = base.where(Equipment.name.ilike(f"%{search}%"))

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = await db.execute(base.order_by(Equipment.name).offset(offset).limit(limit))
    equipments = rows.scalars().all()

    return EquipmentListResponse(
        items=await _enriquece(db, equipments, para_equipe=para_equipe),
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/equipments", response_model=EquipmentListResponse)
async def list_all_equipments(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=100),
    product_id: uuid.UUID | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    company_id: uuid.UUID | None = Query(default=None),
    without_owner: bool = Query(default=False),
) -> EquipmentListResponse:
    """
    O parque inteiro, de todos os produtos — só para a equipe.

    A listagem por produto obrigava a abrir produto por produto para achar um
    aparelho. Esta é a mesma consulta sem o produto fixo, para a tela de
    Equipamentos. O cliente é recusado pelo PAPEL (403), antes de qualquer
    consulta: o escopo dele continua sendo o `/equipment/my`.

    `company_id` casa só o vínculo oficial do responsável
    (`users.company_id`). O nome de empresa que o cliente digitou
    (`users.company_name`) não entra em filtro nem em busca: ele é
    autodeclarado e não decide de que empresa alguém é.
    """
    # Outer join: o equipamento sem responsável continua na lista; só os
    # filtros que dependem do responsável (busca por ele, empresa) o excluem.
    base = select(Equipment).outerjoin(User, User.id == Equipment.owner_id)
    if product_id is not None:
        base = base.where(Equipment.product_id == product_id)
    if is_active is not None:
        base = base.where(Equipment.is_active == is_active)
    if without_owner:
        base = base.where(Equipment.owner_id.is_(None))
    if company_id is not None:
        base = base.where(User.company_id == company_id)
    if search:
        termo = f"%{search}%"
        base = base.where(
            or_(
                Equipment.name.ilike(termo),
                Equipment.serial_number.ilike(termo),
                Equipment.model.ilike(termo),
                User.name.ilike(termo),
                User.email.ilike(termo),
            )
        )

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    # O id desempata nomes iguais: sem ele, dois "Titan" trocariam de página
    # entre uma requisição e outra.
    rows = await db.execute(base.order_by(Equipment.name, Equipment.id).offset(offset).limit(limit))

    return EquipmentListResponse(
        items=await _enriquece(db, rows.scalars().all(), para_equipe=True),
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/equipments/{equipment_id}", response_model=EquipmentResponse)
async def get_equipment(
    equipment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
) -> EquipmentResponse:
    equipment = await get_or_404(db, Equipment, equipment_id, _EQUIPAMENTO_NAO_ENCONTRADO)

    # Staff precisa ver o parque inteiro para dar suporte. Para o cliente vale a
    # regra de dono — e equipamento sem dono também é negado (fail closed), o
    # mesmo critério do /equipment/my, que devolve só o que é dele.
    if actor.role == UserRole.client:
        _check_equipment_owner(equipment, actor)
        # O cliente recebe o que sempre recebeu: o equipamento cru.
        return EquipmentResponse.model_validate(equipment)

    (resposta,) = await _enriquece(db, [equipment], para_equipe=True)
    return resposta


@router.patch("/equipments/{equipment_id}", response_model=EquipmentResponse)
async def update_equipment(
    equipment_id: uuid.UUID,
    body: EquipmentStaffUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> EquipmentResponse:
    equipment = await get_or_404(db, Equipment, equipment_id, _EQUIPAMENTO_NAO_ENCONTRADO)

    # É por aqui que se conserta o equipamento cadastrado sem dono. Enviar
    # `owner_id: null` desvincula de propósito.
    if body.owner_id:
        await _valida_dono(db, body.owner_id)

    # Com o dono fora da chave, trocar de dono nao mexe mais na unicidade:
    # o par a validar e (produto, serie), e o produto nao muda por aqui. Sobra
    # a serie -- e so quando ela realmente muda.
    enviados = body.model_fields_set
    serial_final = body.serial_number if "serial_number" in enviados else equipment.serial_number
    if serial_final != equipment.serial_number:
        await _recusa_serie_do_produto(
            db, equipment.product_id, serial_final, ignorando=equipment.id
        )

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(equipment, field, value)

    _audit(db, AuditAction.update, actor.id, "equipment", equipment.id)
    await db.commit()
    await db.refresh(equipment)
    return EquipmentResponse.model_validate(equipment)


# ── Client self-service equipment endpoints ───────────────────


@router.post(
    "/equipment/my",
    response_model=EquipmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_equipment(
    body: EquipmentCreate,
    product_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.client))],
) -> EquipmentResponse:
    await get_or_404(db, Product, product_id, "Product not found")

    # `(produto, série)` já cadastrado — dele, de outro cliente ou sem
    # responsável — é 409, com o mesmo texto nos três casos.
    #
    # Até 09/10 a série alheia ANEXAVA o cliente ao aparelho existente e
    # respondia 201 com esse aparelho: `owner_id` de outra empresa, nome,
    # modelo, descrição e localização. Acertar a série bastava para ler o
    # cadastro alheio. O 201 também não fechava o oráculo que prometia: o
    # aparelho "cadastrado" não aparecia no `GET /equipment/my`, que filtra por
    # `owner_id`, e o vínculo em `equipment_users` não era lido por consulta
    # nenhuma. A anexação saiu; se o aparelho compartilhado voltar, volta como
    # regra própria, decidindo antes quem pode se anexar.
    await _recusa_serie_do_produto(db, product_id, body.serial_number)

    ts = datetime.now(UTC)
    equipment = Equipment(
        id=uuid.uuid4(),
        product_id=product_id,
        owner_id=actor.id,
        name=body.name,
        serial_number=body.serial_number,
        model=body.model,
        description=body.description,
        location=body.location,
        is_active=True,
        created_at=ts,
        updated_at=ts,
    )
    db.add(equipment)
    # O cadastrante entra na tabela de usuários como qualquer outro: assim
    # nenhuma consulta de "quem usa este aparelho" precisa juntar `owner_id`
    # com a associação num OR e lembrar de tratar os dois casos.
    await db.flush()
    await _anexa_usuario(db, equipment.id, actor.id)
    _audit(db, AuditAction.create, actor.id, "equipment", equipment.id)
    await db.commit()
    await db.refresh(equipment)
    return EquipmentResponse.model_validate(equipment)


@router.get("/equipment/my", response_model=EquipmentListResponse)
async def list_my_equipment(
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    is_active: bool | None = Query(default=None),
) -> EquipmentListResponse:
    base = select(Equipment).where(Equipment.owner_id == actor.id)
    if is_active is not None:
        base = base.where(Equipment.is_active == is_active)  # noqa: E712
    rows = await db.execute(base.order_by(Equipment.name))
    equipments = rows.scalars().all()
    # Mesma escolha da lista de técnicos: são os equipamentos DO próprio
    # usuário, um conjunto pequeno e fechado que a tela mostra inteiro.
    return EquipmentListResponse(
        items=[EquipmentResponse.model_validate(e) for e in equipments],
        total=len(equipments),
        limit=len(equipments),
        offset=0,
    )


@router.patch(
    "/equipment/my/{equipment_id}",
    response_model=EquipmentResponse,
)
async def update_my_equipment(
    equipment_id: uuid.UUID,
    body: EquipmentUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.client))],
) -> EquipmentResponse:
    equipment = await get_or_404(db, Equipment, equipment_id, _EQUIPAMENTO_NAO_ENCONTRADO)
    _check_equipment_owner(equipment, actor)

    if body.serial_number and body.serial_number != equipment.serial_number:
        await _recusa_serie_do_produto(
            db, equipment.product_id, body.serial_number, ignorando=equipment.id
        )

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(equipment, field, value)

    _audit(db, AuditAction.update, actor.id, "equipment", equipment.id)
    await db.commit()
    await db.refresh(equipment)
    return EquipmentResponse.model_validate(equipment)


@router.delete("/equipment/my/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_equipment(
    equipment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.client))],
) -> None:
    equipment = await get_or_404(db, Equipment, equipment_id, _EQUIPAMENTO_NAO_ENCONTRADO)
    _check_equipment_owner(equipment, actor)
    equipment.is_active = False
    _audit(db, AuditAction.delete, actor.id, "equipment", equipment.id)
    await db.commit()


@router.delete("/equipments/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_equipment(
    equipment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> None:
    equipment = await get_or_404(db, Equipment, equipment_id, _EQUIPAMENTO_NAO_ENCONTRADO)
    equipment.is_active = False
    _audit(db, AuditAction.delete, actor.id, "equipment", equipment.id)
    await db.commit()
