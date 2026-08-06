"""
Testes dos tokens de confirmação de e-mail e redefinição de senha.

O ponto mais importante aqui é o uso único do token de senha: assim que a
senha muda, o link recebido por e-mail precisa deixar de funcionar.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from app.core.config import get_settings
from app.services import account_tokens

_real = get_settings()


def _settings(verify_hours: int = 24, reset_hours: int = 1):
    s = MagicMock()
    s.jwt_algorithm = _real.jwt_algorithm
    s.jwt_issuer = _real.jwt_issuer
    s.get_private_key = _real.get_private_key
    s.get_public_key = _real.get_public_key
    s.email_verification_token_hours = verify_hours
    s.password_reset_token_hours = reset_hours
    return s


# ── Confirmação de e-mail ─────────────────────────────────────


def test_token_de_confirmacao_ida_e_volta():
    settings = _settings()
    user_id = uuid.uuid4()

    token = account_tokens.create_email_verification_token(user_id, settings)

    assert account_tokens.read_email_verification_token(token, settings) == user_id


def test_token_de_confirmacao_vencido_e_recusado():
    settings = _settings(verify_hours=-1)
    token = account_tokens.create_email_verification_token(uuid.uuid4(), settings)

    with pytest.raises(account_tokens.InvalidTokenError):
        account_tokens.read_email_verification_token(token, settings)


def test_token_adulterado_e_recusado():
    settings = _settings()

    with pytest.raises(account_tokens.InvalidTokenError):
        account_tokens.read_email_verification_token("nao.e.token", settings)


def test_token_de_senha_nao_confirma_email():
    """Cada link serve para uma coisa só."""
    settings = _settings()
    token = account_tokens.create_password_reset_token(uuid.uuid4(), "hash-atual", settings)

    with pytest.raises(account_tokens.InvalidTokenError):
        account_tokens.read_email_verification_token(token, settings)


# ── Redefinição de senha ──────────────────────────────────────


def test_token_de_senha_ida_e_volta():
    settings = _settings()
    user_id = uuid.uuid4()

    token = account_tokens.create_password_reset_token(user_id, "hash-atual", settings)

    assert account_tokens.read_password_reset_token(token, "hash-atual", settings) == user_id


def test_token_de_senha_morre_apos_a_senha_mudar():
    """
    Uso único: o token carrega a impressão digital da senha vigente. Trocada a
    senha, o link que chegou por e-mail deixa de valer.
    """
    settings = _settings()
    token = account_tokens.create_password_reset_token(uuid.uuid4(), "hash-antigo", settings)

    with pytest.raises(account_tokens.InvalidTokenError):
        account_tokens.read_password_reset_token(token, "hash-novo", settings)


def test_token_de_senha_vencido_e_recusado():
    settings = _settings(reset_hours=-1)
    token = account_tokens.create_password_reset_token(uuid.uuid4(), "hash", settings)

    with pytest.raises(account_tokens.InvalidTokenError):
        account_tokens.read_password_reset_token(token, "hash", settings)


def test_token_de_confirmacao_nao_redefine_senha():
    settings = _settings()
    token = account_tokens.create_email_verification_token(uuid.uuid4(), settings)

    with pytest.raises(account_tokens.InvalidTokenError):
        account_tokens.read_password_reset_token(token, "hash", settings)
