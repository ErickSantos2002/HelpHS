"""
Listagem e detalhe de empresas da equipe (`GET /companies`, `GET /companies/{id}`)
contra PostgreSQL.

O que precisa de banco de verdade: que a busca por CNPJ ignore a pontuação dos
dois lados (o CNPJ das empresas antigas nunca foi normalizado em produção), que
as contagens venham do vínculo OFICIAL (`users.company_id`) e nunca do nome que
o cliente digitou, e que a contagem de equipamentos bata com o que
`GET /equipments?company_id=` devolve — as duas telas não podem discordar.
"""

import uuid

import pytest
from sqlalchemy import event

from app.models.models import Company, Group, UserRole
from tests import test_equipamentos_staff_postgres as _base
from tests.test_equipamentos_staff_postgres import _aparelho, _get, _Parque, _usuario

# As fixtures de banco real são as da tela de Equipamentos. Atribuídas, e não
# importadas pelo nome — mesmo motivo do `test_anexos_zip.py`: o import direto
# faz o ruff ler cada parâmetro `db` como redefinição (F811).
url_do_banco = _base.url_do_banco
db = _base.db
_limpa_overrides = _base._limpa_overrides


class _Empresas(_Parque):
    """O parque da Fase B, mais um segundo grupo e uma empresa sem ninguém."""

    def __init__(self) -> None:
        super().__init__()
        self.alfa.cnpj = "11.222.333/0001-81"  # pontuada: dado antigo, não normalizado
        self.beta.cnpj = "44555666000177"
        self.grupo_sul = Group(id=uuid.uuid4(), name="Grupo Sul")
        self.vazia = Company(
            id=uuid.uuid4(), group_id=self.grupo_sul.id, name="Gama Vazia", cnpj=None
        )
        # Nome com dígito: não pode virar busca por CNPJ.
        self.filial = Company(
            id=uuid.uuid4(),
            group_id=self.grupo_sul.id,
            name="Filial 2 Norte",
            cnpj="99888777000166",
        )

    async def grava(self, db) -> "_Empresas":
        db.add(self.grupo_sul)
        await super().grava(db)
        db.add_all([self.vazia, self.filial])
        await db.flush()
        return self


def _nomes(resp) -> list[str]:
    return [i["name"] for i in resp.json()["items"]]


def _item(resp, nome):
    return next(i for i in resp.json()["items"] if i["name"] == nome)


# ── Quem pode ─────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", ["tecnico", "admin"])
async def test_equipe_lista_as_empresas_de_todos_os_grupos(db, papel):
    e = await _Empresas().grava(db)
    ator = e.tecnico if papel == "tecnico" else e.admin

    resp = await _get(db, ator, "/companies")

    assert resp.status_code == 200, resp.text
    assert _nomes(resp) == ["Alfa Transportes", "Beta Logística", "Filial 2 Norte", "Gama Vazia"]
    assert resp.json()["total"] == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("caminho", ["/companies", "/companies/{alfa}"])
async def test_cliente_recebe_403_na_lista_e_no_detalhe(db, caminho):
    """Nem a própria empresa: o cliente não lista empresas nem vê colegas."""
    e = await _Empresas().grava(db)

    resp = await _get(db, e.maria, caminho.format(alfa=e.alfa.id))

    assert resp.status_code == 403
    assert "Alfa" not in resp.text
    assert "João" not in resp.text and "Pedro" not in resp.text


# ── Paginação, busca e filtro ─────────────────────────────────


@pytest.mark.asyncio
async def test_paginas_nao_repetem_nem_perdem_empresa(db):
    e = await _Empresas().grava(db)

    p1 = await _get(db, e.tecnico, "/companies", limit=3, offset=0)
    p2 = await _get(db, e.tecnico, "/companies", limit=3, offset=3)

    assert p1.json()["total"] == p2.json()["total"] == 4
    assert _nomes(p1) + _nomes(p2) == [
        "Alfa Transportes",
        "Beta Logística",
        "Filial 2 Norte",
        "Gama Vazia",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "termo, esperado",
    [
        ("beta", ["Beta Logística"]),
        ("11.222.333/0001-81", ["Alfa Transportes"]),  # pontuado, contra dado pontuado
        ("11222333000181", ["Alfa Transportes"]),  # só dígitos, contra dado pontuado
        ("555.666", ["Beta Logística"]),  # trecho pontuado, contra dado só dígitos
        ("Filial 2", ["Filial 2 Norte"]),  # nome com dígito: não é busca por CNPJ
    ],
    ids=["nome", "cnpj-pontuado", "cnpj-digitos", "cnpj-trecho", "nome-com-digito"],
)
async def test_busca_por_nome_e_cnpj(db, termo, esperado):
    e = await _Empresas().grava(db)

    resp = await _get(db, e.tecnico, "/companies", search=termo)

    assert resp.status_code == 200, resp.text
    assert _nomes(resp) == esperado


