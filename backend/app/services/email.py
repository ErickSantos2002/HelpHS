"""
Email notification service via FastAPI-Mail.

Provides a thin async wrapper used by the notification service.
The FastMail instance is created lazily so that missing SMTP config
in development does not crash startup.
"""

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from loguru import logger

from app.core.config import Settings

# Module-level cache — one instance per Settings snapshot
_mail_instance: FastMail | None = None
_mail_settings_hash: int | None = None


def _get_mail_client(settings: Settings) -> FastMail:
    global _mail_instance, _mail_settings_hash

    h = hash((settings.smtp_host, settings.smtp_port, settings.smtp_user))
    if _mail_instance is None or _mail_settings_hash != h:
        config = ConnectionConfig(
            MAIL_USERNAME=settings.smtp_user,
            MAIL_PASSWORD=settings.smtp_password,
            MAIL_FROM=settings.smtp_from_email or settings.smtp_user,
            MAIL_FROM_NAME=settings.smtp_from_name,
            MAIL_PORT=settings.smtp_port,
            MAIL_SERVER=settings.smtp_host,
            MAIL_STARTTLS=settings.smtp_tls,
            MAIL_SSL_TLS=settings.smtp_ssl,
            # Verificar o certificado do servidor é o que impede entregar
            # usuário e senha do SMTP a quem conseguir responder no endereço —
            # e a senha do SMTP é a credencial de envio da empresa inteira.
            # Sem chave de configuração para desligar: uma opção "não verifique
            # o certificado" é o tipo de coisa que alguém liga para destravar um
            # relay interno e nunca mais desliga. Se um dia houver um servidor
            # de certificado próprio, isso é decisão para tomar na hora.
            VALIDATE_CERTS=True,
            USE_CREDENTIALS=bool(settings.smtp_user),
        )
        _mail_instance = FastMail(config)
        _mail_settings_hash = h

    return _mail_instance


async def send_email(
    to_email: str,
    subject: str,
    body: str,
    settings: Settings,
) -> bool:
    """
    Send a plain-text email notification.

    Returns True on success, False if delivery failed (error is logged but
    not re-raised so the caller is never blocked by email failures).
    """
    if not settings.smtp_from_email and not settings.smtp_user:
        logger.debug(f"SMTP not configured — skipping email to {to_email}")
        return False

    try:
        mail = _get_mail_client(settings)
        message = MessageSchema(
            subject=subject,
            recipients=[to_email],
            body=body,
            subtype=MessageType.plain,
            # SMTP_REPLY_TO é opcional e nasce vazio. O MessageSchema recusa
            # None neste campo, e a montagem morreria antes de tentar entregar.
            reply_to=[settings.smtp_reply_to] if settings.smtp_reply_to else [],
        )
        await mail.send_message(message)
        logger.info(f"Email sent to {to_email}: {subject}")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to send email to {to_email}: {exc}")
        return False
