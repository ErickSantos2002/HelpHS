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

import inspect
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
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
    return await ligacao.inicia_ligacao(sessao, ticket_id=ticket_id or uuid.uuid4(), ator=ator)


@pytest.fixture(autouse=True)
def telefonia_ligada():
    """Liga a flag e substitui o transporte — em TODOS os testes deste arquivo.

    Autouse de propósito: um teste que esquecesse de mockar falaria com a
    API4COM de verdade. Aqui o esquecimento não é possível; quem quer medir a
    flag desligada desliga explicitamente.

    O dublê devolve sucesso confirmado. Os testes de recusa trocam o
    `side_effect` pelo que querem medir.
    """
    from app.services.api4com import Api4ComCreateCallResult

    with (
        patch("app.services.ligacao.get_settings") as settings_falso,
        patch(
            "app.services.ligacao.api4com.create_call",
            new=AsyncMock(
                return_value=Api4ComCreateCallResult(
                    status_code=200, provider_call_id="1PkXhmBsYAvr9legLB2d7BimT0Q"
                )
            ),
        ) as chamada,
    ):
        from app.core.config import get_settings as real

        base = real()
        settings_falso.return_value = SimpleNamespace(
            api4com_enabled=True,
            api4com_lock_ttl_seconds=base.api4com_lock_ttl_seconds,
            api4com_calls_per_actor_per_hour=base.api4com_calls_per_actor_per_hour,
            api4com_called_format=base.api4com_called_format,
        )
        yield chamada


# ── Autorização ──────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", [UserRole.admin, UserRole.technician])
async def test_staff_com_ramal_prepara_a_tentativa(redis_falso, papel):
    ticket = _ticket()
    sessao = _Sessao(ticket, _cliente())
    tentativa = await _prepara(_ator(papel), sessao, ticket.id)

    assert tentativa.creation_status == CallCreationStatus.confirmed.value
    assert tentativa.provider_call_id == "1PkXhmBsYAvr9legLB2d7BimT0Q"
    assert tentativa.provider_http_status == 200
    # Três commits, e a conta importa: `pending`, `dispatching` e o estado
    # final. Juntar quaisquer dois abriria a janela que o desenho fecha.
    assert sessao.commit.await_count == 3


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
    assert tentativa.creation_status == CallCreationStatus.confirmed.value


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
    """Falha depois do lock não pode prender o chamado por 30s.

    ⚠️ A causa da falha mudou em 25/09/2026. Este caso usava uma tentativa
    recente `confirmed` para provocar o 409 da antirrepetição; com aquela regra
    removida, uma tentativa recente não falha mais nada. A falha agora vem do
    teto por hora, que é a outra recusa que acontece DEPOIS do lock — e é
    exatamente essa posição que o caso mede.
    """
    ticket = _ticket()
    sessao = _Sessao(ticket, _cliente())
    with patch.object(ligacao, "_consome_teto", new=AsyncMock(return_value=False)):
        with pytest.raises(HTTPException) as erro:
            await _prepara(_ator(), sessao, ticket.id)

    assert erro.value.status_code == 429
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


# ── Repetição PERMITIDA (2C.5b) ──────────────────────────────
#
# Até 25/09/2026 uma janela de 5 minutos recusava com 409 a segunda ligação
# para o mesmo chamado quando a primeira estava em `dispatching`, `confirmed`
# ou `indeterminate`. A regra de negócio mudou: quem atende liga para o cliente
# quantas vezes for preciso.
#
# A primeira ligação real do HelpHS mostrou por que isso importa — ela precisou
# de DUAS tentativas, porque a primeira voltou 424 do fornecedor. Se aquela
# primeira tivesse sido `confirmed`, a janela teria transformado a segunda
# tentativa legítima em erro.
#
# O que os casos abaixo prendem é o inverso do que os antigos prendiam.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "estado_anterior",
    ["pending", "dispatching", "confirmed", "rejected", "unavailable", "indeterminate"],
)
async def test_tentativa_anterior_nao_bloqueia_mais(redis_falso, estado_anterior):
    """NENHUM estado anterior recusa uma nova tentativa manual."""
    ticket = _ticket()
    sessao = _Sessao(ticket, _cliente(), recentes=[_tentativa_recente(estado_anterior)])

    tentativa = await _prepara(_ator(), sessao, ticket.id)

    assert tentativa is not None
    assert sessao.add.call_count >= 1, "a tentativa nova precisa ter sido criada"


