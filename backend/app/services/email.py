"""
Email notification service via FastAPI-Mail.

Provides a thin async wrapper used by the notification service.
The FastMail instance is created lazily so that missing SMTP config
in development does not crash startup.
"""

from fastapi_mail import (
    ConnectionConfig,
    FastMail,
    MessageSchema,
    MessageType,
    MultipartSubtypeEnum,
)
from loguru import logger

from app.core.config import Settings
from app.services.email_layout import CID_LOGO, LOGO_EMAIL


def _resumo_do_erro(exc: BaseException) -> str:
    """A CLASSE do erro e, quando houver, o código numérico do servidor.

    **Nunca `str(exc)`.** Medido no aiosmtplib 3.0.2, em 25/09/2026:

        SMTPSenderRefused      -> o str() carrega o REMETENTE
        SMTPRecipientRefused   -> carrega o DESTINATÁRIO
        SMTPRecipientsRefused  -> carrega o destinatário, dentro da lista

    Ou seja: logar `{exc}` põe endereço de cliente no log sem ninguém ter
    escrito `{to_email}` em lugar nenhum. É o vazamento que não aparece na
    revisão, porque a linha de código parece limpa.

    O código numérico FICA, e é o que sobra de diagnóstico: separa 535
    (credencial recusada) de 550 (domínio não verificado) e de 421 (tente mais
    tarde). É inteiro do protocolo SMTP, não texto que o servidor escolhe.

    A mensagem do servidor sai inteira. Hoje ela é inócua na maioria dos casos,
    mas é conteúdo variável de terceiro — e o log não é lugar para apostar nisso.
    """
    codigo = getattr(exc, "code", None)
    nome = type(exc).__name__
    return f"{nome} (code {codigo})" if isinstance(codigo, int) else nome


def _anexo_da_logo() -> list[dict]:
    """A logo da faixa, como parte MIME `inline` referenciada por `cid:`.

    Só acompanha e-mail COM html — em texto puro ela não seria vista e os 75 KB
    viajariam por nada.

    A árvore que isto produz é `multipart/related` envolvendo o
    `multipart/alternative`, com a imagem IRMÃ dele. Isso importa: dentro do
    `alternative`, a RFC 2046 permite ao cliente escolher a imagem e descartar o
    HTML, e o leitor receberia só a logo. Quem monta assim é o
    `attach_alternative` da `fastapi_mail` — comportamento de terceiro, medido em
    `tests/test_email_anexo.py` e não deduzido da documentação.

    Asset ausente devolve lista vazia em vez de levantar: o e-mail sai sem a
    imagem, e a faixa continua dizendo "Help Desk Health & Safety" em texto.
    Derrubar o envio porque falta um arquivo decorativo seria trocar um e-mail
    feio por nenhum e-mail.
    """
    if not LOGO_EMAIL.is_file():
        logger.warning(f"logo do e-mail ausente em {LOGO_EMAIL}: a mensagem sai sem imagem")
        return []

    return [
        {
            "file": str(LOGO_EMAIL),
            "mime_type": "image",
            "mime_subtype": "png",
            "headers": {
                # Os `<>` são do cabeçalho; no `src` o `cid:` vem sem eles.
                "Content-ID": f"<{CID_LOGO}>",
                "Content-Disposition": f'inline; filename="{LOGO_EMAIL.name}"',
            },
        }
    ]


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
    html: str | None = None,
    contexto: str = "email",
) -> bool:
    """Envia o e-mail; com `html`, manda texto e HTML na mesma mensagem.

    A parte de texto NÃO é rascunho da de HTML: filtro de spam penaliza HTML sem
    alternativa, e gateway corporativo às vezes entrega só ela. Quem monta as
    duas é o `email_layout`, a partir da mesma `Mensagem`, para não divergirem.

    Sem `html`, sai só o texto — que é o caminho de quem ainda não migrou.

    Devolve True quando o servidor aceitou. Falha é registrada e NÃO
    re-levantada: quem chamou já fez o trabalho, e o e-mail é o acessório.

    ``contexto`` é o que vai para o LOG no lugar do destinatário.
    -----------------------------------------------------------
    Até 25/09/2026 estas três linhas registravam `{to_email}` e `{subject}`.
    Com SMTP desligado nada saía — a função retorna antes —, então ligar o envio
    ligava junto um vazamento de dado pessoal no log de produção: endereço do
    cliente e, no aviso de chamado novo, o TÍTULO do chamado dentro do assunto.

    Quem chama diz o que a linha deve identificar, e a regra é que seja
    identificador INTERNO ou nome de evento: `notification <uuid>` para o
    sininho, `account email (password reset)` para os de conta. Nunca endereço.

    Não há hash de e-mail aqui de propósito. A correlação que faltaria já existe
    por outro caminho: o `request_id` de `core/contexto.py` é `ContextVar`, e
    `asyncio.create_task` copia o contexto — então a task do envio herda o id da
    requisição que a originou, e ele entra no `extra` de toda linha.
    """
    if not settings.smtp_from_email and not settings.smtp_user:
        logger.debug(f"SMTP not configured — {contexto} skipped")
        return False

    try:
        mail = _get_mail_client(settings)
        # `body` vira text/plain e `alternative_body` vira text/html, nessa
        # ordem dentro do multipart/alternative — conferido na árvore MIME que a
        # biblioteca monta, não deduzido da documentação.
        duas_partes = (
            {
                "alternative_body": html,
                "multipart_subtype": MultipartSubtypeEnum.alternative,
                "attachments": _anexo_da_logo(),
            }
            if html
            else {}
        )
        message = MessageSchema(
            subject=subject,
            recipients=[to_email],
            body=body,
            subtype=MessageType.plain,
            # SMTP_REPLY_TO é opcional e nasce vazio. O MessageSchema recusa
            # None neste campo, e a montagem morreria antes de tentar entregar.
            reply_to=[settings.smtp_reply_to] if settings.smtp_reply_to else [],
            **duas_partes,
        )
        await mail.send_message(message)
        logger.info(f"Delivery accepted by SMTP server: {contexto}")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"SMTP delivery failed for {contexto}: {_resumo_do_erro(exc)}")
        return False
