"""O canal por fora do processo que faz o chat funcionar com mais de um worker.

Hoje o `ConnectionManager` guarda as salas na memória DO PROCESSO. Com dois
workers, duas pessoas no mesmo chamado caem em processos diferentes e param de
se ver — sem erro, sem log, sem nada: as mensagens continuam sendo gravadas
corretamente e só o tempo real some. É por isso que o `start.sh` fixa
`--workers 1`.

Este módulo não importa nada de `app.routers.chat`. Quem entrega é uma callable
recebida por parâmetro, e a identidade de quem publicou também vem de fora —
assim o laço não sabe o que é uma sala, e o `chat.py` não sabe o que é um canal.

**A origem NÃO é global de módulo, e isso é o desenho, não um detalhe.** Com um
global, dois `ConnectionManager` do mesmo processo dividiriam o carimbo, a
supressão de eco descartaria a mensagem que deveria atravessar, e não haveria
como escrever o teste de entrega entre processos — justamente a propriedade que
justifica o módulo existir.

Redis fora do ar não pode piorar o que já funciona: hoje o chat não depende de
Redis nenhum. O `publicar` engole a falha e o assinante fica reassinando calado.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from app.core.redis import get_redis

# Um canal só, com o chamado dentro do envelope. Canal por chamado obrigaria
# SUBSCRIBE/UNSUBSCRIBE dentro do `connect`/`disconnect` do ConnectionManager —
# que são síncronos —, metendo chamada de rede no aperto de mão do WebSocket,
# que hoje não depende do Redis. O custo do canal único é cada worker decodificar
# um JSON pequeno e descartar o que não é seu.
CANAL = "helphs:chat"

# Quanto esperar antes de reassinar. Sobrescrito nos testes.
ESPERA_RECONEXAO = 5.0

_assinado = False

Entregar = Callable[[str, dict[str, Any]], Awaitable[None]]


def assinatura_ativa() -> bool:
    """Se a inscrição deste processo está de pé agora. Vai para o readiness."""
    return _assinado


async def publicar(origem: str, ticket_id: str, payload: dict[str, Any]) -> None:
    """Empurra a mensagem para os outros workers. Nunca levanta.

    É best-effort de propósito: a entrega local já aconteceu quando isto roda, e
    derrubar o envio de uma mensagem porque o Redis piscou seria trocar um chat
    degradado por um chat quebrado.
    """
    envelope = json.dumps({"origem": origem, "ticket_id": ticket_id, "payload": payload})
    try:
        redis = await get_redis()
        await redis.publish(CANAL, envelope)
    except Exception as exc:  # noqa: BLE001 — ver docstring
        logger.debug(f"Backplane do chat: publish falhou, seguindo local: {exc}")


async def _entregar_um(bruto: str, entregar: Entregar, origem: str) -> None:
    try:
        envelope = json.loads(bruto)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Backplane do chat: envelope ilegível, descartado")
        return

    # Eco: este processo já entregou localmente antes de publicar.
    if envelope.get("origem") == origem:
        return

    ticket_id = envelope.get("ticket_id")
    payload = envelope.get("payload")
    if not ticket_id or not isinstance(payload, dict):
        return

    try:
        await entregar(str(ticket_id), payload)
    except Exception as exc:  # noqa: BLE001 — uma sala ruim não derruba o laço
        logger.warning(f"Backplane do chat: entrega local falhou: {exc}")


async def _laco(entregar: Entregar, origem: str) -> None:
    global _assinado
    ja_avisou_da_queda = False

    while True:
        try:
            redis = await get_redis()
            async with redis.pubsub() as canal:
                await canal.subscribe(CANAL)
                _assinado = True
                if ja_avisou_da_queda:
                    logger.info("Backplane do chat: assinatura restabelecida")
                    ja_avisou_da_queda = False
                else:
                    logger.info(f"Backplane do chat assinado em {CANAL}")

                async for bruto in canal.listen():
                    if bruto.get("type") == "message":
                        await _entregar_um(bruto["data"], entregar, origem)
        except asyncio.CancelledError:
            # Redundante desde o 3.8, escrito de propósito: sinaliza para quem
            # for alargar o `except` abaixo que o shutdown depende disto.
            _assinado = False
            raise
        except Exception as exc:  # noqa: BLE001
            # Só na TRANSIÇÃO. Uma linha por tentativa, a cada poucos segundos,
            # transforma uma queda de Redis numa inundação — e o log que deveria
            # denunciar o problema vira o problema.
            if not ja_avisou_da_queda:
                logger.warning(
                    f"Backplane do chat caiu; reassinando a cada {ESPERA_RECONEXAO}s: {exc}"
                )
                ja_avisou_da_queda = True
        finally:
            _assinado = False

        await asyncio.sleep(ESPERA_RECONEXAO)


def start_chat_backplane(entregar: Entregar, origem: str) -> asyncio.Task:
    """Sobe o assinante deste processo. Mesmo formato do auto-close worker."""
    return asyncio.create_task(_laco(entregar, origem), name="chat-backplane")
