"""Middleware que dá um id a cada requisição e o devolve no cabeçalho.

É **ASGI puro**, não `BaseHTTPMiddleware`. O `BaseHTTPMiddleware` do Starlette
embrulha a requisição num par de tasks para adaptar a interface, e isso já
custou caro em outros projetos: interfere em streaming, em `BackgroundTasks` e
na propagação de exceções — justamente o que este projeto usa nos e-mails e no
que os três exception handlers tratam. ASGI puro não embrulha nada: lê o escopo,
chama o app, observa as mensagens de saída.

Ele é o middleware mais externo (o último registrado no `add_middleware` fica
por fora), então o id existe antes de qualquer outra camada — inclusive antes do
CORS — e o cabeçalho é carimbado por último, depois de a resposta estar pronta.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from app.core.contexto import CABECALHO, normalizar, request_id_var

_CABECALHO_BYTES = CABECALHO.encode("latin-1")


def _le_cabecalho(scope: dict[str, Any]) -> str | None:
    alvo = _CABECALHO_BYTES.lower()
    for nome, valor in scope.get("headers", []):
        if nome.lower() == alvo:
            try:
                return valor.decode("latin-1")
            except UnicodeDecodeError:
                return None
    return None


class CorrelacaoMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        # `lifespan` passa direto: não é requisição e não tem id.
        if scope.get("type") not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        rid = normalizar(_le_cabecalho(scope))
        token = request_id_var.set(rid)

        async def _envia(mensagem: dict[str, Any]) -> None:
            # Só a resposta HTTP tem onde carimbar. O WebSocket ganha o id no
            # contexto — que é o que faz as linhas de log dele se amarrarem —,
            # mas o handshake não leva cabeçalho nosso.
            if mensagem.get("type") == "http.response.start":
                cabecalhos = list(mensagem.get("headers", []))
                cabecalhos.append((_CABECALHO_BYTES, rid.encode("latin-1")))
                mensagem = {**mensagem, "headers": cabecalhos}
            await send(mensagem)

        try:
            await self.app(scope, receive, _envia)
        finally:
            # Cada requisição roda na própria task, então o vazamento seria
            # improvável — mas restaurar custa uma linha e tira a dúvida.
            request_id_var.reset(token)