def test_a_regra_da_antirrepeticao_nao_existe_mais(redis_falso):
    """Sentinela estrutural: o código da janela não pode voltar por descuido.

    Prende o NOME e a MENSAGEM, não o comportamento — comportamento já está nos
    casos acima. Se alguém reintroduzir a regra, é aqui que aparece primeiro.
    """
    assert not hasattr(ligacao, "STATUS_QUE_BLOQUEIAM_REPETICAO")
    assert not hasattr(ligacao, "_recusa_repeticao")
    fonte = inspect.getsource(ligacao.inicia_ligacao)
    assert "_recusa_repeticao" not in fonte
    assert "poucos minutos" not in inspect.getsource(ligacao)


@pytest.mark.asyncio
async def test_duas_chamadas_seguidas_geram_duas_tentativas(redis_falso):
    """Duas ações manuais sucessivas: duas linhas, duas idas ao fornecedor.

    É a prova direta da regra nova — e também prova que não há repetição
    automática, porque cada `create_call` corresponde a UMA ação de gente.
    """
    ticket = _ticket()

    primeira = await _prepara(_ator(), _Sessao(ticket, _cliente()), ticket.id)
    segunda = await _prepara(
        _ator(),
        _Sessao(ticket, _cliente(), recentes=[_tentativa_recente("confirmed")]),
        ticket.id,
    )

    assert primeira is not None
    assert segunda is not None
    assert primeira is not segunda


@pytest.mark.asyncio
async def test_duas_chamadas_geram_dois_eventos_de_historico(redis_falso):
    """Cada tentativa que entra no fluxo conta a sua própria linha na Atividade.

    Mede o que o banco de produção mediu depois da primeira ligação real: duas
    tentativas, dois eventos. O AST de `test_efeito_externo_telefonia` já prende
    o CONTEÚDO do evento; este prende a CONTAGEM, que é o que a regra nova
    mudou.
    """
    from app.models.models import TicketHistory

    ticket = _ticket()
    eventos = []

    for _ in range(2):
        sessao = _Sessao(ticket, _cliente(), recentes=[_tentativa_recente("confirmed")])
        await _prepara(_ator(), sessao, ticket.id)
        eventos += [
            c.args[0] for c in sessao.add.call_args_list if isinstance(c.args[0], TicketHistory)
        ]

    assert len(eventos) == 2, f"esperava 2 eventos, vieram {len(eventos)}"
    for e in eventos:
        assert e.field == "ligacao"
        assert e.new_value == "tentativa"
        assert e.old_value is None
        # Nada de sensível viaja no evento: ele diz QUE houve tentativa.
        texto = f"{e.field}{e.old_value}{e.new_value}{getattr(e, 'comment', None)}"
        for proibido in (
            "phone",
            "telefone",
            "ramal",
            "extension",
            "caller",
            "called",
            "1019",
            "provider",
        ):
            assert proibido not in texto


@pytest.mark.asyncio
async def test_o_lock_continua_barrando_a_simultaneidade(redis_falso):
    """A defesa que NÃO saiu: duas execuções ao mesmo tempo no mesmo chamado.

    A janela olhava para o passado; o lock olha para o presente. Só a primeira
    contrariava a regra nova, e é por isso que esta continua de pé.
    """
    ticket = _ticket()
    await redis_falso.set(f"{ligacao._PREFIXO_LOCK}{ticket.id}", "de-outro", nx=True, ex=30)

    with pytest.raises(HTTPException) as erro:
        await _prepara(_ator(), _Sessao(ticket, _cliente()), ticket.id)

    assert erro.value.status_code == 409
    assert "andamento" in erro.value.detail


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
async def test_o_chamado_nao_tem_teto(redis_falso, telefonia_ligada):
    """SEIS chamadas manuais no MESMO chamado, todas aceitas.

    Antes de 25/09/2026 a quarta batia num teto de 3/hora por chamado e voltava
    429. O teto saiu: quem atende liga quantas vezes for preciso.

    Seis é de propósito — o dobro do teto antigo mais um. Ator diferente a cada
    volta para que o teto do ATOR, que continua existindo, não responda no
    lugar do que este caso mede.
    """
    from app.models.models import TicketHistory

    ticket = _ticket()
    tentativas, eventos = [], []

    for _ in range(6):
        sessao = _Sessao(ticket, _cliente(), recentes=[_tentativa_recente("confirmed")])
        tentativas.append(await _prepara(_ator(), sessao, ticket.id))
        eventos += [
            c.args[0] for c in sessao.add.call_args_list if isinstance(c.args[0], TicketHistory)
        ]

    # 1. todas permitidas
    assert all(t is not None for t in tentativas)
    # 2. linhas independentes
    assert len({id(t) for t in tentativas}) == 6
    # 3. um evento de histórico por tentativa
    assert len(eventos) == 6
    # 4. o fornecedor foi chamado uma vez por ação de gente — nunca mais
    assert telefonia_ligada.await_count == 6


