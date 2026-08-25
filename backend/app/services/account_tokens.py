"""
Tokens dos links enviados por e-mail: confirmação de cadastro e redefinição
de senha.

São JWT assinados com a mesma chave da aplicação, então não precisam de tabela
nem de limpeza periódica — vencem sozinhos.

Os dois são de uso único, pelo mesmo mecanismo: carregam o estado que a ação
vai mudar, e a validação compara com o estado atual do usuário. O de senha
carrega a impressão digital da senha vigente; o de confirmação, se a conta já
estava confirmada. Assim que a ação acontece, o estado muda e o link para de
funcionar — inclusive o próprio link que acabou de ser usado.
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from app.core.config import Settings

_VERIFY_TYPE = "email_verify"
_RESET_TYPE = "password_reset"


class InvalidTokenError(Exception):
    """Token ausente, vencido, adulterado ou de outro propósito."""


def _password_fingerprint(password_hash: str) -> str:
    """Resumo curto da senha atual — não expõe o hash dentro do token."""
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def _encode(payload: dict, settings: Settings) -> str:
    return jwt.encode(payload, settings.get_private_key(), algorithm=settings.jwt_algorithm)


def _decode(token: str, expected_type: str, settings: Settings) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.get_public_key(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
        )
    except JWTError as exc:
        raise InvalidTokenError("Link inválido ou expirado.") from exc

    if payload.get("type") != expected_type:
        raise InvalidTokenError("Este link não serve para esta ação.")
    return payload


def _subject(payload: dict) -> uuid.UUID:
    try:
        return uuid.UUID(str(payload.get("sub")))
    except (ValueError, TypeError) as exc:
        raise InvalidTokenError("Link inválido.") from exc


# ── Confirmação de e-mail ─────────────────────────────────────


def create_email_verification_token(
    user_id: uuid.UUID, email_verified: bool, settings: Settings
) -> str:
    now = datetime.now(UTC)
    return _encode(
        {
            "sub": str(user_id),
            "type": _VERIFY_TYPE,
            # Estado de verificação de quando o link foi emitido. É o simétrico
            # do "pwd" do token de senha: assim que a conta é confirmada, o
            # estado muda e o link para de valer — inclusive o que acabou de
            # ser usado. Sem isto o link servia pelas 24 h inteiras, mesmo já
            # confirmado.
            "vrf": bool(email_verified),
            "iat": now,
            "exp": now + timedelta(hours=settings.email_verification_token_hours),
            "iss": settings.jwt_issuer,
        },
        settings,
    )


def peek_email_verification_subject(token: str, settings: Settings) -> uuid.UUID:
    """
    De quem é o link, sem ainda checar se continua valendo.

    Mesmo motivo do `peek_password_reset_subject`: a validação de uso único
    compara com o estado atual do usuário, e para buscá-lo é preciso saber o id
    primeiro. Assinatura e tipo já são verificados aqui.
    """
    return _subject(_decode(token, _VERIFY_TYPE, settings))


def read_email_verification_token(
    token: str, email_verified: bool, settings: Settings
) -> uuid.UUID:
    payload = _decode(token, _VERIFY_TYPE, settings)

    if bool(payload.get("vrf")) != bool(email_verified):
        raise InvalidTokenError("Este link de confirmação já foi usado.")

    return _subject(payload)


# ── Redefinição de senha ──────────────────────────────────────


def create_password_reset_token(
    user_id: uuid.UUID, current_password_hash: str, settings: Settings
) -> str:
    now = datetime.now(UTC)
    return _encode(
        {
            "sub": str(user_id),
            "type": _RESET_TYPE,
            "pwd": _password_fingerprint(current_password_hash),
            "iat": now,
            "exp": now + timedelta(hours=settings.password_reset_token_hours),
            "iss": settings.jwt_issuer,
        },
        settings,
    )


def peek_password_reset_subject(token: str, settings: Settings) -> uuid.UUID:
    """
    De quem é o link, sem ainda checar se continua valendo.

    Necessário porque a validação de uso único compara com a senha atual do
    usuário — e para buscar esse usuário é preciso saber o id primeiro. A
    assinatura e o tipo do token já são verificados aqui.
    """
    return _subject(_decode(token, _RESET_TYPE, settings))


def read_password_reset_token(
    token: str, current_password_hash: str, settings: Settings
) -> uuid.UUID:
    payload = _decode(token, _RESET_TYPE, settings)

    if payload.get("pwd") != _password_fingerprint(current_password_hash):
        raise InvalidTokenError("Este link já foi usado ou a senha foi alterada depois do pedido.")

    return _subject(payload)
