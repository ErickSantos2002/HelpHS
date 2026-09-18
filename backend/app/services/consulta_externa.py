"""
Consulta de CNPJ e CEP em provedores públicos, com cache.

O risco que este módulo endereça não é derrubar o HelpHS — é o caminho
`usuário → HelpHS → API externa`: sem teto e sem cache, um usuário autenticado
transforma a nossa API num proxy ilimitado para a `brasilapi` e a `viacep`, e
quem leva o bloqueio é o **IP público do servidor**. Aí a funcionalidade morre
para todo mundo, e a causa não aparece em log nenhum nosso.

Por isso a ordem das defesas aqui é: **cache primeiro, teto depois**. O teto
limita cada pessoa; o cache é o que de fato reduz o número de chamadas que saem
daqui, porque CEP e CNPJ são consultados repetidamente com os mesmos valores —
os colegas de uma empresa moram todos no mesmo CEP.

O cache usa o Redis que já existe (blacklist de JWT, rate limit, locks,
pub/sub do chat). Não é infraestrutura nova.

**Redis fora do ar não derruba a consulta.** Falha de cache é ignorada e a
chamada segue para o provedor: cache é otimização, e otimização que vira ponto
de falha piora o sistema que deveria melhorar.
"""

import json
import re
from typing import Any

import httpx
from loguru import logger

from app.core.redis import get_redis

# ── TTLs ──────────────────────────────────────────────────────
#
# Assimétricos de propósito. Endereço de CEP é praticamente imutável; razão
# social e nome fantasia de um CNPJ mudam de vez em quando. O TTL negativo é
# curto porque "não encontrado" pode ser um cadastro que ainda vai existir —
# e porque sem ele alguém varreria CEPs inválidos passando por fora do cache.
_TTL_CEP = 30 * 24 * 3600
_TTL_CNPJ = 7 * 24 * 3600
_TTL_NAO_ENCONTRADO = 3600

_PREFIXO = "consulta"
_MARCA_NAO_ENCONTRADO = "__nao_encontrado__"

_TIMEOUT = httpx.Timeout(10.0)


class ConsultaNaoEncontradaError(Exception):
    """O provedor respondeu, e o documento não existe."""


class ConsultaIndisponivelError(Exception):
    """O provedor não respondeu: rede, timeout ou erro dele.

    Separada da anterior de propósito. "CEP não existe" é resposta; "o provedor
    caiu" é indisponibilidade nossa, e o usuário merece saber a diferença —
    num caso ele corrige o que digitou, no outro ele tenta de novo mais tarde.
    """


async def _le_cache(chave: str) -> dict[str, Any] | None:
    try:
        redis = await get_redis()
        bruto = await redis.get(chave)
    except Exception as exc:  # noqa: BLE001 — cache indisponível não é erro do usuário
        logger.debug(f"Cache de consulta externa indisponível na leitura: {exc}")
        return None

    if bruto is None:
        return None
    if bruto == _MARCA_NAO_ENCONTRADO:
        raise ConsultaNaoEncontradaError
    try:
        return dict(json.loads(bruto))
    except (ValueError, TypeError):
        return None


async def _grava_cache(chave: str, valor: dict[str, Any] | None, ttl: int) -> None:
    try:
        redis = await get_redis()
        conteudo = _MARCA_NAO_ENCONTRADO if valor is None else json.dumps(valor)
        await redis.setex(chave, ttl, conteudo)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"Cache de consulta externa indisponível na escrita: {exc}")


async def _busca(url: str) -> httpx.Response:
    """Faz a chamada externa. Qualquer falha de rede vira `ConsultaIndisponivelError`.

    Sem isto, um `ConnectError` ou `ReadTimeout` do provedor subia como exceção
    não tratada e o nosso usuário recebia **500** — dizendo que o defeito é
    nosso quando o provedor é que está fora.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            return await client.get(url)
    except httpx.HTTPError as exc:
        logger.warning(f"Consulta externa falhou ({type(exc).__name__}): {url}")
        raise ConsultaIndisponivelError from exc


async def consulta_cnpj(cnpj: str) -> dict[str, Any]:
    """Devolve os dados do CNPJ, do cache ou da `brasilapi`."""
    limpo = re.sub(r"\D", "", cnpj)
    chave = f"{_PREFIXO}:cnpj:{limpo}"

    do_cache = await _le_cache(chave)
    if do_cache is not None:
        return do_cache

    resp = await _busca(f"https://brasilapi.com.br/api/cnpj/v1/{limpo}")
    if resp.status_code != 200:
        await _grava_cache(chave, None, _TTL_NAO_ENCONTRADO)
        raise ConsultaNaoEncontradaError

    dados = resp.json()
    resultado = {
        "cnpj": limpo,
        "company_name": dados.get("razao_social") or "",
        "trade_name": dados.get("nome_fantasia") or "",
        "city": dados.get("municipio") or "",
        "state": dados.get("uf") or "",
    }
    await _grava_cache(chave, resultado, _TTL_CNPJ)
    return resultado


async def consulta_cep(cep: str) -> dict[str, Any]:
    """Devolve o endereço do CEP, do cache ou da `viacep`."""
    limpo = re.sub(r"\D", "", cep)
    chave = f"{_PREFIXO}:cep:{limpo}"

    do_cache = await _le_cache(chave)
    if do_cache is not None:
        return do_cache

    resp = await _busca(f"https://viacep.com.br/ws/{limpo}/json/")
    if resp.status_code != 200:
        await _grava_cache(chave, None, _TTL_NAO_ENCONTRADO)
        raise ConsultaNaoEncontradaError

    dados = resp.json()
    # A viacep responde 200 com `{"erro": true}` para CEP inexistente, em vez
    # de 404. Sem esta checagem o "não encontrado" entraria no cache como
    # resultado válido e ficaria trinta dias.
    if dados.get("erro"):
        await _grava_cache(chave, None, _TTL_NAO_ENCONTRADO)
        raise ConsultaNaoEncontradaError

    resultado = {
        "cep": f"{limpo[:5]}-{limpo[5:]}",
        "address": dados.get("logradouro") or "",
        "neighborhood": dados.get("bairro") or "",
        "city": dados.get("localidade") or "",
        "state": dados.get("uf") or "",
    }
    await _grava_cache(chave, resultado, _TTL_CEP)
    return resultado
