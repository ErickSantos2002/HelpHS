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
from unittest.mock import MagicMock, patch

import pytest
from loguru import logger

from app.core.logging import instalar_ponte_stdlib, setup_logging

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


# ── Valor de variável local não pode ser renderizado ─────────
#
# Outro caminho, e o patcher acima não alcança este. O `diagnose` do loguru
# acrescenta ao traceback o VALOR das variáveis locais de cada quadro. Uma
# função que tenha a credencial numa variável — montar um `Authorization`, por
# exemplo — passa a imprimir a credencial em qualquer exceção que atravesse
# aquele quadro.
#
# A redação de `_SEGREDO_NA_QUERY` reescreve `record["message"]`; o bloco de
# diagnóstico é montado pelo loguru DEPOIS, ao formatar a exceção. São caminhos
# diferentes, e por isso este grupo existe.
#
# Medido no loguru 0.7.3: `logger.add` tem `diagnose=True` por default, e o
# `setup_logging` não passava o parâmetro em nenhum dos três sinks.

_SEGREDO_EM_VARIAVEL = "credencial-que-so-existe-numa-variavel-local-7K3P"


def _monta_cabecalho_e_falha(token: str) -> dict:
    """Reproduz o risco real: a credencial numa variável, e a linha estoura.

    A linha que falha é a MESMA que referencia `token`, e isso é o ponto. O
    `diagnose` anota o valor das variáveis CITADAS na linha exibida de cada
    quadro — uma primeira versão deste teste levantava o erro numa linha que
    não mencionava a variável, o `diagnose=True` não anotava nada, e o teste
    passava sem provar coisa nenhuma.
    """
    return {"Authorization": token, "estoura": 1 // 0}


def _loga_excecao_com_segredo_na_pilha(**opcoes_do_sink) -> str:
    """Loga uma exceção com o segredo na pilha e devolve o texto formatado."""
    saida: list[str] = []
    sink = logger.add(lambda m: saida.append(str(m)), level="DEBUG", **opcoes_do_sink)
    try:
        try:
            _monta_cabecalho_e_falha(_SEGREDO_EM_VARIAVEL)
        except ZeroDivisionError:
            logger.exception("falha ao falar com o fornecedor")
    finally:
        logger.remove(sink)
    return "".join(saida)


def test_o_valor_de_variavel_local_nao_vai_para_o_traceback():
    """Com `diagnose=False`, o traceback mostra as linhas e não os valores."""
    texto = _loga_excecao_com_segredo_na_pilha(diagnose=False)

    assert "ZeroDivisionError" in texto, "o traceback sumiu junto com o diagnóstico"
    assert _SEGREDO_EM_VARIAVEL not in texto


def test_o_teste_acima_detectaria_a_volta_do_default():
    """Prova que o teste anterior tem dente.

    Sem isto, `diagnose=False` poderia estar sendo verificado contra uma saída
    que nunca renderizaria variável nenhuma, e o teste passaria por engano.
    """
    texto = _loga_excecao_com_segredo_na_pilha(diagnose=True)

    assert _SEGREDO_EM_VARIAVEL in texto


@pytest.mark.parametrize("ambiente", ["development", "production"])
def test_setup_logging_desliga_o_diagnostico_em_todos_os_sinks(ambiente):
    """Prende a configuração real, e não só o comportamento do loguru.

    Os dois ramos de `setup_logging` são percorridos: development instala dois
    sinks (stdout colorido e arquivo), produção instala um (stdout em JSON).
    Qualquer `logger.add` novo que esqueça o `diagnose=False` derruba isto.
    """
    ajustes = MagicMock()
    ajustes.log_level = "INFO"
    # O sink de arquivo nunca chega a ser criado: `logger.add` está trocado.
    ajustes.log_dir = "/caminho/que/nao/e/aberto"
    ajustes.is_development = ambiente == "development"

    with (
        patch("app.core.logging.get_settings", return_value=ajustes),
        patch("app.core.logging.instalar_ponte_stdlib"),
        patch("app.core.logging.logger.remove"),
        patch("app.core.logging.logger.add") as adicionar,
    ):
        setup_logging()

    assert adicionar.call_count >= 1
    for chamada in adicionar.call_args_list:
        assert (
            chamada.kwargs.get("diagnose") is False
        ), f"um sink de {ambiente} foi instalado sem diagnose=False"


# ══════════════════════════════════════════════════════════════
# DADO PESSOAL NO LOG DE E-MAIL
# ══════════════════════════════════════════════════════════════
#
# Os testes acima tratam de SEGREDO. Este grupo trata de DADO PESSOAL, que é
# problema diferente e chega pelo mesmo cano.
#
# Até 25/09/2026 o caminho de e-mail logava, em `INFO`:
#
#     Email sent to cliente@empresa.com.br: [HelpHS] Novo chamado HS-2026-0042
#     — Impressora da recepção sem conexão
#
# Endereço do cliente e TÍTULO DO CHAMADO, no log de produção, numa linha por
# e-mail. Enquanto não houve SMTP configurado nada disso saiu — a função retorna
# antes. Ligar o SMTP ligava o vazamento junto, e era o mesmo restart.
#
# O `patcher` de `logging.py` não alcança isto: ele apaga token de QUERY STRING,
# e aqui o dado vem interpolado no texto da mensagem.
#
# ⚠️ E `str(exc)` também carrega endereço. Medido no aiosmtplib 3.0.2:
# `SMTPSenderRefused` leva o remetente, `SMTPRecipientRefused` e
# `SMTPRecipientsRefused` levam o DESTINATÁRIO. É por isso que o log passou a
# registrar a CLASSE do erro e o código numérico, nunca a mensagem.

_ENDERECO = "cliente.real@empresa.com.br"
_TITULO_DO_CHAMADO = "Impressora da recepcao sem conexao"
_ASSUNTO = f"[HelpHS] Novo chamado HS-2026-0042 - {_TITULO_DO_CHAMADO}"
_SENHA_SMTP = "re_CHAVE-FALSA-DE-TESTE-9Q2W"

# O que NUNCA pode aparecer numa linha de log do caminho de e-mail.
_PROIBIDO = {
    "endereço do destinatário": _ENDERECO,
    "título do chamado": _TITULO_DO_CHAMADO,
    "assunto do e-mail": _ASSUNTO,
    "senha do SMTP": _SENHA_SMTP,
}


def _dado_pessoal_em(linhas: list[str]) -> list[str]:
    """Quais fragmentos proibidos aparecem nas linhas. Vazio = limpo.

    Devolve o NOME do fragmento, e não o valor: a mensagem de falha do pytest
    vai para o terminal, e o terminal costuma virar print no chat.
    """
    texto = "\n".join(linhas)
    return [nome for nome, valor in _PROIBIDO.items() if valor in texto]


def _settings_com_smtp():
    from app.core.config import Settings

    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        smtp_from_email="naoresponda@test.com",
        smtp_user="naoresponda@test.com",
        smtp_password=_SENHA_SMTP,
    )


