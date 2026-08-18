"""
Validações de configuração que rodam no boot (Settings.model_post_init).

São testes de configuração, não de request: o que se prova aqui é que a
aplicação se recusa a subir em produção com valor de desenvolvimento, do mesmo
jeito que já faz com a SECRET_KEY curta.
"""

import pytest

from app.core.config import Settings

# Valores mínimos para instanciar Settings sem esbarrar em outra validação
_BASE = {
    "database_url": "postgresql+asyncpg://user:pass@localhost/db",
    "secret_key": "x" * 32,
}


def _settings(**overrides) -> Settings:
    return Settings(**{**_BASE, **overrides})


# ── Produção precisa de CORS_ORIGINS explícito ────────────────
#
# O default de `cors_origins` é localhost. Como o nginx do front não faz proxy
# para a API, o navegador fala com outro domínio e o CORS é obrigatório: subir
# em produção com o default significa front bloqueado — ou, se alguém "resolver"
# com "*", origem liberada para qualquer site.


def test_production_rejects_default_localhost_origins():
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _settings(app_env="production")


def test_production_rejects_explicit_localhost_origin():
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _settings(app_env="production", cors_origins="https://helpdesk.tld,http://localhost:5173")


def test_production_rejects_wildcard_origin():
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _settings(app_env="production", cors_origins="*")


def test_production_accepts_real_domain():
    s = _settings(app_env="production", cors_origins="https://helpdesk.healthsafetytech.com")
    assert s.get_cors_origins() == ["https://helpdesk.healthsafetytech.com"]


def test_development_keeps_localhost_default():
    """Dev não é afetado: o default de localhost continua valendo."""
    s = _settings(app_env="development")
    assert "http://localhost:5173" in s.get_cors_origins()


def test_testing_keeps_localhost_default():
    """A suíte roda com APP_ENV=testing e não pode exigir configuração de produção."""
    s = _settings(app_env="testing")
    assert "http://localhost:5173" in s.get_cors_origins()


# ── A validação de SECRET_KEY que já existia segue valendo ────


def test_production_still_rejects_short_secret_key():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(
            database_url=_BASE["database_url"],
            secret_key="curta",
            app_env="production",
            cors_origins="https://helpdesk.healthsafetytech.com",
        )
