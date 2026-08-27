"""
Unit tests for the LLM service (T52 — Sprint 6).
All HTTP calls are mocked; no real API keys required.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import llm
from app.services.llm import (
    _parse_json_response,
    classify_ticket,
    suggest_reply,
    summarize_conversation,
)

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
# classify_ticket
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_classify_ticket_openai_success():
    """classify_ticket returns result when OpenAI succeeds."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"priority": "high", "confidence": 0.85, "summary": "Falha crítica"}'
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with (
        patch("app.services.llm.settings") as mock_settings,
        patch("app.services.llm.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.openai_api_key = "sk-valid-key"
        mock_settings.openai_model = "gpt-4o-mini"
        mock_settings.openai_temperature = 0.3
        mock_settings.llm_request_timeout_seconds = 30
        mock_settings.llm_fallback_enabled = True

        result = await classify_ticket("Sistema fora do ar", "ERP não inicia", "software")

    assert result is not None
    assert result["priority"] == "high"
    assert result["confidence"] == 0.85


@pytest.mark.asyncio
async def test_classify_ticket_placeholder_key_returns_none():
    """Returns None immediately when key is placeholder."""
    with patch("app.services.llm.settings") as mock_settings:
        mock_settings.openai_api_key = "sk-CHANGE_ME"
        mock_settings.anthropic_api_key = "sk-ant-CHANGE_ME"
        mock_settings.llm_fallback_enabled = True

        result = await classify_ticket("Título", "Descrição", "general")

    assert result is None


@pytest.mark.asyncio
async def test_classify_ticket_falls_back_to_anthropic():
    """Falls back to Anthropic when OpenAI fails."""
    anthropic_response = MagicMock()
    anthropic_response.json.return_value = {
        "content": [{"text": '{"priority": "medium", "confidence": 0.7, "summary": "Moderado"}'}]
    }
    anthropic_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    # First call (OpenAI) raises, second call (Anthropic) succeeds
    mock_client.post = AsyncMock(side_effect=[Exception("timeout"), anthropic_response])

    with (
        patch("app.services.llm.settings") as mock_settings,
        patch("app.services.llm.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.openai_api_key = "sk-valid"
        mock_settings.anthropic_api_key = "sk-ant-valid"
        mock_settings.openai_model = "gpt-4o-mini"
        mock_settings.anthropic_model = "claude-3-5-haiku-20241022"
        mock_settings.openai_temperature = 0.3
        mock_settings.llm_request_timeout_seconds = 30
        mock_settings.llm_fallback_enabled = True

        result = await classify_ticket("Problema de acesso", "VPN não conecta", "access")

    assert result is not None
    assert result["priority"] == "medium"


@pytest.mark.asyncio
async def test_classify_ticket_all_providers_fail_returns_none():
    """Returns None when all providers fail."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=Exception("network error"))

    with (
        patch("app.services.llm.settings") as mock_settings,
        patch("app.services.llm.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.openai_api_key = "sk-valid"
        mock_settings.anthropic_api_key = "sk-ant-valid"
        mock_settings.openai_model = "gpt-4o-mini"
        mock_settings.anthropic_model = "claude-3-5-haiku-20241022"
        mock_settings.openai_temperature = 0.3
        mock_settings.llm_request_timeout_seconds = 30
        mock_settings.llm_fallback_enabled = True

        result = await classify_ticket("Título", "Descrição", "general")

    assert result is None


# ═══════════════════════════════════════════════════════════════
# suggest_reply
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_suggest_reply_returns_text():
    """suggest_reply returns suggestion text on success."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {"message": {"content": '{"suggestion": "Prezado usuário, já estamos analisando."}'}}
        ]
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with (
        patch("app.services.llm.settings") as mock_settings,
        patch("app.services.llm.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.openai_api_key = "sk-valid"
        mock_settings.openai_model = "gpt-4o-mini"
        mock_settings.openai_temperature = 0.3
        mock_settings.llm_request_timeout_seconds = 30
        mock_settings.llm_fallback_enabled = False

        result = await suggest_reply(
            title="VPN lenta",
            description="Dificuldade de acesso remoto",
            category="network",
            priority="medium",
            status="open",
            history=[{"sender": "João", "role": "client", "content": "A VPN está muito lenta"}],
        )

    assert result is not None
    assert "analisando" in result


@pytest.mark.asyncio
async def test_suggest_reply_placeholder_key_returns_none():
    """Returns None when key is placeholder."""
    with patch("app.services.llm.settings") as mock_settings:
        mock_settings.openai_api_key = "CHANGE_ME"
        mock_settings.anthropic_api_key = "CHANGE_ME"
        mock_settings.llm_fallback_enabled = True

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
# summarize_conversation
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_summarize_conversation_returns_text():
    """summarize_conversation returns summary text on success."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"summary": "Usuário relatou problema com bafômetro. Técnico identificou falha de hardware."}'
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with (
        patch("app.services.llm.settings") as mock_settings,
        patch("app.services.llm.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.openai_api_key = "sk-valid"
        mock_settings.openai_model = "gpt-4o-mini"
        mock_settings.openai_temperature = 0.3
        mock_settings.llm_request_timeout_seconds = 30
        mock_settings.llm_fallback_enabled = False

        result = await summarize_conversation(
            title="Bafômetro com falha",
            category="hardware",
            status="resolved",
            history=[
                {"sender": "João", "role": "client", "content": "O bafômetro não liga"},
                {
                    "sender": "Técnico",
                    "role": "technician",
                    "content": "Identificamos falha de hardware",
                },
            ],
        )

    assert result is not None
    assert len(result) > 0


@pytest.mark.asyncio
async def test_summarize_conversation_empty_history_returns_none():
    """Returns None immediately with empty history."""
    result = await summarize_conversation(title="x", category="general", status="open", history=[])
    assert result is None


# ═══════════════════════════════════════════════════════════════
# LLM_ENABLED — desligar a IA sem esvaziar chave
# ═══════════════════════════════════════════════════════════════
#
# Até aqui a única forma de parar de mandar conteúdo de chamado para a OpenAI
# e a Anthropic era apagar as chaves do painel — uma manobra que também apaga
# a configuração e que ninguém consegue desfazer sem ter as chaves de novo.
# Com a flag, desligar é reversível e não destrói nada.


def _llm_desligado():
    """Patch da flag no módulo, que lê settings uma vez na importação."""
    from app.services import llm

    return patch.object(llm.settings, "llm_enabled", False)


def _com_chaves():
    """Chaves válidas nos dois provedores, para isolar o efeito da flag."""
    from app.services import llm

    return (
        patch.object(llm.settings, "openai_api_key", "sk-chave-de-teste"),
        patch.object(llm.settings, "anthropic_api_key", "sk-ant-chave-de-teste"),
    )


@pytest.mark.asyncio
async def test_com_a_flag_desligada_nenhuma_chamada_externa_acontece():
    """
    O que importa não é o retorno, é a rede: o teste falha se qualquer HTTP
    sair. Um teste que só afirmasse `is None` passaria mesmo com a requisição
    sendo feita e falhando.
    """
    from app.services import llm

    k1, k2 = _com_chaves()
    with k1, k2, _llm_desligado(), patch("app.services.llm.httpx.AsyncClient") as cliente:
        assert await llm.classify_ticket("Título", "Descrição", "general") is None
        assert await llm.suggest_reply("Título", "Descrição", "general", "high", "open", []) is None
        assert await llm.summarize_conversation("Título", "general", "open", []) is None
        assert await llm.improve_message("rascunho", "Título", "Descrição") is None

    cliente.assert_not_called()


@pytest.mark.asyncio
async def test_com_a_flag_ligada_a_chamada_continua_acontecendo():
    """Não-regressão: a flag nasce ligada e não muda o comportamento de hoje."""
    from app.services import llm

    resposta = MagicMock()
    resposta.status_code = 200
    resposta.json.return_value = {
        "choices": [
            {"message": {"content": '{"priority": "high", "confidence": 0.9, "summary": "resumo"}'}}
        ]
    }

    k1, k2 = _com_chaves()
    with k1, k2, patch.object(llm.settings, "llm_enabled", True):
        with patch("app.services.llm.httpx.AsyncClient") as cliente:
            instancia = cliente.return_value.__aenter__.return_value
            instancia.post = AsyncMock(return_value=resposta)
            resultado = await llm.classify_ticket("Sistema fora", "ERP não abre", "software")

    assert resultado is not None
    assert resultado["priority"] == "high"


def test_a_flag_nasce_ligada():
    """
    Padrão `True` de propósito: desligar por padrão apagaria a classificação
    automática em produção no deploy seguinte, sem ninguém pedir. Quem quiser
    parar o envio agora tem um interruptor — e é isso que faltava.
    """
    from app.core.config import Settings

    s = Settings(database_url="postgresql+asyncpg://u:p@localhost/db")
    assert s.llm_enabled is True


# ── O corte do histórico do resumo ────────────────────────────
#
# Era `history_text[:6000]`: junta todas as mensagens em ordem cronológica e
# guarda os 6000 primeiros caracteres. Numa conversa longa isso descarta
# justamente as mensagens MAIS RECENTES — o técnico que abre o resumo para saber
# onde o chamado está lê o começo dele.
#
# O título, a categoria e o status já vão para o prompt por fora, então o
# enunciado do problema não depende do começo do chat. O que não pode faltar é o
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
