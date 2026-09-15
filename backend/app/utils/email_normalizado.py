"""
E-mail em minúsculas, no tipo — a identidade não distingue maiúsculas.

O `EmailStr` do Pydantic normaliza só o domínio e preserva a caixa da parte
local: `FuLaNo@ExEmPlo.COM` passava como `FuLaNo@exemplo.com`, e como as
buscas comparam igualdade exata, `Fulano@` e `fulano@` viravam contas
distintas — a mesma caixa postal no mundo real (medido em 15/09; produção
estava limpa e a porta foi fechada antes da primeira duplicata).

A regra viaja no TIPO, como o CNPJ em `app/utils/documents.py`: declarar
`EmailNormalizado` traz a normalização junto, e o próximo campo de e-mail de
entrada declarado sem ele é pego pelo guard de fonte em
`tests/test_email_normalizado.py`.

`AfterValidator` e não `Before`: rodando depois do `EmailStr`, o valor já é
um e-mail válido com domínio normalizado — só falta baixar a parte local.

O passado é do `scripts/normaliza_emails.py`; a trava de banco é o índice
único em `lower(email)`.
"""

from typing import Annotated

from pydantic import AfterValidator, EmailStr


def normaliza_email(valor: str) -> str:
    """Baixa a parte local — o domínio o `EmailStr` já baixou antes."""
    return valor.lower()


EmailNormalizado = Annotated[EmailStr, AfterValidator(normaliza_email)]
