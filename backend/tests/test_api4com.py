"""
O transporte da API4COM — e, sobretudo, como ele FALHA.

A Fase 2A não disca para ninguém: a flag nasce desligada, o token nasce vazio e
nenhum router importa o módulo. O que se prova aqui é o contrato da requisição,
que é o que o fornecedor recusa em silêncio se estiver errado, e a classificação
da falha, que é o que decide se uma pessoa pode receber duas ligações.

O teste que mais importa deste arquivo não é nenhum dos de sucesso: é o grupo
que prende `post.await_count == 1`. `POST /calls` é a primeira escrita externa
do HelpHS, e um retry acrescentado por distração — ou por um `httpcore` novo
num rebuild — tocaria o telefone de alguém duas vezes sem ninguém pedir.

Nenhum teste toca a rede: o `httpx.AsyncClient` é substituído por um duplo,
como já fazem `test_llm.py` e `test_consulta_externa.py`.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from loguru import logger

from app.services import api4com
from app.services.api4com import (
    Api4ComDesligadaError,
    Api4ComIndisponivelError,
    Api4ComRecusadaError,
    Api4ComResultadoIndeterminadoError,
    create_call,
)

# Marcador que não existe em lugar nenhum do sistema: se ele aparecer numa
# mensagem de exceção ou numa linha de log, veio do token.
_TOKEN = "marcador-de-token-que-nao-pode-vazar-9Z7Q"

_CALLER = "1130000000"
_CALLED = "  +55 (81) 99999-9999  "  # sujo DE PROPÓSITO — ver o teste do byte a byte
_EXTENSION = "1001"


# ═══════════════════════════════════════════════════════════════
# Ferramentas dos testes
# ═══════════════════════════════════════════════════════════════


def _settings(
    *, ligada: bool = True, base_url: str = "https://exemplo.invalido/api/v1"
) -> MagicMock:
    """Settings de mentira, sem passar pela validação de boot.

    `api4com_token` precisa responder a `get_secret_value()` como o `SecretStr`
    de verdade responde — é por lá que o módulo lê o segredo.
    """
    s = MagicMock()
    s.api4com_enabled = ligada
    s.api4com_base_url = base_url
    s.api4com_timeout_seconds = 15
    s.api4com_token = MagicMock()
    s.api4com_token.get_secret_value = MagicMock(return_value=_TOKEN)
    return s


def _resposta(
    *, status: int = 200, conteudo: bytes = b"", json_devolve=None, json_erro=None
) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.content = conteudo
    if json_erro is not None:
        r.json = MagicMock(side_effect=json_erro)
    else:
        r.json = MagicMock(return_value=json_devolve)
    return r


def _cliente(*, resposta: MagicMock | None = None, erro: Exception | None = None) -> AsyncMock:
    """Duplo do AsyncClient que sabe `async with` — mesmo molde do test_llm."""
    c = AsyncMock()
    c.__aenter__ = AsyncMock(return_value=c)
    c.__aexit__ = AsyncMock(return_value=False)
    c.post = AsyncMock(side_effect=erro) if erro else AsyncMock(return_value=resposta)
    return c


def _monta(*, resposta=None, erro=None, ligada=True, base_url="https://exemplo.invalido/api/v1"):
    """Contexto com settings, cliente e transporte trocados. Devolve o duplo do cliente.

    O `AsyncHTTPTransport` também é substituído, e não por preguiça: construí-lo
    de verdade carrega o pacote de CAs do certifi e monta um `SSLContext`, que
    MEDIDO nesta máquina custa ~4 s. Como o `AsyncClient` aqui já é duplo, o
    transporte real nunca chega a ser usado — construí-lo em cada teste só
    somaria minutos à suíte. Quem prende o `retries=0` é o teste dedicado, que
    inspeciona a chamada à fábrica.
    """
    cliente = _cliente(resposta=resposta, erro=erro)
    return cliente, (
        patch.object(
            api4com, "get_settings", return_value=_settings(ligada=ligada, base_url=base_url)
        ),
        patch.object(api4com.httpx, "AsyncClient", return_value=cliente),
        patch.object(api4com.httpx, "AsyncHTTPTransport"),
    )


# ═══════════════════════════════════════════════════════════════
# A flag desligada não pode tocar a rede
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_desligada_nao_constroi_cliente_http():
    """Desligada é erro de uso, não estado normal — e não pode abrir socket.

    Diferente do `llm.py`, que devolve None em silêncio porque lá a ausência de
    chave É o estado de produção. Aqui, chamar o transporte com a integração
    desligada é defeito de quem chamou, e precisa doer.
    """
    with (
        patch.object(api4com, "get_settings", return_value=_settings(ligada=False)),
        patch.object(api4com.httpx, "AsyncClient") as fabrica,
    ):
        with pytest.raises(Api4ComDesligadaError):
            await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    fabrica.assert_not_called()


@pytest.mark.asyncio
async def test_desligada_nao_le_o_token():
    """Sem integração ligada, o segredo nem sai do SecretStr."""
    s = _settings(ligada=False)
    with patch.object(api4com, "get_settings", return_value=s):
        with pytest.raises(Api4ComDesligadaError):
            await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    s.api4com_token.get_secret_value.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# O cabeçalho — a casa nunca testou header de saída antes deste
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_authorization_e_o_token_cru():
    """`Authorization: <token>`. O fornecedor confirmou que é assim."""
    cliente, contextos = _monta(resposta=_resposta())
    with contextos[0], contextos[1], contextos[2]:
        await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert cliente.post.await_args.kwargs["headers"] == {"Authorization": _TOKEN}


@pytest.mark.asyncio
async def test_authorization_nao_leva_bearer():
    """O único header de saída que a casa tinha era `Bearer` (llm.py:173).

    Este teste existe porque copiar aquele molde é o erro mais provável — e a
    API4COM devolveria 401 sem explicar por quê.
    """
    cliente, contextos = _monta(resposta=_resposta())
    with contextos[0], contextos[1], contextos[2]:
        await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    enviado = cliente.post.await_args.kwargs["headers"]["Authorization"]
    assert "Bearer" not in enviado
    assert "bearer" not in enviado.lower()
    assert enviado == _TOKEN


# ═══════════════════════════════════════════════════════════════
# O payload
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_o_post_vai_para_calls():
    cliente, contextos = _monta(resposta=_resposta())
    with contextos[0], contextos[1], contextos[2]:
        await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert cliente.post.await_args.args[0] == "https://exemplo.invalido/api/v1/calls"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "base",
    [
        "https://exemplo.invalido/api/v1",
        "https://exemplo.invalido/api/v1/",
        "https://exemplo.invalido/api/v1///",
    ],
)
async def test_barra_sobrando_na_base_nao_duplica_na_url(base):
    """Quem preenche o painel não deveria precisar acertar a barra final."""
    cliente, contextos = _monta(resposta=_resposta(), base_url=base)
    with contextos[0], contextos[1], contextos[2]:
        await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert cliente.post.await_args.args[0] == "https://exemplo.invalido/api/v1/calls"


@pytest.mark.asyncio
async def test_called_chega_byte_a_byte_como_entrou():
    """O transporte NÃO normaliza telefone, e é isso que este teste prende.

    `_CALLED` entra com espaços, parênteses, hífen e `+55`. O formato que a
    API4COM aceita em `called` segue em aberto com o fornecedor: se este módulo
    "consertasse" o número, criaria uma segunda regra brasileira competindo com
    `app/utils/telefone.py` — e nenhuma das duas saberia da outra.
    """
    cliente, contextos = _monta(resposta=_resposta())
    with contextos[0], contextos[1], contextos[2]:
        await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert cliente.post.await_args.kwargs["json"]["called"] == _CALLED


@pytest.mark.asyncio
async def test_caller_e_extension_chegam_sem_transformacao():
    cliente, contextos = _monta(resposta=_resposta())
    with contextos[0], contextos[1], contextos[2]:
        await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    corpo = cliente.post.await_args.kwargs["json"]
    assert corpo["caller"] == _CALLER
    assert corpo["extension"] == _EXTENSION


@pytest.mark.asyncio
async def test_metadata_e_exatamente_o_gateway():
    """Grafia divergente faz o webhook parar em silêncio — não levanta erro."""
    cliente, contextos = _monta(resposta=_resposta())
    with contextos[0], contextos[1], contextos[2]:
        await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert cliente.post.await_args.kwargs["json"]["metadata"] == {"gateway": "HelpHS"}


@pytest.mark.asyncio
async def test_o_corpo_nao_tem_mais_nada_alem_dos_quatro_campos():
    """Duas integrações desta conta estão sem filtro de webhook.

    Se `webhookConstraint` vazia significar "sem filtro", o que sai daqui chega
    a endpoints de outros sistemas da empresa. Por isso o corpo é fechado: sem
    parâmetro de metadata, sem nome, sem e-mail, sem texto de chamado.
    """
    cliente, contextos = _monta(resposta=_resposta())
    with contextos[0], contextos[1], contextos[2]:
        await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    corpo = cliente.post.await_args.kwargs["json"]
    assert set(corpo) == {"caller", "called", "extension", "metadata"}
    assert set(corpo["metadata"]) == {"gateway"}


def test_create_call_nao_aceita_metadata():
    """Não dá para sobrescrever `gateway` porque não há por onde passar nada."""
    import inspect

    parametros = set(inspect.signature(create_call).parameters)
    assert parametros == {"caller", "called", "extension"}


# ═══════════════════════════════════════════════════════════════
# Retry e redirect — o grupo que impede ligação duplicada
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_o_transporte_e_construido_com_retries_zero():
    """Explícito, mesmo sendo o default do httpx.

    `httpcore` é transitiva e não está pinada: só `httpcore==1.*`. Se um
    rebuild trouxer outro default, é esta linha que segura.
    """
    cliente = _cliente(resposta=_resposta())
    with (
        patch.object(api4com, "get_settings", return_value=_settings()),
        patch.object(api4com.httpx, "AsyncClient", return_value=cliente),
        patch.object(api4com.httpx, "AsyncHTTPTransport") as transporte,
    ):
        await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    transporte.assert_called_once_with(retries=0)


@pytest.mark.asyncio
async def test_o_cliente_nao_segue_redirect():
    """307 e 308 preservam método e corpo: seguir seria criar a ligação duas vezes."""
    cliente = _cliente(resposta=_resposta())
    with (
        patch.object(api4com, "get_settings", return_value=_settings()),
        patch.object(api4com.httpx, "AsyncClient", return_value=cliente) as fabrica,
        patch.object(api4com.httpx, "AsyncHTTPTransport"),
    ):
        await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert fabrica.call_args.kwargs["follow_redirects"] is False


@pytest.mark.asyncio
async def test_o_timeout_vem_da_configuracao():
    cliente = _cliente(resposta=_resposta())
    with (
        patch.object(api4com, "get_settings", return_value=_settings()),
        patch.object(api4com.httpx, "AsyncClient", return_value=cliente) as fabrica,
        patch.object(api4com.httpx, "AsyncHTTPTransport"),
    ):
        await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert fabrica.call_args.kwargs["timeout"] == 15


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "erro",
    [
        httpx.ReadTimeout("demorou"),
        httpx.ConnectError("recusado"),
        httpx.ConnectTimeout("sem resposta"),
        httpx.WriteTimeout("escrita"),
        httpx.RemoteProtocolError("protocolo"),
    ],
    ids=["ReadTimeout", "ConnectError", "ConnectTimeout", "WriteTimeout", "RemoteProtocolError"],
)
async def test_nenhuma_falha_dispara_um_segundo_post(erro):
    """Falhou, acabou — em TODOS os modos de falha, não só nos de conexão.

    Mesma disciplina de `test_llm.py::test_uma_falha_nao_dispara_uma_segunda_tentativa`,
    mas aqui a consequência de errar é uma pessoa sendo ligada duas vezes.
    """
    cliente, contextos = _monta(erro=erro)
    with contextos[0], contextos[1], contextos[2]:
        with pytest.raises((Api4ComIndisponivelError, Api4ComResultadoIndeterminadoError)):
            await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert cliente.post.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 302, 307, 308, 400, 401, 422, 429, 500, 502, 503, 504])
async def test_nenhuma_resposta_de_erro_dispara_um_segundo_post(status):
    """Vale para TODA faixa: 3xx, 4xx e 5xx saem com um único POST."""
    cliente, contextos = _monta(resposta=_resposta(status=status))
    with contextos[0], contextos[1], contextos[2]:
        with pytest.raises((Api4ComRecusadaError, Api4ComResultadoIndeterminadoError)):
            await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert cliente.post.await_count == 1


# ═══════════════════════════════════════════════════════════════
# A classificação das falhas: a ligação saiu?
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "erro",
    [httpx.ConnectError("recusado"), httpx.ConnectTimeout("sem resposta")],
    ids=["ConnectError", "ConnectTimeout"],
)
async def test_falha_de_conexao_prova_que_a_ligacao_nao_saiu(erro):
    """O laço do httpcore cobre só TCP/TLS: nenhum byte de requisição foi escrito."""
    _, contextos = _monta(erro=erro)
    with contextos[0], contextos[1], contextos[2]:
        with pytest.raises(Api4ComIndisponivelError):
            await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "erro",
    [
        httpx.ReadTimeout("leitura"),
        httpx.ReadError("leitura"),
        httpx.WriteTimeout("escrita"),
        httpx.WriteError("escrita"),
        httpx.RemoteProtocolError("protocolo"),
        httpx.PoolTimeout("pool"),
        httpx.ProxyError("proxy"),
    ],
    ids=[
        "ReadTimeout",
        "ReadError",
        "WriteTimeout",
        "WriteError",
        "RemoteProtocolError",
        "PoolTimeout",
        "ProxyError",
    ],
)
async def test_o_resto_do_transporte_e_conservadoramente_indeterminado(erro):
    """Se não dá para PROVAR que a ligação não saiu, ela pode estar tocando.

    `PoolTimeout` e `ProxyError` entram aqui de propósito. Dá para argumentar
    que em ambos a requisição não saiu — mas o argumento depende de detalhe
    interno de biblioteca não pinada, e o custo de errar para o lado otimista é
    ligar duas vezes para a mesma pessoa.
    """
    _, contextos = _monta(erro=erro)
    with contextos[0], contextos[1], contextos[2]:
        with pytest.raises(Api4ComResultadoIndeterminadoError):
            await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 429])
async def test_4xx_e_rejeicao_confirmada_com_status(status):
    """SÓ 4xx. E a afirmação é sobre a REQUISIÇÃO, não sobre o telefone."""
    cliente, contextos = _monta(resposta=_resposta(status=status))
    with contextos[0], contextos[1], contextos[2]:
        with pytest.raises(Api4ComRecusadaError) as capturado:
            await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert capturado.value.status_code == status
    assert cliente.post.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [500, 501, 502, 503, 504])
async def test_5xx_e_indeterminado_e_nao_recusa(status):
    """5xx NÃO prova que a ligação não saiu, e essa distinção custa caro.

    O fornecedor pode ter recebido o POST, disparado a chamada e só então
    quebrado por dentro: o 500 descreve o estado do servidor dele, não o do
    telefone de quem ia receber. Classificar como recusa autorizaria uma
    segunda tentativa — e tocaria o telefone duas vezes.
    """
    cliente, contextos = _monta(resposta=_resposta(status=status))
    with contextos[0], contextos[1], contextos[2]:
        with pytest.raises(Api4ComResultadoIndeterminadoError):
            await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert cliente.post.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_3xx_e_indeterminado_e_nao_e_seguido(status):
    """Redirect chega aqui sem ter sido seguido, e não é sucesso nem recusa.

    307 e 308 preservam método e corpo: se algum dia alguém ligar
    `follow_redirects`, o POST sai de novo. Enquanto estiver desligado, o
    redirect é resposta inesperada num endpoint de escrita — pode ter havido
    efeito antes dele.
    """
    cliente, contextos = _monta(resposta=_resposta(status=status))
    with contextos[0], contextos[1], contextos[2]:
        with pytest.raises(Api4ComResultadoIndeterminadoError):
            await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert cliente.post.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 302, 307, 308, 500, 502, 503, 504])
async def test_indeterminado_por_status_nao_guarda_nada(status):
    """Nem Response, nem Request, nem corpo, nem cabeçalho — nem atributo."""
    _, contextos = _monta(resposta=_resposta(status=status))
    with contextos[0], contextos[1], contextos[2]:
        with pytest.raises(Api4ComResultadoIndeterminadoError) as capturado:
            await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert vars(capturado.value) == {}
    assert _TOKEN not in str(capturado.value)
    assert _TOKEN not in repr(capturado.value)
    assert capturado.value.__cause__ is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "erro",
    [httpx.ReadTimeout, httpx.ConnectError],
    ids=["ReadTimeout", "ConnectError"],
)
async def test_nao_repetimos_a_mensagem_da_excecao_original(erro):
    """Se a biblioteca vazar o segredo no texto dela, nós não repetimos.

    Hoje o httpx não põe cabeçalho na mensagem, então este teste passaria
    mesmo se o módulo interpolasse `{exc}`. Ele existe para o caso contrário:
    uma versão futura que cite a requisição, ou um erro de proxy que traga o
    cabeçalho. A nossa mensagem é escrita do zero, e este teste prende isso —
    é o alvo da mutação que troca `from None` por texto do `exc`.
    """
    _, contextos = _monta(erro=erro(f"falhou ao enviar Authorization: {_TOKEN}"))
    with contextos[0], contextos[1], contextos[2]:
        with pytest.raises(
            (Api4ComIndisponivelError, Api4ComResultadoIndeterminadoError)
        ) as capturado:
            await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert _TOKEN not in str(capturado.value)
    assert _TOKEN not in repr(capturado.value)
    assert capturado.value.__cause__ is None


# ═══════════════════════════════════════════════════════════════
# A resposta 2xx — sem inventar schema
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_2xx_com_json_devolve_o_payload_sem_extrair_nada():
    """O caminho do identificador da chamada NÃO está confirmado.

    Enquanto não estiver, o payload volta inteiro e quem chamar decide. A Fase
    2B é quem acrescenta o campo, com evidência.
    """
    corpo = {"id": "abc-123", "status": "queued", "qualquer": {"coisa": 1}}
    _, contextos = _monta(resposta=_resposta(status=201, conteudo=b"{...}", json_devolve=corpo))
    with contextos[0], contextos[1], contextos[2]:
        resultado = await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert resultado.status_code == 201
    assert resultado.payload == corpo


@pytest.mark.asyncio
async def test_2xx_com_corpo_vazio_devolve_payload_none():
    _, contextos = _monta(resposta=_resposta(status=204, conteudo=b""))
    with contextos[0], contextos[1], contextos[2]:
        resultado = await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert resultado.status_code == 204
    assert resultado.payload is None


@pytest.mark.asyncio
async def test_2xx_com_corpo_ilegivel_e_indeterminado():
    """Respondeu, provavelmente criou — e não dá para afirmar. Regra conservadora."""
    _, contextos = _monta(
        resposta=_resposta(
            status=200, conteudo=b"<html>opa</html>", json_erro=ValueError("nao e json")
        )
    )
    with contextos[0], contextos[1], contextos[2]:
        with pytest.raises(Api4ComResultadoIndeterminadoError):
            await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)


def test_o_resultado_nao_tem_campo_de_identificador():
    """Prende a ausência: inventar `provider_call_id` aqui seria contrato falso."""
    campos = set(api4com.Api4ComCreateCallResult.__dataclass_fields__)
    assert campos == {"status_code", "payload"}


# ═══════════════════════════════════════════════════════════════
# O segredo não escapa por nenhum caminho de erro
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "erro",
    [httpx.ConnectError("recusado"), httpx.ReadTimeout("demorou"), httpx.WriteError("escrita")],
    ids=["ConnectError", "ReadTimeout", "WriteError"],
)
async def test_o_token_nao_aparece_na_excecao_de_transporte(erro):
    _, contextos = _monta(erro=erro)
    with contextos[0], contextos[1], contextos[2]:
        with pytest.raises(
            (Api4ComIndisponivelError, Api4ComResultadoIndeterminadoError)
        ) as capturado:
            await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert _TOKEN not in str(capturado.value)
    assert _TOKEN not in repr(capturado.value)


@pytest.mark.asyncio
async def test_o_token_nao_aparece_na_excecao_de_recusa():
    _, contextos = _monta(resposta=_resposta(status=401))
    with contextos[0], contextos[1], contextos[2]:
        with pytest.raises(Api4ComRecusadaError) as capturado:
            await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert _TOKEN not in str(capturado.value)
    assert _TOKEN not in repr(capturado.value)


@pytest.mark.asyncio
async def test_a_excecao_de_transporte_nao_encadeia_a_original():
    """`from None` de propósito.

    A exceção do httpx carrega `request` — e o `request` carrega os cabeçalhos
    por referência, `Authorization` incluído. Encadear a penduraria no
    `__cause__`, de onde qualquer traceback a alcançaria.
    """
    original = httpx.ReadTimeout("demorou")
    original.request = httpx.Request(
        "POST", "https://exemplo.invalido/api/v1/calls", headers={"Authorization": _TOKEN}
    )

    _, contextos = _monta(erro=original)
    with contextos[0], contextos[1], contextos[2]:
        with pytest.raises(Api4ComResultadoIndeterminadoError) as capturado:
            await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)

    assert capturado.value.__cause__ is None
    assert capturado.value.__context__ is None or _TOKEN not in str(capturado.value)


def test_nenhuma_excecao_do_modulo_guarda_request_ou_response():
    """Guardar o objeto do httpx levaria o Authorization por referência."""
    recusa = Api4ComRecusadaError(401)
    assert vars(recusa) == {"status_code": 401}

    for classe in (
        Api4ComDesligadaError,
        Api4ComIndisponivelError,
        Api4ComResultadoIndeterminadoError,
    ):
        assert vars(classe("mensagem")) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "erro",
    [httpx.ConnectError("recusado"), httpx.ReadTimeout("demorou")],
    ids=["ConnectError", "ReadTimeout"],
)
async def test_nenhum_caminho_de_erro_escreve_o_token_no_log(erro):
    linhas: list[str] = []
    sink = logger.add(lambda m: linhas.append(m.record["message"]), level="DEBUG")

    _, contextos = _monta(erro=erro)
    try:
        with contextos[0], contextos[1], contextos[2]:
            with pytest.raises((Api4ComIndisponivelError, Api4ComResultadoIndeterminadoError)):
                await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)
    finally:
        logger.remove(sink)

    assert _TOKEN not in "\n".join(linhas)


@pytest.mark.asyncio
async def test_o_telefone_tambem_nao_vai_para_o_log():
    """PII: `called` é telefone de pessoa e não entra em linha de log nenhuma."""
    linhas: list[str] = []
    sink = logger.add(lambda m: linhas.append(m.record["message"]), level="DEBUG")

    _, contextos = _monta(erro=httpx.ReadTimeout("demorou"))
    try:
        with contextos[0], contextos[1], contextos[2]:
            with pytest.raises(Api4ComResultadoIndeterminadoError):
                await create_call(caller=_CALLER, called=_CALLED, extension=_EXTENSION)
    finally:
        logger.remove(sink)

    assert _CALLED.strip() not in "\n".join(linhas)
