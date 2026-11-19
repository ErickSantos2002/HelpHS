"""
Empresa do equipamento (ECE-01, Fase 1) — contra PostgreSQL real.

O que se prova aqui
-------------------
1. **A empresa é gravada no cadastro**, com a flag `equipamento_por_empresa`
   desligada: cliente vinculado cadastra e o aparelho nasce na empresa dele;
   a equipe informa a empresa ou herda a do responsável. O cliente não escolhe
   a empresa por nenhum corpo de requisição.
2. **O vínculo oficial propaga.** Vincular o cliente leva a empresa aos
   aparelhos dele que ainda não têm nenhuma — e só a esses. Desvincular não
   tira; trocar o responsável não muda.
3. **Empresa com equipamento não sai**: 409 pela contagem e, por baixo, a FK
   `RESTRICT`.
4. **Sem espera em círculo.** As rotas do cliente travam a própria conta ANTES
   do aparelho — a mesma ordem do vínculo (cliente → aparelhos).
5. **Nenhuma permissão nova.** O colega da mesma empresa continua sem ver,
   editar ou usar o aparelho: a leitura não mudou nesta fase.
6. **Os dois scripts**: o de preenchimento só grava o que não tem dúvida e
   mostra o resto; o de fusão leva os aparelhos junto.

Banco próprio e o mesmo jeito de forçar a corrida de
`test_vinculo_cliente_empresa_postgres.py`.
"""

import asyncio
import shutil
import tempfile
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app
from app.models.models import (
    AuditAction,
    AuditLog,
    Base,
    Company,
    Equipment,
    Group,
    Product,
    Ticket,
    TicketCategory,
    User,
    UserRole,
    UserStatus,
    equipment_users,
    ticket_equipments,
)
from app.schemas.groups import AssignClientRequest, CreateCompanyFromSuggestion
from app.schemas.product import (
    EquipmentCreate,
    EquipmentStaffCreate,
    EquipmentStaffUpdate,
    EquipmentUpdate,
)

_BANCO = "ece01_empresa_do_equipamento_testes"
_AGORA = datetime.now(UTC)


# ── Infraestrutura ────────────────────────────────────────────


def _url_do_servidor() -> tuple[str | None, object]:
    import os

    do_ambiente = os.environ.get("TEST_POSTGRES_URL")
    if do_ambiente:
        return do_ambiente.replace("postgresql://", "postgresql+asyncpg://"), None
    try:
        import pgserver
    except ImportError:
        return None, None
    pasta = tempfile.mkdtemp(prefix="helphs-testes-pg-")
    servidor = pgserver.get_server(pasta, cleanup_mode=None)
    url = servidor.get_uri(database="postgres")
    return url.replace("postgresql://", "postgresql+asyncpg://"), (servidor, pasta)


@pytest.fixture(scope="module")
def url_do_banco():
    servidor_url, recurso = _url_do_servidor()
    if servidor_url is None:
        pytest.skip("sem PostgreSQL à mão")

    url = servidor_url.rsplit("/", 1)[0] + f"/{_BANCO}"

    async def _monta() -> None:
        admin = create_async_engine(servidor_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{_BANCO}" WITH (FORCE)'))
            await conn.execute(text(f'CREATE DATABASE "{_BANCO}"'))
        await admin.dispose()
        motor = create_async_engine(url, poolclass=NullPool)
        async with motor.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        await motor.dispose()

    async def _desmonta() -> None:
        admin = create_async_engine(servidor_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{_BANCO}" WITH (FORCE)'))
        await admin.dispose()

    asyncio.run(_monta())
    yield url
    asyncio.run(_desmonta())

    if recurso is not None:
        servidor, pasta = recurso
        try:
            servidor.cleanup()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(pasta, ignore_errors=True)


@pytest_asyncio.fixture
async def fabrica(url_do_banco):
    motor = create_async_engine(url_do_banco, poolclass=NullPool)
    async with motor.begin() as conn:
        await conn.execute(
            text("TRUNCATE groups, companies, users, audit_logs, products, equipments CASCADE")
        )
    yield async_sessionmaker(motor, expire_on_commit=False)
    await motor.dispose()


async def _pessoa(
    fabrica, papel: UserRole = UserRole.client, *, company_id=None, situacao=UserStatus.active
) -> User:
    pessoa = User(
        id=uuid.uuid4(),
        name=f"Pessoa {papel.value} {uuid.uuid4().hex[:6]}",
        email=f"{uuid.uuid4().hex[:12]}@test.invalid",
        password="x",
        role=papel,
        status=situacao,
        phone="+5511999990000",
        company_id=company_id,
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
        created_at=_AGORA,
        updated_at=_AGORA,
    )
    async with fabrica() as s:
        s.add(pessoa)
        await s.commit()
    return pessoa


async def _grupo(fabrica, nome="Grupo Alfa") -> Group:
    g = Group(id=uuid.uuid4(), name=nome)
    async with fabrica() as s:
        s.add(g)
        await s.commit()
    return g


async def _empresa(fabrica, grupo: Group, nome="Acme Ltda", cnpj=None) -> Company:
    c = Company(id=uuid.uuid4(), group_id=grupo.id, name=nome, cnpj=cnpj)
    async with fabrica() as s:
        s.add(c)
        await s.commit()
    return c


async def _produto(fabrica, nome="Titan") -> Product:
    p = Product(id=uuid.uuid4(), name=nome, is_active=True)
    async with fabrica() as s:
        s.add(p)
        await s.commit()
    return p


async def _aparelho(
    fabrica, produto: Product, *, dono: User | None = None, company_id=None, serie=None, ativo=True
) -> Equipment:
    e = Equipment(
        id=uuid.uuid4(),
        product_id=produto.id,
        owner_id=dono.id if dono else None,
        company_id=company_id,
        name=f"Aparelho {uuid.uuid4().hex[:6]}",
        serial_number=serie or uuid.uuid4().hex[:10],
        is_active=ativo,
        created_at=_AGORA,
        updated_at=_AGORA,
    )
    async with fabrica() as s:
        s.add(e)
        await s.commit()
    return e


async def _empresa_do(fabrica, aparelho_id) -> uuid.UUID | None:
    async with fabrica() as s:
        return (
            await s.execute(select(Equipment.company_id).where(Equipment.id == aparelho_id))
        ).scalar_one()


async def _marca_do(fabrica, aparelho_id) -> bool:
    """`sem_empresa_por_decisao`: a equipe deixou o aparelho sem empresa de propósito."""
    async with fabrica() as s:
        return (
            await s.execute(
                select(Equipment.sem_empresa_por_decisao).where(Equipment.id == aparelho_id)
            )
        ).scalar_one()


async def _auditorias_de_aparelho(fabrica) -> list[AuditLog]:
    async with fabrica() as s:
        return list(
            (
                await s.execute(
                    select(AuditLog)
                    .where(AuditLog.entity_type == "equipment")
                    .order_by(AuditLog.created_at, AuditLog.id)
                )
            ).scalars()
        )


async def _conta(fabrica, modelo) -> int:
    async with fabrica() as s:
        return (await s.execute(select(func.count()).select_from(modelo))).scalar_one()


async def _corrida(fabrica, primeira, segunda):
    """Roda as duas em paralelo, segurando a primeira entre o flush e o commit.

    Devolve, para cada uma, "ok", o status HTTP da recusa, "IntegrityError" ou
    "deadlock". Qualquer outra exceção sobe.
    """
    a_segunda_chegou = asyncio.Event()

    async def roda(operacao, e_a_primeira: bool):
        async with fabrica() as s:
            commit_original = s.commit

            async def commit_vigiado():
                if e_a_primeira:
                    await s.flush()
                    try:
                        await asyncio.wait_for(a_segunda_chegou.wait(), timeout=1.0)
                    except TimeoutError:
                        pass  # a segunda está presa na trava
                else:
                    a_segunda_chegou.set()
                await commit_original()

            s.commit = commit_vigiado  # type: ignore[method-assign]
            try:
                await operacao(s)
                return "ok"
            except HTTPException as e:
                return e.status_code
            except IntegrityError:
                return "IntegrityError"
            except DBAPIError as e:
                if "deadlock" in str(e).lower():
                    return "deadlock"
                raise

    primeira_tarefa = asyncio.create_task(roda(primeira, True))
    await asyncio.sleep(0.3)
    segunda_tarefa = asyncio.create_task(roda(segunda, False))
    return await asyncio.gather(primeira_tarefa, segunda_tarefa)


# ── As operações, chamadas como o FastAPI as chama ────────────


def _vincula(ator, c, cliente):
    from app.routers.groups import assign_client

    return lambda s: assign_client(
        c.group_id, c.id, AssignClientRequest(user_id=cliente.id), s, ator
    )


def _desvincula(ator, c, cliente):
    from app.routers.groups import unassign_client

    return lambda s: unassign_client(c.group_id, c.id, cliente.id, s, ator)


def _pela_sugestao(ator, g, clientes, nome="Pela Sugestao", cnpj=None):
    from app.routers.groups import create_company_from_suggestion

    corpo = CreateCompanyFromSuggestion(name=nome, cnpj=cnpj, client_ids=[u.id for u in clientes])
    return lambda s: create_company_from_suggestion(g.id, corpo, s, ator)


def _exclui_empresa(admin, c):
    from app.routers.groups import delete_company

    return lambda s: delete_company(c.group_id, c.id, s, admin)


def _cliente_cadastra(cliente, produto, nome="Meu aparelho", serie=None):
    from app.routers.products import create_my_equipment

    corpo = EquipmentCreate(name=nome, serial_number=serie or uuid.uuid4().hex[:10])
    return lambda s: create_my_equipment(corpo, produto.id, s, cliente)


def _cliente_edita(cliente, aparelho, **campos):
    from app.routers.products import update_my_equipment

    return lambda s: update_my_equipment(aparelho.id, EquipmentUpdate(**campos), s, cliente)


def _cliente_inativa(cliente, aparelho):
    from app.routers.products import delete_my_equipment

    return lambda s: delete_my_equipment(aparelho.id, s, cliente)


def _equipe_cadastra(ator, produto, **campos):
    from app.routers.products import create_equipment

    campos.setdefault("name", "Da equipe")
    campos.setdefault("serial_number", uuid.uuid4().hex[:10])
    return lambda s: create_equipment(produto.id, EquipmentStaffCreate(**campos), s, ator)


def _equipe_edita(ator, aparelho, **campos):
    from app.routers.products import update_equipment

    return lambda s: update_equipment(aparelho.id, EquipmentStaffUpdate(**campos), s, ator)


async def _roda(fabrica, operacao):
    async with fabrica() as s:
        return await operacao(s)


# ══════════════════════════════════════════════════════════════
# 0. A flag
# ══════════════════════════════════════════════════════════════


def test_a_flag_nasce_desligada():
    assert get_settings().equipamento_por_empresa is False


# ══════════════════════════════════════════════════════════════
# 1. A empresa é gravada no cadastro (flag desligada)
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cliente_vinculado_cadastra_e_o_aparelho_nasce_na_empresa_dele(fabrica):
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica, company_id=c.id)
    produto = await _produto(fabrica)

    criado = await _roda(fabrica, _cliente_cadastra(cliente, produto))

    assert await _empresa_do(fabrica, criado.id) == c.id
    [auditoria] = await _auditorias_de_aparelho(fabrica)
    assert auditoria.action == AuditAction.create
    assert auditoria.new_data == {"company_id": str(c.id), "origem": "empresa_do_cadastrante"}


@pytest.mark.asyncio
async def test_cliente_sem_vinculo_cadastra_e_o_aparelho_fica_sem_empresa(fabrica):
    cliente = await _pessoa(fabrica)
    produto = await _produto(fabrica)

    criado = await _roda(fabrica, _cliente_cadastra(cliente, produto))

    assert await _empresa_do(fabrica, criado.id) is None
    [auditoria] = await _auditorias_de_aparelho(fabrica)
    assert auditoria.new_data is None


@pytest.mark.asyncio
async def test_a_empresa_vem_do_banco_e_nao_do_objeto_do_ator(fabrica):
    """O ator chega carregado antes da requisição; o vínculo pode ter mudado."""
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica)
    produto = await _produto(fabrica)
    admin = await _pessoa(fabrica, UserRole.admin)
    await _roda(fabrica, _vincula(admin, c, cliente))
    assert cliente.company_id is None, "o objeto em mãos ficou velho de propósito"

    criado = await _roda(fabrica, _cliente_cadastra(cliente, produto))

    assert await _empresa_do(fabrica, criado.id) == c.id


