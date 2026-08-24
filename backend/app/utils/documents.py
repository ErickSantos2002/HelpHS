"""
Normalização de documentos brasileiros — ponto único.

Espelha `frontend/src/lib/documents.ts`, que faz o mesmo trabalho antes de
enviar. **As duas pontas precisam concordar**, e é por isso que aqui é uma
função e não três cópias: a regra estava só no `OnboardingUpdate` e faltava
nos outros três pontos de escrita (`UserUpdate`, `CompanyCreate`,
`CompanyUpdate`), o que deixava `users.cnpj` com 14 dígitos crus e
`companies.cnpj` com a máscara que o próprio front sugeria no `placeholder`.
Comparar as duas colunas por string nunca dava igual — foi o que travou a
unicidade de série por empresa (levantamento de 24/08).

O script de backfill (`backend/scripts/normaliza_cnpj.py`) importa daqui.
É o ponto: se a normalização do backfill divergisse da do validador, o script
gravaria linhas que a API recusaria depois.

**O que estas funções NÃO fazem:** conferir os dígitos verificadores. Isso é
feito no front (`isValidCnpj`) e continua lá. Trazer para cá recusaria linhas
que já estão no banco e não fecharia buraco nenhum de segurança — CNPJ é dado
autodeclarado de qualquer jeito, e `decisoes-e-regras.md` já diz que ele não
serve para escopo nem permissão. Quem manda nisso é `companies.id`.
"""

import re
from typing import Annotated

from pydantic import AfterValidator

_ERRO = "O CNPJ deve conter 14 dígitos."


def normaliza_cnpj(valor: str) -> str:
    """
    Devolve só os dígitos do CNPJ, exigindo que sejam exatamente 14.

    Para o campo **obrigatório** (onboarding). String vazia é recusada aqui:
    quem quiser tratar ausência usa `normaliza_cnpj_opcional`.

    Raises:
        ValueError: se o valor não tiver exatamente 14 dígitos.
    """
    digitos = re.sub(r"\D", "", valor)
    if len(digitos) != 14:
        raise ValueError(_ERRO)
    return digitos


def normaliza_cnpj_opcional(valor: str | None) -> str | None:
    """
    Versão para campo opcional: ausência e campo limpo viram `None`.

    `None` e string vazia (ou só espaços) significam "sem CNPJ" — limpar o
    campo no front manda `""`, não `null`, porque os dois modais de empresa do
    `GroupsPage` nascem com `cnpj: ""` no `defaultValues`. Recusar isso
    quebraria criar empresa sem CNPJ, que hoje funciona.

    O que **não** é tratado como ausência é lixo com conteúdo: `"abc"` tem
    zero dígitos, mas é erro de digitação, não campo limpo. Vira `ValueError`
    em vez de virar `None` em silêncio.

    Raises:
        ValueError: se houver conteúdo que não some 14 dígitos.
    """
    if valor is None or not valor.strip():
        return None
    return normaliza_cnpj(valor)


# ── Tipos para os schemas ─────────────────────────────────────
#
# A validação viaja no TIPO, não num validador copiado em cada modelo. É o que
# fecha o buraco de verdade: `CompanyCreate.cnpj` era `str | None` puro e por
# isso não validava nada, e o próximo campo de CNPJ declarado assim nasceria
# com o mesmo defeito, em silêncio. Declarando `CnpjOpcional` a validação vem
# junto e esquecer dela exige contrariar o tipo.
#
# `AfterValidator` e não `BeforeValidator`: rodando depois da coerção, o valor
# que chega já é `str | None` de verdade — com `Before`, um `123` numérico
# entraria como int e estouraria `AttributeError` em vez de virar 422.

CnpjObrigatorio = Annotated[str, AfterValidator(normaliza_cnpj)]
CnpjOpcional = Annotated[str | None, AfterValidator(normaliza_cnpj_opcional)]
