"""
Equipamento compartilhado por empresa (ECE-01, Fase 2) — contra PostgreSQL real.

O que se prova aqui
-------------------
1. **A matriz de quem enxerga o quê**, com `EQUIPAMENTO_POR_EMPRESA` ligada:
   o cliente vê o que é dele (ativo ou não, com empresa ou sem) e o ATIVO da
   empresa oficial dele. Não vê o de outra empresa, o sem empresa de outra
   pessoa, o inativo do colega. A mesma matriz roda na listagem, na listagem
   por produto, no detalhe, na condição SQL e no predicado — os cinco têm de
   concordar.
2. **Com a flag desligada nada muda**: só o dono, nos mesmos caminhos.
3. **O responsável não aparece** para o colega: nem id, nem nome, nem e-mail,
   nem a empresa e o CNPJ que ele declarou. Nem por filtro, nem por contagem,
   nem pelo corpo do 404.
4. **Ver não é alterar**: editar e inativar continuam só com o responsável.
5. **Usar em chamado** segue a mesma regra de enxergar — e **não compartilha
   chamado**: quem usa o aparelho do colega não vê os chamados dele, nem ele os
   seus, nem pela busca por número de série.
6. **A Helô** só recebe o histórico de chamados do próprio cliente (flag
   ligada). Desligada, o recorte continua o de antes — registrado como achado.
7. **As telas da equipe** passam a filtrar e contar pela empresa do
   equipamento, mostrando as duas empresas lado a lado.
8. **Concorrência**: o vínculo empresarial e o estado do aparelho valem no
   momento do commit do chamado, não no da leitura.

Banco, ajudantes e o jeito de forçar a corrida vêm de
`test_empresa_do_equipamento_postgres.py`.
"""

import asyncio
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update

from app.core.config import get_settings
from app.models.models import (
    Equipment,
    Ticket,
    TicketCategory,
    User,
    UserRole,
    ticket_equipments,
)
from app.services.escopo_de_equipamento import cliente_enxerga, escopo_do_cliente
from tests import test_empresa_do_equipamento_postgres as _fase1
from tests.test_empresa_do_equipamento_postgres import (
    _aparelho,
    _cliente_inativa,
    _corrida,
    _desvincula,
    _empresa,
    _empresa_do,
    _equipe_edita,
    _grupo,
    _pessoa,
    _produto,
    _roda,
    _vincula,
)

# As fixtures da Fase 1, por atribuição: importadas pelo nome, o parâmetro de
# cada teste as redefiniria aos olhos do linter.
url_do_banco = _fase1.url_do_banco
fabrica = _fase1.fabrica
http = _fase1.http

_NAO_ENCONTRADO = {"detail": "Equipment not found"}
_OCULTOS = ("owner_id", "owner_name", "owner_email", "company_name", "company_cnpj")


@pytest.fixture
def ligada(monkeypatch):
    monkeypatch.setattr(get_settings(), "equipamento_por_empresa", True)


@pytest.fixture
def desligada(monkeypatch):
    monkeypatch.setattr(get_settings(), "equipamento_por_empresa", False)


async def _cenario(fabrica) -> dict:
    """Duas empresas, quatro clientes e um aparelho para cada linha da matriz.

    `ator` e `colega` são da empresa X; `estranho`, da Y; `solto` não tem
    vínculo. Tudo no mesmo produto, para a listagem por produto ver o conjunto
    inteiro.
    """
    g = await _grupo(fabrica)
    x = await _empresa(fabrica, g, "Empresa X")
    y = await _empresa(fabrica, g, "Empresa Y")
    ator = await _pessoa(fabrica, company_id=x.id)
    colega = await _pessoa(fabrica, company_id=x.id)
    estranho = await _pessoa(fabrica, company_id=y.id)
    solto = await _pessoa(fabrica)
    admin = await _pessoa(fabrica, UserRole.admin)
    tecnico = await _pessoa(fabrica, UserRole.technician)
    produto = await _produto(fabrica)

    async def novo(dono, empresa, ativo=True):
        return await _aparelho(
            fabrica, produto, dono=dono, company_id=empresa.id if empresa else None, ativo=ativo
        )

    aparelhos = {
        # ── do próprio ator: sempre visíveis, em qualquer estado
        "proprio_ativo": await novo(ator, x),
        "proprio_inativo": await novo(ator, x, ativo=False),
        "proprio_sem_empresa": await novo(ator, None),
        "proprio_em_y": await novo(ator, y),
        # ── da empresa X, de outra pessoa
        "colega_ativo": await novo(colega, x),
        "colega_inativo": await novo(colega, x, ativo=False),
        "sem_dono_em_x": await novo(None, x),
        # responsável mudou de empresa e o aparelho ficou em X: vale a do APARELHO
        "de_x_com_dono_em_y": await novo(estranho, x),
        # ── fora do alcance do ator
        "colega_sem_empresa": await novo(colega, None),
        "colega_por_decisao": await novo(colega, None),
        "colega_em_y": await novo(colega, y),
        "de_y": await novo(estranho, y),
        "de_y_inativo": await novo(estranho, y, ativo=False),
        "do_solto": await novo(solto, None),
        "sem_dono_sem_empresa": await novo(None, None),
    }
    await _roda(fabrica, _equipe_edita(admin, aparelhos["colega_por_decisao"], company_id=None))
    return {
        "x": x,
        "y": y,
        "ator": ator,
        "colega": colega,
        "estranho": estranho,
        "solto": solto,
        "admin": admin,
        "tecnico": tecnico,
        "produto": produto,
        **aparelhos,
    }


_APARELHOS = (
    "proprio_ativo",
    "proprio_inativo",
    "proprio_sem_empresa",
    "proprio_em_y",
    "colega_ativo",
    "colega_inativo",
    "sem_dono_em_x",
    "de_x_com_dono_em_y",
    "colega_sem_empresa",
    "colega_por_decisao",
    "colega_em_y",
    "de_y",
    "de_y_inativo",
    "do_solto",
    "sem_dono_sem_empresa",
)

_PROPRIOS = {"proprio_ativo", "proprio_inativo", "proprio_sem_empresa", "proprio_em_y"}
_DA_EMPRESA = {"colega_ativo", "sem_dono_em_x", "de_x_com_dono_em_y"}

# Quem enxerga o quê, com a flag LIGADA. Desligada, cada um vê só os próprios.
_VISIVEL = {
    "ator": _PROPRIOS | _DA_EMPRESA,
    "colega": {
        "colega_ativo",
        "colega_inativo",
        "colega_sem_empresa",
        "colega_por_decisao",
        "colega_em_y",
        "proprio_ativo",
        "sem_dono_em_x",
        "de_x_com_dono_em_y",
    },
    # Da empresa Y: os próprios e os ativos de Y, inclusive os cadastrados por
    # gente de X. O inativo `de_y_inativo` é dele, por isso aparece.
    "estranho": {"de_x_com_dono_em_y", "de_y", "de_y_inativo", "proprio_em_y", "colega_em_y"},
    # Sem vínculo: só o que cadastrou.
    "solto": {"do_solto"},
}
_SEUS = {
    "ator": _PROPRIOS,
    "colega": {
        "colega_ativo",
        "colega_inativo",
        "colega_sem_empresa",
        "colega_por_decisao",
        "colega_em_y",
    },
    "estranho": {"de_x_com_dono_em_y", "de_y", "de_y_inativo"},
    "solto": {"do_solto"},
}


def _nomes(c: dict, ids) -> set[str]:
    por_id = {str(c[nome].id): nome for nome in _APARELHOS}
    return {por_id[str(i)] for i in ids}


