"""
Manda as amostras dos e-mails do HelpHS para os endereços que você passar.

**Avulso, rodado a mão.** Não é chamado por ninguém, não entra no boot, não
entra no CI. Não toca banco, não toca fila, não cria notificação: monta as
`Mensagem` direto e chama o `send_email`.

Por que ele NÃO imita o testa_smtp.py no ponto principal
--------------------------------------------------------
O `testa_smtp.py` usa `smtplib` da biblioteca padrão **de propósito**, para
separar "credencial errada" de "defeito na aplicação". Este script faz o
contrário, e a diferença é o motivo dele existir: quem monta o MIME é a
`fastapi-mail`, e é justamente a montagem que está sob suspeita.

Sabemos que ela declara `Content-Transfer-Encoding: base64` nos contêineres
`multipart`, o que a RFC 2045 §6.4 não permite. Na prática os clientes ignoram.
Montar a mensagem aqui com a biblioteca padrão produziria um MIME correto e o
teste passaria sem provar nada — a caixa receberia algo que a produção não
manda.

O que olhar em cada cliente
---------------------------
A ordem importa: o primeiro é o mais implacável, e o que falhar nele
provavelmente falha em vários.

1. **Outlook desktop clássico** (motor do Word). Botão azul e retangular, ou
   virou texto sublinhado? Largura estourou? Acento saiu certo? Espaçamento
   inflado?
2. **Novo Outlook / Outlook Web.** Inverte cor sozinho no tema escuro — a faixa
   azul e o botão sobreviveram?
3. **Gmail web.** Aparece "[Mensagem cortada]"? (não deveria: ~5 KB)
4. **Gmail app** (iOS/Android). Inversão forçada; com conta não-Google ele
   descarta o `<head>` inteiro, então o que depende da media query cai.
5. **Apple Mail**, se houver.

**E em todos: o e-mail apareceu como página, ou como código-fonte?** Se apareceu
como código, o `Content-Transfer-Encoding` deixou de ser risco teórico e virou
defeito com evidência — anote em qual cliente.

Uso:

    python -m scripts.envia_amostras_email eu@empresa.com
    python -m scripts.envia_amostras_email eu@empresa.com outro@gmail.com
    python -m scripts.envia_amostras_email eu@empresa.com --so confirmacao,chamado
    python -m scripts.envia_amostras_email eu@empresa.com --env .env.local

Lê SMTP_* do `.env` do backend, ou das variáveis de ambiente quando não houver
arquivo. **Recusa rodar com APP_ENV=production**: as amostras têm texto de teste
e não devem sair pelo remetente de produção.

O nome do arquivo importa. Este exemplo já sugeriu `../.env.dev`, e esse nome
**não era pego pelo .gitignore** — a credencial de envio entrava no `git status`
como arquivo novo, esperando alguém dar `git add .`. Hoje o `.gitignore` cobre
`backend/.env.*` (com exceção do `.env.example`), mas prefira `.env.local`:
funciona nas duas regras e é o nome que o resto do projeto já usa.

Rodar numa worktree é o caso em que a variável de ambiente ganha do arquivo:
worktree não carrega arquivo ignorado, então não há `backend/.env` aqui, e
exportar as SMTP_* só na janela do terminal não deixa credencial em disco.

Nunca imprime a senha inteira — o terminal costuma virar print no chat, e a
credencial é a da empresa.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import Settings  # noqa: E402
from app.services.email import send_email  # noqa: E402
from app.services.email_layout import Mensagem, em_html, em_texto  # noqa: E402

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
    "SMTP_REPLY_TO",
    "FRONTEND_URL",
)

_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.AMOSTRA.naoUseIsto"


def ler_env(caminho: Path, exigido: bool) -> tuple[dict[str, str], str]:
    """Lê a configuração do arquivo, ou do AMBIENTE quando não houver arquivo.

    Mesma regra do `testa_smtp.py`: arquivo pedido com `--env` continua sendo
    exigido, porque quem o nomeou merece saber que ele não existe em vez de
    receber a configuração de outro lugar.
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
            "Aponte --env para um arquivo de desenvolvimento."
        )
    return do_ambiente, "variaveis de ambiente"


def mascarar(segredo: str) -> str:
    """O suficiente para conferir que e a chave certa, sem revelar a chave."""
    if not segredo:
        return "(vazia)"
    if len(segredo) <= 12:
        return f"({len(segredo)} chars)"
    return f"{segredo[:6]}…{segredo[-4:]} ({len(segredo)} chars)"


