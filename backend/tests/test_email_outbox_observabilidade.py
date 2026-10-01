"""
Fase 3D — observabilidade da outbox de e-mail: estado, health e log de `dead`.

Este arquivo é todo de unidade, e isso é deliberado: `classifica_estado` é uma
função PURA, e a razão de ela ser pura é poder prender cada fronteira de limiar
sem subir banco nenhum. O que precisa de PostgreSQL de verdade — retenção,
lotes, `SKIP LOCKED` — está em `test_email_outbox_retencao_postgres.py`.

As fronteiras são testadas em `==` e em `+1`, não "por volta de"
-----------------------------------------------------------------
Todo limiar da Fase 3D é `>` estrito: exatamente NO limite ainda é o estado de
baixo. Um teste que só verificasse "muito acima" e "muito abaixo" passaria
igual com `>=` no lugar de `>`, e é justamente essa a mutação que a frente
mandou prender.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from loguru import logger

from app.core.config import Settings
from app.models.models import EmailOutbox, Notification, NotificationType
from app.services import email_outbox as mod
from app.services.email_outbox import (
    _CONTA_USUARIO_ANONIMIZADO,
    _CONTA_USUARIO_INATIVO,
    _CONTA_USUARIO_NAO_ENCONTRADO,
    _CONTA_VERIFICACAO_JA_CONCLUIDA,
    _NOTIFICACAO_NAO_ENCONTRADA,
    DEAD_CONFIGURACAO,
    DEAD_DEFENSIVO,
    DEAD_ENTREGA,
    DEAD_NEGOCIO,
    ESTADO_DEGRADADO,
    ESTADO_DESLIGADO,
    ESTADO_ERRO,
    ESTADO_INICIANDO,
    ESTADO_OK,
    SnapshotDaFila,
    bloco_de_health,
    classifica_dead,
    classifica_estado,
)

_AGORA = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

# Os mesmos valores do default de produção, para os limiares derivados serem
# os de verdade: 30 s de intervalo e 5 min de stale.
_INTERVALO = 30
_STALE_MIN = 5

# Derivados — escritos aqui em número fechado de propósito. Se alguém mudar a
# fórmula em `classifica_estado`, estes números param de casar e o teste cai,
# que é o ponto: a derivação é contrato, não detalhe.
_DEGRADADO_S = 4 * _INTERVALO  # 120
_ERRO_S = 20 * _INTERVALO  # 600
_OVERDUE_DEGRADADO_S = 2 * _INTERVALO  # 60
_STALE_S = _STALE_MIN * 60  # 300


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        email_outbox_interval_seconds=_INTERVALO,
        email_outbox_stale_processing_minutes=_STALE_MIN,
    )
    base.update(overrides)
    return Settings(**base)


def _snap(**overrides) -> SnapshotDaFila:
    campos = dict(
        as_of=_AGORA,
        pending=0,
        processing=0,
        sent=0,
        dead=0,
        oldest_overdue_seconds=None,
        oldest_processing_seconds=None,
    )
    campos.update(overrides)
    return SnapshotDaFila(**campos)


def _classifica(**overrides) -> str:
    """Worker ligado, girando há pouco, fila vazia — o caso saudável."""
    base = dict(
        habilitado=True,
        inicio=_AGORA - timedelta(hours=1),
        last_run=_AGORA,
        last_success=_AGORA,
        snapshot=_snap(),
        intervalo_segundos=_INTERVALO,
        stale_processing_minutes=_STALE_MIN,
        agora=_AGORA,
    )
    base.update(overrides)
    return classifica_estado(**base)


# ═══════════════════════════════════════════════════════════════
# Desligado e iniciando: nunca afirmar saúde que não se mediu
# ═══════════════════════════════════════════════════════════════


def test_intervalo_zero_e_desligado_e_nao_e_erro():
    """`EMAIL_OUTBOX_INTERVAL_SECONDS=0` é escolha de operação, não falha. O
    primeiro deploy desta fase sobe assim de propósito."""
    assert _classifica(habilitado=False) == ESTADO_DESLIGADO


def test_desligado_vence_qualquer_outro_sinal():
    """Com o worker desligado não existe heartbeat atrasado: não há worker."""
    estado = _classifica(
        habilitado=False,
        last_run=None,
        last_success=None,
        snapshot=_snap(oldest_overdue_seconds=99999, oldest_processing_seconds=99999),
    )
    assert estado == ESTADO_DESLIGADO


def test_antes_da_primeira_rodada_e_starting_nao_ok():
    """O laço espera `min(30, intervalo)` antes da primeira rodada. Dizer `ok`
    aí seria afirmar saúde sem nenhuma medição — e `ok` é exatamente o que um
    `/health` ingênuo responderia."""
    assert _classifica(last_run=None, last_success=None, snapshot=None, inicio=_AGORA) == (
        ESTADO_INICIANDO
    )


def test_sem_inicio_registrado_e_starting():
    """Processo em que `start_email_outbox_worker` nem rodou ainda (import do
    módulo sem lifespan — o caso do cliente de teste)."""
    assert _classifica(inicio=None, last_run=None, last_success=None, snapshot=None) == (
        ESTADO_INICIANDO
    )


def test_starting_nao_e_eterno_laco_que_nunca_rodou_degrada():
    """O risco do `starting`: virar desculpa permanente. Passado o limiar de
    degradação sem NENHUMA rodada, o laço não subiu — e isso é problema, não
    boot em andamento."""
    inicio = _AGORA - timedelta(seconds=_DEGRADADO_S + 1)
    assert _classifica(inicio=inicio, last_run=None, last_success=None, snapshot=None) == (
        ESTADO_DEGRADADO
    )

    inicio_antigo = _AGORA - timedelta(seconds=_ERRO_S + 1)
    assert (
        _classifica(inicio=inicio_antigo, last_run=None, last_success=None, snapshot=None)
        == ESTADO_ERRO
    )


def test_starting_dura_exatamente_ate_o_limiar():
    """Fronteira: NO limiar ainda é `starting`."""
    assert (
        _classifica(
            inicio=_AGORA - timedelta(seconds=_DEGRADADO_S),
            last_run=None,
            last_success=None,
            snapshot=None,
        )
        == ESTADO_INICIANDO
    )


# ═══════════════════════════════════════════════════════════════
# Heartbeats — fronteiras exatas
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "idade, esperado",
    [
        (0, ESTADO_OK),
        (_DEGRADADO_S - 1, ESTADO_OK),
        (_DEGRADADO_S, ESTADO_OK),  # `>` estrito: no limite ainda é ok
        (_DEGRADADO_S + 1, ESTADO_DEGRADADO),
        (_ERRO_S - 1, ESTADO_DEGRADADO),
        (_ERRO_S, ESTADO_DEGRADADO),  # `>` estrito de novo
        (_ERRO_S + 1, ESTADO_ERRO),
    ],
)
def test_fronteiras_do_last_run(idade, esperado):
    momento = _AGORA - timedelta(seconds=idade)
    assert _classifica(last_run=momento, last_success=_AGORA) == esperado


@pytest.mark.parametrize(
    "idade, esperado",
    [
        (_DEGRADADO_S, ESTADO_OK),
        (_DEGRADADO_S + 1, ESTADO_DEGRADADO),
        (_ERRO_S, ESTADO_DEGRADADO),
        (_ERRO_S + 1, ESTADO_ERRO),
    ],
)
def test_fronteiras_do_last_success(idade, esperado):
    momento = _AGORA - timedelta(seconds=idade)
    assert _classifica(last_run=_AGORA, last_success=momento) == esperado


def test_sem_sucesso_nenhum_a_idade_que_vale_e_a_do_processo():
    """O buraco que este teste fecha: `last_run` é atualizado a cada rodada, e
    ficaria sempre novo mesmo num worker que LEVANTA em toda rodada desde o
    boot. Sem cair para a idade do processo, isso apareceria como `ok`."""
    estado = _classifica(
        inicio=_AGORA - timedelta(seconds=_ERRO_S + 1),
        last_run=_AGORA,  # rodada começou agora...
        last_success=None,  # ...e nunca nenhuma terminou
    )
    assert estado == ESTADO_ERRO


def test_o_pior_sinal_manda():
    """Heartbeat novo não perdoa fila velha, e vice-versa."""
    assert _classifica(snapshot=_snap(oldest_overdue_seconds=_STALE_S + 1)) == ESTADO_ERRO
    assert _classifica(last_run=_AGORA - timedelta(seconds=_ERRO_S + 1)) == ESTADO_ERRO


# ═══════════════════════════════════════════════════════════════
# Estado da fila — o pending em backoff é o caso que engana
# ═══════════════════════════════════════════════════════════════


def test_pending_sozinho_nunca_degrada():
    """`pending > 0` é o estado NORMAL entre o enqueue e a rodada seguinte."""
    assert _classifica(snapshot=_snap(pending=500)) == ESTADO_OK


def test_pending_em_backoff_futuro_nao_esta_overdue():
    """A correção central do desenho. Uma linha esperando os 60 min do último
    degrau do backoff está `pending` e está EM DIA — `oldest_overdue_seconds`
    só conta o que já venceu, e por isso vem `None` aqui.

    Medir idade desde `created_at` confundiria "o worker parou" com "esta linha
    está cumprindo o backoff dela", e daria degradado num sistema saudável."""
    assert _classifica(snapshot=_snap(pending=3, oldest_overdue_seconds=None)) == ESTADO_OK


