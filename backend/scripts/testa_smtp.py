"""
Testa o envio de e-mail direto no SMTP, sem subir a aplicacao.

**Avulso, rodado a mao.** Nao e chamado por ninguem, nao entra no boot.

Existe para separar duas falhas que se parecem quando alguem diz "o e-mail de
recuperacao de senha nao chegou": credencial/dominio errados no provedor, ou
defeito no caminho da aplicacao. O script usa `smtplib` da biblioteca padrao
de proposito — nao passa pelo FastAPI-Mail nem pelo `Settings` do app. Se ele
entrega e a aplicacao nao, o problema esta na aplicacao; se ele tambem falha,
nao adianta procurar no codigo.

Le as variaveis SMTP_* do `.env` do backend; se esse arquivo nao existir,
cai para as VARIAVEIS DE AMBIENTE — que e o caso de rodar dentro do
container, onde a configuracao vem do painel do EasyPanel. A origem usada
sai impressa no relatorio. O script **nunca imprime a senha inteira** — o terminal costuma virar print no chat, e
a API key do provedor e a credencial de envio da empresa inteira.

Uso:

    python -m scripts.testa_smtp destino@exemplo.com
    python -m scripts.testa_smtp destino@exemplo.com --env ../.env.staging

Dentro do container do EasyPanel, sem `.env`, as variaveis do painel sao
usadas automaticamente.

Sair com codigo 0 significa apenas que o servidor ACEITOU a mensagem para
entrega. Nao prova que ela chegou na caixa: quem responde isso e o painel do
provedor (no Resend, a aba Emails, com delivered/bounced/complained).
"""

from __future__ import annotations

import argparse
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path

PADRAO_ENV = Path(__file__).resolve().parent.parent / ".env"


_CHAVES = (
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_TLS",
    "SMTP_SSL",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM_NAME",
    "SMTP_FROM_EMAIL",
)


def ler_env(caminho: Path, exigido: bool) -> tuple[dict[str, str], str]:
    """Le a configuracao de SMTP do arquivo, ou do AMBIENTE quando nao ha arquivo.

    O fallback existe para o caso que mais importa: rodar isto DENTRO do
    container, onde as variaveis vem do painel do EasyPanel e nao ha `.env`
    nenhum. Sem ele o script morria com "arquivo nao encontrado" justamente no
    ambiente que a gente precisa diagnosticar.

    Arquivo pedido explicitamente com `--env` continua sendo exigido: ali o
    silencio seria pior, porque a pessoa nomeou o arquivo e mereceria saber que
    ele nao existe em vez de receber a configuracao de outro lugar.

    Devolve tambem a ORIGEM, que vai impressa no relatorio: diagnosticar sem
    saber de onde veio a configuracao ja custou tempo neste projeto.
    """
    if caminho.is_file():
        valores: dict[str, str] = {}
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, _, valor = linha.partition("=")
            valores[chave.strip()] = valor.strip()
        return valores, str(caminho)

    if exigido:
        sys.exit(f"ERRO: arquivo de ambiente nao encontrado: {caminho}")

    do_ambiente = {c: os.environ[c] for c in _CHAVES if c in os.environ}
    if not do_ambiente:
        sys.exit(
            f"ERRO: nao achei {caminho} nem variaveis SMTP_* no ambiente. "
            "Rode de dentro do container, ou aponte --env para um arquivo."
        )
    return do_ambiente, "variaveis de ambiente"


def mascarar(segredo: str) -> str:
    """O suficiente para conferir que e a chave certa, sem revelar a chave."""
    if not segredo:
        return "(vazia)"
    if len(segredo) <= 12:
        return f"({len(segredo)} chars)"
    return f"{segredo[:6]}…{segredo[-4:]} ({len(segredo)} chars)"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destino", help="endereco que vai receber o teste")
    parser.add_argument("--env", type=Path, default=None, help="arquivo .env a ler")
    args = parser.parse_args()

    # Sem --env: tenta o .env do backend e, se nao existir, cai para as
    # variaveis de ambiente (o caso de rodar dentro do container).
    env, origem = ler_env(args.env or PADRAO_ENV, exigido=args.env is not None)
    host = env.get("SMTP_HOST", "")
    porta = int(env.get("SMTP_PORT", "587") or 587)
    usuario = env.get("SMTP_USER", "")
    senha = env.get("SMTP_PASSWORD", "")
    remetente = env.get("SMTP_FROM_EMAIL", "") or usuario
    nome = env.get("SMTP_FROM_NAME", "HelpHS")
    reply_to = env.get("SMTP_REPLY_TO", "")
    usa_ssl = env.get("SMTP_SSL", "false").lower() == "true"
    usa_tls = env.get("SMTP_TLS", "true").lower() == "true"

    print(f"config de : {origem}")
    print(f"host      : {host}:{porta} (ssl={usa_ssl}, starttls={usa_tls})")
    print(f"usuario   : {usuario or '(sem autenticacao)'}")
    print(f"senha     : {mascarar(senha)}")
    print(f"remetente : {nome} <{remetente}>")
    print(f"reply-to  : {reply_to or '(vazio)'}")
    print(f"destino   : {args.destino}\n")

    if not host:
        sys.exit("ERRO: SMTP_HOST vazio.")
    if not remetente:
        sys.exit("ERRO: sem SMTP_FROM_EMAIL nem SMTP_USER — nao ha remetente.")
    if "CHANGE_ME" in senha:
        sys.exit("ERRO: SMTP_PASSWORD ainda esta com o valor de exemplo.")

    msg = EmailMessage()
    msg["Subject"] = "[HelpHS] Teste de envio SMTP"
    msg["From"] = f"{nome} <{remetente}>"
    msg["To"] = args.destino
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(
        "Teste de configuracao de SMTP do HelpHS.\n\n"
        "Se esta mensagem chegou, o provedor aceita a credencial e o dominio\n"
        "do remetente esta verificado. Os e-mails de confirmacao de cadastro e\n"
        "de redefinicao de senha saem por este mesmo caminho.\n\n"
        "-- Help Desk Health & Safety\n"
    )

    contexto = ssl.create_default_context()
    try:
        if usa_ssl:
            servidor = smtplib.SMTP_SSL(host, porta, timeout=30, context=contexto)
        else:
            servidor = smtplib.SMTP(host, porta, timeout=30)
        with servidor as smtp:
            smtp.ehlo()
            if usa_tls and not usa_ssl:
                smtp.starttls(context=contexto)
                smtp.ehlo()
            if usuario:
                smtp.login(usuario, senha)
            recusados = smtp.send_message(msg)
        if recusados:
            sys.exit(f"FALHA parcial — destinatarios recusados: {recusados}")
        print("OK — servidor aceitou a mensagem para entrega.")
        print("Confirme a entrega real no painel do provedor.")
    except smtplib.SMTPAuthenticationError as exc:
        sys.exit(f"FALHA na autenticacao: {exc}\n-> credencial errada ou sem permissao de envio.")
    except smtplib.SMTPSenderRefused as exc:
        sys.exit(
            f"FALHA — remetente recusado: {exc}\n-> dominio do remetente nao verificado no provedor."
        )
    except smtplib.SMTPRecipientsRefused as exc:
        sys.exit(f"FALHA — destinatario recusado: {exc}")
    except OSError as exc:
        sys.exit(f"FALHA de conexao: {exc}\n-> host/porta errados ou saida SMTP bloqueada na rede.")


if __name__ == "__main__":
    main()
