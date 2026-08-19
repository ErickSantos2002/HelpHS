"""
Textos dos e-mails de conta: confirmação de cadastro e redefinição de senha.

Ficam separados do envio para que o conteúdo possa ser lido e revisado sem
abrir a mecânica de SMTP.
"""

from urllib.parse import quote

from app.core.config import Settings
from app.services.email import send_email


def _link(settings: Settings, caminho: str, token: str) -> str:
    base = settings.frontend_url.rstrip("/")
    return f"{base}/{caminho}?token={quote(token)}"


async def send_verification_email(to_email: str, name: str, token: str, settings: Settings) -> bool:
    link = _link(settings, "confirmar-email", token)
    horas = settings.email_verification_token_hours

    corpo = (
        f"Olá, {name}!\n\n"
        "Recebemos o seu cadastro no HelpHS, o sistema de chamados da Health & Safety.\n\n"
        "Para ativar a sua conta, confirme o seu e-mail acessando o endereço abaixo:\n\n"
        f"{link}\n\n"
        f"O link vale por {horas} horas.\n\n"
        "Se não foi você quem se cadastrou, ignore esta mensagem — nenhuma conta será "
        "ativada sem essa confirmação.\n\n"
        "Equipe Health & Safety"
    )

    return await send_email(
        to_email=to_email,
        subject="[HelpHS] Confirme seu e-mail para ativar a conta",
        body=corpo,
        settings=settings,
    )


async def send_password_reset_email(
    to_email: str, name: str, token: str, settings: Settings
) -> bool:
    link = _link(settings, "redefinir-senha", token)
    horas = settings.password_reset_token_hours

    corpo = (
        f"Olá, {name}!\n\n"
        "Recebemos um pedido para redefinir a senha da sua conta no HelpHS.\n\n"
        "Para escolher uma nova senha, acesse:\n\n"
        f"{link}\n\n"
        f"O link vale por {horas} hora(s) e só pode ser usado uma vez.\n\n"
        "Se não foi você quem pediu, ignore esta mensagem: sua senha atual continua "
        "valendo e nada muda na sua conta.\n\n"
        "Equipe Health & Safety"
    )

    return await send_email(
        to_email=to_email,
        subject="[HelpHS] Redefinição de senha",
        body=corpo,
        settings=settings,
    )
