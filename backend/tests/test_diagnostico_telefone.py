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

⚠️ Por que `CREATE TEMP TABLE`, e não tabela comum
--------------------------------------------------
A primeira versão deste arquivo criava uma tabela `users` FÍSICA e a
derrubava a cada teste. Passava aqui e **quebrava no CI**, com 18 erros de
`DependentObjectsStillExistError: cannot drop table users because other
objects depend on it`.

A diferença não era o PostgreSQL: era a topologia. Sem `TEST_POSTGRES_URL`,
`_sobe_postgres` cria um servidor e um banco NOVOS a cada chamada, então cada
módulo ganha um banco vazio. **No CI a variável existe**, a mesma função
devolve sempre o banco COMPARTILHADO — onde as migrations já rodaram e
`public.users` tem doze chaves estrangeiras apontando para ela. O `DROP` batia
nelas.

A tabela temporária resolve os dois lados de uma vez: ela vive no schema
`pg_temp` da própria sessão, que vem antes de `public` no `search_path`, então
o `FROM users` da consulta real resolve para ela — e `public.users` não é
tocada, lida nem derrubada. O ciclo de vida é o da conexão, então não há
teardown a esquecer.

**Não existe um único `DROP TABLE` neste arquivo**, e há teste guardando isso.

Nada aqui toca em produção nem em rede.
"""

import shutil

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

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
# 2. A contagem — contra PostgreSQL de verdade, em tabela TEMPORÁRIA
# ══════════════════════════════════════════════════════════════

# Só as colunas que as consultas do script realmente tocam. Reconstruir o
# model `User` inteiro aqui seria manter um segundo schema em paralelo, e o
# que se mede é o SQL do script, não a declaração da aplicação.
_TEMP_USERS = """
CREATE TEMP TABLE users (
    role   text NOT NULL,
    status text NOT NULL,
    phone  text
)
"""

# O bloco 5 do relatório consulta `companies`. Temporária pelo mesmo motivo.
_TEMP_COMPANIES = "CREATE TEMP TABLE companies (phone text)"


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
    """Uma conexão por teste, com `users` e `companies` TEMPORÁRIAS.

    `NullPool` não é detalhe: com o pool padrão, a conexão física volta para a
    piscina levando as tabelas temporárias junto, e o próximo teste esbarraria
    num `relation "users" already exists`. Sem pool, cada teste abre e fecha a
    sua sessão — e o fim da sessão é o que apaga as temporárias, de graça.

    Por isso também não há teardown aqui: não existe `DROP` neste arquivo.
    """
    engine = create_async_engine(url_do_banco, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with engine.connect() as conn:
        await conn.execute(text(_TEMP_USERS))
        await conn.execute(text(_TEMP_COMPANIES))
        yield conn
    await engine.dispose()


async def _planta(conn, role, status, phone):
    await conn.execute(
        text("INSERT INTO users (role, status, phone) VALUES (:r,:s,:p)"),
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
# 3. Isolamento: a suíte não pode tocar em public.users
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_a_consulta_real_resolve_para_a_tabela_temporaria(conexao):
    """A prova de que o isolamento funciona onde importa: no `FROM users` da
    consulta do script, e não só no `INSERT` do teste.

    `'users'::regclass` resolve pelo `search_path` da sessão — o mesmo caminho
    que a consulta real percorre. Se o schema não começar com `pg_temp`, o
    script está lendo a tabela compartilhada, e o teste que passa aqui estaria
    medindo o banco de outra pessoa.
    """
    schema = (
        await conexao.execute(
            text(
                "SELECT n.nspname FROM pg_class c"
                " JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE c.oid = 'users'::regclass"
            )
        )
    ).scalar_one()
    assert schema.startswith("pg_temp"), f"`users` resolveu para {schema}, não para pg_temp"


@pytest.mark.asyncio
async def test_public_users_sobrevive_intacta_ao_diagnostico(conexao):
    """Regressão do defeito que derrubou o CI do PR #30.

    Quando o banco tem o schema HelpHS completo — que é a condição do CI —
    `public.users` existe e carrega doze chaves estrangeiras. Rodar o
    diagnóstico não pode alterá-la, lê-la nem derrubá-la. Onde ela não existir
    (banco vazio do desenvolvimento), o que se afirma é que o diagnóstico
    também **não a cria**.
    """
    existia = (await conexao.execute(text("SELECT to_regclass('public.users')"))).scalar()

    antes = None
    if existia is not None:
        antes = (await conexao.execute(text("SELECT count(*) FROM public.users"))).scalar_one()

    await _planta(conexao, "client", "active", None)
    assert await conta_legado_invalido(conexao) == 1

    depois_existe = (await conexao.execute(text("SELECT to_regclass('public.users')"))).scalar()

    if existia is not None:
        assert depois_existe is not None, "public.users foi DERRUBADA pelo diagnóstico"
        depois = (await conexao.execute(text("SELECT count(*) FROM public.users"))).scalar_one()
        assert depois == antes, "public.users foi ALTERADA pelo diagnóstico"
    else:
        assert depois_existe is None, "o diagnóstico CRIOU uma public.users"


def _sql_que_este_arquivo_executa() -> list[str]:
    """Todo literal passado a `text(...)` neste arquivo.

    Por AST, e não por busca de substring: a prosa aqui NOMEIA o comando que
    quebrou o CI para explicá-lo, e um `grep` casaria com a explicação. O que
    interessa é o que chega ao banco.
    """
    import ast
    from pathlib import Path

    arvore = ast.parse(Path(__file__).read_text(encoding="utf-8"))

    # As DDLs das temporárias moram em constantes de módulo, então `text(...)`
    # recebe um nome e não um literal. Sem resolver isso, o guard passaria a
    # não enxergar justamente o SQL que ele existe para conferir.
    constantes: dict[str, str] = {
        alvo.id: no.value.value
        for no in ast.walk(arvore)
        if isinstance(no, ast.Assign)
        and isinstance(no.value, ast.Constant)
        and isinstance(no.value.value, str)
        for alvo in no.targets
        if isinstance(alvo, ast.Name)
    }

    achados: list[str] = []
    for no in ast.walk(arvore):
        if not (
            isinstance(no, ast.Call)
            and isinstance(no.func, ast.Name)
            and no.func.id == "text"
            and no.args
        ):
            continue
        arg = no.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            achados.append(arg.value)
        elif isinstance(arg, ast.Name) and arg.id in constantes:
            achados.append(constantes[arg.id])
        else:
            raise AssertionError(f"SQL que o guard não consegue ler: {ast.dump(arg)[:80]}")
    return achados


def test_a_suite_nao_derruba_tabela_nenhuma():
    """Guard de fonte: foi um comando de derrubar tabela que quebrou o CI com
    18 erros. A correção é a tabela temporária, cujo ciclo de vida é o da
    sessão — então não há motivo para a suíte destruir nada, e reintroduzir
    isso é o caminho de volta para o mesmo defeito.
    """
    executado = " ".join(_sql_que_este_arquivo_executa()).upper()
    assert executado, "a varredura por AST não achou SQL nenhum — o guard ficou cego"

    for proibido in ("DROP ", "CASCADE", "TRUNCATE", "ALTER "):
        assert proibido not in executado, f"a suíte voltou a executar {proibido.strip()}"
    assert "CREATE TEMP TABLE" in executado, "as tabelas do teste deixaram de ser temporárias"
    # E o que é criado tem de ser SEMPRE temporário: um `CREATE TABLE` comum
    # em `public` é exatamente o defeito original, com outro nome.
    assert "CREATE TABLE" not in executado.replace("CREATE TEMP TABLE", "")


# ══════════════════════════════════════════════════════════════
# 4. A saída não pode vazar dado pessoal
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_a_saida_nao_imprime_dado_pessoal_nem_a_url(conexao, capsys):
    """O relatório é feito para ser colado num chamado. Se ele imprimir
    telefone, nome ou a URL do banco, deixa de ser colável — e alguém vai
    colar mesmo assim."""
    from scripts.diagnostico_telefone import _relatorio

    await _planta(conexao, "client", "active", "+5581987654321")
    await _planta(conexao, "client", "active", None)

    await _relatorio(conexao)
    saida = capsys.readouterr().out

    assert "LEGADO_INVALIDO=1" in saida
    for vazamento in ("+5581987654321", "87654321", "5581987"):
        assert vazamento not in saida, f"telefone vazou: {vazamento}"
    # `password` fica na lista de propósito. O GitGuardian marcou ESTA linha
    # no PR #30 — é falso positivo (lista de substrings de uma asserção
    # negativa, sem valor secreto nenhum) e foi classificado como tal. Tirar a
    # palavra para agradar o detector enfraqueceria a verificação.
    for chave in ("postgresql", "asyncpg", "password", "@127.0.0.1", "DATABASE_URL="):
        assert chave not in saida, f"credencial/URL vazou: {chave}"


@pytest.mark.asyncio
async def test_a_linha_parseavel_sai_exatamente_uma_vez(conexao, capsys):
    from scripts.diagnostico_telefone import _relatorio

    await _relatorio(conexao)
    saida = capsys.readouterr().out
    assert saida.count("LEGADO_INVALIDO=") == 1
    assert "LEGADO_INVALIDO=0" in saida


def test_o_script_nao_tem_verbo_de_escrita():
    """Guard de fonte: o portão é somente leitura, e isso não pode depender de
    alguém lembrar. Um INSERT/UPDATE/DELETE/DDL ali seria mudança de natureza
    da ferramenta, não detalhe de implementação."""
    from pathlib import Path

    import scripts.diagnostico_telefone as modulo

    fonte = Path(modulo.__file__).read_text(encoding="utf-8")
    corpo = fonte.split('"""', 2)[2]
    for verbo in ("INSERT ", "UPDATE ", "DELETE ", "ALTER ", "DROP ", "CREATE "):
        assert verbo not in corpo.upper(), f"o script passou a escrever: {verbo}"
