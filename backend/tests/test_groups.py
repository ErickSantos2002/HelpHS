"""
Cobertura do domínio de empresa em `groups.py`.

Até aqui, **nenhum** teste da suíte referenciava `Company`, `company_id` ou
qualquer endpoint de `/groups` — os únicos "company" em `tests/` eram
`company_name` e `company_cep`, colunas de onboarding do `User`. O router com
mais regra de negócio sobre empresa era o único sem rede.

Estes testes são de **caracterização**: prendem o que o código faz hoje, para
que a próxima mudança seja decisão e não descoberta. Dois comportamentos
entram aqui exatamente porque são silenciosos e ninguém os escolheu de
propósito — o `PUT` que ignora `None` e a exclusão que desvincula cliente sem
avisar.

Banco de verdade, não mock. A exclusão de empresa **não dá para provar com
mock**: quem desvincula o cliente é o SQLAlchemy (a relação `Company.clients`
não tem cascade de exclusão, então o ORM anula a FK) com a FK
`ON DELETE SET NULL` por baixo. Um mock afirmaria que `db.delete` foi chamado
e passaria mesmo que a regra fosse o contrário — o teste que promete mais do
que prova. SQLite em memória serve: reproduz o mesmo resultado que o Postgres
efêmero mostrou no levantamento de 24/08, e roda no CI sem subir serviço.

`create_all` vai só no subconjunto de tabelas usado aqui porque `kb_articles`
tem uma coluna `ARRAY`, que o SQLite não compila.
"""

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app
from app.models.models import Base, Company, CompanyNote, Group, User, UserRole, UserStatus

_TABELAS = ("groups", "companies", "users", "company_notes")

CNPJ_MASCARADO = "11.222.333/0001-81"
CNPJ_DIGITOS = "11222333000181"


