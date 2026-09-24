"""
A orquestração da tentativa de ligação — tudo, menos ligar.

Esta fase termina numa linha `pending` commitada. O teste que mais importa
aqui não é nenhum dos bloqueios: é o sentinela do fim do arquivo, que prova que
NENHUM caminho deste módulo fala com o fornecedor. Enquanto isso for verdade, um
erro em qualquer regra abaixo custa um 4xx — nunca um telefone tocando.

O Redis é falsificado. Não há Redis nos testes deste projeto, e o
`_RedisFalso` abaixo implementa exatamente as quatro operações que o
orquestrador usa (`set` com `nx`/`ex`, `incr`, `expire`, `eval`), com a mesma
semântica. O `eval` emula o script Lua de liberação: compara e só então apaga.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models.models import (
    CallCreationStatus,
    TicketCall,
    TicketStatus,
    UserRole,
    UserStatus,
)
from app.services import ligacao

_RAMAL = "1000"
_TELEFONE = "+5581999999999"


# ── Redis de mentira ─────────────────────────────────────────


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
        """Emula `_LUA_LIBERA_SE_MEU`: só apaga se o valor for o do dono."""
        if self.dados.get(chave) == arg:
            del self.dados[chave]
            return 1
        return 0


# ── Objetos de domínio ───────────────────────────────────────


def _ator(role=UserRole.technician, ramal=_RAMAL):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.role = role
    u.status = UserStatus.active
    u.api4com_extension = ramal
    return u


def _cliente(role=UserRole.client, status=UserStatus.active, telefone=_TELEFONE):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.role = role
    u.status = status
    u.phone = telefone
    return u


def _ticket(status=TicketStatus.open, creator_id=None):
    t = MagicMock()
    t.id = uuid.uuid4()
    t.status = status
    t.creator_id = creator_id or uuid.uuid4()
    return t


class _Sessao:
    """Sessão falsa com respostas em sequência.

    O orquestrador consulta, nesta ordem: o chamado, o destinatário, as
    tentativas recentes. Uma sessão que devolvesse sempre a mesma coisa faria a
    busca de repetição encontrar o próprio chamado.
    """

    def __init__(self, ticket=None, destinatario=None, recentes=None):
        self._fila = [ticket, destinatario]
        self._recentes = recentes or []
        self._n = 0
        self.add = MagicMock()
        self.commit = AsyncMock()
        self.refresh = AsyncMock()
        self.flush = AsyncMock()

    async def execute(self, *a, **k):
        r = MagicMock()
        if self._n < len(self._fila):
            valor = self._fila[self._n]
            r.scalar_one_or_none.return_value = valor
            r.scalars.return_value.first.return_value = None
        else:
            r.scalar_one_or_none.return_value = None
            r.scalars.return_value.first.return_value = (
                self._recentes[0] if self._recentes else None
            )
        self._n += 1
        return r


def _tentativa_recente(status, minutos_atras=1):
    c = MagicMock(spec=TicketCall)
    c.creation_status = status
    c.created_at = datetime.now(UTC) - timedelta(minutes=minutos_atras)
    return c


@pytest.fixture()
def redis_falso():
    r = _RedisFalso()

    async def _get():
        return r

    with patch("app.services.ligacao.get_redis", new=_get):
        yield r


async def _prepara(ator, sessao, ticket_id=None):
    return await ligacao.prepara_tentativa(sessao, ticket_id=ticket_id or uuid.uuid4(), ator=ator)


# ── Autorização ──────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", [UserRole.admin, UserRole.technician])
async def test_staff_com_ramal_prepara_a_tentativa(redis_falso, papel):
    ticket = _ticket()
    sessao = _Sessao(ticket, _cliente())
    tentativa = await _prepara(_ator(papel), sessao, ticket.id)

    assert tentativa.creation_status == CallCreationStatus.pending.value
    assert tentativa.provider_call_id is None
    assert tentativa.provider_http_status is None
    assert sessao.commit.await_count == 1, "a tentativa precisa ficar DURÁVEL"


@pytest.mark.asyncio
async def test_cliente_nao_inicia_ligacao(redis_falso):
    ticket = _ticket()
    sessao = _Sessao(ticket, _cliente())

    with pytest.raises(HTTPException) as erro:
        await _prepara(_ator(UserRole.client), sessao, ticket.id)

    assert erro.value.status_code == 403
    assert sessao.add.call_count == 0, "nada pode ter sido gravado"


# ── Ramal do ator ────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("ramal", [None, "", "   "])
async def test_ator_sem_ramal_e_bloqueado(redis_falso, ramal):
    """Hoje TODO mundo cai aqui: os ramais do suporte ainda não existem."""
    ticket = _ticket()
    sessao = _Sessao(ticket, _cliente())

    with pytest.raises(HTTPException) as erro:
        await _prepara(_ator(ramal=ramal), sessao, ticket.id)

    assert erro.value.status_code == 422
    assert sessao.add.call_count == 0
    assert redis_falso.dados == {}, "não se toma lock para depois recusar"


# ── Situação do chamado ──────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "situacao",
    [
        TicketStatus.open,
        TicketStatus.in_progress,
        TicketStatus.awaiting_client,
        TicketStatus.awaiting_technical,
        TicketStatus.resolved,
    ],
)
async def test_situacoes_que_aceitam_ligacao(redis_falso, situacao):
    ticket = _ticket(situacao)
    tentativa = await _prepara(_ator(), _Sessao(ticket, _cliente()), ticket.id)
    assert tentativa.creation_status == CallCreationStatus.pending.value


@pytest.mark.asyncio
@pytest.mark.parametrize("situacao", [TicketStatus.closed, TicketStatus.cancelled])
async def test_chamado_encerrado_nao_aceita_ligacao(redis_falso, situacao):
    ticket = _ticket(situacao)
    sessao = _Sessao(ticket, _cliente())

    with pytest.raises(HTTPException) as erro:
        await _prepara(_ator(), sessao, ticket.id)

    assert erro.value.status_code == 422
    assert sessao.add.call_count == 0


def test_a_lista_de_situacoes_e_uma_lista_do_que_pode():
    """Estado novo no enum nasce BLOQUEADO, não liberado por omissão."""
    todos = set(TicketStatus)
    assert ligacao.STATUS_QUE_PERMITEM_LIGACAO < todos
    assert TicketStatus.closed not in ligacao.STATUS_QUE_PERMITEM_LIGACAO
    assert TicketStatus.cancelled not in ligacao.STATUS_QUE_PERMITEM_LIGACAO


# ── Destinatário ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chamado_sem_destinatario_no_banco(redis_falso):
    ticket = _ticket()
    sessao = _Sessao(ticket, None)

    with pytest.raises(HTTPException) as erro:
        await _prepara(_ator(), sessao, ticket.id)

    assert erro.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", [UserRole.admin, UserRole.technician])
async def test_destinatario_que_nao_e_cliente_e_bloqueado(redis_falso, papel):
    """Chamado aberto por staff fica de fora da V1 — dívida conhecida."""
    ticket = _ticket()
    sessao = _Sessao(ticket, _cliente(role=papel))

    with pytest.raises(HTTPException) as erro:
        await _prepara(_ator(), sessao, ticket.id)

    assert erro.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("situacao", [UserStatus.inactive, UserStatus.anonymized])
async def test_destinatario_inativo_e_bloqueado(redis_falso, situacao):
    ticket = _ticket()
    sessao = _Sessao(ticket, _cliente(status=situacao))

    with pytest.raises(HTTPException) as erro:
        await _prepara(_ator(), sessao, ticket.id)

    assert erro.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("telefone", [None, "", "   ", "abc", "123"])
async def test_telefone_ausente_ou_invalido_bloqueia(redis_falso, telefone):
    """O CHECK do banco garante PRESENÇA; o formato é conferido aqui."""
    ticket = _ticket()
    sessao = _Sessao(ticket, _cliente(telefone=telefone))

    with pytest.raises(HTTPException) as erro:
        await _prepara(_ator(), sessao, ticket.id)

    assert erro.value.status_code == 422
    assert sessao.add.call_count == 0


# ── Lock ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lock_e_adquirido_e_liberado_no_sucesso(redis_falso):
    ticket = _ticket()
    await _prepara(_ator(), _Sessao(ticket, _cliente()), ticket.id)

    chave = f"{ligacao._PREFIXO_LOCK}{ticket.id}"
    assert chave not in redis_falso.dados, "o lock ficou preso depois do sucesso"


@pytest.mark.asyncio
async def test_lock_ocupado_devolve_409(redis_falso):
    ticket = _ticket()
    outro = await ligacao.adquire_lock(ticket.id)
    assert outro

    sessao = _Sessao(ticket, _cliente())
    with pytest.raises(HTTPException) as erro:
        await _prepara(_ator(), sessao, ticket.id)

    assert erro.value.status_code == 409
    assert sessao.add.call_count == 0
    assert (
        f"{ligacao._PREFIXO_LOCK}{ticket.id}" in redis_falso.dados
    ), "a execução recusada apagou o lock de quem estava dentro"


@pytest.mark.asyncio
async def test_lock_e_liberado_quando_a_execucao_falha(redis_falso):
    """Falha depois do lock não pode prender o chamado por 30s."""
    ticket = _ticket()
    sessao = _Sessao(ticket, _cliente(), recentes=[_tentativa_recente("confirmed")])

    with pytest.raises(HTTPException):
        await _prepara(_ator(), sessao, ticket.id)

    assert f"{ligacao._PREFIXO_LOCK}{ticket.id}" not in redis_falso.dados


@pytest.mark.asyncio
async def test_lock_so_e_liberado_por_quem_o_tem(redis_falso):
    """Token de outra execução não apaga o nosso — a razão do script Lua."""
    ticket = _ticket()
    meu = await ligacao.adquire_lock(ticket.id)

    await ligacao.libera_lock(ticket.id, "token-de-outra-execucao")
    assert f"{ligacao._PREFIXO_LOCK}{ticket.id}" in redis_falso.dados

    await ligacao.libera_lock(ticket.id, meu)
    assert f"{ligacao._PREFIXO_LOCK}{ticket.id}" not in redis_falso.dados


@pytest.mark.asyncio
async def test_o_lock_nasce_com_ttl(redis_falso):
    from app.core.config import get_settings

    ticket = _ticket()
    await ligacao.adquire_lock(ticket.id)
    assert redis_falso.ttls[f"{ligacao._PREFIXO_LOCK}{ticket.id}"] == (
        get_settings().api4com_lock_ttl_seconds
    )


# ── Antirrepetição ───────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("status_recente", ["dispatching", "confirmed", "indeterminate"])
async def test_tentativa_recente_que_pode_ter_tocado_bloqueia(redis_falso, status_recente):
    ticket = _ticket()
    sessao = _Sessao(ticket, _cliente(), recentes=[_tentativa_recente(status_recente)])

    with pytest.raises(HTTPException) as erro:
        await _prepara(_ator(), sessao, ticket.id)

    assert erro.value.status_code == 409
    assert sessao.add.call_count == 0


def test_pending_nao_bloqueia_repeticao():
    """A diferença que o estado `dispatching` comprou.

    Antes dele, `pending` órfão era ambíguo e a conduta segura era travar. Com
    a fronteira explícita, `pending` significa que NADA saiu — travar seria
    punir o usuário por um crash que não causou efeito nenhum.
    """
    assert CallCreationStatus.pending.value not in ligacao.STATUS_QUE_BLOQUEIAM_REPETICAO
    assert CallCreationStatus.dispatching.value in ligacao.STATUS_QUE_BLOQUEIAM_REPETICAO


def test_rejected_e_unavailable_nao_bloqueiam():
    """4xx e falha de conexão: o fornecedor respondeu, ou nem ouviu. Nada tocou."""
    assert CallCreationStatus.rejected.value not in ligacao.STATUS_QUE_BLOQUEIAM_REPETICAO
    assert CallCreationStatus.unavailable.value not in ligacao.STATUS_QUE_BLOQUEIAM_REPETICAO


# ── Tetos por hora ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_teto_do_ator(redis_falso):
    from app.core.config import get_settings

    limite = get_settings().api4com_calls_per_actor_per_hour
    ator = _ator()
    # Cada tentativa é um chamado diferente, para o teto do CHAMADO não
    # responder no lugar do teto do ator.
    for _ in range(limite):
        t = _ticket()
        await _prepara(ator, _Sessao(t, _cliente()), t.id)

    t = _ticket()
    with pytest.raises(HTTPException) as erro:
        await _prepara(ator, _Sessao(t, _cliente()), t.id)

    assert erro.value.status_code == 429
    assert "ligações por hora" in erro.value.detail


@pytest.mark.asyncio
async def test_teto_do_chamado(redis_falso):
    from app.core.config import get_settings

    limite = get_settings().api4com_calls_per_ticket_per_hour
    ticket = _ticket()
    for _ in range(limite):
        # Ator diferente a cada volta, para o teto do ATOR não responder antes.
        await _prepara(_ator(), _Sessao(ticket, _cliente()), ticket.id)

    with pytest.raises(HTTPException) as erro:
        await _prepara(_ator(), _Sessao(ticket, _cliente()), ticket.id)

    assert erro.value.status_code == 429
    assert "Este chamado" in erro.value.detail


@pytest.mark.asyncio
async def test_janela_expirada_libera(redis_falso):
    """O contador some com o TTL; apagar a chave é o que o Redis faria."""
    from app.core.config import get_settings

    limite = get_settings().api4com_calls_per_ticket_per_hour
    ticket = _ticket()
    for _ in range(limite):
        await _prepara(_ator(), _Sessao(ticket, _cliente()), ticket.id)

    redis_falso.dados.pop(f"{ligacao._PREFIXO_TETO_CHAMADO}{ticket.id}")

    tentativa = await _prepara(_ator(), _Sessao(ticket, _cliente()), ticket.id)
    assert tentativa.creation_status == CallCreationStatus.pending.value


@pytest.mark.asyncio
async def test_recusa_antes_das_validacoes_nao_gasta_cota(redis_falso):
    """Chamado encerrado não consome a hora de ninguém."""
    ator = _ator()
    ticket = _ticket(TicketStatus.closed)

    with pytest.raises(HTTPException):
        await _prepara(ator, _Sessao(ticket, _cliente()), ticket.id)

    assert f"{ligacao._PREFIXO_TETO_ATOR}{ator.id}" not in redis_falso.dados


# ── O sentinela ──────────────────────────────────────────────


def test_a_orquestracao_nao_fala_com_o_fornecedor():
    """Nenhum caminho deste módulo alcança a API4COM. Prova por AST.

    Enquanto isto for verdade, um erro em qualquer regra acima custa um 4xx —
    nunca um telefone tocando. É o teste que dá licença para os outros
    existirem.
    """
    import ast
    from pathlib import Path

    fonte = Path(ligacao.__file__).read_text(encoding="utf-8")
    arvore = ast.parse(fonte)

    importados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            importados.add(no.module)
            importados.update(f"{no.module}.{a.name}" for a in no.names)

    proibidos = {i for i in importados if "api4com" in i or i == "httpx"}
    assert not proibidos, f"a orquestração importou o transporte: {proibidos}"

    chamadas = {
        no.func.attr
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
    }
    assert "create_call" not in chamadas


@pytest.mark.asyncio
async def test_nenhuma_requisicao_http_sai_durante_a_preparacao(redis_falso):
    """Cinto e suspensório: o sentinela é estático, este é em execução."""
    ticket = _ticket()
    with patch("httpx.AsyncClient.send", side_effect=AssertionError("saiu HTTP!")):
        tentativa = await _prepara(_ator(), _Sessao(ticket, _cliente()), ticket.id)
    assert tentativa.creation_status == CallCreationStatus.pending.value


# ── A transição que existe mas não é exercida ─────────────────


@pytest.mark.asyncio
async def test_marca_em_despacho_muda_o_estado():
    """Disponível para a fase seguinte, e provada agora."""
    from app.services import telefonia

    db = AsyncMock()
    tentativa = TicketCall(
        ticket_id=uuid.uuid4(),
        initiated_by_id=uuid.uuid4(),
        creation_status=CallCreationStatus.pending.value,
    )
    devolvida = await telefonia.marca_em_despacho(db, tentativa)

    assert devolvida.creation_status == CallCreationStatus.dispatching.value
    db.flush.assert_awaited_once()


def test_a_orquestracao_desta_fase_nao_usa_dispatching():
    """A fase termina no `pending`. O despacho entra na próxima."""
    import ast
    from pathlib import Path

    fonte = Path(ligacao.__file__).read_text(encoding="utf-8")
    chamadas = {
        no.func.attr
        for no in ast.walk(ast.parse(fonte))
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
    }
    assert "marca_em_despacho" not in chamadas


# ── Contrato do request ──────────────────────────────────────


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
def test_o_navegador_nao_escolhe_nada_da_telefonia(campo):
    """`extra="forbid"`: escolher destino vira 422, não silêncio."""
    from pydantic import ValidationError

    from app.schemas.telefonia import TicketCallCreate

    with pytest.raises(ValidationError):
        TicketCallCreate.model_validate({campo: "qualquer-coisa"})


def test_o_corpo_valido_e_vazio():
    from app.schemas.telefonia import TicketCallCreate

    assert TicketCallCreate.model_validate({}) is not None


def test_a_resposta_nao_leva_dado_do_fornecedor():
    from app.schemas.telefonia import TicketCallResponse

    campos = set(TicketCallResponse.model_fields)
    assert campos == {"id", "creation_status", "created_at"}
    for proibido in ("provider_call_id", "provider_http_status", "phone", "caller", "extension"):
        assert proibido not in campos
