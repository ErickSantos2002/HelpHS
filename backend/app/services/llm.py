"""
LLM Service — OpenAI primary + Anthropic fallback.

Usage
-----
result = await classify_ticket(title, description, category)
if result:
    priority, confidence, summary = result["priority"], result["confidence"], result["summary"]

All functions return None on failure (missing key, timeout, parse error),
so callers should treat None as "classification unavailable".
"""

import json
import re
from typing import Any

import httpx
from loguru import logger

from app.core.config import get_settings

settings = get_settings()

# ── Constants ─────────────────────────────────────────────────

_VALID_PRIORITIES = {"critical", "high", "medium", "low"}

_CLASSIFICATION_SYSTEM = (
    "Você é um assistente de triagem de chamados para uma empresa de "
    "Saúde & Segurança do Trabalho. Analise o ticket e responda APENAS "
    "com JSON válido, sem markdown, sem explicações."
)

_CLASSIFICATION_TEMPLATE = """Ticket:
Título: {title}
Descrição: {description}
Categoria: {category}

Responda com este JSON exato (sem markdown):
{{
  "priority": "critical|high|medium|low",
  "confidence": 0.0,
  "summary": "uma frase resumindo o problema em português"
}}

Diretrizes de prioridade:
- critical: sistemas essenciais fora do ar, risco de vida ou segurança imediata
- high: impacto significativo em múltiplos usuários ou operação crítica
- medium: impacto moderado, workaround disponível
- low: solicitação de rotina, sem urgência"""

_SUMMARIZE_SYSTEM = (
    "Você é um assistente de suporte técnico especializado em Saúde & Segurança do Trabalho. "
    "Seu papel é gerar resumos concisos de conversas de suporte para facilitar a transferência "
    "de chamados e o registro de histórico. Responda APENAS com JSON válido, sem markdown."
)

_SUMMARIZE_TEMPLATE = """Ticket de suporte:
Título: {title}
Categoria: {category}
Status: {status}

Conversa completa:
{history}

Gere um resumo objetivo da conversa em português (máximo 5 frases), destacando:
- O problema relatado
- Ações tomadas pelo suporte
- Situação atual / próximos passos

Responda com este JSON exato (sem markdown):
{{
  "summary": "texto do resumo"
}}"""

_SUGGEST_REPLY_SYSTEM = (
    "Você é um assistente de suporte técnico especializado em Saúde & Segurança do Trabalho. "
    "Seu papel é ajudar técnicos a redigir respostas profissionais, claras e empáticas para "
    "chamados de suporte. Responda APENAS com JSON válido, sem markdown, sem explicações."
)

_SUGGEST_REPLY_TEMPLATE = """Ticket de suporte:
Título: {title}
Descrição: {description}
Categoria: {category}
Prioridade: {priority}
Status: {status}

Histórico recente da conversa:
{history}

Gere uma sugestão de resposta profissional em português para o técnico enviar ao solicitante.
A resposta deve ser útil, empática e objetiva (2-4 parágrafos no máximo).

Responda com este JSON exato (sem markdown):
{{
  "suggestion": "texto da resposta sugerida"
}}"""


# ── Internal helpers ──────────────────────────────────────────


