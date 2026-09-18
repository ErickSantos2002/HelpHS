"""
Rate limiting da API (slowapi).

Fecha o brute-force de senha e a enumeração de conta em escala nos endpoints de
autenticação. Antes disto os limites existiam só como configuração
(RATE_LIMIT_*), sem nada aplicando — config que finge proteger.

Decisões:
  - Storage em Redis em produção, para o limite valer entre os múltiplos
    workers do uvicorn (hoje o start.sh sobe 1, mas o limite não pode depender
    disso). Em teste usa memória, sem Redis.
  - Desligado por padrão sob APP_ENV=testing, senão as várias chamadas de
    /auth/login da suíte estourariam o limite e falhariam. O teste dedicado
    de rate limit liga explicitamente.
"""

from fastapi import Request
from jose import JWTError
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.core.security import decode_token

settings = get_settings()

_is_testing = settings.is_testing

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://" if _is_testing else settings.redis_url,
    enabled=not _is_testing,
    # O balde é a FUNÇÃO, não a URL. O padrão do slowapi é `"url"`, e com ele um
    # endpoint que leva o dado no caminho ganha um balde por valor: `/cep/01001000`
    # e `/cep/01001001` contam separado, e quem quisesse esgotar o provedor
    # externo só precisaria variar o CEP — que é exatamente o abuso que o limite
    # existe para conter.
    #
    # Para os limites antigos isto não muda nada: `/auth/login`, `/auth/register`
    # e os demais têm caminho constante, então URL e função davam a mesma chave.
    key_style="endpoint",
)


def chave_por_usuario(request: Request) -> str:
    """Chave de rate limit pelo USUÁRIO, e não pelo IP.

    Para endpoint autenticado, o IP é a chave errada em duas direções: uma
    empresa inteira atrás de um NAT divide o mesmo balde e um usuário sozinho
    derruba os colegas; e quem quer abusar troca de IP mais fácil do que troca
    de conta.

    O `sub` sai do token do próprio cabeçalho. Isso é seguro **porque o
    decorador do slowapi roda depois das dependências da rota**: quando esta
    função é chamada, o `get_current_user` já validou assinatura, tipo,
    blacklist e status da conta. Aqui o `decode_token` só relê o que já passou.

    Sem `Authorization` utilizável, cai para o IP. Nas rotas onde isto é usado
    esse caminho não acontece — elas exigem sessão —, mas uma chave vazia
    juntaria todo mundo num balde só, e o padrão precisa ser o restritivo.
    """
    cabecalho = request.headers.get("authorization", "")
    if cabecalho.lower().startswith("bearer "):
        try:
            sub = decode_token(cabecalho[7:]).get("sub")
        except JWTError:
            sub = None
        if sub:
            return f"usuario:{sub}"
    return get_remote_address(request)
