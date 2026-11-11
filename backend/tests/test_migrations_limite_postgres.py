"""
Limites de espera das migrations (`ALEMBIC_LOCK_TIMEOUT` e
`ALEMBIC_STATEMENT_TIMEOUT`), contra PostgreSQL de verdade (F1-B-04c).

Produção está em `l8g9h0i1j2k3`: o próximo boot aplica `m9h0i1j2k3l4` e
`n0i1j2k3l4m5` numa transação só, com a instância anterior ainda atendendo.
O que se prende aqui:

- o upgrade conjunto, desde `l8g9`, não toca no que já existia;
- sem as variáveis, nada muda: a migration ESPERA a transação alheia;
- com elas, desiste no prazo, e o banco fica EXATAMENTE em `l8g9` — nenhuma
  coluna, índice ou tabela de nenhuma das duas revisions;
- a tentativa seguinte, sem concorrência, passa;
- valor inválido não chega a conectar;
- um head só.

Migration como subprocesso, igual ao `start.sh`.
"""

import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.utils.migrations import LimiteDeMigrationInvalidoError, comandos_de_limite
from tests import test_chat_sequencia_migracao_postgres as _mig
from tests.test_chat_sequencia_migracao_postgres import (
    _chamado,
    _consulta,
    _mensagem_antiga,
    _usuario,
)
from tests.test_ticket_calls_postgres import _BACKEND

servidor = _mig.servidor
banco = _mig.banco

_PRODUCAO = "l8g9h0i1j2k3"
_HEAD = "n0i1j2k3l4m5"
# O que cada uma das duas revisions cria; nada disso pode sobrar de uma falha.
_RASTROS = (
    ("chat_messages", "client_message_id"),
    ("chat_messages", "client_message_fingerprint"),
    ("chat_messages", "seq"),
    ("tickets", "chat_seq"),
)


def _alembic(url: str, *args: str, timeout: float = 120, **limites: str):
    ambiente = {**os.environ, "DATABASE_URL": url, "APP_ENV": "testing"}
    for chave in ("ALEMBIC_LOCK_TIMEOUT", "ALEMBIC_STATEMENT_TIMEOUT"):
        ambiente.pop(chave, None)
    ambiente.update(limites)
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", *args],
        cwd=_BACKEND,
        env=ambiente,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout,
    )


async def _versao(url: str) -> str:
    return (await _consulta(url, "SELECT version_num FROM alembic_version"))[0][0]


async def _rastros(url: str) -> list[tuple]:
    return await _consulta(
        url,
        "SELECT table_name, column_name FROM information_schema.columns"
        " WHERE (table_name, column_name) IN"
        " (('chat_messages', 'client_message_id'), ('chat_messages', 'client_message_fingerprint'),"
        "  ('chat_messages', 'seq'), ('tickets', 'chat_seq'))"
        " ORDER BY 1, 2",
    )


class _Segura:
    """Uma transação alheia aberta em `chat_messages` — a leitura de uma
    instância que ainda atende. `ACCESS SHARE` basta para o `ALTER TABLE`
    (que pede `ACCESS EXCLUSIVE`) ter de esperar."""

    def __init__(self, url: str):
        self._motor = create_async_engine(url, poolclass=NullPool)

    async def __aenter__(self):
        self._conn = await self._motor.connect()
        await self._conn.execute(text("SELECT count(*) FROM chat_messages"))
        return self

    async def __aexit__(self, *exc):
        await self._conn.rollback()
        await self._conn.close()
        await self._motor.dispose()


async def _quem_espera(url: str) -> list[int]:
    """Os backends deste banco parados num bloqueio."""
    return [
        pid
        for (pid,) in await _consulta(
            url,
            "SELECT pid FROM pg_stat_activity WHERE datname = current_database()"
            " AND wait_event_type = 'Lock'",
        )
    ]


# ── O valor da variável ───────────────────────────────────────


def test_sem_variaveis_nada_muda():
    assert comandos_de_limite({}) == []
    assert comandos_de_limite({"ALEMBIC_LOCK_TIMEOUT": "  "}) == []


def test_as_duas_variaveis_viram_set_local():
    assert comandos_de_limite(
        {"ALEMBIC_LOCK_TIMEOUT": "3s", "ALEMBIC_STATEMENT_TIMEOUT": "2min"}
    ) == ["SET LOCAL lock_timeout = '3s'", "SET LOCAL statement_timeout = '2min'"]


@pytest.mark.parametrize("valor", ["3 s", "3s; DROP TABLE users", "-1", "1h", "abc", "1.5s"])
def test_valor_que_nao_e_duracao_simples_e_recusado(valor):
    with pytest.raises(LimiteDeMigrationInvalidoError):
        comandos_de_limite({"ALEMBIC_LOCK_TIMEOUT": valor})