def _parse_json_response(text: str) -> dict[str, Any] | None:
    """Extract and validate JSON from LLM response text."""
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?", "", text).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find first {...} block
        match = re.search(r"\{[^{}]+\}", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return None

    priority = data.get("priority", "").lower()
    if priority not in _VALID_PRIORITIES:
        return None

    try:
        confidence = float(data.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.5

    summary = str(data.get("summary", "")).strip()[:500]

    return {"priority": priority, "confidence": confidence, "summary": summary}


# ── OpenAI ────────────────────────────────────────────────────


async def _call_openai(prompt: str) -> dict[str, Any] | None:
    key = settings.openai_api_key
    if not key or key.startswith("CHANGE_ME") or key.startswith("sk-CHANGE"):
        return None

    try:
        async with httpx.AsyncClient(timeout=settings.llm_request_timeout_seconds) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": settings.openai_model,
                    "messages": [
                        {"role": "system", "content": _CLASSIFICATION_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 256,
                    "temperature": settings.openai_temperature,
                },
            )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _parse_json_response(content)
    except Exception as exc:
        logger.warning(f"OpenAI classification failed: {exc}")
        return None


# ── Anthropic ─────────────────────────────────────────────────


async def _call_anthropic(prompt: str) -> dict[str, Any] | None:
    key = settings.anthropic_api_key
    if not key or key.startswith("CHANGE_ME") or key.startswith("sk-ant-CHANGE"):
        return None

    try:
        async with httpx.AsyncClient(timeout=settings.llm_request_timeout_seconds) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": settings.anthropic_model,
                    "max_tokens": 256,
                    "system": _CLASSIFICATION_SYSTEM,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        resp.raise_for_status()
        content = resp.json()["content"][0]["text"]
        return _parse_json_response(content)
    except Exception as exc:
        logger.warning(f"Anthropic classification failed: {exc}")
        return None


# ── Public API ────────────────────────────────────────────────


async def classify_ticket(
    title: str,
    description: str,
    category: str,
) -> dict[str, Any] | None:
    """
    Classify a ticket using the configured LLM provider.

    Returns dict with keys: priority, confidence, summary
    Returns None if all providers fail or keys are not configured.
    """
    prompt = _CLASSIFICATION_TEMPLATE.format(
        title=title[:500],
        description=description[:2000],
        category=category,
    )

    # Try primary provider (OpenAI)
    result = await _call_openai(prompt)
    if result:
        logger.info(
            f"Ticket classified via OpenAI: priority={result['priority']} confidence={result['confidence']:.2f}"
        )
        return result

    # Try fallback (Anthropic)
    if settings.llm_fallback_enabled:
        result = await _call_anthropic(prompt)
        if result:
            logger.info(
                f"Ticket classified via Anthropic: priority={result['priority']} confidence={result['confidence']:.2f}"
            )
            return result

    logger.debug("LLM classification unavailable — no valid API keys configured")
    return None


async def suggest_reply(
    title: str,
    description: str,
    category: str,
    priority: str,
    status: str,
    history: list[dict[str, str]],
) -> str | None:
    """
    Generate a suggested reply for a technician based on ticket context and chat history.

    history: list of {"sender": name, "role": role, "content": message}
    Returns the suggestion text, or None if all providers fail.
    """
    if history:
        history_text = "\n".join(
            f"[{h['role']}] {h['sender']}: {h['content']}" for h in history[-10:]
        )
    else:
        history_text = "(sem mensagens ainda)"

    prompt = _SUGGEST_REPLY_TEMPLATE.format(
        title=title[:500],
        description=description[:1000],
        category=category,
        priority=priority,
        status=status,
        history=history_text,
    )

    async def _parse_suggestion(text: str) -> str | None:
        text = re.sub(r"```(?:json)?", "", text).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'\{"suggestion"\s*:\s*"((?:[^"\\]|\\.)*)"\}', text, re.DOTALL)
            if match:
                return match.group(1).replace("\\n", "\n")
            return None
        suggestion = data.get("suggestion", "")
        return str(suggestion).strip() if suggestion else None

    async def _call_openai_suggest(prompt: str) -> str | None:
        key = settings.openai_api_key
        if not key or key.startswith("CHANGE_ME") or key.startswith("sk-CHANGE"):
            return None
        try:
            async with httpx.AsyncClient(timeout=settings.llm_request_timeout_seconds) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": settings.openai_model,
                        "messages": [
                            {"role": "system", "content": _SUGGEST_REPLY_SYSTEM},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 512,
                        "temperature": 0.7,
                    },
                )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return await _parse_suggestion(content)
        except Exception as exc:
            logger.warning(f"OpenAI suggest_reply failed: {exc}")
            return None

    async def _call_anthropic_suggest(prompt: str) -> str | None:
        key = settings.anthropic_api_key
        if not key or key.startswith("CHANGE_ME") or key.startswith("sk-ant-CHANGE"):
            return None
        try:
            async with httpx.AsyncClient(timeout=settings.llm_request_timeout_seconds) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                    json={
                        "model": settings.anthropic_model,
                        "max_tokens": 512,
                        "system": _SUGGEST_REPLY_SYSTEM,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
            resp.raise_for_status()
            content = resp.json()["content"][0]["text"]
            return await _parse_suggestion(content)
        except Exception as exc:
            logger.warning(f"Anthropic suggest_reply failed: {exc}")
            return None

    result = await _call_openai_suggest(prompt)
    if result:
        logger.info("Reply suggestion generated via OpenAI")
        return result

    if settings.llm_fallback_enabled:
        result = await _call_anthropic_suggest(prompt)
        if result:
            logger.info("Reply suggestion generated via Anthropic")
            return result

    logger.debug("LLM suggest_reply unavailable — no valid API keys configured")
    return None


async def summarize_conversation(
    title: str,
    category: str,
    status: str,
    history: list[dict[str, str]],
) -> str | None:
    """
    Generate a concise summary of the full ticket conversation.

    history: list of {"sender": name, "role": role, "content": message}
    Returns the summary text, or None if all providers fail.
    """
    if not history:
        return None

    history_text = "\n".join(f"[{h['role']}] {h['sender']}: {h['content']}" for h in history)

    prompt = _SUMMARIZE_TEMPLATE.format(
        title=title[:500],
        category=category,
        status=status,
        history=history_text[:6000],
    )

    async def _parse_summary(text: str) -> str | None:
        text = re.sub(r"```(?:json)?", "", text).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'\{"summary"\s*:\s*"((?:[^"\\]|\\.)*)"\}', text, re.DOTALL)
            if match:
                return match.group(1).replace("\\n", "\n")
            return None
        summary = data.get("summary", "")
        return str(summary).strip() if summary else None

    async def _call_openai_summarize(prompt: str) -> str | None:
        key = settings.openai_api_key
        if not key or key.startswith("CHANGE_ME") or key.startswith("sk-CHANGE"):
            return None
        try:
            async with httpx.AsyncClient(timeout=settings.llm_request_timeout_seconds) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": settings.openai_model,
                        "messages": [
                            {"role": "system", "content": _SUMMARIZE_SYSTEM},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 400,
                        "temperature": 0.3,
                    },
                )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return await _parse_summary(content)
        except Exception as exc:
            logger.warning(f"OpenAI summarize_conversation failed: {exc}")
            return None

    async def _call_anthropic_summarize(prompt: str) -> str | None:
        key = settings.anthropic_api_key
        if not key or key.startswith("CHANGE_ME") or key.startswith("sk-ant-CHANGE"):
            return None
        try:
            async with httpx.AsyncClient(timeout=settings.llm_request_timeout_seconds) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                    json={
                        "model": settings.anthropic_model,
                        "max_tokens": 400,
                        "system": _SUMMARIZE_SYSTEM,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
            resp.raise_for_status()
            content = resp.json()["content"][0]["text"]
            return await _parse_summary(content)
        except Exception as exc:
            logger.warning(f"Anthropic summarize_conversation failed: {exc}")
            return None

    result = await _call_openai_summarize(prompt)
    if result:
        logger.info(f"Conversation summarized via OpenAI for ticket: {title[:50]}")
        return result

    if settings.llm_fallback_enabled:
        result = await _call_anthropic_summarize(prompt)
        if result:
            logger.info(f"Conversation summarized via Anthropic for ticket: {title[:50]}")
            return result

    logger.debug("LLM summarize_conversation unavailable — no valid API keys configured")
    return None
