"""
O aviso de SLA de resolução próximo do vencimento — Fase 2A.

Por que este arquivo existe
---------------------------
`SLAConfig.warning_threshold` existe desde o schema inicial, é editável por
prioridade, aparece na tela como "80%" e **nunca foi lido por regra nenhuma**.
Pior: `SlaConfigPage` afirma ao administrador que "o alerta dispara quando o
percentual do tempo já consumido atingir o limiar". Nada disparava. Esta fase
não acrescenta funcionalidade — ela cumpre uma promessa que a interface já
fazia.

O que é testado aqui, e o que é testado no Postgres
---------------------------------------------------
Aqui: o CÁLCULO, os FILTROS de candidato, a AUDIÊNCIA e o LAÇO do worker —
tudo o que é decidido em Python.

Em `tests/test_sla_alertas_postgres.py`: a UNIQUE, o `ON CONFLICT DO NOTHING`,
a concorrência entre dois workers e o rollback. Nada disso se prova com
`AsyncMock`: um mock aceita duas inserções idênticas sem reclamar, que é
exatamente o defeito que a constraint existe para impedir.

O percentual não é reimplementado
---------------------------------
`prazo_efetivo_de_resolucao` e `business_minutes_between` são a fonte de
verdade, e este worker as consome. Um espelho em Python provaria que a cópia
funciona, não que o motor funciona — e a casa já pagou por isso quando o chip
da tela calculava o vencimento por conta própria e discordava do motor sempre
que havia pausa.

Nada aqui envia e-mail: `FastMail.send_message` nunca é alcançado porque
`settings` é sempre um dublê sem SMTP, e há contraprova disso no fim do arquivo.
"""

import asyncio
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.models import (
    NotificationType,
    SLAConfig,
    SLALevel,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
)
from app.services import sla_alertas
from app.services.notifications import _EMAIL_PARA_STAFF
from app.services.sla_alertas import (
    _BATCH_LIMIT,
    _LOCK_KEY,
    ALERTA_RESOLUCAO,
    assunto_do_aviso,
    consumido_pct,
    dados_do_aviso,
    e_candidato,
    mensagem_do_aviso,
    threshold_da_prioridade,
)
from app.utils.sla import add_business_minutes, business_minutes_between

# Uma terça-feira às 09:00 em São Paulo, dentro do expediente (08:00–17:00).
_ABERTURA = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)  # 09:00 BRT


def _config(nivel: SLALevel, threshold: int, resolve_min: int = 540) -> SLAConfig:
    return SLAConfig(
        id=uuid.uuid4(),
        level=nivel,
        response_time_minutes=60,
        resolve_time_minutes=resolve_min,
        warning_threshold=threshold,
        is_active=True,
    )


def _chamado(
    *,
    prioridade: TicketPriority | None = TicketPriority.medium,
    status: TicketStatus = TicketStatus.in_progress,
    resolve_min: int = 540,
    pausado: bool = False,
    pausa_ms: int = 0,
    extensao_min: int = 0,
    reaberturas: int = 0,
) -> Ticket:
    """Chamado sintético com prazo de resolução carimbado da abertura.

    `resolve_min` são minutos ÚTEIS, como `resolve_time_minutes` do `SLAConfig`:
    540 é uma jornada inteira.
    """
    prazo = add_business_minutes(_ABERTURA, resolve_min)
    t = Ticket(
        id=uuid.uuid4(),
        protocol="HS-2026-0042",
        title="Impressora da recepção sem conexão",
        description="corpo",
        priority=prioridade,
        category=TicketCategory.hardware,
        status=status,
        creator_id=uuid.uuid4(),
        sla_resolve_due_at=prazo,
        sla_resolve_effective_due_at=prazo,
        sla_total_paused_ms=pausa_ms,
        sla_resolve_extension_total_min=extensao_min,
        sla_paused_at=_ABERTURA if pausado else None,
        sla_response_breach=False,
        sla_resolve_breach=False,
        auto_closed=False,
        reopen_count=reaberturas,
        created_at=_ABERTURA,
        updated_at=_ABERTURA,
    )
    return t


