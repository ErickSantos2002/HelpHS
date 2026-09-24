"""
Contratos da telefonia. O pedido de ligação é deliberadamente VAZIO.

O navegador não escolhe para quem se liga, de onde se liga nem por qual ramal:
o backend deriva tudo do banco, no instante da ação. Este arquivo é onde essa
frase vira contrato executável.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict

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


class TicketCallResponse(AppBaseModel):
    """O que o navegador recebe de volta. Nada do fornecedor.

    Sem `provider_call_id`, sem telefone, sem `caller`, sem `extension`, sem
    metadata, sem corpo bruto e sem `provider_http_status`: o estado já carrega
    a decisão, e o resto é detalhe de fornecedor que a tela não usa.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    creation_status: str
    created_at: datetime