@pytest.mark.asyncio
async def test_filtro_de_grupo(db):
    e = await _Empresas().grava(db)

    resp = await _get(db, e.tecnico, "/companies", group_id=str(e.grupo_sul.id))

    assert _nomes(resp) == ["Filial 2 Norte", "Gama Vazia"]
    assert {i["group_name"] for i in resp.json()["items"]} == {"Grupo Sul"}


# ── Contagens: só o vínculo oficial ───────────────────────────


@pytest.mark.asyncio
async def test_linha_traz_grupo_e_contagens_do_vinculo_oficial(db):
    """O Pedro DIGITOU "Alfa Transportes": não conta como cliente nem como aparelho da Alfa."""
    e = await _Empresas().grava(db)

    resp = await _get(db, e.tecnico, "/companies")
    alfa = _item(resp, "Alfa Transportes")
    vazia = _item(resp, "Gama Vazia")

    assert alfa["group_id"] == str(e.grupo.id) and alfa["group_name"] == "Grupo Norte"
    assert alfa["client_count"] == 1
    assert alfa["equipment_count"] == 1
    assert vazia["client_count"] == 0 and vazia["equipment_count"] == 0


@pytest.mark.asyncio
async def test_contagem_de_equipamentos_bate_com_a_tela_de_equipamentos(db):
    """Inativo também conta: a lista de equipamentos sem filtro de status traz os dois."""
    e = await _Empresas().grava(db)
    db.add(_aparelho(e.titan, "Titan desativado da Maria", responsavel=e.maria, ativo=False))
    await db.flush()

    empresas = await _get(db, e.tecnico, "/companies")
    equipamentos = await _get(db, e.tecnico, "/equipments", company_id=str(e.alfa.id))

    assert _item(empresas, "Alfa Transportes")["equipment_count"] == 2
    assert equipamentos.json()["total"] == 2


@pytest.mark.asyncio
async def test_numero_de_consultas_nao_cresce_com_a_pagina(db):
    e = await _Empresas().grava(db)
    motor = db.bind.sync_engine
    contagem = {"n": 0}

    def _conta(*_args, **_kwargs):
        contagem["n"] += 1

    event.listen(motor, "before_cursor_execute", _conta)
    try:
        contagem["n"] = 0
        await _get(db, e.tecnico, "/companies", limit=1)
        uma = contagem["n"]
        contagem["n"] = 0
        await _get(db, e.tecnico, "/companies", limit=4)
        quatro = contagem["n"]
    finally:
        event.remove(motor, "before_cursor_execute", _conta)

    assert quatro == uma, (uma, quatro)


# ── Detalhe ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detalhe_traz_grupo_clientes_vinculados_e_contagens(db):
    e = await _Empresas().grava(db)
    colega = _usuario(UserRole.client, "Ana Colega", empresa=e.alfa)
    db.add(colega)
    await db.flush()

    resp = await _get(db, e.admin, f"/companies/{e.alfa.id}")

    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    assert corpo["name"] == "Alfa Transportes"
    assert corpo["group_name"] == "Grupo Norte"
    assert [c["name"] for c in corpo["clients"]] == ["Ana Colega", "Maria Souza"]
    assert corpo["client_count"] == 2
    assert corpo["equipment_count"] == 1
    # Quem só DIGITOU o nome da empresa não aparece entre os vinculados.
    assert "Pedro" not in resp.text


@pytest.mark.asyncio
async def test_detalhe_de_empresa_sem_clientes(db):
    e = await _Empresas().grava(db)

    resp = await _get(db, e.tecnico, f"/companies/{e.vazia.id}")

    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    assert corpo["clients"] == [] and corpo["client_count"] == 0
    assert corpo["equipment_count"] == 0
    assert corpo["group_name"] == "Grupo Sul"


@pytest.mark.asyncio
async def test_detalhe_de_empresa_inexistente_e_404(db):
    e = await _Empresas().grava(db)

    resp = await _get(db, e.tecnico, f"/companies/{uuid.uuid4()}")

    assert resp.status_code == 404


# ── Regressão do que já existia ───────────────────────────────


@pytest.mark.asyncio
async def test_sugestoes_continuam_respondendo(db):
    """`/companies/suggestions` vem antes de `/companies/{id}`: senão viraria 422."""
    e = await _Empresas().grava(db)

    resp = await _get(db, e.tecnico, "/companies/suggestions")

    assert resp.status_code == 200, resp.text
    # O Pedro declarou empresa e não tem vínculo: é exatamente uma sugestão.
    assert any(s["company_name"] == "Alfa Transportes" for s in resp.json())


@pytest.mark.asyncio
async def test_detalhe_por_grupo_continua_igual(db):
    e = await _Empresas().grava(db)

    resp = await _get(db, e.tecnico, f"/groups/{e.grupo.id}/companies/{e.alfa.id}")

    assert resp.status_code == 200, resp.text
    assert [c["name"] for c in resp.json()["clients"]] == ["Maria Souza"]
