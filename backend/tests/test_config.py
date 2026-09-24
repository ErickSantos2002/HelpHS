"""
Validações de configuração que rodam no boot (Settings.model_post_init).

São testes de configuração, não de request: o que se prova aqui é que a
aplicação se recusa a subir em produção com valor de desenvolvimento, do mesmo
jeito que já faz com a SECRET_KEY curta.
"""

import os
from unittest.mock import patch

import pytest

from app.core.config import ConfiguracaoDaTelefoniaInvalidaError, Settings

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
        "API4COM_ENABLED",
        "API4COM_TOKEN",
        "API4COM_BASE_URL",
        "API4COM_TIMEOUT_SECONDS",
        "LGPD_REVISAO_POLITICA",
        "LGPD_REVISAO_TERMOS",
        "LGPD_EXIGE_REACEITE",
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
        "lgpd_revisao_politica": "00",
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
    s = _settings(
        app_env=digitado,
        cors_origins=_DOMINIO_REAL,
        frontend_url=_DOMINIO_REAL,
        lgpd_revisao_politica="00",
    )
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


# ═══════════════════════════════════════════════════════════════
# Ambiente que não é local vale como ambiente de verdade
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize("ambiente", ["staging", "homolog", "qa", "sandbox"])
def test_ambiente_nao_local_nao_escapa_das_validacoes(ambiente):
    """
    O guard começava com `if not self.is_production: return`, então qualquer
    APP_ENV fora de "production"/"prod" aceitava SECRET_KEY curta,
    CORS_ORIGINS=* e FRONTEND_URL de localhost.

    Um staging exposto na internet com essas três é um ambiente de produção
    com outro nome — e é justamente onde se testa com dado copiado do real.
    """
    with pytest.raises(ValueError, match="SECRET_KEY"):
        _settings(app_env=ambiente, secret_key="curta")


@pytest.mark.parametrize("ambiente", ["staging", "qa"])
def test_ambiente_nao_local_recusa_cors_aberto(ambiente):
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _settings(app_env=ambiente, cors_origins="*", frontend_url=_DOMINIO_REAL)


@pytest.mark.parametrize("ambiente", ["staging", "qa"])
def test_ambiente_nao_local_recusa_frontend_local(ambiente):
    with pytest.raises(ValueError, match="FRONTEND_URL"):
        _settings(
            app_env=ambiente,
            cors_origins=_DOMINIO_REAL,
            frontend_url="http://localhost:5173",
        )


@pytest.mark.parametrize("ambiente", ["development", "testing"])
def test_ambiente_local_continua_liberado(ambiente):
    """
    A blindagem não pode atrapalhar quem desenvolve: sem SECRET_KEY longa, com
    localhost no CORS e no FRONTEND_URL, tem de subir igual.
    """
    s = _settings(app_env=ambiente, secret_key="curta")
    assert s.app_env == ambiente


def test_staging_correto_sobe_e_continua_nao_sendo_producao():
    """
    A validação aperta, mas não promove: `is_production` segue False, senão
    staging herdaria decisões que são só de produção (o /docs desligado, o
    seed de admin que não roda).
    """
    s = _settings(
        app_env="staging",
        cors_origins=_DOMINIO_REAL,
        frontend_url=_DOMINIO_REAL,
        lgpd_revisao_politica="00",
    )
    assert s.is_production is False
    assert s.is_development is False


_SEGREDO = "token-de-teste-que-nao-pode-aparecer-em-lugar-nenhum-4F2X"


# ── Telefonia — API4COM ──────────────────────────────────────
#
# Esta validação é a ÚNICA do arquivo que roda em todos os ambientes. As
# outras protegem contra subir PRODUÇÃO com valor de desenvolvimento, e em dev
# aquele valor é o certo. Esta protege contra ligar a integração sem ter como
# autenticar — e isso está igualmente errado em qualquer lugar.
#
# Daí a posição no `model_post_init`: no topo, antes do `return` que dispensa
# development e testing. Os dois testes de ambiente abaixo prendem justamente
# essa posição; se alguém mover a chamada para baixo do `return`, eles caem.


