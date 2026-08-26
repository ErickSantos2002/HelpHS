"""
Helô — o atendimento por IA que fala com o cliente.

Fase 1: acolher e triar. Ela não resolve problema técnico, não promete prazo e
não continua a conversa depois de entregar o chamado para um humano.

Este módulo começa pelo interruptor, e não pela conversa, de propósito: uma IA
que fala com cliente sem ter como ser calada é a única parte disto que não tem
volta. Ver o desenho em
`docs/superpowers/specs/2026-08-11-helo-atendimento-ia-design.md`.
"""

from app.core.config import get_settings
from app.models.models import Ticket, User

# Por que uma função e não três `if` espalhados: a mesma pergunta — "a Helô
# pode falar aqui?" — vai ser feita na criação do chamado, na resposta do
# cliente e em qualquer entrada futura. Copiada, ela vira as doze cópias de
# `ensure_ticket_visible` que custaram uma rodada inteira para reunir.


def helo_pode_falar(ticket: Ticket, cliente: User) -> bool:
    """
    Os três níveis de desligamento, em conjunção.

    Qualquer chave desligada cala a Helô. **Não existe religar num nível mais
    específico**: o técnico não reativa a IA num chamado de cliente que pediu
    para não ser atendido por robô, e a flag global vence os dois. É a única
    semântica em que "eu desliguei" continua verdade depois — com precedência
    invertida, quem desligou precisaria vigiar os outros níveis para sempre.

    Args:
        ticket: o chamado em questão — `ai_enabled` é o interruptor do técnico.
        cliente: o autor do chamado — `ai_enabled` é a preferência dele (ou da
            empresa dele, quando o nível por CNPJ existir).

    Returns:
        True quando os três níveis estão ligados.
    """
    if not get_settings().helo_enabled:
        return False
    if not ticket.ai_enabled:
        return False
    return bool(cliente.ai_enabled)
