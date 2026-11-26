"""
A regra de empresa dos equipamentos de um chamado (ECE-01) — a parte pura.

`_empresas_incompativeis` decide, sem banco, se um conjunto de equipamentos
pode ir no mesmo chamado. As rotas, as travas e a flag são provadas contra
PostgreSQL em `test_equipamento_compartilhado_postgres.py`.
"""

from types import SimpleNamespace

import pytest

from app.routers.tickets import _empresas_incompativeis

_X, _Y = "empresa-x", "empresa-y"


def _aparelhos(*empresas):
    return [SimpleNamespace(company_id=e) for e in empresas]


@pytest.mark.parametrize(
    ("empresas", "de_quem_abriu", "incompativel"),
    [
        # nada a conferir
        ((), None, False),
        ((), _X, False),
        # todos da mesma
        ((_X,), None, False),
        ((_X, _X, _X), None, False),
        ((_X, _X), _X, False),
        # todos sem empresa, tenha ou não empresa quem abriu
        ((None,), None, False),
        ((None, None), None, False),
        ((None, None), _X, False),
        # duas empresas
        ((_X, _Y), None, True),
        ((_X, _Y), _X, True),
        ((_X, _X, _Y), None, True),
        # classificado junto de não classificado
        ((_X, None), None, True),
        ((None, _X), _X, True),
        ((_X, _X, None), _X, True),
        # uma empresa só, que não é a de quem abriu
        ((_Y,), _X, True),
        ((_Y, _Y), _X, True),
    ],
)
def test_um_chamado_uma_classificacao(empresas, de_quem_abriu, incompativel):
    assert _empresas_incompativeis(_aparelhos(*empresas), de_quem_abriu) is incompativel
