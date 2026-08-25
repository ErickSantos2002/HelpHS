import json
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Nomes e endereços que só existem na máquina de quem desenvolve. Comparar o
# HOST da URL com este conjunto — e não procurar "localhost" no texto — evita os
# dois erros: barrar um domínio legítimo que contenha a palavra (ex.:
# localhost.healthsafetytech.com) e deixar passar [::1] ou 0.0.0.0.
_HOSTS_LOCAIS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0", ""})

# APP_ENV vem digitado à mão no painel de deploy: "Production" e "prod" precisam
# valer como produção, senão um detalhe de caixa desliga TODAS as validações.
#
# A tolerância mora no próprio campo (ver `_normaliza_app_env`), não em cada
# leitura: enquanto estava só aqui, `is_development` e o rate limiter
# comparavam a string crua — `APP_ENV=Testing` num job de CI subia o limiter
# ligado contra um Redis inexistente, e `Development` desligava o /docs calado.
_NOMES_DE_PRODUCAO = frozenset({"production", "prod"})


def _host_de(url: str) -> str:
    """Host da URL, em minúsculas. Aceita valor sem esquema (`localhost:5173`)."""
    referencia = url if "//" in url else f"//{url}"
    return (urlparse(referencia).hostname or "").lower()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: str = "development"

    @field_validator("app_env")
    @classmethod
    def _normaliza_app_env(cls, valor: str) -> str:
        """Ponto único onde a caixa e o espaço do APP_ENV deixam de importar."""
        return valor.strip().lower()

    # Senha do admin criado por `app.seeds`, que o `start.sh` roda a cada boot.
    # Sem default de propósito: enquanto havia um literal no código, todo deploy
    # de produção criava um administrador ativo com senha publicada no
    # repositório. Ausente, o seed pula a criação em vez de cair num valor
    # conhecido — e é essa ausência, não o APP_ENV, que segura o caso de a
    # variável de ambiente estar errada.
    seed_admin_password: str | None = None

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://localhost:8000"

    def get_cors_origins(self) -> list[str]:
        v = self.cors_origins.strip()
        if v.startswith("["):
            try:
                carregado = json.loads(v)
            except json.JSONDecodeError as exc:
                # Sem isto o boot morre com um JSONDecodeError que não diz qual
                # variável está malformada
                raise ValueError(f"CORS_ORIGINS não é um JSON válido: {exc}") from exc
            return [str(o).strip() for o in carregado if str(o).strip()]
        return [o.strip() for o in v.split(",") if o.strip()]

    # Database
    database_url: str
    postgres_user: str = "helpdesk_user"
    postgres_password: str = ""
    postgres_db: str = "helpdesk_db"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""

    # JWT — suporta conteudo direto (producao) ou caminho de arquivo (dev)
    jwt_private_key_path: str = "./keys/private.pem"
    jwt_public_key_path: str = "./keys/public.pem"
    jwt_private_key: str = ""  # conteudo PEM direto (prioridade sobre path)
    jwt_public_key: str = ""  # conteudo PEM direto (prioridade sobre path)
    jwt_access_token_expires_minutes: int = 480
    jwt_refresh_token_expires_days: int = 7
    jwt_algorithm: str = "RS256"
    jwt_issuer: str = "helpdesk.healthsafetytech.com"

    def get_private_key(self) -> str:
        if self.jwt_private_key:
            return self.jwt_private_key.replace("\\n", "\n")
        with open(self.jwt_private_key_path) as f:
            return f.read()

    def get_public_key(self) -> str:
        if self.jwt_public_key:
            return self.jwt_public_key.replace("\\n", "\n")
        with open(self.jwt_public_key_path) as f:
            return f.read()

    # Security
    secret_key: str = ""
    bcrypt_rounds: int = 12

    def model_post_init(self, __context) -> None:
        if not self.is_production:
            return

        if len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters in production")

        # O default de cors_origins é localhost. Como o nginx do front não faz
        # proxy para a API, o navegador fala com outro domínio e o CORS é
        # obrigatório: subir com o default deixaria o front bloqueado, e "*"
        # abriria a API para qualquer site. Falhar no boot é melhor do que
        # descobrir isso em produção — mesma escolha feita para a SECRET_KEY.
        origens = self.get_cors_origins()
        if not origens:
            raise ValueError("CORS_ORIGINS está vazio em produção: defina o domínio real do front")
        if any(o == "*" for o in origens):
            raise ValueError("CORS_ORIGINS não pode ser '*' em produção: use o domínio do front")
        locais = [o for o in origens if _host_de(o) in _HOSTS_LOCAIS]
        if locais:
            raise ValueError(
                "CORS_ORIGINS precisa ser definido com o domínio real do front em produção "
                f"(estas origens são locais: {', '.join(locais)})"
            )

        # Mesma classe de falha, outro efeito: FRONTEND_URL monta os links dos
        # e-mails de confirmação e de redefinição de senha. Apontando para
        # localhost em produção, o e-mail sai com um link que não abre para
        # ninguém — e nada no backend reclama.
        if _host_de(self.frontend_url) in _HOSTS_LOCAIS:
            raise ValueError(
                "FRONTEND_URL precisa ser o endereço público do sistema em produção: "
                "os links dos e-mails de confirmação e de senha saem a partir dele"
            )

        # Adotar a confirmação de e-mail sem ter como enviar e-mail é a
        # armadilha que travou login em produção: conta nasce não-verificada e
        # a mensagem de confirmação nunca sai.
        if self.email_verification_enabled and not self.email_is_configured():
            raise ValueError(
                "EMAIL_VERIFICATION_ENABLED=true exige SMTP configurado "
                "(SMTP_USER/SMTP_FROM_EMAIL): sem ele, contas novas ficariam "
                "presas esperando um e-mail que nunca chega"
            )

    # Armazenamento de arquivos (anexos e avatares) em disco.
    # No deploy, este caminho precisa ser um volume — sem isso os arquivos
    # somem a cada redeploy do container.
    upload_dir: str = "/app/uploads"
    # Validade do link temporario devolvido para baixar/exibir um arquivo
    file_url_expires_seconds: int = 3600

    # MinIO — mantido apenas para compatibilidade de configuracao; o
    # armazenamento passou a ser em disco (ver upload_dir)
    minio_endpoint: str = "localhost"
    minio_port: int = 9000
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket_name: str = "helpdesk-attachments"
    minio_use_ssl: bool = False

    # LLM
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_temperature: float = 0.3

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-20241022"

    llm_fallback_enabled: bool = True
    llm_request_timeout_seconds: int = 30

    # Email
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_tls: bool = True
    smtp_ssl: bool = False
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_name: str = "Help Desk Health & Safety"
    smtp_from_email: str = ""
    # Para onde vão as respostas de quem responder um e-mail automático.
    # Vazio = as respostas caem na própria caixa de disparo, que ninguém lê.
    smtp_reply_to: str = ""

    # Endereço público do sistema — usado para montar os links dos e-mails
    frontend_url: str = "http://localhost:5173"

    # Confirmação de e-mail no cadastro
    # A exigência é ADOTADA por esta flag, não deduzida das variáveis de SMTP:
    # a inferência já travou login em produção — SMTP_USER/SMTP_FROM_EMAIL
    # preenchidos (seed do .env.example) ligavam a confirmação sem SMTP
    # funcional, a conta nascia não-verificada e o e-mail nunca saía.
    email_verification_enabled: bool = False
    email_verification_token_hours: int = 24
    password_reset_token_hours: int = 1

    def email_is_configured(self) -> bool:
        """Só dá para exigir confirmação se houver como enviar o e-mail."""
        return bool(self.smtp_from_email or self.smtp_user)

    def requires_email_verification(self) -> bool:
        """
        Confirmação de e-mail só quando adotada de propósito E com SMTP
        presente. Sem a flag, variável de SMTP preenchida não muda nada; sem
        SMTP, ligar a flag sozinha também não — senão o cliente criaria conta
        e ficaria esperando um e-mail que nunca chega.
        """
        return self.email_verification_enabled and self.email_is_configured()

    # ClamAV
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    clamav_timeout_seconds: int = 30

    # Upload
    upload_max_file_size_mb: int = 25
    upload_max_files_per_ticket: int = 10
    upload_allowed_extensions: str = (
        ".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.gif,.txt,.csv,.zip,.rar"
    )

    # SLA
    sla_business_hours_start: str = "08:00"
    sla_business_hours_end: str = "18:00"
    sla_business_days: str = "1,2,3,4,5"
    sla_timezone: str = "America/Sao_Paulo"

    # Encerramento do chamado (RN-005 / RN-006).
    # Os prazos são contados em DIAS ÚTEIS a partir do momento em que o chamado
    # foi resolvido — em dias corridos, quem resolvesse na sexta daria ao cliente
    # praticamente nenhum dia de trabalho para se manifestar.
    ticket_auto_close_business_days: int = 3
    ticket_reopen_business_days: int = 5
    # De quanto em quanto tempo a rotina de fechamento automático roda.
    # 0 desliga a rotina (útil em testes e em execução local).
    ticket_auto_close_interval_seconds: int = 3600

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_default_max_retries: int = 3
    celery_task_soft_time_limit: int = 300
    celery_task_time_limit: int = 600

    # Logging
    log_level: str = "INFO"
    log_dir: str = "./logs"

    # Rate limiting
    rate_limit_login: str = "5/15minutes"

    # Quem pode falar pelos outros: lista de IPs/redes cujo X-Forwarded-For o
    # uvicorn aceita como sendo o IP real de quem chamou. O uvicorn lê esta
    # mesma variável do ambiente por conta própria — por isso o `start.sh` não
    # passa flag nenhuma, para não existirem duas fontes que podem divergir.
    #
    # O default do uvicorn é 127.0.0.1, ou seja, não confia em proxy nenhum.
    # Atrás do proxy do EasyPanel isso faz `get_remote_address` devolver o IP
    # do PRÓPRIO proxy, e o rate limit de login (5/15min) vira um balde único
    # para o sistema inteiro: cinco senhas erradas de qualquer pessoa travam o
    # login de todo mundo.
    #
    # Ligar resolve, MAS só é seguro se a porta do backend não estiver
    # publicada direto na internet — se estiver, qualquer um forja o
    # X-Forwarded-For e pula o rate limit por completo, que é pior do que o
    # balde global. Daí o default conservador: ligar é decisão de quem conhece
    # a topologia do deploy. Ver o aviso em mudanças.md.
    forwarded_allow_ips: str = ""

    @property
    def trusts_proxy_headers(self) -> bool:
        return bool(self.forwarded_allow_ips.strip())

    @property
    def rate_limit_por_ip_do_proxy(self) -> bool:
        """Produção sem proxy autorizado: o rate limit por IP é um balde só."""
        return self.is_production and not self.trusts_proxy_headers

    # As três leituras do ambiente ficam juntas e comparam o valor já
    # normalizado pelo `_normaliza_app_env` — nenhuma delas repete o strip/lower.

    @property
    def is_production(self) -> bool:
        return self.app_env in _NOMES_DE_PRODUCAO

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_testing(self) -> bool:
        return self.app_env == "testing"

    @property
    def allowed_extensions(self) -> list[str]:
        return [ext.strip() for ext in self.upload_allowed_extensions.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