@pytest.mark.asyncio
async def test_equipe_cadastra_com_responsavel_e_herda_a_empresa_dele(fabrica):
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica, company_id=c.id)
    tecnico = await _pessoa(fabrica, UserRole.technician)
    produto = await _produto(fabrica)

    criado = await _roda(fabrica, _equipe_cadastra(tecnico, produto, owner_id=cliente.id))

    assert await _empresa_do(fabrica, criado.id) == c.id
    [auditoria] = await _auditorias_de_aparelho(fabrica)
    assert auditoria.new_data == {"company_id": str(c.id), "origem": "empresa_do_responsavel"}


@pytest.mark.asyncio
async def test_equipe_informa_a_empresa_e_ela_vence_a_do_responsavel(fabrica):
    g = await _grupo(fabrica)
    do_responsavel = await _empresa(fabrica, g, "Do responsavel")
    informada = await _empresa(fabrica, g, "Informada")
    cliente = await _pessoa(fabrica, company_id=do_responsavel.id)
    admin = await _pessoa(fabrica, UserRole.admin)
    produto = await _produto(fabrica)

    criado = await _roda(
        fabrica, _equipe_cadastra(admin, produto, owner_id=cliente.id, company_id=informada.id)
    )

    assert await _empresa_do(fabrica, criado.id) == informada.id
    [auditoria] = await _auditorias_de_aparelho(fabrica)
    assert auditoria.new_data == {"company_id": str(informada.id), "origem": "equipe"}


@pytest.mark.asyncio
async def test_equipe_manda_empresa_nula_e_o_aparelho_nasce_sem_empresa(fabrica):
    """Nulo explícito é decisão da equipe; omitir é que herda."""
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica, company_id=c.id)
    admin = await _pessoa(fabrica, UserRole.admin)
    produto = await _produto(fabrica)

    criado = await _roda(
        fabrica, _equipe_cadastra(admin, produto, owner_id=cliente.id, company_id=None)
    )

    assert await _empresa_do(fabrica, criado.id) is None
    assert await _marca_do(fabrica, criado.id) is True
    [auditoria] = await _auditorias_de_aparelho(fabrica)
    assert auditoria.new_data == {
        "company_id": None,
        "sem_empresa_por_decisao": True,
        "origem": "equipe",
    }


@pytest.mark.asyncio
async def test_equipe_cadastra_sem_responsavel_e_sem_empresa(fabrica):
    admin = await _pessoa(fabrica, UserRole.admin)
    produto = await _produto(fabrica)

    criado = await _roda(fabrica, _equipe_cadastra(admin, produto))

    assert await _empresa_do(fabrica, criado.id) is None


@pytest.mark.asyncio
async def test_equipe_informa_empresa_que_nao_existe_e_nada_e_gravado(fabrica):
    admin = await _pessoa(fabrica, UserRole.admin)
    produto = await _produto(fabrica)

    with pytest.raises(HTTPException) as recusa:
        await _roda(fabrica, _equipe_cadastra(admin, produto, company_id=uuid.uuid4()))

    assert recusa.value.status_code == 400
    assert await _conta(fabrica, Equipment) == 0


@pytest.mark.asyncio
async def test_o_cadastro_continua_gravando_equipment_users(fabrica):
    """Regra 14: a tabela segue sendo gravada até a auditoria complementar."""
    cliente = await _pessoa(fabrica)
    produto = await _produto(fabrica)

    criado = await _roda(fabrica, _cliente_cadastra(cliente, produto))

    async with fabrica() as s:
        vinculos = (await s.execute(select(equipment_users))).all()
    assert [(v.equipment_id, v.user_id) for v in vinculos] == [(criado.id, cliente.id)]


