"""Ensaio conjunto das migrations m9h0 → n0i1 → o1j2 em PostgreSQL ISOLADO.

uso (de backend/ do commit a ensaiar):

    python <este arquivo> --base l8g9h0i1j2k3 --escala 1 --saida <pasta>
        [--servidor postgresql://usuario:senha@127.0.0.1:PORTA/postgres]
        [--pg-bin <pasta com pg_dump e pg_restore da MESMA versão do servidor>]

Sem `--servidor`, sobe um Postgres efêmero do `pgserver` (PG 16.2, pgvector
0.6.2) numa pasta temporária — serve para validar ESTE roteiro, não para o
ensaio de equivalência: produção é PG 17.

Só dados SINTÉTICOS, gerados aqui. O roteiro se recusa a rodar contra host que
não seja a própria máquina, contra a 5432 (o Postgres instalado nesta máquina)
e contra a 8888 (a porta do banco de produção).

`--base` é a revision em que a PRODUÇÃO está. Ela tem de ser confirmada pelo
operador antes do ensaio de equivalência; este roteiro não a descobre. Só
serve uma das quatro da cadeia (`l8g9h0i1j2k3` ou uma das três seguintes): as
migrations aplicadas são as que vêm DEPOIS dela.

Termina com código 1 se houve falha ou exceção; o veredito também fica em
`resultado.json`.

O que mede, nesta ordem:
  1. esquema na revision base + dados sintéticos;
  2. retrato (contagem e soma de verificação por tabela) e backup (`pg_dump`);
  3. cada migration, uma por vez: duração, e o que ela deixou;
  4. integridade depois das três: constraints validadas, índices válidos,
     contagens iguais, valores padrão das colunas novas;
  5. scripts de dados em dry-run (diagnóstico, preenchimento, fusão) e a
     fusão aplicada;
  6. restauração do backup em OUTRO banco: duração, retrato igual, revision
     de volta à base;
  7. downgrade: o da o1j2 com dado gravado (tem de ser recusado), e a descida
     inteira num banco restaurado e migrado sem dado novo.
"""

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

import psycopg2
from sqlalchemy.engine import make_url

ANTES_DA_CADEIA = "l8g9h0i1j2k3"
CADEIA = ["m9h0i1j2k3l4", "n0i1j2k3l4m5", "o1j2k3l4m5n6"]
TABELAS = [
    "groups",
    "companies",
    "users",
    "products",
    "equipments",
    "tickets",
    "chat_messages",
    "company_notes",
]
PORTAS_PROIBIDAS = {5432, 8888}

resultado: dict = {"etapas": [], "falhas": []}


def etapa(nome: str, **dados) -> None:
    resultado["etapas"].append({"etapa": nome, **dados})
    print(f"[{nome}] " + ", ".join(f"{k}={v}" for k, v in dados.items()), flush=True)


def confere(condicao: bool, o_que: str) -> None:
    if not condicao:
        resultado["falhas"].append(o_que)
    print(("  ok    " if condicao else "  FALHA ") + o_que, flush=True)


# ── Servidor ─────────────────────────────────────────────────


def sobe_servidor(args):
    if args.servidor:
        url = make_url(args.servidor)
        if url.host not in ("127.0.0.1", "localhost", "::1"):
            raise SystemExit(f"recusado: {url.host} não é esta máquina")
        if (url.port or 5432) in PORTAS_PROIBIDAS:
            raise SystemExit(f"recusado: porta {url.port or 5432} é reservada")
        return url, None
    import pgserver

    pasta = tempfile.mkdtemp(prefix="helphs-ensaio-migr-")
    servidor = pgserver.get_server(pasta, cleanup_mode=None)
    url = make_url(servidor.get_uri(database="postgres"))
    if url.host and url.host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit(f"recusado: {url.host} não é esta máquina")
    if (url.port or 0) in PORTAS_PROIBIDAS:
        raise SystemExit(f"recusado: porta {url.port} é reservada")
    return url, (servidor, pasta)