@pytest.mark.parametrize(
    "idade, esperado",
    [
        (0, ESTADO_OK),
        (_OVERDUE_DEGRADADO_S, ESTADO_OK),
        (_OVERDUE_DEGRADADO_S + 1, ESTADO_DEGRADADO),
        (_STALE_S, ESTADO_DEGRADADO),
        (_STALE_S + 1, ESTADO_ERRO),
    ],
)
def test_fronteiras_do_oldest_overdue(idade, esperado):
    assert _classifica(snapshot=_snap(pending=1, oldest_overdue_seconds=idade)) == esperado


@pytest.mark.parametrize(
    "idade, esperado",
    [
        (_STALE_S - 1, ESTADO_OK),
        (_STALE_S, ESTADO_OK),
        (_STALE_S + 1, ESTADO_DEGRADADO),
        (3 * _STALE_S, ESTADO_DEGRADADO),
        (3 * _STALE_S + 1, ESTADO_ERRO),
    ],
)
def test_fronteiras_do_oldest_processing(idade, esperado):
    """É este sinal que torna o achado A3 OBSERVÁVEL: a linha que o worker
    reivindica e devolve a cada `stale_minutes`, sem nunca avançar `attempts`,
    aparece aqui como idade que não baixa."""
    assert _classifica(snapshot=_snap(processing=1, oldest_processing_seconds=idade)) == (esperado)