async def _envia_capturando(erro: BaseException | None = None, **extras) -> list[str]:
    """Roda `send_email` com o sink instalado e devolve as linhas logadas."""
    from unittest.mock import AsyncMock

    from app.services import email as servico

    linhas, sink = _captura()
    enviar = AsyncMock(side_effect=erro) if erro else AsyncMock()
    try:
        with patch.object(servico.FastMail, "send_message", new=enviar):
            await servico.send_email(
                to_email=_ENDERECO,
                subject=_ASSUNTO,
                body="corpo",
                settings=_settings_com_smtp(),
                **extras,
            )
    finally:
        logger.remove(sink)
    return linhas


# ── O detector tem dente ──────────────────────────────────────


def test_o_detector_de_dado_pessoal_pegaria_o_formato_antigo():
    """Prova que os testes abaixo não passam por vacuidade.

    Reproduz as duas linhas que existiam antes da correção. Se `_dado_pessoal_em`
    não as acusasse, todo teste deste grupo passaria sem verificar nada.
    """
    antigas = [
        f"Email sent to {_ENDERECO}: {_ASSUNTO}",
        f"Failed to send email to {_ENDERECO}: algum erro",
    ]

    achados = _dado_pessoal_em(antigas)
    assert "endereço do destinatário" in achados
    assert "assunto do e-mail" in achados
    assert "título do chamado" in achados


# ── Sucesso ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_o_log_de_entrega_aceita_nao_leva_endereco_nem_assunto():
    linhas = await _envia_capturando()

    assert linhas, "o envio bem-sucedido deixou de registrar qualquer linha"
    assert not _dado_pessoal_em(linhas), _dado_pessoal_em(linhas)


@pytest.mark.asyncio
async def test_o_log_de_entrega_ainda_diz_que_deu_certo():
    """Remover dado pessoal não pode virar remover informação operacional."""
    linhas = await _envia_capturando()

    texto = " ".join(linhas).lower()
    assert "accepted" in texto or "delivered" in texto or "sent" in texto


# ── Falha ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_o_log_de_falha_nao_leva_o_endereco_que_a_excecao_carrega():
    """O caso mais traiçoeiro: o endereço vem de DENTRO da exceção.

    `SMTPRecipientRefused` guarda o destinatário e o expõe no `str()`. Logar
    `{exc}` põe o endereço do cliente no log sem ninguém escrever `{to_email}`.
    """
    from aiosmtplib.errors import SMTPRecipientRefused

    linhas = await _envia_capturando(
        erro=SMTPRecipientRefused(550, "mailbox unavailable", _ENDERECO)
    )

    assert linhas, "a falha deixou de registrar qualquer linha"
    assert not _dado_pessoal_em(linhas), _dado_pessoal_em(linhas)


@pytest.mark.asyncio
async def test_o_log_de_falha_diz_a_classe_e_o_codigo_do_servidor():
    """O que sobra tem de bastar para diagnosticar.

    A classe separa "não conectou" de "credencial recusada"; o código separa
    535 (credencial) de 550 (domínio não verificado) e de 421 (tente depois).
    O código é inteiro do protocolo, não texto de servidor.
    """
    from aiosmtplib.errors import SMTPAuthenticationError

    linhas = await _envia_capturando(
        erro=SMTPAuthenticationError(535, "Authentication credentials invalid")
    )

    texto = " ".join(linhas)
    assert "SMTPAuthenticationError" in texto
    assert "535" in texto


