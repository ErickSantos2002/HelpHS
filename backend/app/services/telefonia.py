"""
Memória das tentativas de ligação. Não fala com o fornecedor.

Este módulo escreve e lê `ticket_calls`, e **não importa `httpx` nem
`api4com.py`**. A separação é a mesma que a Helô já usa entre
`helo_embedding.py` (o cliente do serviço) e `helo.py` (a regra): transporte de
um lado, domínio do outro. Aqui o domínio é ainda menor — é só estado.

Quem orquestra `banco → API4COM → banco` é a Fase 2C, quando existir endpoint.
Enquanto isso, cada função abaixo é testável sem rede nenhuma, e é exatamente
por isso que elas existem antes da orquestração: a máquina de estados fica
provada antes de haver efeito externo para depurar junto.

O ciclo
-------
Uma tentativa nasce ``pending`` — a linha existe **antes** de a requisição
sair. Não é zelo de contabilidade: se o processo morrer entre o `POST` e a
resposta, sem a linha prévia não haveria sequer registro de que alguém tentou.

Dali ela vai para exatamente um destino, e cada um responde à mesma pergunta
que o `api4com.py` responde — **a chamada saiu?**

- ``confirmed``     HTTP 200 com `id` legível. Saiu, e temos o identificador.
- ``rejected``      4xx. O fornecedor recusou a requisição.
- ``unavailable``   não houve comunicação HTTP útil.
- ``indeterminate`` ⚠️ pode ter tocado o telefone de alguém.

`indeterminate` é o estado que justifica a tabela inteira. Ele é o que a
reconciliação da 2D vai procurar, e o que impede uma segunda tentativa às
cegas.

O que NÃO entra aqui
--------------------
Telefone, `caller`, `extension`, corpo de requisição, corpo de resposta,
`message` do fornecedor, metadata, URL de gravação. Nenhuma função aceita esses
dados, então não há como persistí-los por descuido — a ausência de parâmetro é
a garantia, não a disciplina de quem chamar.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import CallCreationStatus, TicketCall


async def registra_tentativa(
    db: AsyncSession,
    *,
    ticket_id: uuid.UUID,
    initiated_by_id: uuid.UUID | None,
) -> TicketCall:
    """Cria a linha `pending`, ANTES de qualquer conversa com o fornecedor.

    Devolve a tentativa já com `id` atribuído — é esse UUID interno que a Fase
    2C poderá mandar no `metadata` da chamada para reconciliar o webhook com a
    linha. (Ainda NÃO mandamos: o payload da 2A segue só com `gateway`.)
    """
    tentativa = TicketCall(
        ticket_id=ticket_id,
        initiated_by_id=initiated_by_id,
        creation_status=CallCreationStatus.pending.value,
    )
    db.add(tentativa)
    await db.flush()
    return tentativa


async def marca_em_despacho(db: AsyncSession, tentativa: TicketCall) -> TicketCall:
    """`pending → dispatching`: a fronteira do efeito externo.

    ⚠️ Quem chamar isto precisa **COMMITAR antes** de emitir o `POST /calls`.
    Não é detalhe de estilo: o estado só protege se estiver durável no banco
    quando o processo morrer. Gravado e não commitado, some no rollback e a
    linha volta a ser um `pending` ambíguo — exatamente o problema que este
    estado existe para resolver.

    Na Fase 2C.2 esta função existe e é testada, mas NÃO é exercida pelo
    orquestrador: aquela fase termina no `pending`, sem tocar no fornecedor. A
    chamada daqui entra na fase seguinte, na linha imediatamente anterior ao
    `create_call`.
    """
    tentativa.creation_status = CallCreationStatus.dispatching.value
    await db.flush()
    return tentativa


async def confirma(
    db: AsyncSession,
    tentativa: TicketCall,
    *,
    provider_call_id: str,
    provider_http_status: int,
) -> TicketCall:
    """A chamada existe do lado de lá, e este é o identificador dela.

    `provider_call_id` é gravado **exatamente como chegou**: sem `strip`, sem
    caixa alterada, sem validação de formato. O fornecedor documenta o tipo
    como `string` e mostra dois formatos diferentes para o mesmo campo; quem
    normalizasse aqui inventaria um terceiro.
    """
    tentativa.provider_call_id = provider_call_id
    tentativa.provider_http_status = provider_http_status
    tentativa.creation_status = CallCreationStatus.confirmed.value
    await db.flush()
    return tentativa


async def marca_recusada(
    db: AsyncSession,
    tentativa: TicketCall,
    *,
    provider_http_status: int,
) -> TicketCall:
    """4xx: o fornecedor respondeu recusando. O status é obrigatório aqui.

    É a única transição de falha em que sabemos o número — e saber que foi 401
    e não 422 é a diferença entre "o token caiu" e "o número não serve".
    """
    tentativa.provider_http_status = provider_http_status
    tentativa.creation_status = CallCreationStatus.rejected.value
    await db.flush()
    return tentativa


async def marca_indisponivel(db: AsyncSession, tentativa: TicketCall) -> TicketCall:
    """Não houve comunicação HTTP útil.

    **Não recebe status HTTP**, e a assinatura é a garantia: não houve resposta,
    então não há número para gravar. Inventar um zero ou um 503 aqui faria o
    banco afirmar que o fornecedor respondeu algo.
    """
    tentativa.creation_status = CallCreationStatus.unavailable.value
    await db.flush()
    return tentativa


async def marca_indeterminada(
    db: AsyncSession,
    tentativa: TicketCall,
    *,
    provider_http_status: int | None = None,
) -> TicketCall:
    """⚠️ Pode ter tocado o telefone de alguém, e não sabemos.

    `provider_http_status` é opcional porque o indeterminado chega por dois
    caminhos: com resposta (5xx, 3xx, 200 sem `id`) e sem resposta nenhuma
    (`ReadTimeout`). A ausência do número é informação, não lacuna.

    `provider_call_id` **não é tocado** de propósito: continua nulo, e é essa
    ausência que a reconciliação vai procurar.
    """
    if provider_http_status is not None:
        tentativa.provider_http_status = provider_http_status
    tentativa.creation_status = CallCreationStatus.indeterminate.value
    await db.flush()
    return tentativa
