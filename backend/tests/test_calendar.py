"""
Tests da agenda da equipe (calendar events).
DB e Redis totalmente mockados.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import CalendarEventType, UserRole, UserStatus

# ── Fake Redis ────────────────────────────────────────────────


class _FakeRedis:
    def __init__(self):
        self._store: dict = {}

    async def setex(self, k, t, v):
        self._store[k] = v

    async def get(self, k):
        return self._store.get(k)

    async def delete(self, k):
        self._store.pop(k, None)

    async def exists(self, k):
        return 1 if k in self._store else 0


_redis = _FakeRedis()


async def _get_redis():
    return _redis


_NOW = datetime.now(UTC)
_EVENT_ID = uuid.uuid4()
_CREATOR_ID = uuid.uuid4()


# ── Mocks ─────────────────────────────────────────────────────


def _mock_user(role=UserRole.technician, user_id=None):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.name = f"{role.value}_user"
    u.email = f"{role.value}@test.com"
    u.role = role
    u.status = UserStatus.active
    return u


def _mock_event(created_by=_CREATOR_ID, all_day=False):
    e = MagicMock()
    e.id = _EVENT_ID
    e.title = "Treinamento de bafômetros"
    e.description = "Sala 201"
    e.event_type = CalendarEventType.training
    e.color = "#047857"
    e.start_date = _NOW
    e.end_date = _NOW + timedelta(days=1)
    # ⚠️ Booleano PRECISA de valor explícito aqui.
    #
    # Atributo de `MagicMock` que ninguém definiu devolve outro `MagicMock`, e
    # `MagicMock` é VERDADEIRO. Sem esta linha, `all_day` lia como ligado em
    # todos os casos deste arquivo — e o PATCH passava a derivar as bordas do
    # dia, apagando as horas que o caso acabara de mandar. O sintoma foi um
    # `assert event.start_date == novo_inicio` falhando com a meia-noite do dia
    # certo, que parece erro de fuso e não é.
    #
    # Vale para qualquer coluna booleana nova: o default do mock é `True` sem
    # que ninguém tenha escrito `True` em lugar nenhum.
    e.all_day = all_day
    e.created_by = created_by
    e.creator = None
    # O response lê este atributo direto do objeto; sem valor explícito o
    # MagicMock devolveria um objeto e a validação falharia
    e.creator_name = None
    e.created_at = _NOW
    e.updated_at = _NOW
    return e


def _db_sequence(*responses):
    call_count = [0]

    async def _execute(*args, **kwargs):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        resp = responses[idx]

        result = MagicMock()
        if isinstance(resp, list):
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = resp
        else:
            result.scalar_one_or_none.return_value = resp
            result.scalars.return_value.all.return_value = [resp] if resp else []
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


def _db_override(*responses):
    session = _db_sequence(*responses)

    async def _gen():
        yield session

    return _gen


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def patch_redis():
    with patch("app.core.security.get_redis", new=_get_redis):
        yield


def _override_user(user):
    from app.core.security import get_current_user

    async def _current():
        return user

    app.dependency_overrides[get_current_user] = _current


def _event_body(**overrides):
    body = {
        "title": "Treinamento de bafômetros",
        "description": "Sala 201",
        "event_type": "training",
        "color": "#047857",
        "start_date": _NOW.isoformat(),
        "end_date": (_NOW + timedelta(days=1)).isoformat(),
    }
    body.update(overrides)
    return body


# ── GET /calendar/events ──────────────────────────────────────


@pytest.mark.asyncio
async def test_tecnico_lista_eventos(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    event = _mock_event()
    creator = _mock_user(UserRole.admin, user_id=_CREATOR_ID)
    # 1ª query: eventos · 2ª query: autores
    app.dependency_overrides[get_db] = _db_override([event], [creator])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/calendar/events")

    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["creator_name"] == creator.name


@pytest.mark.asyncio
async def test_lista_eventos_filtrando_por_mes(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override([], [])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/calendar/events?year=2026&month=8")

    assert r.status_code == 200
    assert r.json()["total"] == 0


@pytest.mark.asyncio
async def test_lista_eventos_em_dezembro_vira_o_ano(patch_redis):
    """Dezembro precisa terminar em janeiro do ano seguinte."""
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override([], [])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/calendar/events?year=2026&month=12")

    assert r.status_code == 200


@pytest.mark.asyncio
async def test_cliente_nao_acessa_a_agenda(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.client))
    app.dependency_overrides[get_db] = _db_override([])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/calendar/events")

    assert r.status_code == 403


# ── POST /calendar/events ─────────────────────────────────────


@pytest.mark.asyncio
async def test_criar_evento(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    app.dependency_overrides[get_db] = _db_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/calendar/events", json=_event_body())

    assert r.status_code == 201
    assert r.json()["title"] == "Treinamento de bafômetros"


@pytest.mark.asyncio
async def test_criar_evento_com_fim_antes_do_inicio_e_rejeitado(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override(None)

    body = _event_body(end_date=(_NOW - timedelta(days=2)).isoformat())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/calendar/events", json=body)

    assert r.status_code == 422
    assert "data de fim" in r.json()["detail"]


@pytest.mark.asyncio
async def test_cliente_nao_cria_evento(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.client))
    app.dependency_overrides[get_db] = _db_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/calendar/events", json=_event_body())

    assert r.status_code == 403


# ── PATCH /calendar/events/{id} ───────────────────────────────


@pytest.mark.asyncio
async def test_editar_evento(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    event = _mock_event()
    creator = _mock_user(UserRole.admin, user_id=_CREATOR_ID)
    # 1ª query: evento · 2ª query: autor
    app.dependency_overrides[get_db] = _db_override(event, creator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(
            f"/api/v1/calendar/events/{_EVENT_ID}",
            json={"title": "Treinamento remarcado", "color": "#dc2626"},
        )

    assert r.status_code == 200
    assert event.title == "Treinamento remarcado"
    # Este caso prendia `event.color == "#dc2626"` — a cor mandada virando a cor
    # gravada. Mudou pela regra de 15/09: a cor vem do tipo e saiu do contrato de
    # escrita. O `color` do corpo é ignorado, e o treinamento continua verde.
    assert event.color == "#047857"
    assert r.json()["color"] == "#047857"


@pytest.mark.asyncio
async def test_editar_todos_os_campos_do_evento(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    event = _mock_event(created_by=None)
    app.dependency_overrides[get_db] = _db_override(event)

    novo_inicio = _NOW + timedelta(days=7)
    novo_fim = _NOW + timedelta(days=8)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(
            f"/api/v1/calendar/events/{_EVENT_ID}",
            json={
                "title": "Reunião de equipe",
                "description": "Pauta: metas do trimestre",
                "event_type": "meeting",
                "color": "#2563eb",
                "start_date": novo_inicio.isoformat(),
                "end_date": novo_fim.isoformat(),
            },
        )

    assert r.status_code == 200
    assert event.description == "Pauta: metas do trimestre"
    assert event.event_type == CalendarEventType.meeting
    assert event.start_date == novo_inicio
    assert event.end_date == novo_fim


@pytest.mark.asyncio
async def test_editar_evento_inexistente_retorna_404(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(f"/api/v1/calendar/events/{uuid.uuid4()}", json={"title": "X"})

    assert r.status_code == 404
    assert "não encontrado" in r.json()["detail"]


@pytest.mark.asyncio
async def test_editar_evento_invertendo_as_datas_e_rejeitado(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    event = _mock_event()
    app.dependency_overrides[get_db] = _db_override(event)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(
            f"/api/v1/calendar/events/{_EVENT_ID}",
            json={"end_date": (_NOW - timedelta(days=3)).isoformat()},
        )

    assert r.status_code == 422


# ── DELETE /calendar/events/{id} ──────────────────────────────


@pytest.mark.asyncio
async def test_excluir_evento(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    app.dependency_overrides[get_db] = _db_override(_mock_event())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.delete(f"/api/v1/calendar/events/{_EVENT_ID}")

    assert r.status_code == 204


@pytest.mark.asyncio
async def test_excluir_evento_inexistente_retorna_404(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.delete(f"/api/v1/calendar/events/{uuid.uuid4()}")

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_cliente_nao_exclui_evento(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.client))
    app.dependency_overrides[get_db] = _db_override(_mock_event())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.delete(f"/api/v1/calendar/events/{_EVENT_ID}")

    assert r.status_code == 403


# ── Nulo explicito no PATCH ─────────────────────────────────


@pytest.mark.asyncio
async def test_descricao_nula_apaga_a_descricao(patch_redis):
    """Limpar o campo de descrição precisa apagar o texto.

    O front manda `description.trim() || null` — nulo explícito — quando a
    pessoa esvazia o campo. O router testava `body.description is not None`,
    que não distingue "campo ausente" de "campo enviado como nulo": o nulo era
    ignorado, o texto antigo ficava no banco e reaparecia no próximo
    carregamento, como se a edição não tivesse acontecido.
    """
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    event = _mock_event(created_by=None)
    app.dependency_overrides[get_db] = _db_override(event)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(f"/api/v1/calendar/events/{_EVENT_ID}", json={"description": None})

    assert r.status_code == 200
    assert event.description is None


@pytest.mark.asyncio
async def test_descricao_ausente_nao_e_apagada(patch_redis):
    """A correção não pode transformar PATCH em PUT.

    Quem edita só o título não está pedindo para apagar a descrição — e um
    `event.description = body.description` incondicional faria exatamente
    isso, trocando um bug por outro pior.
    """
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    event = _mock_event(created_by=None)
    app.dependency_overrides[get_db] = _db_override(event)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(
            f"/api/v1/calendar/events/{_EVENT_ID}", json={"title": "Só o título mudou"}
        )

    assert r.status_code == 200
    assert event.title == "Só o título mudou"
    assert event.description == "Sala 201", "a descrição sumiu sem ninguém ter pedido"


@pytest.mark.asyncio
async def test_nulo_em_campo_not_null_continua_ignorado(patch_redis):
    """Só `description` é nullable no modelo (models.py:873-893).

    `title`, `event_type`, `color`, `start_date` e `end_date` são NOT NULL —
    para eles, ignorar o nulo está certo. Este teste existe para reprovar quem
    "uniformizar" os seis campos: aceitar nulo neles trocaria um bug de
    usabilidade por um erro de integridade no banco.
    """
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    event = _mock_event(created_by=None)
    app.dependency_overrides[get_db] = _db_override(event)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(
            f"/api/v1/calendar/events/{_EVENT_ID}",
            json={"title": None, "color": None, "event_type": None},
        )

    assert r.status_code == 200
    assert event.title == "Treinamento de bafômetros"
    assert event.color == "#047857"
    assert event.event_type == CalendarEventType.training


# ── Horário e dia inteiro ─────────────────────────────────────
#
# A agenda sempre PÔDE guardar hora: `start_date` e `end_date` são
# `TIMESTAMPTZ` desde que a tabela nasceu. O que faltava é que a tela só tinha
# campo de data e mandava `T00:00:00Z` / `T23:59:59Z` — todo evento era de dia
# inteiro por convenção, sem nada dizendo isso.
#
# A chave `all_day` dá nome à convenção. Quando ligada, a API DERIVA as bordas
# do dia e descarta a hora recebida; quando desligada, a hora atravessa intacta.


@pytest.mark.asyncio
async def test_dia_inteiro_descarta_a_hora_e_grava_as_bordas_do_dia(patch_redis):
    """A hora que veio junto não sobrevive — senão o registro se contradiz."""
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override(None)

    body = _event_body(
        start_date="2026-01-15T14:30:00Z",
        end_date="2026-01-15T17:00:00Z",
    )
    body["all_day"] = True

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/calendar/events", json=body)

    assert r.status_code == 201
    corpo = r.json()
    assert corpo["all_day"] is True
    assert corpo["start_date"].startswith("2026-01-15T00:00:00")
    assert "23:59:59.999999" in corpo["end_date"]


@pytest.mark.asyncio
async def test_evento_com_horario_guarda_a_hora_exata(patch_redis):
    """O outro lado da chave: sem `all_day`, nada é derivado."""
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override(None)

    body = _event_body(
        start_date="2026-01-15T14:30:00Z",
        end_date="2026-01-15T17:00:00Z",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/calendar/events", json=body)

    assert r.status_code == 201
    corpo = r.json()
    assert corpo["all_day"] is False
    assert corpo["start_date"].startswith("2026-01-15T14:30:00")
    assert corpo["end_date"].startswith("2026-01-15T17:00:00")


@pytest.mark.asyncio
async def test_evento_atravessa_a_virada_do_dia(patch_redis):
    """22:00 de um dia até 02:00 do seguinte: aceito, e as duas datas ficam.

    É o caso que o desenho pediu. Antes da hora existir ele nem era
    expressável: dois campos de data davam "dia 31 ao dia 1º", que a tela
    desenhava como dois dias inteiros.
    """
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override(None)

    body = _event_body(
        start_date="2026-01-31T22:00:00Z",
        end_date="2026-02-01T02:00:00Z",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/calendar/events", json=body)

    assert r.status_code == 201
    corpo = r.json()
    assert corpo["start_date"].startswith("2026-01-31T22:00:00")
    assert corpo["end_date"].startswith("2026-02-01T02:00:00")


@pytest.mark.asyncio
async def test_fim_igual_ao_inicio_e_recusado(patch_redis):
    """Evento de duração zero não existe.

    Com data-só isto nunca acontecia — a tela mandava 00:00 e 23:59, sempre
    diferentes. Com hora, o mesmo instante nos dois campos passa a ser
    digitável, e `<` deixava passar.
    """
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override(None)

    body = _event_body(
        start_date="2026-01-15T14:30:00Z",
        end_date="2026-01-15T14:30:00Z",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/calendar/events", json=body)

    assert r.status_code == 422
    assert "posterior" in r.json()["detail"]


@pytest.mark.asyncio
async def test_dia_inteiro_de_um_dia_so_nao_cai_na_recusa_de_duracao_zero(patch_redis):
    """O caso que prende a ORDEM entre derivar e validar.

    Um dia inteiro de um dia só chega com início e fim na MESMA data — iguais,
    portanto. Validar antes de derivar recusaria o evento mais comum da agenda
    com a mensagem de duração zero, e o defeito só apareceria em produção, na
    primeira pessoa que marcasse um treinamento de um dia.
    """
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override(None)

    body = _event_body(
        start_date="2026-01-15T00:00:00Z",
        end_date="2026-01-15T00:00:00Z",
    )
    body["all_day"] = True

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/calendar/events", json=body)

    assert r.status_code == 201, r.json()
    assert "23:59:59.999999" in r.json()["end_date"]


@pytest.mark.asyncio
async def test_ligar_dia_inteiro_na_edicao_reescreve_as_horas(patch_redis):
    """Ligar a chave sem mandar data nenhuma precisa alcançar as horas antigas.

    Senão a coluna diria 14:30 e a chave diria dia inteiro, e o registro
    passaria a se contradizer — quem lesse a coluna sem ler a chave veria um
    evento de meia tarde.
    """
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    event = _mock_event(created_by=None, all_day=False)
    event.start_date = datetime(2026, 1, 15, 14, 30, tzinfo=UTC)
    event.end_date = datetime(2026, 1, 15, 17, 0, tzinfo=UTC)
    app.dependency_overrides[get_db] = _db_override(event)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(f"/api/v1/calendar/events/{_EVENT_ID}", json={"all_day": True})

    assert r.status_code == 200
    assert event.start_date == datetime(2026, 1, 15, tzinfo=UTC)
    assert event.end_date == datetime(2026, 1, 15, 23, 59, 59, 999999, tzinfo=UTC)


@pytest.mark.asyncio
async def test_fuso_desconhecido_na_consulta_e_recusado(patch_redis):
    """Recusa, e não volta calado para o padrão.

    Cair no padrão faria quem escreveu o fuso errado receber o mês de outro
    lugar e nunca descobrir: o sintoma seria "alguns eventos somem", meses
    depois, sem nada apontando para a letra trocada.
    """
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override([], [])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/calendar/events?year=2026&month=1&timezone=Marte/Olimpo")

    assert r.status_code == 422
    assert "Marte/Olimpo" in r.json()["detail"]


@pytest.mark.asyncio
async def test_fuso_conhecido_na_consulta_e_aceito(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override([], [])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/calendar/events?year=2026&month=1&timezone=America/Sao_Paulo")

    assert r.status_code == 200


# ── A tela antiga, lida corretamente ──────────────────────────
#
# A tela no ar ainda não conhece `all_day`, e manda `T00:00:00Z` / `T23:59:59Z`
# a partir de dois campos de data. Isso É dia inteiro por convenção — e o padrão
# `all_day=False` do #16 gravava cada um desses eventos como evento COM horário,
# que a tela nova desenharia às 21:00 do dia anterior.
#
# A regra: `all_day` AUSENTE + a pegada exata = dia inteiro. Explícito vence
# sempre, nos dois sentidos.


def _corpo_da_tela_antiga(inicio="2026-01-15", fim="2026-01-15"):
    """O payload exato que `CalendarPage.tsx:153-161` monta hoje."""
    corpo = _event_body(start_date=f"{inicio}T00:00:00Z", end_date=f"{fim}T23:59:59Z")
    assert "all_day" not in corpo
    return corpo


@pytest.mark.asyncio
async def test_post_da_tela_antiga_grava_dia_inteiro(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/calendar/events", json=_corpo_da_tela_antiga())

    assert r.status_code == 201
    corpo = r.json()
    assert corpo["all_day"] is True
    # E as bordas passam a ser as derivadas: o último microssegundo do dia.
    assert "23:59:59.999999" in corpo["end_date"]


@pytest.mark.asyncio
async def test_post_da_tela_antiga_de_varios_dias_grava_dia_inteiro(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/api/v1/calendar/events",
            json=_corpo_da_tela_antiga(inicio="2026-01-15", fim="2026-01-17"),
        )

    assert r.status_code == 201
    assert r.json()["all_day"] is True
    assert r.json()["end_date"].startswith("2026-01-17T23:59:59.999999")


@pytest.mark.asyncio
async def test_all_day_false_explicito_vence_a_pegada(patch_redis):
    """Quem manda o campo decide. A inferência só existe para quem não sabe dele.

    Sem isto, um cliente que conhece a chave e quer mesmo um evento das 00:00
    às 23:59:59 teria a escolha dele reescrita por uma regra feita para outro
    cliente.
    """
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override(None)

    corpo = _corpo_da_tela_antiga()
    corpo["all_day"] = False

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/calendar/events", json=corpo)

    assert r.status_code == 201
    assert r.json()["all_day"] is False
    assert r.json()["end_date"].startswith("2026-01-15T23:59:59")
    assert "999999" not in r.json()["end_date"]


@pytest.mark.asyncio
async def test_evento_com_horario_sem_a_chave_continua_com_horario(patch_redis):
    """A inferência não pega o que não tem a pegada."""
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override(None)

    corpo = _event_body(start_date="2026-01-15T09:00:00Z", end_date="2026-01-15T17:00:00Z")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/calendar/events", json=corpo)

    assert r.status_code == 201
    assert r.json()["all_day"] is False
    assert r.json()["start_date"].startswith("2026-01-15T09:00:00")


@pytest.mark.asyncio
async def test_patch_da_tela_antiga_cura_evento_gravado_na_lacuna(patch_redis):
    """Um evento criado entre o deploy do #16 e este conserto tem `all_day=false`.

    A tela antiga, ao editá-lo, manda o payload inteiro de novo — com a pegada e
    sem a chave. É a chance de a linha voltar a dizer o que ela é.
    """
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    event = _mock_event(created_by=None, all_day=False)
    event.start_date = datetime(2026, 1, 15, 0, 0, 0, tzinfo=UTC)
    event.end_date = datetime(2026, 1, 15, 23, 59, 59, tzinfo=UTC)
    app.dependency_overrides[get_db] = _db_override(event)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(f"/api/v1/calendar/events/{_EVENT_ID}", json=_corpo_da_tela_antiga())

    assert r.status_code == 200
    assert event.all_day is True
    assert event.end_date == datetime(2026, 1, 15, 23, 59, 59, 999999, tzinfo=UTC)


@pytest.mark.asyncio
async def test_patch_sem_datas_nao_infere_nada(patch_redis):
    """A pegada é lida no que CHEGOU, não no que já estava no banco.

    Trocar só o título de um evento gravado na lacuna não pode ligar a chave: a
    convenção é da requisição, e uma edição que não mandou data nenhuma não falou
    convenção nenhuma. Ler a linha do banco transformaria qualquer edição num
    backfill escondido — e a regra do projeto é que backfill não se esconde.
    """
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    event = _mock_event(created_by=None, all_day=False)
    event.start_date = datetime(2026, 1, 15, 0, 0, 0, tzinfo=UTC)
    event.end_date = datetime(2026, 1, 15, 23, 59, 59, tzinfo=UTC)
    app.dependency_overrides[get_db] = _db_override(event)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(f"/api/v1/calendar/events/{_EVENT_ID}", json={"title": "Novo título"})

    assert r.status_code == 200
    assert event.all_day is False
    assert event.end_date == datetime(2026, 1, 15, 23, 59, 59, tzinfo=UTC)


@pytest.mark.asyncio
async def test_patch_com_all_day_false_explicito_vence_a_pegada(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    event = _mock_event(created_by=None, all_day=True)
    app.dependency_overrides[get_db] = _db_override(event)

    corpo = _corpo_da_tela_antiga()
    corpo["all_day"] = False

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(f"/api/v1/calendar/events/{_EVENT_ID}", json=corpo)

    assert r.status_code == 200
    assert event.all_day is False


# ── A cor vem do tipo ─────────────────────────────────────────
#
# Havia duas fontes para a mesma coisa. O mapa por tipo no front só sugeria a
# cor na criação; o desenho lia a coluna, que guardava o que tivesse sido
# clicado. Em produção, 15/09: cinco dos seis eventos numa cor diferente da do
# tipo — treinamento e reunião no mesmo azul, feriado em cinza.
#
# A resposta passa a DERIVAR a cor do tipo e nunca ler a coluna. A coluna
# continua existindo e é gravada a partir do mapa, para quem lê o banco direto
# e para um rollback do código — mas é cópia, não fonte.


def _sessao_que_guarda(gravados: list, *respostas):
    """A sessão do arreio, com o `add` anotando o que a rota gravou."""
    sessao = _db_sequence(*respostas)
    sessao.add = lambda objeto: gravados.append(objeto)

    async def _gen():
        yield sessao

    return _gen


@pytest.mark.asyncio
async def test_cor_enviada_no_post_e_ignorada_e_a_do_tipo_vence(patch_redis):
    """A tela no ar sempre manda `color`. Ignorar, e não recusar, é de propósito.

    Recusar com 422 quebraria a criação de evento na tela antiga até o round do
    frontend — a mesma armadilha do #16. E ignorar não fica escondido: a resposta
    da mesma requisição já traz a cor que valeu.
    """
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    gravados: list = []
    app.dependency_overrides[get_db] = _sessao_que_guarda(gravados, None)

    corpo = _event_body(event_type="meeting", color="#eab308")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/calendar/events", json=corpo)

    assert r.status_code == 201
    assert r.json()["color"] == "#2563eb"
    # E a coluna recebe a do tipo, não a clicada.
    assert gravados[0].color == "#2563eb"


@pytest.mark.asyncio
async def test_feriado_criado_sem_cor_nasce_vermelho_e_nao_indigo(patch_redis):
    """O padrão antigo era `#4f46e5` para qualquer tipo."""
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    gravados: list = []
    app.dependency_overrides[get_db] = _sessao_que_guarda(gravados, None)

    corpo = _event_body(event_type="holiday")
    corpo.pop("color")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/calendar/events", json=corpo)

    assert r.status_code == 201
    assert r.json()["color"] == "#dc2626"
    assert gravados[0].color == "#dc2626"


@pytest.mark.asyncio
async def test_trocar_o_tipo_na_edicao_leva_a_cor_junto(patch_redis):
    """Na tela, a trava de cor ficava ligada em toda edição — trocar o tipo nunca
    mudava a cor. Aqui a cor não tem como ficar para trás."""
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    event = _mock_event(created_by=None)
    event.event_type = CalendarEventType.meeting
    event.color = "#2563eb"
    app.dependency_overrides[get_db] = _db_override(event)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(f"/api/v1/calendar/events/{_EVENT_ID}", json={"event_type": "deadline"})

    assert r.status_code == 200
    assert r.json()["color"] == "#b45309"
    assert event.color == "#b45309"


@pytest.mark.asyncio
async def test_mandar_so_a_cor_na_edicao_nao_muda_nada(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    event = _mock_event(created_by=None)
    event.event_type = CalendarEventType.training
    event.color = "#047857"
    app.dependency_overrides[get_db] = _db_override(event)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(f"/api/v1/calendar/events/{_EVENT_ID}", json={"color": "#ec4899"})

    assert r.status_code == 200
    assert r.json()["color"] == "#047857"
    assert event.color == "#047857"


@pytest.mark.asyncio
async def test_a_listagem_desfaz_a_divergencia_sem_reescrever_linha(patch_redis):
    """Os quatro valores DE PRODUÇÃO de 15/09, com a coluna divergindo do tipo.

    É este caso que autoriza o "sem backfill": a coluna continua com o valor
    antigo, e a resposta já sai com a cor do tipo. A divergência some no deploy,
    sem nenhuma linha tocada.
    """
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))

    def _divergente(tipo, cor_na_coluna):
        e = _mock_event(created_by=None)
        e.id = uuid.uuid4()
        e.event_type = tipo
        e.color = cor_na_coluna
        return e

    linhas = [
        _divergente(CalendarEventType.event, "#f97316"),
        _divergente(CalendarEventType.meeting, "#eab308"),
        _divergente(CalendarEventType.training, "#2563eb"),
        _divergente(CalendarEventType.holiday, "#64748b"),
    ]
    app.dependency_overrides[get_db] = _db_override(linhas, [])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/calendar/events")

    assert r.status_code == 200
    cores = {item["event_type"]: item["color"] for item in r.json()["items"]}
    assert cores == {
        "event": "#4f46e5",
        "meeting": "#2563eb",
        "training": "#047857",
        "holiday": "#dc2626",
    }
    # E a coluna não foi reescrita pela leitura.
    assert linhas[0].color == "#f97316"


@pytest.mark.asyncio
async def test_a_tela_le_o_mapa_de_cores_da_api(patch_redis):
    """O endpoint existe para a tela não precisar de uma cópia do mapa.

    Sem ele, o modal só mostraria a cor de um tipo antes de salvar se tivesse o
    mapa escrito localmente — e a segunda fonte voltaria pela porta da frente.
    Rótulo não vem: texto é da tela.
    """
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    app.dependency_overrides[get_db] = _db_override([])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/calendar/event-types")

    assert r.status_code == 200
    assert r.json() == [
        {"value": "event", "color": "#4f46e5"},
        {"value": "meeting", "color": "#2563eb"},
        {"value": "training", "color": "#047857"},
        {"value": "deadline", "color": "#b45309"},
        {"value": "holiday", "color": "#dc2626"},
    ]


@pytest.mark.asyncio
async def test_cliente_nao_le_o_mapa_de_cores(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.client))
    app.dependency_overrides[get_db] = _db_override([])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/calendar/event-types")

    assert r.status_code == 403


def test_a_cor_nao_esta_no_contrato_de_escrita():
    """ "Sai do contrato" preso no contrato, e não só no comportamento.

    Um mutante que devolvia `color` ao schema de criação SOBREVIVEU aos casos de
    comportamento: o router ignora o campo e a resposta é calculada, então nada
    muda por fora. Mas o OpenAPI voltaria a anunciar uma entrada que não faz nada
    — e a tela nova, lendo esse contrato, manteria as fichas de cor. Bastaria uma
    linha no router para a segunda fonte voltar.
    """
    esquemas = app.openapi()["components"]["schemas"]

    assert "color" not in esquemas["CalendarEventCreate"]["properties"]
    assert "color" not in esquemas["CalendarEventUpdate"]["properties"]
    # E na resposta ela continua — derivada, mas presente.
    assert "color" in esquemas["CalendarEventResponse"]["properties"]