def _instante_com_consumo(ticket: Ticket, pct: float) -> datetime:
    """O instante em que `pct`% do prazo ÚTIL do chamado terá sido consumido.

    Calculado pelo motor, não por regra de três sobre tempo corrido: o prazo é
    em minutos úteis e a jornada tem 9 h, então somar tempo de relógio daria
    outro ponto.
    """
    from app.utils.sla import prazo_efetivo_de_resolucao

    prazo = prazo_efetivo_de_resolucao(ticket)
    assert prazo is not None
    total = business_minutes_between(ticket.created_at, prazo)
    return add_business_minutes(ticket.created_at, int(round(total * pct / 100)))


def _pessoa(papel: UserRole, status: UserStatus = UserStatus.active, nome: str = "Ana") -> User:
    return User(
        id=uuid.uuid4(),
        name=nome,
        email=f"{uuid.uuid4().hex[:8]}@test.com",
        password="x",
        role=papel,
        status=status,
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
    )


# ══════════════════════════════════════════════════════════════
# 1. O percentual consumido
# ══════════════════════════════════════════════════════════════


def test_metade_do_prazo_consumido_da_cinquenta_por_cento():
    ticket = _chamado()
    agora = _instante_com_consumo(ticket, 50)

    assert consumido_pct(ticket, agora) == pytest.approx(50, abs=0.5)


def test_o_percentual_e_de_tempo_uteis_nao_de_relogio():
    """Um chamado aberto às 09:00 com prazo de uma jornada vence às 08:00 do dia
    seguinte em tempo de RELÓGIO — 23 h depois. Meia jornada útil são 4h30, não
    11h30. Contar relógio daria 20%, e o aviso sairia na hora errada."""
    ticket = _chamado(resolve_min=540)
    meio = _ABERTURA + timedelta(hours=4, minutes=30)

    assert consumido_pct(ticket, meio) == pytest.approx(50, abs=1)


def test_prazo_sem_duracao_util_nao_produz_percentual():
    """`total <= 0` não pode virar divisão por zero nem 100% por acidente."""
    ticket = _chamado()
    ticket.sla_resolve_due_at = ticket.created_at
    ticket.sla_resolve_effective_due_at = ticket.created_at

    assert consumido_pct(ticket, _ABERTURA) is None


def test_sem_prazo_nao_produz_percentual():
    ticket = _chamado()
    ticket.sla_resolve_due_at = None
    ticket.sla_resolve_effective_due_at = None

    assert consumido_pct(ticket, _ABERTURA) is None


def test_a_extensao_entra_no_percentual_pelo_motor():
    """Prorrogar dilui o consumo: o mesmo instante passa a representar uma
    fração menor de um prazo maior. Quem faz essa conta é
    `prazo_efetivo_de_resolucao`, e o worker só a consome."""
    sem = _chamado()
    com = _chamado(extensao_min=540)
    agora = _instante_com_consumo(sem, 90)

    pct_sem = consumido_pct(sem, agora)
    pct_com = consumido_pct(com, agora)

    assert pct_sem is not None and pct_com is not None
    assert pct_com < pct_sem


# ══════════════════════════════════════════════════════════════
# 2. O limiar — por prioridade, em percentual inteiro
# ══════════════════════════════════════════════════════════════


def test_exatamente_no_limiar_avisa():
    """`>=`, e não `>`: o limiar é o ponto em que o aviso deve sair. Com `>` um
    chamado que cai exatamente em 80,0 só avisaria na rodada seguinte — ou
    nunca, se o expediente fechasse no meio."""
    ticket = _chamado()
    agora = _instante_com_consumo(ticket, 80)
    configs = {SLALevel.medium: _config(SLALevel.medium, 80)}

    assert e_candidato(ticket, agora, configs) is True


