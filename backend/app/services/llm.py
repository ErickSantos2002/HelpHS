"""
LLM Service — DeepSeek, provedor único.

Usage
-----
result = await classify_ticket(title, description, category)
if result:
    priority, confidence, summary = result["priority"], result["confidence"], result["summary"]

All functions return None on failure (missing key, timeout, parse error),
so callers should treat None as "classification unavailable".

Desenho
-------
Havia oito cópias da mesma requisição HTTP: quatro funções públicas × dois
provedores, com a URL escrita à mão em cada uma. Com um provedor só, quatro
blocos viraram código morto e os outros quatro, a mesma função repetida.

Sobrou UM transporte — `_chamar_deepseek` — e o parsing ficou de fora dele, de
propósito: as quatro não esperam a mesma coisa. `classify_ticket` quer JSON
estruturado (prioridade, confiança, resumo) e recusa a resposta se o contrato
não vier; as outras três querem um campo de texto, cada uma com o SEU nome
(`suggestion`, `summary`, `improved`). Colapsar isso junto com a chamada
quebraria uma das quatro.

⚠️ O endpoint e o nome do modelo NÃO foram conferidos contra a documentação
oficial da DeepSeek. Por isso `DEEPSEEK_BASE_URL` e `DEEPSEEK_MODEL` são
configuração com padrão, e não constante: o ajuste, quando o serviço real
disser outra coisa, é no painel.
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

_IMPROVE_MESSAGE_SYSTEM = (
    "Você é um assistente de escrita para técnicos de suporte em Saúde & Segurança do Trabalho. "
    "Seu papel é melhorar a clareza, gramática e profissionalismo de rascunhos de mensagens, "
    "mantendo o tom e a intenção original. Responda APENAS com JSON válido, sem markdown."
)

_IMPROVE_MESSAGE_TEMPLATE = """Ticket de suporte:
Título: {title}
Descrição: {description}

Rascunho da mensagem do técnico:
{draft}

Melhore o rascunho acima: corrija gramática, pontuação e ortografia, torne o texto mais claro e \
profissional, mas preserve o significado e o tom original. Escreva em português brasileiro.

Responda com este JSON exato (sem markdown):
{{
  "improved": "texto melhorado"
}}"""

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


# ── Transporte ────────────────────────────────────────────────


def _sem_chave_utilizavel() -> bool:
    """Chave ausente ou placeholder do `.env.example` contam como ausente."""
    key = settings.deepseek_api_key
    return not key or key.startswith("CHANGE_ME") or key.startswith("sk-CHANGE")


async def _chamar_deepseek(
    *,
    system: str,
    prompt: str,
    max_tokens: int,
    operacao: str,
) -> str | None:
    """Faz a chamada e devolve o TEXTO cru da resposta. Não interpreta nada.

    Sem chave, devolve None em SILÊNCIO — sem exceção e sem log de aviso. É o
    estado de produção com a IA desligada, e não é anormalidade que mereça
    poluir o log a cada chamado aberto. Log de aviso fica só para falha de
    verdade: rede, timeout, HTTP de erro.
    """
    if not settings.llm_enabled or _sem_chave_utilizavel():
        return None

    url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=settings.llm_request_timeout_seconds) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                json={
                    "model": settings.deepseek_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": settings.llm_temperature,
                },
            )
        resp.raise_for_status()
        return str(resp.json()["choices"][0]["message"]["content"])
    except Exception as exc:
        logger.warning(f"DeepSeek {operacao} falhou: {exc}")
        return None


# ── Leitura da resposta ───────────────────────────────────────


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


def _parse_campo_texto(text: str, campo: str) -> str | None:
    """Lê UM campo de texto do JSON da resposta.

    O `campo` é o que distingue as três funções de texto entre si — quem chama
    diz qual quer. Sem isso, `suggest_reply` aceitaria o resumo de outra
    chamada como se fosse a sugestão.
    """
    text = re.sub(r"```(?:json)?", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        padrao = rf'\{{"{campo}"\s*:\s*"((?:[^"\\]|\\.)*)"\}}'
        match = re.search(padrao, text, re.DOTALL)
        if match:
            return match.group(1).replace("\\n", "\n")
        return None
    valor = data.get(campo, "")
    return str(valor).strip() if valor else None


# ── Public API ────────────────────────────────────────────────
#
# O `llm_enabled` é conferido na entrada de cada função pública, e não só no
# transporte: com a IA desligada nem o prompt chega a ser montado, e o teste
# prende isso olhando a rede — nenhum `httpx.AsyncClient` é sequer construído.


async def classify_ticket(
    title: str,
    description: str,
    category: str,
) -> dict[str, Any] | None:
    """
    Classify a ticket using DeepSeek.

    Returns dict with keys: priority, confidence, summary
    Returns None if the call fails or the key is not configured.
    """
    if not settings.llm_enabled:
        return None

    prompt = _CLASSIFICATION_TEMPLATE.format(
        title=title[:500],
        description=description[:2000],
        category=category,
    )

    conteudo = await _chamar_deepseek(
        system=_CLASSIFICATION_SYSTEM,
        prompt=prompt,
        max_tokens=256,
        operacao="classify_ticket",
    )
    if conteudo is None:
        logger.debug("LLM classification unavailable — no valid API key configured")
        return None

    result = _parse_json_response(conteudo)
    if result is None:
        logger.debug("LLM classification discarded — response did not match the contract")
        return None

    logger.info(
        f"Ticket classified via DeepSeek: "
        f"priority={result['priority']} confidence={result['confidence']:.2f}"
    )
    return result


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
    Returns the suggestion text, or None if the call fails.
    """
    if not settings.llm_enabled:
        return None

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

    conteudo = await _chamar_deepseek(
        system=_SUGGEST_REPLY_SYSTEM,
        prompt=prompt,
        max_tokens=512,
        operacao="suggest_reply",
    )
    if conteudo is None:
        logger.debug("LLM suggest_reply unavailable — no valid API key configured")
        return None

    sugestao = _parse_campo_texto(conteudo, "suggestion")
    if sugestao is None:
        logger.debug("LLM suggest_reply discarded — response had no suggestion field")
        return None

    logger.info("Reply suggestion generated via DeepSeek")
    return sugestao


