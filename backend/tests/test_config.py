"""
Validações de configuração que rodam no boot (Settings.model_post_init).

São testes de configuração, não de request: o que se prova aqui é que a
aplicação se recusa a subir em produção com valor de desenvolvimento, do mesmo
jeito que já faz com a SECRET_KEY curta.
"""

import os
from unittest.mock import patch

import pytest

from app.core.config import Settings

# Variáveis que, exportadas no shell, mudariam o resultado destes testes: são
# exatamente as que a suíte quer avaliar no default. O conftest já exporta
# APP_ENV, e os containers de dev e staging exportam CORS_ORIGINS.
_ENVS_SENSIVEIS = frozenset(
    {
        "APP_ENV",
        "CORS_ORIGINS",
        "SECRET_KEY",
        "FRONTEND_URL",
        "EMAIL_VERIFICATION_ENABLED",
        "SMTP_USER",
        "SMTP_FROM_EMAIL",
    }
)

# Valores mínimos para instanciar Settings sem esbarrar em outra validação
_BASE = {
    "database_url": "postgresql+asyncpg://user:pass@localhost/db",
    "secret_key": "x" * 32,
}

_DOMINIO_REAL = "https://helpdesk.healthsafetytech.com"


def _settings(**overrides) -> Settings:
    """
    Settings isolado do ambiente.

    `_env_file=None` ignora o `.env` da máquina — mas só ele. Variável
    exportada no shell vence o default do pydantic-settings, então quem tivesse
    CORS_ORIGINS no ambiente veria os testes de default quebrarem sem ter
    mexido em nada. Daí o segundo isolamento: as sensíveis saem do
    `os.environ` durante a construção e o `patch.dict` devolve tudo ao sair.
    """
    with patch.dict(os.environ):
        for nome in [k for k in os.environ if k.upper() in _ENVS_SENSIVEIS]:
            os.environ.pop(nome, None)
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


def test_production_rejects_default_localhost_origins():
    """Sem CORS_ORIGINS no ambiente, o default de localhost não pode passar."""
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


# ── A normalização vale para TODAS as leituras do APP_ENV ─────
#
# A tolerância de caixa e espaço existia só dentro do ramo de produção. As
# outras duas leituras comparavam a string crua, então `APP_ENV=Testing` num
# job de CI subia o rate limiter LIGADO apontando para um Redis que não existe,
# e `APP_ENV=Development` desligava o /docs calado. Normalizar na origem — no
# próprio campo — faz as três leituras enxergarem o mesmo valor.


@pytest.mark.parametrize(
    ("digitado", "esperado"),
    [
        ("Production", "production"),
        (" testing ", "testing"),
        ("DEVELOPMENT", "development"),
        ("  Prod", "prod"),
    ],
)
def test_app_env_is_stored_normalized(digitado, esperado):
    s = _settings(app_env=digitado, cors_origins=_DOMINIO_REAL, frontend_url=_DOMINIO_REAL)
    assert s.app_env == esperado


@pytest.mark.parametrize("valor", ["development", "Development", " DEVELOPMENT "])
def test_is_development_ignores_case_and_spacing(valor):
    """`is_development` liga o /docs e o echo de SQL — caixa não pode desligar isso."""
    assert _settings(app_env=valor).is_development


@pytest.mark.parametrize("valor", ["testing", "Testing", " TESTING "])
def test_is_testing_ignores_case_and_spacing(valor):
    """
    É o que o rate limiter consulta para subir desligado e em memória.

    Com a comparação exata, `APP_ENV=Testing` no CI deixava o limiter ligado
    contra o `redis_url` — a suíte de auth batia num Redis inexistente.
    """
    assert _settings(app_env=valor).is_testing


def test_production_is_not_development_nor_testing():
    s = _producao()
    assert not s.is_development
    assert not s.is_testing
    assert s.is_production


# ── O helper precisa isolar do ambiente, não só do .env ───────
#
# `_env_file=None` cala o `.env` da máquina, mas não as variáveis exportadas no
# shell — e elas vencem o default do pydantic-settings. Quem tivesse
# CORS_ORIGINS no ambiente (o caso de dentro dos containers de dev e staging)
# via os testes de default quebrarem sem ter mexido em nada, exatamente o
# problema que o conftest foi escrito para resolver.


