"""
Os e-mails de conta: confirmação de cadastro, redefinição de senha e o aviso de
conta já existente.

Ficam separados do envio para que o conteúdo possa ser lido e revisado sem abrir
a mecânica de SMTP. Desde 04/09/2026 cada um monta uma `Mensagem`, e o
`email_layout` a renderiza em texto e em HTML a partir da mesma fonte — a parte
de texto não é rascunho da de HTML: é o que vários gateways corporativos
entregam, e o que filtro de spam procura.

Estes três continuam indo para TODO MUNDO, inclusive técnico e admin. São a
autenticação e a troca de senha, e o filtro por papel das notificações não os
alcança.
"""

from urllib.parse import quote

from app.core.config import Settings
from app.services.email import send_email
from app.services.email_layout import Mensagem, em_html, em_texto


def _link(settings: Settings, caminho: str, token: str) -> str:
    base = settings.frontend_url.rstrip("/")
    return f"{base}/{caminho}?token={quote(token)}"


async def _envia(to_email: str, assunto: str, conteudo: Mensagem, settings: Settings) -> bool:
    return await send_email(
        to_email=to_email,
        subject=assunto,
        body=em_texto(conteudo),
        html=em_html(conteudo),
        settings=settings,
    )


async def send_verification_email(to_email: str, name: str, token: str, settings: Settings) -> bool:
    link = _link(settings, "confirmar-email", token)
    horas = settings.email_verification_token_hours

    conteudo = Mensagem(
        rotulo="confirmação de conta",
        titulo="Confirme seu e-mail",
        saudacao=f"Olá, {name}!",
        paragrafos=(
            "Recebemos o seu cadastro no HelpHS, o sistema de chamados da Health & Safety.",
            "Para ativar a sua conta, confirme o seu e-mail:",
        ),
        acao=("Confirmar meu e-mail", link),
        apoio=(f"O link vale por {horas} horas.",),
        ressalva=(
            "Se não foi você quem se cadastrou, ignore esta mensagem — nenhuma conta "
            "será ativada sem essa confirmação."
        ),
    )

    return await _envia(
        to_email,
        "[HelpHS] Confirme seu e-mail para ativar a conta",
        conteudo,
        settings,
    )


async def send_password_reset_email(
    to_email: str, name: str, token: str, settings: Settings
) -> bool:
    link = _link(settings, "redefinir-senha", token)
    horas = settings.password_reset_token_hours

    conteudo = Mensagem(
        rotulo="redefinição de senha",
        titulo="Redefinição de senha",
        saudacao=f"Olá, {name}!",
        paragrafos=(
            "Recebemos um pedido para redefinir a senha da sua conta no HelpHS.",
            "Para escolher uma nova senha, use o botão abaixo:",
        ),
        acao=("Escolher nova senha", link),
        apoio=(f"O link vale por {horas} hora(s) e só pode ser usado uma vez.",),
        ressalva=(
            "Se não foi você quem pediu, ignore esta mensagem: sua senha atual continua "
            "valendo e nada muda na sua conta."
        ),
    )

    return await _envia(to_email, "[HelpHS] Redefinição de senha", conteudo, settings)


async def send_account_exists_email(to_email: str, settings: Settings) -> bool:
    """Avisa que já existe conta com este endereço, sem dizer isso a mais ninguém.

    É o que sustenta a resposta neutra do cadastro. Sem esta mensagem, quem
    esqueceu que já tinha conta recebe um 201, vai para o login, tenta a senha
    que acabou de escolher e não entra — sem nada explicando por quê.

    O texto NÃO revela nome, data de criação nem qualquer outro dado: quem
    recebe já sabe que a conta é dele, e quem não é dono não deveria receber
    nada. É o mesmo cuidado do "esqueci minha senha" — e por isso, ao contrário
    dos outros dois, esta mensagem não cumprimenta pelo nome.
    """
    base = settings.frontend_url.rstrip("/")

    conteudo = Mensagem(
        rotulo="acesso à sua conta",
        titulo="Você já tem uma conta",
        saudacao="Olá!",
        paragrafos=(
            "Alguém — provavelmente você — tentou criar uma conta no HelpHS com este "
            "endereço de e-mail.",
            "Você já tem uma conta aqui, então não criamos outra. Para entrar:",
        ),
        acao=("Entrar no HelpHS", f"{base}/login"),
        apoio=(
            "Se você não lembra a senha, use a opção “Esqueci minha senha” na tela de "
            f"acesso: {base}/esqueci-senha",
        ),
        ressalva=(
            "Se não foi você, pode ignorar esta mensagem: nada mudou na sua conta e "
            "ninguém teve acesso a ela."
        ),
    )

    return await _envia(
        to_email,
        "[HelpHS] Você já tem uma conta com este e-mail",
        conteudo,
        settings,
    )