def test_abaixo_do_limiar_nao_avisa():
    ticket = _chamado()
    agora = _instante_com_consumo(ticket, 70)
    configs = {SLALevel.medium: _config(SLALevel.medium, 80)}

    assert e_candidato(ticket, agora, configs) is False


def test_acima_do_limiar_e_antes_do_vencimento_avisa():
    ticket = _chamado()
    agora = _instante_com_consumo(ticket, 95)
    configs = {SLALevel.medium: _config(SLALevel.medium, 80)}

    assert e_candidato(ticket, agora, configs) is True


def test_limiar_de_setenta_dispara_em_setenta_e_nao_em_oitenta():
    """O caso que prova que o campo do banco é lido de verdade. Com o 80 fixo
    do frontend copiado para cá, este teste falha."""
    ticket = _chamado()
    agora = _instante_com_consumo(ticket, 72)
    configs = {SLALevel.medium: _config(SLALevel.medium, 70)}

    assert e_candidato(ticket, agora, configs) is True


def test_o_limiar_e_percentual_inteiro_e_nao_fracao():
    """⚠️ `frontend/src/test/services/slaService.test.ts` usa
    `warning_threshold: 0.8`. É fixture de mock, mas codifica a escala errada —
    e quem escrever a Fase 2B olhando para lá divide por 100 sem pensar.

    Com `threshold / 100`, um chamado em 5% de consumo já avisaria: 5 >= 0,8.
    """
    ticket = _chamado()
    agora = _instante_com_consumo(ticket, 5)
    configs = {SLALevel.medium: _config(SLALevel.medium, 80)}

    assert e_candidato(ticket, agora, configs) is False


def test_cada_prioridade_usa_o_proprio_limiar():
    baixa = _chamado(prioridade=TicketPriority.low)
    critica = _chamado(prioridade=TicketPriority.critical)
    configs = {
        SLALevel.low: _config(SLALevel.low, 90),
        SLALevel.critical: _config(SLALevel.critical, 50),
    }
    agora = _instante_com_consumo(baixa, 60)

    assert e_candidato(baixa, agora, configs) is False
    assert e_candidato(critica, agora, configs) is True


def test_prioridade_sem_config_ativa_nao_avisa():
    """Sem linha de catálogo não há limiar, e inventar 80 aqui seria a mesma
    divergência que esta fase existe para fechar."""
    ticket = _chamado(prioridade=TicketPriority.high)

    assert threshold_da_prioridade(ticket, {}) is None
    assert e_candidato(ticket, _instante_com_consumo(ticket, 99), {}) is False


# ══════════════════════════════════════════════════════════════
# 3. Os filtros de estado
# ══════════════════════════════════════════════════════════════


def test_vencido_nao_produz_warning():
    """Passado o prazo o assunto é violação, não aviso. Produzir `sla_warning`
    aqui diria "está chegando" sobre algo que já chegou."""
    ticket = _chamado()
    prazo = ticket.sla_resolve_effective_due_at
    assert prazo is not None
    configs = {SLALevel.medium: _config(SLALevel.medium, 80)}

    assert e_candidato(ticket, prazo + timedelta(minutes=1), configs) is False


def test_exatamente_no_vencimento_nao_produz_warning():
    """A fronteira fica do lado da violação: no instante do prazo o consumo é
    100%, e 100% não é "próximo do vencimento"."""
    ticket = _chamado()
    prazo = ticket.sla_resolve_effective_due_at
    assert prazo is not None
    configs = {SLALevel.medium: _config(SLALevel.medium, 80)}

    assert e_candidato(ticket, prazo, configs) is False


def test_sem_prioridade_nao_avisa():
    """Chamado nasce sem prioridade — quem a define é a triagem. Sem ela não há
    prazo carimbado e não há limiar a consultar."""
    ticket = _chamado(prioridade=None)
    ticket.sla_resolve_due_at = None
    ticket.sla_resolve_effective_due_at = None
    configs = {SLALevel.medium: _config(SLALevel.medium, 80)}

    assert e_candidato(ticket, _ABERTURA, configs) is False


