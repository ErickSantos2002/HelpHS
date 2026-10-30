"""
Centralized exception handling and standardized error responses.

All validation errors from FastAPI/Pydantic are converted to:
    { "detail": [{ "field": "...", "message": "..." }] }

HTTPExceptions keep their existing:
    { "detail": "..." }
"""

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# ── pt-BR translation map for Pydantic error types ────────────

_PYDANTIC_MSG: dict[str, str] = {
    "missing": "Campo obrigatório",
    "string_too_short": "Deve ter no mínimo {min_length} caractere(s)",
    "string_too_long": "Deve ter no máximo {max_length} caractere(s)",
    "string_type": "Deve ser um texto",
    "int_type": "Deve ser um número inteiro",
    "float_type": "Deve ser um número",
    "bool_type": "Deve ser verdadeiro ou falso",
    "enum": "Valor inválido. Opções: {expected}",
    "uuid_type": "Deve ser um UUID válido",
    "uuid_parsing": "UUID inválido",
    "datetime_type": "Deve ser uma data/hora válida",
    "datetime_parsing": "Formato de data/hora inválido",
    # Datas puras, como `start_date`/`end_date` dos relatórios (F1-B-03a): sem
    # estas entradas, "2026-13-01" voltava em inglês.
    "date_type": "Data inválida. Use o formato AAAA-MM-DD",
    "date_parsing": "Data inválida. Use o formato AAAA-MM-DD",
    "date_from_datetime_parsing": "Data inválida. Use o formato AAAA-MM-DD",
    "date_from_datetime_inexact": "Informe só a data, sem hora (AAAA-MM-DD)",
    "url_type": "Deve ser uma URL válida",
    "url_parsing": "URL inválida",
    "value_error.email": "E-mail inválido",
    "email": "E-mail inválido",
    "too_short": "Deve ter no mínimo {min_length} item(ns)",
    "too_long": "Deve ter no máximo {max_length} item(ns)",
    "json_invalid": "JSON inválido",
    "literal_error": "Valor inválido. Esperado: {expected}",
    "int_from_float": "Deve ser um número inteiro (sem casas decimais)",
    "greater_than": "Deve ser maior que {gt}",
    "greater_than_equal": "Deve ser maior ou igual a {ge}",
    "less_than": "Deve ser menor que {lt}",
    "less_than_equal": "Deve ser menor ou igual a {le}",
    "string_pattern_mismatch": "Formato inválido",
}


_PREFIXO_DO_PYDANTIC = "Value error, "


def _mensagem_do_value_error(raw_msg: str, ctx: dict) -> str:
    """O texto do `ValueError` de um validador, sem o que o pydantic acrescenta.

    O pydantic v2 monta `msg = "Value error, <texto>"` e guarda a exceção
    original em `ctx["error"]` — o texto dela é exatamente o que o validador
    escreveu, em português, e vale mais que cortar a string (F1-B-02). Sem a
    exceção, corta só o prefixo exato do começo, uma vez: um texto legítimo
    que contenha essas palavras mais adiante fica inteiro.

    O `EmailStr` também sai como `value_error`, mas com um motivo em inglês em
    `ctx["reason"]` e sem exceção: vira "E-mail inválido". Outro `value_error`
    com `reason` não é tratado como e-mail.
    """
    erro = ctx.get("error")
    if isinstance(erro, Exception) and str(erro).strip():
        return str(erro).strip()
    if "reason" in ctx and raw_msg.startswith("value is not a valid email address"):
        return "E-mail inválido"
    if raw_msg.startswith(_PREFIXO_DO_PYDANTIC):
        return raw_msg[len(_PREFIXO_DO_PYDANTIC) :].strip() or "Valor inválido"
    return raw_msg or "Valor inválido"


def _translate_error(error: dict) -> dict:
    """Convert a single Pydantic error dict into a pt-BR friendly dict."""
    error_type: str = error.get("type", "")
    ctx: dict = error.get("ctx", {}) or {}
    raw_msg: str = error.get("msg", "")

    # Field path: ["body", "email"] → "email"
    loc = error.get("loc", [])
    field_parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    field = ".".join(field_parts) if field_parts else "campo"

    # Translate message
    if error_type == "value_error":
        return {"field": field, "message": _mensagem_do_value_error(raw_msg, ctx)}

    template = _PYDANTIC_MSG.get(error_type)
    if template:
        try:
            message = template.format(**ctx, msg=raw_msg)
        except KeyError:
            message = raw_msg or error_type
    else:
        message = raw_msg or error_type

    return {"field": field, "message": message}


# ── Exception handlers ────────────────────────────────────────


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [_translate_error(e) for e in exc.errors()]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": errors},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


# ── Custom app exceptions ─────────────────────────────────────


class AppException(HTTPException):
    """Base class for domain-level exceptions with a Portuguese detail message."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(status_code=status_code, detail=detail)


class NotFoundException(AppException):
    def __init__(self, entity: str = "Recurso") -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, f"{entity} não encontrado(a)")


class ConflictException(AppException):
    def __init__(self, detail: str = "Conflito com um recurso existente") -> None:
        super().__init__(status.HTTP_409_CONFLICT, detail)


class ForbiddenException(AppException):
    def __init__(self, detail: str = "Acesso negado") -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, detail)


class UnauthorizedException(AppException):
    def __init__(self, detail: str = "Não autenticado") -> None:
        super().__init__(
            status.HTTP_401_UNAUTHORIZED,
            detail,
        )


# ── Aceite da Política pendente (HTTP 428) ────────────────────

# O contrato que o front lê. O texto do `detail` pode mudar; o `code`, não.
CODIGO_ACEITE_POLITICA_PENDENTE = "aceite_politica_pendente"


class AceitePoliticaPendenteError(Exception):
    """A pessoa está autenticada, mas falta aceitar a revisão vigente da Política.

    NÃO é `HTTPException` de propósito: o tratador genérico acima devolve só
    `{"detail": ...}`, e um `detail` em dicionário sairia aninhado. Este erro
    tem corpo próprio, com `code` no nível de cima, e um tratador só dele.

    428 porque nenhum outro caminho do projeto usa: 401 dispararia o refresh do
    front (e mudaria o sentido de "sessão inválida"), 403 já significa conta
    inativa e falta de permissão, 409 é conflito de negócio.
    """

    def __init__(self, revisao_politica_vigente: str | None) -> None:
        super().__init__(CODIGO_ACEITE_POLITICA_PENDENTE)
        self.revisao_politica_vigente = revisao_politica_vigente


async def aceite_politica_pendente_handler(
    request: Request, exc: AceitePoliticaPendenteError
) -> JSONResponse:
    # Sem a revisão dos Termos: este erro é só da Política, e os Termos não
    # bloqueiam o backend nesta fase.
    return JSONResponse(
        status_code=status.HTTP_428_PRECONDITION_REQUIRED,
        content={
            "detail": "Para continuar, aceite a revisão vigente da Política de Privacidade.",
            "code": CODIGO_ACEITE_POLITICA_PENDENTE,
            "revisao_politica_vigente": exc.revisao_politica_vigente,
        },
    )