def conecta(url, banco: str, autocommit: bool = True):
    c = psycopg2.connect(
        host=url.host or None,
        port=url.port,
        user=url.username,
        password=url.password,
        dbname=banco,
        **({} if url.host else {"host": url.query.get("host")}),
    )
    c.autocommit = autocommit
    return c


def sql(con, texto: str, params=None):
    with con.cursor() as cur:
        cur.execute(texto, params)
        return cur.fetchall() if cur.description else []


def uma_vez(url, banco: str, texto: str):
    """Abre, roda fora de transação e fecha — `DROP DATABASE` exige isso."""
    c = conecta(url, banco)
    try:
        return sql(c, texto)
    finally:
        c.close()


def cria_banco(url, nome: str) -> None:
    uma_vez(url, "postgres", f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)')
    uma_vez(url, "postgres", f'CREATE DATABASE "{nome}"')
    uma_vez(url, nome, "CREATE EXTENSION IF NOT EXISTS vector")


def url_do_app(url, banco: str) -> str:
    return url.set(drivername="postgresql+asyncpg", database=banco).render_as_string(
        hide_password=False
    )


def alembic(url, banco: str, *comando: str) -> tuple[int, float, str]:
    amb = {
        **os.environ,
        "APP_ENV": "testing",
        "DATABASE_URL": url_do_app(url, banco),
        "PYTHONIOENCODING": "utf-8",
    }
    amb.pop("ALEMBIC_ALVO_REMOTO_LIBERADO", None)
    inicio = time.perf_counter()
    r = subprocess.run(
        [sys.executable, "-m", "alembic", *comando],
        env=amb,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return r.returncode, time.perf_counter() - inicio, (r.stdout + r.stderr)[-1500:]


def revision(con) -> str:
    return sql(con, "SELECT version_num FROM alembic_version")[0][0]


# ── Dados sintéticos ─────────────────────────────────────────


def obrigatorias(con, tabela: str) -> dict[str, tuple[str, str]]:
    """Colunas NOT NULL sem valor padrão no banco: nome → (tipo, tipo udt)."""
    linhas = sql(
        con,
        """SELECT column_name, data_type, udt_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
              AND is_nullable = 'NO' AND column_default IS NULL""",
        (tabela,),
    )
    return {n: (t, u) for n, t, u in linhas}


def valor_padrao(con, tipo: str, udt: str, i: int):
    if tipo == "uuid":
        return str(uuid.uuid4())
    if tipo in ("character varying", "text", "character"):
        return f"sintetico-{i}"
    if tipo == "boolean":
        return False
    if tipo.startswith("timestamp") or tipo == "date":
        return "2026-01-01T00:00:00+00:00"
    if tipo in ("integer", "bigint", "smallint", "numeric", "double precision", "real"):
        return 0
    if tipo == "USER-DEFINED":
        return sql(
            con,
            "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = %s ORDER BY e.enumsortorder LIMIT 1",
            (udt,),
        )[0][0]
    if tipo in ("json", "jsonb"):
        return "{}"
    raise SystemExit(f"tipo sem valor sintético: {tipo}/{udt}")


def insere(con, tabela: str, linhas: list[dict]) -> None:
    """Insere preenchendo sozinho o que for obrigatório e não veio."""
    if not linhas:
        return
    faltam = {c: tu for c, tu in obrigatorias(con, tabela).items() if c not in linhas[0]}
    colunas = list(linhas[0]) + list(faltam)
    with con.cursor() as cur:
        for i, linha in enumerate(linhas):
            valores = list(linha.values()) + [
                valor_padrao(con, t, u, i) for t, u in faltam.values()
            ]
            cur.execute(
                f"INSERT INTO {tabela} ({', '.join(colunas)}) "
                f"VALUES ({', '.join(['%s'] * len(colunas))})",
                valores,
            )


def semeia(con, escala: int) -> dict:
    """Cenário representativo, só com dado inventado. `escala` multiplica o volume."""
    novo = lambda: str(uuid.uuid4())  # noqa: E731
    grupos = [{"id": novo(), "name": f"Grupo {i}"} for i in range(2 * escala)]
    insere(con, "groups", grupos)

    empresas = []
    for i in range(6 * escala):
        # Uma em cada três repete o CNPJ da anterior, com outra máscara.
        base = i - 1 if i % 3 == 2 else i
        doc = f"{10000000000100 + base:014d}"
        cnpj = doc if i % 3 != 2 else f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}"
        empresas.append(
            {
                "id": novo(),
                "group_id": (
                    grupos[i % len(grupos)]["id"] if i % 3 != 2 else empresas[-1]["group_id"]
                ),
                "name": f"Empresa {i}",
                "cnpj": cnpj,
            }
        )
    insere(con, "companies", empresas)

    usuarios = []
    for i in range(40 * escala):
        usuarios.append(
            {
                "id": novo(),
                "name": f"Pessoa {i}",
                "email": f"pessoa{i}-{uuid.uuid4().hex[:8]}@sintetico.invalid",
                "password": "x",
                # Dois em cada cinco sem empresa.
                "company_id": empresas[i % len(empresas)]["id"] if i % 5 < 3 else None,
            }
        )
    insere(con, "users", usuarios)

    produtos = [{"id": novo(), "name": f"Produto {i}"} for i in range(3)]
    insere(con, "products", produtos)

    equipamentos = []
    for i in range(30 * escala):
        equipamentos.append(
            {
                "id": novo(),
                "product_id": produtos[i % 3]["id"],
                "name": f"Aparelho {i}",
                "serial_number": f"SN-{i:07d}",
                # Um em cada quatro sem responsável; um em cada sete inativo.
                "owner_id": usuarios[i % len(usuarios)]["id"] if i % 4 else None,
                "is_active": i % 7 != 0,
            }
        )
    insere(con, "equipments", equipamentos)

    chamados = [
        {
            "id": novo(),
            "protocol": f"S{i:09d}",
            "title": f"Chamado {i}",
            "description": "sintético",
            "creator_id": usuarios[i % len(usuarios)]["id"],
        }
        for i in range(50 * escala)
    ]
    insere(con, "tickets", chamados)

    mensagens = [
        {
            "id": novo(),
            "ticket_id": chamados[i % len(chamados)]["id"],
            "sender_id": usuarios[i % len(usuarios)]["id"],
            "content": f"mensagem {i}",
        }
        for i in range(400 * escala)
    ]
    insere(con, "chat_messages", mensagens)

    notas = [
        {
            "id": novo(),
            "company_id": empresas[i % len(empresas)]["id"],
            "author_id": usuarios[0]["id"],
            "content": f"nota {i}",
        }
        for i in range(10 * escala)
    ]
    insere(con, "company_notes", notas)
    return {
        t: len(v)
        for t, v in zip(
            TABELAS,
            [grupos, empresas, usuarios, produtos, equipamentos, chamados, mensagens, notas],
            strict=True,
        )
    }


