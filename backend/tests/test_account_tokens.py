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

    token = account_tokens.create_email_verification_token(user_id, False, settings)

    assert account_tokens.read_email_verification_token(token, False, settings) == user_id


def test_token_de_confirmacao_vencido_e_recusado():
    settings = _settings(verify_hours=-1)
    token = account_tokens.create_email_verification_token(uuid.uuid4(), False, settings)

    with pytest.raises(account_tokens.InvalidTokenError):
        account_tokens.read_email_verification_token(token, False, settings)


def test_token_adulterado_e_recusado():
    settings = _settings()

    with pytest.raises(account_tokens.InvalidTokenError):
        account_tokens.read_email_verification_token("nao.e.token", False, settings)


def test_token_de_senha_nao_confirma_email():
    """Cada link serve para uma coisa só."""
    settings = _settings()
    token = account_tokens.create_password_reset_token(uuid.uuid4(), "hash-atual", settings)

    with pytest.raises(account_tokens.InvalidTokenError):
        account_tokens.read_email_verification_token(token, False, settings)


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
    token = account_tokens.create_email_verification_token(uuid.uuid4(), False, settings)

    with pytest.raises(account_tokens.InvalidTokenError):
        account_tokens.read_password_reset_token(token, "hash", settings)


# ═══════════════════════════════════════════════════════════════
# O link de confirmação é de uso único, como o de senha
# ═══════════════════════════════════════════════════════════════


def test_token_de_confirmacao_para_de_valer_depois_de_usado():
    """
    O token de senha já é de uso único: carrega a impressão da senha vigente e
    morre quando ela muda. O de confirmação não carregava estado nenhum, então
    valia pelas 24 h inteiras — um link vazado (e-mail encaminhado, histórico
    do navegador, log de proxy) continuava servindo depois de confirmado.

    Simétrico: o token carrega o estado de verificação de quando foi emitido.
    """
    from app.services import account_tokens

    user_id = uuid.uuid4()
    token = account_tokens.create_email_verification_token(user_id, False, _settings())

    # Primeiro uso: a conta ainda não estava confirmada.
    assert account_tokens.read_email_verification_token(token, False, _settings()) == user_id

    # Depois de confirmada, o MESMO link não vale mais.
    with pytest.raises(account_tokens.InvalidTokenError):
        account_tokens.read_email_verification_token(token, True, _settings())


def test_peek_de_confirmacao_diz_de_quem_e_sem_validar_o_estado():
    """
    Necessário pelo mesmo motivo do de senha: para comparar com o estado atual
    é preciso buscar o usuário, e para buscar é preciso saber o id primeiro.
    """
    from app.services import account_tokens

    user_id = uuid.uuid4()
    token = account_tokens.create_email_verification_token(user_id, False, _settings())
    assert account_tokens.peek_email_verification_subject(token, _settings()) == user_id


def test_token_de_confirmacao_nao_serve_para_redefinir_senha():
    """A separação por `type` continua valendo depois da mudança."""
    from app.services import account_tokens

    token = account_tokens.create_email_verification_token(uuid.uuid4(), False, _settings())
    with pytest.raises(account_tokens.InvalidTokenError):
        account_tokens.peek_password_reset_subject(token, _settings())