# Orçamento do histórico que vai no prompt do resumo, em caracteres.
LIMITE_HISTORICO_RESUMO = 6000

_AVISO_DE_CORTE = "[... mensagens anteriores omitidas por tamanho ...]"


def montar_historico(history: list[dict[str, str]]) -> tuple[str, bool]:
    """Monta o histórico do resumo guardando as mensagens MAIS RECENTES.

    Devolve o texto e se houve corte.

    Antes isto era `"\n".join(...)[:6000]`: juntava tudo em ordem cronológica e
    guardava os 6000 **primeiros** caracteres. Numa conversa longa, o resumo
    perdia justamente o fim — e quem o abre está tentando descobrir onde o
    chamado está, não como ele começou. O enunciado do problema não depende
    disso: título, categoria e status vão para o prompt por fora.

    O corte é por MENSAGEM, não por caractere. Fatiar a string produz linha
    truncada no meio de uma frase — o modelo recebe "o erro é TIMEO" e trata
    como conteúdo íntegro.
    """
    linhas = [f"[{h['role']}] {h['sender']}: {h['content']}" for h in history]

    escolhidas: list[str] = []
    gasto = 0
    for linha in reversed(linhas):
        if escolhidas and gasto + len(linha) + 1 > LIMITE_HISTORICO_RESUMO:
            break
        escolhidas.append(linha)
        gasto += len(linha) + 1

    escolhidas.reverse()
    cortou = len(escolhidas) < len(linhas)

    # Uma única fala maior que o orçamento inteiro: aí não há como não cortar no
    # meio, e o corte fica no COMEÇO dela — o fim de uma mensagem costuma ser
    # onde está a conclusão.
    if len(escolhidas) == 1 and gasto > LIMITE_HISTORICO_RESUMO:
        escolhidas[0] = escolhidas[0][-LIMITE_HISTORICO_RESUMO:]
        cortou = True

    if cortou:
        escolhidas.insert(0, _AVISO_DE_CORTE)

    return "\n".join(escolhidas), cortou


async def summarize_conversation(
    title: str,
    category: str,
    status: str,
    history: list[dict[str, str]],
) -> str | None:
    """
    Generate a concise summary of the full ticket conversation.

    history: list of {"sender": name, "role": role, "content": message}
    Returns the summary text, or None if the call fails.
    """
    if not settings.llm_enabled:
        return None

    if not history:
        return None

    history_text, _cortou = montar_historico(history)

    prompt = _SUMMARIZE_TEMPLATE.format(
        title=title[:500],
        category=category,
        status=status,
        history=history_text,
    )

    conteudo = await _chamar_deepseek(
        system=_SUMMARIZE_SYSTEM,
        prompt=prompt,
        max_tokens=400,
        operacao="summarize_conversation",
    )
    if conteudo is None:
        logger.debug("LLM summarize_conversation unavailable — no valid API key configured")
        return None

    resumo = _parse_campo_texto(conteudo, "summary")
    if resumo is None:
        logger.debug("LLM summarize_conversation discarded — response had no summary field")
        return None

    logger.info(f"Conversation summarized via DeepSeek for ticket: {title[:50]}")
    return resumo


async def improve_message(draft: str, title: str, description: str) -> str | None:
    """
    Improve a technician's draft message: fix grammar, clarity and professionalism
    while preserving original intent.

    Returns the improved text, or None if the call fails.
    """
    if not settings.llm_enabled:
        return None

    prompt = _IMPROVE_MESSAGE_TEMPLATE.format(
        title=title[:500],
        description=description[:500],
        draft=draft[:2000],
    )

    conteudo = await _chamar_deepseek(
        system=_IMPROVE_MESSAGE_SYSTEM,
        prompt=prompt,
        max_tokens=512,
        operacao="improve_message",
    )
    if conteudo is None:
        logger.debug("LLM improve_message unavailable — no valid API key configured")
        return None

    melhorado = _parse_campo_texto(conteudo, "improved")
    if melhorado is None:
        logger.debug("LLM improve_message discarded — response had no improved field")
        return None

    logger.info("Message improved via DeepSeek")
    return melhorado
