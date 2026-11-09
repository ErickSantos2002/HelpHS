"""
Vínculo de cliente a empresa (F2-A1) — contra PostgreSQL real.

O que se prova aqui
-------------------
1. **Nenhuma transferência silenciosa.** Dois vínculos simultâneos do mesmo
   cliente a empresas diferentes: um vence, o outro recebe 409. O mesmo para
   duas confirmações de sugestão com clientes em comum, e para vínculo direto
   contra sugestão.
2. **Vínculo contra exclusão** (F1-D1). A exclusão em curso faz o vínculo
   responder 404 — não o 500 da FK que a F1-D1 deixou registrado como ponto
   de coordenação —, e o vínculo em curso faz a exclusão recusar.
3. **Vínculo contra desativação e anonimização.** Quem chega depois relê a
   situação comitada: conta que acabou de ficar inativa não é vinculada.
4. **Sem espera em círculo.** As alterações de conta da F1-A travam todos os
   admins e depois o alvo; o INSERT em `audit_logs` do vínculo checa a FK do
   ator. Com a trava do ator tomada por último, as duas operações travavam em
   círculo (`DeadlockDetectedError`, medido em SQL puro antes da escrita).
5. **O cliente não muda o próprio vínculo** pelo `PATCH /users/me`.

Banco próprio, como `test_exclusao_grupos_empresas_postgres.py`, e o mesmo
jeito de forçar a corrida: a primeira operação fica presa entre o flush e o
commit, com as travas de pé, enquanto a segunda roda ou espera.
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
from sqlalchemy import func, select, text
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
    Group,
    User,
    UserRole,
    UserStatus,
)
from app.schemas.groups import AssignClientRequest, CreateCompanyFromSuggestion
from app.schemas.user import UserStatusUpdate

_BANCO = "vinculo_cliente_empresa_testes"
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
        await conn.execute(text("TRUNCATE groups, companies, users, audit_logs CASCADE"))
    yield async_sessionmaker(motor, expire_on_commit=False)
    await motor.dispose()


async def _pessoa(fabrica, papel: UserRole, *, company_id=None) -> User:
    pessoa = User(
        id=uuid.uuid4(),
        name=f"Pessoa {papel.value} {uuid.uuid4().hex[:6]}",
        email=f"{uuid.uuid4().hex[:12]}@test.invalid",
        password="x",
        role=papel,
        status=UserStatus.active,
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


async def _vinculo(fabrica, pessoa: User):
    async with fabrica() as s:
        return (await s.execute(select(User.company_id).where(User.id == pessoa.id))).scalar_one()


async def _situacao(fabrica, pessoa: User) -> UserStatus:
    async with fabrica() as s:
        return (await s.execute(select(User.status).where(User.id == pessoa.id))).scalar_one()


async def _vinculos_auditados(fabrica) -> list[AuditLog]:
    async with fabrica() as s:
        return list(
            (
                await s.execute(
                    select(AuditLog)
                    .where(AuditLog.action == AuditAction.assign)
                    .order_by(AuditLog.created_at)
                )
            ).scalars()
        )


async def _conta(fabrica, modelo) -> int:
    async with fabrica() as s:
        return (await s.execute(select(func.count()).select_from(modelo))).scalar_one()


async def _cliente_solto(fabrica) -> int:
    """Cliente apontando para empresa que não existe — nunca pode haver."""
    async with fabrica() as s:
        return (
            await s.execute(
                text(
                    "SELECT count(*) FROM users u LEFT JOIN companies c ON c.id = u.company_id "
                    "WHERE u.company_id IS NOT NULL AND c.id IS NULL"
                )
            )
        ).scalar_one()


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


def _exclui_grupo(admin, g):
    from app.routers.groups import delete_group

    return lambda s: delete_group(g.id, s, admin)


def _desativa(admin, cliente):
    from app.routers.users import update_user_status

    return lambda s: update_user_status(
        cliente.id, UserStatusUpdate(status=UserStatus.inactive), s, admin
    )


def _anonimiza(admin, cliente):
    from app.routers.users import anonymize_user

    return lambda s: anonymize_user(cliente.id, s, admin, get_settings())


# ══════════════════════════════════════════════════════════════
# 1. Nenhuma transferência silenciosa
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_dois_vinculos_simultaneos_a_empresas_diferentes_um_vence(fabrica):
    """Sem a trava no cliente, os dois liam `company_id` nulo e o último vencia."""
    admin = await _pessoa(fabrica, UserRole.admin)
    tecnico = await _pessoa(fabrica, UserRole.technician)
    g = await _grupo(fabrica)
    c1 = await _empresa(fabrica, g, "Primeira")
    c2 = await _empresa(fabrica, g, "Segunda")
    cliente = await _pessoa(fabrica, UserRole.client)

    resultados = await _corrida(
        fabrica, _vincula(admin, c1, cliente), _vincula(tecnico, c2, cliente)
    )

    assert resultados == ["ok", 409]
    assert await _vinculo(fabrica, cliente) == c1.id, "a segunda não pode mover o cliente"
    (registro,) = await _vinculos_auditados(fabrica)
    assert registro.new_data["company_id"] == str(c1.id)


@pytest.mark.asyncio
async def test_dois_vinculos_simultaneos_na_mesma_empresa_auditam_uma_vez(fabrica):
    admin = await _pessoa(fabrica, UserRole.admin)
    outro_admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica, UserRole.client)

    resultados = await _corrida(
        fabrica, _vincula(admin, c, cliente), _vincula(outro_admin, c, cliente)
    )

    assert resultados == ["ok", "ok"], "a segunda é idempotente (200), não erro"
    assert await _vinculo(fabrica, cliente) == c.id
    assert len(await _vinculos_auditados(fabrica)) == 1


@pytest.mark.asyncio
async def test_duas_sugestoes_cruzadas_com_os_mesmos_clientes_sem_deadlock(fabrica):
    """Listas em ordens opostas: a trava por id impede a espera em círculo."""
    admin = await _pessoa(fabrica, UserRole.admin)
    outro_admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    um = await _pessoa(fabrica, UserRole.client)
    dois = await _pessoa(fabrica, UserRole.client)

    resultados = await _corrida(
        fabrica,
        _pela_sugestao(admin, g, [um, dois], nome="Primeira"),
        _pela_sugestao(outro_admin, g, [dois, um], nome="Segunda"),
    )

    assert resultados == ["ok", 409]
    async with fabrica() as s:
        nomes = (await s.execute(select(Company.name))).scalars().all()
    assert nomes == ["Primeira"], "a recusa não pode deixar empresa criada"
    assert await _vinculo(fabrica, um) == await _vinculo(fabrica, dois)
    assert len(await _vinculos_auditados(fabrica)) == 2


@pytest.mark.asyncio
async def test_vinculo_direto_e_sugestao_sobre_o_mesmo_cliente(fabrica):
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica, UserRole.client)

    resultados = await _corrida(
        fabrica, _vincula(admin, c, cliente), _pela_sugestao(admin, g, [cliente])
    )

    assert resultados == ["ok", 409]
    assert await _vinculo(fabrica, cliente) == c.id
    assert await _conta(fabrica, Company) == 1


@pytest.mark.asyncio
async def test_sugestao_e_vinculo_direto_sobre_o_mesmo_cliente(fabrica):
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g, "Ja Existia")
    cliente = await _pessoa(fabrica, UserRole.client)

    resultados = await _corrida(
        fabrica, _pela_sugestao(admin, g, [cliente], nome="Nova"), _vincula(admin, c, cliente)
    )

    assert resultados == ["ok", 409]
    async with fabrica() as s:
        nova = (await s.execute(select(Company.id).where(Company.name == "Nova"))).scalar_one()
    assert await _vinculo(fabrica, cliente) == nova


# ══════════════════════════════════════════════════════════════
# 2. Vínculo contra exclusão de empresa ou grupo (F1-D1)
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_exclusao_da_empresa_em_curso_faz_o_vinculo_responder_404(fabrica):
    """Até a F2-A1 o vínculo esbarrava na FK: `IntegrityError`, 500 pela API."""
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica, UserRole.client)

    resultados = await _corrida(fabrica, _exclui_empresa(admin, c), _vincula(admin, c, cliente))

    assert resultados == ["ok", 404]
    assert await _vinculo(fabrica, cliente) is None
    assert await _cliente_solto(fabrica) == 0
    assert await _vinculos_auditados(fabrica) == []


@pytest.mark.asyncio
async def test_vinculo_em_curso_faz_a_exclusao_da_empresa_recusar(fabrica):
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica, UserRole.client)

    resultados = await _corrida(fabrica, _vincula(admin, c, cliente), _exclui_empresa(admin, c))

    assert resultados == ["ok", 409]
    assert await _vinculo(fabrica, cliente) == c.id
    assert len(await _vinculos_auditados(fabrica)) == 1


@pytest.mark.asyncio
async def test_exclusao_da_empresa_com_cliente_recusa_e_o_desvinculo_segue(fabrica):
    """Empresa só sai vazia: aqui ela tem cliente, então a exclusão recusa
    e o desvínculo segue — a ordem das travas não deixa nenhum dos dois em 500."""
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica, UserRole.client, company_id=c.id)

    resultados = await _corrida(fabrica, _exclui_empresa(admin, c), _desvincula(admin, c, cliente))

    assert resultados == [409, "ok"]
    assert await _vinculo(fabrica, cliente) is None
    assert await _conta(fabrica, Company) == 1


@pytest.mark.asyncio
async def test_exclusao_do_grupo_em_curso_faz_a_sugestao_responder_404(fabrica):
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    cliente = await _pessoa(fabrica, UserRole.client)

    resultados = await _corrida(
        fabrica, _exclui_grupo(admin, g), _pela_sugestao(admin, g, [cliente])
    )

    assert resultados == ["ok", 404]
    assert await _conta(fabrica, Company) == 0
    assert await _vinculo(fabrica, cliente) is None
    assert await _vinculos_auditados(fabrica) == []


@pytest.mark.asyncio
async def test_sugestao_em_curso_faz_a_exclusao_do_grupo_recusar(fabrica):
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    cliente = await _pessoa(fabrica, UserRole.client)

    resultados = await _corrida(
        fabrica, _pela_sugestao(admin, g, [cliente]), _exclui_grupo(admin, g)
    )

    assert resultados == ["ok", 409]
    assert await _conta(fabrica, Group) == 1
    assert await _vinculo(fabrica, cliente) is not None


@pytest.mark.asyncio
async def test_exclusao_da_empresa_reaproveitavel_em_curso_nao_solta_a_sugestao(fabrica):
    """A sugestão ia reaproveitar a empresa pelo CNPJ e ela foi excluída no meio.

    A trava na empresa faz a sugestão esperar e, ao reler, não encontrá-la:
    cria uma nova. O que nunca pode acontecer é vincular à que sumiu.
    """
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    cnpj = "11222333000181"
    c = await _empresa(fabrica, g, "Vazia", cnpj=cnpj)
    cliente = await _pessoa(fabrica, UserRole.client)

    resultados = await _corrida(
        fabrica, _exclui_empresa(admin, c), _pela_sugestao(admin, g, [cliente], cnpj=cnpj)
    )

    assert resultados == ["ok", "ok"]
    vinculo = await _vinculo(fabrica, cliente)
    assert vinculo is not None and vinculo != c.id
    assert await _cliente_solto(fabrica) == 0


# ══════════════════════════════════════════════════════════════
# 3. Vínculo contra desativação e anonimização
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_desativacao_em_curso_faz_o_vinculo_recusar(fabrica):
    admin = await _pessoa(fabrica, UserRole.admin)
    outro_admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica, UserRole.client)

    resultados = await _corrida(
        fabrica, _desativa(outro_admin, cliente), _vincula(admin, c, cliente)
    )

    assert resultados == ["ok", 409]
    assert await _situacao(fabrica, cliente) == UserStatus.inactive
    assert await _vinculo(fabrica, cliente) is None


@pytest.mark.asyncio
async def test_vinculo_em_curso_e_desativacao_terminam_os_dois(fabrica):
    admin = await _pessoa(fabrica, UserRole.admin)
    outro_admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica, UserRole.client)

    resultados = await _corrida(
        fabrica, _vincula(admin, c, cliente), _desativa(outro_admin, cliente)
    )

    assert resultados == ["ok", "ok"]
    assert await _vinculo(fabrica, cliente) == c.id
    assert await _situacao(fabrica, cliente) == UserStatus.inactive


@pytest.mark.asyncio
async def test_anonimizacao_em_curso_faz_o_vinculo_recusar(fabrica):
    admin = await _pessoa(fabrica, UserRole.admin)
    outro_admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica, UserRole.client)

    resultados = await _corrida(
        fabrica, _anonimiza(outro_admin, cliente), _vincula(admin, c, cliente)
    )

    assert resultados == ["ok", 409]
    assert await _situacao(fabrica, cliente) == UserStatus.anonymized
    assert await _vinculo(fabrica, cliente) is None


@pytest.mark.asyncio
async def test_desativacao_em_curso_faz_a_sugestao_recusar(fabrica):
    admin = await _pessoa(fabrica, UserRole.admin)
    outro_admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    cliente = await _pessoa(fabrica, UserRole.client)

    resultados = await _corrida(
        fabrica, _desativa(outro_admin, cliente), _pela_sugestao(admin, g, [cliente])
    )

    assert resultados == ["ok", 409]
    assert await _conta(fabrica, Company) == 0


# ══════════════════════════════════════════════════════════════
# 4. Ordem das travas: sem espera em círculo com a F1-A
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("operacao", ["vincula", "desvincula", "sugestao"])
async def test_alteracao_de_conta_com_os_admins_travados_nao_trava_em_circulo(
    fabrica, url_do_banco, operacao
):
    """A intercalação que dava deadlock, reproduzida passo a passo.

    T2 faz o que `_trava_para_alterar_conta` faz: `FOR UPDATE` em todos os
    admins ativos (o ator do vínculo entre eles) e DEPOIS no alvo. O vínculo
    começa no meio. Se ele travasse o cliente antes do ator, ficaria com o
    cliente esperando o ator (pela FK de `audit_logs`), e T2 com o ator
    esperando o cliente. Travando o ator primeiro, o vínculo espera sem segurar
    nada, T2 termina, e o vínculo relê o cliente já desativado.
    """
    admin = await _pessoa(fabrica, UserRole.admin)
    await _pessoa(fabrica, UserRole.admin)  # quem altera a conta em T2
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    vinculado = operacao == "desvincula"
    cliente = await _pessoa(fabrica, UserRole.client, company_id=c.id if vinculado else None)
    if operacao == "vincula":
        op = _vincula(admin, c, cliente)
    elif operacao == "desvincula":
        op = _desvincula(admin, c, cliente)
    else:
        op = _pela_sugestao(admin, g, [cliente])

    motor = create_async_engine(url_do_banco, poolclass=NullPool)
    try:
        async with motor.connect() as t2:
            await t2.execute(text("SET deadlock_timeout = '200ms'"))
            await t2.execute(
                text(
                    "SELECT id FROM users WHERE role = 'admin' AND status = 'active' "
                    "ORDER BY id FOR UPDATE"
                )
            )

            async def roda_o_vinculo():
                async with fabrica() as s:
                    await s.execute(text("SET deadlock_timeout = '200ms'"))
                    try:
                        await op(s)
                        return "ok"
                    except HTTPException as e:
                        return e.status_code
                    except DBAPIError as e:
                        return "deadlock" if "deadlock" in str(e).lower() else repr(e)

            tarefa = asyncio.create_task(roda_o_vinculo())
            await asyncio.sleep(0.5)  # o vínculo chegou à primeira trava que conflita

            await t2.execute(
                text("SELECT id FROM users WHERE id = :id FOR UPDATE"), {"id": cliente.id}
            )
            await t2.execute(
                text("UPDATE users SET status = 'inactive' WHERE id = :id"), {"id": cliente.id}
            )
            await t2.commit()

            resultado = await asyncio.wait_for(tarefa, timeout=10)
    finally:
        await motor.dispose()

    assert resultado != "deadlock"
    if operacao == "desvincula":
        # Desvincular não depende da situação: limpa o vínculo de quem está inativo.
        assert resultado == "ok"
        assert await _vinculo(fabrica, cliente) is None
    else:
        assert resultado == 409, "o vínculo relê o cliente desativado"
        assert await _vinculo(fabrica, cliente) is None
    assert await _situacao(fabrica, cliente) == UserStatus.inactive


@pytest.mark.asyncio
@pytest.mark.parametrize("operacao", ["vincula", "desvincula", "sugestao"])
async def test_travas_saem_na_ordem_ator_grupo_ou_empresa_clientes(fabrica, operacao):
    """A ordem, lida nas instruções que chegam ao banco.

    As corridas acima não conseguem intercalar duas aquisições de trava no
    meio (a primeira operação já segura tudo quando a segunda começa), então
    "clientes em ordem de id" não aparece nelas. Aqui ela fica presa: uma
    instrução só trava os clientes, com `ORDER BY users.id` — o PostgreSQL
    trava as linhas na ordem em que o `ORDER BY` as entrega.
    """
    from sqlalchemy import event

    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g, cnpj="11222333000181")
    um = await _pessoa(
        fabrica, UserRole.client, company_id=c.id if operacao == "desvincula" else None
    )
    dois = await _pessoa(fabrica, UserRole.client)
    if operacao == "vincula":
        op = _vincula(admin, c, um)
    elif operacao == "desvincula":
        op = _desvincula(admin, c, um)
    else:
        op = _pela_sugestao(admin, g, [dois, um], cnpj="11222333000181")

    travas: list[str] = []

    def _anota(_conn, _cursor, sql, *_args):
        if " FOR " in sql:
            travas.append(" ".join(sql.split()))

    async with fabrica() as s:
        motor = s.bind.sync_engine if hasattr(s.bind, "sync_engine") else s.bind
        event.listen(motor, "before_cursor_execute", _anota)
        try:
            await op(s)
        finally:
            event.remove(motor, "before_cursor_execute", _anota)

    def tipo(sql: str) -> str:
        if "FROM users" in sql:
            return "clientes" if sql.endswith("FOR UPDATE") else "ator"
        return "grupo" if "FROM groups" in sql else "empresa"

    esperado = {
        "vincula": ["ator", "empresa", "clientes"],
        "desvincula": ["ator", "empresa", "clientes"],
        "sugestao": ["ator", "grupo", "empresa", "clientes"],
    }[operacao]
    assert [tipo(t) for t in travas] == esperado, travas
    assert travas[0].endswith("FOR KEY SHARE")
    (dos_clientes,) = [t for t in travas if tipo(t) == "clientes"]
    assert "ORDER BY users.id" in dos_clientes


# ══════════════════════════════════════════════════════════════
# 5. O cliente não muda o próprio vínculo
# ══════════════════════════════════════════════════════════════


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
async def test_cliente_nao_muda_o_proprio_vinculo_pelo_perfil(fabrica, http, vinculado):
    g = await _grupo(fabrica)
    propria = await _empresa(fabrica, g, "Propria")
    alheia = await _empresa(fabrica, g, "Alheia")
    cliente = await _pessoa(fabrica, UserRole.client, company_id=propria.id if vinculado else None)
    http.estado["ator"] = cliente

    resp = await http.patch(
        "/api/v1/users/me", json={"name": "Nome Novo", "company_id": str(alheia.id)}
    )

    assert resp.status_code == 200, resp.text
    assert await _vinculo(fabrica, cliente) == (propria.id if vinculado else None)
    assert await _vinculos_auditados(fabrica) == []