def test_desligada_e_sem_token_e_configuracao_valida():
    """O estado de hoje em produção: ninguém precisa de token para o sistema subir."""
    s = _settings()
    assert s.api4com_enabled is False
    assert s.api4com_token.get_secret_value() == ""
    assert s.api4com_base_url == "https://api.api4com.com/api/v1"


def test_ligada_sem_token_nao_sobe():
    with pytest.raises(ConfiguracaoDaTelefoniaInvalidaError, match="API4COM_TOKEN"):
        _settings(api4com_enabled=True)


@pytest.mark.parametrize("vazio", ["", "   ", "\t", "\n"])
def test_token_so_de_espaco_conta_como_ausente(vazio):
    """Um espaço colado sem querer no painel não pode passar por credencial."""
    with pytest.raises(ConfiguracaoDaTelefoniaInvalidaError, match="API4COM_TOKEN"):
        _settings(api4com_enabled=True, api4com_token=vazio)


@pytest.mark.parametrize(
    "url",
    ["", "   ", "api.api4com.com/api/v1", "ftp://api.api4com.com", "https://", "só um texto"],
)
def test_ligada_com_base_url_invalida_nao_sobe(url):
    with pytest.raises(ConfiguracaoDaTelefoniaInvalidaError, match="API4COM_BASE_URL"):
        _settings(api4com_enabled=True, api4com_token="x", api4com_base_url=url)


@pytest.mark.parametrize("url", ["https://api.api4com.com/api/v1", "http://localhost:8080/v1"])
def test_ligada_com_base_url_valida_sobe(url):
    """`http` é aceito de propósito: um proxy local de homologação é caso legítimo."""
    s = _settings(api4com_enabled=True, api4com_token="x", api4com_base_url=url)
    assert s.api4com_base_url == url


@pytest.mark.parametrize("valor", [0, -1, -30])
def test_ligada_com_timeout_nao_positivo_nao_sobe(valor):
    with pytest.raises(ConfiguracaoDaTelefoniaInvalidaError, match="API4COM_TIMEOUT_SECONDS"):
        _settings(api4com_enabled=True, api4com_token="x", api4com_timeout_seconds=valor)


@pytest.mark.parametrize("ambiente", ["development", "testing", "staging", "production"])
def test_a_validacao_da_telefonia_vale_em_todos_os_ambientes(ambiente):
    """Inclusive dev e testing, ao contrário de todas as outras deste arquivo.

    Se a chamada a `_valida_api4com()` escorregar para depois do `return` que
    dispensa os ambientes locais, os dois primeiros casos deste teste passam a
    não levantar nada — e é exatamente isso que ele existe para impedir.
    """
    base = {"app_env": ambiente, "api4com_enabled": True}
    if ambiente in {"staging", "production"}:
        base |= {"cors_origins": _DOMINIO_REAL, "frontend_url": _DOMINIO_REAL}

    with pytest.raises(ConfiguracaoDaTelefoniaInvalidaError, match="API4COM_TOKEN"):
        _settings(**base)


@pytest.mark.parametrize(
    "estrago",
    [
        {"api4com_base_url": "nao-e-url"},
        {"api4com_timeout_seconds": 0},
    ],
    ids=["base_url", "timeout"],
)
def test_o_erro_de_boot_nao_conta_qual_era_o_token(estrago):
    """Quem lê um log de boot que falhou não pode ganhar a credencial de brinde.

    Este teste pegou um vazamento real. Enquanto a validação levantava
    `ValueError`, o pydantic a embrulhava num `ValidationError` que imprime
    `input_value=` com o dicionário de entrada truncado — e a CAUDA do token
    aparecia ali, medido com o valor vindo do ambiente. Por isso
    `ConfiguracaoDaTelefoniaInvalidaError` não herda de `ValueError`.

    Os dois casos estragam OUTRO campo de propósito: com o token preenchido e
    válido, ele é justamente o que não pode aparecer na mensagem.
    """
    with pytest.raises(ConfiguracaoDaTelefoniaInvalidaError) as capturado:
        _settings(api4com_enabled=True, api4com_token=_SEGREDO, **estrago)

    texto = str(capturado.value)
    assert _SEGREDO not in texto
    assert _SEGREDO[-12:] not in texto, "a cauda do token vazou na mensagem de boot"
    assert _SEGREDO[:12] not in texto, "a cabeça do token vazou na mensagem de boot"
    assert "input_value" not in texto, "o pydantic voltou a ecoar o dicionário de entrada"
    assert "database_url" not in texto.lower()


