"""
O histórico do chamado — uma linha por mudança, e um só lugar que a escreve.

Morava em `app/routers/tickets.py` como função privada, e ficou impossível
quando a Helô passou a precisar dela: `tickets.py` importa
`app.services.helo`, então a Helô importando de volta seria ciclo. As saídas
eram duplicar o corpo num segundo lugar ou trazê-lo para cá. Duplicar regra é
o defeito que este projeto já pagou caro — doze cópias de "é seu?" espalhadas
em quatro arquivos —, e o histórico é o tipo de coisa em que duas versões
divergem em silêncio: uma grava `comment`, a outra esquece, e ninguém percebe
até alguém procurar por que a IA saiu de um chamado.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import TicketHistory


def registra_historico(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    # Nulo quando quem agiu foi o sistema — a Helô movendo o chamado para "Em
    # andamento", ou saindo dele. A coluna já aceitava (`TicketHistory.user_id`
    # é nullable); só a anotação era estreita demais.
    user_id: uuid.UUID | None,
    field: str,
    # Aceita UUID porque vários campos de histórico são id: o corpo faz `str()`
    # antes de gravar, então a anotação estreita era a única coisa errada.
    old_value: str | uuid.UUID | None,
    new_value: str | uuid.UUID | None,
    comment: str | None = None,
) -> None:
    db.add(
        TicketHistory(
            id=uuid.uuid4(),
            ticket_id=ticket_id,
            user_id=user_id,
            field=field,
            old_value=str(old_value) if old_value is not None else None,
            new_value=str(new_value) if new_value is not None else None,
            comment=comment,
        )
    )
