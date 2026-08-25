"""
Consultas por item: o número de consultas não pode crescer com a lista.

Três listagens administrativas montavam a resposta item a item, e cada item
disparava os seus próprios COUNTs — um por grupo, dois por empresa, dois por
técnico. Não era urgente no volume de hoje; é higiene antes de a base crescer.

O que estes testes prendem NÃO é um número fixo de consultas — esse número
muda legitimamente quando alguém acrescenta um campo. É a propriedade que
importa: dobrar a lista não pode dobrar as consultas.

Mock aqui é o instrumento certo: o que se mede é quantas vezes o `execute` foi
chamado, não o que o banco respondeu.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest


def _grupo(nome: str):
    g = MagicMock()
    g.id = uuid.uuid4()
    g.name = nome
    g.description = None
    g.notes = None
    g.created_at = datetime.now(UTC)
    g.updated_at = datetime.now(UTC)
    return g


def _sessao_que_conta(grupos):
    """1ª chamada devolve os grupos; as seguintes, linhas de GROUP BY."""
    contador = {"n": 0}

    async def _execute(*args, **kwargs):
        contador["n"] += 1
        result = MagicMock()
        if contador["n"] == 1:
            result.scalars.return_value.all.return_value = grupos
            result.__iter__ = lambda self: iter([])
        else:
            result.__iter__ = lambda self: iter([(g.id, 3) for g in grupos])
            result.scalars.return_value.all.return_value = []
        return result

    session = AsyncMock()
    session.execute = _execute
    return session, contador


async def _consultas_para_listar_grupos(quantos: int) -> int:
    from app.routers import groups as router_groups

    grupos = [_grupo(f"Grupo {i}") for i in range(quantos)]
    session, contador = _sessao_que_conta(grupos)

    resposta = await router_groups.list_groups(session, None)

    assert len(resposta) == quantos
    assert all(g.company_count == 3 for g in resposta), "a contagem em lote não chegou na resposta"
    return contador["n"]


@pytest.mark.asyncio
async def test_listar_grupos_nao_consulta_uma_vez_por_grupo():
    poucos = await _consultas_para_listar_grupos(2)
    muitos = await _consultas_para_listar_grupos(20)

    assert poucos == muitos, (
        f"o número de consultas cresceu com a lista ({poucos} para 2 grupos, "
        f"{muitos} para 20): a contagem voltou a ser por item"
    )
    assert muitos <= 2, f"esperava a consulta de grupos + a de contagens, foram {muitos}"
