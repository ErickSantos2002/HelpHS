"""Fase 2C.5c: o solicitante aparece no chamado, e o técnico corrige o telefone dele.

Duas metades, e a segunda tem uma história.

**O solicitante no chamado.** `TicketResponse` expunha só `creator_id` — um
UUID, que não diz nome, empresa, e-mail nem telefone. Quem atendia um chamado
alheio não sabia com quem falar sem abrir outra tela. Agora o detalhe (e SÓ o
detalhe) traz `creator`, com os quatro campos que servem para atender.

**O telefone.** A regra pedida era "técnico também pode alterar telefone de
cliente". Ao medir, o backend já permitia: `update_user` aceita
`admin | technician` desde sempre. O que NÃO deixava era outra coisa —
`_guarda_de_atribuicao_de_papel` recusava qualquer `role` no corpo vindo de
não-admin, e o formulário de usuário manda `role` SEMPRE, inclusive igual ao
que já está gravado. O efeito somado: o técnico levava 403 ao salvar QUALQUER
campo daquela tela, telefone incluído.

A correção é de uma frase: **atribuir papel é MUDAR papel**. Mandar de volta o
papel que a pessoa já tem não move ninguém de lugar. Quem tenta mudar continua
recusado, e é isso que os casos abaixo prendem dos dois lados.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import UserRole, UserStatus

_ERRO_PAPEL = "Apenas administradores podem alterar o tipo de usuário."
_ERRO_RAMAL = "Apenas administradores podem configurar o ramal da telefonia."


def _usuario(role: UserRole, **extras) -> MagicMock:
    u = MagicMock()
    u.id = extras.pop("id", uuid.uuid4())
    u.role = role
    u.status = extras.pop("status", UserStatus.active)
    u.email = extras.pop("email", f"{role.value}@teste.com")
    u.name = extras.pop("name", f"Fulano {role.value}")
    u.phone = extras.pop("phone", "+5581999999999")
    u.company_name = extras.pop("company_name", "Health & Safety")
    u.api4com_extension = extras.pop("api4com_extension", None)
    u.department = extras.pop("department", None)
    # ⚠️ `_to_response` faz `UserResponse.model_validate(user)`, e um MagicMock
    # devolve OUTRO mock para atributo não declarado — que o pydantic recusa.
    # Declarar o contrato inteiro aqui é o que separa "o teste falhou" de "o
    # dublê estava incompleto"; a mesma pedra já custou 37 casos nesta casa.
    agora = datetime.now(UTC)
    padroes = {
        "avatar_url": None,
        "last_login": None,
        "lgpd_consent": True,
        "lgpd_consent_at": agora,
        "email_verified": True,
        "company_cep": None,
        "company_address": None,
        "company_city": None,
        "company_state": None,
        "cnpj": None,
        "onboarding_completed": True,
        "ai_enabled": True,
        "created_at": agora,
        "updated_at": agora,
    }
    for campo, valor in padroes.items():
        setattr(u, campo, extras.pop(campo, valor))
    for k, v in extras.items():
        setattr(u, k, v)
    return u


class _Sessao:
    """Devolve o alvo da edição e conta o que foi gravado."""

    def __init__(self, alvo=None) -> None:
        self.alvo = alvo
        self.add = MagicMock()
        self.commit = AsyncMock()
        self.refresh = AsyncMock()
        self.flush = AsyncMock()

    async def execute(self, *a, **k):
        r = MagicMock()
        r.scalar_one_or_none.return_value = self.alvo
        r.scalars.return_value.first.return_value = None
        return r

    async def get(self, *a, **k):
        return self.alvo


def _prepara(ator: MagicMock, alvo=None) -> _Sessao:
    from app.core.database import get_db
    from app.core.security import get_current_user

    sessao = _Sessao(alvo)

    async def _db():
        yield sessao

    async def _atual():
        return ator

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _atual
    return sessao


@pytest.fixture(autouse=True)
def _limpa():
    yield
    app.dependency_overrides.clear()


async def _patch(corpo: dict, alvo_id) -> tuple[int, dict]:
    transporte = ASGITransport(app=app)
    async with AsyncClient(transport=transporte, base_url="http://t") as c:
        r = await c.patch(f"/api/v1/users/{alvo_id}", json=corpo)
    try:
        return r.status_code, r.json()
    except Exception:  # noqa: BLE001
        return r.status_code, {}


# ── O SOLICITANTE NO CHAMADO ─────────────────────────────────


def test_o_schema_do_solicitante_traz_exatamente_quatro_dados_e_o_id():
    """A lista é a regra, não um começo.

    Cada campo a mais aqui é PII a mais numa tela que a equipe inteira abre. O
    que entra serve para ATENDER: nome, empresa, e-mail, telefone.
    """
    from app.schemas.ticket import TicketRequesterBrief

    assert set(TicketRequesterBrief.model_fields) == {
        "id",
        "name",
        "email",
        "phone",
        "company_name",
    }


@pytest.mark.parametrize(
    "proibido",
    [
        "cpf",
        "cnpj",
        "company_cep",
        "company_address",
        "company_city",
        "company_state",
        "department",
        "api4com_extension",
        "lgpd_consent",
        "lgpd_consent_at",
        "password_hash",
        "last_login",
        "status",
        "role",
    ],
)
def test_o_solicitante_nao_carrega_dado_administrativo_nem_pessoal(proibido):
    from app.schemas.ticket import TicketRequesterBrief

    assert proibido not in TicketRequesterBrief.model_fields


def test_a_empresa_vem_de_company_name_e_nao_da_relacao():
    """`users.company_name` é o campo do onboarding, e é o que está preenchido.

    O vínculo `company_id` -> `Company` pertence à frente de grupos/CNPJ, cujo
    backfill nunca rodou em produção. Apontar para lá mostraria "Não informada"
    para todo mundo — correto no tipo, inútil na tela.
    """
    from app.models.models import User
    from app.schemas.ticket import TicketRequesterBrief

    assert "company_name" in TicketRequesterBrief.model_fields
    assert hasattr(User, "company_name")
    assert "company_id" not in TicketRequesterBrief.model_fields


def test_a_listagem_de_chamados_nao_traz_solicitante():
    """O solicitante NÃO mora no `TicketResponse` — e isso é o desenho.

    Aquele modelo é validado a partir do objeto do ORM (`from_attributes`), e
    as rotas de mutação o devolvem sem o criador. Um campo opcional ali seria
    lido do ORM em toda serialização e apagaria o bloco da tela a cada ação.
    Quem carrega o solicitante é o modelo do DETALHE.
    """
    from app.schemas.ticket import TicketDetailResponse, TicketResponse

    assert "requester" not in TicketResponse.model_fields
    assert "requester" in TicketDetailResponse.model_fields
    assert TicketDetailResponse.model_fields["requester"].default is None
    # E o detalhe continua sendo o chamado inteiro, não outro contrato.
    assert set(TicketResponse.model_fields) <= set(TicketDetailResponse.model_fields)


def test_o_detalhe_carrega_o_criador_por_chave_primaria_e_nao_por_lazy():
    """`db.get`, e não `ticket.creator`.

    O relacionamento é lazy e tocá-lo em sessão async estoura `MissingGreenlet`
    — a mesma pedra que o responsável e o destinatário da telefonia já tinham
    contornado. Duas consultas por chave primária no chamado avulso não são um
    N+1: a listagem não passa por aqui.
    """
    import inspect

    from app.routers import tickets

    fonte = inspect.getsource(tickets.get_ticket)
    assert "db.get(User, ticket.creator_id)" in fonte
    assert "ticket.creator." not in fonte


@pytest.mark.asyncio
async def test_o_detalhe_do_chamado_devolve_o_solicitante_de_verdade():
    """O caso que faltava — e a mutação provou que faltava.

    Os outros casos desta seção conferem o CONTRATO: que campo existe, o que
    não existe, de onde o dado sai. Nenhum deles chamava a rota. Apagar a linha
    que preenche `response.creator` deixava a suíte inteira verde, porque o
    campo continuava declarado e opcional — a tela é que ficaria vazia.

    Este chama `GET /tickets/{id}` e olha o corpo.
    """
    from app.core.database import get_db
    from app.core.security import get_current_user
    from app.models.models import Ticket, TicketCategory, TicketStatus

    criador = _usuario(
        UserRole.client,
        name="Pedro Henrique",
        email="pedro@empresa.com",
        phone="+5581988887777",
        company_name="Health & Safety",
    )

    chamado = MagicMock(spec=Ticket)
    agora = datetime.now(UTC)
    for campo, valor in {
        "id": uuid.uuid4(),
        "protocol": "HS-2026-0001",
        "title": "Teste",
        "description": "d",
        "status": TicketStatus.open,
        "priority": None,
        "category": TicketCategory.hardware,
        "creator_id": criador.id,
        "assignee_id": None,
        "product_id": None,
        "equipments": [],
        "tags": [],
        "sla_response_due_at": None,
        "sla_resolve_due_at": None,
        "sla_response_breach": False,
        "sla_resolve_breach": False,
        "sla_first_response": None,
        "sla_resolve_extension_total_min": 0,
        "closed_at": None,
        "resolved_at": None,
        "auto_closed": False,
        "reopened_at": None,
        "reopen_count": 0,
        "ai_enabled": True,
        "technician_notes": None,
        "ai_classification": None,
        "ai_confidence": None,
        "ai_summary": None,
        "ai_conversation_summary": None,
        "client_observation": None,
        "resolution_note": None,
        "created_at": agora,
        "updated_at": agora,
    }.items():
        setattr(chamado, campo, valor)

    class _SessaoDoChamado:
        add = MagicMock()
        commit = AsyncMock()
        refresh = AsyncMock()

        async def get(self, modelo, chave, *a, **k):
            return criador if modelo.__name__ == "User" else chamado

        async def execute(self, *a, **k):
            r = MagicMock()
            r.scalar_one_or_none.return_value = None
            r.scalars.return_value.all.return_value = []
            return r

    sessao = _SessaoDoChamado()

    async def _db():
        yield sessao

    async def _atual():
        return _usuario(UserRole.technician)

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _atual

    with patch("app.routers.tickets.get_or_404", new=AsyncMock(return_value=chamado)):
        transporte = ASGITransport(app=app)
        async with AsyncClient(transport=transporte, base_url="http://t") as c:
            r = await c.get(f"/api/v1/tickets/{chamado.id}")

    assert r.status_code == 200, r.text
    corpo = r.json()
    criador_json = corpo.get("requester")
    assert criador_json is not None, "o detalhe TEM de trazer o solicitante"
    assert criador_json["name"] == "Pedro Henrique"
    assert criador_json["email"] == "pedro@empresa.com"
    assert criador_json["phone"] == "+5581988887777"
    assert criador_json["company_name"] == "Health & Safety"
    # E nada além dos cinco.
    assert set(criador_json) == {"id", "name", "email", "phone", "company_name"}


def test_nenhum_campo_do_response_colide_com_relacionamento_lazy_do_orm():
    """A pedra em que esta fase tropecou, agora presa.

    `TicketResponse` tem `from_attributes=True`, e `_serialize_ticket` faz
    `model_validate(ticket)` com o objeto do ORM. Qualquer campo do schema cujo
    NOME bata com um `relationship()` do `Ticket` passa a ser LIDO nessa
    validacao — e relacionamento lazy lido em sessao async estoura
    `MissingGreenlet`, em toda serializacao de chamado, listagem inclusive.

    Foi exatamente o que aconteceu ao chamar o campo de `creator`: existe
    `Ticket.creator`. Virou `requester`.

    `equipments` e `tags` sao a excecao consciente: relacionamentos que o
    endpoint CARREGA de proposito antes de serializar.
    """
    from sqlalchemy import inspect as sa_inspect

    from app.models.models import Ticket
    from app.schemas.ticket import TicketResponse

    carregados_de_proposito = {"equipments", "tags"}
    lazy = {r.key for r in sa_inspect(Ticket).relationships} - carregados_de_proposito
    colisoes = lazy & set(TicketResponse.model_fields)
    assert not colisoes, (
        f"campo do schema com nome de relacionamento lazy: {sorted(colisoes)} "
        "-- renomeie, ou `model_validate` vai tocar o lazy e estourar MissingGreenlet"
    )


# ── TELEFONE: QUEM PODE MUDAR ────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("papel_do_ator", [UserRole.admin, UserRole.technician])
async def test_staff_altera_o_telefone_de_um_cliente(papel_do_ator):
    """O caso que a fase pediu — e que o técnico não conseguia fazer."""
    alvo = _usuario(UserRole.client, phone="+5581988887777")
    _prepara(_usuario(papel_do_ator), alvo)

    codigo, _ = await _patch({"phone": "(81) 99999-1234"}, alvo.id)

    assert codigo == 200, codigo
    assert alvo.phone == "+5581999991234", "o telefone tem de chegar normalizado"


@pytest.mark.asyncio
async def test_o_telefone_e_normalizado_pelo_helper_da_casa():
    """Nada de regra de telefone duplicada: o schema usa `normaliza_telefone`."""
    alvo = _usuario(UserRole.client)
    _prepara(_usuario(UserRole.technician), alvo)

    codigo, _ = await _patch({"phone": "81 9 9999-1234"}, alvo.id)

    assert codigo == 200
    assert alvo.phone == "+5581999991234"


@pytest.mark.asyncio
async def test_telefone_invalido_e_recusado():
    alvo = _usuario(UserRole.client)
    _prepara(_usuario(UserRole.technician), alvo)

    codigo, _ = await _patch({"phone": "123"}, alvo.id)

    assert codigo == 422


@pytest.mark.asyncio
async def test_cliente_nao_edita_outro_cliente():
    outro = _usuario(UserRole.client)
    _prepara(_usuario(UserRole.client), outro)

    codigo, corpo = await _patch({"phone": "(81) 99999-1234"}, outro.id)

    assert codigo == 403
    assert corpo.get("detail") == "Você não tem permissão para acessar este item."


# ── AUTORIZAÇÃO POR CAMPO ────────────────────────────────────
#
# Poder chamar a rota não é poder escrever tudo o que cabe no corpo.


@pytest.mark.asyncio
async def test_tecnico_nao_promove_ninguem_mesmo_mandando_telefone_junto():
    """O ataque óbvio: esconder a promoção dentro de uma edição legítima."""
    alvo = _usuario(UserRole.client)
    _prepara(_usuario(UserRole.technician), alvo)

    codigo, corpo = await _patch({"phone": "(81) 99999-1234", "role": "admin"}, alvo.id)

    assert codigo == 403
    assert corpo.get("detail") == _ERRO_PAPEL
    assert alvo.role == UserRole.client, "o papel não pode ter sido tocado"


@pytest.mark.asyncio
@pytest.mark.parametrize("novo_papel", ["admin", "technician"])
async def test_tecnico_nao_muda_papel_de_cliente_para_staff(novo_papel):
    alvo = _usuario(UserRole.client)
    _prepara(_usuario(UserRole.technician), alvo)

    codigo, corpo = await _patch({"role": novo_papel}, alvo.id)

    assert codigo == 403
    assert corpo.get("detail") == _ERRO_PAPEL


@pytest.mark.asyncio
async def test_tecnico_nao_rebaixa_staff_a_cliente():
    """Rebaixar também é MUDAR — e continua sendo atribuição de papel."""
    alvo = _usuario(UserRole.technician)
    _prepara(_usuario(UserRole.technician), alvo)

    codigo, corpo = await _patch({"role": "client"}, alvo.id)

    assert codigo == 403
    assert corpo.get("detail") == _ERRO_PAPEL


@pytest.mark.asyncio
async def test_tecnico_nao_configura_ramal():
    alvo = _usuario(UserRole.technician)
    _prepara(_usuario(UserRole.technician), alvo)

    codigo, corpo = await _patch({"api4com_extension": "1020"}, alvo.id)

    assert codigo == 403
    assert corpo.get("detail") == _ERRO_RAMAL


@pytest.mark.asyncio
async def test_tecnico_nao_apaga_ramal_alheio_mandando_nulo():
    """`null` é remoção, e remoção é administrativa. O sinal é o campo VIR."""
    alvo = _usuario(UserRole.technician, api4com_extension="1019")
    _prepara(_usuario(UserRole.technician), alvo)

    codigo, corpo = await _patch({"api4com_extension": None}, alvo.id)

    assert codigo == 403
    assert corpo.get("detail") == _ERRO_RAMAL
    assert alvo.api4com_extension == "1019"


@pytest.mark.asyncio
async def test_status_nao_se_muda_por_esta_rota_nem_para_admin():
    """A situação da conta tem rota própria (`PATCH /users/{id}/status`).

    `UserUpdate` não declara `status`, e `AppBaseModel` ignora extra — então o
    campo é DESCARTADO, e não escrito. O caso prende isso: o que protege não é
    um `if`, é o schema não ter a porta.
    """
    from app.schemas.user import UserUpdate

    assert "status" not in UserUpdate.model_fields

    alvo = _usuario(UserRole.client, status=UserStatus.active)
    _prepara(_usuario(UserRole.technician), alvo)

    codigo, _ = await _patch({"status": "inactive"}, alvo.id)

    assert codigo == 200
    assert alvo.status == UserStatus.active, "a situação não podia ter mudado"


# ── O QUE A CORREÇÃO DESTRAVOU, SEM ABRIR MAIS NADA ──────────


@pytest.mark.asyncio
async def test_o_papel_igual_ao_atual_nao_e_atribuicao():
    """O coração da correção.

    O formulário de usuário manda `role` sempre. Antes, isso bastava para o
    técnico levar 403 ao salvar o nome de um cliente. Mandar de volta o papel
    que já está gravado não move ninguém de lugar.
    """
    alvo = _usuario(UserRole.client, name="Nome Antigo")
    _prepara(_usuario(UserRole.technician), alvo)

    codigo, _ = await _patch(
        {"name": "Nome Novo", "role": "client", "phone": "(81) 99999-1234"}, alvo.id
    )

    assert codigo == 200, codigo
    assert alvo.name == "Nome Novo"
    assert alvo.phone == "+5581999991234"


@pytest.mark.asyncio
async def test_admin_continua_podendo_mudar_papel():
    """A correção não podia fechar o que era permitido."""
    alvo = _usuario(UserRole.client)
    _prepara(_usuario(UserRole.admin), alvo)

    codigo, _ = await _patch({"role": "technician"}, alvo.id)

    assert codigo == 200, codigo
    assert alvo.role == "technician"


def test_a_guarda_do_papel_le_o_papel_atual_antes_de_decidir():
    """Sentinela estrutural: a comparação não pode sumir num refactor.

    Sem ela a guarda volta a recusar papel repetido, e o técnico volta a não
    conseguir salvar nada — que é o defeito que esta fase conserta.
    """
    import inspect

    from app.routers import users

    fonte = inspect.getsource(users.update_user)
    assert "body.role if body.role != user.role else None" in fonte


def test_a_criacao_de_usuario_nao_foi_afrouxada():
    """`create_user` compartilha a guarda e NÃO pode ter mudado de regra.

    Lá o sinal continua sendo o papel pedido, porque não existe conta anterior
    com que comparar — técnico criando admin segue 403.
    """
    import inspect

    from app.routers import users

    fonte = inspect.getsource(users.create_user)
    assert "_guarda_de_atribuicao_de_papel" in fonte
    assert "user.role" not in fonte.split("_guarda_de_atribuicao_de_papel")[1][:200]


# ── AUDITORIA ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_edicao_de_telefone_e_auditada_sem_o_numero():
    """O AuditLog registra QUE houve edição, com autor e alvo.

    Não guarda o telefone: o padrão da rota é `_audit(db, update, ator, alvo)`,
    sem `old_data`/`new_data`. Manter assim é o que impede que o histórico
    administrativo vire um segundo lugar por onde PII vaza.
    """
    from app.models.models import AuditLog

    alvo = _usuario(UserRole.client)
    sessao = _prepara(_usuario(UserRole.technician), alvo)

    codigo, _ = await _patch({"phone": "(81) 99999-1234"}, alvo.id)
    assert codigo == 200

    registros = [c.args[0] for c in sessao.add.call_args_list if isinstance(c.args[0], AuditLog)]
    assert len(registros) == 1, f"esperava um registro, vieram {len(registros)}"
    registro = registros[0]
    texto = f"{registro.old_data}{registro.new_data}"
    for pedaco in ("99999", "1234", "+55", "8199"):
        assert pedaco not in texto, f"o telefone vazou para a auditoria: {pedaco}"