def _amostras(base: str) -> dict[str, tuple[str, Mensagem]]:
    """As cinco formas distintas que o layout produz.

    Cinco e não quinze: o que muda de e-mail para e-mail e o texto, e o que
    precisa ser olhado em cliente e a FORMA. Estas cinco cobrem todas as formas —
    com botao e sem, com cartao de dado e sem, com ressalva e sem.
    """
    return {
        "confirmacao": (
            "[HelpHS] Confirme seu e-mail para ativar a conta",
            Mensagem(
                rotulo="confirmação de conta",
                titulo="Confirme seu e-mail",
                saudacao="Olá, Welton!",
                paragrafos=(
                    "Recebemos o seu cadastro no HelpHS, o sistema de chamados da "
                    "Health & Safety.",
                    "Para ativar a sua conta, confirme o seu e-mail:",
                ),
                acao=("Confirmar meu e-mail", f"{base}/confirmar-email?token={_TOKEN}"),
                apoio=("O link vale por 24 horas.",),
                ressalva=(
                    "Se não foi você quem se cadastrou, ignore esta mensagem — nenhuma "
                    "conta será ativada sem essa confirmação."
                ),
            ),
        ),
        "senha": (
            "[HelpHS] Redefinição de senha",
            Mensagem(
                rotulo="redefinição de senha",
                titulo="Redefinição de senha",
                saudacao="Olá, Welton!",
                paragrafos=(
                    "Recebemos um pedido para redefinir a senha da sua conta no HelpHS.",
                    "Para escolher uma nova senha, use o botão abaixo:",
                ),
                acao=("Escolher nova senha", f"{base}/redefinir-senha?token={_TOKEN}"),
                apoio=("O link vale por 1 hora(s) e só pode ser usado uma vez.",),
                ressalva=(
                    "Se não foi você quem pediu, ignore esta mensagem: sua senha atual "
                    "continua valendo e nada muda na sua conta."
                ),
            ),
        ),
        "conta_existente": (
            "[HelpHS] Você já tem uma conta com este e-mail",
            Mensagem(
                rotulo="acesso à sua conta",
                titulo="Você já tem uma conta",
                saudacao="Olá!",
                paragrafos=(
                    "Alguém — provavelmente você — tentou criar uma conta no HelpHS "
                    "com este endereço de e-mail.",
                    "Você já tem uma conta aqui, então não criamos outra. Para entrar:",
                ),
                acao=("Entrar no HelpHS", f"{base}/login"),
                apoio=(
                    "Se você não lembra a senha, use a opção “Esqueci minha senha” na "
                    f"tela de acesso: {base}/esqueci-senha",
                ),
                ressalva=(
                    "Se não foi você, pode ignorar esta mensagem: nada mudou na sua "
                    "conta e ninguém teve acesso a ela."
                ),
            ),
        ),
        "chamado": (
            "[HelpHS] Chamado resolvido · HS-2026-0042",
            Mensagem(
                rotulo="seu chamado",
                titulo="Chamado resolvido",
                saudacao="Olá, Welton.",
                paragrafos=("O chamado HS-2026-0042 foi marcado como resolvido.",),
                acao=("Ver o chamado", f"{base}/tickets/64f2664d-a94f-44fb-9c50-b5dfa30f5a9d"),
                dados=(("protocolo", "HS-2026-0042"),),
            ),
        ),
        "sem_botao": (
            "[HelpHS] Aviso do sistema",
            Mensagem(
                rotulo="aviso do sistema",
                titulo="Aviso do sistema",
                saudacao="Olá, Welton.",
                paragrafos=(
                    "Esta amostra não tem botão nem cartão de dado — é a forma mais "
                    "simples que o layout produz, e serve para ver se a moldura se "
                    "sustenta sozinha.",
                ),
            ),
        ),
    }


async def _dispara(destinos: list[str], quais: list[str], settings: Settings) -> int:
    amostras = _amostras(settings.frontend_url.rstrip("/"))
    falhas = 0

    for destino in destinos:
        print(f"\n── {destino} " + "─" * max(0, 52 - len(destino)))
        for nome in quais:
            assunto, conteudo = amostras[nome]
            ok = await send_email(
                to_email=destino,
                subject=assunto,
                body=em_texto(conteudo),
                html=em_html(conteudo),
                settings=settings,
            )
            marca = "OK    " if ok else "FALHOU"
            print(f"  {marca} {nome:<16} {assunto}")
            if not ok:
                falhas += 1

    return falhas


