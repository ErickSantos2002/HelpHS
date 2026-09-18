"""
Unit tests for the LLM service (T52 — Sprint 6).
All HTTP calls are mocked; no real API keys required.

O DeepSeek e o unico provedor. Os testes que existiam mockavam OpenAI e
Anthropic; os que sobreviveram foram reescritos para provar a MESMA coisa
contra o provedor unico, e os que so existiam por causa do fallback foram
trocados por um que prova o oposto: que nao ha segunda tentativa.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from loguru import logger

from app.services import llm
from app.services.llm import (
    _parse_json_response,
    classify_ticket,
    improve_message,
    suggest_reply,
    summarize_conversation,
)

# ═══════════════════════════════════════════════════════════════
# Ferramentas dos testes
# ═══════════════════════════════════════════════════════════════


def _resposta_deepseek(conteudo: str) -> MagicMock:
    """Envelope de chat-completions que o DeepSeek devolve."""
    resposta = MagicMock()
    resposta.json.return_value = {"choices": [{"message": {"content": conteudo}}]}
    resposta.raise_for_status = MagicMock()
    return resposta


def _cliente_http(*, resposta: MagicMock | None = None, erro: Exception | None = None) -> AsyncMock:
    cliente = AsyncMock()
    cliente.__aenter__ = AsyncMock(return_value=cliente)
    cliente.__aexit__ = AsyncMock(return_value=False)
    cliente.post = AsyncMock(side_effect=erro) if erro else AsyncMock(return_value=resposta)
    return cliente


def _configura(s: MagicMock) -> None:
    """Configuracao valida. Cada teste sobrescreve o que quiser isolar."""
    s.deepseek_api_key = "sk-chave-valida"
    s.deepseek_model = "deepseek-chat"
    s.deepseek_base_url = "https://api.deepseek.com/v1"
    s.llm_temperature = 0.3
    s.llm_request_timeout_seconds = 30


@contextmanager
def _capturando_avisos():
    """Coleta tudo que o loguru emitir em WARNING ou acima."""
    registros: list[str] = []
    sink = logger.add(lambda mensagem: registros.append(str(mensagem)), level="WARNING")
    try:
        yield registros
    finally:
        logger.remove(sink)


# ═══════════════════════════════════════════════════════════════
# _parse_json_response
# ═══════════════════════════════════════════════════════════════


def test_parse_json_valid():
    text = '{"priority": "high", "confidence": 0.9, "summary": "Equipamento com falha"}'
    result = _parse_json_response(text)
    assert result is not None
    assert result["priority"] == "high"
    assert result["confidence"] == 0.9
    assert result["summary"] == "Equipamento com falha"


def test_parse_json_strips_markdown_fences():
    text = '```json\n{"priority": "low", "confidence": 0.5, "summary": "Rotina"}\n```'
    result = _parse_json_response(text)
    assert result is not None
    assert result["priority"] == "low"


def test_parse_json_invalid_priority_returns_none():
    text = '{"priority": "urgent", "confidence": 0.9, "summary": "x"}'
    assert _parse_json_response(text) is None


def test_parse_json_missing_fields_uses_defaults():
    text = '{"priority": "medium"}'
    result = _parse_json_response(text)
    assert result is not None
    assert result["confidence"] == 0.0
    assert result["summary"] == ""


def test_parse_json_confidence_clamped():
    text = '{"priority": "critical", "confidence": 99.0, "summary": "x"}'
    result = _parse_json_response(text)
    assert result["confidence"] == 1.0


def test_parse_json_fallback_regex():
    """Should still parse even with surrounding text."""
    text = 'Here is the result: {"priority": "medium", "confidence": 0.7, "summary": "ok"} done.'
    result = _parse_json_response(text)
    assert result is not None
    assert result["priority"] == "medium"


def test_parse_json_completely_invalid_returns_none():
    assert _parse_json_response("not json at all") is None


# ═══════════════════════════════════════════════════════════════
# A chamada: URL, modelo e temperature vem da configuracao
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_a_url_o_modelo_e_a_temperature_vem_da_configuracao():
    """
    O trabalho de hoje foi tirar a URL do codigo. Este teste prende isso: se
    alguem voltar a fixar a URL do provedor numa string literal, a URL de teste
    abaixo nao aparece na chamada e o teste cai.
    """
    cliente = _cliente_http(
        resposta=_resposta_deepseek('{"priority": "high", "confidence": 0.9, "summary": "x"}')
    )

    with (
        patch("app.services.llm.settings") as s,
        patch("app.services.llm.httpx.AsyncClient", return_value=cliente),
    ):
        _configura(s)
        s.deepseek_base_url = "https://exemplo.invalido/v9"
        s.deepseek_model = "modelo-de-teste"
        s.llm_temperature = 0.11

        await classify_ticket("Titulo", "Descricao", "geral")

    url = cliente.post.await_args.args[0]
    corpo = cliente.post.await_args.kwargs["json"]
    assert url == "https://exemplo.invalido/v9/chat/completions"
    assert corpo["model"] == "modelo-de-teste"
    assert corpo["temperature"] == 0.11


@pytest.mark.asyncio
async def test_a_barra_sobrando_na_base_url_nao_duplica_no_caminho():
    """Quem digita a URL no painel do EasyPanel termina com barra metade das vezes."""
    cliente = _cliente_http(
        resposta=_resposta_deepseek('{"priority": "low", "confidence": 0.1, "summary": "x"}')
    )

    with (
        patch("app.services.llm.settings") as s,
        patch("app.services.llm.httpx.AsyncClient", return_value=cliente),
    ):
        _configura(s)
        s.deepseek_base_url = "https://exemplo.invalido/v9/"

        await classify_ticket("Titulo", "Descricao", "geral")

    assert cliente.post.await_args.args[0] == "https://exemplo.invalido/v9/chat/completions"


@pytest.mark.asyncio
async def test_uma_falha_nao_dispara_uma_segunda_tentativa():
    """
    Substitui o antigo `test_classify_ticket_falls_back_to_anthropic`.

    Aquele provava que a falha do primeiro provedor levava ao segundo. Com um
    provedor so, o que precisa ficar preso e o contrario: falhou, acabou. Um
    segundo POST aqui seria fallback ressuscitado por engano.
    """
    cliente = _cliente_http(erro=Exception("timeout"))

    with (
        patch("app.services.llm.settings") as s,
        patch("app.services.llm.httpx.AsyncClient", return_value=cliente),
    ):
        _configura(s)
        resultado = await classify_ticket("Titulo", "Descricao", "geral")

    assert resultado is None
    assert cliente.post.await_count == 1


# ═══════════════════════════════════════════════════════════════
# O caminho sem chave: None em silencio
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sem_chave_as_quatro_devolvem_none_sem_excecao_e_sem_log_de_erro():
    """
    E o estado de producao hoje: a IA esta desligada e a chave nao existe. O
    sistema nao pode nem estourar, nem sujar o log com aviso a cada chamado
    aberto. `is None` sozinho nao provaria isso — passaria com a requisicao
    saindo e falhando. Por isso o teste tambem olha a rede e o log.
    """
    historico = [{"sender": "Joao", "role": "client", "content": "oi"}]

    with (
        patch.object(llm.settings, "deepseek_api_key", ""),
        patch("app.services.llm.httpx.AsyncClient") as cliente,
        _capturando_avisos() as avisos,
    ):
        assert await classify_ticket("Titulo", "Descricao", "geral") is None
        assert await suggest_reply("T", "D", "geral", "high", "open", historico) is None
        assert await summarize_conversation("T", "geral", "open", historico) is None
        assert await improve_message("rascunho", "T", "D") is None

    cliente.assert_not_called()
    assert avisos == [], f"log sujo com a IA sem chave: {avisos}"


@pytest.mark.asyncio
async def test_chave_de_placeholder_conta_como_ausente():
    """`CHANGE_ME` no painel e o mesmo que chave nenhuma."""
    with (
        patch.object(llm.settings, "deepseek_api_key", "CHANGE_ME_DEEPSEEK"),
        patch("app.services.llm.httpx.AsyncClient") as cliente,
    ):
        assert await classify_ticket("Titulo", "Descricao", "geral") is None

    cliente.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# classify_ticket — JSON estruturado
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_classify_ticket_devolve_prioridade_e_confianca():
    cliente = _cliente_http(
        resposta=_resposta_deepseek(
            '{"priority": "high", "confidence": 0.85, "summary": "Falha critica"}'
        )
    )

    with (
        patch("app.services.llm.settings") as s,
        patch("app.services.llm.httpx.AsyncClient", return_value=cliente),
    ):
        _configura(s)
        result = await classify_ticket("Sistema fora do ar", "ERP nao inicia", "software")

    assert result is not None
    assert result["priority"] == "high"
    assert result["confidence"] == 0.85
    assert result["summary"] == "Falha critica"


@pytest.mark.asyncio
async def test_classify_ticket_com_json_ilegivel_devolve_none():
    """A resposta chegou, mas nao e o contrato. Nao inventa prioridade."""
    cliente = _cliente_http(resposta=_resposta_deepseek("desculpe, nao posso ajudar"))

    with (
        patch("app.services.llm.settings") as s,
        patch("app.services.llm.httpx.AsyncClient", return_value=cliente),
    ):
        _configura(s)
        assert await classify_ticket("Titulo", "Descricao", "geral") is None


@pytest.mark.asyncio
async def test_classify_ticket_falha_de_rede_devolve_none():
    cliente = _cliente_http(erro=Exception("network error"))

    with (
        patch("app.services.llm.settings") as s,
        patch("app.services.llm.httpx.AsyncClient", return_value=cliente),
    ):
        _configura(s)
        assert await classify_ticket("Titulo", "Descricao", "geral") is None


# ═══════════════════════════════════════════════════════════════
# suggest_reply — texto
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_suggest_reply_devolve_o_campo_suggestion():
    cliente = _cliente_http(
        resposta=_resposta_deepseek('{"suggestion": "Prezado usuario, ja estamos analisando."}')
    )

    with (
        patch("app.services.llm.settings") as s,
        patch("app.services.llm.httpx.AsyncClient", return_value=cliente),
    ):
        _configura(s)
        result = await suggest_reply(
            title="VPN lenta",
            description="Dificuldade de acesso remoto",
            category="network",
            priority="medium",
            status="open",
            history=[{"sender": "Joao", "role": "client", "content": "A VPN esta muito lenta"}],
        )

    assert result == "Prezado usuario, ja estamos analisando."


@pytest.mark.asyncio
async def test_suggest_reply_ignora_resposta_sem_o_campo():
    """Campo errado no JSON e resposta invalida — nao vira texto solto."""
    cliente = _cliente_http(resposta=_resposta_deepseek('{"resposta": "texto no campo errado"}'))

    with (
        patch("app.services.llm.settings") as s,
        patch("app.services.llm.httpx.AsyncClient", return_value=cliente),
    ):
        _configura(s)
        result = await suggest_reply(
            title="x",
            description="y",
            category="general",
            priority="low",
            status="open",
            history=[],
        )

    assert result is None


# ═══════════════════════════════════════════════════════════════
# summarize_conversation — texto
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_summarize_conversation_devolve_o_campo_summary():
    cliente = _cliente_http(
        resposta=_resposta_deepseek('{"summary": "Bafometro com falha de hardware."}')
    )

    with (
        patch("app.services.llm.settings") as s,
        patch("app.services.llm.httpx.AsyncClient", return_value=cliente),
    ):
        _configura(s)
        result = await summarize_conversation(
            title="Bafometro com falha",
            category="hardware",
            status="resolved",
            history=[
                {"sender": "Joao", "role": "client", "content": "O bafometro nao liga"},
                {
                    "sender": "Tecnico",
                    "role": "technician",
                    "content": "Identificamos falha de hardware",
                },
            ],
        )

    assert result == "Bafometro com falha de hardware."


@pytest.mark.asyncio
async def test_summarize_conversation_empty_history_returns_none():
    """Returns None immediately with empty history."""
    result = await summarize_conversation(title="x", category="general", status="open", history=[])
    assert result is None


# ═══════════════════════════════════════════════════════════════
# improve_message — texto
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_improve_message_devolve_o_campo_improved():
    """
    Nao existia teste proprio desta funcao. Ela so aparecia no teste da flag
    desligada, que passa com a funcao inteira quebrada — basta devolver None.
    """
    cliente = _cliente_http(
        resposta=_resposta_deepseek('{"improved": "Prezado cliente, seguem as orientacoes."}')
    )

    with (
        patch("app.services.llm.settings") as s,
        patch("app.services.llm.httpx.AsyncClient", return_value=cliente),
    ):
        _configura(s)
        result = await improve_message("segue ai as orientacao", "Titulo", "Descricao")

    assert result == "Prezado cliente, seguem as orientacoes."


@pytest.mark.asyncio
async def test_improve_message_ignora_resposta_sem_o_campo():
    cliente = _cliente_http(resposta=_resposta_deepseek('{"texto": "campo errado"}'))

    with (
        patch("app.services.llm.settings") as s,
        patch("app.services.llm.httpx.AsyncClient", return_value=cliente),
    ):
        _configura(s)
        assert await improve_message("rascunho", "Titulo", "Descricao") is None


# ═══════════════════════════════════════════════════════════════
# Cada funcao le o SEU campo
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cada_funcao_le_o_seu_proprio_campo():
    """
    A unificacao juntou o TRANSPORTE, nao a leitura. Uma resposta que traz os
    tres campos de uma vez prova que cada funcao pega o seu: se o parsing
    tivesse colapsado num campo so, duas das tres devolveriam o texto errado.
    """
    conteudo = (
        '{"suggestion": "sou a sugestao", "summary": "sou o resumo", "improved": "sou o melhorado"}'
    )

    async def _roda(chamada):
        cliente = _cliente_http(resposta=_resposta_deepseek(conteudo))
        with (
            patch("app.services.llm.settings") as s,
            patch("app.services.llm.httpx.AsyncClient", return_value=cliente),
        ):
            _configura(s)
            return await chamada()

    historico = [{"sender": "Joao", "role": "client", "content": "oi"}]

    assert (
        await _roda(lambda: suggest_reply("T", "D", "geral", "high", "open", historico))
        == "sou a sugestao"
    )
    assert await _roda(lambda: summarize_conversation("T", "geral", "open", historico)) == (
        "sou o resumo"
    )
    assert await _roda(lambda: improve_message("rascunho", "T", "D")) == "sou o melhorado"


# ═══════════════════════════════════════════════════════════════
# LLM_ENABLED — desligar a IA sem esvaziar chave
# ═══════════════════════════════════════════════════════════════
#
# Ate aqui a unica forma de parar de mandar conteudo de chamado para fora era
# apagar a chave do painel — uma manobra que tambem apaga a configuracao e que
# ninguem consegue desfazer sem ter a chave de novo. Com a flag, desligar e
# reversivel e nao destroi nada.


def _llm_desligado():
    """Patch da flag no modulo, que le settings uma vez na importacao."""
    return patch.object(llm.settings, "llm_enabled", False)


def _com_chave():
    """Chave valida, para isolar o efeito da flag."""
    return patch.object(llm.settings, "deepseek_api_key", "sk-chave-de-teste")


@pytest.mark.asyncio
async def test_com_a_flag_desligada_nenhuma_chamada_externa_acontece():
    """
    O que importa nao e o retorno, e a rede: o teste falha se qualquer HTTP
    sair. Um teste que so afirmasse `is None` passaria mesmo com a requisicao
    sendo feita e falhando.
    """
    with (
        _com_chave(),
        _llm_desligado(),
        patch("app.services.llm.httpx.AsyncClient") as cliente,
    ):
        assert await llm.classify_ticket("Titulo", "Descricao", "general") is None
        assert await llm.suggest_reply("Titulo", "Descricao", "general", "high", "open", []) is None
        assert await llm.summarize_conversation("Titulo", "general", "open", []) is None
        assert await llm.improve_message("rascunho", "Titulo", "Descricao") is None

    cliente.assert_not_called()


@pytest.mark.asyncio
async def test_com_a_flag_ligada_a_chamada_continua_acontecendo():
    """Nao-regressao: a flag nasce ligada e nao muda o comportamento de hoje."""
    resposta = _resposta_deepseek('{"priority": "high", "confidence": 0.9, "summary": "resumo"}')

    with _com_chave(), patch.object(llm.settings, "llm_enabled", True):
        with patch("app.services.llm.httpx.AsyncClient") as cliente:
            instancia = cliente.return_value.__aenter__.return_value
            instancia.post = AsyncMock(return_value=resposta)
            resultado = await llm.classify_ticket("Sistema fora", "ERP nao abre", "software")

    assert resultado is not None
    assert resultado["priority"] == "high"


def test_a_flag_nasce_ligada():
    """
    Padrao `True` de proposito: desligar por padrao apagaria a classificacao
    automatica em producao no deploy seguinte, sem ninguem pedir. Quem quiser
    parar o envio agora tem um interruptor — e e isso que faltava.
    """
    from app.core.config import Settings

    s = Settings(database_url="postgresql+asyncpg://u:p@localhost/db")
    assert s.llm_enabled is True


def test_a_chave_do_deepseek_nasce_vazia():
    """
    A chave vai para o painel do EasyPanel, nunca para o repositorio, e a IA so
    e ligada depois do documento de LGPD publicado. Default vazio e o que faz o
    caminho silencioso acima ser o comportamento padrao de quem sobe o projeto.
    """
    from app.core.config import Settings

    s = Settings(database_url="postgresql+asyncpg://u:p@localhost/db")
    assert s.deepseek_api_key == ""
    assert s.deepseek_base_url.startswith("https://")


# ── O corte do historico do resumo ────────────────────────────
#
# Era `history_text[:6000]`: junta todas as mensagens em ordem cronologica e
# guarda os 6000 primeiros caracteres. Numa conversa longa isso descarta
# justamente as mensagens MAIS RECENTES — o tecnico que abre o resumo para saber
# onde o chamado esta le o comeco dele.
#
# O titulo, a categoria e o status ja vao para o prompt por fora, entao o
# enunciado do problema nao depende do comeco do chat. O que nao pode faltar e o
# estado atual.


def _fala(indice: int, tamanho: int = 200) -> dict[str, str]:
    return {"role": "client", "sender": "Fulano", "content": f"m{indice} " + "x" * tamanho}


def test_o_historico_curto_entra_inteiro():
    falas = [_fala(i) for i in range(3)]

    texto, cortou = llm.montar_historico(falas)

    assert cortou is False
    assert "m0" in texto and "m1" in texto and "m2" in texto


def test_o_corte_guarda_as_mensagens_mais_recentes():
    """O conserto: antes guardava as MAIS ANTIGAS, que e o oposto do util."""
    falas = [_fala(i) for i in range(200)]

    texto, cortou = llm.montar_historico(falas)

    assert cortou is True
    assert "m199" in texto, "a mensagem mais recente ficou de fora"
    assert "m0 " not in texto, "a mais antiga sobreviveu — está cortando pelo lado errado"


def test_nenhuma_mensagem_e_cortada_ao_meio():
    """Fatiar por caractere produz linha truncada no meio de uma frase.

    O modelo recebe algo como "[client] Fulano: o erro é TIMEO" e trata como
    conteúdo íntegro. Montar mensagem a mensagem custa o mesmo e não mente.
    """
    falas = [_fala(i) for i in range(200)]

    texto, _ = llm.montar_historico(falas)

    for linha in texto.splitlines():
        if linha == llm._AVISO_DE_CORTE:
            continue  # o aviso tambem comeca com "[", e e legitimo
        assert linha.endswith("x"), f"linha truncada no meio: ...{linha[-40:]}"


def test_o_corte_avisa_que_houve_corte():
    """Quem lê o resumo precisa saber que ele não viu a conversa toda."""
    falas = [_fala(i) for i in range(200)]

    texto, cortou = llm.montar_historico(falas)

    assert cortou is True
    assert "anteriores" in texto.lower()


def test_o_orcamento_e_respeitado():
    falas = [_fala(i) for i in range(500)]

    texto, _ = llm.montar_historico(falas)

    assert len(texto) <= llm.LIMITE_HISTORICO_RESUMO * 1.2


def test_uma_mensagem_gigante_sozinha_nao_estoura_o_orcamento():
    """Caso de borda: uma única fala maior que o orçamento inteiro."""
    falas = [_fala(0, tamanho=llm.LIMITE_HISTORICO_RESUMO * 2)]

    texto, cortou = llm.montar_historico(falas)

    assert len(texto) <= llm.LIMITE_HISTORICO_RESUMO * 1.2
    assert cortou is True
