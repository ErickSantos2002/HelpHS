"""
A cadeia da telefonia depois da colisão de revision ID, contra PostgreSQL real.

O QUE ACONTECEU, E POR QUE ESTE ARQUIVO EXISTE
-----------------------------------------------
A migration do ramal nasceu com o id `j6e7f8a9b0c1`, escolhido seguindo o
padrão visual da cadeia ("cada caractere +1"). Outra frente fez a mesma conta
para o histórico de aceites da LGPD, e a dela foi a produção primeiro.

Duas migrations diferentes com o mesmo id **não dão conflito de merge**: os
arquivos têm nomes distintos e nunca se tocam. `git merge` passa limpo, o CI
passa limpo, e o defeito só aparece no banco — `alembic_version` dizia
`j6e7f8a9b0c1`, a LGPD estava aplicada, e a coluna do ramal não existia. Um
`upgrade head` naquele estado pularia a migration do ramal para sempre.

É a mesma família do que a Fase 2B viu com as migrations irmãs: **o Alembic não
é verificável por diff de texto, e sim contando o grafo.**

O que estes testes prendem, partindo do estado REAL de produção:

* saindo de `j6e7f8a9b0c1` (LGPD aplicada), o upgrade roda SÓ as duas da
  telefonia e não tenta recriar `lgpd_consents`;
* a tabela da LGPD sobrevive intacta, com os dados que tinha;
* o downgrade volta até a LGPD — e PARA nela.
"""

import uuid

import pytest
from sqlalchemy import text

from tests.test_constraint_telefone_postgres import (  # noqa: F401
    _alembic,
    _conecta,
    banco,
    servidor,
)

# O ponto em que produção está de verdade, medido em 24/09/2026.
_PRODUCAO = "j6e7f8a9b0c1"
_RAMAL = "d68500999f24"
_DISPATCHING = "8d08cbca1768"


async def _versao(conn) -> str:
    return (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()


@pytest.mark.asyncio
async def test_upgrade_a_partir_do_estado_real_de_producao(banco):  # noqa: F811
    """O teste que a colisão exige: sair de onde produção está e chegar inteiro."""
    # 1. Coloca o banco exatamente onde produção está.
    r = _alembic(banco, "upgrade", _PRODUCAO)
    assert r.returncode == 0, r.stderr[-2000:]

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        assert await _versao(conn) == _PRODUCAO
        # A LGPD está aplicada, e é dela que este id é.
        assert (
            await conn.execute(text("SELECT to_regclass('public.lgpd_consents')"))
        ).scalar_one() == "lgpd_consents"
        # E o ramal ainda não existe.
        assert (
            await conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.columns"
                    " WHERE table_name='users' AND column_name='api4com_extension'"
                )
            )
        ).scalar_one() == 0
        # Uma linha na tabela da LGPD, para provar depois que nada a recriou.
        marca = str(uuid.uuid4())
        await conn.execute(
            text(
                "INSERT INTO users (id, name, email, password, role, status, phone,"
                " lgpd_consent, created_at, updated_at)"
                " VALUES (gen_random_uuid(), 'Quem Aceitou', :e, 'hash', 'client',"
                " 'active', '+5581999999999', true, now(), now())"
            ),
            {"e": f"{marca}@x.com"},
        )
    await engine.dispose()

    # 2. O upgrade que produção receberia.
    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr[-2000:]

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        assert await _versao(conn) == _DISPATCHING

        # A LGPD continua de pé, e NÃO foi recriada — a linha de antes está lá.
        assert (
            await conn.execute(text("SELECT to_regclass('public.lgpd_consents')"))
        ).scalar_one() == "lgpd_consents"
        assert (
            await conn.execute(
                text("SELECT count(*) FROM users WHERE email = :e"), {"e": f"{marca}@x.com"}
            )
        ).scalar_one() == 1, "o usuário sumiu: alguma coisa recriou a tabela"

        # E as duas da telefonia entraram.
        assert (
            await conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.columns"
                    " WHERE table_name='users' AND column_name='api4com_extension'"
                )
            )
        ).scalar_one() == 1
        assert (
            await conn.execute(
                text("SELECT count(*) FROM pg_indexes WHERE indexname='uq_users_api4com_extension'")
            )
        ).scalar_one() == 1
        check = (
            await conn.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                    " WHERE conname='ck_ticket_calls_status_conhecido'"
                )
            )
        ).scalar_one()
        assert "dispatching" in check
    await engine.dispose()


@pytest.mark.asyncio
async def test_downgrade_volta_ate_a_lgpd_e_para_nela(banco):  # noqa: F811
    """Desfaz a telefonia sem encostar no que já está em produção."""
    assert _alembic(banco, "upgrade", "head").returncode == 0

    r = _alembic(banco, "downgrade", _PRODUCAO)
    assert r.returncode == 0, r.stderr[-2000:]

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        assert await _versao(conn) == _PRODUCAO
        # A telefonia saiu...
        assert (
            await conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.columns"
                    " WHERE table_name='users' AND column_name='api4com_extension'"
                )
            )
        ).scalar_one() == 0
        # ...e a LGPD, que é de outra frente e está em produção, ficou.
        assert (
            await conn.execute(text("SELECT to_regclass('public.lgpd_consents')"))
        ).scalar_one() == "lgpd_consents"
    await engine.dispose()


def test_nenhum_revision_id_se_repete():
    """Guard de fonte: dois arquivos com o mesmo id não dão conflito de merge.

    Por isso a checagem é por CONTAGEM, não por diff — foi exatamente assim que
    a colisão passou por todos os gates e só apareceu no banco.
    """
    import re
    from collections import defaultdict
    from pathlib import Path

    versoes = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    por_id = defaultdict(list)
    for arquivo in sorted(versoes.glob("*.py")):
        fonte = arquivo.read_text(encoding="utf-8")
        achado = re.search(r"^revision(?::\s*str)?\s*=\s*[\"']([^\"']+)", fonte, re.M)
        if achado:
            por_id[achado.group(1)].append(arquivo.name)

    repetidos = {k: v for k, v in por_id.items() if len(v) > 1}
    assert not repetidos, f"revision id repetido: {repetidos}"


def test_a_cadeia_e_linear_e_tem_um_head_so():
    import re
    from pathlib import Path

    versoes = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    pai = {}
    for arquivo in versoes.glob("*.py"):
        fonte = arquivo.read_text(encoding="utf-8")
        rev = re.search(r"^revision(?::\s*str)?\s*=\s*[\"']([^\"']+)", fonte, re.M)
        down = re.search(r"^down_revision(?::[^=]*)?\s*=\s*(.+)$", fonte, re.M)
        if not rev:
            continue
        bruto = down.group(1).strip() if down else "None"
        casado = re.match(r"[\"']([^\"']+)", bruto)
        pai[rev.group(1)] = casado.group(1) if casado else None

    filhos = {p for p in pai.values() if p}
    heads = [r for r in pai if r not in filhos]
    assert heads == [_DISPATCHING], f"heads: {heads}"

    # E a ordem que importa: LGPD antes do ramal, ramal antes do dispatching.
    assert pai[_DISPATCHING] == _RAMAL
    assert pai[_RAMAL] == _PRODUCAO

    atual, cadeia = heads[0], []
    while atual:
        cadeia.append(atual)
        atual = pai[atual]
    assert len(cadeia) == len(pai), "a cadeia não alcança todas as revisões"
