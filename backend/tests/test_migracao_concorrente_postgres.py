"""
A migration `m9h0` + `n0i1` contra a imagem antiga que segue atendendo
(F1-B-04c), em PostgreSQL de verdade.

O que protege o modo incremental NÃO é a margem de 15 min: é a ordem dos
bloqueios. Os quatro escritores de mensagem de `0450129` travam `tickets` (o
SELECT do chamado, ou o piso do protocolo na abertura) ANTES de calcular
`created_at` no relógio da aplicação, e seguram a trava até o commit. A `n0i1`
pega `ACCESS EXCLUSIVE` em `tickets` antes de gravar o marco. Logo, mensagem
antiga que comita depois da migration tem `created_at` depois do marco — e é
vista. A margem sobra para desvio de relógio entre aplicação e banco.

Aqui:

- A: o escritor antigo esperando a migration em `tickets` calcula
  `created_at` depois do marco; o chamado sai do incremental até o script.
- B: o ciclo `tickets` × `chat_messages` (o escritor trava o chamado e depois
  grava a mensagem; a migration trava `chat_messages` na `m9h0` e depois
  `tickets` na `n0i1`) termina em deadlock. A vítima NÃO é afirmada: o
  PostgreSQL roda a detecção em quem espera há `deadlock_timeout` e, na
  prática, derruba quem fechou o ciclo — mas isso não é contrato. O teste
  cobre as duas ordens e prova o que vale para QUALQUER vítima.
- A ordem relevante das operações da `n0i1`, pelo SQL do modo offline.

O escritor antigo é SQL cru com as colunas de `0450129` — o mesmo INSERT da
imagem antiga, sem `seq`.
"""

import asyncio
import time
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services.chat_sequencia import incremental_disponivel
from scripts.numera_mensagens_sem_seq import numera
from tests import test_chat_sequencia_migracao_postgres as _mig
from tests.test_chat_sequencia_migracao_postgres import _chamado, _consulta, _usuario
from tests.test_migrations_limite_postgres import _HEAD, _PRODUCAO, _alembic, _rastros, _versao

servidor = _mig.servidor
banco = _mig.banco

_DEADLOCK = "40P01"


async def _esperando(url: str) -> list[tuple]:
    """(pid, tabela, modo) de cada pedido de bloqueio ainda não concedido."""
    return await _consulta(
        url,
        "SELECT l.pid, l.relation::regclass::text, l.mode FROM pg_locks l"
        " WHERE NOT l.granted AND l.locktype = 'relation' ORDER BY l.pid",
    )


async def _espera_ate(url: str, condicao, prazo: float = 20.0) -> list[tuple]:
    fim = time.monotonic() + prazo
    while time.monotonic() < fim:
        agora = await _esperando(url)
        if condicao(agora):
            return agora
        await asyncio.sleep(0.05)
    raise AssertionError(f"bloqueio esperado não apareceu: {await _esperando(url)}")


def _migration_espera(tabela: str):
    return lambda linhas: any(t == tabela and m == "AccessExclusiveLock" for _, t, m in linhas)


def _pid_espera(pid: int):
    return lambda linhas: any(p == pid for p, _, _ in linhas)


async def _deadlock_timeout(url: str) -> float:
    [(ms,)] = await _consulta(
        url, "SELECT setting::int FROM pg_settings WHERE name = 'deadlock_timeout'"
    )
    return ms / 1000


class _EscritorAntigo:
    """A ordem do `create_message` de `0450129`, um passo por vez: SELECT do
    chamado, `created_at` no relógio da aplicação, INSERT sem `seq`, commit."""

    def __init__(self, url: str, chamado: uuid.UUID, autor: uuid.UUID):
        self._motor = create_async_engine(url, poolclass=NullPool)
        self.chamado, self.autor = chamado, autor
        self.id = uuid.uuid4()
        self.antes_do_select: datetime | None = None
        self.created_at: datetime | None = None
        self.erro: str | None = None

    async def abre(self) -> int:
        self._conn = await self._motor.connect()
        return (await self._conn.execute(text("SELECT pg_backend_pid()"))).scalar_one()

    async def trava_o_chamado(self) -> None:
        self.antes_do_select = datetime.now(UTC)
        await self._conn.execute(text("SELECT id FROM tickets WHERE id = :t"), {"t": self.chamado})
        self.created_at = datetime.now(UTC)

    async def grava_e_comita(self) -> None:
        try:
            await self._conn.execute(
                text(
                    "INSERT INTO chat_messages (id, ticket_id, sender_id, content, is_system,"
                    " is_ai, created_at) VALUES (:id, :t, :s, 'da imagem antiga', false,"
                    " false, :q)"
                ),
                {"id": self.id, "t": self.chamado, "s": self.autor, "q": self.created_at},
            )
            await self._conn.commit()
        except DBAPIError as exc:
            self.erro = getattr(exc.orig, "sqlstate", None) or type(exc.orig).__name__
            await self._conn.rollback()

    async def fecha(self) -> None:
        await self._conn.close()
        await self._motor.dispose()