# ── O token não vaza pela representação do Settings ──────────
#
# Divergência deliberada do resto do arquivo: `smtp_password`,
# `deepseek_api_key` e `mfa_secret_encryption_key` são `str` cru e SAEM por
# extenso em qualquer uma das quatro formas abaixo. O que segura os três hoje é
# disciplina de quem escreve log, não o tipo. Segredo novo não precisa nascer
# com essa dívida.


@pytest.mark.parametrize(
    "como",
    [repr, str, lambda s: str(s.model_dump()), lambda s: s.model_dump_json()],
    ids=["repr", "str", "model_dump", "model_dump_json"],
)
def test_o_token_nao_aparece_na_representacao_do_settings(como):
    s = _settings(api4com_enabled=True, api4com_token=_SEGREDO)
    assert _SEGREDO not in como(s)


def test_o_token_continua_legivel_por_quem_precisa_dele():
    """O segredo não some — só exige um `get_secret_value()` explícito e greppável."""
    s = _settings(api4com_enabled=True, api4com_token=_SEGREDO)
    assert s.api4com_token.get_secret_value() == _SEGREDO


def test_os_segredos_antigos_continuam_como_estao():
    """Prende o ESCOPO da divergência: a 2A não mexeu nos outros campos.

    Este teste não aprova o comportamento — ele documenta que a dívida dos
    segredos antigos segue de pé e que trocá-los é decisão separada, com
    migração de painel. Se alguém converter um deles para `SecretStr`, este
    teste cai e obriga a conversa.
    """
    s = _settings(smtp_password="x", deepseek_api_key="y", mfa_secret_encryption_key="z")
    assert isinstance(s.smtp_password, str)
    assert isinstance(s.deepseek_api_key, str)
    assert isinstance(s.mfa_secret_encryption_key, str)


# ── LGPD: a revisão vigente da política é obrigatória ─────────
#
# Cada aceite grava a revisão vigente em `lgpd_consents`. Subir produção sem
# ela recriaria, por esquecimento de variável, o aceite que não diz qual texto
# foi aceito — o estado que a tabela existe para acabar.


def test_producao_sem_revisao_da_politica_nao_sobe():
    with pytest.raises(ValueError, match="LGPD_REVISAO_POLITICA"):
        _producao(lgpd_revisao_politica=None)


def test_producao_com_revisao_em_branco_nao_sobe():
    """Variável criada no painel e deixada vazia é ausência, não a revisão ""."""
    with pytest.raises(ValueError, match="LGPD_REVISAO_POLITICA"):
        _producao(lgpd_revisao_politica="   ")


def test_staging_tambem_exige_a_revisao():
    with pytest.raises(ValueError, match="LGPD_REVISAO_POLITICA"):
        _producao(app_env="staging", lgpd_revisao_politica=None)


def test_desenvolvimento_sobe_sem_revisao():
    assert _settings(app_env="development").lgpd_revisao_politica is None


def test_revisao_chega_sem_espacos():
    s = _producao(lgpd_revisao_politica=" 01 ", lgpd_revisao_termos=" 00 ")
    assert s.lgpd_revisao_politica == "01"
    assert s.lgpd_revisao_termos == "00"


def test_termos_de_uso_em_branco_viram_ausencia():
    """Os Termos ainda não existem: vazio precisa gravar NULL, não ""."""
    assert _producao(lgpd_revisao_termos="").lgpd_revisao_termos is None


def test_reaceite_nasce_desligado():
    assert _producao().lgpd_exige_reaceite is False
