"""O estado que existe entre a senha aceita e o código conferido.

Até aqui o sistema não tinha nenhum estado de sessão parcial: as quatro chaves
Redis existentes são por token ou globais, nenhuma é por tentativa de login.
Esta é a primeira.

O desafio é um token **opaco**, não um JWT. Um sexto tipo de JWT compartilharia
a chave RS256 e o `iss` dos outros cinco, e a separação entre eles passaria a
depender de todo consumidor futuro de `decode_token` lembrar de conferir o
claim `type`. Um token opaco não tem como ser confundido com um access token
porque não é decodificável em lugar nenhum — ele só significa alguma coisa
enquanto existir a entrada no Redis.

A chave guarda o **sha256** do token, não o token. Aqui a chave é a credencial:
quem lesse as chaves de um `KEYS` — num Redis que também hospeda cache de
dashboard e o lock do auto-close — teria material que pula a senha.

Redis fora do ar vira 503, nunca "pode entrar". Um segundo fator que se desliga
sozinho quando uma dependência cai não é um segundo fator.
"""

import hashlib
import secrets
import uuid
from collections.abc import Awaitable
from typing import Any, cast

from app.core.redis import get_redis


async def _aguardar(resultado: Any) -> Any:
    """Contorna a tipagem dos comandos de hash do redis-py.

    A mesma classe serve o cliente síncrono e o assíncrono, então os stubs
    declaram `Awaitable[X] | X` e o mypy recusa o `await` direto. Os comandos de
    string não têm esse problema, e é por isso que o resto do projeto nunca
    precisou disto — este é o primeiro módulo a usar hash.
    """
    return await cast(Awaitable[Any], resultado)


_PENDENTE = "mfa:pending:"
_PASSO_USADO = "mfa:used:"

# Cinco minutos: sobra para abrir o aplicativo e digitar, e um token vazado
# vira lixo depressa.
TTL_DESAFIO = 300

# Cobre com folga os ~90 s em que um código continua matematicamente válido.
_TTL_PASSO = 120

_MAX_TENTATIVAS = 5


class DesafioIndisponivelError(RuntimeError):
    """O Redis não respondeu. Quem chama devolve 503, nunca sessão."""


class TentativasEsgotadasError(RuntimeError):
    """Erros demais no mesmo desafio; ele foi queimado."""


def _chave(token: str) -> str:
    return _PENDENTE + hashlib.sha256(token.encode()).hexdigest()


def _chave_passo(user_id: uuid.UUID, passo: int) -> str:
    return f"{_PASSO_USADO}{user_id}:{passo}"


async def abrir(user_id: uuid.UUID) -> str:
    """Cria o desafio e devolve o token que o representa.

    O token é gerado aqui e nunca deriva de nada do usuário — não carrega id,
    e-mail nem papel. Quem o recebe não aprende nada sobre a conta.
    """
    token = secrets.token_urlsafe(32)
    try:
        redis = await get_redis()
        chave = _chave(token)
        await _aguardar(redis.hset(chave, mapping={"user_id": str(user_id), "erros": "0"}))
        await redis.expire(chave, TTL_DESAFIO)
    except Exception as exc:
        raise DesafioIndisponivelError(str(exc)) from exc
    return token


async def dono(token: str) -> uuid.UUID | None:
    """De quem é este desafio, sem consumi-lo. `None` se não existe mais."""
    try:
        dados = await _aguardar((await get_redis()).hgetall(_chave(token)))
    except Exception as exc:
        raise DesafioIndisponivelError(str(exc)) from exc

    if not dados or "user_id" not in dados:
        return None
    try:
        return uuid.UUID(dados["user_id"])
    except ValueError:
        return None


async def registrar_erro(token: str) -> None:
    """Conta mais um código errado e queima o desafio ao estourar o limite."""
    try:
        redis = await get_redis()
        chave = _chave(token)
        erros = await _aguardar(redis.hincrby(chave, "erros", 1))
        if erros >= _MAX_TENTATIVAS:
            await redis.delete(chave)
            raise TentativasEsgotadasError()
    except TentativasEsgotadasError:
        raise
    except Exception as exc:
        raise DesafioIndisponivelError(str(exc)) from exc


async def consumir(token: str) -> bool:
    """Reivindica o desafio. `True` para quem chegou primeiro, e só para ele.

    O `DEL` é a reivindicação: ele devolve 1 uma única vez, mesmo que duas
    requisições cheguem juntas com o mesmo token. É o uso único, em uma linha,
    sem transação nem lock.
    """
    try:
        return bool(await (await get_redis()).delete(_chave(token)))
    except Exception as exc:
        raise DesafioIndisponivelError(str(exc)) from exc


async def passo_ja_usado(user_id: uuid.UUID, passo: int) -> bool:
    try:
        return bool(await (await get_redis()).exists(_chave_passo(user_id, passo)))
    except Exception as exc:
        raise DesafioIndisponivelError(str(exc)) from exc


async def marcar_passo(user_id: uuid.UUID, passo: int) -> None:
    """Marca o passo como gasto — **depois** de o código ter conferido.

    A ordem importa: marcar antes de conferir deixaria alguém queimar os
    códigos legítimos da vítima só chutando, já que o passo é previsível e o
    chute não precisa acertar para gravar a marca.
    """
    try:
        await (await get_redis()).setex(_chave_passo(user_id, passo), _TTL_PASSO, "1")
    except Exception as exc:
        raise DesafioIndisponivelError(str(exc)) from exc
