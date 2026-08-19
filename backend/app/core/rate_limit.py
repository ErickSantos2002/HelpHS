"""
Rate limiting da API (slowapi).

Fecha o brute-force de senha e a enumeração de conta em escala nos endpoints de
autenticação. Antes disto os limites existiam só como configuração
(RATE_LIMIT_*), sem nada aplicando — config que finge proteger.

Decisões:
  - Storage em Redis em produção, para o limite valer entre os múltiplos
    workers do uvicorn (start.sh sobe 2). Em teste usa memória, sem Redis.
  - Desligado por padrão sob APP_ENV=testing, senão as várias chamadas de
    /auth/login da suíte estourariam o limite e falhariam. O teste dedicado
    de rate limit liga explicitamente.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

settings = get_settings()

_is_testing = settings.is_testing

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://" if _is_testing else settings.redis_url,
    enabled=not _is_testing,
)
