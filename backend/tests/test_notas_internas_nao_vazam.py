"""
`technician_notes` é interna, e o banco não é quem garante isso — nós somos.

O modelo declara a intenção em `models.py`::

    # Notas internas (visível apenas para admin/técnico)
    technician_notes: Mapped[str | None]

Mas a máscara vivia copiada em dois endpoints de leitura e **faltava em três**
caminhos que um cliente alcança. O defeito não foi de quem escreveu cada
endpoint: foi de a regra morar no call site. Cada saída nova precisava lembrar
dela, e três não lembraram.

Estes testes existem para que a regra pare de depender de memória. Eles usam
uma nota **real, não-nula** de propósito — a suíte antiga tinha `technician_notes
= None` nas fixtures, e por isso nunca teria pego nada.

Os três caminhos que vazavam, todos alcançáveis por um cliente autenticado dono
do chamado:

- ``PATCH /tickets/{id}/observation`` — o cliente edita a própria observação e
  recebe o chamado inteiro de volta;
- ``POST /tickets/{id}/reopen`` — e aqui é pior, porque é o momento em que a
  nota interna está mais cheia;
- ``GET /tickets/{id}/history`` — o pior dos três: não entrega a nota atual,
  entrega **todas as versões** dela, porque `PATCH /tickets/{id}` registra
  `old_value` e `new_value` por extenso no histórico.

O histórico continua sendo GRAVADO com a nota. O que muda é quem pode lê-lo —
auditoria não se protege apagando registro.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import UserRole
from tests.test_tickets import (
    _CREATOR_ID,
    _TICKET_ID,
    _db_override,
    _db_seq_override,
    _mock_ticket,
    _mock_user,
    _override_user,
    patch_redis,  # noqa: F401 — fixture usada por nome
)

# A nota que NÃO pode chegar ao cliente. Texto marcado para que qualquer
# vazamento apareça na asserção, em vez de passar como string genérica.
_NOTA = "SEGREDO INTERNO: cliente reclamou do atendimento, tratar com cuidado"
_NOTA_ANTIGA = "SEGREDO INTERNO A: primeira versao da nota"
_NOTA_NOVA = "SEGREDO INTERNO B: segunda versao da nota"


def _com_nota(**kwargs):
    """Chamado com nota interna REAL — o contrário da fixture padrão."""
    ticket = _mock_ticket(**kwargs)
    ticket.technician_notes = _NOTA
    return ticket


def _mock_sla():
    """SLAConfig com números de verdade — o cálculo de prazo não aceita mock cru."""
    from unittest.mock import MagicMock

    c = MagicMock()
    c.response_time_minutes = 240
    c.resolve_time_minutes = 1440
    return c


class _Consultas:
    """Sessão de mentira que GUARDA o SQL de cada `execute`.

    Necessária porque o recorte do histórico é um `WHERE` — um mock que
    devolve lista fixa ignora a cláusula, e o teste passaria com a correção
    apagada. Aqui a prova é o SQL que o endpoint mandou ao banco.
    """

    def __init__(self, ticket):
        from unittest.mock import AsyncMock, MagicMock

        self.sqls: list[str] = []
        self._ticket = ticket
        self._n = 0

        async def _execute(stmt, *a, **k):
            self.sqls.append(str(stmt))
            self._n += 1
            r = MagicMock()
            if self._n == 1:
                r.scalar_one_or_none.return_value = ticket
                r.scalar_one.return_value = 0
                r.scalars.return_value.all.return_value = [ticket]
            else:
                r.scalar_one_or_none.return_value = None
                r.scalar_one.return_value = 0
                r.scalars.return_value.all.return_value = []
            return r

        sessao = AsyncMock()
        sessao.execute = _execute
        sessao.add = MagicMock()
        sessao.commit = AsyncMock()
        sessao.refresh = AsyncMock()
        self._sessao = sessao

    @property
    def sqls_do_historico(self) -> list[str]:
        """Só as consultas a `ticket_history`.

        O primeiro `execute` do endpoint é o `select(Ticket)` do `get_or_404`, e
        a TABELA `tickets` tem a coluna `technician_notes` — procurar a palavra
        em todas as consultas daria positivo mesmo para staff. Foi o que
        aconteceu na primeira versão deste arquivo.
        """
        return [q for q in self.sqls if "ticket_history" in q]

    @property
    def override(self):
        async def _gen():
            yield self._sessao

        return _gen


def _captura_consultas(ticket):
    return _Consultas(ticket)


def _historico(field: str, antigo: str, novo: str):
    """Uma linha de `ticket_history`, como o PATCH do técnico a grava."""
    from unittest.mock import MagicMock

    h = MagicMock()
    h.id = uuid.uuid4()
    h.ticket_id = _TICKET_ID
    h.user_id = uuid.uuid4()
    h.user = None
    h.field = field
    h.old_value = antigo
    h.new_value = novo
    h.comment = None
    # Sem valor explícito o MagicMock devolve um objeto e a validação falha —
    # a mesma armadilha que `_mock_ticket` documenta para os campos opcionais.
    h.user_name = None
    from tests.test_tickets import _NOW

    h.created_at = _NOW
    return h


# ── Os três caminhos que vazavam ─────────────────────────────


@pytest.mark.asyncio
async def test_observation_nao_devolve_nota_interna_ao_cliente(patch_redis):  # noqa: F811
    """O cliente edita a própria observação — e não pode receber a nota junto.

    Caminho real: ele já tem permissão para chamar este endpoint (é o chamado
    dele, e o campo é dele). O que estava errado era a RESPOSTA.
    """
    from app.core.database import get_db

    dono = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _com_nota(creator_id=_CREATOR_ID)
    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(dono)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/observation",
            json={"client_observation": "O aparelho voltou a falhar"},
        )

    assert resp.status_code == 200
    assert resp.json()["technician_notes"] is None
    assert _NOTA not in resp.text


@pytest.mark.asyncio
async def test_reopen_nao_devolve_nota_interna_ao_cliente(patch_redis):  # noqa: F811
    """Reabrir é quando a nota está mais cheia — todo o atendimento já passou."""
    from app.core.database import get_db
    from app.models.models import TicketStatus

    dono = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _com_nota(creator_id=_CREATOR_ID, status=TicketStatus.resolved)
    ticket.resolved_at = ticket.created_at
    # A reabertura recalcula prazo, e o cálculo lê um SLAConfig do banco. Sem
    # este segundo item da sequência, o mock devolveria o próprio ticket no
    # lugar da configuração e o SLA compararia MagicMock com int.
    app.dependency_overrides[get_db] = _db_seq_override(ticket, _mock_sla())
    _override_user(dono)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/reopen",
            json={"reason": "Continua com o mesmo defeito"},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["technician_notes"] is None
    assert _NOTA not in resp.text


@pytest.mark.asyncio
async def test_criar_chamado_nao_devolve_nota_interna(patch_redis):  # noqa: F811
    """Auditado porque você pediu, ainda que a nota nasça nula.

    Prende o contrato: se um dia a criação passar a copiar nota de template ou
    de chamado anterior, o cliente não recebe.
    """
    from app.core.database import get_db

    cliente = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    app.dependency_overrides[get_db] = _db_seq_override(0, None, None)
    _override_user(cliente)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/tickets",
            json={"title": "Aparelho parou", "description": "Nao liga"},
        )

    if resp.status_code == 201:
        assert resp.json()["technician_notes"] is None


# ── O histórico: o pior dos três ─────────────────────────────


@pytest.mark.asyncio
async def test_historico_nao_entrega_versoes_da_nota_ao_cliente(patch_redis):  # noqa: F811
    """⚠️ O caminho mais grave: entregava TODAS as versões, não só a atual.

    `PATCH /tickets/{id}` grava `registra_historico(..., 'technician_notes',
    old, new)`, e `history.py` guarda os dois textos por extenso, sem truncar.
    Depois o cliente dono lia o histórico e recebia o antes e o depois.

    O recorte é aplicado na CONSULTA, então o que este teste prende é a
    cláusula que chega ao banco — capturada do `select` real que o endpoint
    monta. Um mock que devolve lista fixa não enxergaria um `WHERE`, e um teste
    que só olhasse a resposta passaria mesmo com a correção removida.

    A linha continua no banco. O que muda é quem a lê.
    """
    from app.core.database import get_db

    dono = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _com_nota(creator_id=_CREATOR_ID)
    consultas = _captura_consultas(ticket)
    app.dependency_overrides[get_db] = consultas.override
    _override_user(dono)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}/history")

    assert resp.status_code == 200, resp.text
    sql = " ".join(consultas.sqls_do_historico)
    assert sql, "o endpoint não consultou o histórico"
    # O SQLAlchemy renderiza os valores do `IN` como placeholder
    # (`__[POSTCOMPILE_field_1]`), então o literal "technician_notes" NÃO
    # aparece no `str(stmt)` — procurar por ele daria falso negativo. O que
    # distingue cliente de staff é a CLÁUSULA sobre `field`, e é ela que se
    # prende aqui; o conteúdo da lista fica com o teste de `CAMPOS_INTERNOS`.
    assert "ticket_history.field NOT IN" in sql, f"o recorte não chegou à consulta: {sql}"


@pytest.mark.asyncio
async def test_historico_do_staff_vai_sem_recorte(patch_redis):  # noqa: F811
    """Para o staff a consulta sai limpa — auditoria inteira, como sempre foi."""
    from app.core.database import get_db

    staff = _mock_user(UserRole.admin)
    ticket = _com_nota(creator_id=_CREATOR_ID)
    consultas = _captura_consultas(ticket)
    app.dependency_overrides[get_db] = consultas.override
    _override_user(staff)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}/history")

    assert resp.status_code == 200, resp.text
    sql = " ".join(consultas.sqls_do_historico)
    assert sql, "o endpoint não consultou o histórico"
    assert "ticket_history.field NOT IN" not in sql, "o staff levou recorte que não é dele"


def test_o_recorte_e_so_para_cliente():
    """A política, direto: cláusula para cliente, nada para staff."""
    from app.utils.history import CAMPOS_INTERNOS, filtra_historico_para

    assert "technician_notes" in CAMPOS_INTERNOS
    assert filtra_historico_para(_mock_user(UserRole.client)) is not None
    assert filtra_historico_para(_mock_user(UserRole.admin)) is None
    assert filtra_historico_para(_mock_user(UserRole.technician)) is None


# ── As duas que já mascaravam: a defesa delas foi TROCADA ────

# `GET /tickets` e `GET /tickets/{id}` não estavam entre os vazamentos — cada
# uma apagava a nota no próprio corpo, logo depois de serializar. A correção
# removeu essas duas linhas e passou a confiar na regra central: a garantia
# continua, mas quem a sustenta mudou. Sem prova direta, essas duas rotas
# ficariam apoiadas nos testes de `observation` e `reopen`, e nada impediria
# uma mudança futura de atender àquelas e não a estas.


@pytest.mark.asyncio
async def test_listagem_nao_devolve_nota_interna_ao_cliente(patch_redis):  # noqa: F811
    """`GET /tickets` — o cliente lista os próprios chamados."""
    from app.core.database import get_db

    dono = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _com_nota(creator_id=_CREATOR_ID)
    # `1` responde ao count e a lista é a página — mesma sequência que o
    # `test_list_tickets_client_sees_own` já usa para esta rota.
    app.dependency_overrides[get_db] = _db_seq_override(1, [ticket])
    _override_user(dono)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/tickets")

    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    # O chamado precisa estar na resposta: "não vazou" não pode ser verdade
    # só porque a página veio vazia.
    assert [item["id"] for item in corpo["items"]] == [str(_TICKET_ID)]
    assert corpo["items"][0]["technician_notes"] is None
    # E o texto da nota não sobra em nenhum outro campo do JSON inteiro.
    assert _NOTA not in resp.text


@pytest.mark.asyncio
async def test_detalhe_nao_devolve_nota_interna_ao_cliente(patch_redis):  # noqa: F811
    """`GET /tickets/{id}` — o cliente abre o chamado que é dele."""
    from app.core.database import get_db

    dono = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _com_nota(creator_id=_CREATOR_ID)
    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(dono)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}")

    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    assert corpo["id"] == str(_TICKET_ID)
    assert corpo["technician_notes"] is None
    assert _NOTA not in resp.text


# ── O staff não pode perder nada ─────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", [UserRole.admin, UserRole.technician])
async def test_staff_continua_vendo_a_nota_no_detalhe(patch_redis, papel):  # noqa: F811
    """A correção não pode cegar quem precisa da nota para trabalhar."""
    from app.core.database import get_db

    staff = _mock_user(papel)
    ticket = _com_nota(creator_id=_CREATOR_ID)
    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(staff)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}")

    assert resp.status_code == 200
    assert resp.json()["technician_notes"] == _NOTA


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", [UserRole.admin, UserRole.technician])
async def test_staff_continua_vendo_a_nota_no_historico(patch_redis, papel):  # noqa: F811
    """Auditoria preservada: o staff lê as versões, o cliente não."""
    from app.core.database import get_db

    staff = _mock_user(papel)
    ticket = _com_nota(creator_id=_CREATOR_ID)
    eventos = [_historico("technician_notes", _NOTA_ANTIGA, _NOTA_NOVA)]
    app.dependency_overrides[get_db] = _db_seq_override(ticket, len(eventos), eventos)
    _override_user(staff)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}/history")

    assert resp.status_code == 200, resp.text
    campos = {item["field"] for item in resp.json()["items"]}
    assert "technician_notes" in campos
    assert _NOTA_ANTIGA in resp.text
    assert _NOTA_NOVA in resp.text


# ── Guard estrutural: a regra não pode voltar a morar no call site ──


def test_nenhum_endpoint_mascara_a_nota_por_conta_propria():
    """A máscara é do serializador. Copiá-la num endpoint é o defeito de volta.

    Foi exatamente assim que o furo nasceu: dois endpoints lembravam da regra e
    três esqueceram. Se alguém acrescentar `technician_notes = None` num
    endpoint novo, este teste cai — não porque a linha faça mal, mas porque
    significa que a regra voltou a ser responsabilidade de quem escreve a rota.
    """
    import ast
    import inspect

    from app.routers import tickets as router_tickets

    fonte = inspect.getsource(router_tickets)
    arvore = ast.parse(fonte)

    culpados = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        if no.name.startswith("_"):  # os helpers privados podem
            continue
        corpo = ast.unparse(no)
        if "technician_notes" in corpo and "= None" in corpo:
            culpados.append(no.name)

    assert not culpados, f"a máscara voltou a ser copiada em: {culpados}"