@pytest.mark.parametrize(
    "status", [TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]
)
def test_chamado_terminal_nao_avisa(status):
    ticket = _chamado(status=status)
    agora = _instante_com_consumo(ticket, 95)
    configs = {SLALevel.medium: _config(SLALevel.medium, 80)}

    assert e_candidato(ticket, agora, configs) is False


def test_pausado_nao_avisa():
    """A pausa EM CURSO não entra no prazo efetivo — decisão antiga, e não a
    consertamos aqui. A consequência é que um chamado parado continua se
    aproximando do vencimento, e avisar a equipe sobre um chamado que ela não
    pode tocar porque espera o cliente é o começo do ruído que derruba o canal.
    """
    ticket = _chamado(pausado=True)
    agora = _instante_com_consumo(ticket, 95)
    configs = {SLALevel.medium: _config(SLALevel.medium, 80)}

    assert e_candidato(ticket, agora, configs) is False


def test_retomado_volta_a_ser_avaliado():
    """`resume_sla` zera `sla_paused_at`, e o chamado volta à fila.

    A pausa é aqui de duração zero de propósito. Uma pausa longa acumularia
    tempo CORRIDO no prazo efetivo (a dívida antiga, que esta fase não conserta)
    e o chamado sairia da faixa por diluição — o que é comportamento legítimo,
    mas provaria outra coisa. O que este teste precisa isolar é que **o filtro
    de pausa era o único bloqueio**, e que retomar o levanta.
    """
    from app.utils.sla import resume_sla

    ticket = _chamado()
    agora = _instante_com_consumo(ticket, 95)
    configs = {SLALevel.medium: _config(SLALevel.medium, 80)}

    ticket.sla_paused_at = agora
    assert e_candidato(ticket, agora, configs) is False

    resume_sla(ticket, agora)

    assert ticket.sla_paused_at is None
    assert ticket.sla_total_paused_ms == 0
    assert e_candidato(ticket, agora, configs) is True


# ══════════════════════════════════════════════════════════════
# 4. A mensagem, o assunto e o `data`
# ══════════════════════════════════════════════════════════════


def test_o_assunto_leva_o_protocolo_e_nao_o_titulo():
    """O título é texto do cliente. Ele não entra no assunto — foi o que o
    endurecimento de logs de 25/09 tirou da linha de log, pela mesma razão."""
    ticket = _chamado()

    assunto = assunto_do_aviso(ticket)

    assert assunto == "[HelpHS] SLA próximo do vencimento — HS-2026-0042"
    assert ticket.title not in assunto


def test_a_mensagem_do_sininho_nao_leva_o_titulo():
    ticket = _chamado()

    msg = mensagem_do_aviso(ticket, 85.0, 42)

    assert "HS-2026-0042" in msg
    assert "85%" in msg
    assert ticket.title not in msg


def test_o_data_carrega_o_que_a_tela_e_a_auditoria_precisam():
    ticket = _chamado()
    prazo = ticket.sla_resolve_effective_due_at
    assert prazo is not None

    dados = dados_do_aviso(ticket, prazo, 80, 84.5)

    assert dados["ticket_id"] == str(ticket.id)
    assert dados["protocol"] == "HS-2026-0042"
    assert dados["sla_kind"] == "resolution"
    assert dados["warning_threshold"] == 80
    assert dados["effective_due_at"] == prazo.isoformat()
    assert dados["consumed_pct"] == pytest.approx(84.5)


def test_o_ticket_id_do_data_e_o_que_monta_o_link():
    """`_link_do_chamado` lê `data["ticket_id"]`. Sem essa chave o e-mail chega
    sem botão e o sininho não navega — foi o defeito de 04/09, em doze dos
    catorze e-mails."""
    from app.services.notifications import _link_do_chamado

    ticket = _chamado()
    prazo = ticket.sla_resolve_effective_due_at
    assert prazo is not None
    settings = MagicMock()
    settings.frontend_url = "https://helphs.example.test"

    dados = dados_do_aviso(ticket, prazo, 80, 84.5)
    link = _link_do_chamado(dados["ticket_id"], settings)

    assert link == f"https://helphs.example.test/tickets/{ticket.id}"