# ── A equipe controla a empresa ───────────────────────────────


@pytest.mark.asyncio
async def test_equipe_troca_a_empresa_do_aparelho_e_fica_auditado(fabrica):
    g = await _grupo(fabrica)
    antiga = await _empresa(fabrica, g, "Antiga")
    nova = await _empresa(fabrica, g, "Nova")
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, company_id=antiga.id)
    admin = await _pessoa(fabrica, UserRole.admin)

    await _roda(fabrica, _equipe_edita(admin, aparelho, company_id=nova.id))

    assert await _empresa_do(fabrica, aparelho.id) == nova.id
    [auditoria] = await _auditorias_de_aparelho(fabrica)
    assert auditoria.action == AuditAction.update
    assert auditoria.user_id == admin.id
    assert auditoria.old_data == {"company_id": str(antiga.id)}
    assert auditoria.new_data == {"company_id": str(nova.id), "origem": "equipe"}


@pytest.mark.asyncio
async def test_equipe_tira_a_empresa_do_aparelho_e_fica_auditado(fabrica):
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, company_id=c.id)
    tecnico = await _pessoa(fabrica, UserRole.technician)

    await _roda(fabrica, _equipe_edita(tecnico, aparelho, company_id=None))

    assert await _empresa_do(fabrica, aparelho.id) is None
    [auditoria] = await _auditorias_de_aparelho(fabrica)
    assert auditoria.old_data == {"company_id": str(c.id)}
    assert auditoria.new_data == {
        "company_id": None,
        "sem_empresa_por_decisao": True,
        "origem": "equipe",
    }
    assert await _marca_do(fabrica, aparelho.id) is True


@pytest.mark.asyncio
async def test_equipe_edita_outro_campo_e_a_empresa_nao_muda_nem_entra_na_auditoria(fabrica):
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, company_id=c.id)
    admin = await _pessoa(fabrica, UserRole.admin)

    await _roda(fabrica, _equipe_edita(admin, aparelho, location="Sala 2"))

    assert await _empresa_do(fabrica, aparelho.id) == c.id
    [auditoria] = await _auditorias_de_aparelho(fabrica)
    assert auditoria.old_data is None and auditoria.new_data is None


@pytest.mark.asyncio
async def test_reenviar_a_mesma_empresa_nao_audita_troca(fabrica):
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, company_id=c.id)
    admin = await _pessoa(fabrica, UserRole.admin)

    await _roda(fabrica, _equipe_edita(admin, aparelho, company_id=c.id))

    [auditoria] = await _auditorias_de_aparelho(fabrica)
    assert auditoria.old_data is None and auditoria.new_data is None


@pytest.mark.asyncio
async def test_equipe_troca_para_empresa_que_nao_existe_e_nada_muda(fabrica):
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, company_id=c.id)
    admin = await _pessoa(fabrica, UserRole.admin)

    with pytest.raises(HTTPException) as recusa:
        await _roda(fabrica, _equipe_edita(admin, aparelho, company_id=uuid.uuid4()))

    assert recusa.value.status_code == 400
    assert await _empresa_do(fabrica, aparelho.id) == c.id
    assert await _auditorias_de_aparelho(fabrica) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("novo_responsavel", ["de_outra_empresa", "sem_empresa", "nenhum"])
async def test_trocar_o_responsavel_nao_muda_a_empresa(fabrica, novo_responsavel):
    """Regra 8."""
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g, "Do aparelho")
    outra = await _empresa(fabrica, g, "Outra")
    antigo = await _pessoa(fabrica, company_id=c.id)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, dono=antigo, company_id=c.id)
    admin = await _pessoa(fabrica, UserRole.admin)
    if novo_responsavel == "de_outra_empresa":
        novo = (await _pessoa(fabrica, company_id=outra.id)).id
    elif novo_responsavel == "sem_empresa":
        novo = (await _pessoa(fabrica)).id
    else:
        novo = None

    await _roda(fabrica, _equipe_edita(admin, aparelho, owner_id=novo))

    assert await _empresa_do(fabrica, aparelho.id) == c.id
    async with fabrica() as s:
        dono = (
            await s.execute(select(Equipment.owner_id).where(Equipment.id == aparelho.id))
        ).scalar_one()
    assert dono == novo


# ── O cliente não escolhe a empresa ───────────────────────────


@pytest_asyncio.fixture
async def http(fabrica):
    async def _get_db():
        async with fabrica() as s:
            yield s

    estado: dict = {}

    async def _get_current_user():
        return estado["ator"]

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_current_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.estado = estado  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("vinculado", [False, True])
async def test_cliente_nao_escolhe_a_empresa_no_cadastro(fabrica, http, vinculado):
    g = await _grupo(fabrica)
    propria = await _empresa(fabrica, g, "Propria")
    alheia = await _empresa(fabrica, g, "Alheia")
    cliente = await _pessoa(fabrica, company_id=propria.id if vinculado else None)
    produto = await _produto(fabrica)
    http.estado["ator"] = cliente

    resp = await http.post(
        f"/api/v1/equipment/my?product_id={produto.id}",
        json={"name": "Meu", "serial_number": "SN-1", "company_id": str(alheia.id)},
    )

    assert resp.status_code == 201, resp.text
    assert "company_id" not in resp.json(), "o cliente não lê o próprio vínculo pela API"
    esperada = propria.id if vinculado else None
    assert await _empresa_do(fabrica, uuid.UUID(resp.json()["id"])) == esperada


@pytest.mark.asyncio
async def test_cliente_nao_troca_a_empresa_pela_edicao(fabrica, http):
    g = await _grupo(fabrica)
    propria = await _empresa(fabrica, g, "Propria")
    alheia = await _empresa(fabrica, g, "Alheia")
    cliente = await _pessoa(fabrica, company_id=propria.id)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, dono=cliente, company_id=propria.id)
    http.estado["ator"] = cliente

    resp = await http.patch(
        f"/api/v1/equipment/my/{aparelho.id}",
        json={"name": "Renomeado", "company_id": str(alheia.id)},
    )

    assert resp.status_code == 200, resp.text
    assert await _empresa_do(fabrica, aparelho.id) == propria.id


# ══════════════════════════════════════════════════════════════
# 2. O vínculo oficial propaga
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_vincular_o_cliente_leva_a_empresa_aos_aparelhos_dele_sem_empresa(fabrica):
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    outra = await _empresa(fabrica, g, "Outra")
    cliente = await _pessoa(fabrica)
    vizinho = await _pessoa(fabrica)
    produto = await _produto(fabrica)
    um = await _aparelho(fabrica, produto, dono=cliente)
    inativo = await _aparelho(fabrica, produto, dono=cliente, ativo=False)
    ja_tem = await _aparelho(fabrica, produto, dono=cliente, company_id=outra.id)
    do_vizinho = await _aparelho(fabrica, produto, dono=vizinho)
    sem_dono = await _aparelho(fabrica, produto)
    admin = await _pessoa(fabrica, UserRole.admin)

    await _roda(fabrica, _vincula(admin, c, cliente))

    assert await _empresa_do(fabrica, um.id) == c.id
    assert await _empresa_do(fabrica, inativo.id) == c.id
    assert await _empresa_do(fabrica, ja_tem.id) == outra.id, "empresa já gravada não é trocada"
    assert await _empresa_do(fabrica, do_vizinho.id) is None
    assert await _empresa_do(fabrica, sem_dono.id) is None
    auditorias = await _auditorias_de_aparelho(fabrica)
    assert {a.entity_id for a in auditorias} == {um.id, inativo.id}
    for a in auditorias:
        assert a.action == AuditAction.update
        assert a.user_id == admin.id
        assert a.old_data == {"company_id": None}
        assert a.new_data == {"company_id": str(c.id), "origem": "vinculo_do_responsavel"}


