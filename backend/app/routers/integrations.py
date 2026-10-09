"""
Integrações de entrada. Nenhuma rota aqui é usada por gente.

Este é o primeiro router do HelpHS que não autentica por sessão. Todos os
outros recebem um `current_user` de `get_current_user` e decidem por papel; aqui
não há usuário, não há papel e não há `Authorization` — há um segredo
compartilhado, validado por `core/integracao.py`.

A separação é deliberada. Misturar uma rota de integração entre as rotas de
domínio convidaria, em alguma revisão futura, a "consertar" o acesso
acrescentando `get_current_user` — e isso transformaria a porta de máquina numa
rota aberta a qualquer usuário autenticado, `client` incluído.

O que NÃO entra em nenhuma rota deste arquivo: telefone, `caller`, `called`,
e-mail, `record_url`, áudio, transcrição, token de fornecedor e payload bruto.
O recorte é feito por quem encaminha, e o `extra="forbid"` do schema garante que
um campo a mais vire 422 observável em vez de passar em silêncio.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.integracao import exige_segredo_de_integracao
from app.schemas.telefonia import EventoDeEncerramento
from app.services import telefonia

router = APIRouter(tags=["Integrations"])


def _cauda(valor: uuid.UUID) -> str:
    """Últimos 6 caracteres do id, para o log poder identificar sem expor.

    Um UUID inteiro em log não é segredo, mas também não é necessário: a cauda
    basta para cruzar com o banco durante uma investigação, e mantém a linha de
    log inútil para quem não tem acesso ao banco.
    """
    return f"...{str(valor)[-6:]}"


@router.post(
    "/integrations/telefonia/call-ended",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(exige_segredo_de_integracao)],
    summary="Registra o desfecho de uma chamada encerrada",
)
async def registra_chamada_encerrada(
    evento: EventoDeEncerramento,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Recebe o evento de encerramento e grava o desfecho. Idempotente.

    O caminho é `telefonia`, e não o nome do fornecedor, de propósito: o contrato
    é interno. Hoje o evento chega encaminhado por um orquestrador externo que
    recorta o payload do webhook da API4COM; amanhã pode chegar de outro lugar, e
    a URL do HelpHS não deveria mudar por isso.

    ⚠️ A autenticação está em `dependencies=[...]`, e não como parâmetro. É
    deliberado: a dependência não devolve ator nenhum, e recebê-la num parâmetro
    nomeado sugeriria que há um "quem" a consultar. Não há.

    Desfechos:

    * **204** — evento registrado, ou evento duplicado. O cliente não distingue
      os dois, e é isso que se quer: uma reentrega não deve parecer erro, nem
      provocar nova tentativa.
    * **401** — segredo ausente, vazio ou incorreto.
    * **404** — não existe `ticket_call` com esse id. Separado do duplicado de
      propósito: é o sinal de que a integração encaminhou evento que não é nosso.
    * **422** — id que não é UUID, ou campo a mais no corpo.
    """
    resultado = await telefonia.registra_encerramento(
        db,
        ticket_call_id=evento.ticket_call_id,
        duration_seconds=evento.duration,
        hangup_cause=evento.hangup_cause,
        recording_available=evento.recording_available,
    )

    if resultado is telefonia.ResultadoDoEncerramento.inexistente:
        # Sem `commit`: nada foi escrito, e não há o que persistir.
        logger.warning(
            "evento de encerramento para ticket_call inexistente: {}",
            _cauda(evento.ticket_call_id),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tentativa de ligação não encontrada.",
        )

    if resultado is telefonia.ResultadoDoEncerramento.duplicado:
        logger.info(
            "evento de encerramento duplicado, nada alterado: {}",
            _cauda(evento.ticket_call_id),
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    await db.commit()
    # O que esta linha carrega, e nada além: a cauda do id, a duração e a causa
    # do fornecedor. Sem telefone, sem `caller`, sem `called`, sem `record_url`,
    # sem o corpo da requisição e sem o segredo.
    logger.info(
        "encerramento registrado: {} duracao={} causa={}",
        _cauda(evento.ticket_call_id),
        evento.duration,
        evento.hangup_cause,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
