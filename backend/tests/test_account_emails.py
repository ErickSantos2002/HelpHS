"""
Testes dos e-mails de conta (`app/services/account_emails.py`).

Não existiam. O levantamento de 04/09/2026 apontou: um `grep` por
`account_emails` em `tests/` não retornava nada — e são justamente os três
e-mails que carregam link de ação, os únicos que TODO mundo recebe (staff
incluído) e os alvos clássicos de phishing.

O que estes testes prendem é o que quebra em silêncio: o link certo, o nome
escapado, e as duas partes saindo juntas. Nada aqui abre conexão SMTP —
`send_email` é substituído.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.services import account_emails

_TOKEN = "eyJhbGciOiJIUzI1NiJ9.abc"


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        frontend_url="https://helphs.exemplo.com/",
    )


async def _captura(coro) -> dict:
    """Roda o envio e devolve os argumentos com que `send_email` foi chamado."""
    with patch.object(account_emails, "send_email", new=AsyncMock(return_value=True)) as enviar:
        await coro
    return enviar.await_args.kwargs


@pytest.mark.asyncio
async def test_confirmacao_leva_o_link_de_confirmar_email():
    args = await _captura(
        account_emails.send_verification_email("welton@exemplo.com", "Welton", _TOKEN, _settings())
    )

    esperado = f"https://helphs.exemplo.com/confirmar-email?token={_TOKEN}"
    assert esperado in args["body"], "a parte de texto precisa da URL inteira"
    assert esperado.replace("&", "&amp;") in args["html"] or esperado in args["html"]
    assert args["subject"] == "[HelpHS] Confirme seu e-mail para ativar a conta"


@pytest.mark.asyncio
async def test_redefinicao_leva_o_link_de_redefinir_senha():
    args = await _captura(
        account_emails.send_password_reset_email(
            "welton@exemplo.com", "Welton", _TOKEN, _settings()
        )
    )

    assert f"https://helphs.exemplo.com/redefinir-senha?token={_TOKEN}" in args["body"]
    assert args["subject"] == "[HelpHS] Redefinição de senha"


@pytest.mark.asyncio
async def test_conta_existente_nao_revela_nada_sobre_a_conta():
    """A mensagem sustenta a resposta neutra do cadastro: não pode vazar dado.

    Ela não recebe `name` por assinatura — este teste prende que nenhum dado da
    conta apareça, hoje ou depois de alguém "melhorar" o texto.
    """
    args = await _captura(
        account_emails.send_account_exists_email("welton@exemplo.com", _settings())
    )

    corpo = args["body"] + args["html"]
    assert "https://helphs.exemplo.com/login" in args["body"]
    assert "welton@exemplo.com" not in corpo, "nem o próprio endereço deve aparecer no corpo"
    assert "Welton" not in corpo


@pytest.mark.asyncio
async def test_as_duas_partes_saem_juntas():
    """Sem a parte de texto, filtro de spam penaliza e gateway corporativo some."""
    args = await _captura(
        account_emails.send_verification_email("welton@exemplo.com", "Welton", _TOKEN, _settings())
    )

    assert args["body"], "faltou a parte de texto"
    assert args["html"], "faltou a parte de HTML"
    assert "<table" in args["html"]
    assert "<table" not in args["body"]


@pytest.mark.asyncio
async def test_o_nome_do_usuario_e_escapado_no_html():
    """Cadastro com nome hostil não pode virar marcação dentro do e-mail.

    Em texto puro isto era inofensivo, e por isso passou despercebido enquanto
    não havia HTML.
    """
    args = await _captura(
        account_emails.send_verification_email(
            "x@exemplo.com", "<script>alert(1)</script>", _TOKEN, _settings()
        )
    )

    assert "<script>" not in args["html"]
    assert "&lt;script&gt;" in args["html"]


@pytest.mark.asyncio
async def test_a_barra_final_do_frontend_url_nao_duplica():
    """`FRONTEND_URL` com barra no fim não pode gerar `//confirmar-email`."""
    args = await _captura(
        account_emails.send_verification_email("x@exemplo.com", "X", _TOKEN, _settings())
    )

    assert "exemplo.com//" not in args["body"]
