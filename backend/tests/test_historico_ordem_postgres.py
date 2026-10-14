"""
Ordem do histórico do chamado com eventos empatados, contra PostgreSQL.

Por que existe
--------------
`ticket_history.created_at` nasce do `now()` do Postgres, que é o horário do
INÍCIO DA TRANSAÇÃO: tudo que uma requisição grava junto — os N anexos de um
envio, por exemplo — sai com o mesmo `created_at`. Ordenar só por ele deixa o
empate na mão do plano de execução, e a tela lê o histórico em páginas. Se o
grupo empatado cair na divisa de duas páginas, cada consulta pode ordená-lo de
um jeito: uma linha repete, outra some.

O desempate pelo `id` torna a ordem total e estável. Os empates aqui são
gravados com ids em ordem DECRESCENTE — o contrário da ordem física de
inserção —, para que, sem o segundo critério, o banco devolva a ordem de
inserção e o teste caia de forma determinística, e não por sorte.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.models import TicketHistory, UserRole
from tests import test_equipamentos_staff_postgres as _base
from tests.test_equipamentos_staff_postgres import _get, _usuario
from tests.test_tickets_postgres import _chamado_novo

# Fixtures de banco real, atribuídas (e não importadas pelo nome) pelo mesmo
# motivo do `test_anexos_zip.py`: o import direto faz o ruff ler cada
# parâmetro `db` como redefinição (F811).
url_do_banco = _base.url_do_banco
db = _base.db
_limpa_overrides = _base._limpa_overrides

_T0 = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)


def _evento(chamado_id, autor_id, quando, id_numerico, campo="attachment_added"):
    return TicketHistory(
        id=uuid.UUID(int=id_numerico),
        ticket_id=chamado_id,
        user_id=autor_id,
        field=campo,
        old_value=None,
        new_value=str(uuid.uuid4()),
        comment=None,
        created_at=quando,
    )


@pytest.mark.asyncio
async def test_empate_na_divisa_da_pagina_nao_repete_nem_perde_evento(db):
    admin = _usuario(UserRole.admin, "Adm. Bruno")
    cliente = _usuario(UserRole.client, "Maria Souza")
    db.add_all([admin, cliente])
    await db.flush()
    chamado = _chamado_novo(cliente)
    db.add(chamado)
    await db.flush()

    empatados = _T0 + timedelta(minutes=5)
    eventos = [
        _evento(chamado.id, cliente.id, _T0, 900, campo="created"),
        _evento(chamado.id, admin.id, _T0 + timedelta(minutes=1), 901, campo="status"),
        # Quatro anexos do MESMO envio: mesmo created_at, ids gravados em ordem
        # decrescente. Com páginas de 3, o grupo atravessa a divisa 3|4.
        _evento(chamado.id, cliente.id, empatados, 40),
        _evento(chamado.id, cliente.id, empatados, 30),
        _evento(chamado.id, cliente.id, empatados, 20),
        _evento(chamado.id, cliente.id, empatados, 10),
        _evento(chamado.id, admin.id, _T0 + timedelta(minutes=9), 902, campo="status"),
    ]
    for e in eventos:  # um por vez: a ordem física de inserção é a da lista
        db.add(e)
        await db.flush()

    lidos: list[str] = []
    for offset in (0, 3, 6):
        resp = await _get(db, admin, f"/tickets/{chamado.id}/history", limit=3, offset=offset)
        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] == 7
        lidos += [i["id"] for i in resp.json()["items"]]

    esperado = [str(e.id) for e in sorted(eventos, key=lambda e: (e.created_at, e.id.bytes))]
    assert len(lidos) == len(set(lidos)) == 7, f"repetiu ou perdeu: {lidos}"
    assert lidos == esperado, "a ordem tem que ser created_at, depois id"