# ══════════════════════════════════════════════════════════════
# 5. A política de e-mail
# ══════════════════════════════════════════════════════════════


def test_sla_warning_recebe_email_de_staff():
    """Técnico e administrador não recebem e-mail por padrão (decisão de
    04/09). `sla_warning` entra na exceção NOMEADA, como `ticket_created` —
    não como condição espalhada por router."""
    assert NotificationType.sla_warning in _EMAIL_PARA_STAFF


def test_a_excecao_de_email_para_staff_nao_foi_alargada():
    """Contraprova: só os dois tipos previstos. Um `frozenset` que crescesse
    sem ninguém ver devolveria o ruído que o filtro de 04/09 eliminou."""
    assert _EMAIL_PARA_STAFF == frozenset(
        {NotificationType.ticket_created, NotificationType.sla_warning}
    )


def test_sla_breached_continua_sem_email_e_sem_produtor():
    """Esta fase NÃO produz violação. O tipo existe no enum desde o schema
    inicial e segue sem produtor — mexer nele muda indicador publicado.

    ⚠️ O guarda ignora comentários e literais, via `tokenize`. A primeira versão
    lia o arquivo inteiro e acusava o próprio docstring do módulo, que explica
    em português que `sla_breached` não é produzido. É a mesma armadilha do
    guarda de log em 24/09: um detector que lê o texto que o descreve acusa a
    documentação e não o código.
    """
    import io
    import tokenize

    assert NotificationType.sla_breached not in _EMAIL_PARA_STAFF

    fonte = sla_alertas.__file__
    assert fonte is not None
    with open(fonte, encoding="utf-8") as arquivo:
        texto = arquivo.read()

    codigo = "".join(
        token.string
        for token in tokenize.generate_tokens(io.StringIO(texto).readline)
        if token.type not in (tokenize.COMMENT, tokenize.STRING)
    )

    assert "sla_breached" not in codigo
    assert "sla_warning" in codigo, "o guarda precisa enxergar o código de verdade"


# ══════════════════════════════════════════════════════════════
# 6. O lote
# ══════════════════════════════════════════════════════════════


def test_o_lote_tem_teto():
    """Mesmo teto do fechamento automático. Adotado desde o início: mudar isso
    depois significa mexer no worker com ele em produção."""
    assert _BATCH_LIMIT == 200


def test_a_chave_do_lock_e_propria():
    """Compartilhar a chave com o fechamento automático faria um worker calar o
    outro — e o sintoma seria "o aviso às vezes não sai"."""
    from app.services.ticket_lifecycle import _LOCK_KEY as LOCK_AUTO_CLOSE

    assert _LOCK_KEY == "helphs:lock:sla-warning"
    assert _LOCK_KEY != LOCK_AUTO_CLOSE


def test_o_tipo_de_alerta_e_string_e_nao_enum_nativo():
    """Convenção da casa, registrada na migration `h4c5d6e7f8g9`: acrescentar
    valor a enum nativo exige `ALTER TYPE`, e o alembic daqui roda a cadeia
    numa transação só. A Fase 2B acrescenta `response_warning`."""
    assert ALERTA_RESOLUCAO == "resolution_warning"
    assert isinstance(ALERTA_RESOLUCAO, str)


# ══════════════════════════════════════════════════════════════
# 7. O laço do worker
# ══════════════════════════════════════════════════════════════


def _settings_do_worker(intervalo: int = 0) -> MagicMock:
    settings = MagicMock()
    settings.sla_warning_interval_seconds = intervalo
    return settings


