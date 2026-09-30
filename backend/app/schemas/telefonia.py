"""
Contratos da telefonia. O pedido de ligação é deliberadamente VAZIO.

O navegador não escolhe para quem se liga, de onde se liga nem por qual ramal:
o backend deriva tudo do banco, no instante da ação. Este arquivo é onde essa
frase vira contrato executável.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import ConfigDict, model_validator

from app.models.models import CallCreationStatus
from app.schemas.base import AppBaseModel


class TicketCallCreate(AppBaseModel):
    """Pedido de ligação: `{}` e nada mais.

    ⚠️ `extra="forbid"` é o PRIMEIRO do projeto, e é uma divergência deliberada
    do `AppBaseModel`, que roda com o `ignore` padrão do pydantic. Em todo
    schema da casa, campo desconhecido é descartado em silêncio e a resposta é
    200 — comportamento razoável para um formulário que evoluiu.

    Aqui não. Um corpo trazendo `phone`, `called`, `caller`, `extension`,
    `metadata`, `provider_call_id`, `client_id` ou `user_id` é alguém tentando
    escolher o destino da ligação. Ignorar seria seguro para o EFEITO — o
    destino continua vindo do banco — e péssimo para a DETECÇÃO: um front
    adulterado, um teste mal escrito ou uma tentativa real passariam
    despercebidos por meses. Com `forbid`, a tentativa vira 422, que é um
    evento observável.
    """

    model_config = ConfigDict(extra="forbid")


class MotivoPublicoDaRecusa(StrEnum):
    """Vocabulário do HelpHS para explicar uma recusa — não o do fornecedor.

    Existe um valor só, e isso é deliberado: só se traduz o que se sabe. A
    API4COM confirmou por escrito que **HTTP 424 significa ramal do operador
    offline ou indisponível** — o que inclui webphone fechado, desconectado ou
    deslogado, além de não registrado no SIP. Os outros 4xx continuam sem
    motivo público, porque inventar rótulo para eles seria publicar hipótese na
    tela de quem atende.

    ⚠️ O nome é `webphone_indisponivel`, e não `webphone_nao_registrado`, que
    foi o primeiro rótulo desta fase. "Não registrado" descrevia UMA das causas
    que o fornecedor listou; o motivo público tem de ser tão largo quanto o
    significado oficial, senão a tela afirma mais do que se sabe. A mensagem
    visual não mudou — ela já pedia a ação certa para qualquer dessas causas.

    ⚠️ Os valores são do HELPHS, não da API4COM. O número "424" não aparece
    aqui nem chega ao navegador: ele é contrato de terceiro, muda com o
    fornecedor, e trocá-lo por um nome nosso é o que permite trocar de
    fornecedor sem reescrever a tela.
    """

    webphone_indisponivel = "webphone_unavailable"


#: A tradução, num lugar só.
#:
#: Um dicionário e não uma cadeia de `if`: acrescentar um motivo, quando o
#: fornecedor documentar outro código, é uma linha aqui — e continua sendo
#: impossível espalhar `status_code == 424` pelo resto do sistema.
_MOTIVO_POR_HTTP_DO_FORNECEDOR: dict[int, MotivoPublicoDaRecusa] = {
    424: MotivoPublicoDaRecusa.webphone_indisponivel,
}


def motivo_publico(
    creation_status: str | None, provider_http_status: int | None
) -> MotivoPublicoDaRecusa | None:
    """Traduz o desfecho do fornecedor no motivo que a tela pode mostrar.

    Só RECUSA tem motivo. Um `confirmed` que por acaso guardasse um número, ou
    um `indeterminate`, não viram explicação: o mapa só vale quando o estado
    já é `rejected`. Sem isso, um 424 registrado numa transição futura
    explicaria a coisa errada.
    """
    if creation_status != CallCreationStatus.rejected.value:
        return None
    if provider_http_status is None:
        return None
    return _MOTIVO_POR_HTTP_DO_FORNECEDOR.get(provider_http_status)


class TicketCallResponse(AppBaseModel):
    """O que o navegador recebe de volta. Nada do fornecedor.

    Sem `provider_call_id`, sem telefone, sem `caller`, sem `extension`, sem
    metadata, sem corpo bruto e sem `provider_http_status`: o estado já carrega
    a decisão, e o resto é detalhe de fornecedor que a tela não usa.

    ⚠️ `reason` não é exceção a isso. Ele é vocabulário do HelpHS, DERIVADO do
    status do fornecedor e nunca igual a ele: a tela aprende "o webphone não
    está registrado", não "424".
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    creation_status: str
    created_at: datetime
    #: Opcional de propósito. A maioria das recusas não tem explicação
    #: publicável, e um front mais novo que um backend antigo precisa
    #: continuar funcionando sem o campo.
    reason: MotivoPublicoDaRecusa | None = None

    @model_validator(mode="before")
    @classmethod
    def _deriva_o_motivo(cls, dados: Any) -> Any:
        """Deriva o motivo a partir do objeto do ORM, sem expor a coluna.

        `mode="before"` porque é aqui que ainda se enxerga a linha inteira de
        `ticket_calls` — inclusive `provider_http_status`, que NÃO é campo
        deste schema e por isso nunca aparece no JSON.

        Fica no schema, e não na rota, para que nenhum caminho que serialize
        uma tentativa possa esquecer de traduzir: um endpoint futuro que
        devolva a mesma linha herda a tradução de graça.
        """
        if isinstance(dados, dict):
            return dados
        bruto = getattr(dados, "provider_http_status", None)
        estado = getattr(dados, "creation_status", None)
        return {
            "id": dados.id,
            "creation_status": estado,
            "created_at": dados.created_at,
            "reason": motivo_publico(estado, bruto),
        }
