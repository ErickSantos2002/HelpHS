"""
Fase 3A — testes que não precisam de PostgreSQL: a política de backoff, a
classificação de falha SMTP, e o `enqueue_email` (que só toca a sessão que
recebe, nunca abre uma própria — testável com uma sessão fake).

Testes que dependem de `FOR UPDATE SKIP LOCKED`, `UNIQUE`, `ON DELETE CASCADE`
ou de concorrência real estão em `test_email_outbox_postgres.py`.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from loguru import logger

from app.core.config import Settings
from app.services.email import (
    EmailDeliveryResult,
    EmailDeliveryStatus,
    _classifica_falha,
    send_email,
    send_email_detalhado,
)
from app.services.email_outbox import MAX_ATTEMPTS, enqueue_email, proximo_estado_apos_falha

_AGORA = datetime(2026, 9, 29, 12, 0, 0, tzinfo=UTC)


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        smtp_from_email="from@test.com",
        smtp_user="from@test.com",
        smtp_host="localhost",
        smtp_port=1025,
    )
    base.update(overrides)
    return Settings(**base)


class _ErroComCodigoError(Exception):
    def __init__(self, code: int):
        super().__init__("mensagem do servidor, nunca deve vazar")
        self.code = code


# ═══════════════════════════════════════════════════════════════
# proximo_estado_apos_falha — a progressão 1m/5m/15m/60m e o limite de 5
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "tentativa,minutos_esperados",
    [(1, 1), (2, 5), (3, 15), (4, 60)],
)
def test_backoff_segue_a_progressao_pedida(tentativa, minutos_esperados):
    status, proxima = proximo_estado_apos_falha(tentativa, _AGORA)
    assert status == "pending"
    assert proxima == _AGORA + timedelta(minutes=minutos_esperados)


def test_quinta_tentativa_vai_para_dead():
    status, proxima = proximo_estado_apos_falha(5, _AGORA)
    assert status == "dead"
    assert proxima is None


def test_mais_de_cinco_tentativas_tambem_e_dead():
    """Defensivo: nunca deveria chegar a 6, mas `>=` (não `==`) cobre o caso."""
    status, proxima = proximo_estado_apos_falha(6, _AGORA)
    assert status == "dead"
    assert proxima is None


def test_max_attempts_e_cinco():
    """Fixa a constante pública que a Fase 3B/3D vai ler — não deixa passar
    despercebido quem mudar `MAX_ATTEMPTS` sem intenção."""
    assert MAX_ATTEMPTS == 5


def test_quarta_tentativa_nao_e_dead_ainda():
    """Alvo de mutação: `attempts >= MAX_ATTEMPTS` virando `attempts > MAX_ATTEMPTS`
    faria a 5ª tentativa (attempts == 5) escapar para `pending` em vez de `dead`.
    Este par (4 -> pending, 5 -> dead) é o que mata essa mutação."""
    status, _ = proximo_estado_apos_falha(4, _AGORA)
    assert status == "pending"


# ═══════════════════════════════════════════════════════════════
# _classifica_falha — 4xx temporário, 5xx permanente, sem código = temporário
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize("codigo", [421, 450, 452, 499])
def test_4xx_e_temporario(codigo):
    assert _classifica_falha(_ErroComCodigoError(codigo)) == EmailDeliveryStatus.temporary_failure


@pytest.mark.parametrize("codigo", [500, 535, 550, 599])
def test_5xx_e_permanente(codigo):
    assert _classifica_falha(_ErroComCodigoError(codigo)) == EmailDeliveryStatus.permanent_failure


def test_fronteira_399_e_temporario():
    """Alvo de mutação na comparação `400 <= codigo`: 399 tem que continuar
    fora da faixa 4xx/5xx e cair no fallback temporário — não em permanente."""
    assert _classifica_falha(_ErroComCodigoError(399)) == EmailDeliveryStatus.temporary_failure


def test_fronteira_400_e_temporario():
    assert _classifica_falha(_ErroComCodigoError(400)) == EmailDeliveryStatus.temporary_failure


def test_fronteira_499_para_500_muda_de_classe():
    """Alvo de mutação central: `< 500` virando `<= 500` faria 500 cair como

    temporário. Testa os dois lados do limite na mesma asserção."""
    assert _classifica_falha(_ErroComCodigoError(499)) == EmailDeliveryStatus.temporary_failure
    assert _classifica_falha(_ErroComCodigoError(500)) == EmailDeliveryStatus.permanent_failure


def test_sem_codigo_numerico_e_temporario():
    """Erro de conexão, timeout, ou qualquer exceção genérica sem `.code`:

    tratado como temporário, nunca descartado direto — é a regra explícita do
    pedido ("tipos não classificáveis... prefira temporários")."""
    assert _classifica_falha(TimeoutError("conexão caiu")) == EmailDeliveryStatus.temporary_failure


def test_codigo_nao_inteiro_e_temporario():
    erro = Exception("algo")
    erro.code = "535"  # string, não int — não deve ser tratado como SMTP code
    assert _classifica_falha(erro) == EmailDeliveryStatus.temporary_failure


# ═══════════════════════════════════════════════════════════════
# send_email_detalhado / send_email — compatibilidade e resultado estruturado
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_send_email_detalhado_sucesso():
    settings = _settings()
    with patch("app.services.email._get_mail_client") as mock_client:
        mock_fm = AsyncMock()
        mock_fm.send_message = AsyncMock()
        mock_client.return_value = mock_fm

        resultado = await send_email_detalhado("to@test.com", "Assunto", "Corpo", settings)

    assert resultado == EmailDeliveryResult(EmailDeliveryStatus.success)


@pytest.mark.asyncio
async def test_send_email_detalhado_falha_permanente_5xx():
    settings = _settings()
    with patch("app.services.email._get_mail_client") as mock_client:
        mock_fm = AsyncMock()
        mock_fm.send_message = AsyncMock(side_effect=_ErroComCodigoError(550))
        mock_client.return_value = mock_fm

        resultado = await send_email_detalhado("to@test.com", "Assunto", "Corpo", settings)

    assert resultado.status == EmailDeliveryStatus.permanent_failure
    assert resultado.error_summary is not None
    # O resumo é classe + código, nunca a mensagem crua do servidor.
    assert "mensagem do servidor" not in resultado.error_summary


@pytest.mark.asyncio
async def test_send_email_detalhado_falha_temporaria_4xx():
    settings = _settings()
    with patch("app.services.email._get_mail_client") as mock_client:
        mock_fm = AsyncMock()
        mock_fm.send_message = AsyncMock(side_effect=_ErroComCodigoError(421))
        mock_client.return_value = mock_fm

        resultado = await send_email_detalhado("to@test.com", "Assunto", "Corpo", settings)

    assert resultado.status == EmailDeliveryStatus.temporary_failure


@pytest.mark.asyncio
async def test_send_email_continua_devolvendo_bool():
    """`send_email` é o contrato antigo — ~20 call sites dependem dele

    continuar devolvendo `bool`. Este teste é o que garante que a Fase 3A não
    quebrou nenhum deles."""
    settings = _settings()
    with patch("app.services.email._get_mail_client") as mock_client:
        mock_fm = AsyncMock()
        mock_fm.send_message = AsyncMock()
        mock_client.return_value = mock_fm

        resultado = await send_email("to@test.com", "Assunto", "Corpo", settings)

    assert resultado is True


@pytest.mark.asyncio
async def test_send_email_bool_false_na_falha():
    settings = _settings()
    with patch("app.services.email._get_mail_client") as mock_client:
        mock_fm = AsyncMock()
        mock_fm.send_message = AsyncMock(side_effect=_ErroComCodigoError(550))
        mock_client.return_value = mock_fm

        resultado = await send_email("to@test.com", "Assunto", "Corpo", settings)

    assert resultado is False


@pytest.mark.asyncio
async def test_smtp_nao_configurado_e_temporario_nao_permanente():
    """Hoje `send_email` devolve `False` quando SMTP não está configurado, sem

    tentar nada. `send_email_detalhado` preserva o `False` (via `send_email`)
    mas precisa classificar como algo — `temporary_failure` é o correto: a
    ausência de configuração pode ser corrigida sem intervenção no conteúdo da
    mensagem, e tratar como `dead` matando a mensagem seria pior."""
    settings = _settings(smtp_from_email="", smtp_user="")
    resultado = await send_email_detalhado("to@test.com", "Assunto", "Corpo", settings)
    assert resultado.status == EmailDeliveryStatus.temporary_failure


# ═══════════════════════════════════════════════════════════════
# Logs continuam sem PII quando o caminho é o novo (send_email_detalhado)
# ═══════════════════════════════════════════════════════════════


def _captura() -> tuple[list[str], int]:
    linhas: list[str] = []
    sink = logger.add(lambda m: linhas.append(m.record["message"]), level="DEBUG")
    return linhas, sink


@pytest.mark.asyncio
async def test_send_email_detalhado_nao_loga_endereco_nem_mensagem_do_servidor():
    endereco = "cliente.real@empresa.com.br"
    settings = _settings()
    linhas, sink = _captura()
    try:
        with patch("app.services.email._get_mail_client") as mock_client:
            mock_fm = AsyncMock()
            mock_fm.send_message = AsyncMock(side_effect=_ErroComCodigoError(550))
            mock_client.return_value = mock_fm
            await send_email_detalhado(endereco, "Assunto qualquer", "Corpo", settings)
    finally:
        logger.remove(sink)

    texto = "\n".join(linhas)
    assert endereco not in texto
    assert "mensagem do servidor, nunca deve vazar" not in texto


# ═══════════════════════════════════════════════════════════════
# enqueue_email — só toca a sessão recebida, nunca commita sozinho
# ═══════════════════════════════════════════════════════════════


def test_enqueue_email_so_adiciona_a_sessao_recebida():
    from app.models.models import Notification, NotificationType

    notif = Notification(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        type=NotificationType.ticket_created,
        title="Ticket aberto",
        message="msg",
        data=None,
        read=False,
        email_sent=False,
    )
    db_fake = MagicMock()
    db_fake.commit = AsyncMock()

    outbox = enqueue_email(db_fake, notif, agora=_AGORA)

    db_fake.add.assert_called_once_with(outbox)
    db_fake.commit.assert_not_called()
    assert outbox.notification_id == notif.id
    assert outbox.status == "pending"
    assert outbox.attempts == 0
    assert outbox.next_attempt_at == _AGORA


def test_enqueue_email_sem_agora_usa_relogio_atual():
    from app.models.models import Notification, NotificationType

    notif = Notification(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        type=NotificationType.ticket_created,
        title="Ticket aberto",
        message="msg",
        data=None,
        read=False,
        email_sent=False,
    )
    db_fake = MagicMock()

    antes = datetime.now(UTC)
    outbox = enqueue_email(db_fake, notif)
    depois = datetime.now(UTC)

    assert antes <= outbox.next_attempt_at <= depois