@pytest.mark.asyncio
async def test_rodada_que_levanta_nao_mata_o_laco():
    chamadas: list[int] = []
    segunda = asyncio.Event()

    async def _falsa():
        chamadas.append(len(chamadas))
        if len(chamadas) == 1:
            raise RuntimeError("Redis respondeu bobagem no meio da rodada")
        segunda.set()

    with (
        patch.object(sla_alertas, "_run_once", new=_falsa),
        patch.object(sla_alertas, "get_settings", return_value=_settings_do_worker()),
    ):
        tarefa = asyncio.create_task(sla_alertas.sla_warning_loop())
        try:
            await asyncio.wait_for(segunda.wait(), timeout=5)
        finally:
            tarefa.cancel()
            with suppress(asyncio.CancelledError):
                await tarefa

    assert len(chamadas) >= 2, f"o laço morreu na primeira exceção: {chamadas}"


@pytest.mark.asyncio
async def test_o_laco_para_quando_cancelado():
    primeira = asyncio.Event()

    async def _falsa():
        primeira.set()

    with (
        patch.object(sla_alertas, "_run_once", new=_falsa),
        patch.object(sla_alertas, "get_settings", return_value=_settings_do_worker()),
    ):
        tarefa = asyncio.create_task(sla_alertas.sla_warning_loop())
        await asyncio.wait_for(primeira.wait(), timeout=5)
        tarefa.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarefa

    assert tarefa.cancelled()


def test_intervalo_zero_desliga_o_worker():
    with patch.object(sla_alertas, "get_settings", return_value=_settings_do_worker(0)):
        assert sla_alertas.start_sla_warning_worker() is None


def test_o_lifespan_sobe_e_derruba_o_laco():
    """Guarda estrutural, e digo por que não é comportamental.

    Este projeto NÃO roda o `lifespan` em teste de propósito — ele abre conexão
    real com o PostgreSQL e com o Redis, e a nota está escrita em
    `tests/test_chat.py`. Encená-lo aqui trocaria um teste rápido por um que
    depende de infraestrutura para provar duas linhas.

    O modo de falha real é acrescentar o `start_` e esquecer o `cancel()`: a
    task sobrevive ao shutdown, e o sintoma é um processo que não termina.
    Quem lê a função inteira vê as duas metades; este teste garante que elas
    continuem juntas.
    """
    import inspect

    from app import main

    fonte = inspect.getsource(main.lifespan)

    assert "start_sla_warning_worker()" in fonte
    assert "sla_warning_task.cancel()" in fonte
    assert "await sla_warning_task" in fonte


def test_intervalo_padrao_e_de_cinco_minutos():
    """3600 s do fechamento automático perderia o limiar inteiro de um prazo de
    resposta de 30 min. 300 s é o precedente da indexação da Helô."""
    from app.core.config import Settings

    assert Settings.model_fields["sla_warning_interval_seconds"].default == 300


# ══════════════════════════════════════════════════════════════
# 8. O lock e o carimbo de rodada
# ══════════════════════════════════════════════════════════════


def _redis_falso(pegou: bool) -> AsyncMock:
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=pegou)
    return redis


@pytest.mark.asyncio
async def test_a_rodada_pede_o_lock_com_nx_e_ttl():
    redis = _redis_falso(True)
    settings = MagicMock()
    settings.sla_warning_interval_seconds = 300

    with (
        patch.object(sla_alertas, "get_settings", return_value=settings),
        patch("app.core.redis.get_redis", return_value=redis),
        patch.object(sla_alertas, "avisa_sla_proximo", new=AsyncMock(return_value=0)),
        patch("app.core.database.AsyncSessionLocal", _sessao_falsa()),
    ):
        await sla_alertas._run_once()

    redis.set.assert_awaited_once()
    args, kwargs = redis.set.await_args
    assert args[0] == _LOCK_KEY
    assert kwargs["nx"] is True
    assert kwargs["ex"] == max(60, 300 - 60)