# ═══════════════════════════════════════════════════════════════
# `dead` é informativo: NUNCA altera o state nesta fase
# ═══════════════════════════════════════════════════════════════


def test_dead_de_negocio_nao_altera_state():
    assert _classifica(snapshot=_snap(dead=42)) == ESTADO_OK


def test_dead_de_entrega_tambem_nao_altera_state():
    """Decisão da frente: sem classificação PERSISTIDA, o health não consegue
    separar com robustez `AccountAlreadyVerified` de uma falha real de entrega,
    e um número que mistura os dois vira alarme que se aprende a ignorar. A
    distinção existe, com severidade, no LOG — ver os testes de `dead` abaixo."""
    assert _classifica(snapshot=_snap(dead=9999)) == ESTADO_OK


def test_dead_nao_resgata_um_estado_ja_degradado():
    """O contrário também precisa valer: `dead` não mexe no state em nenhuma
    direção."""
    estado = _classifica(
        snapshot=_snap(dead=9999, oldest_overdue_seconds=_STALE_S + 1),
    )
    assert estado == ESTADO_ERRO


# ═══════════════════════════════════════════════════════════════
# Classificação de `dead` — e o default é o pior caso
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "motivo, classe",
    [
        (_CONTA_USUARIO_ANONIMIZADO, DEAD_NEGOCIO),
        (_CONTA_USUARIO_INATIVO, DEAD_NEGOCIO),
        (_CONTA_VERIFICACAO_JA_CONCLUIDA, DEAD_NEGOCIO),
        (_CONTA_USUARIO_NAO_ENCONTRADO, DEAD_DEFENSIVO),
        (_NOTIFICACAO_NAO_ENCONTRADA, DEAD_DEFENSIVO),
        ("SMTPNotConfigured", DEAD_CONFIGURACAO),
        ("SMTPRecipientRefused (code 550)", DEAD_ENTREGA),
        ("SMTPServerDisconnected", DEAD_ENTREGA),
    ],
)
def test_classifica_dead_cobre_todos_os_motivos_que_o_codigo_produz(motivo, classe):
    assert classifica_dead(motivo) == classe