def main() -> None:
    # O console do Windows usa cp1252 e estoura no caractere de caixa. Este
    # script roda justamente na maquina de quem desenvolve, que e onde o
    # defeito apareceria — o mesmo que o gate de dependencias ja comprou.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    amostras = _amostras("https://exemplo")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destinos", nargs="+", help="endereços que vão receber as amostras")
    parser.add_argument("--env", type=Path, default=None, help="arquivo .env a ler")
    parser.add_argument(
        "--so",
        default="",
        help="amostras a mandar, separadas por vírgula: " + ", ".join(amostras),
    )
    args = parser.parse_args()

    env, origem = ler_env(args.env or PADRAO_ENV, exigido=args.env is not None)

    ambiente = env.get("APP_ENV", os.environ.get("APP_ENV", "development"))
    if ambiente == "production":
        sys.exit(
            "ERRO: APP_ENV=production. Este script manda texto de AMOSTRA e nao deve\n"
            "sair pelo remetente de producao. Aponte --env para um arquivo de\n"
            "desenvolvimento, ou rode com APP_ENV=development."
        )

    quais = [q.strip() for q in args.so.split(",") if q.strip()] or list(amostras)
    desconhecidas = [q for q in quais if q not in amostras]
    if desconhecidas:
        sys.exit(f"ERRO: amostra desconhecida: {', '.join(desconhecidas)}")

    settings = Settings(
        database_url="postgresql+asyncpg://naoUsado:naoUsado@localhost/naoUsado",
        app_env=ambiente,
        smtp_host=env.get("SMTP_HOST", ""),
        smtp_port=int(env.get("SMTP_PORT", "465") or 465),
        smtp_user=env.get("SMTP_USER", ""),
        smtp_password=env.get("SMTP_PASSWORD", ""),
        smtp_from_name=env.get("SMTP_FROM_NAME", "Help Desk Health & Safety"),
        smtp_from_email=env.get("SMTP_FROM_EMAIL", ""),
        smtp_reply_to=env.get("SMTP_REPLY_TO", ""),
        smtp_tls=env.get("SMTP_TLS", "false").lower() == "true",
        smtp_ssl=env.get("SMTP_SSL", "true").lower() == "true",
        frontend_url=env.get("FRONTEND_URL", "https://helphs.healthsafetytech.com"),
    )

    print(f"config de : {origem}")
    print(f"ambiente  : {ambiente}")
    print(
        f"host      : {settings.smtp_host}:{settings.smtp_port} "
        f"(ssl={settings.smtp_ssl}, starttls={settings.smtp_tls})"
    )
    print(f"usuario   : {settings.smtp_user or '(sem autenticacao)'}")
    print(f"senha     : {mascarar(settings.smtp_password)}")
    print(f"remetente : {settings.smtp_from_name} <{settings.smtp_from_email}>")
    print(f"links para: {settings.frontend_url}")
    print(f"amostras  : {', '.join(quais)}")

    if not settings.smtp_host:
        sys.exit("ERRO: SMTP_HOST vazio.")
    if "CHANGE_ME" in settings.smtp_password:
        sys.exit("ERRO: SMTP_PASSWORD ainda esta com o valor de exemplo.")

    falhas = asyncio.run(_dispara(args.destinos, quais, settings))

    print("\n" + "=" * 62)
    if falhas:
        print(f"{falhas} envio(s) FALHARAM — veja o log acima.")
        sys.exit(1)

    print("Todas as amostras foram aceitas para entrega.")
    print(
        "\nAgora abra cada caixa, nesta ordem:\n"
        "  1. Outlook desktop classico   botao virou texto sublinhado? largura estourou?\n"
        "  2. Novo Outlook / Outlook Web faixa e botao sobreviveram ao tema escuro?\n"
        "  3. Gmail web                  apareceu '[Mensagem cortada]'?\n"
        "  4. Gmail app                  inversao forcada quebrou alguma cor?\n"
        "  5. Apple Mail, se houver\n"
        "\nE em TODOS: apareceu como pagina ou como codigo-fonte?\n"
        "Se apareceu como codigo, o Content-Transfer-Encoding deixou de ser risco\n"
        "teorico — anote em qual cliente e isso vira defeito com evidencia."
    )


if __name__ == "__main__":
    main()
