"""
A categoria recebida como filtro de listagem (`?category=`), validada no tipo.

`GET /tickets` e `GET /kb/articles` recebiam `category: str` e o comparavam com
a coluna do enum `ticketcategory`. Valor fora do enum (`other`, que saiu no
PR #28, um erro de digitação, ou `General` com maiúscula) chegava ao PostgreSQL
e virava **500** (`invalid input value for enum`), não 422 (INC-01, frente C).

Por que não `TicketCategory | None` direto no `Query`: o front manda `""` quando
a pessoa limpa o menu, e o enum recusaria a string vazia, quebrando a listagem
sem filtro. O tipo abaixo trata vazio (ou só espaço) como ausência e recusa o
resto. O `ValueError` vira o 422 de sempre pelo handler central
(`app/core/exceptions.py`): `{"detail": [{"field": "category", ...}]}`.

`AfterValidator` e não `Before`: rodando depois da coerção, o valor que chega já
é `str` ou `None` — a mesma escolha de `telefone.py` e `documents.py`.
"""

from typing import Annotated

from pydantic import AfterValidator

from app.models.models import TicketCategory

_OPCOES = ", ".join(c.value for c in TicketCategory)

# Para o OpenAPI: o tipo do parâmetro continua `string | null`, e esta frase diz
# o que ele aceita.
DESCRICAO_DO_FILTRO = f"Uma de: {_OPCOES}. Vazio ou ausente = sem filtro. Outro valor = 422."


def categoria_do_filtro(valor: str | None) -> TicketCategory | None:
    """`None` para ausente ou vazio; o membro do enum para valor válido.

    A comparação é exata: `General` não é `general`. O filtro aceita o que a
    API devolve nas respostas, e ela devolve sempre em minúsculas.
    """
    if valor is None or not valor.strip():
        return None
    try:
        return TicketCategory(valor)
    except ValueError:
        raise ValueError(f"Valor inválido. Opções: {_OPCOES}") from None


CategoriaDoFiltro = Annotated[str | None, AfterValidator(categoria_do_filtro)]
