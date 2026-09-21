"""
A constraint `ck_users_cliente_ativo_tem_telefone`, contra PostgreSQL real.

Por que este arquivo existe
---------------------------
A Fase 1C põe no banco a invariante que a Fase 1A pôs na aplicação. As duas
não se substituem: a aplicação devolve mensagem de domínio e UX, o banco
recusa o estado impossível mesmo para o caminho de escrita que ainda não foi
escrito. Defesa em profundidade só vale se as duas forem exercitadas, e a do
banco só se exercita contra um banco.

Aqui a migration roda **de verdade**, como subprocesso, num banco recriado do
zero — mesmo mecanismo de `test_migrations_postgres.py`, de onde a função de
subida é importada em vez de copiada.

O que NÃO se testa aqui
-----------------------
Formato. A constraint é de PRESENÇA: `NULL`, vazio e whitespace são ausência,
e qualquer outra coisa passa. Um telefone com máscara ou até com lixo satisfaz
o banco — corrigi-lo é assunto do tipo anotado nas portas de escrita, e
confundir os dois faria a constraint recusar linha que a aplicação aceita.

⚠️ Tabelas TEMPORÁRIAS não servem aqui, ao contrário de
`test_diagnostico_telefone.py`: o que se testa é a constraint aplicada à
`public.users` real pela migration. Por isso cada teste recria o banco
inteiro, e nenhum deles toca num banco compartilhado.
"""

import asyncio
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests.test_dashboard_postgres import _sobe_postgres

_BACKEND = Path(__file__).resolve().parent.parent
_BANCO = "constraint_telefone_testes"

_ANTES = "f2a3b4c5d6e7"
_DEPOIS = "g3b4c5d6e7f8"
_NOME = "ck_users_cliente_ativo_tem_telefone"


def _alembic(url: str, comando: str, alvo: str) -> subprocess.CompletedProcess:
    """Roda o alembic como SUBPROCESSO, igual ao `start.sh`.

    O `alembic/env.py` chama `asyncio.run()` por dentro, e invocá-lo de dentro
    de um teste async estouraria com "cannot be called from a running event
    loop". O subprocesso também relê `get_settings()` do zero.
    """
    ambiente = {**os.environ, "DATABASE_URL": url, "APP_ENV": "testing"}
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", comando, alvo],
        cwd=_BACKEND,
        env=ambiente,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


@pytest.fixture(scope="module")
def servidor():
    """Sobe o Postgres uma vez para o módulo — o custo grande do pgserver."""
    url, recurso = _sobe_postgres()
    if url is None:
        pytest.skip("sem PostgreSQL: defina TEST_POSTGRES_URL ou instale pgserver")

    yield url

    if recurso is not None:
        servidor_pg, pasta = recurso
        try:
            servidor_pg.cleanup()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(pasta, ignore_errors=True)


@pytest_asyncio.fixture
async def banco(servidor):
    """Banco recém-criado por teste: `upgrade` precisa partir do zero."""
    admin = create_async_engine(servidor, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{_BANCO}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{_BANCO}"'))
    await admin.dispose()

    url = servidor.rsplit("/", 1)[0] + f"/{_BANCO}"
    novo = create_async_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with novo.connect() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    await novo.dispose()

    yield url


async def _conecta(url):
    return create_async_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)


async def _insere(conn, role, status, phone, email=None):
    """Um usuário mínimo. Só as colunas NOT NULL sem default, mais as três
    que a constraint enxerga."""
    await conn.execute(
        text(
            "INSERT INTO users (id, name, email, password, role, status, phone,"
            " lgpd_consent, created_at, updated_at)"
            " VALUES (gen_random_uuid(), 'Teste', :e, 'hash', :r, :s, :p,"
            " false, now(), now())"
        ),
        {"e": email or f"{uuid.uuid4()}@x.com", "r": role, "s": status, "p": phone},
    )


async def _tenta(conn, sql, parametros=None):
    try:
        await conn.execute(text(sql), parametros or {})
        return "ACEITO"
    except Exception:  # noqa: BLE001 - o erro E o resultado
        return "REJEITADO"


