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

_DOMINIO_REAL = "https://helpdesk.healthsafetytech.com"


def _settings(**overrides) -> Settings:
    """
    Settings isolado do ambiente.

    `_env_file=None` ignora o `.env` da máquina; sem isso o teste passaria a
    depender da configuração local de quem roda — e testaria outra coisa.
    """
    return Settings(_env_file=None, **{**_BASE, **overrides})


def _producao(**overrides) -> Settings:
    """Produção com as duas URLs já válidas — cada teste estraga só o que testa."""
    base = {
        "app_env": "production",
        "cors_origins": _DOMINIO_REAL,
        "frontend_url": _DOMINIO_REAL,
    }
    return _settings(**{**base, **overrides})


# ── Produção precisa de CORS_ORIGINS explícito ────────────────
#
# O default de `cors_origins` é localhost. Como o nginx do front não faz proxy
# para a API, o navegador fala com outro domínio e o CORS é obrigatório: subir
# em produção com o default significa front bloqueado — ou, se alguém "resolver"
# com "*", origem liberada para qualquer site.


def test_production_rejects_default_localhost_origins(monkeypatch):
    """Sem CORS_ORIGINS no ambiente, o default de localhost não pode passar."""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _settings(app_env="production", frontend_url=_DOMINIO_REAL)


def test_production_rejects_explicit_localhost_origin():
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _producao(cors_origins=f"{_DOMINIO_REAL},http://localhost:5173")


def test_production_rejects_wildcard_origin():
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _producao(cors_origins="*")


def test_production_accepts_real_domain():
    s = _producao()
    assert s.get_cors_origins() == [_DOMINIO_REAL]


# ── Lista vazia não é configuração válida ─────────────────────
#
# `any()` sobre lista vazia é falso: sem checar o tamanho, CORS_ORIGINS=""
# passava por todas as regras e a API subia com zero origens — o front fica
# bloqueado e o backend não reclama de nada.


@pytest.mark.parametrize("vazio", ["", "   ", "[]", ","])
def test_production_rejects_empty_origin_list(vazio):
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _producao(cors_origins=vazio)


# ── APP_ENV precisa ser reconhecido sem depender de caixa ─────
#
# A comparação exata com "production" fazia APP_ENV=Production pular TODA a
# validação de produção, inclusive a da SECRET_KEY.


@pytest.mark.parametrize("valor", ["Production", "PRODUCTION", " production ", "prod"])
def test_production_is_recognized_regardless_of_case_and_spacing(valor):
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _settings(app_env=valor, cors_origins="http://localhost:5173")


# ── Loopback pelo host, não por substring ─────────────────────
#
# Procurar "localhost" no texto da URL errava nas duas direções: barrava um
# domínio legítimo que contivesse a palavra e deixava passar [::1] e 0.0.0.0.


@pytest.mark.parametrize(
    "origem",
    [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://[::1]:5173",
        "http://0.0.0.0:8000",
        "localhost:5173",
    ],
)
def test_production_rejects_loopback_origins(origem):
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _producao(cors_origins=origem)


def test_production_accepts_domain_that_merely_contains_localhost():
    """`localhost.healthsafetytech.com` é um domínio real, não loopback."""
    s = _producao(cors_origins="https://localhost.healthsafetytech.com")
    assert s.get_cors_origins() == ["https://localhost.healthsafetytech.com"]


# ── Formato JSON: strip e erro legível ────────────────────────


def test_json_origins_are_stripped():
    s = _producao(cors_origins=f'["  {_DOMINIO_REAL}  ", ""]')
    assert s.get_cors_origins() == [_DOMINIO_REAL]


def test_broken_json_origins_names_the_variable():
    """JSONDecodeError cru no boot não diz qual variável está errada."""
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _producao(cors_origins='["https://helpdesk.tld"')


# ── FRONTEND_URL tem a mesma classe de falha ──────────────────
#
# É a URL usada para montar os links dos e-mails de confirmação e de
# redefinição de senha: apontando para localhost em produção, o e-mail sai com
# link que não funciona para ninguém.


@pytest.mark.parametrize(
    "url", ["http://localhost:5173", "http://127.0.0.1:3000", "http://[::1]:5173"]
)
def test_production_rejects_loopback_frontend_url(url):
    with pytest.raises(ValueError, match="FRONTEND_URL"):
        _producao(frontend_url=url)


def test_production_accepts_real_frontend_url():
    s = _producao(frontend_url=_DOMINIO_REAL)
    assert s.frontend_url == _DOMINIO_REAL


# ── Fora de produção nada disso é exigido ─────────────────────


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
        _producao(secret_key="curta")
