"""
Quais equipamentos um CLIENTE enxerga (ECE-01, Fase 2).

Ponto único da regra. Listagem, detalhe e vínculo a chamado perguntam aqui, e
não cada um do seu jeito — três cópias da mesma condição são três chances de
uma delas esquecer o "ativo" ou o "empresa não nula".

A regra
-------
O cliente enxerga um equipamento quando:

1. é o responsável por ele (`owner_id`) — ativo ou não, com empresa ou sem.
   É o que sempre valeu, e não depende de flag nenhuma; ou
2. `EQUIPAMENTO_POR_EMPRESA` está ligada, o cliente tem vínculo oficial
   (`users.company_id`), o equipamento é dessa MESMA empresa
   (`equipments.company_id`) e está ATIVO.

O que cai fora por construção, sem condição própria:

- equipamento sem empresa de outra pessoa: nulo não é igual a nada;
- cliente sem vínculo: sem empresa para comparar, sobra a regra 1;
- equipamento inativo de colega: a regra 2 exige ativo;
- equipamento de outra empresa.

"Enxergar" é ler e usar em chamado próprio. NÃO é editar nem inativar: essas
rotas continuam perguntando só pelo responsável (`_check_equipment_owner`).

A regra existe duas vezes de propósito — como condição SQL, para listagem e
paginação, e como predicado sobre o objeto, para detalhe e vínculo — e
`tests/test_equipamento_compartilhado_postgres.py` roda a mesma matriz nas
duas, para que não se afastem.
"""

import uuid

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import Equipment, User


def compartilha_por_empresa() -> bool:
    return bool(get_settings().equipamento_por_empresa)


def escopo_do_cliente(cliente_id: uuid.UUID, empresa: uuid.UUID | None) -> ColumnElement[bool]:
    """A regra como condição de `WHERE`."""
    proprio = Equipment.owner_id == cliente_id
    if not compartilha_por_empresa() or empresa is None:
        return proprio
    return or_(
        proprio,
        and_(Equipment.company_id == empresa, Equipment.is_active.is_(True)),
    )


def cliente_enxerga(
    equipamento: Equipment, cliente_id: uuid.UUID, empresa: uuid.UUID | None
) -> bool:
    """A mesma regra, sobre um equipamento já carregado."""
    if equipamento.owner_id == cliente_id:
        return True
    if not compartilha_por_empresa() or empresa is None:
        return False
    return equipamento.company_id == empresa and bool(equipamento.is_active)


async def empresa_do_cliente(db: AsyncSession, cliente_id: uuid.UUID) -> uuid.UUID | None:
    """O vínculo oficial COMITADO do cliente, para LEITURA.

    O ator chega carregado no início da requisição; quem decide o que ele vê é
    o valor do banco. Com a flag desligada não há consulta nenhuma: a empresa
    não entra na regra, e o caminho fica exatamente o de antes.
    """
    if not compartilha_por_empresa():
        return None
    return (
        await db.execute(select(User.company_id).where(User.id == cliente_id))
    ).scalar_one_or_none()


async def trava_conta_e_le_empresa(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID | None:
    """`FOR KEY SHARE` na conta e, de volta, o vínculo oficial COMITADO dela.

    Para quem vai ESCREVER com base no vínculo (cadastrar aparelho, vincular
    aparelho a chamado). O vínculo e o desvínculo pegam a mesma linha com
    `FOR UPDATE`: ou esperam esta transação, ou ela os espera e lê o valor novo.
    """
    return (
        await db.execute(
            select(User.company_id)
            .where(User.id == user_id)
            .with_for_update(read=True, key_share=True)
        )
    ).scalar_one_or_none()