async def _tenta_inserir(conn, role, status, phone):
    try:
        await _insere(conn, role, status, phone)
        return "ACEITO"
    except Exception:  # noqa: BLE001
        return "REJEITADO"


# ══════════════════════════════════════════════════════════════
# 1. A migration sobe, e a constraint existe
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_upgrade_sobe_do_zero_e_cria_a_constraint(banco):
    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr[-2000:]

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        existe = (
            await conn.execute(
                text("SELECT count(*) FROM pg_constraint" " WHERE conname = :n AND contype = 'c'"),
                {"n": _NOME},
            )
        ).scalar_one()
        assert existe == 1, "a constraint não foi criada"

        # E ela nasce VALIDADA: `NOT VALID` deixaria `convalidated` falso, e
        # foi justamente o que rejeitamos.
        validada = (
            await conn.execute(
                text("SELECT convalidated FROM pg_constraint WHERE conname = :n"),
                {"n": _NOME},
            )
        ).scalar_one()
        assert validada is True, "a constraint nasceu NOT VALID"
    await engine.dispose()


# ══════════════════════════════════════════════════════════════
# 2. O que a constraint recusa e o que ela aceita
# ══════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def migrado(banco):
    """Banco no head, pronto para exercitar a constraint."""
    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr[-2000:]
    engine = await _conecta(banco)
    async with engine.connect() as conn:
        yield conn
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("phone", "descricao"),
    [
        (None, "NULL"),
        ("", "string vazia"),
        ("   ", "só espaços"),
        ("\t", "tabulação"),
        ("\n", "quebra de linha"),
        (" \t \n ", "mistura de whitespace"),
    ],
)
async def test_cliente_ativo_sem_telefone_e_recusado(migrado, phone, descricao):
    assert await _tenta_inserir(migrado, "client", "active", phone) == "REJEITADO", descricao


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phone",
    ["+5581999999999", "8133334444", "(81) 99999-9999", "qualquer coisa"],
)
async def test_cliente_ativo_com_telefone_e_aceito(migrado, phone):
    """Inclui um valor fora de formato de propósito: a constraint é de
    PRESENÇA. Recusar `'qualquer coisa'` aqui significaria o banco opinando
    sobre formato, e divergindo da aplicação no primeiro dado legado."""
    assert await _tenta_inserir(migrado, "client", "active", phone) == "ACEITO"


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
async def test_fora_do_recorte_sem_telefone_e_aceito(migrado, role, status, porque):
    assert await _tenta_inserir(migrado, role, status, None) == "ACEITO", porque


# ══════════════════════════════════════════════════════════════
# 3. As transições — o que a Fase 1A chama de P1 e P2
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_reativar_cliente_sem_telefone_e_recusado(migrado):
    """P2 pela porta do banco: a volta para `active` é o instante em que a
    conta passa a valer para a telefonia."""
    await _insere(migrado, "client", "inactive", None, email="inativo@x.com")
    assert (
        await _tenta(migrado, "UPDATE users SET status='active' WHERE email='inativo@x.com'")
        == "REJEITADO"
    )


@pytest.mark.asyncio
async def test_virar_cliente_sem_telefone_e_recusado(migrado):
    await _insere(migrado, "technician", "active", None, email="tecnico@x.com")
    assert (
        await _tenta(migrado, "UPDATE users SET role='client' WHERE email='tecnico@x.com'")
        == "REJEITADO"
    )


@pytest.mark.asyncio
async def test_remover_telefone_de_cliente_ativo_e_recusado(migrado):
    """P1 pela porta do banco."""
    await _insere(migrado, "client", "active", "+5581999999999", email="ativo@x.com")
    assert (
        await _tenta(migrado, "UPDATE users SET phone=NULL WHERE email='ativo@x.com'")
        == "REJEITADO"
    )
    assert (
        await _tenta(migrado, "UPDATE users SET phone='   ' WHERE email='ativo@x.com'")
        == "REJEITADO"
    ), "whitespace tem de contar como remoção"