@pytest.mark.asyncio
async def test_vinculo_repetido_na_mesma_empresa_nao_propaga_nem_audita(fabrica):
    """O 200 idempotente da F2-A1 continua sem escrever nada."""
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica, company_id=c.id)
    produto = await _produto(fabrica)
    antigo = await _aparelho(fabrica, produto, dono=cliente)
    admin = await _pessoa(fabrica, UserRole.admin)

    await _roda(fabrica, _vincula(admin, c, cliente))

    assert await _empresa_do(fabrica, antigo.id) is None
    assert await _conta(fabrica, AuditLog) == 0


@pytest.mark.asyncio
async def test_a_sugestao_propaga_para_os_aparelhos_de_cada_cliente(fabrica):
    g = await _grupo(fabrica)
    um = await _pessoa(fabrica)
    dois = await _pessoa(fabrica)
    produto = await _produto(fabrica)
    do_um = await _aparelho(fabrica, produto, dono=um)
    do_dois = await _aparelho(fabrica, produto, dono=dois)
    admin = await _pessoa(fabrica, UserRole.admin)

    resposta = await _roda(fabrica, _pela_sugestao(admin, g, [um, dois]))

    criada = resposta.company.id
    assert await _empresa_do(fabrica, do_um.id) == criada
    assert await _empresa_do(fabrica, do_dois.id) == criada
    assert len(await _auditorias_de_aparelho(fabrica)) == 2


@pytest.mark.asyncio
async def test_desvincular_o_cliente_nao_tira_a_empresa_do_aparelho(fabrica):
    """Regra 7."""
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica, company_id=c.id)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, dono=cliente, company_id=c.id)
    admin = await _pessoa(fabrica, UserRole.admin)

    await _roda(fabrica, _desvincula(admin, c, cliente))

    assert await _empresa_do(fabrica, aparelho.id) == c.id
    assert await _auditorias_de_aparelho(fabrica) == []


@pytest.mark.asyncio
async def test_vinculo_recusado_nao_propaga(fabrica):
    g = await _grupo(fabrica)
    atual = await _empresa(fabrica, g, "Atual")
    pedida = await _empresa(fabrica, g, "Pedida")
    cliente = await _pessoa(fabrica, company_id=atual.id)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, dono=cliente)
    admin = await _pessoa(fabrica, UserRole.admin)

    with pytest.raises(HTTPException) as recusa:
        await _roda(fabrica, _vincula(admin, pedida, cliente))

    assert recusa.value.status_code == 409
    assert await _empresa_do(fabrica, aparelho.id) is None


# ══════════════════════════════════════════════════════════════
# 3. Empresa com equipamento não sai
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_empresa_com_equipamento_nao_e_excluida(fabrica):
    """Regra 9."""
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, company_id=c.id)
    admin = await _pessoa(fabrica, UserRole.admin)

    with pytest.raises(HTTPException) as recusa:
        await _roda(fabrica, _exclui_empresa(admin, c))

    assert recusa.value.status_code == 409
    assert "1 equipamento(s)" in recusa.value.detail
    assert await _conta(fabrica, Company) == 1
    assert await _empresa_do(fabrica, aparelho.id) == c.id


@pytest.mark.asyncio
async def test_a_chave_estrangeira_recusa_apagar_empresa_com_equipamento(fabrica):
    """A rede por baixo da contagem: nenhum caminho solta o aparelho em silêncio."""
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    produto = await _produto(fabrica)
    await _aparelho(fabrica, produto, company_id=c.id)

    async with fabrica() as s:
        with pytest.raises(IntegrityError):
            await s.execute(text("DELETE FROM companies WHERE id = :id"), {"id": c.id})

    assert await _conta(fabrica, Company) == 1


@pytest.mark.asyncio
async def test_cadastro_em_curso_faz_a_exclusao_da_empresa_recusar(fabrica):
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    admin = await _pessoa(fabrica, UserRole.admin)
    tecnico = await _pessoa(fabrica, UserRole.technician)
    produto = await _produto(fabrica)

    resultado = await _corrida(
        fabrica,
        _equipe_cadastra(tecnico, produto, company_id=c.id),
        _exclui_empresa(admin, c),
    )

    assert resultado == ["ok", 409]
    assert await _conta(fabrica, Company) == 1
    assert await _conta(fabrica, Equipment) == 1


@pytest.mark.asyncio
async def test_exclusao_em_curso_faz_o_cadastro_recusar_sem_erro_de_chave(fabrica):
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    admin = await _pessoa(fabrica, UserRole.admin)
    tecnico = await _pessoa(fabrica, UserRole.technician)
    produto = await _produto(fabrica)

    resultado = await _corrida(
        fabrica,
        _exclui_empresa(admin, c),
        _equipe_cadastra(tecnico, produto, company_id=c.id),
    )

    assert resultado == ["ok", 400]
    assert await _conta(fabrica, Company) == 0
    assert await _conta(fabrica, Equipment) == 0


@pytest.mark.asyncio
async def test_troca_de_empresa_em_curso_faz_a_exclusao_recusar(fabrica):
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto)
    admin = await _pessoa(fabrica, UserRole.admin)
    tecnico = await _pessoa(fabrica, UserRole.technician)

    resultado = await _corrida(
        fabrica,
        _equipe_edita(tecnico, aparelho, company_id=c.id),
        _exclui_empresa(admin, c),
    )

    assert resultado == ["ok", 409]
    assert await _empresa_do(fabrica, aparelho.id) == c.id


# ══════════════════════════════════════════════════════════════
# 4. Concorrência: vínculo × cadastro e edição pelo cliente
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_vinculo_em_curso_e_cadastro_do_cliente_terminam_com_a_empresa(fabrica):
    """O cadastro espera o vínculo e lê a empresa já comitada."""
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica)
    admin = await _pessoa(fabrica, UserRole.admin)
    produto = await _produto(fabrica)

    resultado = await _corrida(
        fabrica, _vincula(admin, c, cliente), _cliente_cadastra(cliente, produto)
    )

    assert resultado == ["ok", "ok"]
    async with fabrica() as s:
        empresas = list((await s.execute(select(Equipment.company_id))).scalars())
    assert empresas == [c.id]


@pytest.mark.asyncio
async def test_cadastro_em_curso_e_vinculo_terminam_com_a_empresa(fabrica):
    """O vínculo espera o cadastro e a propagação já enxerga o aparelho novo."""
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica)
    admin = await _pessoa(fabrica, UserRole.admin)
    produto = await _produto(fabrica)

    resultado = await _corrida(
        fabrica, _cliente_cadastra(cliente, produto), _vincula(admin, c, cliente)
    )

    assert resultado == ["ok", "ok"]
    async with fabrica() as s:
        empresas = list((await s.execute(select(Equipment.company_id))).scalars())
    assert empresas == [c.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("ordem", ["vinculo_primeiro", "cliente_primeiro"])
@pytest.mark.parametrize("operacao", ["edita", "inativa"])
async def test_vinculo_e_escrita_do_cliente_no_aparelho_nao_travam_em_circulo(
    fabrica, ordem, operacao
):
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica)
    admin = await _pessoa(fabrica, UserRole.admin)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, dono=cliente)
    do_cliente = (
        _cliente_edita(cliente, aparelho, location="Sala 9")
        if operacao == "edita"
        else _cliente_inativa(cliente, aparelho)
    )
    vinculo = _vincula(admin, c, cliente)
    par = (vinculo, do_cliente) if ordem == "vinculo_primeiro" else (do_cliente, vinculo)

    resultado = await _corrida(fabrica, *par)

    assert resultado == ["ok", "ok"]
    assert await _empresa_do(fabrica, aparelho.id) == c.id


