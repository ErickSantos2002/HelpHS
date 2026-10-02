"""Autenticação máquina-a-máquina das integrações de entrada.

Este módulo existe porque o HelpHS não tinha nenhuma. Até aqui, tudo o que
autenticava uma requisição vinha de `get_current_user` — sessão de gente, com
JWT, papel e usuário — e as únicas credenciais do projeto eram de SAÍDA
(`api4com_token`, `deepseek_api_key`, SMTP). O evento de encerramento de
chamada é a primeira porta de entrada, e por isso ela nasce em arquivo próprio:
misturá-la com `core/security.py` convidaria, no futuro, a reaproveitar uma
dependência de sessão onde a de integração deveria estar — ou o contrário.

Três recusas, e cada uma com um código diferente de propósito:

* **503** quando o servidor não tem segredo configurado. É falha de operação, e
  não do cliente: a integração não existe nesse ambiente. Nunca 200.
* **401** quando o cabeçalho falta, vem vazio ou não bate. **Mensagem igual nos
  três casos**, porque distinguir "faltou" de "errou" entrega ao atacante a
  informação de que o cabeçalho é o caminho certo.
* Nada de 403: não há papel aqui, não há usuário, e não há escalonamento
  possível. Ou a chamada é da integração, ou não é.

⚠️ A comparação é `hmac.compare_digest`, e não `==`. O `==` de strings em
CPython retorna no primeiro byte diferente, e o tempo dessa resposta vaza o
prefixo correto. É o mesmo cuidado que `services/mfa.py` já toma com o código
TOTP, e o único outro lugar do projeto onde isso aparece.

⚠️ Nada neste módulo registra o segredo — nem o recebido, nem o esperado, nem o
comprimento de um deles. Mensagem de erro cita o NOME do cabeçalho e mais nada,
mesmo critério do `_valida_api4com` do boot.
"""

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings

# O nome do cabeçalho é público — o que é segredo é o valor.
CABECALHO_DO_SEGREDO = "X-HelpHS-Webhook-Secret"

_RECUSA_GENERICA = "Credencial de integração inválida."


async def exige_segredo_de_integracao(
    settings: Annotated[Settings, Depends(get_settings)],
    x_helphs_webhook_secret: Annotated[str | None, Header()] = None,
) -> None:
    """Deixa passar só quem apresenta o segredo configurado no servidor.

    Devolve `None` de propósito: esta dependência não identifica ninguém. Quem a
    usa não ganha um ator, um papel nem um usuário — só a garantia de que a
    chamada veio de quem tem o segredo. Endpoint que precisar saber "quem" está
    pedindo a coisa errada a ela.

    ⚠️ **Não existe caminho alternativo.** Esta dependência não aceita sessão,
    não consulta `get_current_user` e não tem modo permissivo. Um endpoint de
    integração que aceitasse sessão como substituto viraria, na prática, uma rota
    pública para qualquer usuário autenticado — inclusive `client`.
    """
    esperado = settings.helphs_webhook_secret.get_secret_value()

    if not esperado:
        # Fail-closed: sem segredo no servidor a integração não funciona. O 503
        # é deliberado e distinto do 401 — diz "este ambiente não tem a
        # integração", não "sua credencial está errada".
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A integração não está disponível no momento.",
        )

    recebido = x_helphs_webhook_secret or ""

    # `compare_digest` exige bytes de mesmo domínio; `encode` antes de comparar.
    # Segredo ausente cai no mesmo ramo do segredo errado, com a MESMA mensagem.
    if not hmac.compare_digest(recebido.encode("utf-8"), esperado.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_RECUSA_GENERICA,
        )
