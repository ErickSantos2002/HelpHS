"""
Desliga o segundo fator de uma conta direto no banco — a última linha de
defesa para quem perdeu o celular.

**Avulso, rodado à mão.** Não é chamado por ninguém, não é migration, não
entra no boot do container.

Existe porque a aplicação NÃO tem caminho de admin para isso: `DELETE
/auth/mfa` exige a senha **e** uma sessão, e quem está trancado fora não tem
nem uma nem outra. Um admin também não pode desligar o segundo fator de
terceiros pela API — de propósito, porque um endpoint desses seria uma forma de
remover a proteção de outra pessoa.

Atenção ao que o `redefine_senha.py` NÃO faz: redefinir a senha de uma conta com
`mfa_enabled = true` deixa a pessoa igualmente trancada, porque o login continua
pedindo o código depois da senha nova. Para o caso "perdi o celular", é ESTE
script, não aquele. Para "perdi celular e senha", os dois, nesta ordem.

Também apaga o refresh token da conta, como o endpoint faz: se alguém tinha uma
sessão aberta, desligar o segundo fator sem despejá-la devolveria acesso a quem
talvez seja o motivo do chamado. Sem `REDIS_URL` o script avisa e segue — o
banco é a parte que não pode ficar pela metade.

Deixa rastro em `audit_logs`, porque desligar um fator de autenticação em
produção sem registro é pior que o problema que veio resolver.

Uso::

    cd backend
    export DATABASE_URL='postgresql+asyncpg://usuario:senha@host:porta/banco'
    export REDIS_URL='redis://:senha@host:6379/0'      # opcional

    python -m scripts.desliga_mfa --email pessoa@empresa.com
    python -m scripts.desliga_mfa --email pessoa@empresa.com --por admin@empresa.com --aplicar

Sem `--aplicar` nada é escrito: o script só localiza a conta e mostra o que
faria. Depois de desligado, a pessoa entra só com a senha e pode cadastrar o
aplicativo de novo pelo próprio perfil.
"""

import argparse
import asyncio
import json
import os
import sys
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# O console do Windows abre em cp1252 e estoura em qualquer acento — e este
# script roda na máquina de quem administra, não no container.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def despeja_sessoes(user_id: uuid.UUID) -> str:
    """Apaga `token:refresh:{id}`. Devolve o que contar ao operador."""
    url = os.environ.get("REDIS_URL")
    if not url:
        return "REDIS_URL não definida — sessões abertas NÃO foram encerradas."

    try:
        import redis.asyncio as aioredis

        cliente = aioredis.from_url(url, socket_connect_timeout=5)
        try:
            apagou = await cliente.delete(f"token:refresh:{user_id}")
        finally:
            await cliente.aclose()
    except Exception as exc:  # pragma: no cover - depende do ambiente
        return f"Falha ao falar com o Redis ({exc}). Sessões abertas NÃO foram encerradas."

    return "Refresh apagado: sessões abertas encerradas." if apagou else "Nenhuma sessão aberta."


async def principal() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="e-mail da conta")
    parser.add_argument("--por", help="e-mail de quem está executando (vai para o audit_log)")
    parser.add_argument("--aplicar", action="store_true", help="grava (sem isto, só relata)")
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL não definida. Exporte-a antes de rodar.")
        return 1

    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            linha = (
                await conn.execute(
                    text(
                        "SELECT id, name, email, role, status, mfa_enabled, "
                        "mfa_secret IS NOT NULL, mfa_confirmed_at "
                        "FROM users WHERE lower(email) = lower(:email)"
                    ),
                    {"email": args.email},
                )
            ).first()

            if linha is None:
                print(f"Nenhuma conta com o e-mail {args.email!r}.")
                return 1

            user_id, nome, email, role, status, ligado, tem_segredo, confirmado = linha
            print(f"Conta: {nome} <{email}>")
            print(f"  id .............. {user_id}")
            print(f"  role ............ {role}")
            print(f"  status .......... {status}")
            print(f"  mfa_enabled ..... {ligado}")
            print(f"  tem segredo ..... {tem_segredo}")
            print(f"  confirmado em ... {confirmado or '—'}")

            if not ligado and not tem_segredo:
                print("\nEsta conta não tem segundo fator. Nada a desligar.")
                return 0

            if not ligado:
                print(
                    "\nATENÇÃO: há um segredo cadastrado mas não confirmado. "
                    "Ele não bloqueia o login; desligar aqui só limpa o cadastro pela metade."
                )

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

            # Os três campos juntos: `mfa_enabled` verdadeiro com segredo nulo é
            # o par que o CHECK do banco recusa, e limpar só a flag deixaria o
            # segredo órfão — cifrado com uma chave que pode nem existir mais.
            await conn.execute(
                text(
                    "UPDATE users SET mfa_enabled = false, mfa_secret = NULL, "
                    "mfa_confirmed_at = NULL, updated_at = now() WHERE id = :id"
                ),
                {"id": user_id},
            )
            await conn.execute(
                text(
                    "INSERT INTO audit_logs (id, user_id, action, entity_type, entity_id, new_data)"
                    " VALUES (:id, :ator, 'update', 'user', :alvo, CAST(:dados AS jsonb))"
                ),
                {
                    "id": uuid.uuid4(),
                    "ator": ator_id,
                    "alvo": user_id,
                    "dados": json.dumps(
                        {
                            "mfa_enabled": False,
                            "motivo": "desligado por scripts/desliga_mfa.py",
                            "por": args.por or "não informado",
                        }
                    ),
                },
            )

        print("\nSegundo fator desligado.")
        print(f"  {await despeja_sessoes(user_id)}")
        print(f"  {email} entra agora só com a senha, e pode cadastrar o app de novo no perfil.")
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