@pytest.mark.asyncio
async def test_o_log_de_falha_nao_leva_a_mensagem_do_servidor():
    """Texto de servidor é conteúdo variável: hoje é inócuo, amanhã não."""
    from aiosmtplib.errors import SMTPAuthenticationError

    linhas = await _envia_capturando(erro=SMTPAuthenticationError(535, f"rejected for {_ENDERECO}"))

    assert "rejected for" not in " ".join(linhas)


@pytest.mark.asyncio
async def test_a_senha_do_smtp_nunca_aparece_no_log():
    """Regressão da conclusão da auditoria: credencial não vaza por este caminho.

    Exercita os dois ramos — aceito e recusado — porque a senha está no
    `Settings` dos dois.
    """
    from aiosmtplib.errors import SMTPAuthenticationError

    aceito = await _envia_capturando()
    recusado = await _envia_capturando(erro=SMTPAuthenticationError(535, "nope"))

    assert _SENHA_SMTP not in " ".join(aceito + recusado)


# ── SMTP desligado ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_o_log_de_smtp_desligado_nao_leva_o_endereco():
    from unittest.mock import AsyncMock

    from app.core.config import Settings
    from app.services import email as servico

    sem_smtp = Settings(database_url="postgresql+asyncpg://u:p@localhost/db")

    linhas, sink = _captura()
    try:
        with patch.object(servico.FastMail, "send_message", new=AsyncMock()):
            await servico.send_email(_ENDERECO, _ASSUNTO, "corpo", sem_smtp)
    finally:
        logger.remove(sink)

    assert not _dado_pessoal_em(linhas), _dado_pessoal_em(linhas)


# ── A notificação mantém o id ─────────────────────────────────


@pytest.mark.asyncio
async def test_o_log_da_notificacao_mantem_o_id_e_perde_o_endereco():
    """`notif_id` é o identificador interno — ele FICA, o endereço sai.

    É o que permite achar a notificação no banco sem que o log carregue para
    quem ela foi.
    """
    import uuid
    from unittest.mock import AsyncMock

    from app.services import notifications

    notif_id = uuid.uuid4()
    pendente = notifications._EmailPendente(
        notif_id=notif_id,
        to_email=_ENDERECO,
        subject=_ASSUNTO,
        body="corpo",
        html="<p>corpo</p>",
        settings=_settings_com_smtp(),
    )

    linhas, sink = _captura()
    try:
        with patch.object(notifications, "send_email", new=AsyncMock(return_value=True)):
            await notifications._send_and_log(pendente)
    finally:
        logger.remove(sink)

    texto = " ".join(linhas)
    assert str(notif_id) in texto, "o id da notificação saiu do log junto com o endereço"
    assert not _dado_pessoal_em(linhas), _dado_pessoal_em(linhas)


@pytest.mark.asyncio
async def test_o_log_da_notificacao_nao_entregue_tambem_perde_o_endereco():
    import uuid
    from unittest.mock import AsyncMock

    from app.services import notifications

    notif_id = uuid.uuid4()
    pendente = notifications._EmailPendente(
        notif_id=notif_id,
        to_email=_ENDERECO,
        subject=_ASSUNTO,
        body="corpo",
        html="<p>corpo</p>",
        settings=_settings_com_smtp(),
    )

    linhas, sink = _captura()
    try:
        with patch.object(notifications, "send_email", new=AsyncMock(return_value=False)):
            await notifications._send_and_log(pendente)
    finally:
        logger.remove(sink)

    assert str(notif_id) in " ".join(linhas)
    assert not _dado_pessoal_em(linhas), _dado_pessoal_em(linhas)


# ── E-mail de conta: evento, não endereço ─────────────────────


@pytest.mark.asyncio
async def test_o_email_de_conta_registra_o_evento_e_nao_o_destinatario():
    """E-mail de conta não tem `notif_id`, então o log diz QUE EVENTO foi.

    Sem isso a linha de transporte seria indistinguível entre confirmação de
    cadastro e redefinição de senha — e é a ÚNICA linha que esses três têm,
    porque o `auth.py` só registra o enfileiramento, nunca o desfecho.
    """
    from unittest.mock import AsyncMock

    from app.services import account_emails

    linhas, sink = _captura()
    try:
        with patch.object(account_emails, "send_email", new=AsyncMock(return_value=True)) as enviar:
            await account_emails.send_password_reset_email(
                _ENDERECO, "Welton", "token-de-teste-123", _settings_com_smtp()
            )
    finally:
        logger.remove(sink)

    # O `contexto` é o que o `send_email` vai logar, e ele não pode ser o endereço.
    contexto = enviar.await_args.kwargs.get("contexto", "")
    assert contexto, "o e-mail de conta não disse ao `send_email` que evento é"
    assert _ENDERECO not in contexto
    assert not _dado_pessoal_em(linhas + [contexto]), _dado_pessoal_em(linhas + [contexto])