async def _minha_lista(http, quem) -> list[dict]:
    http.estado["ator"] = quem
    resp = await http.get("/api/v1/equipment/my")
    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    assert corpo["total"] == len(corpo["items"])
    return corpo["items"]


# ══════════════════════════════════════════════════════════════
# 1. A matriz, nos cinco lugares em que a regra é perguntada
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("quem", ["ator", "colega", "estranho", "solto"])
async def test_matriz_na_minha_lista(fabrica, http, ligada, quem):
    c = await _cenario(fabrica)

    itens = await _minha_lista(http, c[quem])

    assert _nomes(c, (i["id"] for i in itens)) == _VISIVEL[quem]
    assert _nomes(c, (i["id"] for i in itens if i["is_mine"])) == _SEUS[quem]


@pytest.mark.asyncio
@pytest.mark.parametrize("quem", ["ator", "colega", "estranho", "solto"])
async def test_matriz_na_listagem_por_produto_com_paginacao(fabrica, http, ligada, quem):
    """Página a página sai exatamente o conjunto visível, e o `total` é o dele —
    o contador não pode denunciar o que a lista esconde."""
    c = await _cenario(fabrica)
    http.estado["ator"] = c[quem]
    url = f"/api/v1/products/{c['produto'].id}/equipments"

    vistos: list[str] = []
    for offset in range(0, 20, 3):
        resp = await http.get(url, params={"limit": 3, "offset": offset})
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert corpo["total"] == len(_VISIVEL[quem])
        vistos += [i["id"] for i in corpo["items"]]

    assert len(vistos) == len(set(vistos))
    assert _nomes(c, vistos) == _VISIVEL[quem]


@pytest.mark.asyncio
@pytest.mark.parametrize("quem", ["ator", "colega", "estranho", "solto"])
async def test_matriz_no_detalhe_e_a_recusa_e_o_404_do_id_inexistente(fabrica, http, ligada, quem):
    c = await _cenario(fabrica)
    http.estado["ator"] = c[quem]
    inexistente = await http.get(f"/api/v1/equipments/{uuid.uuid4()}")
    assert (inexistente.status_code, inexistente.json()) == (404, _NAO_ENCONTRADO)

    for nome in _APARELHOS:
        resp = await http.get(f"/api/v1/equipments/{c[nome].id}")
        if nome in _VISIVEL[quem]:
            assert resp.status_code == 200, f"{quem} deveria abrir {nome}"
            assert resp.json()["is_mine"] is (nome in _SEUS[quem])
        else:
            assert resp.status_code == 404, f"{quem} não deveria abrir {nome}"
            assert resp.json() == inexistente.json(), "a recusa não pode diferir do id inexistente"
            assert resp.headers.keys() == inexistente.headers.keys()


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", [False, True])
async def test_a_condicao_sql_e_o_predicado_dizem_a_mesma_coisa(fabrica, monkeypatch, flag):
    """A regra existe duas vezes (WHERE e predicado); aqui elas são comparadas."""
    monkeypatch.setattr(get_settings(), "equipamento_por_empresa", flag)
    c = await _cenario(fabrica)

    for quem in ("ator", "colega", "estranho", "solto"):
        pessoa = c[quem]
        async with fabrica() as s:
            pelo_sql = set(
                (
                    await s.execute(
                        select(Equipment.id).where(escopo_do_cliente(pessoa.id, pessoa.company_id))
                    )
                ).scalars()
            )
            todos = (await s.execute(select(Equipment))).scalars().all()
        pelo_predicado = {e.id for e in todos if cliente_enxerga(e, pessoa.id, pessoa.company_id)}
        assert pelo_sql == pelo_predicado
        assert _nomes(c, pelo_sql) == (_VISIVEL[quem] if flag else _SEUS[quem])


# ══════════════════════════════════════════════════════════════
# 2. Com a flag desligada, nada muda
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("quem", ["ator", "colega", "estranho", "solto"])
async def test_com_a_flag_desligada_cada_um_ve_so_o_que_cadastrou(fabrica, http, desligada, quem):
    c = await _cenario(fabrica)

    itens = await _minha_lista(http, c[quem])
    por_produto = await http.get(f"/api/v1/products/{c['produto'].id}/equipments?limit=100")

    assert _nomes(c, (i["id"] for i in itens)) == _SEUS[quem]
    assert _nomes(c, (i["id"] for i in por_produto.json()["items"])) == _SEUS[quem]
    assert por_produto.json()["total"] == len(_SEUS[quem])
    assert all(i["is_mine"] is True for i in itens)
    assert all(i["owner_id"] == str(c[quem].id) for i in itens)
    for nome in _APARELHOS:
        resp = await http.get(f"/api/v1/equipments/{c[nome].id}")
        assert resp.status_code == (200 if nome in _SEUS[quem] else 404), nome
        if resp.status_code == 404:
            assert resp.json() == _NAO_ENCONTRADO


@pytest.mark.asyncio
async def test_com_a_flag_desligada_o_colega_nao_usa_o_aparelho_em_chamado(fabrica, desligada):
    c = await _cenario(fabrica)

    with pytest.raises(HTTPException) as recusa:
        await _roda(fabrica, _abre_chamado(c["ator"], [c["colega_ativo"].id]))

    assert recusa.value.status_code == 403
    assert recusa.value.detail == "Só é possível vincular equipamentos que pertencem a você."


# ══════════════════════════════════════════════════════════════
# 3. O responsável não aparece para o colega
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_o_colega_nao_recebe_nenhum_dado_do_responsavel(fabrica, http, ligada):
    c = await _cenario(fabrica)
    # O responsável tem empresa e CNPJ DECLARADOS — é o que a listagem por
    # produto devolvia junto do aparelho.
    async with fabrica() as s:
        colega = await s.get(type(c["colega"]), c["colega"].id)
        colega.company_name = "Declarada Ltda"
        colega.cnpj = "11222333000181"
        await s.commit()
    http.estado["ator"] = c["ator"]
    alvo = str(c["colega_ativo"].id)
    segredos = (
        str(c["colega"].id),
        c["colega"].name,
        c["colega"].email,
        "Declarada Ltda",
        "11222333000181",
    )

    respostas = [
        await http.get("/api/v1/equipment/my"),
        await http.get(f"/api/v1/products/{c['produto'].id}/equipments?limit=100"),
        await http.get(f"/api/v1/equipments/{alvo}"),
    ]

    for resp in respostas:
        assert resp.status_code == 200, resp.text
        for segredo in segredos:
            assert segredo not in resp.text, f"{segredo!r} vazou em {resp.request.url}"
        corpo = resp.json()
        itens = corpo["items"] if "items" in corpo else [corpo]
        [do_colega] = [i for i in itens if i["id"] == alvo]
        assert do_colega["is_mine"] is False
        for campo in _OCULTOS:
            assert do_colega[campo] is None, campo
        # A empresa oficial também não é lida pelo cliente em lugar nenhum.
        for campo in ("linked_company_id", "equipment_company_id", "equipment_company_name"):
            assert do_colega[campo] is None, campo


@pytest.mark.asyncio
async def test_o_que_e_do_proprio_cliente_continua_saindo_inteiro(fabrica, http, ligada):
    c = await _cenario(fabrica)
    http.estado["ator"] = c["ator"]
    meu = str(c["proprio_ativo"].id)

    por_produto = await http.get(f"/api/v1/products/{c['produto'].id}/equipments?limit=100")
    detalhe = await http.get(f"/api/v1/equipments/{meu}")

    [item] = [i for i in por_produto.json()["items"] if i["id"] == meu]
    assert item["is_mine"] is True
    assert item["owner_id"] == str(c["ator"].id)
    assert item["owner_name"] == c["ator"].name
    assert item["owner_email"] == c["ator"].email
    assert detalhe.json()["owner_id"] == str(c["ator"].id)