@pytest.mark.parametrize("motivo", [None, "", "MotivoQueNinguemCadastrou"])
def test_motivo_desconhecido_cai_em_entrega_nao_em_negocio(motivo):
    """O default é o pior caso de propósito: um motivo novo que alguém esqueça
    de cadastrar aparece como falha de entrega (nível ERROR), alto demais e não
    baixo demais. Um default silencioso esconderia exatamente o que este log
    existe para mostrar."""
    assert classifica_dead(motivo) == DEAD_ENTREGA


# ═══════════════════════════════════════════════════════════════
# O log de `dead` (achado A1) — existe, e não vaza
# ═══════════════════════════════════════════════════════════════

_EMAIL = "cliente.pessoa@empresa.com.br"
_NOME = "Maria da Silva Pessoa"
_TITULO = "Impressora da recepção parou e o faturamento travou"


def _captura() -> tuple[list[tuple[str, str]], int]:
    capturado: list[tuple[str, str]] = []
    sink = logger.add(
        lambda m: capturado.append((m.record["level"].name, m.record["message"])),
        level="DEBUG",
    )
    return capturado, sink


async def _dead_com(motivo: str, *, origem: str = "account", attempts: int = 1):
    """Dispara `_loga_dead` com uma linha de outbox montada à mão.

    Não sobe banco: `db` é um mock cujo `get` devolve a `Notification` quando a
    origem é Notification. O que está sob teste é a linha de LOG, não o SQL.
    """
    if origem == "account":
        outbox = EmailOutbox(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            event_type="password_reset",
            dedup_key=f"password_reset:{uuid.uuid4()}:{uuid.uuid4()}",
            status="dead",
            attempts=attempts,
            next_attempt_at=_AGORA,
        )
        db = MagicMock()
        db.get = AsyncMock(return_value=None)
    else:
        notif = Notification(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            type=NotificationType.ticket_created,
            title=_TITULO,
            message=f"Olá, {_NOME} — o chamado foi aberto.",
            data={"ticket_id": str(uuid.uuid4()), "protocol": "HS-2026-0007"},
            read=False,
            email_sent=False,
        )
        outbox = EmailOutbox(
            id=uuid.uuid4(),
            notification_id=notif.id,
            status="dead",
            attempts=attempts,
            next_attempt_at=_AGORA,
        )
        db = MagicMock()
        db.get = AsyncMock(return_value=notif)

    capturado, sink = _captura()
    try:
        await mod._loga_dead(db, outbox, motivo)
    finally:
        logger.remove(sink)
    return capturado, outbox


@pytest.mark.asyncio
async def test_dead_deixa_de_ser_silencioso():
    """O achado A1: até a Fase 3D a linha virava `dead` sem UMA linha de log.
    O e-mail definitivamente não entregue era o evento mais importante do
    subsistema e só existia como estado no banco."""
    capturado, _ = await _dead_com("SMTPRecipientRefused (code 550)")

    assert len(capturado) == 1
    nivel, mensagem = capturado[0]
    assert nivel == "ERROR"
    assert "dead" in mensagem
    assert f"dead_kind={DEAD_ENTREGA}" in mensagem
    assert "attempts=1" in mensagem
    assert "origin=account" in mensagem
    assert "event=password_reset" in mensagem


@pytest.mark.asyncio
async def test_dead_de_negocio_sai_como_info_nao_como_erro():
    """Um terminal de negócio não é incidente — a pessoa anonimizou a conta, ou
    já confirmou o e-mail por outro caminho. Logar isso como erro treinaria
    quem lê o log a ignorar a linha que importa."""
    capturado, _ = await _dead_com(_CONTA_USUARIO_ANONIMIZADO)

    nivel, mensagem = capturado[0]
    assert nivel == "INFO"
    assert f"dead_kind={DEAD_NEGOCIO}" in mensagem