@pytest.mark.asyncio
async def test_desativar_cliente_sem_telefone_e_aceito(migrado):
    """Sair de ativo nunca é bloqueado — a constraint guarda o estado ATIVO.
    É este caminho que permitiu inativar as contas de exemplo em produção."""
    await _insere(migrado, "client", "active", "+5581999999999", email="saindo@x.com")
    assert (
        await _tenta(
            migrado,
            "UPDATE users SET status='inactive', phone=NULL WHERE email='saindo@x.com'",
        )
        == "ACEITO"
    )


# ══════════════════════════════════════════════════════════════
# 4. A anonimização não pode quebrar
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_anonimizacao_num_mesmo_update_e_aceita(migrado):
    """O caminho REAL do `anonymize_user`: `phone = None` e
    `status = anonymized` na mesma unidade de trabalho.

    Medido antes de existir constraint, e é por isso que este teste está
    aqui: o direito ao esquecimento é mais forte que a regra de telefone, e
    uma constraint que o bloqueasse seria pior que não ter constraint.
    """
    await _insere(migrado, "client", "active", "+5581999999999", email="anon@x.com")
    assert (
        await _tenta(
            migrado,
            "UPDATE users SET phone=NULL, status='anonymized' WHERE email='anon@x.com'",
        )
        == "ACEITO"
    )


@pytest.mark.asyncio
async def test_anonimizar_em_dois_passos_recusa_o_primeiro(migrado):
    """A armadilha que a constraint cria para QUEM ESCREVER SCRIPT NOVO.

    Limpar o telefone antes de mudar a situação é recusado — e o resultado,
    se alguém ignorar o erro, é pior que uma falha visível: a conta termina
    `anonymized` com o telefone intacto. A aplicação de hoje grava os dois
    campos juntos; este teste existe para que o próximo script avulso saiba.
    """
    await _insere(migrado, "client", "active", "+5581999999999", email="dois@x.com")
    assert (
        await _tenta(migrado, "UPDATE users SET phone=NULL WHERE email='dois@x.com'") == "REJEITADO"
    )
    ainda_tem = (
        await migrado.execute(text("SELECT phone FROM users WHERE email='dois@x.com'"))
    ).scalar_one()
    assert ainda_tem == "+5581999999999", "o primeiro passo não podia ter gravado"


# ══════════════════════════════════════════════════════════════
# 5. O legado bloqueia a migration — e ela não sana nada
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_upgrade_falha_se_houver_cliente_ativo_invalido(banco):
    """A prova de que a migration não esconde o problema nem o conserta.

    Sobe até a revision ANTERIOR, planta uma linha legada, e só então tenta a
    nova. O `upgrade` tem de falhar — e a linha tem de continuar exatamente
    como estava, sem telefone inventado e sem mudança de situação.
    """
    r = _alembic(banco, "upgrade", _ANTES)
    assert r.returncode == 0, r.stderr[-2000:]

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        await _insere(conn, "client", "active", None, email="legado@x.com")
    await engine.dispose()

    r = _alembic(banco, "upgrade", _DEPOIS)
    assert r.returncode != 0, "o upgrade passou com cliente ativo sem telefone"
    assert "check constraint" in (r.stderr or "").lower(), r.stderr[-1500:]

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        linha = (
            await conn.execute(
                text("SELECT phone, status::text FROM users WHERE email='legado@x.com'")
            )
        ).one()
        assert linha.phone is None, "a migration INVENTOU telefone"
        assert linha.status == "active", "a migration MUDOU a situação da conta"

        constraint = (
            await conn.execute(
                text("SELECT count(*) FROM pg_constraint WHERE conname = :n"), {"n": _NOME}
            )
        ).scalar_one()
        assert constraint == 0, "a constraint foi criada apesar do legado"
    await engine.dispose()


