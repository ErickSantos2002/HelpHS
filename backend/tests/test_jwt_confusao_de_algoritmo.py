"""Regressão de segurança: confusão de algoritmo em JWT (PYSEC-2026-4298).

Mesma vulnerabilidade com vários nomes — aliases mútuos no OSV:
PYSEC-2026-4298, CVE-2026-85394, GHSA-3qf3-8w2g-rqmx (o pip-audit passou a
reportá-la pelo PYSEC em 15/10/2026). É a correção incompleta do
CVE-2024-33663 / GHSA-6c5p-j8vq-pqhj.

O que a vulnerabilidade descreve
--------------------------------
`python-jose` <= 3.5.0 valida mal a chave em HMAC: a trava que impede usar
uma chave assimétrica como segredo HMAC só reconhece PEM (`-----BEGIN`) e
SSH. A mesma chave PÚBLICA RSA em DER passa, e um verificador que aceite
`alg: HS256` pode ser enganado por um token assinado em HMAC com esse DER —
o atacante forja um token válido só com material público. É o ataque
clássico de "algorithm confusion" (RS256 ↔ HS256). Não há versão corrigida
publicada.

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

O ataque de verdade, não só o portão
------------------------------------
Os primeiros casos assinam com um segredo comum: a rejeição acontece no portão
do algoritmo, idêntica para qualquer segredo. Os casos `_der` usam o vetor
exato do aviso — a chave pública do próprio HelpHS em DER como segredo HMAC —
e um teste-controle prova que esse token forjado É aceito por um verificador
ingênuo do jose instalado. Sem esse controle, "o HelpHS rejeitou" poderia ser
só um token malformado; com ele, a rejeição é do HelpHS, e não do acaso.

Uma segunda barreira, que estes testes não dispensam: a chave do HelpHS é PEM
(`get_public_key`), e PEM a trava do jose ainda reconhece. Mesmo com
`JWT_ALGORITHM=HS256` no ambiente, o jose recusaria a chave PEM — o sistema
não emitiria token nenhum, em vez de aceitar um forjado.
"""

import time
import uuid

import pytest
from jose import JWTError, jwt

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

    assert version("python-jose").startswith("3."), "reavaliar o PYSEC-2026-4298"


def _der_publico() -> bytes:
    """A chave pública do HelpHS em DER — o material que o atacante tem."""
    from cryptography.hazmat.primitives import serialization

    publica = serialization.load_pem_public_key(_s.get_public_key().encode())
    return publica.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def _hs256_der(**claims) -> str:
    """O token do ataque: HS256 assinado com a chave pública em DER."""
    agora = int(time.time())
    base = {"iat": agora, "exp": agora + 3600, "iss": _s.jwt_issuer}
    base.update(claims)
    return jwt.encode(base, _der_publico(), algorithm="HS256")


def test_controle_o_token_der_engana_um_verificador_ingenuo():
    """Prova que o ataque é real no jose instalado: sem restringir o
    algoritmo, o token forjado passa. É isso que torna significativa a
    rejeição pelos decoders do HelpHS logo abaixo. Quando o jose corrigir,
    este teste cai — e a entrada do baseline também, como obsoleta."""
    token = _hs256_der(sub="x", type="access")
    aceito = jwt.decode(token, _der_publico(), algorithms=None, issuer=_s.jwt_issuer)
    assert aceito["sub"] == "x"


@pytest.mark.parametrize("tipo", ["access", "refresh"])
def test_decode_token_rejeita_o_ataque_der(tipo):
    token = _hs256_der(sub=str(uuid.uuid4()), role="admin", email="x@y.com", type=tipo)
    with pytest.raises(JWTError, match="alg"):
        security.decode_token(token)


def test_email_verification_rejeita_o_ataque_der():
    token = _hs256_der(sub=str(uuid.uuid4()), type="email_verify")
    with pytest.raises(account_tokens.InvalidTokenError):
        account_tokens.read_email_verification_token(token, False, _s)


def test_password_reset_rejeita_o_ataque_der():
    token = _hs256_der(sub=str(uuid.uuid4()), type="password_reset")
    with pytest.raises(account_tokens.InvalidTokenError):
        account_tokens.peek_password_reset_subject(token, _s)


def test_file_token_rejeita_o_ataque_der():
    """O decode de arquivo recebe um objeto `Key` em cache, não o PEM — outro
    caminho dentro do jose; o portão do algoritmo tem de barrar igual."""
    token = _hs256_der(sub="tickets/x/laudo.pdf", type="file", v=0)
    with pytest.raises(storage.StorageError):
        storage.ler_token_de_arquivo(token, _s)


def test_token_do_lote_zip_rejeita_o_ataque_der():
    token = _hs256_der(sub=str(uuid.uuid4()), ids=["a"], type=storage._TOKEN_TYPE_LOTE)
    with pytest.raises(storage.StorageError):
        storage.read_archive_token(token, _s)


def test_token_do_lote_zip_rejeita_hs256():
    token = _hs256(sub=str(uuid.uuid4()), ids=["a"], type=storage._TOKEN_TYPE_LOTE)
    with pytest.raises(storage.StorageError):
        storage.read_archive_token(token, _s)


def test_os_controles_rs256_de_arquivo_e_lote_continuam_aceitos():
    """Negativo do negativo para os dois decoders que usam o `Key` em cache."""
    arquivo = storage.create_file_token("tickets/x/a.pdf", _s)
    assert storage.ler_token_de_arquivo(arquivo, _s)[0] == "tickets/x/a.pdf"
    lote = storage.create_archive_token("chamado", ["a", "b"], _s)
    assert storage.read_archive_token(lote, _s) == ("chamado", ["a", "b"])


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