@pytest.mark.asyncio
async def test_dead_defensivo_sai_como_warning():
    capturado, _ = await _dead_com(_CONTA_USUARIO_NAO_ENCONTRADO)
    assert capturado[0][0] == "WARNING"
    assert f"dead_kind={DEAD_DEFENSIVO}" in capturado[0][1]


@pytest.mark.asyncio
async def test_dead_de_configuracao_sai_como_erro():
    capturado, _ = await _dead_com("SMTPNotConfigured")
    assert capturado[0][0] == "ERROR"
    assert f"dead_kind={DEAD_CONFIGURACAO}" in capturado[0][1]


@pytest.mark.asyncio
async def test_log_de_dead_da_origem_notification_traz_o_tipo_do_aviso():
    """`notification_type` é valor de enum fechado: diz QUAL espécie de aviso
    está falhando sem apontar pessoa nenhuma."""
    capturado, _ = await _dead_com("SMTPDataError (code 554)", origem="notification")
    assert "origin=notification" in capturado[0][1]
    assert "event=ticket_created" in capturado[0][1]


@pytest.mark.asyncio
@pytest.mark.parametrize("origem", ["account", "notification"])
async def test_log_de_dead_nao_vaza_pii_em_nenhuma_das_duas_origens(origem):
    """O inverso do A1: fechar o silêncio não pode abrir um vazamento. Nem
    endereço, nem nome, nem título de chamado, nem id de pessoa."""
    capturado, outbox = await _dead_com("SMTPRecipientRefused (code 550)", origem=origem)
    mensagem = capturado[0][1]

    for proibido in (_EMAIL, _NOME, _TITULO):
        assert proibido not in mensagem

    assert str(outbox.id) not in mensagem
    if outbox.user_id is not None:
        assert str(outbox.user_id) not in mensagem
    if outbox.notification_id is not None:
        assert str(outbox.notification_id) not in mensagem
    assert "dedup_key" not in mensagem
    if outbox.dedup_key is not None:
        assert outbox.dedup_key not in mensagem


# ═══════════════════════════════════════════════════════════════
# O bloco do health — lê memória, carrega `as_of`, não vaza
# ═══════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def estado_limpo():
    """Estado de módulo vaza entre casos, e um health que herda o carimbo do
    teste anterior passa verde por acidente."""
    mod.reinicia_estado_para_testes()
    yield
    mod.reinicia_estado_para_testes()


def test_bloco_no_boot_nao_afirma_saude():
    bloco = bloco_de_health(_settings(), agora=_AGORA)

    assert bloco["enabled"] is True
    assert bloco["state"] == ESTADO_INICIANDO
    assert bloco["last_run"] is None
    assert bloco["last_success"] is None
    assert bloco["as_of"] is None


def test_bloco_sem_snapshot_devolve_none_e_nao_zero():
    """`0` ali seria afirmar uma contagem que não houve. `None` diz a verdade:
    não medimos."""
    bloco = bloco_de_health(_settings(), agora=_AGORA)
    for campo in ("pending", "processing", "dead"):
        assert bloco[campo] is None, campo
    assert bloco["oldest_overdue_seconds"] is None
    assert bloco["oldest_processing_seconds"] is None


def test_bloco_desligado_e_explicito():
    bloco = bloco_de_health(_settings(email_outbox_interval_seconds=0), agora=_AGORA)
    assert bloco["enabled"] is False
    assert bloco["state"] == ESTADO_DESLIGADO


def test_bloco_expoe_as_of_junto_das_contagens():
    """O `as_of` é obrigatório: sem ele ninguém distingue "a fila está vazia"
    de "o worker parou de medir há duas horas"."""
    medido_em = _AGORA - timedelta(seconds=10)
    mod._inicio_do_worker = _AGORA - timedelta(hours=1)
    mod._ultima_rodada_iniciada = medido_em
    mod._ultima_rodada_sem_erro = medido_em
    mod._snapshot = _snap(as_of=medido_em, pending=3, processing=1, sent=900, dead=2)

    bloco = bloco_de_health(_settings(), agora=_AGORA)

    assert bloco["as_of"] == medido_em.isoformat()
    assert bloco["pending"] == 3
    assert bloco["processing"] == 1
    assert bloco["dead"] == 2
    assert bloco["state"] == ESTADO_OK