@pytest_asyncio.fixture
async def db():
    """
    Sessão sobre SQLite em memória, com o schema real dos modelos.

    `StaticPool` é obrigatório: sem ele cada conexão nova abre um banco em
    memória **próprio** e a tabela criada no setup some na primeira consulta
    do endpoint. `PRAGMA foreign_keys=ON` também é — no SQLite a FK é
    desligada por padrão, e sem ela o `ON DELETE SET NULL` que este arquivo
    testa não valeria nada.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _liga_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    tabelas = [Base.metadata.tables[t] for t in _TABELAS]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tabelas)

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as sessao:
        yield sessao

    await engine.dispose()


@pytest_asyncio.fixture
async def cliente_http(db):
    """Cliente HTTP autenticado como admin, ligado à sessão do teste."""
    admin = User(
        name="Admin",
        email=f"admin-{uuid.uuid4()}@helphs.test",
        password="x",
        role=UserRole.admin,
        status=UserStatus.active,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)

    async def _get_db():
        yield db

    async def _get_current_user():
        return admin

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_current_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


async def _grupo(db, nome="Grupo Teste") -> Group:
    g = Group(name=nome)
    db.add(g)
    await db.commit()
    await db.refresh(g)
    return g


async def _empresa(db, grupo, **campos) -> Company:
    c = Company(group_id=grupo.id, name=campos.pop("name", "Acme"), **campos)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def _cliente(db, **campos) -> User:
    u = User(
        name=campos.pop("name", "Cliente"),
        email=campos.pop("email", f"cli-{uuid.uuid4()}@x.com"),
        password="x",
        role=UserRole.client,
        status=campos.pop("status", UserStatus.active),
        **campos,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


# ═══════════════════════════════════════════════════════════════
# create_company
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cria_empresa_e_normaliza_o_cnpj_ate_o_banco(db, cliente_http):
    """
    Fecha o circuito do `62f022e`: o teste de schema provava a conversão, este
    prova que o que chega à coluna são os 14 dígitos.
    """
    g = await _grupo(db)

    resp = await cliente_http.post(
        f"/api/v1/groups/{g.id}/companies",
        json={"name": "Acme", "cnpj": CNPJ_MASCARADO},
    )

    assert resp.status_code == 201
    assert resp.json()["cnpj"] == CNPJ_DIGITOS

    gravada = (await db.execute(select(Company).where(Company.name == "Acme"))).scalar_one()
    assert gravada.cnpj == CNPJ_DIGITOS


@pytest.mark.asyncio
async def test_cria_empresa_sem_cnpj(db, cliente_http):
    g = await _grupo(db)
    resp = await cliente_http.post(f"/api/v1/groups/{g.id}/companies", json={"name": "Sem CNPJ"})
    assert resp.status_code == 201
    assert resp.json()["cnpj"] is None


@pytest.mark.asyncio
async def test_cria_empresa_com_cnpj_torto_e_recusado(db, cliente_http):
    g = await _grupo(db)
    resp = await cliente_http.post(
        f"/api/v1/groups/{g.id}/companies", json={"name": "Acme", "cnpj": "123"}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_cria_empresa_em_grupo_inexistente_da_404(db, cliente_http):
    resp = await cliente_http.post(
        f"/api/v1/groups/{uuid.uuid4()}/companies", json={"name": "Acme"}
    )
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════
# update_company — o PUT que ignora None
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_atualiza_empresa_troca_os_campos_enviados(db, cliente_http):
    g = await _grupo(db)
    c = await _empresa(db, g, name="Antiga", cnpj=CNPJ_DIGITOS)

    resp = await cliente_http.put(
        f"/api/v1/groups/{g.id}/companies/{c.id}", json={"name": "Nova", "city": "Recife"}
    )

    assert resp.status_code == 200
    await db.refresh(c)
    assert c.name == "Nova"
    assert c.city == "Recife"


@pytest.mark.asyncio
async def test_campo_ausente_no_put_nao_apaga_o_valor(db, cliente_http):
    """
    `update_company` pula valor `None` (`groups.py:282`), então campo não
    enviado fica como está. É o comportamento desejado num PUT parcial.
    """
    g = await _grupo(db)
    c = await _empresa(db, g, name="Acme", cnpj=CNPJ_DIGITOS, city="Recife")

    resp = await cliente_http.put(f"/api/v1/groups/{g.id}/companies/{c.id}", json={"name": "Acme2"})

    assert resp.status_code == 200
    await db.refresh(c)
    assert c.cnpj == CNPJ_DIGITOS
    assert c.city == "Recife"


@pytest.mark.asyncio
async def test_campo_enviado_vazio_limpa_o_valor(db, cliente_http):
    """
    Enviado vazio significa **limpar**; ausente significa **não mexer**.

    O laço antigo era `if val is not None`, e com ele os dois casos eram
    indistinguíveis: o admin apagava o CNPJ na tela, salvava, e o valor velho
    voltava sem nenhum aviso. A distinção agora vem do `model_fields_set` do
    pydantic, que diz o que o cliente **mandou** — não o que chegou nulo.
    """
    g = await _grupo(db)
    c = await _empresa(db, g, name="Acme", cnpj=CNPJ_DIGITOS, city="Recife")

    resp = await cliente_http.put(
        f"/api/v1/groups/{g.id}/companies/{c.id}",
        json={"name": "Acme", "cnpj": "", "city": None},
    )

    assert resp.status_code == 200
    await db.refresh(c)
    assert c.cnpj is None, "campo enviado vazio precisa limpar"
    assert c.city is None, "null explícito também limpa"


@pytest.mark.asyncio
async def test_nome_enviado_vazio_da_422_e_nao_500(db, cliente_http):
    """
    `companies.name` é `NOT NULL` no banco, mas `str | None` no schema.

    Sem guarda, "enviou, grava" mandaria `NULL` para uma coluna obrigatória e
    o admin veria erro de servidor no lugar de uma mensagem. Empresa sem nome
    não é estado válido — a recusa é do contrato, não do banco.
    """
    g = await _grupo(db)
    c = await _empresa(db, g, name="Acme")

    for vazio in ("", None):
        resp = await cliente_http.put(
            f"/api/v1/groups/{g.id}/companies/{c.id}", json={"name": vazio}
        )
        assert resp.status_code == 422, f"name={vazio!r} devia dar 422, veio {resp.status_code}"

    await db.refresh(c)
    assert c.name == "Acme", "a recusa não pode ter gravado nada"


@pytest.mark.asyncio
async def test_atualiza_empresa_de_outro_grupo_da_404(db, cliente_http):
    """`_get_company_or_404` casa empresa **e** grupo: id certo, grupo errado, 404."""
    g1 = await _grupo(db, "G1")
    g2 = await _grupo(db, "G2")
    c = await _empresa(db, g1, name="Acme")

    resp = await cliente_http.put(f"/api/v1/groups/{g2.id}/companies/{c.id}", json={"name": "X"})
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════
# assign_client / unassign_client
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_vincula_cliente_a_empresa(db, cliente_http):
    g = await _grupo(db)
    c = await _empresa(db, g)
    u = await _cliente(db)

    resp = await cliente_http.post(
        f"/api/v1/groups/{g.id}/companies/{c.id}/clients", json={"user_id": str(u.id)}
    )

    assert resp.status_code == 201
    await db.refresh(u)
    assert u.company_id == c.id


@pytest.mark.asyncio
async def test_vincular_move_de_uma_empresa_para_outra_sem_reclamar(db, cliente_http):
    """
    `assign_client` não checa vínculo anterior: sobrescreve. Vale registrar —
    é o que permite corrigir um vínculo errado sem desvincular antes, e
    também o que deixa mover cliente sem rastro.
    """
    g = await _grupo(db)
    c1 = await _empresa(db, g, name="Primeira")
    c2 = await _empresa(db, g, name="Segunda")
    u = await _cliente(db, company_id=c1.id)

    resp = await cliente_http.post(
        f"/api/v1/groups/{g.id}/companies/{c2.id}/clients", json={"user_id": str(u.id)}
    )

    assert resp.status_code == 201
    await db.refresh(u)
    assert u.company_id == c2.id


@pytest.mark.asyncio
async def test_vincular_quem_nao_e_cliente_da_404(db, cliente_http):
    """A busca filtra `role == client`: técnico não entra em empresa."""
    g = await _grupo(db)
    c = await _empresa(db, g)
    tecnico = User(
        name="Tec",
        email=f"tec-{uuid.uuid4()}@x.com",
        password="x",
        role=UserRole.technician,
    )
    db.add(tecnico)
    await db.commit()
    await db.refresh(tecnico)

    resp = await cliente_http.post(
        f"/api/v1/groups/{g.id}/companies/{c.id}/clients", json={"user_id": str(tecnico.id)}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_desvincula_cliente(db, cliente_http):
    g = await _grupo(db)
    c = await _empresa(db, g)
    u = await _cliente(db, company_id=c.id)

    resp = await cliente_http.delete(f"/api/v1/groups/{g.id}/companies/{c.id}/clients/{u.id}")

    assert resp.status_code == 204
    await db.refresh(u)
    assert u.company_id is None


@pytest.mark.asyncio
async def test_desvincular_cliente_de_outra_empresa_da_404(db, cliente_http):
    g = await _grupo(db)
    c1 = await _empresa(db, g, name="Primeira")
    c2 = await _empresa(db, g, name="Segunda")
    u = await _cliente(db, company_id=c1.id)

    resp = await cliente_http.delete(f"/api/v1/groups/{g.id}/companies/{c2.id}/clients/{u.id}")

    assert resp.status_code == 404
    await db.refresh(u)
    assert u.company_id == c1.id


# ═══════════════════════════════════════════════════════════════
# delete_company — a desvinculação silenciosa
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_excluir_empresa_desvincula_clientes_em_silencio(db, cliente_http):
    """
    **O comportamento que ninguém escolheu.** Excluir a empresa não é
    bloqueado nem deixa FK órfã: o cliente sobrevive com `company_id` nulo,
    o `204` não diz quantos foram soltos, e `_company_client_count` — que
    existe e é exibido na listagem — não é consultado na exclusão.

    Comprovado antes em Postgres efêmero (levantamento de 24/08) e reproduzido
    aqui. O teste não aprova a regra; **fixa** para que mudá-la seja decisão.
    """
    g = await _grupo(db)
    c = await _empresa(db, g)
    u1 = await _cliente(db, name="Um", company_id=c.id)
    u2 = await _cliente(db, name="Dois", company_id=c.id)

    resp = await cliente_http.delete(f"/api/v1/groups/{g.id}/companies/{c.id}")

    # O silêncio é o próprio 204: não bloqueia (409) e não informa (200 com
    # contagem). Não se afirma corpo vazio — isso o 204 já garante, e seria
    # asserção tautológica: verificado por mutação, um corpo devolvido aqui
    # continuava passando.
    assert resp.status_code == 204

    for u in (u1, u2):
        await db.refresh(u)
        assert u.company_id is None, "cliente desvinculado, não apagado"

    assert (
        await db.execute(select(Company).where(Company.id == c.id))
    ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_excluir_empresa_apaga_as_notas_da_empresa(db, cliente_http):
    """
    Diferente dos clientes: `CompanyNote` tem `cascade="all, delete-orphan"`,
    então some junto. A assimetria é de propósito e vale registrar — nota é
    da empresa, cliente não é.
    """
    g = await _grupo(db)
    c = await _empresa(db, g)
    admin = (await db.execute(select(User).where(User.role == UserRole.admin))).scalars().first()
    nota = CompanyNote(company_id=c.id, author_id=admin.id, content="interna")
    db.add(nota)
    await db.commit()
    nota_id = nota.id

    resp = await cliente_http.delete(f"/api/v1/groups/{g.id}/companies/{c.id}")

    assert resp.status_code == 204
    assert (
        await db.execute(select(CompanyNote).where(CompanyNote.id == nota_id))
    ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_cliente_desvinculado_volta_a_aparecer_como_sugestao(db, cliente_http):
    """
    O que salva parcialmente a exclusão silenciosa: `cnpj` e `company_name` do
    cliente sobrevivem, então ele reaparece em `/companies/suggestions`. O
    sistema meio que se autocura — mas em silêncio, e alimentando o bug de
    empresa duplicada, porque criar a empresa pela sugestão não vincula
    ninguém (defeito 1 do levantamento).
    """
    g = await _grupo(db)
    c = await _empresa(db, g, name="Acme", cnpj=CNPJ_DIGITOS)
    await _cliente(db, company_id=c.id, company_name="Acme", cnpj=CNPJ_DIGITOS)

    antes = await cliente_http.get("/api/v1/companies/suggestions")
    assert antes.json() == [], "vinculado não é sugestão"

    await cliente_http.delete(f"/api/v1/groups/{g.id}/companies/{c.id}")

    depois = await cliente_http.get("/api/v1/companies/suggestions")
    assert [s["company_name"] for s in depois.json()] == ["Acme"]


# ═══════════════════════════════════════════════════════════════
# get_company_suggestions — o agrupamento pela tupla inteira
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sugestao_agrupa_clientes_da_mesma_empresa(db, cliente_http):
    for nome in ("Um", "Dois"):
        await _cliente(db, name=nome, company_name="Acme", cnpj=CNPJ_DIGITOS, company_city="Recife")

    resp = await cliente_http.get("/api/v1/companies/suggestions")

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["client_count"] == 2


@pytest.mark.asyncio
async def test_sugestao_racha_em_duas_quando_o_endereco_diverge(db, cliente_http):
    """
    **Defeito 2 do levantamento.** O `GROUP BY` é pela tupla inteira, endereço
    incluído, então dois funcionários da mesma empresa que digitaram o
    endereço diferente viram duas sugestões — mesmo com o CNPJ idêntico, que é
    a única coisa que identifica a empresa de verdade.
    """
    await _cliente(
        db, name="Um", company_name="Acme", cnpj=CNPJ_DIGITOS, company_address="Rua A, 10"
    )
    await _cliente(
        db,
        name="Dois",
        company_name="Acme",
        cnpj=CNPJ_DIGITOS,
        company_address="Rua A, 10 - sala 2",
    )

    resp = await cliente_http.get("/api/v1/companies/suggestions")

    sugestoes = resp.json()
    assert len(sugestoes) == 2, "mesmo CNPJ, endereços diferentes: racha em duas"
    assert {s["cnpj"] for s in sugestoes} == {CNPJ_DIGITOS}
    assert all(s["client_count"] == 1 for s in sugestoes)


@pytest.mark.asyncio
async def test_sugestao_ignora_cliente_ja_vinculado(db, cliente_http):
    g = await _grupo(db)
    c = await _empresa(db, g, name="Acme")
    await _cliente(db, company_name="Acme", cnpj=CNPJ_DIGITOS, company_id=c.id)

    resp = await cliente_http.get("/api/v1/companies/suggestions")
    assert resp.json() == []


@pytest.mark.asyncio
async def test_sugestao_ignora_cliente_inativo(db, cliente_http):
    await _cliente(
        db,
        company_name="Acme",
        cnpj=CNPJ_DIGITOS,
        status=UserStatus.inactive,
    )

    resp = await cliente_http.get("/api/v1/companies/suggestions")
    assert resp.json() == []


@pytest.mark.asyncio
async def test_lista_clientes_sem_empresa(db, cliente_http):
    g = await _grupo(db)
    c = await _empresa(db, g)
    await _cliente(db, name="Solto")
    await _cliente(db, name="Vinculado", company_id=c.id)

    resp = await cliente_http.get("/api/v1/clients/unassigned")

    assert resp.status_code == 200
    assert [u["name"] for u in resp.json()] == ["Solto"]


@pytest.mark.asyncio
async def test_detalhe_da_empresa_traz_clientes_e_contagem(db, cliente_http):
    g = await _grupo(db)
    c = await _empresa(db, g, name="Acme")
    await _cliente(db, name="Um", company_id=c.id)
    await _cliente(db, name="Dois", company_id=c.id)

    resp = await cliente_http.get(f"/api/v1/groups/{g.id}/companies/{c.id}")

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["client_count"] == 2
    assert sorted(u["name"] for u in corpo["clients"]) == ["Dois", "Um"]


@pytest.mark.asyncio
async def test_data_de_criacao_da_empresa_e_preenchida(db, cliente_http):
    """Guarda contra `server_default` que não roda: o response exige a data."""
    g = await _grupo(db)
    resp = await cliente_http.post(f"/api/v1/groups/{g.id}/companies", json={"name": "Acme"})
    assert resp.status_code == 201
    criada = datetime.fromisoformat(resp.json()["created_at"])
    # O SQLite devolve naive; o Postgres, com fuso. O que importa é existir.
    agora = datetime.now(UTC) if criada.tzinfo else datetime.now(UTC).replace(tzinfo=None)
    assert criada <= agora


# ═══════════════════════════════════════════════════════════════
# POST /companies/from-suggestion — o laço que se fecha (Passo 3B)
# ═══════════════════════════════════════════════════════════════
#
# Criar empresa a partir de uma sugestão passava a NÃO vincular ninguém: os
# clientes que geraram o card seguiam com `company_id` nulo, a sugestão
# reaparecia e clicar de novo criava empresa duplicada. O contador "3 clientes"
# era uma promessa que a ação não cumpria.
#
# O vínculo é pela lista EXPLÍCITA que o admin confirmou, não por uma consulta
# que o servidor refaz: o que a tela mostrou é o que é gravado, e ninguém
# vincula em massa um conjunto que não viu.


async def _sugestao_body(clientes, **over):
    corpo = {
        "name": "Acme",
        "cnpj": CNPJ_DIGITOS,
        "client_ids": [str(u.id) for u in clientes],
    }
    corpo.update(over)
    return corpo


@pytest.mark.asyncio
async def test_criar_da_sugestao_cria_a_empresa_e_vincula_os_clientes(db, cliente_http):
    g = await _grupo(db)
    u1 = await _cliente(db, name="Um", company_name="Acme", cnpj=CNPJ_DIGITOS)
    u2 = await _cliente(db, name="Dois", company_name="Acme", cnpj=CNPJ_DIGITOS)

    resp = await cliente_http.post(
        f"/api/v1/groups/{g.id}/companies/from-suggestion",
        json=await _sugestao_body([u1, u2]),
    )

    assert resp.status_code == 201
    corpo = resp.json()
    assert corpo["company_created"] is True
    assert corpo["company"]["cnpj"] == CNPJ_DIGITOS
    assert sorted(c["name"] for c in corpo["linked_clients"]) == ["Dois", "Um"]

    for u in (u1, u2):
        await db.refresh(u)
        assert u.company_id is not None


@pytest.mark.asyncio
async def test_a_sugestao_some_depois_de_criada(db, cliente_http):
    """O defeito original: a sugestão reaparecia porque ninguém era vinculado."""
    g = await _grupo(db)
    u = await _cliente(db, company_name="Acme", cnpj=CNPJ_DIGITOS)

    await cliente_http.post(
        f"/api/v1/groups/{g.id}/companies/from-suggestion", json=await _sugestao_body([u])
    )

    assert (await cliente_http.get("/api/v1/companies/suggestions")).json() == []


@pytest.mark.asyncio
async def test_clicar_de_novo_reusa_a_empresa_em_vez_de_duplicar(db, cliente_http):
    """
    O bug da empresa duplicada. `Company.group_id` é **NOT NULL e único**, então
    reuso é sempre dentro do grupo: reaproveitar empresa de outro grupo seria
    *mudá-la de grupo*, não reutilizá-la.
    """
    g = await _grupo(db)
    u1 = await _cliente(db, name="Um", company_name="Acme", cnpj=CNPJ_DIGITOS)
    u2 = await _cliente(db, name="Dois", company_name="Acme", cnpj=CNPJ_DIGITOS)

    r1 = await cliente_http.post(
        f"/api/v1/groups/{g.id}/companies/from-suggestion", json=await _sugestao_body([u1])
    )
    r2 = await cliente_http.post(
        f"/api/v1/groups/{g.id}/companies/from-suggestion", json=await _sugestao_body([u2])
    )

    assert r1.json()["company_created"] is True
    assert r2.json()["company_created"] is False
    assert r1.json()["company"]["id"] == r2.json()["company"]["id"]

    empresas = (await db.execute(select(Company).where(Company.group_id == g.id))).scalars().all()
    assert len(empresas) == 1, "clicar duas vezes não pode criar duas empresas"


@pytest.mark.asyncio
async def test_empresa_de_mesmo_cnpj_em_outro_grupo_nao_e_reusada(db, cliente_http):
    """Reusar cruzando grupo mudaria a empresa de grupo — não é reuso."""
    g1 = await _grupo(db, "G1")
    g2 = await _grupo(db, "G2")
    await _empresa(db, g1, name="Acme", cnpj=CNPJ_DIGITOS)
    u = await _cliente(db, company_name="Acme", cnpj=CNPJ_DIGITOS)

    resp = await cliente_http.post(
        f"/api/v1/groups/{g2.id}/companies/from-suggestion", json=await _sugestao_body([u])
    )

    assert resp.status_code == 201
    assert resp.json()["company_created"] is True
    assert resp.json()["company"]["group_id"] == str(g2.id)


@pytest.mark.asyncio
async def test_recusa_vincular_cliente_que_ja_tem_empresa(db, cliente_http):
    """
    O caso TOCTOU: o admin viu a lista, outra pessoa vinculou o cliente antes
    do clique. `409` porque é conflito de estado, não corpo malformado — e
    **nada** é gravado, nem a empresa.
    """
    g = await _grupo(db)
    outra = await _empresa(db, g, name="Outra")
    u = await _cliente(db, company_name="Acme", cnpj=CNPJ_DIGITOS, company_id=outra.id)

    resp = await cliente_http.post(
        f"/api/v1/groups/{g.id}/companies/from-suggestion", json=await _sugestao_body([u])
    )

    assert resp.status_code == 409
    await db.refresh(u)
    assert u.company_id == outra.id, "o vínculo antigo fica intacto"
    nomes = (await db.execute(select(Company.name).where(Company.group_id == g.id))).scalars().all()
    assert nomes == ["Outra"], "a empresa nova não pode ter sido criada"


@pytest.mark.asyncio
async def test_recusa_vincular_quem_nao_e_cliente(db, cliente_http):
    g = await _grupo(db)
    tecnico = User(
        name="Tec", email=f"tec-{uuid.uuid4()}@x.com", password="x", role=UserRole.technician
    )
    db.add(tecnico)
    await db.commit()
    await db.refresh(tecnico)

    resp = await cliente_http.post(
        f"/api/v1/groups/{g.id}/companies/from-suggestion", json=await _sugestao_body([tecnico])
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_recusa_lista_vazia(db, cliente_http):
    """O endpoint serve para vincular; sem ninguém, o caminho é o create normal."""
    g = await _grupo(db)
    resp = await cliente_http.post(
        f"/api/v1/groups/{g.id}/companies/from-suggestion",
        json={"name": "Acme", "cnpj": CNPJ_DIGITOS, "client_ids": []},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_grupo_inexistente_da_404(db, cliente_http):
    u = await _cliente(db, company_name="Acme", cnpj=CNPJ_DIGITOS)
    resp = await cliente_http.post(
        f"/api/v1/groups/{uuid.uuid4()}/companies/from-suggestion",
        json=await _sugestao_body([u]),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sugestao_traz_os_clientes_para_o_admin_conferir(db, cliente_http):
    """
    A prévia. Vincular em massa sem ver quem é a ação que ninguém desfaz, e o
    `client_count` sozinho é um número sem nomes.
    """
    await _cliente(db, name="Um", company_name="Acme", cnpj=CNPJ_DIGITOS)
    await _cliente(db, name="Dois", company_name="Acme", cnpj=CNPJ_DIGITOS)

    resp = await cliente_http.get("/api/v1/companies/suggestions")

    sugestao = resp.json()[0]
    assert sugestao["client_count"] == 2
    assert sorted(c["name"] for c in sugestao["clients"]) == ["Dois", "Um"]
