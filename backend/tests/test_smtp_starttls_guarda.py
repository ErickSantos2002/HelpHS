"""
Guarda de boot contra STARTTLS vulnerável (CVE-2026-55558).

O `aiosmtplib` abaixo da 5.1.2 não descarta o que ficou no buffer de recepção
antes do handshake do STARTTLS: bytes lidos do socket em TEXTO CLARO sobrevivem
à fronteira e são interpretados como se tivessem chegado dentro do TLS. Um
atacante ativo na perna em claro injeta respostas na sessão SMTP.

O aviso afeta **só** quem faz o upgrade por STARTTLS. Com TLS implícito na 465
não existe perna em claro, e o caminho vulnerável nunca é percorrido — a
mitigação é de configuração, e não depende de subir o pacote.

Estes testes existem porque **configuração não se defende sozinha**. A variável
mora no painel do EasyPanel, fora do repositório e fora de qualquer revisão de
código: alguém pode voltar `SMTP_TLS=true` sem que nada reclame. A guarda
transforma isso em falha de boot, e estes testes garantem que a guarda continue
existindo.

Porta 465 conferida contra o provedor em 01/09/2026, sem enviar e-mail e sem
credencial: `smtp.resend.com:465` aceitou TLS implícito com TLSv1.3 e anunciou
AUTH — as mesmas extensões da 587.
"""

from unittest.mock import patch

import pytest

from app.core.config import Settings, _aiosmtplib_vulneravel


def _producao(**extra):
    """Settings de produção com o mínimo para passar das outras validações."""
    base = dict(
        app_env="production",
        secret_key="x" * 40,
        cors_origins='["https://helphs.exemplo.com"]',
        frontend_url="https://helphs.exemplo.com",
        smtp_from_email="naoresponda@exemplo.com",
    )
    base.update(extra)
    return Settings(**base)


# ── A guarda barra o caminho vulnerável ───────────────────────


def test_starttls_com_aiosmtplib_vulneravel_derruba_o_boot():
    with patch("app.core.config._aiosmtplib_vulneravel", return_value=True):
        with pytest.raises(ValueError) as erro:
            _producao(smtp_tls=True, smtp_ssl=False, smtp_port=587)

    texto = str(erro.value)
    assert "STARTTLS" in texto
    assert "465" in texto, "a mensagem precisa dizer qual é a saída"
    assert "5.1.2" in texto, "a mensagem precisa dizer qual versão corrige"


def test_tls_implicito_na_465_passa():
    """A configuração recomendada não pode ser barrada."""
    with patch("app.core.config._aiosmtplib_vulneravel", return_value=True):
        s = _producao(smtp_tls=False, smtp_ssl=True, smtp_port=465)

    assert s.smtp_ssl is True
    assert s.smtp_tls is False


def test_com_aiosmtplib_corrigido_o_starttls_volta_a_ser_permitido():
    """A guarda é sobre a versão vulnerável, não sobre STARTTLS em si.

    Se ela barrasse STARTTLS para sempre, viraria dogma: no dia em que o
    `fastapi-mail` liberar o `aiosmtplib >= 5.1.2`, a 587 volta a ser uma
    escolha legítima e ninguém precisa lembrar de mexer aqui.
    """
    with patch("app.core.config._aiosmtplib_vulneravel", return_value=False):
        s = _producao(smtp_tls=True, smtp_ssl=False, smtp_port=587)

    assert s.smtp_tls is True


# ── Configuração incoerente ───────────────────────────────────


def test_tls_e_ssl_juntos_derrubam_o_boot():
    """Ligar os dois esconde qual caminho está em uso — e a guarda do STARTTLS
    passaria a depender de qual deles o cliente escolhe internamente."""
    with pytest.raises(ValueError) as erro:
        _producao(smtp_tls=True, smtp_ssl=True, smtp_port=465)

    assert "não podem estar ligados ao mesmo tempo" in str(erro.value)


# ── Sem SMTP, sem trava ───────────────────────────────────────


def test_smtp_desligado_nao_bloqueia_o_boot():
    """Quem não envia e-mail não tem risco de transporte.

    Barrar aqui seria transformar uma proteção em obstáculo para quem sequer
    usa o recurso.
    """
    with patch("app.core.config._aiosmtplib_vulneravel", return_value=True):
        s = _producao(smtp_tls=True, smtp_ssl=False, smtp_from_email="", smtp_user="")

    assert s.email_is_configured() is False


def test_desenvolvimento_segue_flexivel():
    """A validação inteira retorna cedo fora de produção/staging — quem
    desenvolve usa Mailpit em texto claro, e travar isso não protege ninguém."""
    with patch("app.core.config._aiosmtplib_vulneravel", return_value=True):
        s = Settings(
            app_env="development",
            smtp_tls=True,
            smtp_ssl=False,
            smtp_from_email="dev@local",
        )

    assert s.smtp_tls is True


# ── O detector de versão ──────────────────────────────────────


@pytest.mark.parametrize(
    "instalada,esperado",
    [
        ("3.0.2", True),
        ("5.1.1", True),
        ("5.1.2", False),
        ("5.2.0", False),
        ("6.0.0", False),
        ("5.1.2rc1", False),
    ],
)
def test_comparacao_de_versao(instalada, esperado):
    with patch("importlib.metadata.version", return_value=instalada):
        assert _aiosmtplib_vulneravel() is esperado


def test_pacote_ausente_nao_e_tratado_como_vulneravel():
    """Sem `aiosmtplib` instalado não há envio, logo não há risco — e falhar
    aqui travaria o boot de quem removeu o e-mail do projeto."""
    with patch("importlib.metadata.version", side_effect=Exception("nao instalado")):
        assert _aiosmtplib_vulneravel() is False