def test_bloco_nao_expoe_sent_total():
    """Total cumulativo, cresce para sempre, ninguém alerta nele — e a retenção
    o torna um número sem significado."""
    mod._snapshot = _snap(sent=12345)
    assert "sent" not in bloco_de_health(_settings(), agora=_AGORA)


def test_bloco_tem_as_chaves_do_contrato_e_so_elas():
    mod._snapshot = _snap()
    assert set(bloco_de_health(_settings(), agora=_AGORA)) == {
        "enabled",
        "state",
        "last_run",
        "last_success",
        "as_of",
        "pending",
        "processing",
        "dead",
        "oldest_overdue_seconds",
        "oldest_processing_seconds",
    }


def test_bloco_de_health_nao_consulta_o_banco():
    """O requisito explícito da frente: o endpoint de readiness lê MEMÓRIA. Se
    `bloco_de_health` virasse `async` e consultasse, cada probe pagaria um
    `COUNT(*)` — e a resolução ganha seria menor que o ciclo do worker."""
    import inspect

    assert not inspect.iscoroutinefunction(bloco_de_health)

    with patch.object(mod, "coleta_snapshot", new=AsyncMock()) as coleta:
        bloco_de_health(_settings(), agora=_AGORA)
    coleta.assert_not_called()


def test_bloco_do_health_nao_carrega_pii():
    """O snapshot é só número e carimbo — por construção. Este teste prende a
    construção: um campo novo com conteúdo de pessoa cairia aqui."""
    mod._snapshot = _snap(pending=1)
    bloco = bloco_de_health(_settings(), agora=_AGORA)
    texto = repr(bloco)

    for proibido in (_EMAIL, _NOME, _TITULO, "@", "token", "subject"):
        assert proibido not in texto, proibido


# ═══════════════════════════════════════════════════════════════
# A rodada: limpeza e métricas não podem derrubar o envio
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_falha_da_limpeza_nao_impede_o_last_success():
    """O ponto de ter `except` próprio: uma limpeza que falhe inventaria um
    alarme de worker parado a partir de um problema que não encostou no envio."""
    settings = _settings()

    with (
        patch.object(mod, "get_settings", return_value=settings),
        patch.object(mod, "processa_lote", new=AsyncMock(return_value=0)) as nucleo,
        patch.object(mod, "limpa_expirados", new=AsyncMock(side_effect=RuntimeError("boom"))),
        patch.object(mod, "coleta_snapshot", new=AsyncMock(return_value=_snap())),
    ):
        await mod._run_once("outbox-teste")

    nucleo.assert_awaited_once()
    assert mod.ultima_rodada_sem_erro() is not None
    assert mod.ultima_rodada_iniciada() is not None


@pytest.mark.asyncio
async def test_falha_do_snapshot_nao_impede_o_last_success():
    settings = _settings()

    with (
        patch.object(mod, "get_settings", return_value=settings),
        patch.object(mod, "processa_lote", new=AsyncMock(return_value=0)),
        patch.object(mod, "limpa_expirados", new=AsyncMock(return_value={"sent": 0, "dead": 0})),
        patch.object(mod, "coleta_snapshot", new=AsyncMock(side_effect=RuntimeError("boom"))),
    ):
        await mod._run_once("outbox-teste")

    assert mod.ultima_rodada_sem_erro() is not None
    assert mod.snapshot_da_fila() is None


@pytest.mark.asyncio
async def test_falha_do_nucleo_nao_carimba_sucesso_mas_carimba_inicio():
    """`last_run` existe para isto: distinguir "o laço girou e falhou" de "o
    laço não girou"."""
    settings = _settings()

    with (
        patch.object(mod, "get_settings", return_value=settings),
        patch.object(mod, "processa_lote", new=AsyncMock(side_effect=RuntimeError("boom"))),
        patch.object(mod, "limpa_expirados", new=AsyncMock(return_value={"sent": 0, "dead": 0})),
        patch.object(mod, "coleta_snapshot", new=AsyncMock(return_value=_snap())),
    ):
        await mod._run_once("outbox-teste")

    assert mod.ultima_rodada_iniciada() is not None
    assert mod.ultima_rodada_sem_erro() is None


