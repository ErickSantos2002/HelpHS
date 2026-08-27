"""O id que amarra as linhas de log de uma mesma requisição.

Antes disto não havia nada: nem `request_id`, nem `ContextVar`, nem middleware
que não fosse o CORS. Reconstruir o percurso de uma chamada nos logs dependia de
adivinhar pela ordem e pelo relógio — e em produção, com JSON serializado numa
stream compartilhada, isso não é adivinhação viável.

Por que `ContextVar` e não um atributo do app ou uma variável de módulo: o
servidor atende requisições concorrentes o tempo todo, e cada uma roda na sua
própria task. Uma variável compartilhada faria duas chamadas simultâneas
enxergarem o id da última que escreveu — silenciosamente, e justo no caso normal.
"""

import re
import uuid
from contextvars import ContextVar

# Vazio, e não `None`, para o log formatar sem tratar caso especial: linhas de
# boot, do worker de auto-close e de script avulso simplesmente saem com o campo
# em branco.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# Letras, dígitos, hífen, sublinhado e ponto cobrem UUID, trace id de proxy e os
# formatos usuais. Nada mais entra.
_ACEITO = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

CABECALHO = "X-Request-ID"


def normalizar(bruto: str | None) -> str:
    """Adota o id de fora se ele for são; senão, gera um.

    Aceitar o id de quem chamou é o que permite amarrar o log daqui ao do lado
    de fora sem combinar formato nenhum. Mas ele entra em **toda** linha de log
    da requisição, então ecoar entrada arbitrária ali é injeção de log: uma
    quebra de linha forja registros inteiros, e um valor gigante enche o
    agregador. Conferir é o preço da conveniência.
    """
    if bruto and _ACEITO.match(bruto):
        return bruto
    return uuid.uuid4().hex


def id_atual() -> str:
    """O id da requisição em curso, ou string vazia fora de uma."""
    return request_id_var.get()
