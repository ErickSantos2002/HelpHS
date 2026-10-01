"""
O efeito externo: o que o HelpHS faz com cada resposta do fornecedor.

Este arquivo cobre a metade da telefonia que a 2C.2 deliberadamente deixou de
fora — a conversa com a API4COM e a leitura do que ela devolveu.

**Nenhum teste aqui alcança a API4COM.** O dublê é posto no boundary do
transporte (`ligacao.api4com.create_call`), e há um caso explícito garantindo
que nenhum socket HTTP é aberto por baixo.

A regra que organiza tudo: cada `except` traduz uma afirmação sobre o EFEITO,
não sobre o erro.

    rejected       o fornecedor respondeu recusando. Nada tocou.
    unavailable    a conexão falhou antes de a requisição ser escrita.
    indeterminate  pode ter tocado e não sabemos.

`indeterminate` é o destino de tudo o que não se encaixa nos dois primeiros —
inclusive exceção inesperada. Conservador de propósito: depois de cruzar a
fronteira, o que não se sabe explicar não pode ser tratado como "não aconteceu".
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models.models import CallCreationStatus, TicketStatus, UserRole, UserStatus
from app.services import ligacao
from app.services.api4com import (
    Api4ComCreateCallResult,
    Api4ComDesligadaError,
    Api4ComIndisponivelError,
    Api4ComRecusadaError,
    Api4ComResultadoIndeterminadoError,
)

_RAMAL = "1019"  # o ramal real da Suelen, provisionado em 24/09/2026
_TELEFONE = "+5548933328530"
_ID_DO_FORNECEDOR = "1PkXhmBsYAvr9legLB2d7BimT0Q"


class _RedisFalso:
    def __init__(self) -> None:
        self.dados: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def set(self, chave, valor, nx=False, ex=None):
        if nx and chave in self.dados:
            return None
        self.dados[chave] = valor
        if ex is not None:
            self.ttls[chave] = ex
        return True

    async def incr(self, chave):
        atual = int(self.dados.get(chave, 0)) + 1
        self.dados[chave] = str(atual)
        return atual

    async def expire(self, chave, segundos):
        self.ttls[chave] = segundos
        return True

    async def eval(self, script, numkeys, chave, arg):
        if self.dados.get(chave) == arg:
            del self.dados[chave]
            return 1
        return 0


def _ator(ramal=_RAMAL):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.role = UserRole.technician
    u.status = UserStatus.active
    u.api4com_extension = ramal
    return u


def _cliente(telefone=_TELEFONE):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.role = UserRole.client
    u.status = UserStatus.active
    u.phone = telefone
    return u


def _ticket():
    t = MagicMock()
    t.id = uuid.uuid4()
    t.status = TicketStatus.open
    t.creator_id = uuid.uuid4()
    return t


class _Sessao:
    """Sessão falsa que guarda a ORDEM dos commits e o estado em cada um.

    A ordem é o desenho desta fase: `pending` durável, depois `dispatching`
    durável, e só então a chamada. Um teste que só olhasse o estado final não
    distinguiria isso de tudo gravado no fim.
    """

    def __init__(self, ticket, destinatario):
        from app.models.models import TicketCall

        self._fila = [ticket, destinatario]
        self._n = 0
        self.adicionados: list[object] = []
        self.refresh = AsyncMock()

        async def _flush():
            # O que o banco faria: `id` vem do `default=uuid.uuid4` (lado
            # Python, aplicado no flush) e `created_at` do `server_default`.
            # Sem isto o `TicketCallResponse` recusa a tentativa por campos
            # nulos — e o defeito seria do dublê, não do produto.
            from datetime import UTC, datetime

            if self.tentativa is not None:
                if self.tentativa.id is None:
                    self.tentativa.id = uuid.uuid4()
                if self.tentativa.created_at is None:
                    self.tentativa.created_at = datetime.now(UTC)

        self.flush = AsyncMock(side_effect=_flush)
        self.estados_commitados: list[str] = []
        self.tentativa = None

        def _add(obj):
            # `db.add` recebe a tentativa E a linha de histórico. Só a primeira
            # tem estado para observar.
            self.adicionados.append(obj)
            if isinstance(obj, TicketCall):
                self.tentativa = obj

        self.add = _add

        async def _commit():
            if self.tentativa is not None:
                self.estados_commitados.append(self.tentativa.creation_status)

        self.commit = AsyncMock(side_effect=_commit)

    async def execute(self, *a, **k):
        r = MagicMock()
        if self._n < len(self._fila):
            r.scalar_one_or_none.return_value = self._fila[self._n]
            r.scalars.return_value.first.return_value = None
        else:
            r.scalar_one_or_none.return_value = None
            r.scalars.return_value.first.return_value = None
        self._n += 1
        return r


@pytest.fixture()
def redis_falso():
    r = _RedisFalso()

    async def _get():
        return r

    with patch("app.services.ligacao.get_redis", new=_get):
        yield r


@pytest.fixture()
def liga(request):
    """Liga a flag e substitui o transporte. `request.param` define a resposta."""
    from app.core.config import get_settings as real

    base = real()
    comportamento = getattr(request, "param", None) or {
        "return_value": Api4ComCreateCallResult(status_code=200, provider_call_id=_ID_DO_FORNECEDOR)
    }
    with (
        patch("app.services.ligacao.get_settings") as cfg,
        patch("app.services.ligacao.api4com.create_call", new=AsyncMock(**comportamento)) as chama,
    ):
        cfg.return_value = SimpleNamespace(
            api4com_enabled=True,
            api4com_lock_ttl_seconds=base.api4com_lock_ttl_seconds,
            api4com_calls_per_actor_per_hour=base.api4com_calls_per_actor_per_hour,
            api4com_called_format=base.api4com_called_format,
        )
        yield chama


async def _liga_para(sessao, ator=None, ticket=None):
    ticket = ticket or _ticket()
    return await ligacao.inicia_ligacao(sessao, ticket_id=ticket.id, ator=ator or _ator())


def _monta(destinatario=None):
    t = _ticket()
    s = _Sessao(t, destinatario or _cliente())
    return t, s


# ── O caminho feliz ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_sucesso_persiste_id_do_fornecedor_e_status_http(redis_falso, liga):
    t, s = _monta()
    tentativa = await _liga_para(s, ticket=t)

    assert tentativa.creation_status == CallCreationStatus.confirmed.value
    assert tentativa.provider_call_id == _ID_DO_FORNECEDOR
    assert tentativa.provider_http_status == 200


@pytest.mark.asyncio
async def test_o_id_do_fornecedor_e_opaco(redis_falso):
    """Nem UUID, nem número: string como veio. São 27 caracteres base62 aqui."""
    from app.core.config import get_settings as real

    base = real()
    esquisito = "  0700-abc_XYZ  "
    with (
        patch("app.services.ligacao.get_settings") as cfg,
        patch(
            "app.services.ligacao.api4com.create_call",
            new=AsyncMock(
                return_value=Api4ComCreateCallResult(status_code=200, provider_call_id=esquisito)
            ),
        ),
    ):
        cfg.return_value = SimpleNamespace(
            api4com_enabled=True,
            api4com_lock_ttl_seconds=base.api4com_lock_ttl_seconds,
            api4com_calls_per_actor_per_hour=base.api4com_calls_per_actor_per_hour,
            api4com_called_format=base.api4com_called_format,
        )
        t, s = _monta()
        tentativa = await _liga_para(s, ticket=t)

    assert tentativa.provider_call_id == esquisito, "o identificador foi transformado"
    assert isinstance(tentativa.provider_call_id, str)


# ── A ordem, que é o desenho ─────────────────────────────────


@pytest.mark.asyncio
async def test_pending_e_dispatching_ficam_duraveis_antes_da_chamada(redis_falso, liga):
    """Três commits, nesta ordem. É o que impede a ambiguidade do `pending`."""
    t, s = _monta()
    await _liga_para(s, ticket=t)

    assert s.estados_commitados == [
        CallCreationStatus.pending.value,
        CallCreationStatus.dispatching.value,
        CallCreationStatus.confirmed.value,
    ]


@pytest.mark.asyncio
async def test_a_chamada_so_acontece_depois_do_despacho_commitado(redis_falso):
    """A janela de crash: se o processo morrer entre o POST e a resposta, a
    linha já precisa estar `dispatching` no banco."""
    from app.core.config import get_settings as real

    base = real()
    estado_no_momento_da_chamada = {}

    t, s = _monta()

    async def _espia(**kwargs):
        estado_no_momento_da_chamada["estado"] = s.tentativa.creation_status
        estado_no_momento_da_chamada["commits"] = list(s.estados_commitados)
        return Api4ComCreateCallResult(status_code=200, provider_call_id=_ID_DO_FORNECEDOR)

    with (
        patch("app.services.ligacao.get_settings") as cfg,
        patch("app.services.ligacao.api4com.create_call", new=AsyncMock(side_effect=_espia)),
    ):
        cfg.return_value = SimpleNamespace(
            api4com_enabled=True,
            api4com_lock_ttl_seconds=base.api4com_lock_ttl_seconds,
            api4com_calls_per_actor_per_hour=base.api4com_calls_per_actor_per_hour,
            api4com_called_format=base.api4com_called_format,
        )
        await _liga_para(s, ticket=t)

    assert estado_no_momento_da_chamada["estado"] == CallCreationStatus.dispatching.value
    assert (
        CallCreationStatus.dispatching.value in estado_no_momento_da_chamada["commits"]
    ), "o despacho não estava commitado quando a chamada saiu"


# ── Classificação das respostas ──────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("liga", [{"side_effect": Api4ComRecusadaError(400)}], indirect=True)
async def test_4xx_vira_rejected_com_o_status_http(redis_falso, liga):
    """O fornecedor respondeu recusando a REQUISIÇÃO. Nada tocou."""
    t, s = _monta()
    tentativa = await _liga_para(s, ticket=t)

    assert tentativa.creation_status == CallCreationStatus.rejected.value
    assert tentativa.provider_http_status == 400
    assert tentativa.provider_call_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "liga", [{"side_effect": Api4ComIndisponivelError("sem conexao")}], indirect=True
)
async def test_falha_de_conexao_vira_unavailable(redis_falso, liga):
    """Única categoria em que se pode afirmar que NÃO houve efeito externo."""
    t, s = _monta()
    tentativa = await _liga_para(s, ticket=t)

    assert tentativa.creation_status == CallCreationStatus.unavailable.value
    assert tentativa.provider_call_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "liga", [{"side_effect": Api4ComResultadoIndeterminadoError("timeout")}], indirect=True
)
async def test_resposta_ambigua_vira_indeterminate(redis_falso, liga):
    """Pode ter tocado. É este estado que bloqueia nova tentativa por 5 min."""
    t, s = _monta()
    tentativa = await _liga_para(s, ticket=t)

    assert tentativa.creation_status == CallCreationStatus.indeterminate.value
    assert tentativa.provider_call_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("liga", [{"side_effect": RuntimeError("surpresa")}], indirect=True)
async def test_excecao_inesperada_vira_indeterminate_e_nao_fica_pending(redis_falso, liga):
    """O pior caso: nem o transporte soube dizer o que houve.

    A tentativa NÃO pode ficar eternamente `pending` nem `dispatching` — a
    primeira mentiria dizendo que nada saiu; a segunda pareceria uma execução
    em curso para sempre.
    """
    t, s = _monta()
    tentativa = await _liga_para(s, ticket=t)

    assert tentativa.creation_status == CallCreationStatus.indeterminate.value
    assert tentativa.creation_status != CallCreationStatus.pending.value
    assert tentativa.creation_status != CallCreationStatus.dispatching.value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "liga", [{"side_effect": Api4ComDesligadaError("flag caiu")}], indirect=True
)
async def test_flag_caindo_no_meio_vira_unavailable(redis_falso, liga):
    """A flag é conferida no início; se mudar no caminho, não houve efeito."""
    t, s = _monta()
    tentativa = await _liga_para(s, ticket=t)

    assert tentativa.creation_status == CallCreationStatus.unavailable.value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "liga",
    [
        {"side_effect": Api4ComRecusadaError(400)},
        {"side_effect": Api4ComIndisponivelError("x")},
        {"side_effect": Api4ComResultadoIndeterminadoError("x")},
        {"side_effect": RuntimeError("x")},
    ],
    indirect=True,
)
async def test_nenhum_desfecho_repete_a_chamada(redis_falso, liga):
    """Sem retry automático, em nenhum caminho."""
    t, s = _monta()
    await _liga_para(s, ticket=t)
    assert liga.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "liga",
    [
        {"side_effect": Api4ComRecusadaError(400)},
        {"side_effect": Api4ComResultadoIndeterminadoError("x")},
        {"side_effect": RuntimeError("x")},
    ],
    indirect=True,
)
async def test_o_lock_e_liberado_em_qualquer_desfecho(redis_falso, liga):
    t, s = _monta()
    await _liga_para(s, ticket=t)
    assert f"{ligacao._PREFIXO_LOCK}{t.id}" not in redis_falso.dados


# ── O payload ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_o_payload_sai_do_banco_e_das_politicas(redis_falso, liga):
    t, s = _monta()
    await _liga_para(s, ator=_ator(ramal="1019"), ticket=t)

    enviado = liga.await_args.kwargs
    assert enviado["extension"] == "1019", "o ramal não veio do ator"
    assert enviado["caller"] == "1019", "o caller não seguiu a política"
    assert enviado["called"] == "48933328530", "o called não passou pela política"
    assert set(enviado) == {"caller", "called", "extension", "ticket_call_id"}


@pytest.mark.asyncio
async def test_o_ticket_call_id_enviado_e_o_da_linha_criada(redis_falso, liga):
    """A correlação da Fase 2D.2, comparada contra a LINHA e não contra literal.

    Este é o teste que importa da fase inteira. Ele não confere que "existe
    alguma coisa" no `ticket_call_id`: ele exige o `id` exato da tentativa que a
    orquestração acabou de criar. Um literal repetido aqui passaria mesmo se o
    código mandasse o UUID errado — por exemplo o `ticket_id`, que também é um
    UUID e está à mão no mesmo escopo.
    """
    t, s = _monta()
    tentativa = await _liga_para(s, ticket=t)

    enviado = liga.await_args.kwargs["ticket_call_id"]
    assert enviado == tentativa.id
    # E não é o do chamado: os dois são UUID, e trocar um pelo outro não levanta
    # erro nenhum — só faz a reconciliação apontar para a linha errada.
    assert enviado != t.id


@pytest.mark.asyncio
async def test_a_correlacao_e_opaca_por_construcao(redis_falso, liga):
    """O que viaja é um UUID, e é por isso que não pode carregar PII.

    ⚠️ Aqui NÃO se procura telefone nem e-mail dentro do valor, e a razão é que
    tal teste seria intermitente: "1019" são quatro dígitos hexadecimais válidos
    e podem aparecer por acaso num UUID aleatório. A garantia é ESTRUTURAL — se
    o tipo é `uuid.UUID` e o valor é o `id` da linha, não existe caminho por onde
    dado de pessoa entre. É o tipo que protege, não a varredura de texto.
    """
    t, s = _monta()
    tentativa = await _liga_para(s, ator=_ator(ramal="1019"), ticket=t)

    enviado = liga.await_args.kwargs["ticket_call_id"]
    assert isinstance(enviado, uuid.UUID), "a interface interna deixou de ser tipada"
    assert enviado == tentativa.id


def test_caller_segue_o_extension_por_politica_explicita():
    """Decisão de integração, com um lugar e um nome — não repetição inline."""
    assert ligacao._resolve_caller("1019") == "1019"
    assert ligacao._resolve_caller("0700") == "0700"


def test_called_no_formato_nacional_tira_o_ddi():
    assert ligacao._formata_called_api4com("+5548933328530") == "48933328530"
    assert ligacao._formata_called_api4com("+5581999999999") == "81999999999"


def test_called_no_formato_e164_preserva():
    from app.core.config import get_settings as real

    base = real()
    with patch("app.services.ligacao.get_settings") as cfg:
        cfg.return_value = SimpleNamespace(api4com_called_format="e164")
        assert ligacao._formata_called_api4com("+5548933328530") == "+5548933328530"
    assert base.api4com_called_format == "nacional", "o padrão do projeto mudou sem aviso"


def test_numero_estrangeiro_nao_e_mutilado():
    """Só sabemos tirar o DDI brasileiro. Portugal volta como está."""
    assert ligacao._formata_called_api4com("+351912345678") == "+351912345678"


def test_a_grafia_de_called_tem_um_autor_so():
    """Concatenação espalhada seria a decisão perdendo dono."""
    import ast
    from pathlib import Path

    fonte = Path(ligacao.__file__).read_text(encoding="utf-8")
    assert fonte.count("api4com_called_format") == 1, "a política vazou para outro lugar"
    chamadas = [
        no.func.id
        for no in ast.walk(ast.parse(fonte))
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
    ]
    assert chamadas.count("_formata_called_api4com") == 1


# ── Segurança ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_flag_desligada_nao_produz_trafego_nem_tentativa(redis_falso):
    """Em produção a flag é falsa. Nada pode ser criado, nem cota consumida."""
    t, s = _monta()
    ator = _ator()

    with patch("app.services.ligacao.api4com.create_call", new=AsyncMock()) as chamada:
        with pytest.raises(HTTPException) as erro:
            await _liga_para(s, ator=ator, ticket=t)

    assert erro.value.status_code == 503
    assert chamada.await_count == 0
    assert s.adicionados == [], "criou tentativa com a telefonia desligada"
    assert redis_falso.dados == {}, "reservou o chamado ou gastou cota"


@pytest.mark.asyncio
async def test_nenhum_socket_http_e_aberto(redis_falso, liga):
    """Cinto e suspensório: o dublê está no boundary, e nada passa por baixo."""
    t, s = _monta()
    with patch("httpx.AsyncClient.send", side_effect=AssertionError("saiu HTTP de verdade!")):
        tentativa = await _liga_para(s, ticket=t)
    assert tentativa.creation_status == CallCreationStatus.confirmed.value


def test_a_resposta_publica_nao_leva_nada_do_fornecedor():
    """O conjunto EXATO de campos públicos, e a lista do que nunca pode entrar.

    ⚠️ `reason` entrou em 30/09 (Fase 2C.6b) e NÃO é exceção à regra: ele é
    vocabulário do HelpHS (`webphone_unavailable`), derivado do status do
    fornecedor e nunca igual a ele. O número do HTTP continua proibido logo
    abaixo — é isso que separa "traduzir" de "vazar".
    """
    from app.schemas.telefonia import TicketCallResponse

    campos = set(TicketCallResponse.model_fields)
    assert campos == {"id", "creation_status", "created_at", "reason"}
    for proibido in (
        "provider_call_id",
        "provider_http_status",
        "phone",
        "caller",
        "called",
        "extension",
        "metadata",
    ):
        assert proibido not in campos


def test_o_modulo_nao_loga_nada_sensivel():
    """Telefone, ramal, token e payload não podem alcançar log nenhum."""
    import ast
    from pathlib import Path

    fonte = Path(ligacao.__file__).read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    logs = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Attribute)
        and isinstance(no.func.value, ast.Name)
        and no.func.value.id == "logger"
    ]
    assert logs == [], "este módulo não deveria logar — e passou a logar"


def test_o_historico_nao_carrega_dado_sensivel():
    """O evento diz QUE houve tentativa, e mais nada."""
    import ast
    import inspect

    fonte = inspect.getsource(ligacao.inicia_ligacao)
    chamada = next(
        no
        for no in ast.walk(ast.parse(fonte))
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Name)
        and no.func.id == "registra_historico"
    )
    literais = [a.value for a in chamada.args if isinstance(a, ast.Constant)]
    assert literais == ["ligacao", None, "tentativa"], literais
    for proibido in ("phone", "telefone", "ramal", "extension", "caller", "called"):
        assert proibido not in str(literais)


# ── A rota ───────────────────────────────────────────────────


@pytest.fixture()
def _limpa_overrides():
    from app.main import app

    yield
    app.dependency_overrides.clear()


def _cliente_http(ator, sessao):
    from app.core.database import get_db
    from app.core.security import get_current_user
    from app.main import app

    async def _db():
        yield sessao

    async def _atual():
        return ator

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _atual
    from httpx import ASGITransport, AsyncClient

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_a_rota_devolve_o_minimo_e_nada_do_fornecedor(redis_falso, liga, _limpa_overrides):
    t, s = _monta()
    async with _cliente_http(_ator(), s) as http:
        resposta = await http.post(f"/api/v1/tickets/{t.id}/calls", json={})

    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    # ⚠️ `reason` entrou na Fase 2C.6b. Aqui ele vem NULO, e isso é o ponto:
    # sucesso não tem motivo de recusa para explicar.
    assert set(corpo) == {"id", "creation_status", "created_at", "reason"}
    assert corpo["creation_status"] == "confirmed"
    assert corpo["reason"] is None
    # E o identificador do fornecedor não aparece em lugar nenhum do corpo.
    assert _ID_DO_FORNECEDOR not in resposta.text
    assert _TELEFONE not in resposta.text
    assert _RAMAL not in resposta.text
    # Nem o número do HTTP do fornecedor, que é o que `reason` TRADUZ.
    assert "424" not in resposta.text
    assert "provider_http_status" not in resposta.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "campo",
    [
        "phone",
        "called",
        "caller",
        "extension",
        "metadata",
        "provider_call_id",
        "client_id",
        "user_id",
    ],
)
async def test_o_navegador_nao_escolhe_o_destino(redis_falso, liga, _limpa_overrides, campo):
    """422, e não silêncio: tentar escolher destino vira evento observável."""
    t, s = _monta()
    async with _cliente_http(_ator(), s) as http:
        resposta = await http.post(f"/api/v1/tickets/{t.id}/calls", json={campo: "1"})

    assert resposta.status_code == 422, resposta.text
    assert liga.await_count == 0, "o fornecedor foi chamado com corpo adulterado"
    assert s.adicionados == []


@pytest.mark.asyncio
async def test_cliente_nao_alcanca_a_rota(redis_falso, liga, _limpa_overrides):
    t, s = _monta()
    cliente = _ator()
    cliente.role = UserRole.client
    async with _cliente_http(cliente, s) as http:
        resposta = await http.post(f"/api/v1/tickets/{t.id}/calls", json={})

    assert resposta.status_code == 403
    assert liga.await_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "liga", [{"side_effect": Api4ComResultadoIndeterminadoError("timeout")}], indirect=True
)
async def test_resultado_indeterminado_ainda_devolve_201(redis_falso, liga, _limpa_overrides):
    """201 de propósito: 5xx aqui convidaria proxy e usuário a tentar de novo,
    e a ligação pode estar tocando neste exato momento."""
    t, s = _monta()
    async with _cliente_http(_ator(), s) as http:
        resposta = await http.post(f"/api/v1/tickets/{t.id}/calls", json={})

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["creation_status"] == "indeterminate"


# ── O motivo público da recusa (2C.6b) ───────────────────────
#
# A API4COM confirmou por escrito: ramal não registrado no SIP devolve
# HTTP 424. É a ÚNICA correspondência documentada, e por isso é a única que
# vira explicação na tela. Qualquer outro 4xx continua sem motivo — inventar
# rótulo seria publicar hipótese para quem atende.


@pytest.mark.asyncio
@pytest.mark.parametrize("liga", [{"side_effect": Api4ComRecusadaError(424)}], indirect=True)
async def test_424_vira_motivo_de_webphone_indisponivel(redis_falso, liga, _limpa_overrides):
    """O caso da fase, medido ponta a ponta pela rota."""
    t, s = _monta()
    async with _cliente_http(_ator(), s) as http:
        resposta = await http.post(f"/api/v1/tickets/{t.id}/calls", json={})

    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["creation_status"] == "rejected"
    assert corpo["reason"] == "webphone_unavailable"
    # O número do fornecedor NÃO viaja — é ele que o motivo traduz.
    assert "424" not in resposta.text
    assert "provider_http_status" not in resposta.text
    assert "SIP" not in resposta.text


@pytest.mark.asyncio
@pytest.mark.parametrize("liga", [{"side_effect": Api4ComRecusadaError(424)}], indirect=True)
async def test_424_continua_sendo_uma_tentativa_de_verdade(redis_falso, liga):
    """Motivo público não muda o que a tentativa É: linha, estado e histórico.

    Sem `provider_call_id`, porque nada foi criado do lado de lá.
    """
    from app.models.models import TicketHistory

    t, s = _monta()
    tentativa = await _liga_para(s, ticket=t)

    assert tentativa.creation_status == CallCreationStatus.rejected.value
    assert tentativa.provider_http_status == 424
    assert tentativa.provider_call_id is None
    eventos = [o for o in s.adicionados if isinstance(o, TicketHistory)]
    assert len(eventos) == 1
    assert eventos[0].field == "ligacao"
    assert eventos[0].new_value == "tentativa"


@pytest.mark.asyncio
@pytest.mark.parametrize("liga", [{"side_effect": Api4ComRecusadaError(424)}], indirect=True)
async def test_o_historico_do_424_nao_conta_o_motivo_tecnico(redis_falso, liga):
    """ "Webphone offline", "424" e "SIP" não entram no histórico do chamado.

    O histórico é lido pelo cliente. A razão técnica serve ao técnico, no
    toast — não ao registro permanente do chamado.
    """
    from app.models.models import TicketHistory

    t, s = _monta()
    await _liga_para(s, ticket=t)

    eventos = [o for o in s.adicionados if isinstance(o, TicketHistory)]
    texto = "".join(
        f"{e.field}{e.old_value}{e.new_value}{getattr(e, 'comment', None)}" for e in eventos
    )
    for proibido in ("424", "webphone", "Webphone", "SIP", "sip", "registrad", "offline"):
        assert proibido not in texto


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "liga",
    [
        {"side_effect": Api4ComRecusadaError(400)},
        {"side_effect": Api4ComRecusadaError(401)},
        {"side_effect": Api4ComRecusadaError(403)},
        {"side_effect": Api4ComRecusadaError(404)},
        {"side_effect": Api4ComRecusadaError(422)},
        {"side_effect": Api4ComRecusadaError(429)},
    ],
    indirect=True,
)
async def test_outros_4xx_nao_viram_problema_de_webphone(redis_falso, liga, _limpa_overrides):
    """Token caído, cota estourada e número inválido NÃO são webphone offline.

    Este é o caso que impede a fase de virar "todo erro é culpa do webphone",
    que seria pior que a mensagem genérica: mandaria o técnico abrir uma
    extensão que já está aberta enquanto o token expirado segue expirado.
    """
    t, s = _monta()
    async with _cliente_http(_ator(), s) as http:
        resposta = await http.post(f"/api/v1/tickets/{t.id}/calls", json={})

    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["creation_status"] == "rejected"
    assert corpo["reason"] is None, "só o 424 vira motivo público"


@pytest.mark.asyncio
async def test_sucesso_nao_tem_motivo(redis_falso, liga, _limpa_overrides):
    t, s = _monta()
    async with _cliente_http(_ator(), s) as http:
        resposta = await http.post(f"/api/v1/tickets/{t.id}/calls", json={})

    corpo = resposta.json()
    assert corpo["creation_status"] == "confirmed"
    assert corpo["reason"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "liga",
    [{"side_effect": Api4ComResultadoIndeterminadoError("timeout")}],
    indirect=True,
)
async def test_indeterminate_nao_tem_motivo(redis_falso, liga, _limpa_overrides):
    """O estado mais perigoso não ganha explicação que não existe."""
    t, s = _monta()
    async with _cliente_http(_ator(), s) as http:
        resposta = await http.post(f"/api/v1/tickets/{t.id}/calls", json={})

    corpo = resposta.json()
    assert corpo["creation_status"] == "indeterminate"
    assert corpo["reason"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("liga", [{"side_effect": Api4ComIndisponivelError()}], indirect=True)
async def test_unavailable_nao_tem_motivo(redis_falso, liga, _limpa_overrides):
    t, s = _monta()
    async with _cliente_http(_ator(), s) as http:
        resposta = await http.post(f"/api/v1/tickets/{t.id}/calls", json={})

    corpo = resposta.json()
    assert corpo["creation_status"] == "unavailable"
    assert corpo["reason"] is None


def test_o_vocabulario_publico_e_do_helphs_e_nao_do_fornecedor():
    """Sentinela: nenhum valor público pode ser o número do fornecedor.

    Se alguém um dia acrescentar `"424"` como motivo, ou nomear um motivo com
    o código HTTP dentro, é aqui que aparece.
    """
    from app.schemas.telefonia import MotivoPublicoDaRecusa

    for motivo in MotivoPublicoDaRecusa:
        assert not motivo.value.isdigit()
        assert "424" not in motivo.value
        assert "http" not in motivo.value.lower()


def test_a_traducao_do_codigo_mora_num_lugar_so():
    """`424` não pode virar `if` espalhado pelo sistema.

    O mapa é um dicionário no schema; o resto do código fala de `reason`.

    ⚠️ Olha o CÓDIGO, não o texto: `ligacao.py` cita 424 em comentários que
    contam a história da primeira ligação real, e comentário não decide nada.
    O que esta sentinela proíbe é o número aparecer numa expressão — um
    `== 424`, um `in (424,)`, um literal dentro de condição.
    """
    import ast
    import inspect

    from app.routers import tickets
    from app.schemas import telefonia
    from app.services import api4com, ligacao

    assert "424" in inspect.getsource(telefonia), "o mapa tem de estar aqui"

    def literais_424(modulo) -> list[int]:
        arvore = ast.parse(inspect.getsource(modulo))
        return [
            no.value for no in ast.walk(arvore) if isinstance(no, ast.Constant) and no.value == 424
        ]

    for modulo in (api4com, ligacao):
        assert not literais_424(modulo), f"{modulo.__name__} não pode decidir isso"
    assert "424" not in inspect.getsource(tickets.iniciar_ligacao)


def test_o_motivo_so_vale_para_recusa():
    """Um número de fornecedor guardado noutro estado não explica nada."""
    from app.schemas.telefonia import motivo_publico

    assert motivo_publico("rejected", 424) is not None
    assert motivo_publico("confirmed", 424) is None
    assert motivo_publico("indeterminate", 424) is None
    assert motivo_publico("dispatching", 424) is None
    assert motivo_publico("rejected", None) is None
    assert motivo_publico("rejected", 401) is None
