"""
O evento de encerramento de chamada: a primeira porta de ENTRADA do HelpHS.

Até esta rota, tudo o que autenticava uma requisição no projeto vinha de
`get_current_user` — sessão de gente, com papel. Aqui não há usuário, e o que
separa o legítimo do resto é um segredo compartilhado. É por isso que metade
deste arquivo testa recusa, e não sucesso.

Os três testes que mais importam não são os de caminho feliz:

* `test_a_rota_nao_depende_de_sessao` impede que alguém "conserte" o acesso
  acrescentando `get_current_user` — o que transformaria a porta de máquina numa
  rota aberta a qualquer usuário autenticado, `client` incluído;
* `test_segredo_ausente_e_errado_dao_a_mesma_resposta` fecha o oráculo que
  distinguir os dois casos abriria;
* `test_nada_do_fornecedor_entra_no_contrato` prende o conjunto fechado do corpo.

Nenhum teste aqui toca rede, e nenhum toca Postgres: a atomicidade do `UPDATE`
se prova contra banco de verdade, e isso vive em
`test_evento_de_encerramento_postgres.py`.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.services import telefonia

ROTA = "/api/v1/integrations/telefonia/call-ended"

_SEGREDO = "segredo-de-integracao-que-nao-pode-vazar-7K2Q"
_CABECALHO = "X-HelpHS-Webhook-Secret"
_TICKET_CALL_ID = "3f1c9d2e-7a84-4b16-9c05-2e8d1f6a40bb"

# Marcadores que não existem em lugar nenhum do sistema: se aparecerem numa
# resposta, veio do corpo que mandamos.
_RECORD_URL = "https://listener.exemplo.invalido/gravacao/marcador-9Z7Q.mp3"
# Marcador no lugar de um telefone: para provar que NADA vaza, basta uma
# cadeia distintiva, e ela nao precisa ter forma de numero. Um numero
# plausivel num arquivo de teste pode ser de alguem.
_TELEFONE = "TELEFONE-QUE-NAO-PODE-VAZAR-4H8M"


def _corpo(**extra) -> dict:
    base = {
        "ticket_call_id": _TICKET_CALL_ID,
        "duration": 9,
        "hangup_cause": "NORMAL_CLEARING",
        "recording_available": True,
    }
    base.update(extra)
    return base


def _sessao(rowcount: int = 1, existe: bool = True) -> MagicMock:
    """Dublê de sessão HONESTO para o que o router consome.

    `execute` devolve um objeto com `rowcount`, que é o que o service lê, e
    `scalar` responde a pergunta "a linha existe?". Não imita banco: imita
    exatamente as duas respostas que a decisão do router depende.
    """
    s = MagicMock()
    s.execute = AsyncMock(return_value=SimpleNamespace(rowcount=rowcount))
    s.scalar = AsyncMock(return_value=uuid.UUID(_TICKET_CALL_ID) if existe else None)
    s.flush = AsyncMock()
    s.commit = AsyncMock()
    return s


def _cliente(sessao, *, segredo: str | None = _SEGREDO) -> AsyncClient:
    from app.core.config import get_settings
    from app.core.database import get_db
    from app.main import app

    base = get_settings()

    async def _db():
        yield sessao

    def _settings():
        return SimpleNamespace(
            helphs_webhook_secret=MagicMock(get_secret_value=lambda: segredo or ""),
            api_prefix=base.api_prefix,
        )

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings] = _settings
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.fixture()
def _limpa_overrides():
    from app.main import app

    yield
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════
# Autenticação — a metade que importa
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_segredo_correto_registra(_limpa_overrides):
    s = _sessao(rowcount=1)
    async with _cliente(s) as c:
        r = await c.post(ROTA, json=_corpo(), headers={_CABECALHO: _SEGREDO})

    assert r.status_code == 204
    s.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_segredo_errado_e_401(_limpa_overrides):
    s = _sessao()
    async with _cliente(s) as c:
        r = await c.post(ROTA, json=_corpo(), headers={_CABECALHO: "errado"})

    assert r.status_code == 401
    s.execute.assert_not_awaited(), "tocou o banco antes de autenticar"


@pytest.mark.asyncio
async def test_segredo_ausente_e_401(_limpa_overrides):
    s = _sessao()
    async with _cliente(s) as c:
        r = await c.post(ROTA, json=_corpo())

    assert r.status_code == 401
    s.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_segredo_ausente_e_errado_dao_a_mesma_resposta(_limpa_overrides):
    """Distinguir os dois casos diria ao atacante que o cabeçalho é o caminho."""
    async with _cliente(_sessao()) as c:
        sem = await c.post(ROTA, json=_corpo())
        errado = await c.post(ROTA, json=_corpo(), headers={_CABECALHO: "errado"})

    assert sem.status_code == errado.status_code == 401
    assert sem.json() == errado.json()


@pytest.mark.asyncio
async def test_segredo_vazio_no_cabecalho_e_401(_limpa_overrides):
    async with _cliente(_sessao()) as c:
        r = await c.post(ROTA, json=_corpo(), headers={_CABECALHO: ""})

    assert r.status_code == 401


@pytest.mark.asyncio
async def test_servidor_sem_segredo_configurado_falha_fechado(_limpa_overrides):
    """Fail-closed: sem segredo no servidor a porta não abre. E 503, não 200."""
    s = _sessao()
    async with _cliente(s, segredo="") as c:
        r = await c.post(ROTA, json=_corpo(), headers={_CABECALHO: _SEGREDO})

    assert r.status_code == 503
    s.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_servidor_sem_segredo_recusa_mesmo_sem_cabecalho(_limpa_overrides):
    """O caso que um `if` invertido deixaria passar: nada no servidor, nada no
    cliente, e os dois "vazios" se encontrando num 200."""
    async with _cliente(_sessao(), segredo="") as c:
        r = await c.post(ROTA, json=_corpo())

    assert r.status_code == 503


def test_a_comparacao_do_segredo_e_em_tempo_constante():
    """`==` de string retorna no primeiro byte diferente, e o tempo vaza o prefixo.

    ⚠️ A verificação é por **AST, dentro da função**, e não por `grep` no módulo.
    A primeira versão deste teste fazia `assert "compare_digest" in fonte` e
    **SOBREVIVEU à mutação**: trocar a chamada por `==` deixava a docstring do
    módulo — que cita `hmac.compare_digest` para explicar a regra — intacta, e o
    grep continuava achando a palavra. Terceira vez que uma sentinela textual
    deste projeto foi enganada pelo texto que explica a própria regra; as outras
    duas foram o `424` em `api4com.py` e o `record_url` no router.
    """
    import ast
    import inspect

    from app.core import integracao

    arvore = ast.parse(inspect.getsource(integracao))
    funcao = next(
        n
        for n in ast.walk(arvore)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "exige_segredo_de_integracao"
    )

    chamadas = {
        no.func.attr
        for no in ast.walk(funcao)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
    }
    assert "compare_digest" in chamadas, "a comparação do segredo deixou de ser constante"

    # E nenhuma comparação de igualdade envolvendo o segredo.
    for no in ast.walk(funcao):
        if isinstance(no, ast.Compare) and any(isinstance(op, ast.Eq | ast.NotEq) for op in no.ops):
            envolvidos = {x.id for x in ast.walk(no) if isinstance(x, ast.Name)}
            assert (
                not {"esperado", "recebido"} & envolvidos
            ), f"comparação de igualdade com o segredo: {envolvidos}"


def _acha_rota(app, funcao):
    """Acha a rota pela FUNÇÃO que a implementa, descendo nos routers incluídos.

    ⚠️ Duas armadilhas aqui, e as duas custaram execução vermelha antes de o
    teste ficar honesto. Primeira: nesta versão do FastAPI os routers incluídos
    aparecem em `app.routes` como `_IncludedRouter`, não achatados — varredura
    rasa não acha nada. Segunda: a `APIRoute` de dentro guarda o caminho SEM o
    prefixo, que vive no wrapper — procurar por `/api/v1/...` também não acha.

    Casar pela função resolve as duas e não depende de como o prefixo é montado.
    E `raise` quando não encontra é essencial: um `_acha_rota` que devolvesse
    `None` faria o teste passar por vacuidade.

    A descida precisa seguir `original_router`, e não `routes`: o
    `_IncludedRouter` guarda o router de origem nesse atributo e não expõe as
    rotas diretamente.
    """
    pilha = list(app.routes)
    while pilha:
        atual = pilha.pop()
        if getattr(atual, "endpoint", None) is funcao and hasattr(atual, "dependant"):
            return atual
        pilha.extend(getattr(atual, "routes", []))
        origem = getattr(atual, "original_router", None)
        if origem is not None:
            pilha.extend(getattr(origem, "routes", []))
    raise AssertionError(f"rota de {funcao.__name__} não encontrada")


def test_a_rota_nao_depende_de_sessao():
    """Sessão NÃO é alternativa ao segredo.

    Se `get_current_user` aparecer nas dependências desta rota, qualquer usuário
    autenticado — inclusive `client` — alcança a integração.
    """
    from app.core.integracao import exige_segredo_de_integracao
    from app.core.security import get_current_user
    from app.main import app
    from app.routers.integrations import registra_chamada_encerrada

    rota = _acha_rota(app, registra_chamada_encerrada)

    def _todas(dependant):
        for d in dependant.dependencies:
            yield d.call
            yield from _todas(d)

    chamadas = set(_todas(rota.dependant))
    assert get_current_user not in chamadas, "a rota de integração aceita sessão"
    assert exige_segredo_de_integracao in chamadas, "a rota perdeu a exigência do segredo"


# ═══════════════════════════════════════════════════════════════
# O contrato do corpo
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_uuid_invalido_e_422(_limpa_overrides):
    async with _cliente(_sessao()) as c:
        r = await c.post(
            ROTA, json=_corpo(ticket_call_id="nao-sou-uuid"), headers={_CABECALHO: _SEGREDO}
        )

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_ticket_call_id_e_obrigatorio(_limpa_overrides):
    corpo = _corpo()
    del corpo["ticket_call_id"]
    async with _cliente(_sessao()) as c:
        r = await c.post(ROTA, json=corpo, headers={_CABECALHO: _SEGREDO})

    assert r.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "campo,valor",
    [
        ("record_url", _RECORD_URL),
        ("caller", "1019"),
        ("called", _TELEFONE),
        ("metadata", {"gateway": "HelpHS"}),
        ("provider_call_id", "qualquer-coisa"),
    ],
)
async def test_nada_do_fornecedor_entra_no_contrato(campo, valor, _limpa_overrides):
    """Conjunto FECHADO. Ignorar seria seguro para o efeito e péssimo para a
    detecção: a integração mandaria dado sensível por meses sem ninguém notar."""
    s = _sessao()
    async with _cliente(s) as c:
        r = await c.post(ROTA, json=_corpo(**{campo: valor}), headers={_CABECALHO: _SEGREDO})

    assert r.status_code == 422
    s.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_os_tres_campos_de_desfecho_sao_opcionais(_limpa_overrides):
    """Chamada não completada chega sem duração e sem gravação. Exigir recusaria
    um evento verdadeiro."""
    s = _sessao(rowcount=1)
    async with _cliente(s) as c:
        r = await c.post(
            ROTA, json={"ticket_call_id": _TICKET_CALL_ID}, headers={_CABECALHO: _SEGREDO}
        )

    assert r.status_code == 204


def test_o_schema_nao_tem_record_url():
    from app.schemas.telefonia import EventoDeEncerramento

    campos = set(EventoDeEncerramento.model_fields)
    assert campos == {"ticket_call_id", "duration", "hangup_cause", "recording_available"}
    for proibido in ("record_url", "recording_url", "caller", "called", "metadata"):
        assert proibido not in campos


# ═══════════════════════════════════════════════════════════════
# Desfechos
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ticket_call_inexistente_e_404(_limpa_overrides):
    """Separado do duplicado de propósito: é o sinal de roteamento errado."""
    s = _sessao(rowcount=0, existe=False)
    async with _cliente(s) as c:
        r = await c.post(ROTA, json=_corpo(), headers={_CABECALHO: _SEGREDO})

    assert r.status_code == 404
    s.commit.assert_not_awaited(), "commitou sem ter escrito nada"


@pytest.mark.asyncio
async def test_evento_duplicado_e_204_e_nao_commita(_limpa_overrides):
    """`rowcount == 0` com a linha existindo: já havia evento. Nada é tocado."""
    s = _sessao(rowcount=0, existe=True)
    async with _cliente(s) as c:
        r = await c.post(ROTA, json=_corpo(), headers={_CABECALHO: _SEGREDO})

    assert r.status_code == 204
    s.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_rowcount_zero_nao_e_assumido_como_duplicado(_limpa_overrides):
    """A função CONFERE a existência antes de decidir — não presume."""
    s = _sessao(rowcount=0, existe=False)
    async with _cliente(s) as c:
        await c.post(ROTA, json=_corpo(), headers={_CABECALHO: _SEGREDO})

    s.scalar.assert_awaited_once(), "decidiu sem conferir se a linha existe"


# ═══════════════════════════════════════════════════════════════
# Vazamento
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_nenhuma_resposta_carrega_segredo_ou_dado_do_fornecedor(_limpa_overrides):
    async with _cliente(_sessao()) as c:
        respostas = [
            await c.post(ROTA, json=_corpo(), headers={_CABECALHO: _SEGREDO}),
            await c.post(ROTA, json=_corpo(), headers={_CABECALHO: "errado"}),
            await c.post(ROTA, json=_corpo(record_url=_RECORD_URL), headers={_CABECALHO: _SEGREDO}),
        ]

    for r in respostas:
        texto = r.text
        assert _SEGREDO not in texto
        assert _RECORD_URL not in texto
        assert _TELEFONE not in texto
        assert "listener" not in texto


@pytest.mark.asyncio
async def test_o_log_nao_carrega_segredo_telefone_nem_record_url(_limpa_overrides, caplog):
    from loguru import logger

    capturado: list[str] = []
    sink = logger.add(capturado.append, level="DEBUG")
    try:
        async with _cliente(_sessao(rowcount=1)) as c:
            await c.post(ROTA, json=_corpo(), headers={_CABECALHO: _SEGREDO})
        async with _cliente(_sessao(rowcount=0, existe=False)) as c:
            await c.post(ROTA, json=_corpo(), headers={_CABECALHO: _SEGREDO})
    finally:
        logger.remove(sink)

    tudo = "".join(capturado)
    for proibido in (_SEGREDO, _RECORD_URL, _TELEFONE, "listener"):
        assert proibido not in tudo
    # O id completo também não: só a cauda de 6.
    assert _TICKET_CALL_ID not in tudo
    assert "...6a40bb" in tudo, "o log perdeu a cauda que permite investigar"


def test_o_router_de_integracoes_nao_importa_nada_de_gravacao():
    """Sentinela de escopo: esta rodada não baixa áudio e não consulta o CDR.

    ⚠️ A varredura é por **AST**, e não por `grep` no texto. A versão textual
    desta sentinela reprovou na primeira execução por achar `record_url` na
    própria docstring que diz que ele é proibido — exatamente o defeito que a
    sentinela do HTTP 424 já tinha cobrado em `api4com.py`. Comentário e
    docstring são onde a proibição é EXPLICADA; o que não pode existir é código.
    """
    import ast
    import inspect

    from app.routers import integrations

    arvore = ast.parse(inspect.getsource(integrations))

    # Os NÓS de docstring, colhidos por identidade. `ast.get_docstring` devolve o
    # texto já limpo e dedentado, que NÃO bate com o `Constant.value` bruto —
    # subtrair por valor falha em silêncio, e foi o que falhou aqui antes.
    docstrings = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            corpo = getattr(no, "body", [])
            if (
                corpo
                and isinstance(corpo[0], ast.Expr)
                and isinstance(corpo[0].value, ast.Constant)
                and isinstance(corpo[0].value.value, str)
            ):
                docstrings.add(id(corpo[0].value))

    nomes: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name):
            nomes.add(no.id)
        elif isinstance(no, ast.Attribute):
            nomes.add(no.attr)
        elif isinstance(no, ast.Constant) and isinstance(no.value, str):
            if id(no) not in docstrings:
                nomes.add(no.value)
        elif isinstance(no, ast.Import | ast.ImportFrom):
            nomes.add(getattr(no, "module", "") or "")
            nomes.update(a.name for a in no.names)

    codigo = " ".join(nomes)
    for proibido in ("record_url", "recording_url", "httpx", "api4com", "download", "mp3"):
        assert proibido not in codigo, f"{proibido!r} apareceu em CÓDIGO do router"


# ═══════════════════════════════════════════════════════════════
# O service, direto
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_o_update_exige_hangup_event_received_at_nulo():
    """A trava de idempotência mora na cláusula do UPDATE, não num `if`."""
    s = _sessao(rowcount=1)
    await telefonia.registra_encerramento(
        s,
        ticket_call_id=uuid.UUID(_TICKET_CALL_ID),
        duration_seconds=9,
        hangup_cause="NORMAL_CLEARING",
        recording_available=True,
    )

    sql = str(s.execute.await_args.args[0])
    assert "hangup_event_received_at IS NULL" in sql
    assert "UPDATE ticket_calls" in sql


@pytest.mark.asyncio
async def test_o_horario_gravado_e_o_nosso_e_nao_o_do_fornecedor():
    """O fornecedor divergiu ~3h e manda campo sem fuso. Esta coluna é nossa."""
    from datetime import UTC, datetime

    s = _sessao(rowcount=1)
    antes = datetime.now(UTC)
    await telefonia.registra_encerramento(
        s,
        ticket_call_id=uuid.UUID(_TICKET_CALL_ID),
        duration_seconds=9,
        hangup_cause="NORMAL_CLEARING",
        recording_available=True,
    )
    depois = datetime.now(UTC)

    valores = s.execute.await_args.args[0].compile().params
    gravado = valores["hangup_event_received_at"]
    assert antes <= gravado <= depois
    assert gravado.tzinfo is not None, "gravou horário ingênuo"