@pytest.mark.asyncio
@pytest.mark.parametrize("operacao", ["cadastra", "edita", "inativa"])
async def test_o_cliente_trava_a_propria_conta_antes_de_tocar_no_aparelho(fabrica, operacao):
    """A ordem, lida nas instruções que chegam ao banco.

    O vínculo trava o cliente (`FOR UPDATE`) e depois escreve nos aparelhos
    dele. Se a rota do cliente escrevesse no aparelho antes de pegar a própria
    linha — o INSERT em `audit_logs` checa a FK `user_id` com `FOR KEY SHARE`
    —, "eu tenho o aparelho e espero a conta; o vínculo tem a conta e espera o
    aparelho" é espera em círculo.
    """
    cliente = await _pessoa(fabrica)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, dono=cliente)
    op = {
        "cadastra": _cliente_cadastra(cliente, produto),
        "edita": _cliente_edita(cliente, aparelho, location="Sala 9"),
        "inativa": _cliente_inativa(cliente, aparelho),
    }[operacao]

    instrucoes: list[str] = []

    def _anota(_conn, _cursor, sql, *_args):
        instrucoes.append(" ".join(sql.split()))

    async with fabrica() as s:
        motor = s.bind.sync_engine
        event.listen(motor, "before_cursor_execute", _anota)
        try:
            await op(s)
        finally:
            event.remove(motor, "before_cursor_execute", _anota)

    trava = next(
        i for i, q in enumerate(instrucoes) if "FROM users" in q and q.endswith("FOR KEY SHARE")
    )
    escritas = [
        i
        for i, q in enumerate(instrucoes)
        if q.startswith(("INSERT INTO equipments", "UPDATE equipments"))
    ]
    assert escritas, instrucoes
    assert trava < min(escritas), instrucoes


@pytest.mark.asyncio
async def test_com_o_cliente_travado_a_edicao_espera_sem_segurar_o_aparelho(fabrica):
    """O mesmo, com as travas de pé.

    T2 faz o que o vínculo faz — `FOR UPDATE` no cliente — e, com a edição do
    cliente já em andamento, consegue travar o aparelho. Se a edição tivesse
    pegado o aparelho primeiro, o `NOWAIT` recusaria.
    """
    cliente = await _pessoa(fabrica)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, dono=cliente)

    async with fabrica() as t2:
        await t2.execute(text("SELECT id FROM users WHERE id = :id FOR UPDATE"), {"id": cliente.id})
        edicao = asyncio.create_task(
            _roda(fabrica, _cliente_edita(cliente, aparelho, location="Sala 9"))
        )
        await asyncio.sleep(0.5)
        assert not edicao.done(), "a edição tinha de estar esperando a conta"
        await t2.execute(
            text("SELECT id FROM equipments WHERE id = :id FOR UPDATE NOWAIT"),
            {"id": aparelho.id},
        )
        await t2.commit()

    await asyncio.wait_for(edicao, timeout=5)
    async with fabrica() as s:
        local = (
            await s.execute(select(Equipment.location).where(Equipment.id == aparelho.id))
        ).scalar_one()
    assert local == "Sala 9"


@pytest.mark.asyncio
async def test_o_vinculo_escreve_nos_aparelhos_depois_de_travar_os_clientes(fabrica):
    """A ordem da F2-A1 fica como está; os aparelhos entram no fim."""
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica)
    admin = await _pessoa(fabrica, UserRole.admin)
    produto = await _produto(fabrica)
    await _aparelho(fabrica, produto, dono=cliente)

    instrucoes: list[str] = []

    def _anota(_conn, _cursor, sql, *_args):
        instrucoes.append(" ".join(sql.split()))

    async with fabrica() as s:
        motor = s.bind.sync_engine
        event.listen(motor, "before_cursor_execute", _anota)
        try:
            await _vincula(admin, c, cliente)(s)
        finally:
            event.remove(motor, "before_cursor_execute", _anota)

    travas = [q for q in instrucoes if " FOR " in q]
    assert len(travas) == 3, travas
    assert travas[0].endswith("FOR KEY SHARE") and "FROM users" in travas[0]
    assert travas[1].endswith("FOR KEY SHARE") and "FROM companies" in travas[1]
    assert travas[2].endswith("FOR UPDATE") and "FROM users" in travas[2]
    dos_aparelhos = next(i for i, q in enumerate(instrucoes) if q.startswith("UPDATE equipments"))
    assert dos_aparelhos > instrucoes.index(travas[2])


# ══════════════════════════════════════════════════════════════
# 5. Nenhuma permissão nova para o cliente
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", [False])
async def test_colega_da_mesma_empresa_continua_sem_acesso_ao_aparelho(fabrica, monkeypatch, flag):
    """As leituras são as de antes, com a empresa gravada e tudo.

    Só com a flag DESLIGADA. Na Fase 1 o caso `True` também passava aqui,
    porque ninguém consultava a flag; a Fase 2 trocou a função de escopo, e o
    que vale com ela ligada está em `test_equipamento_compartilhado_postgres.py`.
    """
    from app.routers.products import (
        delete_my_equipment,
        get_equipment,
        list_equipments,
        list_my_equipment,
        update_my_equipment,
    )
    from app.routers.tickets import _set_ticket_equipments

    monkeypatch.setattr(get_settings(), "equipamento_por_empresa", flag)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    dono = await _pessoa(fabrica, company_id=c.id)
    colega = await _pessoa(fabrica, company_id=c.id)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, dono=dono, company_id=c.id)

    async with fabrica() as s:
        meus = await list_my_equipment(s, colega, None)
        do_produto = await list_equipments(produto.id, s, colega, 0, 20, None, None, False)
        assert meus.items == [] and do_produto.items == []

        for recusada in (
            lambda: get_equipment(aparelho.id, s, colega),
            lambda: update_my_equipment(aparelho.id, EquipmentUpdate(name="Tomado"), s, colega),
            lambda: delete_my_equipment(aparelho.id, s, colega),
        ):
            with pytest.raises(HTTPException) as recusa:
                await recusada()
            assert recusa.value.status_code == 404
            await s.rollback()

        with pytest.raises(HTTPException) as recusa:
            await _set_ticket_equipments(s, Ticket(), [aparelho.id], colega)
        assert recusa.value.status_code == 403

    async with fabrica() as s:
        intacto = (
            await s.execute(select(Equipment).where(Equipment.id == aparelho.id))
        ).scalar_one()
    assert (intacto.name, intacto.is_active) == (aparelho.name, True)

    async with fabrica() as s:
        do_dono = await list_my_equipment(s, dono, None)
    assert [e.id for e in do_dono.items] == [aparelho.id]


# ══════════════════════════════════════════════════════════════
# 6. Os scripts
# ══════════════════════════════════════════════════════════════


async def _conexao(fabrica):
    async with fabrica() as s:
        return s.bind


@pytest.mark.asyncio
async def test_o_preenchimento_grava_so_o_que_nao_tem_duvida(fabrica):
    from scripts.preenche_empresa_do_equipamento import aplica, levanta, planeja

    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    outra = await _empresa(fabrica, g, "Outra")
    vinculado = await _pessoa(fabrica, company_id=c.id)
    solto = await _pessoa(fabrica)
    inativo = await _pessoa(fabrica, company_id=c.id, situacao=UserStatus.inactive)
    de_fora = await _pessoa(fabrica, company_id=outra.id)
    produto = await _produto(fabrica)
    limpo = await _aparelho(fabrica, produto, dono=vinculado)
    sem_dono = await _aparelho(fabrica, produto)
    de_solto = await _aparelho(fabrica, produto, dono=solto)
    de_inativo = await _aparelho(fabrica, produto, dono=inativo)
    compartilhado = await _aparelho(fabrica, produto, dono=vinculado)
    ja_tem = await _aparelho(fabrica, produto, dono=vinculado, company_id=outra.id)
    async with fabrica() as s:
        # Alguém de OUTRA empresa consta como usuário do aparelho: resto da
        # anexação por série que existiu de 26/08 a 09/10.
        await s.execute(
            equipment_users.insert().values(equipment_id=compartilhado.id, user_id=de_fora.id)
        )
        await s.commit()

    motor = await _conexao(fabrica)
    async with motor.connect() as conn:
        plano = planeja(await levanta(conn))

    assert [i.id for i in plano["preenchivel"]] == [limpo.id]
    assert [i.id for i in plano["sem_responsavel"]] == [sem_dono.id]
    assert [i.id for i in plano["responsavel_sem_vinculo"]] == [de_solto.id]
    assert [i.id for i in plano["responsavel_inapto"]] == [de_inativo.id]
    assert [i.id for i in plano["ambiguo"]] == [compartilhado.id]
    assert [i.id for i in plano["divergente"]] == [ja_tem.id]

    # Só levantar não grava.
    for aparelho in (limpo, sem_dono, de_solto, de_inativo, compartilhado):
        assert await _empresa_do(fabrica, aparelho.id) is None

    async with motor.connect() as conn:
        gravados, pulados = await aplica(conn, plano["preenchivel"])

    assert (gravados, pulados) == ([limpo.id], [])
    assert await _empresa_do(fabrica, limpo.id) == c.id
    for aparelho in (sem_dono, de_solto, de_inativo, compartilhado):
        assert await _empresa_do(fabrica, aparelho.id) is None
    assert await _empresa_do(fabrica, ja_tem.id) == outra.id
    [auditoria] = await _auditorias_de_aparelho(fabrica)
    assert auditoria.entity_id == limpo.id
    assert auditoria.action == AuditAction.update
    assert auditoria.user_id is None
    assert auditoria.old_data == {"company_id": None}
    assert auditoria.new_data == {
        "company_id": str(c.id),
        "origem": "script_preenche_empresa_do_equipamento",
    }

    # Rodar de novo não acha mais nada.
    async with motor.connect() as conn:
        de_novo = planeja(await levanta(conn))
    assert de_novo["preenchivel"] == []


