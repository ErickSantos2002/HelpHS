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


async def send_account_exists_email(to_email: str, settings: Settings) -> bool:
    """Avisa que já existe conta com este endereço, sem dizer isso a mais ninguém.

    É o que sustenta a resposta neutra do cadastro. Sem esta mensagem, quem
    esqueceu que já tinha conta recebe um 201, vai para o login, tenta a senha
    que acabou de escolher e não entra — sem nada explicando por quê.

    O texto NÃO revela nome, data de criação nem qualquer outro dado: quem
    recebe já sabe que a conta é dele, e quem não é dono não deveria receber
    nada. É o mesmo cuidado do "esqueci minha senha".
    """
    base = settings.frontend_url.rstrip("/")

    corpo = (
        "Olá!\n\n"
        "Alguém — provavelmente você — tentou criar uma conta no HelpHS com este "
        "endereço de e-mail.\n\n"
        "Você já tem uma conta aqui, então não criamos outra. Para entrar, use:\n\n"
        f"{base}/login\n\n"
        'Se você não lembra a senha, use a opção "Esqueci minha senha" na tela de '
        "acesso.\n\n"
        "Se não foi você, pode ignorar esta mensagem: nada mudou na sua conta e "
        "ninguém teve acesso a ela.\n\n"
        "Equipe Health & Safety"
    )

    return await send_email(
        to_email=to_email,
        subject="[HelpHS] Você já tem uma conta com este e-mail",
        body=corpo,
        settings=settings,
    )