class _Segura:
    """Uma transação alheia com `ACCESS SHARE` numa tabela."""

    def __init__(self, url: str, tabela: str):
        self._motor = create_async_engine(url, poolclass=NullPool)
        self._tabela = tabela

    async def abre(self) -> "_Segura":
        self._conn = await self._motor.connect()
        await self._conn.execute(text(f"SELECT count(*) FROM {self._tabela}"))  # noqa: S608
        return self

    async def solta(self) -> None:
        await self._conn.rollback()
        await self._conn.close()
        await self._motor.dispose()


def _migra(url: str) -> asyncio.Future:
    return asyncio.ensure_future(asyncio.to_thread(_alembic, url, "upgrade", "head", timeout=90))


async def _disponivel(url: str, chamado: uuid.UUID) -> bool:
    motor = create_async_engine(url, poolclass=NullPool)
    try:
        async with async_sessionmaker(motor)() as s:
            return await incremental_disponivel(s, chamado)
    finally:
        await motor.dispose()


async def _producao_com_um_chamado(url: str) -> tuple[uuid.UUID, uuid.UUID]:
    r = _alembic(url, "upgrade", _PRODUCAO)
    assert r.returncode == 0, r.stderr
    autor = await _usuario(url)
    return autor, await _chamado(url, autor)


# ── A: o escritor esperando a migration ───────────────────────


@pytest.mark.asyncio
async def test_cenario_a_escritor_preso_em_tickets_calcula_created_at_depois_do_marco(banco):
    autor, chamado = await _producao_com_um_chamado(banco)

    # Um relatório longo lendo `tickets`: a migration passa da m9h0 e para no
    # ALTER TABLE tickets da n0i1.
    relatorio = await _Segura(banco, "tickets").abre()
    migration = _migra(banco)
    await _espera_ate(banco, _migration_espera("tickets"))

    escritor = _EscritorAntigo(banco, chamado, autor)
    pid = await escritor.abre()
    travando = asyncio.ensure_future(escritor.trava_o_chamado())
    fila = await _espera_ate(banco, _pid_espera(pid))
    # A ordem: ele espera em `tickets`, ANTES de ter `created_at`.
    assert (pid, "tickets", "AccessShareLock") in fila
    assert escritor.created_at is None

    await asyncio.sleep(1)
    await relatorio.solta()
    r = await migration
    assert r.returncode == 0, r.stderr[-2000:]
    await asyncio.wait_for(travando, 30)
    await escritor.grava_e_comita()
    await escritor.fecha()
    assert escritor.erro is None

    [(marco,)] = await _consulta(banco, "SELECT migrada_em FROM chat_seq_corte")
    assert escritor.created_at > marco
    # Se ele calculasse `created_at` antes de travar o chamado, a mensagem
    # ficaria antes do marco pelo tempo inteiro da espera — é isso que a ordem
    # impede.
    assert (marco - escritor.antes_do_select).total_seconds() >= 1
    assert await _consulta(banco, "SELECT seq FROM chat_messages WHERE id = :m", m=escritor.id) == [
        (None,)
    ]

    # Sem perda silenciosa: quem ancorou em 0 logo depois da migration não
    # usa mais o incremental neste chamado; o script a põe depois da âncora.
    assert await _disponivel(banco, chamado) is False
    assert await numera(banco) == {str(chamado): 1}
    assert await _consulta(banco, "SELECT seq FROM chat_messages WHERE id = :m", m=escritor.id) == [
        (1,)
    ]
    assert await _disponivel(banco, chamado) is True