def test_valor_invalido_nao_chega_a_conectar():
    # Porta onde ninguém escuta: se ele tentasse conectar, o erro seria outro.
    r = _alembic(
        "postgresql+asyncpg://x:y@127.0.0.1:9/nada",
        "upgrade",
        "head",
        ALEMBIC_LOCK_TIMEOUT="3 segundos",
    )
    assert r.returncode != 0
    assert "LimiteDeMigrationInvalidoError" in r.stderr


def test_um_head_so():
    r = _alembic("postgresql+asyncpg://x:y@127.0.0.1:9/nada", "heads")
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == [_HEAD, "(head)"]


# ── Contra o banco ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upgrade_conjunto_desde_producao_nao_toca_no_que_existia(banco):
    r = _alembic(banco, "upgrade", _PRODUCAO)
    assert r.returncode == 0, r.stderr
    autor = await _usuario(banco)
    chamado = await _chamado(banco, autor)
    for i in range(3):
        await _mensagem_antiga(banco, chamado, autor, datetime.now(UTC) - timedelta(days=i))
    antes = await _consulta(banco, "SELECT id, content, created_at FROM chat_messages ORDER BY id")

    r = _alembic(banco, "upgrade", "head", ALEMBIC_LOCK_TIMEOUT="3s")
    assert r.returncode == 0, r.stderr

    assert await _versao(banco) == _HEAD
    assert await _rastros(banco) == sorted(_RASTROS)
    [(marco,)] = await _consulta(banco, "SELECT migrada_em FROM chat_seq_corte")
    assert marco > max(q for _, _, q in antes), "o histórico fica antes do marco"
    assert (
        await _consulta(banco, "SELECT id, content, created_at FROM chat_messages ORDER BY id")
        == antes
    )
    assert await _consulta(
        banco,
        "SELECT count(*) FROM chat_messages WHERE seq IS NOT NULL OR client_message_id IS NOT NULL",
    ) == [(0,)]


@pytest.mark.asyncio
async def test_sem_limite_a_migration_espera_a_transacao_alheia(banco):
    """O comportamento de hoje, preservado: sem as variáveis, ela espera. O
    processo é encerrado pelo teste, e o backend dele também — senão ele
    seguiria na fila do bloqueio depois de o cliente sumir."""
    r = _alembic(banco, "upgrade", _PRODUCAO)
    assert r.returncode == 0, r.stderr

    async with _Segura(banco):
        with pytest.raises(subprocess.TimeoutExpired):
            _alembic(banco, "upgrade", "head", timeout=8)
        presos = await _quem_espera(banco)
        assert presos, "a migration deveria estar esperando o bloqueio"
        for pid in presos:
            await _consulta(banco, "SELECT pg_terminate_backend(:p)", p=pid)

    assert await _versao(banco) == _PRODUCAO
    assert await _rastros(banco) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "limite", [{"ALEMBIC_LOCK_TIMEOUT": "1s"}, {"ALEMBIC_STATEMENT_TIMEOUT": "1s"}]
)
async def test_com_limite_desiste_desfaz_tudo_e_a_proxima_passa(banco, limite):
    r = _alembic(banco, "upgrade", _PRODUCAO)
    assert r.returncode == 0, r.stderr

    async with _Segura(banco):
        inicio = time.monotonic()
        r = _alembic(banco, "upgrade", "head", timeout=60, **limite)
        duracao = time.monotonic() - inicio
        assert await _quem_espera(banco) == [], "ninguém pode ficar na fila depois da falha"

    assert r.returncode != 0, "a migration deveria ter desistido"
    assert "lock timeout" in r.stderr or "statement timeout" in r.stderr, r.stderr[-2000:]
    assert duracao < 30, f"desistiu em {duracao:.1f} s"
    # Nem a m9h0, que roda ANTES da n0i1 na mesma transação, ficou.
    assert await _versao(banco) == _PRODUCAO
    assert await _rastros(banco) == []
    assert (
        await _consulta(
            banco,
            "SELECT indexname FROM pg_indexes WHERE indexname IN"
            " ('uq_chat_messages_envio', 'uq_chat_messages_seq')",
        )
        == []
    )
    assert await _consulta(banco, "SELECT to_regclass('chat_seq_corte')") == [(None,)]

    # Sem ninguém segurando a tabela, a mesma tentativa passa.
    r = _alembic(banco, "upgrade", "head", **limite)
    assert r.returncode == 0, r.stderr
    assert await _versao(banco) == _HEAD