@pytest.mark.asyncio
async def test_o_teto_do_ator_continua_de_pe(redis_falso):
    """A defesa que FICA: 20/h por ator, contra laço e conta comprometida.

    O mesmo ator, em chamados diferentes, para que nenhum teto por chamado
    pudesse responder no lugar — e hoje não há nenhum.
    """
    from app.core.config import get_settings

    limite = get_settings().api4com_calls_per_actor_per_hour
    ator = _ator()

    for _ in range(limite):
        t = _ticket()
        await _prepara(ator, _Sessao(t, _cliente()), t.id)

    t = _ticket()
    with pytest.raises(HTTPException) as erro:
        await _prepara(ator, _Sessao(t, _cliente()), t.id)

    assert erro.value.status_code == 429
    assert "Você atingiu" in erro.value.detail


def test_a_regra_do_teto_por_chamado_nao_existe_mais():
    """Sentinela estrutural: o teto por chamado não pode voltar por descuido."""
    from app.core.config import get_settings

    assert not hasattr(ligacao, "_PREFIXO_TETO_CHAMADO")
    assert not hasattr(get_settings(), "api4com_calls_per_ticket_per_hour")
    fonte = inspect.getsource(ligacao)
    assert "Este chamado atingiu" not in fonte
    # E o teto que fica continua lá.
    assert hasattr(ligacao, "_PREFIXO_TETO_ATOR")
    assert get_settings().api4com_calls_per_actor_per_hour == 20


@pytest.mark.asyncio
async def test_janela_expirada_libera(redis_falso):
    """O contador some com o TTL; apagar a chave é o que o Redis faria.

    ⚠️ Medido no teto do ATOR desde 25/09/2026. Este caso usava o teto por
    chamado, que deixou de existir — mas o que ele mede é o comportamento da
    JANELA, e essa continua igual no contador que sobrou.
    """
    from app.core.config import get_settings

    limite = get_settings().api4com_calls_per_actor_per_hour
    ator = _ator()
    for _ in range(limite):
        t = _ticket()
        await _prepara(ator, _Sessao(t, _cliente()), t.id)

    redis_falso.dados.pop(f"{ligacao._PREFIXO_TETO_ATOR}{ator.id}")

    t = _ticket()
    tentativa = await _prepara(ator, _Sessao(t, _cliente()), t.id)
    assert tentativa.creation_status == CallCreationStatus.confirmed.value


@pytest.mark.asyncio
async def test_recusa_antes_das_validacoes_nao_gasta_cota(redis_falso):
    """Chamado encerrado não consome a hora de ninguém."""
    ator = _ator()
    ticket = _ticket(TicketStatus.closed)

    with pytest.raises(HTTPException):
        await _prepara(ator, _Sessao(ticket, _cliente()), ticket.id)

    assert f"{ligacao._PREFIXO_TETO_ATOR}{ator.id}" not in redis_falso.dados


# ── Os ramais reais do suporte ───────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("ramal", ["1018", "1019"])
async def test_os_ramais_do_suporte_passam_pela_validacao(redis_falso, telefonia_ligada, ramal):
    """1018 e 1019 foram criados na API4COM para o suporte do HelpHS.

    Este teste prova que a orquestração deixa de parar no "ator sem ramal"
    para quem os tiver — e que, mesmo passando, NADA sai para o fornecedor.
    O provisionamento em si (qual pessoa recebe qual ramal) é decisão
    administrativa, não código.
    """
    ticket = _ticket()
    sessao = _Sessao(ticket, _cliente())

    with patch("httpx.AsyncClient.send", side_effect=AssertionError("saiu HTTP!")):
        tentativa = await _prepara(_ator(ramal=ramal), sessao, ticket.id)

    assert tentativa.creation_status == CallCreationStatus.confirmed.value
    # E o ramal do ator chegou ao fornecedor como `extension` E como `caller`.
    enviado = telefonia_ligada.await_args.kwargs
    assert enviado["extension"] == ramal
    assert enviado["caller"] == ramal