# ── B: o deadlock ─────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("fecha_o_ciclo", ["migration", "escritor"])
async def test_cenario_b_ciclo_tickets_chat_messages_qualquer_vitima_sem_estado_parcial(
    banco, fecha_o_ciclo, request
):
    """Duas ordens do mesmo ciclo. Em `migration`, o escritor já espera em
    `chat_messages` (atrás da migration na fila) quando ela pede `tickets`. Em
    `escritor`, a migration já espera em `tickets` quando ele grava a
    mensagem. Quem morre, o PostgreSQL escolhe; o teste afirma o que vale nos
    dois desfechos."""
    autor, chamado = await _producao_com_um_chamado(banco)
    espera = await _deadlock_timeout(banco) + 0.5
    escritor = _EscritorAntigo(banco, chamado, autor)
    pid = await escritor.abre()

    if fecha_o_ciclo == "migration":
        leitor = await _Segura(banco, "chat_messages").abre()
        await escritor.trava_o_chamado()
        migration = _migra(banco)
        await _espera_ate(banco, _migration_espera("chat_messages"))
        gravando = asyncio.ensure_future(escritor.grava_e_comita())
        await _espera_ate(banco, _pid_espera(pid))
        await asyncio.sleep(espera)  # a detecção dele roda antes de o ciclo existir
        await leitor.solta()
    else:
        await escritor.trava_o_chamado()
        migration = _migra(banco)
        await _espera_ate(banco, _migration_espera("tickets"))
        await asyncio.sleep(espera)  # a detecção dela roda antes de o ciclo existir
        gravando = asyncio.ensure_future(escritor.grava_e_comita())

    r = await migration
    await asyncio.wait_for(gravando, 30)
    await escritor.fecha()

    migration_morreu = r.returncode != 0
    escritor_morreu = escritor.erro is not None
    assert migration_morreu != escritor_morreu, (r.returncode, escritor.erro, r.stderr[-1500:])
    # Registrado, não afirmado: aparece no relatório junit (`--junitxml`).
    request.node.user_properties.append(("vitima", "migration" if migration_morreu else "escritor"))

    if migration_morreu:
        assert "deadlock detected" in r.stderr, r.stderr[-1500:]
        # Rollback integral: nem a m9h0, que rodou antes, ficou.
        assert await _versao(banco) == _PRODUCAO
        assert await _rastros(banco) == []
        assert await _consulta(banco, "SELECT to_regclass('chat_seq_corte')") == [(None,)]
        assert (
            await _consulta(
                banco,
                "SELECT indexname FROM pg_indexes WHERE indexname IN"
                " ('uq_chat_messages_envio', 'uq_chat_messages_seq')",
            )
            == []
        )
        # A mensagem entrou ANTES da migration: é histórico.
        assert await _consulta(
            banco, "SELECT count(*) FROM chat_messages WHERE id = :m", m=escritor.id
        ) == [(1,)]
        # Solta a trava, a mesma migration passa.
        r = _alembic(banco, "upgrade", "head")
        assert r.returncode == 0, r.stderr[-1500:]
        assert await _versao(banco) == _HEAD
        [(marco,)] = await _consulta(banco, "SELECT migrada_em FROM chat_seq_corte")
        assert escritor.created_at < marco
        # Histórico nunca é numerado; na janela, o chamado fica no legado.
        assert await numera(banco) == {}
        assert await _disponivel(banco, chamado) is False
    else:
        assert escritor.erro == _DEADLOCK
        # O envio falhou com erro — nada gravado, nada a numerar.
        assert await _versao(banco) == _HEAD
        assert await _consulta(
            banco, "SELECT count(*) FROM chat_messages WHERE id = :m", m=escritor.id
        ) == [(0,)]
        assert await _disponivel(banco, chamado) is True


# ── A ordem das operações ─────────────────────────────────────


def _sql_offline() -> list[str]:
    r = _alembic(
        "postgresql+asyncpg://x:y@127.0.0.1:9/nada", "upgrade", f"{_PRODUCAO}:head", "--sql"
    )
    assert r.returncode == 0, r.stderr
    # O alembic põe `-- Running upgrade a -> b` antes do primeiro comando de cada revision.
    sem_comentario = "\n".join(
        linha for linha in r.stdout.splitlines() if not linha.lstrip().startswith("--")
    )
    return [c.strip() for c in sem_comentario.split(";") if c.strip()]


def _indice(comandos: list[str], comeco: str) -> int:
    achados = [i for i, c in enumerate(comandos) if c.upper().startswith(comeco.upper())]
    assert achados, f"{comeco!r} não está no SQL da migration"
    return achados[0]


def test_o_marco_vem_depois_do_bloqueio_de_tickets_e_e_o_ultimo_comando():
    """Se o marco for gravado antes do `ALTER TABLE tickets` — ou se outra
    operação entrar depois dele —, a regra do cabeçalho deixa de valer: um
    escritor antigo poderia comitar depois do marco com `created_at` de
    antes."""
    comandos = _sql_offline()
    tickets = _indice(comandos, "ALTER TABLE tickets ADD COLUMN chat_seq")
    marco = _indice(comandos, "INSERT INTO chat_seq_corte")
    versao = _indice(comandos, f"UPDATE alembic_version SET version_num='{_HEAD}'")

    assert tickets < marco
    assert "clock_timestamp()" in comandos[marco]
    assert marco == versao - 1, comandos[marco + 1 : versao]
