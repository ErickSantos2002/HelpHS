"""
A tela só oferece categoria que a API aceita, e oferece todas (INC-01).

Em 18/09/2026 o `other` saiu do `TicketCategory` (PR #28) e a API passou a
recusá-lo com 422. A metade do frontend — tirar "Outro" das listas — ficou para
"depois" e não aconteceu: quem escolhia "Outro" via "Erro ao salvar o chamado"
e não conseguia abrir o chamado.

As duas pontas moram no mesmo repositório e o job de backend do CI faz checkout
dele inteiro (`.github/workflows/ci.yml`, sem filtro de caminho), então a
comparação é direta: estes casos leem os `value` da lista `CATEGORIAS` em
`frontend/src/lib/categoria.ts` — a fonte única das telas — e os comparam com
o enum.

A ORDEM NÃO É CONTRATO. Ela é a da grade de fichas, decisão de apresentação do
front, e quem a prende é `frontend/src/test/lib/categoria.test.ts`. Aqui vale o
conjunto: nenhum valor a mais, nenhum a menos, nenhum repetido.

O arquivo do front AUSENTE reprova, não pula: um `skip` deixaria o contrato
passar calado no dia em que o caminho mudasse.
"""

import re
from collections import Counter
from pathlib import Path

from app.models.models import TicketCategory

_ARQUIVO_DO_FRONT = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "categoria.ts"
)

# Saíram do enum e não podem voltar à tela sem voltar antes à API.
_DESCONTINUADAS = {"other"}


def _valores_oferecidos_pelo_front() -> list[str]:
    assert (
        _ARQUIVO_DO_FRONT.is_file()
    ), f"{_ARQUIVO_DO_FRONT} não encontrado: o contrato precisa do repositório inteiro"
    fonte = _ARQUIVO_DO_FRONT.read_text(encoding="utf-8")
    inicio = fonte.index("export const CATEGORIAS")
    fim = fonte.index("] as const;", inicio)
    # Só o que é código: comentário pode citar valor que não é opção.
    bloco = re.sub(r"/\*.*?\*/|//[^\n]*", "", fonte[inicio:fim], flags=re.DOTALL)
    valores = re.findall(r"""\bvalue:\s*["']([^"']+)["']""", bloco)
    assert valores, "nenhum `value` lido de CATEGORIAS: o formato do arquivo mudou"
    return valores


_ACEITAS_PELA_API = {c.value for c in TicketCategory}


def test_o_front_nao_oferece_categoria_que_a_api_recusa() -> None:
    a_mais = set(_valores_oferecidos_pelo_front()) - _ACEITAS_PELA_API
    assert not a_mais, f"a tela oferece e a API responde 422: {sorted(a_mais)}"


def test_o_front_oferece_todas_as_categorias_da_api() -> None:
    faltando = _ACEITAS_PELA_API - set(_valores_oferecidos_pelo_front())
    assert not faltando, f"a API aceita e a tela não oferece: {sorted(faltando)}"


def test_o_front_nao_repete_categoria() -> None:
    repetidas = [v for v, n in Counter(_valores_oferecidos_pelo_front()).items() if n > 1]
    assert not repetidas, f"categoria repetida na tela: {repetidas}"


def test_categoria_descontinuada_nao_volta_a_ser_oferecida() -> None:
    voltaram = _DESCONTINUADAS & set(_valores_oferecidos_pelo_front())
    assert not voltaram, f"descontinuada de volta na tela: {sorted(voltaram)}"
    # E a API continua sem ela — a regra do PR #28 não muda aqui.
    assert not (_DESCONTINUADAS & _ACEITAS_PELA_API)
