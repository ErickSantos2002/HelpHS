"""
Exclusão de grupo e de empresa (F1-D1) — contra PostgreSQL real.

O que se prova aqui
-------------------
1. **Só administrador exclui.** Técnico recebe 403 nas duas rotas, e nada muda.
2. **Exclusão não leva nada junto.** Grupo com empresa ou nota, e empresa com
   cliente vinculado ou nota, recusam com 409 e as contagens — sem nome nem
   e-mail de cliente. Até 04/11/2026 a FK `companies.group_id` (CASCADE), o
   `delete-orphan` do ORM e o `SET NULL` de `users.company_id` apagavam as
   empresas e as notas e soltavam os clientes, em silêncio.
3. **Vazio continua excluível**, e a exclusão grava `audit_logs` com o retrato
   do que saiu. Recusa não grava `audit_logs` (decisão D3 da F1-A): só o aviso
   no log da aplicação.
4. **Concorrência.** Uma criação de empresa, nota ou vínculo de cliente que
   corre junto com a exclusão nunca é apagada nem solta: ou a exclusão espera e
   recusa, ou a outra operação falha sem gravar.
5. **Falha no commit não exclui pela metade.**

Por que banco próprio e PostgreSQL
----------------------------------
A corrida depende das travas de linha do PostgreSQL (`FOR UPDATE` contra o
`FOR KEY SHARE` que a checagem de FK pega na linha mãe). SQLite não tem nada
disso, e um mock afirmaria a chamada, não o efeito. O banco é deste módulo,
como em `test_hierarquia_de_usuarios_postgres.py`, para nenhum dado de outro
módulo entrar nas contagens.

Como a corrida é forçada
------------------------
`_corrida` roda duas operações em sessões separadas e segura a PRIMEIRA
**depois do flush e antes do commit** — o instante em que a escrita dela já foi
para o banco e as travas de linha estão de pé, mas nada foi comitado. A segunda
roda inteira nesse intervalo, ou fica presa na trava até a primeira soltar
(1 s no máximo).
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
from loguru import logger
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app
from app.models.models import (
    AuditAction,
    AuditLog,
    Base,
    Company,
    CompanyNote,
    Group,
    GroupNote,
    User,
    UserRole,
    UserStatus,
)
from app.schemas.groups import (
    AssignClientRequest,
    CompanyCreate,
    CompanyNoteCreate,
    GroupNoteCreate,
)

_BANCO = "exclusao_grupos_empresas_testes"
_AGORA = datetime.now(UTC)
_CNPJ = "11222333000181"


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
    """Banco PRÓPRIO, criado do zero para este módulo (ver o cabeçalho)."""
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
    """Fábrica de sessões presa ao ENGINE, com as tabelas do domínio vazias."""
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


async def _empresa(fabrica, grupo: Group, nome="Acme Ltda", cnpj=_CNPJ) -> Company:
    c = Company(id=uuid.uuid4(), group_id=grupo.id, name=nome, cnpj=cnpj)
    async with fabrica() as s:
        s.add(c)
        await s.commit()
    return c


async def _nota_do_grupo(fabrica, grupo: Group, autor: User) -> None:
    async with fabrica() as s:
        s.add(GroupNote(group_id=grupo.id, author_id=autor.id, content="nota do grupo"))
        await s.commit()


async def _nota_da_empresa(fabrica, empresa: Company, autor: User) -> None:
    async with fabrica() as s:
        s.add(CompanyNote(company_id=empresa.id, author_id=autor.id, content="nota da empresa"))
        await s.commit()


async def _retrato(fabrica) -> dict:
    """Todas as linhas do domínio — para provar que a recusa não tocou em nada."""
    async with fabrica() as s:
        retrato = {}
        for tabela in ("groups", "companies", "group_notes", "company_notes"):
            linhas = (await s.execute(text(f"SELECT * FROM {tabela} ORDER BY id"))).mappings()
            retrato[tabela] = [dict(linha) for linha in linhas]
        vinculos = await s.execute(text("SELECT id, company_id FROM users ORDER BY id"))
        retrato["vinculos"] = [tuple(v) for v in vinculos]
    return retrato


async def _auditorias(fabrica) -> list[AuditLog]:
    async with fabrica() as s:
        return list((await s.execute(select(AuditLog).order_by(AuditLog.created_at))).scalars())


async def _conta(fabrica, modelo) -> int:
    async with fabrica() as s:
        return (await s.execute(select(func.count()).select_from(modelo))).scalar_one()


@pytest_asyncio.fixture
async def http(fabrica):
    """Cliente HTTP cujo usuário logado é o que o teste puser em `http.ator`."""

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


def _como(http, ator: User):
    http.estado["ator"] = ator
    return http


class _Avisos:
    """Captura o que o loguru escreveu em WARNING ou acima."""

    def __enter__(self):
        self.linhas: list[str] = []
        self._id = logger.add(lambda m: self.linhas.append(str(m)), level="WARNING")
        return self

    def __exit__(self, *exc):
        logger.remove(self._id)

    @property
    def texto(self) -> str:
        return "\n".join(self.linhas)


def _url_grupo(g: Group) -> str:
    return f"/api/v1/groups/{g.id}"


def _url_empresa(c: Company) -> str:
    return f"/api/v1/groups/{c.group_id}/companies/{c.id}"


# ══════════════════════════════════════════════════════════════
# 1. Autorização: só administrador exclui
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("alvo", ["grupo", "empresa"])
async def test_tecnico_nao_exclui_grupo_nem_empresa(fabrica, http, alvo):
    tecnico = await _pessoa(fabrica, UserRole.technician)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    antes = await _retrato(fabrica)

    url = _url_grupo(g) if alvo == "grupo" else _url_empresa(c)
    resp = await _como(http, tecnico).delete(url)

    assert resp.status_code == 403
    assert await _retrato(fabrica) == antes
    assert await _auditorias(fabrica) == []


@pytest.mark.asyncio
async def test_tecnico_recebe_403_mesmo_com_grupo_vazio(fabrica, http):
    """O 403 é por papel, não por conteúdo: vazio não abre a porta ao técnico."""
    tecnico = await _pessoa(fabrica, UserRole.technician)
    g = await _grupo(fabrica)

    resp = await _como(http, tecnico).delete(_url_grupo(g))

    assert resp.status_code == 403
    assert await _conta(fabrica, Group) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", [UserRole.technician, UserRole.client])
async def test_quem_nao_e_admin_continua_gerindo_o_resto_do_grupo(fabrica, http, papel):
    """Não-regressão: só as duas exclusões mudaram de dono.

    Técnico segue criando empresa e nota e vinculando cliente; cliente segue
    sem acesso a nada de `/groups`.
    """
    ator = await _pessoa(fabrica, papel)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica, UserRole.client)
    cliente_http = _como(http, ator)

    respostas = [
        await cliente_http.post(f"{_url_grupo(g)}/companies", json={"name": "Nova"}),
        await cliente_http.post(f"{_url_grupo(g)}/notes", json={"content": "x"}),
        await cliente_http.post(f"{_url_empresa(c)}/clients", json={"user_id": str(cliente.id)}),
    ]

    esperado = 201 if papel == UserRole.technician else 403
    assert [r.status_code for r in respostas] == [esperado] * 3


# ══════════════════════════════════════════════════════════════
# 2. Recusa com contagens, sem perder nada
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_grupo_com_empresas_recusa_com_as_contagens(fabrica, http):
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c1 = await _empresa(fabrica, g, nome="Um")
    c2 = await _empresa(fabrica, g, nome="Dois", cnpj=None)
    clientes = [
        await _pessoa(fabrica, UserRole.client, company_id=c1.id),
        await _pessoa(fabrica, UserRole.client, company_id=c1.id),
        await _pessoa(fabrica, UserRole.client, company_id=c2.id),
    ]
    await _nota_da_empresa(fabrica, c2, admin)
    antes = await _retrato(fabrica)

    with _Avisos() as avisos:
        resp = await _como(http, admin).delete(_url_grupo(g))

    assert resp.status_code == 409
    detalhe = resp.json()["detail"]
    assert "2 empresa(s)" in detalhe
    assert "3 cliente(s) vinculado(s)" in detalhe
    assert "1 nota(s) de empresa" in detalhe
    assert "do grupo" not in detalhe, "sem nota do grupo, a contagem não aparece"
    # Contagem, nunca quem: nenhum nome nem e-mail de cliente no corpo nem no log.
    for cliente in clientes:
        assert cliente.name not in detalhe and cliente.email not in detalhe
        assert cliente.name not in avisos.texto and cliente.email not in avisos.texto
    assert str(g.id) in avisos.texto and str(admin.id) in avisos.texto
    assert await _retrato(fabrica) == antes
    assert await _auditorias(fabrica) == []


@pytest.mark.asyncio
async def test_grupo_so_com_nota_recusa(fabrica, http):
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    await _nota_do_grupo(fabrica, g, admin)
    await _nota_do_grupo(fabrica, g, admin)
    antes = await _retrato(fabrica)

    resp = await _como(http, admin).delete(_url_grupo(g))

    assert resp.status_code == 409
    detalhe = resp.json()["detail"]
    assert "2 nota(s) do grupo" in detalhe
    assert "empresa(s)" not in detalhe
    assert await _retrato(fabrica) == antes
    assert await _auditorias(fabrica) == []


@pytest.mark.asyncio
async def test_empresa_com_clientes_recusa_e_mantem_o_vinculo(fabrica, http):
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    outra = await _empresa(fabrica, g, nome="Outra", cnpj=None)
    await _pessoa(fabrica, UserRole.client, company_id=c.id)
    await _pessoa(fabrica, UserRole.client, company_id=c.id)
    await _pessoa(fabrica, UserRole.client, company_id=outra.id)  # não conta para `c`
    antes = await _retrato(fabrica)

    resp = await _como(http, admin).delete(_url_empresa(c))

    assert resp.status_code == 409
    detalhe = resp.json()["detail"]
    assert "2 cliente(s) vinculado(s)" in detalhe
    assert "nota(s)" not in detalhe
    assert await _retrato(fabrica) == antes
    assert await _auditorias(fabrica) == []


@pytest.mark.asyncio
async def test_empresa_com_cliente_inativo_tambem_recusa(fabrica, http):
    """Vínculo é vínculo: a conta inativa volta a valer se for reativada."""
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica, UserRole.client, company_id=c.id)
    async with fabrica() as s:
        await s.execute(
            text("UPDATE users SET status = 'inactive' WHERE id = :id"), {"id": cliente.id}
        )
        await s.commit()

    resp = await _como(http, admin).delete(_url_empresa(c))

    assert resp.status_code == 409
    assert "1 cliente(s) vinculado(s)" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_empresa_com_notas_recusa_e_mantem_as_notas(fabrica, http):
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    await _nota_da_empresa(fabrica, c, admin)
    antes = await _retrato(fabrica)

    resp = await _como(http, admin).delete(_url_empresa(c))

    assert resp.status_code == 409
    detalhe = resp.json()["detail"]
    assert "1 nota(s)" in detalhe
    assert "cliente(s)" not in detalhe
    assert await _retrato(fabrica) == antes
    assert await _auditorias(fabrica) == []


@pytest.mark.asyncio
async def test_empresa_de_outro_grupo_continua_404(fabrica, http):
    admin = await _pessoa(fabrica, UserRole.admin)
    g1 = await _grupo(fabrica, "Um")
    g2 = await _grupo(fabrica, "Dois")
    c = await _empresa(fabrica, g1)

    resp = await _como(http, admin).delete(f"/api/v1/groups/{g2.id}/companies/{c.id}")

    assert resp.status_code == 404
    assert await _conta(fabrica, Company) == 1


# ══════════════════════════════════════════════════════════════
# 3. Vazio sai, com auditoria
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_admin_exclui_grupo_vazio_e_audita(fabrica, http):
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica, "Grupo Vazio")
    fica = await _grupo(fabrica, "Fica")

    resp = await _como(http, admin).delete(_url_grupo(g))

    assert resp.status_code == 204
    async with fabrica() as s:
        restantes = list((await s.execute(select(Group.id))).scalars())
    assert restantes == [fica.id]
    [auditoria] = await _auditorias(fabrica)
    assert auditoria.user_id == admin.id
    assert auditoria.action == AuditAction.delete
    assert auditoria.entity_type == "group"
    assert auditoria.entity_id == g.id
    assert auditoria.old_data == {
        "name": "Grupo Vazio",
        "empresas": 0,
        "clientes_vinculados": 0,
        "notas_do_grupo": 0,
        "notas_de_empresas": 0,
    }
    assert auditoria.new_data is None
    assert auditoria.created_at is not None


@pytest.mark.asyncio
async def test_admin_exclui_empresa_vazia_e_audita(fabrica, http):
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g, nome="Acme Vazia")
    fica = await _empresa(fabrica, g, nome="Fica", cnpj=None)

    resp = await _como(http, admin).delete(_url_empresa(c))

    assert resp.status_code == 204
    async with fabrica() as s:
        restantes = list((await s.execute(select(Company.id))).scalars())
    assert restantes == [fica.id], "só a empresa vazia sai; o grupo e a irmã ficam"
    assert await _conta(fabrica, Group) == 1
    [auditoria] = await _auditorias(fabrica)
    assert auditoria.user_id == admin.id
    assert auditoria.action == AuditAction.delete
    assert auditoria.entity_type == "company"
    assert auditoria.entity_id == c.id
    assert auditoria.old_data == {
        "name": "Acme Vazia",
        "cnpj": _CNPJ,
        "group_id": str(g.id),
        "clientes_vinculados": 0,
        "notas": 0,
    }


@pytest.mark.asyncio
async def test_grupo_volta_a_ser_excluivel_depois_de_esvaziado(fabrica, http):
    """O 409 orienta, não prende: tirando o que bloqueia, a exclusão passa."""
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    admin_http = _como(http, admin)

    r_grupo_cheio = await admin_http.delete(_url_grupo(g))
    assert r_grupo_cheio.status_code == 409

    r_empresa = await admin_http.delete(_url_empresa(c))
    assert r_empresa.status_code == 204

    r_grupo_vazio = await admin_http.delete(_url_grupo(g))
    assert r_grupo_vazio.status_code == 204
    assert [a.entity_type for a in await _auditorias(fabrica)] == ["company", "group"]


@pytest.mark.asyncio
async def test_grupo_inexistente_continua_404(fabrica, http):
    admin = await _pessoa(fabrica, UserRole.admin)

    resp = await _como(http, admin).delete(f"/api/v1/groups/{uuid.uuid4()}")

    assert resp.status_code == 404
    assert await _auditorias(fabrica) == []


# ══════════════════════════════════════════════════════════════
# 4. Concorrência
# ══════════════════════════════════════════════════════════════


async def _corrida(fabrica, primeira, segunda):
    """Roda as duas em paralelo, segurando a primeira entre o flush e o commit.

    Devolve, para cada uma, "ok", o status HTTP da recusa ou "IntegrityError".
    Qualquer outra exceção sobe.
    """
    a_segunda_chegou = asyncio.Event()

    async def roda(operacao, e_a_primeira: bool):
        async with fabrica() as s:
            commit_original = s.commit

            async def commit_vigiado():
                if e_a_primeira:
                    await s.flush()  # a escrita vai ao banco e as travas ficam de pé
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

    primeira_tarefa = asyncio.create_task(roda(primeira, True))
    await asyncio.sleep(0.3)  # a primeira chega ao commit antes de a segunda começar
    segunda_tarefa = asyncio.create_task(roda(segunda, False))
    return await asyncio.gather(primeira_tarefa, segunda_tarefa)


def _exclui_grupo(admin, g):
    from app.routers.groups import delete_group

    return lambda s: delete_group(g.id, s, admin)


def _exclui_empresa(admin, c):
    from app.routers.groups import delete_company

    return lambda s: delete_company(c.group_id, c.id, s, admin)


def _cria_empresa(admin, g):
    from app.routers.groups import create_company

    return lambda s: create_company(g.id, CompanyCreate(name="Chegou Agora"), s, admin)


def _cria_nota_do_grupo(admin, g):
    from app.routers.groups import create_group_note

    return lambda s: create_group_note(g.id, GroupNoteCreate(content="agora"), s, admin)


def _vincula_cliente(admin, c, cliente):
    from app.routers.groups import assign_client

    return lambda s: assign_client(
        c.group_id, c.id, AssignClientRequest(user_id=cliente.id), s, admin
    )


def _cria_nota_da_empresa(admin, c):
    from app.routers.groups import create_company_note

    return lambda s: create_company_note(
        c.group_id, c.id, CompanyNoteCreate(content="agora"), s, admin
    )


async def _empresas_orfas_ou_soltas(fabrica) -> dict:
    """O que nunca pode existir depois de uma corrida."""
    async with fabrica() as s:
        sem_grupo = (
            await s.execute(
                text(
                    "SELECT count(*) FROM companies c "
                    "LEFT JOIN groups g ON g.id = c.group_id WHERE g.id IS NULL"
                )
            )
        ).scalar_one()
        cliente_para_empresa_inexistente = (
            await s.execute(
                text(
                    "SELECT count(*) FROM users u LEFT JOIN companies c ON c.id = u.company_id "
                    "WHERE u.company_id IS NOT NULL AND c.id IS NULL"
                )
            )
        ).scalar_one()
    return {"sem_grupo": sem_grupo, "cliente_solto": cliente_para_empresa_inexistente}


@pytest.mark.asyncio
@pytest.mark.parametrize("criacao", ["empresa", "nota_do_grupo"])
async def test_criacao_em_curso_impede_a_exclusao_do_grupo(fabrica, criacao):
    """A criação escreveu e ainda não comitou quando a exclusão chega.

    Sem a trava, a exclusão não via a linha nova (não comitada), seguia, e o
    CASCADE da FK apagava a empresa ou a nota assim que ela comitava: as duas
    operações respondiam sucesso e o que acabou de ser criado sumia.
    """
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    cria = _cria_empresa(admin, g) if criacao == "empresa" else _cria_nota_do_grupo(admin, g)

    resultados = await _corrida(fabrica, cria, _exclui_grupo(admin, g))

    assert resultados == ["ok", 409]
    assert await _conta(fabrica, Group) == 1
    modelo = Company if criacao == "empresa" else GroupNote
    assert await _conta(fabrica, modelo) == 1, "o que foi criado não pode sumir"
    assert await _auditorias(fabrica) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("operacao", ["vincula_cliente", "nota_da_empresa"])
async def test_vinculo_ou_nota_em_curso_impede_a_exclusao_da_empresa(fabrica, operacao):
    """Sem a trava, o `SET NULL` soltava o cliente recém-vinculado em silêncio."""
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica, UserRole.client)
    if operacao == "vincula_cliente":
        outra = _vincula_cliente(admin, c, cliente)
    else:
        outra = _cria_nota_da_empresa(admin, c)

    resultados = await _corrida(fabrica, outra, _exclui_empresa(admin, c))

    assert resultados == ["ok", 409]
    assert await _conta(fabrica, Company) == 1
    async with fabrica() as s:
        vinculo = (
            await s.execute(select(User.company_id).where(User.id == cliente.id))
        ).scalar_one()
        notas = (await s.execute(select(func.count()).select_from(CompanyNote))).scalar_one()
    if operacao == "vincula_cliente":
        assert vinculo == c.id, "o cliente vinculado não pode ser solto"
    else:
        assert notas == 1
    assert await _auditorias(fabrica) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("criacao", ["empresa", "nota_do_grupo"])
async def test_exclusao_do_grupo_em_curso_faz_a_criacao_falhar_sem_gravar(fabrica, criacao):
    """A exclusão (grupo vazio) já escreveu quando a criação chega.

    A exclusão é legítima — o grupo estava vazio — e vale. A criação esbarra na
    FK e não grava nada: nenhuma empresa ou nota fica sem grupo.

    ⚠️ Hoje a criação devolve `IntegrityError` (500 pela API). Transformar isso
    em 404 exige mexer em `create_company`/`create_group_note`, que são da
    Sessão 4 — fora da F1-D1. Este teste prende a INTEGRIDADE; a resposta HTTP
    da criação é o ponto de coordenação registrado nas notas da F1-D1.
    """
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    cria = _cria_empresa(admin, g) if criacao == "empresa" else _cria_nota_do_grupo(admin, g)

    resultados = await _corrida(fabrica, _exclui_grupo(admin, g), cria)

    assert resultados[0] == "ok"
    assert resultados[1] in ("IntegrityError", 404), resultados
    assert await _conta(fabrica, Group) == 0
    assert await _conta(fabrica, Company) == 0
    assert await _conta(fabrica, GroupNote) == 0
    assert await _empresas_orfas_ou_soltas(fabrica) == {"sem_grupo": 0, "cliente_solto": 0}
    assert [a.entity_type for a in await _auditorias(fabrica)] == ["group"]


@pytest.mark.asyncio
@pytest.mark.parametrize("operacao", ["vincula_cliente", "nota_da_empresa"])
async def test_exclusao_da_empresa_em_curso_faz_o_vinculo_falhar_sem_gravar(fabrica, operacao):
    """Simétrico ao anterior, para empresa. Mesmo ponto de coordenação."""
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    cliente = await _pessoa(fabrica, UserRole.client)
    if operacao == "vincula_cliente":
        outra = _vincula_cliente(admin, c, cliente)
    else:
        outra = _cria_nota_da_empresa(admin, c)

    resultados = await _corrida(fabrica, _exclui_empresa(admin, c), outra)

    assert resultados[0] == "ok"
    assert resultados[1] in ("IntegrityError", 404), resultados
    assert await _conta(fabrica, Company) == 0
    assert await _conta(fabrica, CompanyNote) == 0
    async with fabrica() as s:
        vinculo = (
            await s.execute(select(User.company_id).where(User.id == cliente.id))
        ).scalar_one()
    assert vinculo is None
    assert await _empresas_orfas_ou_soltas(fabrica) == {"sem_grupo": 0, "cliente_solto": 0}


@pytest.mark.asyncio
async def test_duas_exclusoes_do_mesmo_grupo_uma_vence_e_a_outra_404(fabrica):
    admin = await _pessoa(fabrica, UserRole.admin)
    outro_admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)

    resultados = await _corrida(fabrica, _exclui_grupo(admin, g), _exclui_grupo(outro_admin, g))

    assert resultados == ["ok", 404]
    assert len(await _auditorias(fabrica)) == 1, "uma exclusão, uma auditoria"


@pytest.mark.asyncio
async def test_exclusao_de_empresa_e_do_grupo_dela_ao_mesmo_tempo(fabrica):
    """A empresa sai; o grupo, que ainda a via, recusa. Nada fica pela metade."""
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)

    resultados = await _corrida(fabrica, _exclui_empresa(admin, c), _exclui_grupo(admin, g))

    assert resultados[0] == "ok"
    assert resultados[1] in ("ok", 409), resultados
    assert await _conta(fabrica, Company) == 0
    assert await _conta(fabrica, Group) == (0 if resultados[1] == "ok" else 1)
    assert await _empresas_orfas_ou_soltas(fabrica) == {"sem_grupo": 0, "cliente_solto": 0}


# ══════════════════════════════════════════════════════════════
# 5. Falha no commit não exclui pela metade
# ══════════════════════════════════════════════════════════════


async def _gatilho_que_recusa_auditoria(fabrica, codigo: str) -> None:
    """Faz o INSERT em `audit_logs` falhar DENTRO da transação da exclusão."""
    async with fabrica() as s:
        await s.execute(
            text(
                "CREATE OR REPLACE FUNCTION recusa_auditoria() RETURNS trigger AS $$ "
                f"BEGIN RAISE EXCEPTION 'falha simulada' USING ERRCODE = '{codigo}'; END "
                "$$ LANGUAGE plpgsql"
            )
        )
        await s.execute(text("DROP TRIGGER IF EXISTS recusa_auditoria ON audit_logs"))
        await s.execute(
            text(
                "CREATE TRIGGER recusa_auditoria BEFORE INSERT ON audit_logs "
                "FOR EACH ROW EXECUTE FUNCTION recusa_auditoria()"
            )
        )
        await s.commit()


async def _remove_gatilho(fabrica) -> None:
    async with fabrica() as s:
        await s.execute(text("DROP TRIGGER IF EXISTS recusa_auditoria ON audit_logs"))
        await s.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("alvo", ["grupo", "empresa"])
async def test_falha_de_integridade_no_commit_devolve_409_e_nao_exclui(fabrica, http, alvo):
    """Rede da rota: `IntegrityError` no commit vira 409, com rollback inteiro.

    A exclusão e a auditoria são uma transação só — se a auditoria não grava,
    a linha não sai.
    """
    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    # Grupo precisa estar vazio para chegar ao commit; a empresa, idem.
    url = _url_grupo(g) if alvo == "grupo" else _url_empresa(await _empresa(fabrica, g))
    antes = await _retrato(fabrica)
    await _gatilho_que_recusa_auditoria(fabrica, "23503")  # foreign_key_violation
    try:
        resp = await _como(http, admin).delete(url)
    finally:
        await _remove_gatilho(fabrica)

    assert resp.status_code == 409
    assert await _retrato(fabrica) == antes
    assert await _auditorias(fabrica) == []


@pytest.mark.asyncio
async def test_falha_qualquer_no_commit_nao_exclui_pela_metade(fabrica):
    """Erro que não é de integridade sobe (vira 500), mas sem gravar nada."""
    from app.routers.groups import delete_company

    admin = await _pessoa(fabrica, UserRole.admin)
    g = await _grupo(fabrica)
    c = await _empresa(fabrica, g)
    antes = await _retrato(fabrica)
    await _gatilho_que_recusa_auditoria(fabrica, "P0001")
    try:
        async with fabrica() as s:
            with pytest.raises(Exception) as erro:
                await delete_company(g.id, c.id, s, admin)
    finally:
        await _remove_gatilho(fabrica)

    assert not isinstance(erro.value, HTTPException)
    assert await _retrato(fabrica) == antes
    assert await _auditorias(fabrica) == []
