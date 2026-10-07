"""Regressão de segurança: confusão de algoritmo em JWT (CVE-2026-85394).

O que o CVE descreve
--------------------
`python-jose` <= 3.5.0 valida mal a chave em HMAC: um verificador que aceite
`alg: HS256` pode ser enganado por um token assinado em HMAC usando a CHAVE
PÚBLICA RSA como segredo — o atacante forja um token válido só com material
público. É o ataque clássico de "algorithm confusion" (RS256 ↔ HS256).

Por que o HelpHS não é alcançável
---------------------------------
TODO `jwt.decode` do backend fixa `algorithms=[settings.jwt_algorithm]`, que é
`["RS256"]`. O `jose` recusa um token cujo `alg` não está nessa lista ANTES de
tocar no material de chave — então um token `HS256` é rejeitado no portão do
algoritmo, e o segredo usado para forjá-lo (público ou não) nunca é alcançado.

Estes testes PRENDEM esse portão. Se algum `decode` futuro largar o
`algorithms=`, ou passar a aceitar HS*, um destes casos cai — e é de propósito
que eles exercitem os validadores REAIS, não um mock, porque é o
`algorithms=[...]` concreto de cada um que fecha o vetor.

Segredo arbitrário, não a chave pública
----------------------------------------
A rejeição acontece no portão do algoritmo, idêntica para qualquer segredo —
então estes tokens são assinados com um segredo comum. Não é preciso (nem o
`jose` 3.4.0 permite) usar a chave pública como segredo HMAC para exercitar a
defesa: a diferença de segredo nunca é alcançada, porque o `alg` já barra.
"""

import time
import uuid

import pytest
from jose import jwt

from app.core import security
from app.core.config import get_settings
from app.services import account_tokens, storage

_s = get_settings()


def _hs256(**claims) -> str:
    """Token com header `alg: HS256`, segredo arbitrário. O `iss` legítimo é
    incluído para que a única razão de rejeição possível seja o algoritmo."""
    agora = int(time.time())
    base = {"iat": agora, "exp": agora + 3600, "iss": _s.jwt_issuer}
    base.update(claims)
    return jwt.encode(base, "segredo-arbitrario-irrelevante", algorithm="HS256")


def test_o_jose_instalado_esta_na_faixa_vulneravel():
    """Este arquivo só tem razão de existir enquanto o pacote for vulnerável.
    Quando subir para uma versão corrigida, a entrada de baseline cai como
    obsoleta e este teste vira o lembrete de reavaliar a prova."""
    from importlib.metadata import version

    assert version("python-jose").startswith("3."), "reavaliar o CVE-2026-85394"


def test_access_token_rejeita_hs256():
    token = _hs256(sub=str(uuid.uuid4()), role="admin", email="x@y.com", type="access")
    with pytest.raises(Exception) as exc:
        security.decode_token(token)
    # JWTError do jose: o alg não está no whitelist.
    assert "alg" in str(exc.value).lower() or exc.type.__name__ == "JWTError"


def test_email_verification_rejeita_hs256():
    token = _hs256(sub=str(uuid.uuid4()), type="email_verify")
    with pytest.raises(account_tokens.InvalidTokenError):
        account_tokens.read_email_verification_token(token, False, _s)


def test_password_reset_rejeita_hs256():
    token = _hs256(sub=str(uuid.uuid4()), type="password_reset")
    # `peek_...` é o leitor mínimo: só decodifica (assinatura + tipo), que é
    # exatamente o portão onde o algoritmo é barrado.
    with pytest.raises(account_tokens.InvalidTokenError):
        account_tokens.peek_password_reset_subject(token, _s)


def test_file_token_rejeita_hs256():
    token = _hs256(sub="tickets/x/laudo.pdf", type="file")
    with pytest.raises(storage.StorageError):
        storage.read_file_token(token, _s)


def test_o_controle_rs256_legitimo_continua_aceito():
    """Negativo do negativo: a defesa não pode rejeitar o algoritmo CERTO."""
    agora = int(time.time())
    legitimo = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "role": "admin",
            "email": "x@y.com",
            "type": "access",
            "iat": agora,
            "exp": agora + 3600,
            "iss": _s.jwt_issuer,
        },
        _s.get_private_key(),
        algorithm=_s.jwt_algorithm,
    )
    assert security.decode_token(legitimo)["type"] == "access"


def test_todo_decode_do_backend_fixa_o_whitelist_de_algoritmo():
    """Guard de fonte: nenhum `jwt.decode` pode existir sem `algorithms=`.

    O ataque de confusão de algoritmo só é possível contra um decode que NÃO
    restrinja `algorithms`. Em vez de confiar que ninguém vai esquecer, este
    teste varre o código e exige a cláusula em todo `jwt.decode(` — a mesma
    disciplina do grep que o baseline de dependências pede como prova.
    """
    import re
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "app"
    faltando = []
    for arquivo in app.rglob("*.py"):
        fonte = arquivo.read_text(encoding="utf-8")
        for m in re.finditer(r"jwt\.decode\s*\(", fonte):
            trecho = fonte[m.start() : m.start() + 400]
            if "algorithms=" not in trecho:
                linha = fonte[: m.start()].count("\n") + 1
                faltando.append(f"{arquivo.relative_to(app.parent)}:{linha}")
    assert not faltando, f"jwt.decode sem algorithms= (vetor de confusão): {faltando}"