@pytest.mark.asyncio
async def test_sem_o_lock_a_rodada_nao_trabalha_mas_conta_como_feita():
    """Ceder a vez conta: o worker que quase nunca pega o lock reportaria
    rotina parada para sempre."""
    sla_alertas._ultima_rodada_sem_erro = None
    avalia = AsyncMock(return_value=0)
    settings = MagicMock()
    settings.sla_warning_interval_seconds = 300

    with (
        patch.object(sla_alertas, "get_settings", return_value=settings),
        patch("app.core.redis.get_redis", return_value=_redis_falso(False)),
        patch.object(sla_alertas, "avisa_sla_proximo", new=avalia),
    ):
        await sla_alertas._run_once()

    avalia.assert_not_awaited()
    assert sla_alertas.ultima_rodada_sem_erro() is not None


@pytest.mark.asyncio
async def test_redis_fora_do_ar_pula_a_rodada_e_nao_carimba():
    sla_alertas._ultima_rodada_sem_erro = None
    avalia = AsyncMock(return_value=0)
    settings = MagicMock()
    settings.sla_warning_interval_seconds = 300

    async def _explode():
        raise ConnectionError("Redis inalcançável")

    with (
        patch.object(sla_alertas, "get_settings", return_value=settings),
        patch("app.core.redis.get_redis", side_effect=_explode),
        patch.object(sla_alertas, "avisa_sla_proximo", new=avalia),
    ):
        await sla_alertas._run_once()

    avalia.assert_not_awaited()
    assert sla_alertas.ultima_rodada_sem_erro() is None


@pytest.mark.asyncio
async def test_rodada_que_falhou_no_banco_nao_carimba():
    sla_alertas._ultima_rodada_sem_erro = None
    settings = MagicMock()
    settings.sla_warning_interval_seconds = 300

    with (
        patch.object(sla_alertas, "get_settings", return_value=settings),
        patch("app.core.redis.get_redis", return_value=_redis_falso(True)),
        patch.object(
            sla_alertas,
            "avisa_sla_proximo",
            new=AsyncMock(side_effect=RuntimeError("banco caiu no meio")),
        ),
        patch("app.core.database.AsyncSessionLocal", _sessao_falsa()),
    ):
        await sla_alertas._run_once()

    assert sla_alertas.ultima_rodada_sem_erro() is None


@pytest.mark.asyncio
async def test_rodada_sem_erro_carimba_o_instante():
    sla_alertas._ultima_rodada_sem_erro = None
    settings = MagicMock()
    settings.sla_warning_interval_seconds = 300
    antes = datetime.now(UTC)

    with (
        patch.object(sla_alertas, "get_settings", return_value=settings),
        patch("app.core.redis.get_redis", return_value=_redis_falso(True)),
        patch.object(sla_alertas, "avisa_sla_proximo", new=AsyncMock(return_value=3)),
        patch("app.core.database.AsyncSessionLocal", _sessao_falsa()),
    ):
        await sla_alertas._run_once()

    carimbo = sla_alertas.ultima_rodada_sem_erro()
    assert carimbo is not None and carimbo >= antes


def _sessao_falsa():
    """Fábrica de sessão que serve de gerenciador de contexto assíncrono."""
    sessao = AsyncMock()

    class _Fabrica:
        def __call__(self):
            return self

        async def __aenter__(self):
            return sessao

        async def __aexit__(self, *_):
            return False

    return _Fabrica()


# ══════════════════════════════════════════════════════════════
# 9. Contraprova: nada aqui envia e-mail
# ══════════════════════════════════════════════════════════════


def test_nenhum_smtp_e_alcancado_por_este_arquivo():
    """`settings` é sempre `MagicMock` sem SMTP configurado, e `send_email`
    retorna no primeiro `if`. O teste existe para que ninguém acrescente um
    `Settings` real aqui sem perceber o que isso ligaria."""
    from app.core.config import Settings

    vazio = Settings.model_construct(smtp_from_email="", smtp_user="")
    assert vazio.email_is_configured() is False
