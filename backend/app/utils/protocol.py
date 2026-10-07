"""
Automatic ticket protocol generator.

Format: HS-YYYY-NNNN  (e.g., HS-2026-0001)

Fonte da verdade: `ticket_protocol_counters`
---------------------------------------------
O próximo número sai do contador do ano — o último protocolo JÁ EMITIDO —, e
não do maior chamado que ainda existe. Até 10/2026 era `max()+1` sobre
`tickets`, e isso tinha dois defeitos:

1. **Reuso.** Apagar chamados devolvia números: com `tickets` vazia o próximo
   voltava a `HS-AAAA-0001`, e apagar o mais recente reusava o dele. O
   protocolo já tinha saído por e-mail e segue no texto de notificações que não
   fazem cascata com o chamado.
2. **Corrida.** Duas aberturas simultâneas liam o mesmo máximo e propunham o
   mesmo número; o índice único recusava uma delas, que gastava uma das cinco
   retentativas do `create_ticket`. Medido com o gerador antigo num Postgres
   efêmero: 10 aberturas simultâneas, 3 falharam depois das 5 tentativas; 20
   simultâneas, 13 falharam. Duplicata nunca houve — o índice único garantia
   isso —, mas o cliente recebia 500.

A alocação é UMA instrução atômica:

    INSERT ... VALUES (ano, piso + 1)
    ON CONFLICT (year) DO UPDATE SET last_number = maior(last_number + 1, piso + 1)
    RETURNING last_number

O `DO UPDATE` trava a linha do ano até o fim da transação. Quem chega depois
espera; se a primeira transação reverte, o incremento reverte junto e o número
volta — e nada foi emitido, porque o chamado e o e-mail (outbox) estão na
mesma transação. Não há lock no Redis: a corretude é do banco.

O piso
------
`piso` é o maior protocolo do ano presente em `tickets`. Ele só ELEVA o
contador, nunca o rebaixa, e existe por dois caminhos que gravam protocolo sem
passar por aqui: o contêiner antigo durante o deploy (a migration semeia o
contador e o código velho ainda abre chamados com `max()+1` até ser trocado), e
seed ou script avulso. Sem o piso, o contador proporia um número que já existe
e o índice único recusaria — o mesmo 500 de antes.

Ano
---
O ano é o do relógio em UTC, como sempre foi. Cada ano tem a sua linha, que
nasce no primeiro chamado dele; não existe virada a fazer.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Ticket

MAX_RETRIES = 5

# `CASE` em vez de `GREATEST`: o SQLite da suíte não tem `GREATEST`, e as duas
# formas dizem a mesma coisa. `excluded.last_number` é o `piso + 1` proposto.
_ALOCA = text(
    """
    INSERT INTO ticket_protocol_counters (year, last_number)
    VALUES (:ano, :proposto)
    ON CONFLICT (year) DO UPDATE SET last_number =
        CASE
            WHEN ticket_protocol_counters.last_number + 1 > excluded.last_number
                THEN ticket_protocol_counters.last_number + 1
            ELSE excluded.last_number
        END
    RETURNING last_number
    """
)


async def _maior_emitido_em_tickets(db: AsyncSession, prefix: str) -> int:
    """O piso: maior número do ano entre os chamados que existem, ou 0."""
    result = await db.execute(
        select(Ticket.protocol)
        .where(Ticket.protocol.like(f"{prefix}%"))
        # Comprimento primeiro, texto depois — NÃO só o texto.
        #
        # A sequência tem 4 dígitos, então a partir do 10.000º chamado do ano o
        # texto e o número discordam: 'HS-2026-9999' > 'HS-2026-10000' é
        # verdade em ordenação de texto. Com o comprimento na frente: sufixo
        # mais longo é número maior, e entre sufixos de mesmo comprimento a
        # ordem de texto já é a numérica. Um CAST do sufixo para inteiro seria
        # mais direto, mas estouraria no Postgres se uma linha com sufixo
        # não-numérico entrasse por fora do gerador.
        .order_by(func.length(Ticket.protocol).desc(), Ticket.protocol.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    if last is None:
        return 0
    sufixo = last.rsplit("-", 1)[-1]
    return int(sufixo) if sufixo.isdigit() else 0


async def generate_protocol(db: AsyncSession, agora: datetime | None = None) -> str:
    """Aloca e devolve o próximo protocolo do ano, na transação de `db`.

    O número fica reservado até a transação terminar: commit o emite, rollback
    o devolve. Chame na mesma transação que grava o chamado.
    """
    year = (agora or datetime.now(UTC)).year
    prefix = f"HS-{year}-"

    piso = await _maior_emitido_em_tickets(db, prefix)
    numero = (await db.execute(_ALOCA, {"ano": year, "proposto": piso + 1})).scalar_one()

    return f"{prefix}{numero:04d}"