@pytest.mark.asyncio
async def test_filtros_do_cliente_nao_revelam_o_que_o_escopo_esconde(fabrica, http, ligada):
    c = await _cenario(fabrica)
    http.estado["ator"] = c["ator"]
    url = f"/api/v1/products/{c['produto'].id}/equipments"

    inativos = await http.get(url, params={"is_active": "false", "limit": 100})
    meus_inativos = await http.get("/api/v1/equipment/my", params={"is_active": "false"})
    sem_dono = await http.get(url, params={"without_owner": "true", "limit": 100})
    pelo_nome_oculto = await http.get(
        url, params={"search": c["colega_inativo"].name, "limit": 100}
    )
    pelo_nome_de_y = await http.get(url, params={"search": c["de_y"].name, "limit": 100})

    # O inativo do colega não aparece nem pedindo inativos.
    assert _nomes(c, (i["id"] for i in inativos.json()["items"])) == {"proprio_inativo"}
    assert inativos.json()["total"] == 1
    assert _nomes(c, (i["id"] for i in meus_inativos.json()["items"])) == {"proprio_inativo"}
    # `sem_dono_em_x` é visível, mas o filtro não confirma que ele não tem dono.
    assert (sem_dono.json()["items"], sem_dono.json()["total"]) == ([], 0)
    for busca in (pelo_nome_oculto, pelo_nome_de_y):
        assert (busca.json()["items"], busca.json()["total"]) == ([], 0)


# ══════════════════════════════════════════════════════════════
# 4. Ver não é alterar
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("alvo", ["colega_ativo", "sem_dono_em_x", "de_x_com_dono_em_y", "de_y"])
async def test_o_colega_nao_edita_nem_inativa_o_que_enxerga(fabrica, http, ligada, alvo):
    c = await _cenario(fabrica)
    http.estado["ator"] = c["ator"]
    aparelho = c[alvo]
    inexistente = await http.patch(f"/api/v1/equipment/my/{uuid.uuid4()}", json={"name": "x"})

    edita = await http.patch(f"/api/v1/equipment/my/{aparelho.id}", json={"name": "Tomado"})
    inativa = await http.delete(f"/api/v1/equipment/my/{aparelho.id}")
    pela_rota_da_equipe = await http.patch(
        f"/api/v1/equipments/{aparelho.id}", json={"name": "Tomado"}
    )
    exclui_pela_equipe = await http.delete(f"/api/v1/equipments/{aparelho.id}")

    for resp in (edita, inativa):
        assert resp.status_code == 404
        assert resp.json() == inexistente.json() == _NAO_ENCONTRADO
    assert pela_rota_da_equipe.status_code == 403
    assert exclui_pela_equipe.status_code == 403
    async with fabrica() as s:
        agora = await s.get(Equipment, aparelho.id)
    assert (agora.name, agora.is_active, agora.owner_id) == (
        aparelho.name,
        True,
        aparelho.owner_id,
    )