# ══════════════════════════════════════════════════════════════
# 6. O caminho de volta
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_downgrade_remove_a_constraint_e_a_protecao_some(banco):
    """Descer tem de devolver o banco ao estado anterior — e a prova de que
    devolveu é o estado inválido voltar a ser aceito. Sem isso, o teste
    provaria apenas que o comando não deu erro."""
    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr[-2000:]

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        assert await _tenta_inserir(conn, "client", "active", None) == "REJEITADO"
    await engine.dispose()

    r = _alembic(banco, "downgrade", _ANTES)
    assert r.returncode == 0, r.stderr[-2000:]

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        restou = (
            await conn.execute(
                text("SELECT count(*) FROM pg_constraint WHERE conname = :n"), {"n": _NOME}
            )
        ).scalar_one()
        assert restou == 0, "a constraint sobreviveu ao downgrade"
        assert (
            await _tenta_inserir(conn, "client", "active", None) == "ACEITO"
        ), "a proteção de banco deveria ter sumido com o downgrade"
    await engine.dispose()


@pytest.mark.asyncio
async def test_upgrade_downgrade_upgrade(banco):
    """O ciclo que o deploy pode precisar fazer numa emergência."""
    for comando, alvo in (
        ("upgrade", "head"),
        ("downgrade", _ANTES),
        ("upgrade", "head"),
    ):
        r = _alembic(banco, comando, alvo)
        assert r.returncode == 0, f"{comando} {alvo}: {r.stderr[-1500:]}"

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        assert await _tenta_inserir(conn, "client", "active", None) == "REJEITADO"
    await engine.dispose()


# ══════════════════════════════════════════════════════════════
# 7. O modelo e a migration não podem divergir
# ══════════════════════════════════════════════════════════════


_ARQUIVO_DA_MIGRATION = (
    _BACKEND / "alembic" / "versions" / "g3b4c5d6e7f8_cliente_ativo_tem_telefone.py"
)


def _carrega_a_migration():
    """Carrega a migration pelo CAMINHO.

    `import alembic.versions...` não funciona: o nome `alembic` resolve para o
    pacote instalado, não para a pasta do projeto — e as migrations nunca são
    importadas como módulo, só executadas pelo runner.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("migration_1c", _ARQUIVO_DA_MIGRATION)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_o_model_declara_a_mesma_constraint():
    """O projeto declara CHECK no `__table_args__` (precedente: o do MFA).
    Se a migration criasse a constraint e o model não a conhecesse, um
    `autogenerate` futuro proporia removê-la — e o teste de deriva
    modelo-x-migration não pega isso, porque ele compara presença de tabela e
    coluna, não de constraint."""
    from app.models.models import User

    checks = {
        c.name: str(c.sqltext)
        for c in User.__table__.constraints
        if type(c).__name__ == "CheckConstraint"
    }
    assert _NOME in checks, "o model não declara a constraint"

    do_model = " ".join(checks[_NOME].split())
    da_migration = " ".join(_carrega_a_migration()._REGRA.split())
    assert (
        do_model == da_migration
    ), f"o predicado divergiu.\n  model:     {do_model}\n  migration: {da_migration}"


def test_a_migration_nao_escreve_em_linha_nenhuma():
    """Guard de fonte: a migration é só DDL. Um `UPDATE`/`DELETE` ali seria
    saneamento escondido dentro de um deploy — e a regra da casa é que dado
    histórico se corrige em script avulso."""
    import ast

    caminho = _BACKEND / "alembic" / "versions" / "g3b4c5d6e7f8_cliente_ativo_tem_telefone.py"
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    chamadas = {
        no.func.attr
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
    }
    assert chamadas <= {
        "create_check_constraint",
        "drop_constraint",
    }, f"a migration faz mais que DDL de constraint: {chamadas}"

    corpo = caminho.read_text(encoding="utf-8").split('"""', 2)[2].upper()
    for proibido in ("EXECUTE", "UPDATE ", "DELETE ", "INSERT ", "NOT VALID"):
        assert proibido not in corpo, f"a migration passou a usar {proibido.strip()}"


def _sem_evento_de_loop():
    """`asyncio` importado mas não usado deixaria o ruff vermelho."""
    return asyncio
