"""
O portão de readiness do telefone: `scripts/diagnostico_telefone.py`.

Por que este arquivo existe
---------------------------
A constraint de presença da Fase 1C só pode nascer quando `LEGADO_INVALIDO`
for zero — e quem responde isso é este script. Se ele contar errado, a
migration nasce cedo demais e derruba o boot do contêiner, ou nasce tarde
demais e a regra fica só na aplicação para sempre. O número é o portão, então
o número precisa de teste.

O que é testado onde, e por quê
-------------------------------
O recorte de "telefone ausente" é uma cláusula SQL. Testá-la com um espelho
em Python provaria que a cópia funciona, não que a consulta funciona — então
ela roda contra **PostgreSQL de verdade**, na convenção dos outros
`*_postgres` do projeto: `TEST_POSTGRES_URL` se existir, senão `pgserver`,
e PULA se não houver nenhum dos dois.

Já o mapeamento contagem -> código de saída é função pura e é testado sem
banco nenhum, porque é isso que ele é.

Nada aqui toca em produção nem em rede.
"""

import shutil

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.diagnostico_telefone import (
    SAIDA_ERRO,
    SAIDA_HA_LEGADO,
    SAIDA_PRONTO,
    conta_legado_invalido,
    decide_saida,
)
from tests.test_dashboard_postgres import _sobe_postgres

# ══════════════════════════════════════════════════════════════
# 1. Código de saída — função pura, sem banco
# ══════════════════════════════════════════════════════════════


def test_zero_legado_libera_a_constraint():
    assert decide_saida(0) == SAIDA_PRONTO == 0


@pytest.mark.parametrize("quantos", [1, 2, 14, 999])
def test_qualquer_legado_trava_a_constraint(quantos):
    assert decide_saida(quantos) == SAIDA_HA_LEGADO == 1


def test_erro_operacional_tem_codigo_proprio():
    """`há legado` e `o script quebrou` não podem compartilhar código: um
    portão que confundisse os dois deixaria passar com o banco fora do ar."""
    assert SAIDA_ERRO == 2
    assert SAIDA_ERRO not in (SAIDA_PRONTO, SAIDA_HA_LEGADO)


def test_sem_database_url_sai_com_erro_operacional(monkeypatch):
    import asyncio

    from scripts.diagnostico_telefone import _main

    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert asyncio.run(_main()) == SAIDA_ERRO


def test_url_invalida_sai_com_erro_operacional_e_nao_com_legado(monkeypatch):
    """Banco inalcançável tem de sair 2, nunca 1 — senão o operador lê
    'ainda há legado' quando o que houve foi conexão recusada."""
    import asyncio

    from scripts.diagnostico_telefone import _main

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://ninguem:nada@127.0.0.1:1/inexistente")
    assert asyncio.run(_main()) == SAIDA_ERRO


# ══════════════════════════════════════════════════════════════
# 2. A contagem — contra PostgreSQL de verdade
# ══════════════════════════════════════════════════════════════

_CRIA = """
CREATE TABLE users (
    id     serial PRIMARY KEY,
    name   text NOT NULL,
    role   text NOT NULL,
    status text NOT NULL,
    phone  text
)
"""


@pytest.fixture(scope="module")
def url_do_banco():
    """Sobe o Postgres uma vez para o módulo — o custo grande do pgserver."""
    url, recurso = _sobe_postgres()
    if url is None:
        pytest.skip("sem PostgreSQL: defina TEST_POSTGRES_URL ou instale pgserver")

    yield url

    if recurso is not None:
        servidor, pasta = recurso
        try:
            servidor.cleanup()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(pasta, ignore_errors=True)


@pytest_asyncio.fixture
async def conexao(url_do_banco):
    """Tabela `users` mínima, recriada a cada teste.

    Mínima de propósito: o que se mede aqui é a cláusula de ausência, e montar
    o schema inteiro por `create_all` traria vinte tabelas irrelevantes e a
    extensão `vector` junto.
    """
    engine = create_async_engine(url_do_banco, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS users"))
        await conn.execute(text(_CRIA))
        yield conn
        await conn.execute(text("DROP TABLE IF EXISTS users"))
    await engine.dispose()


async def _planta(conn, role, status, phone):
    await conn.execute(
        text("INSERT INTO users (name, role, status, phone) VALUES ('x',:r,:s,:p)"),
        {"r": role, "s": status, "p": phone},
    )


@pytest.mark.asyncio
async def test_banco_vazio_conta_zero(conexao):
    assert await conta_legado_invalido(conexao) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("phone", "descricao"),
    [
        (None, "NULL"),
        ("", "string vazia"),
        ("   ", "só espaços"),
        ("\t", "tabulação"),
        ("\n", "quebra de linha"),
        (" \t \n ", "mistura de espaço, tab e quebra"),
    ],
)
async def test_cliente_ativo_sem_telefone_conta(conexao, phone, descricao):
    """`btrim` sozinho não pegaria tabulação nem quebra de linha — por isso a
    cláusula usa `\\s`, e é isso que estes casos guardam."""
    await _planta(conexao, "client", "active", phone)
    assert await conta_legado_invalido(conexao) == 1, descricao