@pytest.mark.asyncio
async def test_o_responsavel_continua_editando_e_inativando_o_proprio(fabrica, http, ligada):
    c = await _cenario(fabrica)
    http.estado["ator"] = c["colega"]

    edita = await http.patch(
        f"/api/v1/equipment/my/{c['colega_ativo'].id}", json={"name": "Renomeado"}
    )
    inativa = await http.delete(f"/api/v1/equipment/my/{c['colega_ativo'].id}")

    assert edita.status_code == 200 and edita.json()["is_mine"] is True
    assert inativa.status_code == 204
    # Inativado pelo dono, sai da vista do colega — e continua na do dono.
    assert "colega_ativo" not in _nomes(c, (i["id"] for i in await _minha_lista(http, c["ator"])))
    assert "colega_ativo" in _nomes(c, (i["id"] for i in await _minha_lista(http, c["colega"])))
    assert (await http.get(f"/api/v1/equipments/{c['colega_ativo'].id}")).status_code == 200
    http.estado["ator"] = c["ator"]
    assert (await http.get(f"/api/v1/equipments/{c['colega_ativo'].id}")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", [False, True])
async def test_o_cadastro_do_cliente_ja_responde_como_dele(fabrica, http, monkeypatch, flag):
    monkeypatch.setattr(get_settings(), "equipamento_por_empresa", flag)
    c = await _cenario(fabrica)
    http.estado["ator"] = c["ator"]

    resp = await http.post(
        f"/api/v1/equipment/my?product_id={c['produto'].id}",
        json={"name": "Recém-cadastrado", "serial_number": "SN-NOVO-1"},
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["is_mine"] is True
    assert resp.json()["owner_id"] == str(c["ator"].id)


@pytest.mark.asyncio
async def test_quem_sai_da_empresa_para_de_ver_e_quem_entra_passa_a_ver(fabrica, http, ligada):
    """O objeto do ator é o de ANTES da mudança, de propósito: quem decide é o
    vínculo comitado no banco, não o que a requisição carregou."""
    c = await _cenario(fabrica)

    await _roda(fabrica, _desvincula(c["admin"], c["x"], c["ator"]))
    depois_de_sair = await _minha_lista(http, c["ator"])
    await _roda(fabrica, _vincula(c["admin"], c["x"], c["solto"]))
    depois_de_entrar = await _minha_lista(http, c["solto"])

    assert _nomes(c, (i["id"] for i in depois_de_sair)) == _PROPRIOS
    # O aparelho do recém-vinculado ganhou a empresa X na propagação.
    assert _nomes(c, (i["id"] for i in depois_de_entrar)) == {
        "do_solto",
        "proprio_ativo",
        "colega_ativo",
        "sem_dono_em_x",
        "de_x_com_dono_em_y",
    }


@pytest.mark.asyncio
async def test_a_equipe_muda_a_empresa_do_aparelho_e_a_vista_acompanha(fabrica, http, ligada):
    c = await _cenario(fabrica)

    # Responsável alterado: o aparelho NÃO muda de empresa, e segue visível em X.
    await _roda(fabrica, _equipe_edita(c["tecnico"], c["colega_ativo"], owner_id=c["estranho"].id))
    assert "colega_ativo" in _nomes(c, (i["id"] for i in await _minha_lista(http, c["ator"])))
    # Empresa alterada pela equipe (técnico também pode): sai de X, entra em Y.
    await _roda(fabrica, _equipe_edita(c["tecnico"], c["colega_ativo"], company_id=c["y"].id))
    assert "colega_ativo" not in _nomes(c, (i["id"] for i in await _minha_lista(http, c["ator"])))
    # Sem empresa por decisão: ninguém além do responsável.
    await _roda(fabrica, _equipe_edita(c["admin"], c["sem_dono_em_x"], company_id=None))
    assert "sem_dono_em_x" not in _nomes(c, (i["id"] for i in await _minha_lista(http, c["ator"])))


# ══════════════════════════════════════════════════════════════
# 5. Usar em chamado — e chamado não é compartilhado
# ══════════════════════════════════════════════════════════════


def _abre_chamado(cliente, ids, titulo="Chamado de teste", comita=True):
    """O que `POST /tickets` faz com os equipamentos, sem o resto da rota."""
    from app.routers.tickets import _set_ticket_equipments

    async def operacao(s):
        chamado = Ticket(
            id=uuid.uuid4(),
            protocol=f"HS-T-{uuid.uuid4().hex[:8]}",
            title=titulo,
            description="Descrição do chamado de teste",
            category=next(iter(TicketCategory)),
            creator_id=cliente.id,
        )
        s.add(chamado)
        await _set_ticket_equipments(s, chamado, list(ids), cliente)
        if comita:
            await s.commit()
        return chamado.id

    return operacao


async def _aparelhos_do_chamado(fabrica, chamado_id) -> set[uuid.UUID]:
    async with fabrica() as s:
        return set(
            (
                await s.execute(
                    select(ticket_equipments.c.equipment_id).where(
                        ticket_equipments.c.ticket_id == chamado_id
                    )
                )
            ).scalars()
        )


@pytest.mark.asyncio
async def test_o_cliente_usa_em_chamado_exatamente_o_que_enxerga(fabrica, ligada):
    c = await _cenario(fabrica)

    for nome in _APARELHOS:
        operacao = _abre_chamado(c["ator"], [c[nome].id])
        if nome in _VISIVEL["ator"]:
            chamado = await _roda(fabrica, operacao)
            assert await _aparelhos_do_chamado(fabrica, chamado) == {c[nome].id}
        else:
            with pytest.raises(HTTPException) as recusa:
                await _roda(fabrica, operacao)
            assert recusa.value.status_code == 403, nome
            assert "a você ou à sua empresa" in recusa.value.detail


@pytest.mark.asyncio
async def test_um_aparelho_fora_do_escopo_derruba_o_pedido_inteiro(fabrica, ligada):
    c = await _cenario(fabrica)

    with pytest.raises(HTTPException) as recusa:
        await _roda(
            fabrica,
            _abre_chamado(c["ator"], [c["proprio_ativo"].id, c["colega_ativo"].id, c["de_y"].id]),
        )
    with pytest.raises(HTTPException) as inexistente:
        await _roda(fabrica, _abre_chamado(c["ator"], [c["colega_ativo"].id, uuid.uuid4()]))

    assert recusa.value.status_code == 403
    assert inexistente.value.status_code == 400, "id que não existe continua sendo 400"
    async with fabrica() as s:
        assert (await s.execute(select(Ticket))).scalars().all() == []


@pytest.mark.asyncio
async def test_usar_o_aparelho_do_colega_nao_compartilha_chamado(fabrica, http, ligada):
    c = await _cenario(fabrica)
    do_ator = await _roda(
        fabrica, _abre_chamado(c["ator"], [c["colega_ativo"].id], "Chamado do ator")
    )
    do_colega = await _roda(
        fabrica, _abre_chamado(c["colega"], [c["colega_ativo"].id], "Chamado do colega")
    )
    serie = c["colega_ativo"].serial_number

    async def ve(quem):
        http.estado["ator"] = quem
        lista = await http.get("/api/v1/tickets")
        busca = await http.get("/api/v1/tickets", params={"search": serie})
        assert lista.status_code == 200 and busca.status_code == 200, lista.text
        return (
            {i["id"] for i in lista.json()["items"]},
            {i["id"] for i in busca.json()["items"]},
            lista.json()["total"],
        )

    assert await ve(c["ator"]) == ({str(do_ator)}, {str(do_ator)}, 1)
    assert await ve(c["colega"]) == ({str(do_colega)}, {str(do_colega)}, 1)
    # E o detalhe do chamado alheio é o 404 do chamado que não existe.
    http.estado["ator"] = c["ator"]
    alheio = await http.get(f"/api/v1/tickets/{do_colega}")
    inexistente = await http.get(f"/api/v1/tickets/{uuid.uuid4()}")
    proprio = await http.get(f"/api/v1/tickets/{do_ator}")
    assert alheio.status_code == 404 and alheio.json() == inexistente.json()
    assert proprio.status_code == 200
    # O chamado próprio mostra o aparelho, e nada do responsável por ele.
    assert [e["id"] for e in proprio.json()["equipments"]] == [str(c["colega_ativo"].id)]
    for segredo in (str(c["colega"].id), c["colega"].name, c["colega"].email):
        assert segredo not in proprio.text


@pytest.mark.asyncio
async def test_pela_rota_de_verdade_o_chamado_nasce_com_o_aparelho_da_empresa(
    fabrica, http, ligada, monkeypatch
):
    """`POST /tickets` inteiro, e não só a função dos equipamentos: o chamado é
    serializado ANTES do flush, e uma consulta fora do `no_autoflush` no meio
    do caminho vira MissingGreenlet (500) — aconteceu durante esta entrega."""
    from unittest.mock import AsyncMock

    from app.routers import tickets as rota

    # Só o que sai do banco fica de fora: classificação por IA e notificações.
    for nome in ("classify_ticket", "notify_ticket_created"):
        if hasattr(rota, nome):
            monkeypatch.setattr(rota, nome, AsyncMock(return_value=None))
    c = await _cenario(fabrica)
    http.estado["ator"] = c["ator"]
    corpo = {"title": "Aparelho não liga", "description": "Parou ontem à tarde."}

    criado = await http.post(
        "/api/v1/tickets",
        json={**corpo, "equipment_ids": [str(c["colega_ativo"].id), str(c["proprio_ativo"].id)]},
    )
    recusado = await http.post(
        "/api/v1/tickets", json={**corpo, "equipment_ids": [str(c["de_y"].id)]}
    )
    inativo = await http.post(
        "/api/v1/tickets", json={**corpo, "equipment_ids": [str(c["colega_inativo"].id)]}
    )

    assert criado.status_code == 201, criado.text
    assert {e["id"] for e in criado.json()["equipments"]} == {
        str(c["colega_ativo"].id),
        str(c["proprio_ativo"].id),
    }
    for segredo in (str(c["colega"].id), c["colega"].name, c["colega"].email):
        assert segredo not in criado.text
    assert recusado.status_code == inativo.status_code == 403
    assert recusado.json() == inativo.json(), "a recusa não distingue o motivo"
    async with fabrica() as s:
        assert len((await s.execute(select(Ticket.id))).scalars().all()) == 1


# ══════════════════════════════════════════════════════════════
# 6. Um chamado, uma classificação de empresa
# ══════════════════════════════════════════════════════════════
#
# Com a flag ligada, os equipamentos de um chamado são todos da MESMA empresa
# ou todos ainda sem empresa — para o cliente e para a equipe, no `POST` e no
# `PATCH`. Para a equipe vale ainda a empresa de quem abriu o chamado.

_MISTURA = "todos da mesma empresa"


async def _troca_aparelhos(fabrica, admin, chamado_id, ids):
    """O que `PATCH /tickets/{id}` faz com os equipamentos."""
    from app.routers.tickets import _set_ticket_equipments

    async def operacao(s):
        chamado = (await s.execute(select(Ticket).where(Ticket.id == chamado_id))).scalar_one()
        await _set_ticket_equipments(s, chamado, list(ids), admin)
        await s.commit()

    await _roda(fabrica, operacao)


def _troca(admin, chamado_id, ids):
    from app.routers.tickets import _set_ticket_equipments

    async def operacao(s):
        chamado = (await s.execute(select(Ticket).where(Ticket.id == chamado_id))).scalar_one()
        await _set_ticket_equipments(s, chamado, list(ids), admin)
        await s.commit()

    return operacao


# (nomes dos aparelhos, quem abriu, esperado) — pela equipe, no chamado já aberto.
_PELA_EQUIPE = [
    # todos da empresa de quem abriu
    (("colega_ativo", "proprio_ativo", "colega_inativo"), "ator", "ok"),
    # todos sem empresa: pode, tenha ou não empresa quem abriu
    (("sem_dono_sem_empresa", "colega_sem_empresa", "do_solto"), "ator", "ok"),
    (("sem_dono_sem_empresa", "do_solto"), "solto", "ok"),
    # sem empresa POR DECISÃO também é "sem empresa"
    (("colega_por_decisao", "colega_sem_empresa"), "ator", "ok"),
    # duas empresas
    (("colega_ativo", "de_y"), "ator", 400),
    (("colega_ativo", "colega_em_y"), "solto", 400),
    # classificado junto de não classificado
    (("colega_ativo", "sem_dono_sem_empresa"), "ator", 400),
    (("de_y", "do_solto"), "solto", 400),
    (("colega_ativo", "colega_por_decisao"), "ator", 400),
    # uma empresa só, mas não a de quem abriu
    (("de_y", "colega_em_y"), "ator", 400),
    (("de_y",), "ator", 400),
    # quem abriu não tem empresa: qualquer empresa única serve
    (("de_y", "colega_em_y"), "solto", "ok"),
    # um só, da empresa de quem abriu
    (("sem_dono_em_x",), "ator", "ok"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("nomes", "quem_abriu", "esperado"), _PELA_EQUIPE)
async def test_a_equipe_associa_so_uma_classificacao_por_chamado(
    fabrica, ligada, nomes, quem_abriu, esperado
):
    c = await _cenario(fabrica)
    chamado = await _roda(fabrica, _abre_chamado(c[quem_abriu], []))
    ids = [c[n].id for n in nomes]

    if esperado == "ok":
        await _troca_aparelhos(fabrica, c["admin"], chamado, ids)
        assert await _aparelhos_do_chamado(fabrica, chamado) == set(ids)
    else:
        with pytest.raises(HTTPException) as recusa:
            await _troca_aparelhos(fabrica, c["admin"], chamado, ids)
        assert recusa.value.status_code == esperado
        assert _MISTURA in recusa.value.detail
        assert await _aparelhos_do_chamado(fabrica, chamado) == set()


@pytest.mark.asyncio
async def test_chamado_aberto_pela_equipe_segue_a_mesma_regra(fabrica, ligada):
    """Quem abriu é da equipe: não há empresa de quem abriu para comparar, e
    sobra a regra entre os equipamentos."""
    c = await _cenario(fabrica)

    for misturados in (("colega_ativo", "de_y"), ("colega_ativo", "sem_dono_sem_empresa")):
        with pytest.raises(HTTPException) as recusa:
            await _roda(fabrica, _abre_chamado(c["admin"], [c[n].id for n in misturados]))
        assert recusa.value.status_code == 400
    de_y = await _roda(fabrica, _abre_chamado(c["admin"], [c["de_y"].id, c["colega_em_y"].id]))
    sem_empresa = await _roda(
        fabrica, _abre_chamado(c["tecnico"], [c["do_solto"].id, c["sem_dono_sem_empresa"].id])
    )

    assert await _aparelhos_do_chamado(fabrica, de_y) == {c["de_y"].id, c["colega_em_y"].id}
    assert await _aparelhos_do_chamado(fabrica, sem_empresa) == {
        c["do_solto"].id,
        c["sem_dono_sem_empresa"].id,
    }
    async with fabrica() as s:
        assert len((await s.execute(select(Ticket.id))).scalars().all()) == 2


# (nomes, esperado) — pelo CLIENTE `ator` (empresa X), abrindo o chamado.
_PELO_CLIENTE = [
    (("proprio_ativo", "colega_ativo", "sem_dono_em_x"), "ok"),
    (("proprio_sem_empresa",), "ok"),
    # O dele continua sendo dele: mesmo classificado em Y, sozinho ele usa.
    (("proprio_em_y",), "ok"),
    (("proprio_ativo", "proprio_em_y"), 400),
    (("proprio_ativo", "proprio_sem_empresa"), 400),
    (("colega_ativo", "proprio_sem_empresa"), 400),
    # Fora do escopo vem ANTES da regra de empresa: 403, e não 400.
    (("proprio_ativo", "de_y"), 403),
    (("proprio_sem_empresa", "colega_sem_empresa"), 403),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("nomes", "esperado"), _PELO_CLIENTE)
async def test_o_cliente_tambem_nao_mistura_classificacoes(fabrica, ligada, nomes, esperado):
    c = await _cenario(fabrica)
    ids = [c[n].id for n in nomes]

    if esperado == "ok":
        chamado = await _roda(fabrica, _abre_chamado(c["ator"], ids))
        assert await _aparelhos_do_chamado(fabrica, chamado) == set(ids)
        return
    with pytest.raises(HTTPException) as recusa:
        await _roda(fabrica, _abre_chamado(c["ator"], ids))
    assert recusa.value.status_code == esperado
    assert (_MISTURA in recusa.value.detail) is (esperado == 400)
    async with fabrica() as s:
        assert (await s.execute(select(Ticket.id))).scalars().all() == []


@pytest.mark.asyncio
async def test_dois_aparelhos_proprios_sem_empresa_cabem_no_mesmo_chamado(fabrica, ligada):
    c = await _cenario(fabrica)
    outro = await _aparelho(fabrica, c["produto"], dono=c["ator"])

    chamado = await _roda(
        fabrica, _abre_chamado(c["ator"], [c["proprio_sem_empresa"].id, outro.id])
    )

    assert await _aparelhos_do_chamado(fabrica, chamado) == {c["proprio_sem_empresa"].id, outro.id}


@pytest.mark.asyncio
async def test_pelas_rotas_de_verdade_post_e_patch_recusam_a_mistura(
    fabrica, http, ligada, monkeypatch
):
    from unittest.mock import AsyncMock

    from app.routers import tickets as rota

    for nome in ("classify_ticket", "notify_ticket_created"):
        if hasattr(rota, nome):
            monkeypatch.setattr(rota, nome, AsyncMock(return_value=None))
    c = await _cenario(fabrica)
    corpo = {"title": "Aparelho não liga", "description": "Parou ontem à tarde."}

    # POST, pelo cliente
    http.estado["ator"] = c["ator"]
    misturado = await http.post(
        "/api/v1/tickets",
        json={
            **corpo,
            "equipment_ids": [str(c["proprio_ativo"].id), str(c["proprio_sem_empresa"].id)],
        },
    )
    criado = await http.post(
        "/api/v1/tickets", json={**corpo, "equipment_ids": [str(c["proprio_ativo"].id)]}
    )
    assert misturado.status_code == 400 and _MISTURA in misturado.json()["detail"]
    assert criado.status_code == 201, criado.text
    chamado = criado.json()["id"]

    # PATCH, pelo admin
    http.estado["ator"] = c["admin"]
    de_outra = await http.patch(
        f"/api/v1/tickets/{chamado}", json={"equipment_ids": [str(c["de_y"].id)]}
    )
    com_nao_classificado = await http.patch(
        f"/api/v1/tickets/{chamado}",
        json={"equipment_ids": [str(c["proprio_ativo"].id), str(c["do_solto"].id)]},
    )
    da_mesma = await http.patch(
        f"/api/v1/tickets/{chamado}",
        json={"equipment_ids": [str(c["proprio_ativo"].id), str(c["colega_inativo"].id)]},
    )

    for recusa in (de_outra, com_nao_classificado):
        assert recusa.status_code == 400, recusa.text
        assert _MISTURA in recusa.json()["detail"]
    assert da_mesma.status_code == 200, da_mesma.text
    assert await _aparelhos_do_chamado(fabrica, uuid.UUID(chamado)) == {
        c["proprio_ativo"].id,
        c["colega_inativo"].id,
    }
    async with fabrica() as s:
        assert len((await s.execute(select(Ticket.id))).scalars().all()) == 1


async def _chamado_antigo_misturado(fabrica, c) -> uuid.UUID:
    """Um chamado de ANTES da regra, com duas empresas e um não classificado."""
    async with fabrica() as s:
        antigo = Ticket(
            id=uuid.uuid4(),
            protocol=f"HS-T-{uuid.uuid4().hex[:8]}",
            title="Chamado antigo",
            description="Associado antes da regra de empresa",
            category=next(iter(TicketCategory)),
            creator_id=c["ator"].id,
        )
        s.add(antigo)
        await s.flush()
        for nome in ("proprio_ativo", "de_y", "do_solto"):
            await s.execute(
                ticket_equipments.insert().values(ticket_id=antigo.id, equipment_id=c[nome].id)
            )
        await s.commit()
        return antigo.id


@pytest.mark.asyncio
async def test_chamado_antigo_misturado_continua_editavel_sem_mexer_nos_aparelhos(fabrica, ligada):
    """Reenviar exatamente o que o chamado já tem não é uma associação nova:
    a regra não reescreve o passado nem trava a edição do chamado antigo. Trocar
    o conjunto, sim, passa pela regra."""
    c = await _cenario(fabrica)
    antigo = await _chamado_antigo_misturado(fabrica, c)
    os_mesmos = [c["do_solto"].id, c["proprio_ativo"].id, c["de_y"].id]

    await _troca_aparelhos(fabrica, c["admin"], antigo, os_mesmos)
    assert await _aparelhos_do_chamado(fabrica, antigo) == set(os_mesmos)

    for outro_conjunto in (
        [c["proprio_ativo"].id, c["de_y"].id],
        [*os_mesmos, c["colega_ativo"].id],
    ):
        with pytest.raises(HTTPException) as recusa:
            await _troca_aparelhos(fabrica, c["admin"], antigo, outro_conjunto)
        assert recusa.value.status_code == 400
    assert await _aparelhos_do_chamado(fabrica, antigo) == set(os_mesmos)

    # Corrigir de verdade continua possível: um conjunto coerente passa.
    await _troca_aparelhos(fabrica, c["admin"], antigo, [c["proprio_ativo"].id])
    assert await _aparelhos_do_chamado(fabrica, antigo) == {c["proprio_ativo"].id}


@pytest.mark.asyncio
async def test_com_a_flag_desligada_a_equipe_vincula_como_sempre(fabrica, desligada):
    c = await _cenario(fabrica)
    chamado = await _roda(fabrica, _abre_chamado(c["ator"], [c["proprio_ativo"].id]))
    misturados = [c["de_y"].id, c["colega_ativo"].id, c["sem_dono_sem_empresa"].id]

    await _troca_aparelhos(fabrica, c["admin"], chamado, misturados)
    aberto_pela_equipe = await _roda(fabrica, _abre_chamado(c["admin"], misturados))

    assert await _aparelhos_do_chamado(fabrica, chamado) == set(misturados)
    assert await _aparelhos_do_chamado(fabrica, aberto_pela_equipe) == set(misturados)


@pytest.mark.asyncio
async def test_com_a_flag_desligada_o_cliente_junta_os_proprios_como_sempre(fabrica, desligada):
    c = await _cenario(fabrica)
    proprios = [c[n].id for n in ("proprio_ativo", "proprio_sem_empresa", "proprio_em_y")]

    chamado = await _roda(fabrica, _abre_chamado(c["ator"], proprios))

    assert await _aparelhos_do_chamado(fabrica, chamado) == set(proprios)


# ── Concorrência da regra de empresa ──────────────────────────


@pytest.mark.asyncio
async def test_troca_de_empresa_em_curso_faz_a_associacao_da_equipe_reler_e_recusar(
    fabrica, ligada
):
    """Um técnico troca a empresa do aparelho; o admin, no meio, associa esse
    aparelho junto de outro da empresa antiga. A associação espera a troca e
    relê o aparelho já na empresa nova: mistura, 400."""
    c = await _cenario(fabrica)
    chamado = await _roda(fabrica, _abre_chamado(c["ator"], []))

    resultado = await _corrida(
        fabrica,
        _equipe_edita(c["tecnico"], c["colega_ativo"], company_id=c["y"].id),
        _troca(c["admin"], chamado, [c["colega_ativo"].id, c["proprio_ativo"].id]),
    )

    assert resultado == ["ok", 400]
    assert await _aparelhos_do_chamado(fabrica, chamado) == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("mudanca", ["outra_empresa", "sem_empresa"])
async def test_associacao_da_equipe_em_curso_faz_a_troca_de_empresa_esperar(
    fabrica, ligada, mudanca
):
    """A associação conferiu e ainda não comitou: quem quer reclassificar um dos
    aparelhos espera. É a espera que se mede — sem o `FOR SHARE` o chamado
    comitaria com dois aparelhos que, naquele instante, já seriam de
    classificações diferentes."""
    c = await _cenario(fabrica)
    chamado = await _roda(fabrica, _abre_chamado(c["ator"], []))
    aparelho = c["colega_ativo"]
    nova = c["y"].id if mudanca == "outra_empresa" else None
    from app.routers.tickets import _set_ticket_equipments

    async with fabrica() as da_associacao:
        alvo = (
            await da_associacao.execute(select(Ticket).where(Ticket.id == chamado))
        ).scalar_one()
        await _set_ticket_equipments(
            da_associacao, alvo, [aparelho.id, c["proprio_ativo"].id], c["admin"]
        )
        tarefa = asyncio.create_task(
            _roda(fabrica, _equipe_edita(c["tecnico"], aparelho, company_id=nova))
        )
        await asyncio.sleep(1.0)

        assert not tarefa.done(), "a reclassificação deveria estar esperando a associação"
        assert await _empresa_do(fabrica, aparelho.id) == c["x"].id
        await da_associacao.commit()
        await asyncio.wait_for(tarefa, timeout=10)

    assert await _aparelhos_do_chamado(fabrica, chamado) == {aparelho.id, c["proprio_ativo"].id}
    assert await _empresa_do(fabrica, aparelho.id) == nova


@pytest.mark.asyncio
async def test_vinculo_em_curso_e_associacao_da_equipe_nao_travam_em_circulo(fabrica, ligada):
    """O vínculo do cliente escreve a empresa nos DOIS aparelhos dele; a equipe,
    no meio, associa os dois a um chamado. A associação pega primeiro a conta
    do responsável — que o vínculo segura — e espera ali, sem segurar aparelho:
    nada de espera em círculo. Quando passa, relê os dois já na mesma empresa."""
    c = await _cenario(fabrica)
    outro = await _aparelho(fabrica, c["produto"], dono=c["solto"])
    chamado = await _roda(fabrica, _abre_chamado(c["admin"], []))

    resultado = await _corrida(
        fabrica,
        _vincula(c["admin"], c["x"], c["solto"]),
        _troca(c["tecnico"], chamado, [c["do_solto"].id, outro.id]),
    )

    assert resultado == ["ok", "ok"]
    assert await _aparelhos_do_chamado(fabrica, chamado) == {c["do_solto"].id, outro.id}
    assert await _empresa_do(fabrica, c["do_solto"].id) == c["x"].id
    assert await _empresa_do(fabrica, outro.id) == c["x"].id


@pytest.mark.asyncio
async def test_empresa_de_quem_abriu_so_conta_quando_quem_abriu_e_cliente(fabrica, ligada):
    """Nada no banco impede uma conta da equipe de carregar `company_id` (um
    cliente promovido, por exemplo). Essa empresa não é "a de quem abriu": a
    equipe abre chamado para qualquer empresa."""
    c = await _cenario(fabrica)
    async with fabrica() as s:
        await s.execute(update(User).where(User.id == c["admin"].id).values(company_id=c["x"].id))
        await s.commit()

    chamado = await _roda(fabrica, _abre_chamado(c["admin"], [c["de_y"].id]))

    assert await _aparelhos_do_chamado(fabrica, chamado) == {c["de_y"].id}


@pytest.mark.asyncio
async def test_associacao_da_equipe_espera_o_vinculo_sem_segurar_aparelho(fabrica, ligada):
    """A ordem das travas, medida: com o vínculo do responsável em curso, a
    associação espera NA CONTA dele e não segura aparelho nenhum. Se travasse
    os aparelhos primeiro, seguraria o livre enquanto espera o do cliente — e o
    vínculo, que escreve nos aparelhos em ordem nenhuma, fecharia o círculo."""
    c = await _cenario(fabrica)
    for _ in range(40):  # um aparelho livre que venha ANTES na ordem das travas
        livre = await _aparelho(fabrica, c["produto"])
        if livre.id < c["do_solto"].id:
            break
    else:  # pragma: no cover
        pytest.fail("não saiu um id menor em 40 sorteios")
    chamado = await _roda(fabrica, _abre_chamado(c["admin"], []))

    async with fabrica() as do_vinculo:
        commit_de_verdade = do_vinculo.commit
        do_vinculo.commit = do_vinculo.flush  # type: ignore[method-assign]
        await _vincula(c["admin"], c["x"], c["solto"])(do_vinculo)

        tarefa = asyncio.create_task(
            _roda(fabrica, _troca(c["tecnico"], chamado, [livre.id, c["do_solto"].id]))
        )
        await asyncio.sleep(1.0)
        assert not tarefa.done(), "a associação deveria estar esperando o vínculo"

        async with fabrica() as sonda:
            await sonda.execute(
                select(Equipment.id).where(Equipment.id == livre.id).with_for_update(nowait=True)
            )
            await sonda.rollback()

        await commit_de_verdade()
        # Passada a espera, ela relê: um na empresa X, o outro sem empresa.
        with pytest.raises(HTTPException) as recusa:
            await asyncio.wait_for(tarefa, timeout=10)

    assert recusa.value.status_code == 400
    assert await _aparelhos_do_chamado(fabrica, chamado) == set()
    assert await _empresa_do(fabrica, c["do_solto"].id) == c["x"].id


# ══════════════════════════════════════════════════════════════
# 7. A Helô
# ══════════════════════════════════════════════════════════════


async def _historico_da_helo(fabrica, cliente, chamado_id, aparelho_id) -> str:
    from app.services.helo_prompt import _chamados_anteriores

    async with fabrica() as s:
        chamado = await s.get(Ticket, chamado_id)
        # O cliente como a requisição o carrega: com o vínculo que está no banco.
        do_banco = await s.get(type(cliente), cliente.id)
        return await _chamados_anteriores(s, chamado, do_banco, [aparelho_id])


@pytest.mark.asyncio
async def test_a_helo_so_recebe_o_historico_do_proprio_cliente(fabrica, ligada):
    from app.services.helo_prompt import monta_cadastro

    c = await _cenario(fabrica)
    aparelho = c["colega_ativo"]
    await _roda(fabrica, _abre_chamado(c["colega"], [aparelho.id], "SEGREDO DO COLEGA"))
    await _roda(fabrica, _abre_chamado(c["ator"], [aparelho.id], "Meu chamado antigo"))
    atual = await _roda(fabrica, _abre_chamado(c["ator"], [aparelho.id], "Meu chamado de agora"))

    historico = await _historico_da_helo(fabrica, c["ator"], atual, aparelho.id)
    async with fabrica() as s:
        cadastro = await monta_cadastro(
            s, await s.get(Ticket, atual), await s.get(type(c["ator"]), c["ator"].id)
        )

    assert "Meu chamado antigo" in historico
    assert "SEGREDO DO COLEGA" not in historico
    assert "Meu chamado de agora" not in historico
    assert "Meu chamado antigo" in cadastro
    for segredo in ("SEGREDO DO COLEGA", c["colega"].name, c["colega"].email):
        assert segredo not in cadastro


@pytest.mark.asyncio
async def test_com_a_flag_desligada_o_recorte_da_helo_continua_o_de_antes(fabrica, desligada):
    """ACHADO PREEXISTENTE, registrado e não corrigido nesta frente.

    Com a flag desligada o histórico é recortado pela EMPRESA de quem abriu, e
    não pelo autor: se o mesmo aparelho já teve chamado de um colega (aparelho
    que trocou de responsável dentro da empresa), o título dele entra no
    prompt. A Sessão 0 decidiu não alterar o escopo atual da Helô aqui; este
    teste prende o comportamento para que a mudança seja deliberada.
    """
    c = await _cenario(fabrica)
    aparelho = c["proprio_ativo"]
    async with fabrica() as s:  # o colega abriu chamado quando o aparelho era dele
        antigo = Ticket(
            id=uuid.uuid4(),
            protocol="HS-T-ANTIGO",
            title="Chamado do colega",
            description="Descrição do chamado antigo",
            category=next(iter(TicketCategory)),
            creator_id=c["colega"].id,
        )
        s.add(antigo)
        await s.flush()
        await s.execute(
            ticket_equipments.insert().values(ticket_id=antigo.id, equipment_id=aparelho.id)
        )
        await s.commit()
    atual = await _roda(fabrica, _abre_chamado(c["ator"], [aparelho.id], "Meu chamado"))

    assert "Chamado do colega" in await _historico_da_helo(fabrica, c["ator"], atual, aparelho.id)


# ══════════════════════════════════════════════════════════════
# 8. As telas da equipe
# ══════════════════════════════════════════════════════════════


async def _da_equipe(http, quem, **params) -> dict:
    http.estado["ator"] = quem
    resp = await http.get("/api/v1/equipments", params={"limit": 100, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _contador_da_empresa(http, quem, empresa) -> int:
    http.estado["ator"] = quem
    resp = await http.get("/api/v1/companies", params={"limit": 100})
    assert resp.status_code == 200, resp.text
    [linha] = [i for i in resp.json()["items"] if i["id"] == str(empresa.id)]
    return linha["equipment_count"]


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", ["admin", "tecnico"])
async def test_filtro_e_contador_da_equipe_usam_a_empresa_do_aparelho(fabrica, http, ligada, papel):
    c = await _cenario(fabrica)
    de_x = {
        "proprio_ativo",
        "proprio_inativo",
        "colega_ativo",
        "colega_inativo",
        "sem_dono_em_x",
        "de_x_com_dono_em_y",
    }
    de_y = {"proprio_em_y", "colega_em_y", "de_y", "de_y_inativo"}

    lista_x = await _da_equipe(http, c[papel], company_id=str(c["x"].id))
    lista_y = await _da_equipe(http, c[papel], company_id=str(c["y"].id))
    sem_empresa = await _da_equipe(http, c[papel], without_company="true")

    assert _nomes(c, (i["id"] for i in lista_x["items"])) == de_x
    assert _nomes(c, (i["id"] for i in lista_y["items"])) == de_y
    assert _nomes(c, (i["id"] for i in sem_empresa["items"])) == set(_APARELHOS) - de_x - de_y
    # Filtro, total e contador da tela de Empresas contam o mesmo conjunto.
    assert lista_x["total"] == len(de_x) == await _contador_da_empresa(http, c["admin"], c["x"])
    assert lista_y["total"] == len(de_y) == await _contador_da_empresa(http, c["admin"], c["y"])
    # Paginado, o conjunto é o mesmo.
    paginado: list[str] = []
    for offset in range(0, 8, 2):
        pagina = await _da_equipe(http, c[papel], company_id=str(c["x"].id), limit=2, offset=offset)
        assert pagina["total"] == len(de_x)
        paginado += [i["id"] for i in pagina["items"]]
    assert _nomes(c, paginado) == de_x and len(paginado) == len(de_x)


@pytest.mark.asyncio
async def test_com_a_flag_desligada_filtro_e_contador_seguem_o_responsavel(
    fabrica, http, desligada
):
    c = await _cenario(fabrica)
    do_responsavel_em_x = _SEUS["ator"] | _SEUS["colega"]

    lista_x = await _da_equipe(http, c["admin"], company_id=str(c["x"].id))

    assert _nomes(c, (i["id"] for i in lista_x["items"])) == do_responsavel_em_x
    assert lista_x["total"] == await _contador_da_empresa(http, c["admin"], c["x"])


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", [False, True])
async def test_a_equipe_ve_as_duas_empresas_e_a_divergencia(fabrica, http, monkeypatch, flag):
    """`linked_company_*` (do responsável) ao lado de `equipment_company_*` (do
    aparelho), nos dois modos da flag: é com isso que a equipe confere o parque
    ANTES de ligar a regra."""
    monkeypatch.setattr(get_settings(), "equipamento_por_empresa", flag)
    c = await _cenario(fabrica)
    http.estado["ator"] = c["tecnico"]

    async def ficha(nome):
        resp = await http.get(f"/api/v1/equipments/{c[nome].id}")
        assert resp.status_code == 200, resp.text
        return resp.json()

    divergente = await ficha("de_x_com_dono_em_y")
    alinhado = await ficha("colega_ativo")
    por_decisao = await ficha("colega_por_decisao")
    nao_classificado = await ficha("colega_sem_empresa")
    sem_dono = await ficha("sem_dono_em_x")

    assert divergente["equipment_company_id"] == str(c["x"].id)
    assert divergente["equipment_company_name"] == "Empresa X"
    assert divergente["linked_company_id"] == str(c["y"].id)
    assert divergente["linked_company_name"] == "Empresa Y"
    assert alinhado["equipment_company_id"] == alinhado["linked_company_id"] == str(c["x"].id)
    assert (por_decisao["equipment_company_id"], por_decisao["no_company_by_decision"]) == (
        None,
        True,
    )
    assert (
        nao_classificado["equipment_company_id"],
        nao_classificado["no_company_by_decision"],
    ) == (None, False)
    assert sem_dono["equipment_company_name"] == "Empresa X" and sem_dono["owner_id"] is None
    # A equipe continua vendo o responsável; `is_mine` é só do cliente.
    assert alinhado["owner_name"] == c["colega"].name and alinhado["is_mine"] is None


# ══════════════════════════════════════════════════════════════
# 9. Concorrência: vale o que está comitado quando o chamado comita
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_desvinculo_em_curso_faz_o_chamado_esperar_e_recusar(fabrica, ligada):
    c = await _cenario(fabrica)

    resultado = await _corrida(
        fabrica,
        _desvincula(c["admin"], c["x"], c["ator"]),
        _abre_chamado(c["ator"], [c["colega_ativo"].id]),
    )

    assert resultado == ["ok", 403]
    async with fabrica() as s:
        assert (await s.execute(select(Ticket))).scalars().all() == []


@pytest.mark.asyncio
async def test_chamado_em_curso_faz_o_desvinculo_esperar(fabrica, ligada):
    """O chamado comita com o cliente ainda vinculado — associação legítima —,
    e o desvínculo passa em seguida. O aparelho fica no chamado: desvincular
    não reescreve o que já foi aberto."""
    c = await _cenario(fabrica)

    resultado = await _corrida(
        fabrica,
        _abre_chamado(c["ator"], [c["colega_ativo"].id]),
        _desvincula(c["admin"], c["x"], c["ator"]),
    )

    assert resultado == ["ok", "ok"]
    async with fabrica() as s:
        [chamado] = (await s.execute(select(Ticket.id))).scalars().all()
    assert await _aparelhos_do_chamado(fabrica, chamado) == {c["colega_ativo"].id}


@pytest.mark.asyncio
async def test_troca_de_empresa_em_curso_faz_o_chamado_reler_e_recusar(fabrica, ligada):
    c = await _cenario(fabrica)

    resultado = await _corrida(
        fabrica,
        _equipe_edita(c["tecnico"], c["colega_ativo"], company_id=c["y"].id),
        _abre_chamado(c["ator"], [c["colega_ativo"].id]),
    )

    assert resultado == ["ok", 403]
    assert await _empresa_do(fabrica, c["colega_ativo"].id) == c["y"].id


@pytest.mark.asyncio
async def test_inativacao_em_curso_faz_o_chamado_do_colega_reler_e_recusar(fabrica, ligada):
    c = await _cenario(fabrica)

    resultado = await _corrida(
        fabrica,
        _cliente_inativa(c["colega"], c["colega_ativo"]),
        _abre_chamado(c["ator"], [c["colega_ativo"].id]),
    )

    assert resultado == ["ok", 403]


@pytest.mark.asyncio
@pytest.mark.parametrize("depois", ["inativa", "troca_de_empresa"])
async def test_chamado_em_curso_faz_a_mudanca_no_aparelho_esperar(fabrica, ligada, depois):
    """O chamado conferiu o aparelho e ainda não comitou. Quem quer mudar o
    aparelho ESPERA — e é a espera que se mede aqui, não só o resultado: sem o
    `FOR SHARE` o estado final seria o mesmo, mas o chamado comitaria com um
    aparelho que, naquele instante, o cliente já não enxergava."""
    c = await _cenario(fabrica)
    aparelho = c["colega_ativo"]
    mudanca = (
        _cliente_inativa(c["colega"], aparelho)
        if depois == "inativa"
        else _equipe_edita(c["admin"], aparelho, company_id=c["y"].id)
    )

    async def como_esta():
        async with fabrica() as s:
            atual = await s.get(Equipment, aparelho.id)
            return atual.is_active, atual.company_id

    async with fabrica() as do_chamado:
        chamado = await _abre_chamado(c["ator"], [aparelho.id], comita=False)(do_chamado)
        tarefa = asyncio.create_task(_roda(fabrica, mudanca))
        await asyncio.sleep(1.0)

        assert not tarefa.done(), "a mudança no aparelho deveria estar esperando o chamado"
        assert await como_esta() == (True, c["x"].id)
        await do_chamado.commit()
        await asyncio.wait_for(tarefa, timeout=10)

    assert await _aparelhos_do_chamado(fabrica, chamado) == {aparelho.id}
    assert await como_esta() == ((False, c["x"].id) if depois == "inativa" else (True, c["y"].id))


@pytest.mark.asyncio
async def test_vinculo_do_colega_em_curso_nao_trava_o_chamado_em_circulo(fabrica, ligada):
    """O chamado pede um aparelho que ainda não enxerga (o colega está sendo
    vinculado agora, e a propagação escreve nesse aparelho). A conferência vem
    ANTES da trava no aparelho: o pedido é recusado sem segurar nada."""
    c = await _cenario(fabrica)

    resultado = await _corrida(
        fabrica,
        _vincula(c["admin"], c["x"], c["solto"]),
        _abre_chamado(c["ator"], [c["proprio_ativo"].id, c["do_solto"].id]),
    )

    assert resultado == ["ok", 403]