@pytest.mark.asyncio
async def test_chamado_aberto_por_gente_de_outra_empresa_torna_o_aparelho_ambiguo(fabrica):
    from scripts.preenche_empresa_do_equipamento import levanta, planeja

    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    outra = await _empresa(fabrica, g, "Outra")
    dono = await _pessoa(fabrica, company_id=c.id)
    de_fora = await _pessoa(fabrica, company_id=outra.id)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, dono=dono)
    async with fabrica() as s:
        chamado = Ticket(
            id=uuid.uuid4(),
            protocol="HS-T-1",
            title="Chamado de fora",
            description="Aberto por gente de outra empresa",
            category=next(iter(TicketCategory)),
            creator_id=de_fora.id,
        )
        s.add(chamado)
        await s.flush()
        await s.execute(
            ticket_equipments.insert().values(ticket_id=chamado.id, equipment_id=aparelho.id)
        )
        await s.commit()

    motor = await _conexao(fabrica)
    async with motor.connect() as conn:
        plano = planeja(await levanta(conn))

    assert plano["preenchivel"] == []
    [item] = plano["ambiguo"]
    assert item.id == aparelho.id
    assert "chamado" in item.motivo


@pytest.mark.asyncio
async def test_o_preenchimento_pula_o_que_mudou_depois_do_levantamento(fabrica):
    from scripts.preenche_empresa_do_equipamento import aplica, levanta, planeja

    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    outra = await _empresa(fabrica, g, "Outra")
    dono = await _pessoa(fabrica, company_id=c.id)
    produto = await _produto(fabrica)
    preenchido_no_meio = await _aparelho(fabrica, produto, dono=dono)
    dono_desvinculado = await _pessoa(fabrica, company_id=c.id)
    do_desvinculado = await _aparelho(fabrica, produto, dono=dono_desvinculado)
    motor = await _conexao(fabrica)
    async with motor.connect() as conn:
        plano = planeja(await levanta(conn))
    assert len(plano["preenchivel"]) == 2

    async with fabrica() as s:
        await s.execute(
            text("UPDATE equipments SET company_id = :c WHERE id = :id"),
            {"c": outra.id, "id": preenchido_no_meio.id},
        )
        await s.execute(
            text("UPDATE users SET company_id = NULL WHERE id = :id"), {"id": dono_desvinculado.id}
        )
        await s.commit()

    async with motor.connect() as conn:
        gravados, pulados = await aplica(conn, plano["preenchivel"])

    assert gravados == []
    assert set(pulados) == {preenchido_no_meio.id, do_desvinculado.id}
    assert await _empresa_do(fabrica, preenchido_no_meio.id) == outra.id
    assert await _empresa_do(fabrica, do_desvinculado.id) is None
    assert await _auditorias_de_aparelho(fabrica) == []


@pytest.mark.asyncio
async def test_a_fusao_de_empresas_leva_os_aparelhos_para_a_sobrevivente(fabrica):
    from scripts.funde_empresas_duplicadas import Empresa, _aplica, planeja_fusao

    g = await _grupo(fabrica)
    fica = await _empresa(fabrica, g, "Fica", cnpj="11222333000181")
    sai = await _empresa(fabrica, g, "Sai", cnpj="11.222.333/0001-81")
    await _pessoa(fabrica, company_id=fica.id)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, company_id=sai.id)
    fusoes, recusadas = planeja_fusao(
        [
            Empresa(fica.id, "11222333000181", "Fica", g.id, _AGORA, 1, 0, 0),
            Empresa(sai.id, "11222333000181", "Sai", g.id, _AGORA, 0, 0, 1),
        ]
    )
    assert recusadas == []

    motor = await _conexao(fabrica)
    async with motor.connect() as conn:
        await _aplica(conn, fusoes)

    async with fabrica() as s:
        restantes = list((await s.execute(select(Company.id))).scalars())
    assert restantes == [fica.id]
    assert await _empresa_do(fabrica, aparelho.id) == fica.id


# ══════════════════════════════════════════════════════════════
# 8. Sem empresa POR DECISÃO: o nulo que ninguém preenche
# ══════════════════════════════════════════════════════════════
#
# `company_id` nulo é "ainda não classificado"; nulo com a marca é "a equipe
# decidiu". O campo da equipe tem três estados — omitido, empresa, `null`
# explícito — e cada um tem o próprio teste.

_MARCADO = {"company_id": None, "sem_empresa_por_decisao": True, "origem": "equipe"}


@pytest.mark.asyncio
async def test_campo_omitido_no_cadastro_nao_marca_decisao(fabrica):
    cliente = await _pessoa(fabrica)  # sem vínculo: herda "nenhuma"
    admin = await _pessoa(fabrica, UserRole.admin)
    produto = await _produto(fabrica)

    da_equipe = await _roda(fabrica, _equipe_cadastra(admin, produto, owner_id=cliente.id))
    do_cliente = await _roda(fabrica, _cliente_cadastra(cliente, produto))

    for criado in (da_equipe, do_cliente):
        assert await _empresa_do(fabrica, criado.id) is None
        assert await _marca_do(fabrica, criado.id) is False
    for auditoria in await _auditorias_de_aparelho(fabrica):
        assert auditoria.new_data is None


@pytest.mark.asyncio
async def test_null_explicito_em_aparelho_sem_empresa_marca_e_audita(fabrica):
    """De nulo para nulo a empresa não muda — muda a intenção, e isso se audita."""
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto)
    tecnico = await _pessoa(fabrica, UserRole.technician)

    await _roda(fabrica, _equipe_edita(tecnico, aparelho, company_id=None))

    assert await _empresa_do(fabrica, aparelho.id) is None
    assert await _marca_do(fabrica, aparelho.id) is True
    [auditoria] = await _auditorias_de_aparelho(fabrica)
    assert auditoria.user_id == tecnico.id
    assert auditoria.old_data == {"company_id": None}
    assert auditoria.new_data == _MARCADO


@pytest.mark.asyncio
async def test_repetir_o_null_em_aparelho_ja_marcado_nao_audita(fabrica):
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto)
    admin = await _pessoa(fabrica, UserRole.admin)
    await _roda(fabrica, _equipe_edita(admin, aparelho, company_id=None))

    await _roda(fabrica, _equipe_edita(admin, aparelho, company_id=None))

    assert await _marca_do(fabrica, aparelho.id) is True
    primeira, segunda = await _auditorias_de_aparelho(fabrica)
    assert primeira.new_data == _MARCADO
    assert segunda.old_data is None and segunda.new_data is None


