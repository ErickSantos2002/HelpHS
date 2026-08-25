"""
Redefine a senha de um usuário direto no banco — socorro enquanto o
"Esqueci minha senha" não entrega e-mail (SMTP de produção pendente).

**Avulso, rodado à mão.** Não é chamado por ninguém, não é migration, não
entra no boot do container.

Existe porque a aplicação NÃO tem caminho de admin para isso:
`PATCH /users/{id}` não aceita senha e `POST /users/me/change-password` exige
a senha atual — que é justamente o que a pessoa perdeu.

Importa `hash_password` do próprio app de propósito: se o script tivesse a sua
própria cópia do bcrypt, gravaria um hash com custo diferente do que a API
usa. O custo viaja dentro do hash, então o login funciona de qualquer jeito —
mas o banco ficaria com uma linha fora do padrão do resto.

Deixa rastro em `audit_logs` com a ação `password_change`, porque uma troca
de senha em produção sem registro é pior que o problema que veio resolver.
(O `/users/me/change-password` da API grava `update` neste mesmo caso — o
enum tem `password_change` desde sempre e ninguém usou. Aqui usamos o certo.)

Uso::

    cd backend
    export DATABASE_URL='postgresql+asyncpg://usuario:senha@host:porta/banco'

    python -m scripts.redefine_senha --email pessoa@empresa.com
    python -m scripts.redefine_senha --email pessoa@empresa.com --aplicar

Sem `--aplicar` nada é escrito: o script só localiza a conta e mostra o que
faria. Sem `--senha` ele sorteia uma provisória e imprime UMA vez — quem
recebe deve trocá-la no próprio perfil logo depois.
"""

import argparse
import asyncio
import os
import secrets
import sys
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# O console do Windows abre em cp1252 e estoura em qualquer acento — e este
# script roda na máquina de quem administra, não no container.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Sem 0/O/1/l/I: a senha provisória vai ser lida em voz alta ou copiada de um
# chat, e um caractere ambíguo vira um chamado de "não funciona".
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def sorteia_senha(tamanho: int = 16) -> str:
    """
    Senha provisória que passa nas regras do `PasswordChange` do app
    (maiúscula + dígito), para quem receber não descobrir só na hora de trocar
    que a provisória não serviria de definitiva.
    """
    while True:
        senha = "".join(secrets.choice(ALFABETO) for _ in range(tamanho))
        if any(c.isupper() for c in senha) and any(c.isdigit() for c in senha):
            return senha


def avisos_de_login(status: str, email_verified: bool, app_env: str | None) -> list[str]:
    """
    O que ainda barra o login DEPOIS da senha certa.

    Separado do resto porque é a parte que engana: trocar a senha de uma conta
    inativa "funciona" e a pessoa continua sem entrar, agora achando que a
    senha nova veio errada.
    """
    avisos = []
    if status != "active":
        avisos.append(f"status = '{status}' — o login recusa com 403 até virar 'active'.")
    if not email_verified:
        avisos.append(
            "email_verified = false — se a verificação de e-mail estiver ligada "
            "em produção, o login recusa mesmo com a senha certa."
        )
    return avisos


async def principal() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="e-mail da conta")
    parser.add_argument("--senha", help="senha a gravar (sem isto, sorteia uma)")
    parser.add_argument("--por", help="e-mail de quem está executando (vai para o audit_log)")
    parser.add_argument("--aplicar", action="store_true", help="grava (sem isto, só relata)")
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL não definida. Exporte-a antes de rodar.")
        return 1

    # Import tardio de propósito: `app.core.security` arrasta
    # `app.core.database`, que monta um engine a partir do `.env` já no import.
    # Importando só aqui, a mensagem acima sai limpa quando ninguém disse em
    # qual banco mexer — e o `.env` só é lido depois dessa decisão.
    from app.core.security import hash_password

    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            linha = (
                await conn.execute(
                    text(
                        "SELECT id, name, email, role, status, email_verified "
                        "FROM users WHERE lower(email) = lower(:email)"
                    ),
                    {"email": args.email},
                )
            ).first()

            if linha is None:
                print(f"Nenhuma conta com o e-mail {args.email!r}.")
                return 1

            user_id, nome, email, role, status, email_verified = linha
            print(f"Conta: {nome} <{email}>")
            print(f"  id .............. {user_id}")
            print(f"  role ............ {role}")
            print(f"  status .......... {status}")
            print(f"  email_verified .. {email_verified}")

            for aviso in avisos_de_login(str(status), bool(email_verified), None):
                print(f"  ATENÇÃO: {aviso}")

            ator_id = None
            if args.por:
                ator = (
                    await conn.execute(
                        text("SELECT id FROM users WHERE lower(email) = lower(:email)"),
                        {"email": args.por},
                    )
                ).first()
                if ator is None:
                    print(f"\n--por {args.por!r} não corresponde a nenhuma conta. Abortado.")
                    return 1
                ator_id = ator[0]

            if not args.aplicar:
                print("\nDry-run: nada foi escrito. Repita com --aplicar para gravar.")
                return 0

            senha = args.senha or sorteia_senha()
            novo_hash = hash_password(senha)

            await conn.execute(
                text("UPDATE users SET password = :hash, updated_at = now() WHERE id = :id"),
                {"hash": novo_hash, "id": user_id},
            )
            await conn.execute(
                text(
                    "INSERT INTO audit_logs (id, user_id, action, entity_type, entity_id, new_data)"
                    " VALUES (:id, :ator, 'password_change', 'user', :alvo, "
                    "CAST(:dados AS jsonb))"
                ),
                {
                    "id": uuid.uuid4(),
                    "ator": ator_id,
                    "alvo": user_id,
                    "dados": '{"campo": "password", "origem": "scripts/redefine_senha"}',
                },
            )

            print("\nSenha redefinida.")
            print(f"  senha provisória: {senha}")
            print(
                "  Entregue por um canal privado. A pessoa troca em Meu perfil "
                "(menu do avatar) → cartão Segurança → Alterar senha."
            )
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