@pytest.mark.parametrize(
    ("variavel", "valor"),
    [
        ("CORS_ORIGINS", "https://exportado.example.com"),
        ("SECRET_KEY", "y" * 40),
        ("APP_ENV", "production"),
        ("FRONTEND_URL", "https://exportado.example.com"),
    ],
)
def test_helper_ignores_exported_environment(monkeypatch, variavel, valor):
    """Variável sensível exportada no shell não pode mudar o Settings do teste."""
    monkeypatch.setenv(variavel, valor)

    s = _settings()

    assert "http://localhost:5173" in s.get_cors_origins()
    assert s.secret_key == _BASE["secret_key"]
    assert s.app_env == "development"
    assert s.frontend_url == "http://localhost:5173"


# ── Confiança nos cabeçalhos do proxy ─────────────────────────
#
# O rate limit de login usa o IP visto pelo servidor. Atrás do proxy do
# EasyPanel esse IP é o do PRÓPRIO proxy, a menos que o uvicorn seja autorizado
# a ler o X-Forwarded-For — e o default dele é não ler de ninguém além do
# loopback. Sem autorizar, o balde de 5/15min vira UM balde para o sistema
# inteiro: cinco senhas erradas de qualquer pessoa travam o login de todos.
#
# Autorizar é o passo que fecha isso, mas só é seguro se o container do backend
# não estiver publicado direto na internet — se estiver, qualquer um forja o
# X-Forwarded-For e pula o rate limit de vez, que é pior. Por isso o default
# aqui é o conservador, e ligar é decisão explícita de quem conhece a
# topologia. Ver o aviso em mudanças.md.


def test_proxy_headers_are_not_trusted_by_default():
    """O default não autoriza ninguém — ligar é decisão explícita."""
    assert _settings().forwarded_allow_ips == ""
    assert not _settings().trusts_proxy_headers


@pytest.mark.parametrize("valor", ["*", "10.0.0.0/8", " 172.17.0.1 "])
def test_configured_proxy_is_trusted(valor):
    assert _settings(forwarded_allow_ips=valor).trusts_proxy_headers


def test_blank_value_does_not_count_as_configured():
    """Só espaço é o mesmo que vazio — não pode passar por 'configurado'."""
    assert not _settings(forwarded_allow_ips="   ").trusts_proxy_headers


def test_production_without_trusted_proxy_is_flagged():
    """
    Produção sem proxy autorizado é o estado que precisa gritar no boot.

    Não derruba o processo: derrubar trocaria um rate limit global por uma API
    que não sobe, e quem tem o backend publicado direto está certo em ficar
    assim.
    """
    assert _producao().rate_limit_por_ip_do_proxy
    assert not _producao(forwarded_allow_ips="*").rate_limit_por_ip_do_proxy
    assert not _settings().rate_limit_por_ip_do_proxy  # fora de produção, não interessa


# ── Confirmação de e-mail é adotada por flag, não inferida ────


def test_confirmacao_desligada_por_padrao_mesmo_com_smtp():
    """SMTP preenchido (seed do .env.example) não pode ligar a exigência sozinho."""
    s = _settings(smtp_user="helpdesk@healthsafetytech.com")
    assert not s.requires_email_verification()


def test_confirmacao_exige_flag_e_smtp_juntos():
    s = _settings(email_verification_enabled=True, smtp_from_email="a@b.c")
    assert s.requires_email_verification()
    assert not _settings(email_verification_enabled=True).requires_email_verification()


def test_producao_recusa_flag_ligada_sem_smtp():
    """Adotar a confirmação sem SMTP é a armadilha que trava login — grita no boot."""
    with pytest.raises(ValueError, match="EMAIL_VERIFICATION_ENABLED"):
        _producao(email_verification_enabled=True)

    # Com SMTP junto, produção sobe normalmente
    _producao(email_verification_enabled=True, smtp_from_email="a@b.c")