@pytest.mark.asyncio
async def test_excecao_do_nucleo_nao_vai_crua_para_o_log():
    """Achado A2. O `str()` de um `DBAPIError` do SQLAlchemy carrega o SQL e os
    `[parameters: ...]` — era por aqui que conteúdo de biblioteca de terceiro
    podia chegar ao log sem ninguém ter escrito um campo sensível."""

    class FalsoDBAPIError(RuntimeError):
        """Imita o que importa: um `str()` gordo e um `.code` que é STRING."""

        code = "e3q8"

        def __str__(self) -> str:
            return (
                "(psycopg.errors.UniqueViolation) duplicate key\n"
                "[SQL: INSERT INTO users (email, name) VALUES ($1, $2)]\n"
                f"[parameters: ('{_EMAIL}', '{_NOME}')]"
            )

    settings = _settings()
    capturado, sink = _captura()
    try:
        with (
            patch.object(mod, "get_settings", return_value=settings),
            patch.object(mod, "processa_lote", new=AsyncMock(side_effect=FalsoDBAPIError())),
            patch.object(
                mod, "limpa_expirados", new=AsyncMock(return_value={"sent": 0, "dead": 0})
            ),
            patch.object(mod, "coleta_snapshot", new=AsyncMock(return_value=_snap())),
        ):
            await mod._run_once("outbox-teste")
    finally:
        logger.remove(sink)

    texto = "\n".join(m for _, m in capturado)
    assert "FalsoDBAPIError" in texto, "o nome da classe é o que DEVE sobrar"
    for proibido in (_EMAIL, _NOME, "INSERT INTO", "parameters", "$1"):
        assert proibido not in texto, proibido


@pytest.mark.asyncio
async def test_falha_da_limpeza_nao_vai_crua_para_o_log():
    settings = _settings()

    class FalsoErroError(RuntimeError):
        def __str__(self) -> str:
            return f"[parameters: ('{_EMAIL}',)]"

    capturado, sink = _captura()
    try:
        with (
            patch.object(mod, "get_settings", return_value=settings),
            patch.object(mod, "processa_lote", new=AsyncMock(return_value=0)),
            patch.object(mod, "limpa_expirados", new=AsyncMock(side_effect=FalsoErroError())),
            patch.object(mod, "coleta_snapshot", new=AsyncMock(return_value=_snap())),
        ):
            await mod._run_once("outbox-teste")
    finally:
        logger.remove(sink)

    texto = "\n".join(m for _, m in capturado)
    assert "FalsoErroError" in texto
    assert _EMAIL not in texto
    assert "parameters" not in texto


# ═══════════════════════════════════════════════════════════════
# O intervalo da limpeza — carimbo de tempo, não contador de rodadas
# ═══════════════════════════════════════════════════════════════


def test_cleanup_desligado_nao_limpa():
    settings = _settings(email_outbox_cleanup_interval_seconds=0)
    assert mod._deve_limpar(settings, _AGORA) is False


def test_primeira_rodada_limpa():
    settings = _settings(email_outbox_cleanup_interval_seconds=3600)
    assert mod._deve_limpar(settings, _AGORA) is True


def test_nao_limpa_de_novo_antes_do_intervalo():
    settings = _settings(email_outbox_cleanup_interval_seconds=3600)
    mod._ultima_limpeza = _AGORA - timedelta(seconds=3599)
    assert mod._deve_limpar(settings, _AGORA) is False


def test_limpa_quando_o_intervalo_fecha():
    settings = _settings(email_outbox_cleanup_interval_seconds=3600)
    mod._ultima_limpeza = _AGORA - timedelta(seconds=3600)
    assert mod._deve_limpar(settings, _AGORA) is True


@pytest.mark.asyncio
async def test_carimbo_da_limpeza_e_da_tentativa_nao_do_sucesso():
    """Gravado antes do trabalho de propósito: uma falha recorrente espera o
    intervalo inteiro em vez de tentar a cada 30 s e encher o log."""
    settings = _settings(email_outbox_cleanup_interval_seconds=3600)

    with patch.object(mod, "limpa_expirados", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await mod._limpeza_protegida(MagicMock(), settings, _AGORA)

    assert mod._ultima_limpeza == _AGORA
    assert mod._deve_limpar(settings, _AGORA) is False
