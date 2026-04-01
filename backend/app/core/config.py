from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8000"]

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
    jwt_access_token_expires_minutes: int = 15
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

    # MinIO
    minio_endpoint: str = "localhost"
    minio_port: int = 9000
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket_name: str = "helpdesk-attachments"
    minio_use_ssl: bool = False

    # LLM
    llm_primary_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_max_tokens: int = 1024
    openai_temperature: float = 0.3

    llm_fallback_provider: str = "anthropic"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-20241022"
    anthropic_max_tokens: int = 1024

    llm_fallback_enabled: bool = True
    llm_max_retries: int = 2
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

    # ClamAV
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    clamav_timeout_seconds: int = 30
    clamav_max_file_size_mb: int = 25

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
    rate_limit_default: str = "100/15minutes"
    rate_limit_login: str = "5/15minutes"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def allowed_extensions(self) -> list[str]:
        return [ext.strip() for ext in self.upload_allowed_extensions.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