@pytest.mark.asyncio
async def test_ramal_do_suporte_nao_e_convertido_para_numero(redis_falso):
    """O ramal viaja como string do banco até o fornecedor, sem passar por int.

    Um ramal com zero à esquerda existe no plano de numeração de muita central;
    `int("0700")` viraria 700 e a ligação sairia de outro lugar.
    """
    ticket = _ticket()
    ator = _ator(ramal="0700")
    assert ligacao._ramal_do_ator(ator) == "0700"

    tentativa = await _prepara(ator, _Sessao(ticket, _cliente()), ticket.id)
    assert tentativa.creation_status == CallCreationStatus.confirmed.value


# ── O sentinela ──────────────────────────────────────────────


def test_o_transporte_e_o_unico_caminho_para_o_fornecedor():
    """A orquestração fala com a API4COM por UMA porta só: `api4com.create_call`.

    Na 2C.2 este sentinela afirmava o oposto — que o módulo não tocava o
    transporte. A fase mudou, e a garantia muda com ela: o que não pode
    acontecer agora é `httpx` aparecer aqui, montando requisição por fora do
    contrato do transporte (que roda `retries=0`, sem redirect e com timeout).
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

    assert "httpx" not in importados, "a orquestração montou HTTP por fora do transporte"

    chamadas = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
    ]
    do_fornecedor = [c for c in chamadas if c.func.attr == "create_call"]
    assert len(do_fornecedor) == 1, "há mais de um ponto chamando o fornecedor"


def test_nao_existe_retry_automatico():
    """Nenhum caminho repete a chamada. Prova por contagem, não por leitura."""
    import ast
    from pathlib import Path

    fonte = Path(ligacao.__file__).read_text(encoding="utf-8")
    chamadas = [
        no
        for no in ast.walk(ast.parse(fonte))
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
    ]
    assert len([c for c in chamadas if c.func.attr == "create_call"]) == 1

    # E nenhuma estrutura de repetição envolve a chamada.
    arvore = ast.parse(fonte)
    for no in ast.walk(arvore):
        if isinstance(no, ast.For | ast.While | ast.AsyncFor):
            dentro = [
                c
                for c in ast.walk(no)
                if isinstance(c, ast.Call)
                and isinstance(c.func, ast.Attribute)
                and c.func.attr == "create_call"
            ]
            assert not dentro, "o `create_call` está dentro de um laço"


def test_o_despacho_e_commitado_antes_da_chamada():
    """A ordem que torna `dispatching` útil: gravar, commitar, só então ligar.

    Se o commit viesse depois do `create_call`, um crash no meio deixaria a
    linha como `pending` — e `pending` significa "nada saiu". Alguém repetiria
    com segurança aparente, e o telefone tocaria de novo.
    """
    import ast
    import inspect

    fonte = inspect.getsource(ligacao.inicia_ligacao)
    linhas = fonte.splitlines()
    i_despacho = next(i for i, ln in enumerate(linhas) if "marca_em_despacho" in ln)
    i_commit = next(i for i, ln in enumerate(linhas) if i > i_despacho and "db.commit()" in ln)
    i_executa = next(i for i, ln in enumerate(linhas) if "_executa_e_persiste" in ln)

    assert (
        i_despacho < i_commit < i_executa
    ), f"ordem errada: despacho({i_despacho}) commit({i_commit}) chamada({i_executa})"
    assert ast.parse(fonte) is not None


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


def test_o_despacho_e_usado_exatamente_uma_vez():
    """Na 2C.2 este caso afirmava que `dispatching` NÃO era exercido.

    A 2C.3 é justamente o efeito externo, então a garantia inverte: o estado
    passa a ser usado, e uma vez só — no ponto que antecede a chamada. Duas
    marcações significariam duas travessias da fronteira.
    """
    import ast
    from pathlib import Path

    fonte = Path(ligacao.__file__).read_text(encoding="utf-8")
    chamadas = [
        no.func.attr
        for no in ast.walk(ast.parse(fonte))
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
    ]
    assert chamadas.count("marca_em_despacho") == 1


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
