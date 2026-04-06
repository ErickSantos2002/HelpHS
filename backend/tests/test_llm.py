"""
Unit tests for the LLM service (T52 — Sprint 6).
All HTTP calls are mocked; no real API keys required.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
