"""
RS-04 — o enfileiramento do e-mail de conta em segundo plano deixa rastro.

Por que este arquivo existe
----------------------------
`forgot_password` e `resend_verification` respondem ANTES de gravar na
`email_outbox`: a gravação vai para `BackgroundTasks`, de propósito, para o
tempo de resposta não denunciar quem tem conta. Até esta frente, esse caminho
tinha três defeitos de observabilidade, medidos na auditoria de novembro/2026
("pedi a redefinição e o e-mail não chegou"):

* a linha `... queued` saía ANTES do `INSERT` — dizia "enfileirado" sem que
  nada estivesse gravado;
* não havia linha nenhuma confirmando o `commit`;
* uma falha do `INSERT`/`commit` não tinha registro próprio — e o traceback
  cru de um erro de banco carrega o SQL e os parâmetros.

O que estes testes fixam: agendamento, confirmação SÓ depois do commit e falha
com a CLASSE do erro — as três linhas ligadas por um identificador de pedido
(`intent`), e nenhuma delas com e-mail, `user_id`, token, SQL ou texto cru de
exceção.

Tudo aqui é mock: a garantia contra PostgreSQL de verdade (a `UNIQUE` de
`dedup_key` estourando dentro do `commit`) mora em
`test_email_outbox_account_postgres.py`.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from loguru import logger
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.config import get_settings
from app.main import app
from app.models.models import EmailOutbox, UserStatus
from app.services import email_outbox
from app.services.email_outbox import enfileira_email_de_conta_em_segundo_plano

_settings = get_settings()

_USER_ID = uuid.uuid4()
_EMAIL = "cliente.rs04@test.com"

_GRAVADO = "e-mail de conta gravado na fila"
_FALHA = "falha ao gravar e-mail de conta na fila"

# O que um erro de banco de verdade carrega no `str()`: o SQL e os parâmetros.
_SQL = "INSERT INTO email_outbox (id, user_id, event_type, dedup_key) VALUES (...)"


@pytest.fixture()
def linhas_de_log():
    """Tudo o que o loguru emitir durante o teste, como `(nível, mensagem)`."""
    capturadas: list[tuple[str, str]] = []

    def _sink(mensagem) -> None:
        registro = mensagem.record
        capturadas.append((registro["level"].name, registro["message"]))

    sink_id = logger.add(_sink, level="DEBUG", format="{message}")
    yield capturadas
    logger.remove(sink_id)


def _sessao(*, commit=None, eventos: list[str] | None = None):
    """Sessão de mentira no formato de `AsyncSessionLocal()`.

    `add` guarda a linha recebida; `commit` falha com o que for passado, e
    anota a ordem em `eventos` para o teste que prova "só depois do commit".
    """
    sessao = MagicMock()
    sessao.adicionadas = []
    sessao.add = MagicMock(side_effect=sessao.adicionadas.append)

    async def _commit() -> None:
        if eventos is not None:
            eventos.append("commit")
        if commit is not None:
            raise commit

    sessao.commit = AsyncMock(side_effect=_commit)

    contexto = MagicMock()
    contexto.__aenter__ = AsyncMock(return_value=sessao)
    contexto.__aexit__ = AsyncMock(return_value=False)
    fabrica = MagicMock(return_value=contexto)
    fabrica.sessao = sessao
    return fabrica


def _com_mensagem(linhas: list[tuple[str, str]], trecho: str) -> list[tuple[str, str]]:
    return [linha for linha in linhas if trecho in linha[1]]


def _nada_sensivel(linhas: list[tuple[str, str]], *proibidos: str) -> None:
    """Nenhuma linha carrega e-mail, `user_id`, SQL ou parâmetro do banco."""
    for _nivel, mensagem in linhas:
        for proibido in (str(_USER_ID), _EMAIL, "INSERT INTO", *proibidos):
            assert proibido not in mensagem, f"vazou {proibido!r} no log: {mensagem}"


# ═══════════════════════════════════════════════════════════════
# O serviço: confirmação e falha de persistência
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_gravacao_confirmada_so_depois_do_commit(linhas_de_log):
    eventos: list[str] = []
    fabrica = _sessao(eventos=eventos)
    intent = uuid.uuid4()

    def _anota(mensagem) -> None:
        if _GRAVADO in mensagem.record["message"]:
            eventos.append("log")

    sink_id = logger.add(_anota, level="DEBUG", format="{message}")
    try:
        with patch("app.core.database.AsyncSessionLocal", new=fabrica):
            await enfileira_email_de_conta_em_segundo_plano(_USER_ID, "password_reset", intent)
    finally:
        logger.remove(sink_id)

    assert eventos == ["commit", "log"], f"a confirmação saiu antes do commit: {eventos}"

    (linha,) = fabrica.sessao.adicionadas
    assert isinstance(linha, EmailOutbox)

    (confirmacao,) = _com_mensagem(linhas_de_log, _GRAVADO)
    assert confirmacao[0] == "INFO"
    assert "event=password_reset" in confirmacao[1]
    assert f"intent={intent}" in confirmacao[1]
    assert f"outbox_id={linha.id}" in confirmacao[1]
    assert not _com_mensagem(linhas_de_log, _FALHA)
    _nada_sensivel(linhas_de_log)


@pytest.mark.asyncio
async def test_falha_no_insert_e_registrada_sem_sql_nem_parametros(linhas_de_log):
    """O `INSERT` só vai ao banco no flush do `commit` — é lá que ele estoura.

    `IntegrityError` de verdade, não uma exceção inventada: o `str()` dela é
    o que traz `[SQL: ...]` e `[parameters: ...]`, e é isso que não pode
    chegar ao log.
    """
    intent = uuid.uuid4()
    erro = IntegrityError(_SQL, {"user_id": str(_USER_ID), "email": _EMAIL}, Exception("23505"))
    assert str(_USER_ID) in str(erro), "o teste precisa de um erro que carregue o parâmetro"

    with patch("app.core.database.AsyncSessionLocal", new=_sessao(commit=erro)):
        # Não levanta: a resposta HTTP já saiu, não há a quem devolver o erro.
        await enfileira_email_de_conta_em_segundo_plano(_USER_ID, "password_reset", intent)

    (falha,) = _com_mensagem(linhas_de_log, _FALHA)
    assert falha[0] == "ERROR"
    assert "event=password_reset" in falha[1]
    assert f"intent={intent}" in falha[1]
    assert "error=IntegrityError" in falha[1]
    assert not _com_mensagem(linhas_de_log, _GRAVADO), "não pode confirmar o que não gravou"
    _nada_sensivel(linhas_de_log, "23505", "parameters")


@pytest.mark.asyncio
async def test_falha_no_commit_e_registrada_sem_texto_cru(linhas_de_log):
    intent = uuid.uuid4()
    erro = OperationalError(_SQL, {"user_id": str(_USER_ID)}, Exception("connection reset"))

    with patch("app.core.database.AsyncSessionLocal", new=_sessao(commit=erro)):
        await enfileira_email_de_conta_em_segundo_plano(_USER_ID, "verification", intent)

    (falha,) = _com_mensagem(linhas_de_log, _FALHA)
    assert falha[0] == "ERROR"
    assert "event=verification" in falha[1]
    assert f"intent={intent}" in falha[1]
    assert "error=OperationalError" in falha[1]
    assert not _com_mensagem(linhas_de_log, _GRAVADO)
    _nada_sensivel(linhas_de_log, "connection reset")


@pytest.mark.asyncio
async def test_falha_ao_abrir_a_sessao_e_registrada(linhas_de_log):
    """Banco fora do ar: o erro vem antes de existir sessão para dar commit."""
    intent = uuid.uuid4()
    contexto = MagicMock()
    contexto.__aenter__ = AsyncMock(side_effect=ConnectionRefusedError("10.0.0.5:5432 recusou"))
    contexto.__aexit__ = AsyncMock(return_value=False)

    with patch("app.core.database.AsyncSessionLocal", new=MagicMock(return_value=contexto)):
        await enfileira_email_de_conta_em_segundo_plano(_USER_ID, "password_reset", intent)

    (falha,) = _com_mensagem(linhas_de_log, _FALHA)
    assert "error=ConnectionRefusedError" in falha[1]
    assert f"intent={intent}" in falha[1]
    _nada_sensivel(linhas_de_log, "10.0.0.5")


@pytest.mark.asyncio
async def test_cancelamento_nao_e_engolido(linhas_de_log):
    """`CancelledError` é o desligamento do processo, não falha de gravação:

    engoli-la seguraria o shutdown, e registrá-la como erro de persistência
    mentiria sobre o que aconteceu.
    """
    with patch(
        "app.core.database.AsyncSessionLocal",
        new=_sessao(commit=asyncio.CancelledError()),
    ):
        with pytest.raises(asyncio.CancelledError):
            await enfileira_email_de_conta_em_segundo_plano(
                _USER_ID, "password_reset", uuid.uuid4()
            )

    assert not _com_mensagem(linhas_de_log, _GRAVADO)
    assert not _com_mensagem(linhas_de_log, _FALHA)


# ═══════════════════════════════════════════════════════════════
# Os dois endpoints: agendamento, neutralidade e erro em segundo plano
# ═══════════════════════════════════════════════════════════════


def _mock_user(*, email_verified=True, status=UserStatus.active):
    u = MagicMock()
    u.id = _USER_ID
    u.email = _EMAIL
    u.status = status
    u.email_verified = email_verified
    return u


def _db_with(user):
    resultado = MagicMock()
    resultado.scalar_one_or_none.return_value = user
    sessao = AsyncMock()
    sessao.execute = AsyncMock(return_value=resultado)

    async def _gen():
        yield sessao

    return _gen


@pytest.fixture()
def smtp_ligado():
    original = _settings.smtp_from_email
    original_flag = _settings.email_verification_enabled
    _settings.smtp_from_email = "naoresponda@healthsafety.com"
    _settings.email_verification_enabled = True
    yield
    _settings.smtp_from_email = original
    _settings.email_verification_enabled = original_flag
    app.dependency_overrides.clear()


async def _post(caminho: str, email: str = _EMAIL):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.post(caminho, json={"email": email})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("caminho", "event_type", "agendado", "usuario"),
    [
        (
            "/api/v1/auth/forgot-password",
            "password_reset",
            "Password reset scheduled",
            {"email_verified": True},
        ),
        (
            "/api/v1/auth/resend-verification",
            "verification",
            "Verification email scheduled (resend)",
            {"email_verified": False},
        ),
    ],
)
async def test_agendamento_registra_o_mesmo_intent_que_vai_para_a_fila(
    smtp_ligado, linhas_de_log, caminho, event_type, agendado, usuario
):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_with(_mock_user(**usuario))
    enfileira = AsyncMock()

    with patch("app.routers.auth.enfileira_email_de_conta_em_segundo_plano", new=enfileira):
        r = await _post(caminho)

    assert r.status_code == 200
    enfileira.assert_awaited_once()
    user_id, tipo, intent = enfileira.await_args.args
    assert (user_id, tipo) == (_USER_ID, event_type)

    (linha,) = _com_mensagem(linhas_de_log, agendado)
    assert linha[0] == "INFO"
    assert linha[1] == f"{agendado}: intent={intent}"
    # "queued" dizia "enfileirado" antes de qualquer gravação — não volta.
    assert not _com_mensagem(linhas_de_log, "queued")
    _nada_sensivel(linhas_de_log)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "usuario",
    [
        None,  # conta inexistente — e também o e-mail que diverge do cadastro
        {"status": UserStatus.inactive},
        {"status": UserStatus.anonymized},
    ],
    ids=["inexistente-ou-divergente", "inativa", "anonimizada"],
)
async def test_esqueci_senha_ramo_neutro_responde_igual_e_nao_agenda(
    smtp_ligado, linhas_de_log, usuario
):
    from app.core.database import get_db

    enfileira = AsyncMock()

    with patch("app.routers.auth.enfileira_email_de_conta_em_segundo_plano", new=enfileira):
        app.dependency_overrides[get_db] = _db_with(_mock_user())
        elegivel = await _post("/api/v1/auth/forgot-password")
        enfileira.reset_mock()
        linhas_de_log.clear()

        app.dependency_overrides[get_db] = _db_with(
            None if usuario is None else _mock_user(**usuario)
        )
        neutro = await _post("/api/v1/auth/forgot-password", "outro.endereco@test.com")

    assert neutro.status_code == elegivel.status_code == 200
    assert neutro.json() == elegivel.json()
    assert neutro.headers.get("content-length") == elegivel.headers.get("content-length")
    enfileira.assert_not_awaited()
    # O log também não pode virar oráculo: nada de "pedido recusado para X".
    assert not _com_mensagem(linhas_de_log, "scheduled")
    assert not _com_mensagem(linhas_de_log, "outro.endereco@test.com")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("caminho", "usuario"),
    [
        ("/api/v1/auth/forgot-password", {"email_verified": True}),
        ("/api/v1/auth/resend-verification", {"email_verified": False}),
    ],
)
async def test_erro_em_segundo_plano_nao_muda_a_resposta_nem_vaza_excecao(
    smtp_ligado, linhas_de_log, caminho, usuario
):
    """O caminho inteiro, sem mock do serviço: resposta, tarefa e falha.

    O `ASGITransport` re-levanta o que escapar do app. Se a exceção do
    `commit` subisse pela `BackgroundTask`, este `post` levantaria — é isso
    que entregava o traceback cru (com o SQL) ao log do servidor.
    """
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_with(_mock_user(**usuario))
    erro = OperationalError(_SQL, {"user_id": str(_USER_ID)}, Exception("server closed"))

    with patch("app.core.database.AsyncSessionLocal", new=_sessao(commit=erro)):
        com_falha = await _post(caminho)

    with patch("app.core.database.AsyncSessionLocal", new=_sessao()):
        sem_falha = await _post(caminho)

    assert com_falha.status_code == sem_falha.status_code == 200
    assert com_falha.json() == sem_falha.json()

    (falha,) = _com_mensagem(linhas_de_log, _FALHA)
    assert "error=OperationalError" in falha[1]
    (gravado,) = _com_mensagem(linhas_de_log, _GRAVADO)

    # As três linhas se ligam pelo `intent`: a agendada, e a de desfecho.
    agendadas = _com_mensagem(linhas_de_log, "scheduled")
    assert len(agendadas) == 2
    intents = [linha[1].split("intent=")[1].split()[0] for linha in agendadas]
    assert f"intent={intents[0]}" in falha[1]
    assert f"intent={intents[1]}" in gravado[1]
    assert intents[0] != intents[1]
    _nada_sensivel(linhas_de_log, "server closed")


def test_o_servico_nao_registra_user_id_nem_excecao_crua():
    """Trava de regressão sobre o TEXTO da função.

    Os testes acima provam os cenários ensaiados; este impede que alguém
    acrescente `{user_id}` ou `{exc}` a uma linha de log desta função num
    ramo que nenhum cenário exercita.
    """
    import inspect

    fonte = inspect.getsource(email_outbox.enfileira_email_de_conta_em_segundo_plano)
    # Cada chamada vai de `logger.<nível>(` até o `)` que fecha, sozinho na linha.
    chamadas = [
        trecho.split("\n        )\n")[0].split("\n    )\n")[0]
        for trecho in fonte.split("logger.")[1:]
        if trecho.startswith(("info(", "error(", "warning("))
    ]
    assert len(chamadas) == 2, "a função registra exatamente dois desfechos"
    for chamada in chamadas:
        assert "{user_id" not in chamada
        assert "{exc}" not in chamada and "str(exc)" not in chamada
