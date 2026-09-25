"""
Testa o envio de e-mail direto no SMTP, sem subir a aplicacao.

**Avulso, rodado a mao.** Nao e chamado por ninguem, nao entra no boot.

Existe para separar duas falhas que se parecem quando alguem diz "o e-mail de
recuperacao de senha nao chegou": credencial/dominio errados no provedor, ou
defeito no caminho da aplicacao. O script usa `smtplib` da biblioteca padrao
de proposito — nao passa pelo FastAPI-Mail nem pelo `Settings` do app. Se ele
entrega e a aplicacao nao, o problema esta na aplicacao; se ele tambem falha,
nao adianta procurar no codigo.

Essa independencia e a razao de existir do script, e por isso ele NAO chama
`get_settings()`: os dois lados do diagnostico diferencial lendo a mesma fonte
acabariam com o diagnostico. Quem garante que ele enxerga a mesma configuracao
que a aplicacao e `tests/test_testa_smtp.py`, por paridade contra os campos
`smtp_*` do `Settings` — inclusive os PADROES de transporte daqui de baixo.

Le as variaveis SMTP_* do `.env` do backend; se esse arquivo nao existir,
cai para as VARIAVEIS DE AMBIENTE — que e o caso de rodar dentro do
container, onde a configuracao vem do painel do EasyPanel. A origem usada
sai impressa no relatorio. O script **nunca imprime a senha inteira** — o terminal costuma virar print no chat, e
a API key do provedor e a credencial de envio da empresa inteira. Pelo mesmo
motivo o Reply-To sai como CONFIGURADO/(vazio), sem o endereco: para
diagnosticar basta saber se existe.

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
import hashlib
import os
import smtplib
import ssl
import sys
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

PADRAO_ENV = Path(__file__).resolve().parent.parent / ".env"


# Lista branca das variaveis copiadas do AMBIENTE (o caminho de dentro do
# container). Chave lida adiante e ausente daqui vira silenciosamente vazia:
# foi assim que `SMTP_REPLY_TO` passou meses aparecendo como "(vazio)" em
# producao com o valor preenchido no painel. O teste de paridade contra
# `Settings` existe para que isso nao dependa de ninguem lembrar.
_CHAVES = (
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_TLS",
    "SMTP_SSL",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM_NAME",
    "SMTP_FROM_EMAIL",
    "SMTP_REPLY_TO",
)

# Padroes iguais aos do `Settings`: TLS implicito na 465, e nao STARTTLS na
# 587. A escolha e a mitigacao do CVE-2026-55558, nao estilo — um script que
# caisse no STARTTLS por omissao testaria um transporte que a aplicacao nao
# usa, e devolveria "OK" sobre outro caminho.
PADRAO_PORTA = 465
PADRAO_SSL = True
PADRAO_TLS = False


@dataclass(frozen=True)
class Configuracao:
    """A configuracao de envio, ja interpretada.

    Imutavel porque atravessa o relatorio E a mensagem: se alguem a ajustasse
    entre os dois, o relatorio deixaria de descrever o que foi enviado — e o
    relatorio e a unica coisa que sobra depois que o terminal fecha.
    """

    host: str
    porta: int
    usuario: str
    senha: str
    remetente: str
    nome: str
    reply_to: str
    usa_ssl: bool
    usa_tls: bool


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


def le_configuracao(env: dict[str, str]) -> Configuracao:
    """Interpreta o mapa cru de variaveis.

    `SMTP_HOST` nao tem padrao de proposito, e o `Settings` tem: num
    diagnostico, adivinhar o servidor e o pior padrao possivel — testaria um
    provedor que ninguem configurou. A ausencia vira erro no `main`.
    """
    return Configuracao(
        host=env.get("SMTP_HOST", ""),
        porta=int(env.get("SMTP_PORT", "") or PADRAO_PORTA),
        usuario=env.get("SMTP_USER", ""),
        senha=env.get("SMTP_PASSWORD", ""),
        # Em muitos provedores remetente e usuario coincidem; exigir o par
        # completo travaria o diagnostico sem motivo.
        remetente=env.get("SMTP_FROM_EMAIL", "") or env.get("SMTP_USER", ""),
        nome=env.get("SMTP_FROM_NAME", "HelpHS"),
        reply_to=env.get("SMTP_REPLY_TO", ""),
        usa_ssl=_booleano(env.get("SMTP_SSL"), PADRAO_SSL),
        usa_tls=_booleano(env.get("SMTP_TLS"), PADRAO_TLS),
    )


def _booleano(valor: str | None, padrao: bool) -> bool:
    """Nem o painel do EasyPanel normaliza caixa, nem quem digita."""
    if valor is None or not valor.strip():
        return padrao
    return valor.strip().lower() == "true"


def impressao_digital(segredo: str) -> str:
    """Identifica a chave sem revelar caractere nenhum dela.

    Esta funcao devolvia os 6 primeiros e os 4 ultimos caracteres. Para uma API
    key de provedor isso e revelar DEZ caracteres dela -- e o docstring deste
    script diz, com razao, que "o terminal costuma virar print no chat".
    Mascarar pela metade continua sendo vazar, so que menos, e o mais enganoso
    e que a saida PARECE segura.

    O digest resolve o mesmo problema sem o vazamento. O que se quer aqui e
    responder "e a chave que eu penso que e?", e para isso basta um valor que
    seja igual quando a chave for igual: dois segredos iguais dao a mesma
    impressao, diferentes dao impressoes diferentes, e nenhum pedaco do segredo
    aparece.

    Oito hex sao 32 bits -- suficiente para comparar duas rodadas ou conferir
    contra uma impressao anotada, e curto o bastante para que o proprio digest
    nao sirva de alvo: ha colisoes demais para que ele identifique um valor
    unico offline. O tamanho continua saindo porque distingue "vazia" de
    "preenchida errada", que e o engano mais comum.
    """
    if not segredo:
        return "(vazia)"
    digest = hashlib.sha256(segredo.encode("utf-8")).hexdigest()[:8]
    return f"impressao {digest} ({len(segredo)} chars)"


def linhas_do_relatorio(cfg: Configuracao, destino: str, origem: str) -> list[str]:
    """O que sai no terminal antes de qualquer conexao.

    O Reply-To sai como CONFIGURADO/(vazio) e nao como endereco: distinguir os
    dois estados e o unico trabalho desta linha, e foi exatamente o que falhou
    em producao. O destino sai inteiro porque quem rodou o comando acabou de
    digita-lo.
    """
    return [
        f"config de : {origem}",
        f"host      : {cfg.host}:{cfg.porta} (ssl={cfg.usa_ssl}, starttls={cfg.usa_tls})",
        f"usuario   : {cfg.usuario or '(sem autenticacao)'}",
        f"senha     : {impressao_digital(cfg.senha)}",
        f"remetente : {cfg.nome} <{cfg.remetente}>",
        f"reply-to  : {'CONFIGURADO' if cfg.reply_to else '(vazio)'}",
        f"destino   : {destino}",
    ]


def monta_mensagem(cfg: Configuracao, destino: str) -> EmailMessage:
    """A mensagem de teste.

    O `Reply-To` so entra quando ha valor: cabecalho vazio e cabecalho
    malformado, e ha provedor que recusa a mensagem por causa dele.
    """
    msg = EmailMessage()
    msg["Subject"] = "[HelpHS] Teste de envio SMTP"
    msg["From"] = f"{cfg.nome} <{cfg.remetente}>"
    msg["To"] = destino
    if cfg.reply_to:
        msg["Reply-To"] = cfg.reply_to
    msg.set_content(
        "Teste de configuracao de SMTP do HelpHS.\n\n"
        "Se esta mensagem chegou, o provedor aceita a credencial e o dominio\n"
        "do remetente esta verificado. Os e-mails de confirmacao de cadastro e\n"
        "de redefinicao de senha saem por este mesmo caminho.\n\n"
        "-- Help Desk Health & Safety\n"
    )
    return msg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destino", help="endereco que vai receber o teste")
    parser.add_argument("--env", type=Path, default=None, help="arquivo .env a ler")
    args = parser.parse_args()

    # Sem --env: tenta o .env do backend e, se nao existir, cai para as
    # variaveis de ambiente (o caso de rodar dentro do container).
    env, origem = ler_env(args.env or PADRAO_ENV, exigido=args.env is not None)
    cfg = le_configuracao(env)

    for linha in linhas_do_relatorio(cfg, args.destino, origem):
        print(linha)
    print()

    if not cfg.host:
        sys.exit("ERRO: SMTP_HOST vazio.")
    if not cfg.remetente:
        sys.exit("ERRO: sem SMTP_FROM_EMAIL nem SMTP_USER — nao ha remetente.")
    if "CHANGE_ME" in cfg.senha:
        sys.exit("ERRO: SMTP_PASSWORD ainda esta com o valor de exemplo.")

    msg = monta_mensagem(cfg, args.destino)

    contexto = ssl.create_default_context()
    try:
        if cfg.usa_ssl:
            servidor = smtplib.SMTP_SSL(cfg.host, cfg.porta, timeout=30, context=contexto)
        else:
            servidor = smtplib.SMTP(cfg.host, cfg.porta, timeout=30)
        with servidor as smtp:
            smtp.ehlo()
            if cfg.usa_tls and not cfg.usa_ssl:
                smtp.starttls(context=contexto)
                smtp.ehlo()
            if cfg.usuario:
                smtp.login(cfg.usuario, cfg.senha)
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
