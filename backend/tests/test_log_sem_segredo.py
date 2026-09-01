"""Segredo não entra no log — em especial o token do WebSocket.

O navegador não deixa mandar cabeçalho no WebSocket, então o JWT viaja na query
string. Solução padrão e correta. O problema é o que vem depois: o uvicorn
registra a linha de acesso com a **URL inteira**, a ponte para o loguru
repassava com `record.getMessage()` sem tocar no texto, e o sink de produção
serializa aquilo em JSON no stdout — que vai para o painel de logs.

Reproduzido contra o uvicorn instalado, antes desta correção::

    INFO: ('127.0.0.1', 63616) - "WebSocket /ws/tickets/abc123
          ?token=eyJhbGciOiJSUzI1NiJ9.<carga>.<assinatura>" [accepted]

Quem lê logs é, tipicamente, mais gente do que quem lê o banco. Com o token em
mãos, essa pessoa personifica o dono da sessão por até oito horas — sem senha e
sem passar pelo segundo fator.

A regra que o projeto já tinha escrita e que isto passou a cumprir: **não logar
Authorization, senha, JWT, TOTP, segredo de MFA nem refresh token.**

A redação mora no `patcher`, e não na ponte, de propósito: o patcher roda em
TODA linha — as nossas e as que vêm do uvicorn. Consertar só a ponte deixaria
a porta aberta para o dia em que alguém escrevesse `logger.info(f"... {url}")`
com uma URL assinada dentro.
"""

import logging

from loguru import logger

from app.core.logging import instalar_ponte_stdlib

_TOKEN = "eyJhbGciOiJSUzI1NiJ9.cargaUtilQueNaoPodeVazar.assinaturaSecreta"


def _captura() -> tuple[list[str], int]:
    """Sink que guarda a mensagem final, já passada pelo patcher."""
    linhas: list[str] = []
    sink = logger.add(lambda m: linhas.append(m.record["message"]), level="DEBUG")
    return linhas, sink


# ── O caso real ───────────────────────────────────────────────


def test_a_linha_de_acesso_do_uvicorn_nao_leva_o_token():
    """O caso que motivou tudo: WebSocket aceito, com o JWT na query."""
    # A ponte troca os handlers da raiz do `logging`. Sem devolver o estado, ela
    # sobrevive ao teste e, no encerramento do interpretador, o `logging` emite
    # sua última linha por um sink do loguru que o pytest já fechou — o que
    # enche a saída da suíte de "I/O operation on closed file".
    raiz = logging.getLogger()
    handlers_originais = list(raiz.handlers)
    nivel_original = raiz.level

    instalar_ponte_stdlib()
    linhas, sink = _captura()
    try:
        logging.getLogger("uvicorn.access").info(
            '("127.0.0.1", 63616) - "WebSocket /api/v1/ws/tickets/abc?token=%s" [accepted]',
            _TOKEN,
        )
    finally:
        logger.remove(sink)
        raiz.handlers = handlers_originais
        raiz.setLevel(nivel_original)

    assert linhas, "a ponte parou de encaminhar as linhas do uvicorn"
    texto = "\n".join(linhas)
    assert _TOKEN not in texto
    assert "cargaUtilQueNaoPodeVazar" not in texto
    assert "assinaturaSecreta" not in texto


# ── Cobre também o que nós mesmos escrevemos ──────────────────


def test_token_em_linha_nossa_tambem_e_apagado():
    """O patcher pega tudo, não só o que vem da ponte."""
    linhas, sink = _captura()
    try:
        logger.info(f"tentando /ws/tickets/1?token={_TOKEN}")
    finally:
        logger.remove(sink)

    assert _TOKEN not in "\n".join(linhas)


def test_apaga_as_outras_grafias_de_segredo_na_query():
    linhas, sink = _captura()
    try:
        logger.info(f"/x?access_token={_TOKEN}&outro=1")
        logger.info(f"/x?refresh_token={_TOKEN}")
        logger.info(f"/x?a=1&TOKEN={_TOKEN}")  # maiúsculas
    finally:
        logger.remove(sink)

    assert _TOKEN not in "\n".join(linhas)
    assert len(linhas) == 3


# ── Não pode apagar demais ────────────────────────────────────


def test_nao_mexe_em_linha_sem_segredo():
    """Redação que come log normal é pior que o problema que resolve."""
    linhas, sink = _captura()
    original = '("127.0.0.1", 1) - "GET /api/v1/tickets?status=open&limit=50" 200'
    try:
        logger.info(original)
    finally:
        logger.remove(sink)

    assert linhas[-1] == original


def test_preserva_o_que_vem_depois_do_token_na_query():
    """Apagar até o fim da linha levaria junto parâmetros úteis ao diagnóstico."""
    linhas, sink = _captura()
    try:
        logger.info(f"/api/v1/ws/tickets/abc?token={_TOKEN}&limit=50")
    finally:
        logger.remove(sink)

    saida = linhas[-1]
    assert _TOKEN not in saida
    assert "limit=50" in saida, "a redação comeu o resto da query"
    assert "/api/v1/ws/tickets/abc" in saida, "a redação comeu o caminho"


def test_o_nome_do_parametro_sobrevive_a_redacao():
    """O log tem que continuar dizendo que HAVIA um token ali.

    Apagando `?token=` junto com o valor, a linha vira
    `/ws/tickets/abc[REDIGIDO]&limit=50` — e quem investiga não distingue
    "token redigido" de "parâmetro estranho no meio da URL". Foi exatamente o
    que aconteceu na primeira tentativa desta correção: a substituição perdeu a
    retrorreferência e comeu o nome do parâmetro. Os outros testes passaram
    assim mesmo, porque só olhavam a ausência do segredo.
    """
    linhas, sink = _captura()
    try:
        logger.info(f"/api/v1/ws/tickets/abc?token={_TOKEN}&limit=50")
    finally:
        logger.remove(sink)

    assert "token=[REDIGIDO]" in linhas[-1], (
        "a redação apagou o nome do parâmetro junto com o valor; a linha "
        f"saiu como {linhas[-1]!r}"
    )


# ── O que já funcionava tem que continuar funcionando ─────────


def test_o_carimbo_de_request_id_sobrevive_a_redacao():
    """O patcher fazia uma coisa só; agora faz duas. A primeira não pode cair."""
    capturado: list[dict] = []
    sink = logger.add(lambda m: capturado.append(dict(m.record["extra"])), level="DEBUG")
    try:
        logger.info(f"linha qualquer com ?token={_TOKEN}")
    finally:
        logger.remove(sink)

    assert capturado, "o log parou de funcionar"
    assert "request_id" in capturado[-1], "o carimbo do request_id sumiu"
