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
    "value_error": "{msg}",
    "string_type": "Deve ser um texto",
    "int_type": "Deve ser um número inteiro",
    "float_type": "Deve ser um número",
    "bool_type": "Deve ser verdadeiro ou falso",
    "enum": "Valor inválido. Opções: {expected}",
    "uuid_type": "Deve ser um UUID válido",
    "uuid_parsing": "UUID inválido",
    "datetime_type": "Deve ser uma data/hora válida",
    "datetime_parsing": "Formato de data/hora inválido",
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

_FIELD_NAMES: dict[str, str] = {
    "email": "e-mail",
    "password": "senha",
    "name": "nome",
    "phone": "telefone",
    "department": "departamento",
    "role": "perfil",
    "status": "status",
    "refresh_token": "token de atualização",
    "access_token": "token de acesso",
    "serial_number": "número de série",
    "product_id": "produto",
    "is_active": "ativo",
    "lgpd_consent": "consentimento LGPD",
    "avatar_url": "avatar",
    "version": "versão",
    "description": "descrição",
    "model": "modelo",
}


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
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