@pytest.mark.asyncio
async def test_cliente_ativo_com_telefone_nao_conta(conexao):
    await _planta(conexao, "client", "active", "+5581999999999")
    assert await conta_legado_invalido(conexao) == 0


@pytest.mark.asyncio
async def test_telefone_fora_do_formato_nao_conta(conexao):
    """O portão mede PRESENÇA, não formato. Uma linha antiga com máscara, ou
    até com lixo, tem telefone — corrigi-la é outro assunto, e confundir os
    dois faria o portão nunca abrir."""
    await _planta(conexao, "client", "active", "(81) 99999-9999")
    await _planta(conexao, "client", "active", "abc")
    assert await conta_legado_invalido(conexao) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "status", "porque"),
    [
        ("client", "inactive", "cliente inativo não vale para a telefonia"),
        ("client", "anonymized", "a anonimização zera o telefone de propósito"),
        ("technician", "active", "a regra é de CLIENTE"),
        ("admin", "active", "a regra é de CLIENTE"),
        ("technician", "inactive", "nem papel nem situação batem"),
    ],
)
async def test_fora_do_recorte_nao_conta(conexao, role, status, porque):
    await _planta(conexao, role, status, None)
    assert await conta_legado_invalido(conexao) == 0, porque


@pytest.mark.asyncio
async def test_status_diferente_de_inactive_nao_e_o_recorte(conexao):
    """A armadilha do enum de TRÊS valores: escrever `status <> 'inactive'`
    incluiria o anonimizado, que é exatamente quem a anonimização acabou de
    deixar sem telefone. O recorte é `= 'active'`, por extenso."""
    await _planta(conexao, "client", "anonymized", None)
    await _planta(conexao, "client", "inactive", None)
    await _planta(conexao, "client", "active", None)
    assert await conta_legado_invalido(conexao) == 1


@pytest.mark.asyncio
async def test_conta_apenas_os_do_recorte_numa_base_misturada(conexao):
    """O caso realista: a contagem precisa achar os 3 no meio dos outros 7."""
    for role, status, phone in [
        ("client", "active", None),  # conta
        ("client", "active", ""),  # conta
        ("client", "active", "  "),  # conta
        ("client", "active", "+5581999999999"),
        ("client", "inactive", None),
        ("client", "anonymized", None),
        ("technician", "active", None),
        ("admin", "active", None),
        ("technician", "active", "+5581988887777"),
        ("client", "active", "8133334444"),
    ]:
        await _planta(conexao, role, status, phone)
    assert await conta_legado_invalido(conexao) == 3


# ══════════════════════════════════════════════════════════════
# 3. A saída não pode vazar dado pessoal
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_a_saida_nao_imprime_dado_pessoal_nem_a_url(conexao, capsys, monkeypatch):
    """O relatório é feito para ser colado num chamado. Se ele imprimir
    telefone, nome ou a URL do banco, deixa de ser colável — e alguém vai
    colar mesmo assim."""
    from scripts.diagnostico_telefone import _relatorio

    await conexao.execute(
        text("CREATE TABLE IF NOT EXISTS companies (id serial PRIMARY KEY, phone text)")
    )
    await _planta(conexao, "client", "active", "+5581987654321")
    await _planta(conexao, "client", "active", None)

    await _relatorio(conexao)
    saida = capsys.readouterr().out

    assert "LEGADO_INVALIDO=1" in saida
    for vazamento in ("+5581987654321", "87654321", "5581987"):
        assert vazamento not in saida, f"telefone vazou: {vazamento}"
    for chave in ("postgresql", "asyncpg", "password", "@127.0.0.1", "DATABASE_URL="):
        assert chave not in saida, f"credencial/URL vazou: {chave}"


@pytest.mark.asyncio
async def test_a_linha_parseavel_sai_exatamente_uma_vez(conexao, capsys):
    from scripts.diagnostico_telefone import _relatorio

    await conexao.execute(
        text("CREATE TABLE IF NOT EXISTS companies (id serial PRIMARY KEY, phone text)")
    )
    await _relatorio(conexao)
    saida = capsys.readouterr().out
    assert saida.count("LEGADO_INVALIDO=") == 1
    assert "LEGADO_INVALIDO=0" in saida


def test_o_script_nao_tem_verbo_de_escrita():
    """Guard de fonte: o portão é somente leitura, e isso não pode depender de
    alguém lembrar. Um INSERT/UPDATE/DELETE/DDL aqui seria mudança de natureza
    da ferramenta, não detalhe de implementação."""
    from pathlib import Path

    import scripts.diagnostico_telefone as modulo

    fonte = Path(modulo.__file__).read_text(encoding="utf-8")
    # Recorta o docstring do módulo: ele NOMEIA os verbos para dizer que não
    # os usa, e casar com a prosa transformaria o guard num falso positivo.
    corpo = fonte.split('"""', 2)[2]
    for verbo in ("INSERT ", "UPDATE ", "DELETE ", "ALTER ", "DROP ", "CREATE "):
        assert verbo not in corpo.upper(), f"o script passou a escrever: {verbo}"