@pytest.mark.asyncio
async def test_informar_empresa_desfaz_a_marca_e_o_antes_fica_na_trilha(fabrica):
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto)
    admin = await _pessoa(fabrica, UserRole.admin)
    await _roda(fabrica, _equipe_edita(admin, aparelho, company_id=None))

    await _roda(fabrica, _equipe_edita(admin, aparelho, company_id=c.id))

    assert await _empresa_do(fabrica, aparelho.id) == c.id
    assert await _marca_do(fabrica, aparelho.id) is False
    _, troca = await _auditorias_de_aparelho(fabrica)
    assert troca.old_data == {"company_id": None, "sem_empresa_por_decisao": True}
    assert troca.new_data == {"company_id": str(c.id), "origem": "equipe"}


@pytest.mark.asyncio
async def test_editar_outro_campo_nao_mexe_na_marca(fabrica):
    cliente = await _pessoa(fabrica)
    outro = await _pessoa(fabrica)
    produto = await _produto(fabrica)
    marcado = await _aparelho(fabrica, produto, dono=cliente)
    solto = await _aparelho(fabrica, produto, dono=cliente)
    admin = await _pessoa(fabrica, UserRole.admin)
    await _roda(fabrica, _equipe_edita(admin, marcado, company_id=None))

    await _roda(fabrica, _equipe_edita(admin, marcado, location="Sala 3", owner_id=outro.id))
    await _roda(fabrica, _equipe_edita(admin, solto, location="Sala 3"))
    await _roda(fabrica, _cliente_edita(cliente, solto, name="Renomeado"))

    assert await _marca_do(fabrica, marcado.id) is True
    assert await _marca_do(fabrica, solto.id) is False


@pytest.mark.asyncio
async def test_o_vinculo_nao_preenche_o_aparelho_sem_empresa_por_decisao(fabrica):
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica)
    produto = await _produto(fabrica)
    marcado = await _aparelho(fabrica, produto, dono=cliente)
    solto = await _aparelho(fabrica, produto, dono=cliente)
    admin = await _pessoa(fabrica, UserRole.admin)
    await _roda(fabrica, _equipe_edita(admin, marcado, company_id=None))

    await _roda(fabrica, _vincula(admin, c, cliente))

    assert await _empresa_do(fabrica, solto.id) == c.id
    assert await _empresa_do(fabrica, marcado.id) is None, "decisão da equipe não é lacuna"
    assert await _marca_do(fabrica, marcado.id) is True
    propagadas = [
        a
        for a in await _auditorias_de_aparelho(fabrica)
        if (a.new_data or {}).get("origem") == "vinculo_do_responsavel"
    ]
    assert [a.entity_id for a in propagadas] == [solto.id]


@pytest.mark.asyncio
async def test_a_sugestao_tambem_respeita_a_decisao_da_equipe(fabrica):
    g = await _grupo(fabrica)
    cliente = await _pessoa(fabrica)
    produto = await _produto(fabrica)
    marcado = await _aparelho(fabrica, produto, dono=cliente)
    solto = await _aparelho(fabrica, produto, dono=cliente)
    admin = await _pessoa(fabrica, UserRole.admin)
    await _roda(fabrica, _equipe_edita(admin, marcado, company_id=None))

    await _roda(fabrica, _pela_sugestao(admin, g, [cliente]))

    assert await _empresa_do(fabrica, solto.id) is not None
    assert await _empresa_do(fabrica, marcado.id) is None
    assert await _marca_do(fabrica, marcado.id) is True


@pytest.mark.asyncio
async def test_o_banco_recusa_marca_de_decisao_com_empresa_gravada(fabrica):
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, company_id=c.id)

    with pytest.raises(IntegrityError, match="ck_equipments_sem_empresa_por_decisao"):
        async with fabrica() as s:
            await s.execute(
                text("UPDATE equipments SET sem_empresa_por_decisao = true WHERE id = :id"),
                {"id": aparelho.id},
            )
            await s.commit()


@pytest.mark.asyncio
async def test_decisao_em_curso_faz_o_vinculo_pular_o_aparelho(fabrica):
    """A equipe marca; o vínculo chega no meio e espera a linha. Quando ela
    solta, o `WHERE` da propagação é reavaliado com a marca já gravada."""
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, dono=cliente)
    admin = await _pessoa(fabrica, UserRole.admin)
    tecnico = await _pessoa(fabrica, UserRole.technician)

    resultado = await _corrida(
        fabrica,
        _equipe_edita(tecnico, aparelho, company_id=None),
        _vincula(admin, c, cliente),
    )

    assert resultado == ["ok", "ok"]
    assert await _empresa_do(fabrica, aparelho.id) is None
    assert await _marca_do(fabrica, aparelho.id) is True


@pytest.mark.asyncio
async def test_vinculo_em_curso_e_decisao_da_equipe_terminam_sem_empresa_e_sem_erro(fabrica):
    """O vínculo propaga; a equipe manda `null` no meio. Sem a trava no
    aparelho, a edição leria "sem empresa", gravaria só a marca por cima da
    empresa recém-propagada e o `CHECK` responderia 500. Com ela, a edição
    espera, vê a empresa e a tira — com o antes certo na trilha."""
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, dono=cliente)
    admin = await _pessoa(fabrica, UserRole.admin)
    tecnico = await _pessoa(fabrica, UserRole.technician)

    resultado = await _corrida(
        fabrica,
        _vincula(admin, c, cliente),
        _equipe_edita(tecnico, aparelho, company_id=None),
    )

    assert resultado == ["ok", "ok"]
    assert await _empresa_do(fabrica, aparelho.id) is None
    assert await _marca_do(fabrica, aparelho.id) is True
    da_equipe = [
        a
        for a in await _auditorias_de_aparelho(fabrica)
        if (a.new_data or {}).get("origem") == "equipe"
    ]
    assert [a.old_data for a in da_equipe] == [{"company_id": str(c.id)}]
    assert [a.new_data for a in da_equipe] == [_MARCADO]


@pytest.mark.asyncio
async def test_o_preenchimento_so_informa_o_aparelho_sem_empresa_por_decisao(fabrica):
    from scripts.preenche_empresa_do_equipamento import aplica, levanta, planeja

    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    vinculado = await _pessoa(fabrica, company_id=c.id)
    produto = await _produto(fabrica)
    limpo = await _aparelho(fabrica, produto, dono=vinculado)
    marcado = await _aparelho(fabrica, produto, dono=vinculado)
    admin = await _pessoa(fabrica, UserRole.admin)
    await _roda(fabrica, _equipe_edita(admin, marcado, company_id=None))

    motor = await _conexao(fabrica)
    async with motor.connect() as conn:
        plano = planeja(await levanta(conn))

    assert [i.id for i in plano["preenchivel"]] == [limpo.id]
    assert [i.id for i in plano["sem_empresa_por_decisao"]] == [marcado.id]

    async with motor.connect() as conn:
        gravados, pulados = await aplica(conn, plano["preenchivel"])
    assert (gravados, pulados) == ([limpo.id], [])
    assert await _empresa_do(fabrica, marcado.id) is None
    assert await _marca_do(fabrica, marcado.id) is True


@pytest.mark.asyncio
async def test_o_preenchimento_pula_o_aparelho_marcado_depois_do_levantamento(fabrica):
    """Entre o `--confere` e o `--aplicar` a equipe decide: a gravação refaz a
    conferência na própria instrução e não passa por cima."""
    from scripts.preenche_empresa_do_equipamento import aplica, levanta, planeja

    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    vinculado = await _pessoa(fabrica, company_id=c.id)
    produto = await _produto(fabrica)
    aparelho = await _aparelho(fabrica, produto, dono=vinculado)
    admin = await _pessoa(fabrica, UserRole.admin)

    motor = await _conexao(fabrica)
    async with motor.connect() as conn:
        plano = planeja(await levanta(conn))
    assert [i.id for i in plano["preenchivel"]] == [aparelho.id]

    await _roda(fabrica, _equipe_edita(admin, aparelho, company_id=None))
    async with motor.connect() as conn:
        gravados, pulados = await aplica(conn, plano["preenchivel"])

    assert (gravados, pulados) == ([], [aparelho.id])
    assert await _empresa_do(fabrica, aparelho.id) is None
    assert await _marca_do(fabrica, aparelho.id) is True