def retrato(con, colunas_de: dict[str, list[str]] | None = None) -> dict:
    """Contagem e soma de verificação por tabela, só sobre as colunas dadas.

    As colunas são as da revision BASE: é o que tem de continuar igual depois
    das migrations e depois da restauração.
    """
    saida = {}
    for t in TABELAS:
        if colunas_de is None:
            cols = [
                c
                for (c,) in sql(
                    con,
                    "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
                    (t,),
                )
            ]
        else:
            cols = colunas_de[t]
        expr = " || '|' || ".join(f"coalesce({c}::text, '∅')" for c in cols)
        h = hashlib.sha256()
        with con.cursor() as cur:
            cur.execute(f"SELECT {expr} FROM {t} ORDER BY id")
            n = 0
            for (linha,) in cur:
                h.update(linha.encode("utf-8"))
                n += 1
        saida[t] = {"linhas": n, "soma": h.hexdigest()[:16], "colunas": cols}
    return saida


def mesmos(a: dict, b: dict) -> bool:
    return all(a[t]["linhas"] == b[t]["linhas"] and a[t]["soma"] == b[t]["soma"] for t in TABELAS)


# ── Roteiro ──────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument(
        "--base", required=True, help="revision em que a produção está (confirmada pelo operador)"
    )
    p.add_argument("--escala", type=int, default=1)
    p.add_argument("--saida", required=True)
    p.add_argument("--servidor")
    p.add_argument("--pg-bin")
    args = p.parse_args()

    conhecidas = [ANTES_DA_CADEIA, *CADEIA]
    if args.base not in conhecidas[:-1]:
        raise SystemExit(f"recusado: --base precisa ser uma de {conhecidas[:-1]}")
    # Só o que vem depois da base: produção pode já ter parte da cadeia.
    a_aplicar = conhecidas[conhecidas.index(args.base) + 1 :]

    # `if`, não `assert`: com `python -O` o assert some, e a trava junto.
    if pathlib.Path(".env").exists():
        raise SystemExit("recusado: há .env nesta pasta")
    if not pathlib.Path("alembic.ini").exists():
        raise SystemExit("recusado: rode de backend/")
    saida = pathlib.Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)

    url, recurso = sobe_servidor(args)
    if args.pg_bin:
        binarios = pathlib.Path(args.pg_bin)
    else:
        import pgserver

        binarios = pathlib.Path(pgserver.__file__).parent / "pginstall" / "bin"
    try:
        versao = uma_vez(url, "postgres", "SHOW server_version")[0][0]
        dump_v = subprocess.run(
            [str(binarios / "pg_dump"), "--version"], capture_output=True, text=True
        ).stdout.strip()
        etapa(
            "servidor",
            postgres=versao,
            pg_dump=dump_v,
            porta=url.port,
            host=url.host or "socket local",
        )
        resultado["equivalente_a_producao"] = versao.split(".")[0] == "17"
        # No Linux a saída traz o pacote depois da versão: "pg_dump (PostgreSQL) 17.2 (Ubuntu ...)".
        maior_do_dump = re.search(r"\(PostgreSQL\) (\d+)", dump_v)
        confere(
            maior_do_dump is not None and versao.split(".")[0] == maior_do_dump.group(1),
            "pg_dump da mesma versão maior do servidor",
        )

        # 1. Base + dados
        cria_banco(url, "ensaio")
        vector = uma_vez(
            url, "ensaio", "SELECT extversion FROM pg_extension WHERE extname='vector'"
        )[0][0]
        cod, dur, log = alembic(url, "ensaio", "upgrade", args.base)
        etapa("esquema na base", revision=args.base, segundos=round(dur, 2), pgvector=vector)
        confere(cod == 0, f"alembic upgrade {args.base}" + ("" if cod == 0 else f": {log[-300:]}"))
        if cod:
            # Sair por aqui com `return` pularia o veredito do fim e daria 0.
            # O `finally` ainda grava o JSON.
            raise SystemExit(1)
        con = conecta(url, "ensaio")
        confere(revision(con) == args.base, "alembic_version na base")
        t0 = time.perf_counter()
        volumes = semeia(con, args.escala)
        etapa("dados sintéticos", segundos=round(time.perf_counter() - t0, 2), **volumes)

        # 2. Retrato e backup
        antes = retrato(con)
        colunas_base = {t: antes[t]["colunas"] for t in TABELAS}
        con.close()
        arquivo = saida / "antes.dump"
        senha = {"PGPASSWORD": url.password} if url.password else {}
        comum = ["-p", str(url.port)] if url.port else []
        comum += (
            ["-h", url.host or url.query.get("host", "")]
            if (url.host or url.query.get("host"))
            else []
        )
        comum += ["-U", url.username] if url.username else []
        t0 = time.perf_counter()
        r = subprocess.run(
            [str(binarios / "pg_dump"), *comum, "-Fc", "-f", str(arquivo), "ensaio"],
            env={**os.environ, **senha},
            capture_output=True,
            text=True,
        )
        etapa(
            "backup",
            segundos=round(time.perf_counter() - t0, 2),
            bytes=arquivo.stat().st_size if arquivo.exists() else 0,
        )
        confere(
            r.returncode == 0, "pg_dump" + ("" if r.returncode == 0 else f": {r.stderr[-300:]}")
        )

        # 3. Migrations, uma por vez
        for rev in a_aplicar:
            cod, dur, log = alembic(url, "ensaio", "upgrade", rev)
            etapa(f"upgrade {rev}", segundos=round(dur, 2))
            confere(cod == 0, f"aplicou {rev}" + ("" if cod == 0 else f": {log[-400:]}"))
            if cod:
                raise SystemExit(1)

        # 4. Integridade
        con = conecta(url, "ensaio")
        confere(revision(con) == CADEIA[-1], "alembic_version no head")
        confere(
            mesmos(antes, retrato(con, colunas_base)),
            "dados das colunas antigas idênticos depois das três",
        )
        invalidas = sql(con, "SELECT conname FROM pg_constraint WHERE NOT convalidated")
        confere(not invalidas, f"todas as constraints validadas ({len(invalidas)} pendente(s))")
        indices = sql(
            con,
            "SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid WHERE NOT i.indisvalid",
        )
        confere(not indices, f"todos os índices válidos ({len(indices)} inválido(s))")
        esperados = {"uq_chat_messages_envio", "uq_chat_messages_seq", "ix_equipments_company_id"}
        tem = {n for (n,) in sql(con, "SELECT indexname FROM pg_indexes WHERE schemaname='public'")}
        confere(esperados <= tem, "índices novos presentes")
        confere(
            sql(con, "SELECT count(*) FROM tickets WHERE chat_seq <> 0")[0][0] == 0,
            "tickets.chat_seq nasce 0",
        )
        confere(
            sql(
                con,
                "SELECT count(*) FROM chat_messages WHERE seq IS NOT NULL OR client_message_id IS NOT NULL",
            )[0][0]
            == 0,
            "mensagens antigas sem seq e sem chave de envio",
        )
        confere(
            sql(
                con,
                "SELECT count(*) FROM equipments WHERE company_id IS NOT NULL OR sem_empresa_por_decisao",
            )[0][0]
            == 0,
            "equipamentos nascem sem empresa e sem marca",
        )
        confere(
            sql(con, "SELECT count(*) FROM chat_seq_corte")[0][0] == 1,
            "chat_seq_corte com uma linha",
        )
        con.close()

        # 5. Scripts de dados (sintéticos)
        amb = {
            **os.environ,
            "APP_ENV": "testing",
            "DATABASE_URL": url_do_app(url, "ensaio"),
            "PYTHONIOENCODING": "utf-8",
        }
        for nome, extra in (
            ("diagnostico_empresa_aparelho", []),
            ("preenche_empresa_do_equipamento", []),
            ("funde_empresas_duplicadas", []),
            ("funde_empresas_duplicadas", ["--aplicar"]),
        ):
            t0 = time.perf_counter()
            r = subprocess.run(
                [sys.executable, "-m", f"scripts.{nome}", *extra],
                env=amb,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            (saida / f"{nome.split('_')[0]}{'_ap' if extra else ''}.log").write_text(
                r.stdout + r.stderr, encoding="utf-8"
            )
            etapa(
                f"script {nome} {' '.join(extra) or '(dry-run)'}",
                segundos=round(time.perf_counter() - t0, 2),
                saida=r.returncode,
            )
            confere(r.returncode == 0, f"{nome} {' '.join(extra)} terminou sem erro")
        con = conecta(url, "ensaio")
        dup = sql(
            con,
            r"SELECT count(*) FROM (SELECT 1 FROM companies WHERE coalesce(cnpj,'')<>'' GROUP BY regexp_replace(cnpj,'\D','','g'), group_id HAVING count(*)>1) x",
        )[0][0]
        confere(dup == 0, "sem CNPJ repetido no mesmo grupo depois da fusão")
        orfaos = sql(
            con,
            "SELECT (SELECT count(*) FROM users u WHERE company_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM companies c WHERE c.id=u.company_id)) + (SELECT count(*) FROM equipments e WHERE company_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM companies c WHERE c.id=e.company_id))",
        )[0][0]
        confere(orfaos == 0, "nenhum vínculo apontando para empresa que não existe")
        con.close()

        # 6. Restauração do backup em outro banco
        cria_banco(url, "restaurado")
        t0 = time.perf_counter()
        r = subprocess.run(
            [str(binarios / "pg_restore"), *comum, "--no-owner", "-d", "restaurado", str(arquivo)],
            env={**os.environ, **senha},
            capture_output=True,
            text=True,
        )
        etapa("restauração", segundos=round(time.perf_counter() - t0, 2), saida=r.returncode)
        # O que o pg_restore disse fica guardado para investigação. A senha
        # vai por variável de ambiente e não aparece aqui.
        (saida / "pg_restore.log").write_text(r.stderr or "", encoding="utf-8")
        # O veredito é o código de saída: erro ignorado na restauração também
        # dá diferente de zero. A leitura do stderr só soma, não substitui.
        erros = [linha for linha in r.stderr.splitlines() if "error" in linha.lower()]
        confere(
            r.returncode == 0 and not erros,
            f"pg_restore terminou com 0 e sem erro (saída {r.returncode}, {len(erros)} linha(s) de erro)"
            + ("" if r.returncode == 0 and not erros else f": {r.stderr[-300:]}"),
        )
        con = conecta(url, "restaurado")
        confere(revision(con) == args.base, "banco restaurado está na revision base")
        confere(
            mesmos(antes, retrato(con, colunas_base)),
            "banco restaurado idêntico ao retrato de antes",
        )
        con.close()

        # 7. Downgrade
        # O preenchimento rodou em dry-run; para a recusa do downgrade ser
        # exercitada, um aparelho sintético ganha empresa aqui.
        con = conecta(url, "ensaio")
        sql(
            con,
            "UPDATE equipments SET company_id = (SELECT id FROM companies ORDER BY id LIMIT 1) WHERE id = (SELECT id FROM equipments ORDER BY id LIMIT 1)",
        )
        con.close()
        cod, dur, log = alembic(url, "ensaio", "downgrade", CADEIA[1])
        con = conecta(url, "ensaio")
        gravados = sql(
            con,
            "SELECT count(*) FROM equipments WHERE company_id IS NOT NULL OR sem_empresa_por_decisao",
        )[0][0]
        if gravados:
            confere(
                cod != 0 and "ROLLBACK BLOQUEADO" in log,
                f"downgrade da o1j2 com {gravados} dado(s) gravado(s) é RECUSADO",
            )
            confere(revision(con) == CADEIA[-1], "banco continua no head depois da recusa")
        else:
            etapa(
                "aviso",
                texto="nenhum equipamento ganhou empresa nos scripts; a recusa do downgrade não foi exercitada",
            )
        con.close()
        # Até o fim da cadeia ensaiada, não até o `head`: o commit pode trazer
        # migration posterior, que não é objeto deste ensaio.
        cod, d1, log1 = alembic(url, "restaurado", "upgrade", CADEIA[-1])
        cod2, d2, log2 = alembic(url, "restaurado", "downgrade", args.base)
        etapa(
            "subida e descida inteiras em banco sem dado novo",
            sobe=round(d1, 2),
            desce=round(d2, 2),
        )
        confere(
            cod == 0 and cod2 == 0,
            "sobe até o fim da cadeia e desce até a base sem dado novo"
            + ("" if cod == 0 else f": {log1[-300:]}")
            + ("" if cod2 == 0 else f": {log2[-300:]}"),
        )
        con = conecta(url, "restaurado")
        confere(revision(con) == args.base, "depois da descida, revision base")
        confere(
            mesmos(antes, retrato(con, colunas_base)),
            "depois da descida, dados idênticos ao retrato",
        )
        con.close()
    except Exception as erro:  # noqa: BLE001 — exceção é falha do ensaio, não some
        resultado["falhas"].append(f"exceção: {type(erro).__name__}: {str(erro)[:300]}")
        raise
    finally:
        resultado["aprovado_como_roteiro"] = not resultado["falhas"]
        (saida / "resultado.json").write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            f"\nFALHAS: {len(resultado['falhas'])} | equivalente a produção (PG 17): {resultado.get('equivalente_a_producao')}",
            flush=True,
        )
        if recurso is not None:
            servidor, pasta = recurso
            try:
                servidor.cleanup()
            except Exception:  # noqa: BLE001
                pass
            shutil.rmtree(pasta, ignore_errors=True)
    if resultado["falhas"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