# ══════════════════════════════════════════════════════════════
# 9. O que o cadastro e a edição pela equipe DEVOLVEM
# ══════════════════════════════════════════════════════════════
#
# A tela de Produtos troca a linha da lista pela resposta do salvar. As duas
# rotas devolviam o equipamento cru — `equipment_company_id: null` com a
# empresa gravada no banco — e a tela passava a dizer "sem empresa (ainda não
# classificado)" logo depois de a equipe classificar. A resposta do salvar tem
# de ser a MESMA do `GET /equipments/{id}`, pelo fio, nos dois modos da flag.

_DA_EQUIPE = (
    "product_name",
    "owner_name",
    "owner_email",
    "linked_company_id",
    "linked_company_name",
    "equipment_company_id",
    "equipment_company_name",
    "no_company_by_decision",
)


async def _cenario_da_resposta(fabrica):
    g = await _grupo(fabrica)
    do_responsavel = await _empresa(fabrica, g, "Do responsavel")
    outra = await _empresa(fabrica, g, "Outra")
    cliente = await _pessoa(fabrica, company_id=do_responsavel.id)
    produto = await _produto(fabrica)
    return do_responsavel, outra, cliente, produto


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", [False, True])
@pytest.mark.parametrize("papel", [UserRole.admin, UserRole.technician])
async def test_o_cadastro_pela_equipe_devolve_as_duas_empresas(
    fabrica, http, monkeypatch, flag, papel
):
    monkeypatch.setattr(get_settings(), "equipamento_por_empresa", flag)
    do_responsavel, outra, cliente, produto = await _cenario_da_resposta(fabrica)
    http.estado["ator"] = await _pessoa(fabrica, papel)

    r = await http.post(
        f"/api/v1/products/{produto.id}/equipments",
        json={"name": "Novo", "owner_id": str(cliente.id), "company_id": str(outra.id)},
    )

    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["equipment_company_id"] == str(outra.id)
    assert corpo["equipment_company_name"] == "Outra"
    assert corpo["no_company_by_decision"] is False
    assert corpo["linked_company_id"] == str(do_responsavel.id)
    assert corpo["linked_company_name"] == "Do responsavel"
    assert corpo["owner_name"] == cliente.name
    assert corpo["owner_email"] == cliente.email
    assert corpo["product_name"] == produto.name
    assert await _empresa_do(fabrica, uuid.UUID(corpo["id"])) == outra.id


@pytest.mark.asyncio
async def test_o_cadastro_que_herda_a_empresa_do_responsavel_devolve_a_herdada(fabrica, http):
    do_responsavel, _, cliente, produto = await _cenario_da_resposta(fabrica)
    http.estado["ator"] = await _pessoa(fabrica, UserRole.admin)

    r = await http.post(
        f"/api/v1/products/{produto.id}/equipments",
        json={"name": "Herdado", "owner_id": str(cliente.id)},
    )

    assert r.status_code == 201, r.text
    assert r.json()["equipment_company_id"] == str(do_responsavel.id)
    assert r.json()["no_company_by_decision"] is False


@pytest.mark.asyncio
async def test_o_cadastro_sem_empresa_por_decisao_devolve_a_marca(fabrica, http):
    _, _, cliente, produto = await _cenario_da_resposta(fabrica)
    http.estado["ator"] = await _pessoa(fabrica, UserRole.admin)

    r = await http.post(
        f"/api/v1/products/{produto.id}/equipments",
        json={"name": "De feira", "owner_id": str(cliente.id), "company_id": None},
    )

    assert r.status_code == 201, r.text
    assert r.json()["equipment_company_id"] is None
    assert r.json()["equipment_company_name"] is None
    assert r.json()["no_company_by_decision"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", [False, True])
async def test_a_edicao_que_define_a_empresa_devolve_a_empresa_definida(
    fabrica, http, monkeypatch, flag
):
    monkeypatch.setattr(get_settings(), "equipamento_por_empresa", flag)
    do_responsavel, outra, cliente, produto = await _cenario_da_resposta(fabrica)
    aparelho = await _aparelho(fabrica, produto, dono=cliente)
    http.estado["ator"] = await _pessoa(fabrica, UserRole.technician)

    r = await http.patch(f"/api/v1/equipments/{aparelho.id}", json={"company_id": str(outra.id)})

    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["equipment_company_id"] == str(outra.id)
    assert corpo["equipment_company_name"] == "Outra"
    assert corpo["no_company_by_decision"] is False
    assert corpo["linked_company_id"] == str(do_responsavel.id)
    assert corpo["owner_name"] == cliente.name
    assert corpo["product_name"] == produto.name


@pytest.mark.asyncio
async def test_a_edicao_com_null_devolve_sem_empresa_por_decisao(fabrica, http):
    do_responsavel, _, cliente, produto = await _cenario_da_resposta(fabrica)
    aparelho = await _aparelho(fabrica, produto, dono=cliente, company_id=do_responsavel.id)
    http.estado["ator"] = await _pessoa(fabrica, UserRole.admin)

    r = await http.patch(f"/api/v1/equipments/{aparelho.id}", json={"company_id": None})

    assert r.status_code == 200, r.text
    assert r.json()["equipment_company_id"] is None
    assert r.json()["no_company_by_decision"] is True


@pytest.mark.asyncio
async def test_inativar_devolve_a_empresa_que_o_aparelho_ja_tinha(fabrica, http):
    """É o caminho do botão de ativar/inativar: `PATCH` só com `is_active`."""
    do_responsavel, _, cliente, produto = await _cenario_da_resposta(fabrica)
    aparelho = await _aparelho(fabrica, produto, dono=cliente, company_id=do_responsavel.id)
    http.estado["ator"] = await _pessoa(fabrica, UserRole.admin)

    r = await http.patch(f"/api/v1/equipments/{aparelho.id}", json={"is_active": False})

    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False
    assert r.json()["equipment_company_id"] == str(do_responsavel.id)
    assert r.json()["equipment_company_name"] == "Do responsavel"
    assert r.json()["no_company_by_decision"] is False
    assert await _empresa_do(fabrica, aparelho.id) == do_responsavel.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corpo_da_edicao",
    [{"name": "Renomeado"}, {"company_id": "OUTRA"}, {"company_id": None}, {"owner_id": None}],
)
async def test_a_resposta_do_salvar_e_a_mesma_do_detalhe(fabrica, http, corpo_da_edicao):
    """A tela pode usar a resposta do salvar no lugar de reler o equipamento."""
    _, outra, cliente, produto = await _cenario_da_resposta(fabrica)
    http.estado["ator"] = await _pessoa(fabrica, UserRole.admin)
    corpo = {k: (str(outra.id) if v == "OUTRA" else v) for k, v in corpo_da_edicao.items()}

    criado = await http.post(
        f"/api/v1/products/{produto.id}/equipments",
        json={"name": "Novo", "owner_id": str(cliente.id)},
    )
    assert criado.status_code == 201, criado.text
    detalhe = await http.get(f"/api/v1/equipments/{criado.json()['id']}")
    assert criado.json() == detalhe.json()

    editado = await http.patch(f"/api/v1/equipments/{criado.json()['id']}", json=corpo)
    assert editado.status_code == 200, editado.text
    detalhe = await http.get(f"/api/v1/equipments/{criado.json()['id']}")
    assert editado.json() == detalhe.json()
    assert set(_DA_EQUIPE) <= set(editado.json())


@pytest.mark.asyncio
async def test_o_cliente_continua_sem_alcancar_as_rotas_da_equipe(fabrica, http):
    """Enriquecer a resposta não abriu a rota: o cliente segue com 403."""
    do_responsavel, _, cliente, produto = await _cenario_da_resposta(fabrica)
    aparelho = await _aparelho(fabrica, produto, dono=cliente, company_id=do_responsavel.id)
    http.estado["ator"] = cliente

    criar = await http.post(f"/api/v1/products/{produto.id}/equipments", json={"name": "X"})
    editar = await http.patch(f"/api/v1/equipments/{aparelho.id}", json={"name": "Y"})

    assert (criar.status_code, editar.status_code) == (403, 403)
    assert "equipment_company_id" not in criar.text + editar.text
