"""
Funde empresas que compartilham o mesmo CNPJ, deixando uma por documento.

**Avulso, rodado à mão, NUNCA em migration** — regra do projeto: dado
histórico se corrige em script, regra nova é prospectiva.

Existe porque o `UNIQUE (companies.cnpj)` não pode ser criado enquanto houver
duplicata: índice único falha na criação, e migration que falha aqui é API que
não sobe. O `diagnostico_empresa_aparelho.py` conta as duplicatas; este resolve.

Funde em vez de apagar, e a diferença não é acadêmica: `company_notes` tem
`ON DELETE CASCADE`. Apagar a empresa duplicada **apaga as notas dela junto**,
em silêncio. E `users.company_id` é `ON DELETE SET NULL`: os clientes seriam
soltos sem ninguém avisar. Movendo antes de apagar, nada se perde mesmo que a
duplicata "vazia" não estivesse tão vazia quanto o relatório sugeria.

Desde a ECE-01 a empresa também tem EQUIPAMENTOS (`equipments.company_id`), e
essa FK é `ON DELETE RESTRICT`: apagar a duplicata sem mover os aparelhos não
os solta — derruba o script no `DELETE`. Eles vão para a sobrevivente junto com
clientes e notas. ⚠️ Por isso este script só roda em banco que já passou pela
revision `o1j2k3l4m5n6`: antes dela a coluna não existe.

Quem sobrevive: a empresa com mais conteúdo (clientes + notas + equipamentos);
empatando, a mais antiga. O critério é o que preserva mais história sem precisar de
julgamento humano linha a linha.

Uso::

    cd backend
    export DATABASE_URL='postgresql+asyncpg://usuario:senha@host:porta/banco'

    python -m scripts.funde_empresas_duplicadas              # dry-run
    python -m scripts.funde_empresas_duplicadas --aplicar    # grava

Sem `--aplicar` nada é escrito. O plano sai igual nos dois modos, então dá
para conferir antes e comparar depois.

Pode rodar com o sistema no ar. Antes de gravar, o `--aplicar` trava as
empresas do plano e o que está pendurado nelas, na MESMA ordem das rotas
(empresa → cliente → aparelho), e confere de novo o que travou contra o plano
que acabou de mostrar. Se alguém vinculou um cliente, classificou um aparelho,
mudou o CNPJ ou apagou uma empresa nesse intervalo, o script NÃO grava nada,
diz o que mudou e sai com código 1 — é só rodar de novo para ver o plano novo.
Tudo acontece numa transação só: ou todas as fusões entram, ou nenhuma.

Duplicatas em GRUPOS diferentes são relatadas com destaque e **não são
fundidas**: juntar empresas de grupos distintos muda a que grupo os clientes
pertencem, e isso é decisão de quem conhece a operação, não de um script.
"""

import argparse
import asyncio
import os
import sys
from collections.abc import Iterable, Sequence
from typing import Any, NamedTuple

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# O console do Windows abre em cp1252 e estoura em qualquer acento — e este
# script roda na máquina de quem administra, não no container.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class Empresa(NamedTuple):
    id: Any
    doc: str
    nome: str
    group_id: Any
    criada_em: Any
    clientes: int
    notas: int
    equipamentos: int = 0

    @property
    def conteudo(self) -> int:
        return self.clientes + self.notas + self.equipamentos


class Fusao(NamedTuple):
    doc: str
    sobrevivente: Empresa
    absorvidas: list[Empresa]


_LEVANTAMENTO = r"""
    WITH duplicadas AS (
        SELECT regexp_replace(coalesce(cnpj, ''), '\D', '', 'g') AS doc
          FROM companies
         WHERE coalesce(cnpj, '') <> ''
         GROUP BY 1
        HAVING count(*) > 1
    )
    SELECT c.id,
           regexp_replace(coalesce(c.cnpj, ''), '\D', '', 'g')              AS doc,
           c.name                                                          AS nome,
           c.group_id,
           c.created_at                                                    AS criada_em,
           (SELECT count(*) FROM users u WHERE u.company_id = c.id)         AS clientes,
           (SELECT count(*) FROM company_notes n WHERE n.company_id = c.id) AS notas,
           (SELECT count(*) FROM equipments e WHERE e.company_id = c.id)    AS equipamentos
      FROM companies c
      JOIN duplicadas d
        ON d.doc = regexp_replace(coalesce(c.cnpj, ''), '\D', '', 'g')
     ORDER BY doc, c.created_at
"""


def planeja_fusao(empresas: Iterable[Empresa]) -> tuple[list[Fusao], list[list[Empresa]]]:
    """
    Decide quem sobrevive em cada CNPJ, sem tocar no banco.

    Separada da parte que grava porque é aqui que mora o risco: é esta função
    que poderia, com um descuido, eleger a empresa errada e mandar as notas de
    um cliente real para o lugar errado. Sendo pura, dá para prendê-la com
    teste.

    Returns:
        ``(fusoes, recusadas)`` — ``recusadas`` são os grupos que abrangem mais
        de um `group_id` e por isso ficam de fora.
    """
    por_doc: dict[str, list[Empresa]] = {}
    for e in empresas:
        por_doc.setdefault(e.doc, []).append(e)

    fusoes: list[Fusao] = []
    recusadas: list[list[Empresa]] = []

    for doc, linhas in por_doc.items():
        if len(linhas) < 2:
            continue
        if len({e.group_id for e in linhas}) > 1:
            recusadas.append(linhas)
            continue
        # Mais conteúdo primeiro; empatando, a mais antiga.
        ordenadas = sorted(linhas, key=lambda e: (-e.conteudo, e.criada_em))
        fusoes.append(Fusao(doc=doc, sobrevivente=ordenadas[0], absorvidas=ordenadas[1:]))

    return fusoes, recusadas


def _relata(fusoes: Sequence[Fusao], recusadas: Sequence[Sequence[Empresa]]) -> None:
    for f in fusoes:
        print(f"\n── CNPJ {f.doc} " + "─" * max(4, 44 - len(f.doc)))
        s = f.sobrevivente
        print(
            f"  FICA     {s.id}  {s.nome!r}  {s.clientes} cliente(s), {s.notas} nota(s), "
            f"{s.equipamentos} equipamento(s)"
        )
        for a in f.absorvidas:
            destino = ""
            if a.conteudo:
                destino = (
                    f"  -> move {a.clientes} cliente(s), {a.notas} nota(s) e "
                    f"{a.equipamentos} equipamento(s)"
                )
            print(f"  APAGA    {a.id}  {a.nome!r}{destino}")

    for grupo in recusadas:
        print(f"\n⚠️  CNPJ {grupo[0].doc}: empresas em GRUPOS diferentes — não fundidas")
        for e in grupo:
            marca = "casca vazia" if not e.conteudo else "TEM CONTEUDO"
            print(f"     {e.id}  {e.nome!r}")
            print(
                f"        grupo {e.group_id}  |  "
                f"{e.clientes} cliente(s), {e.notas} nota(s), "
                f"{e.equipamentos} equipamento(s)  -> {marca}"
            )
        print("     Juntar mudaria o grupo dos clientes. Decida à mão.")


class PlanoDesatualizadoError(Exception):
    """O banco mudou entre o levantamento e a gravação. Nada foi gravado."""

    def __init__(self, diferencas: Sequence[str]) -> None:
        super().__init__("; ".join(diferencas))
        self.diferencas = list(diferencas)


# Quanto o script espera por uma trava antes de desistir. Ele segura as
# empresas do plano em `FOR UPDATE` enquanto espera o resto, e com isso segura
# as rotas que tocam nelas: esperar para sempre por uma transação esquecida
# aberta pararia o cadastro junto. Estourou, nada é gravado.
_ESPERA_POR_TRAVA = "15s"

# As travas, na ordem das rotas (`groups.py` e `products.py`): EMPRESA →
# cliente → aparelho, cada tabela em ordem de id.
#
#   - Empresa em `FOR UPDATE`, o modo da exclusão (F1-D1): conflita com o
#     `FOR KEY SHARE` que vínculo, desvínculo, nota e classificação de aparelho
#     pegam nela. Ou a rota comitou antes, e o que ela gravou aparece na
#     reconferência; ou espera a fusão e encontra a empresa já fundida.
#   - Cliente em `FOR NO KEY UPDATE` — o que o `UPDATE` de `company_id` pegaria
#     de todo jeito, só que em ordem de id — e NÃO em `FOR UPDATE`. A troca de
#     responsável (`PATCH /equipments/{id}`) trava a conta em `FOR KEY SHARE`
#     ANTES da empresa; `FOR UPDATE` aqui esperaria por ela enquanto ela espera
#     pela empresa: círculo. `FOR NO KEY UPDATE` convive com `FOR KEY SHARE`, e
#     quem fecha essa corrida é a trava da empresa — a troca que leu o vínculo
#     antigo para na empresa absorvida e, depois da fusão, não a encontra.
#   - Nota e aparelho em `FOR UPDATE`, o modo das rotas de aparelho.
_TRAVA_EMPRESAS = r"""
    SELECT id, regexp_replace(coalesce(cnpj, ''), '\D', '', 'g') AS doc, group_id
      FROM companies
     WHERE id = ANY(:ids)
     ORDER BY id
       FOR UPDATE
"""
_TRAVA_DEPENDENTES = (
    ("clientes", "users", "NO KEY UPDATE"),
    ("notas", "company_notes", "UPDATE"),
    ("equipamentos", "equipments", "UPDATE"),
)


async def _trava_e_confere(conn, fusoes: Sequence[Fusao]) -> None:
    """Trava tudo o que o plano toca e recusa o plano que envelheceu.

    O levantamento é uma leitura solta, feita antes de qualquer trava: entre
    ele e a gravação o sistema continua em uso. Gravar por cima sem olhar
    moveria em silêncio o que o plano mostrado não mostrava — ou elegeria a
    sobrevivente por uma contagem que já não vale. Com as linhas travadas, o
    que se lê aqui é o que será gravado.
    """
    planejadas = [e for f in fusoes for e in (f.sobrevivente, *f.absorvidas)]
    ids = sorted({e.id for e in planejadas}, key=str)

    travadas = {r.id: r for r in (await conn.execute(text(_TRAVA_EMPRESAS), {"ids": ids})).all()}
    contagens: dict[str, dict[Any, int]] = {}
    for rotulo, tabela, modo in _TRAVA_DEPENDENTES:
        consulta = (
            f"SELECT company_id FROM {tabela} WHERE company_id = ANY(:ids) "
            f"ORDER BY id FOR {modo}"
        )
        por_empresa: dict[Any, int] = {}
        for (empresa_id,) in (await conn.execute(text(consulta), {"ids": ids})).all():
            por_empresa[empresa_id] = por_empresa.get(empresa_id, 0) + 1
        contagens[rotulo] = por_empresa

    diferencas: list[str] = []
    for e in planejadas:
        atual = travadas.get(e.id)
        if atual is None:
            diferencas.append(f"{e.id} ({e.nome!r}): a empresa não existe mais")
            continue
        if atual.doc != e.doc:
            diferencas.append(f"{e.id} ({e.nome!r}): o CNPJ mudou")
        if atual.group_id != e.group_id:
            diferencas.append(f"{e.id} ({e.nome!r}): o grupo mudou")
        for rotulo, antes in (
            ("clientes", e.clientes),
            ("notas", e.notas),
            ("equipamentos", e.equipamentos),
        ):
            agora = contagens[rotulo].get(e.id, 0)
            if agora != antes:
                diferencas.append(f"{e.id} ({e.nome!r}): {rotulo} eram {antes}, agora {agora}")
    if diferencas:
        raise PlanoDesatualizadoError(diferencas)


async def _aplica(conn, fusoes: Sequence[Fusao]) -> dict[str, int]:
    """Grava o plano inteiro numa transação; em qualquer erro, desfaz tudo.

    Devolve quantas linhas foram movidas de cada tipo.
    """
    movidos = {"clientes": 0, "notas": 0, "equipamentos": 0}
    try:
        await conn.execute(text(f"SET LOCAL lock_timeout = '{_ESPERA_POR_TRAVA}'"))
        await _trava_e_confere(conn, fusoes)
        for f in fusoes:
            alvos = [a.id for a in f.absorvidas]
            # Move ANTES de apagar: company_notes é ON DELETE CASCADE e users é
            # SET NULL. Na ordem inversa, nota vira lixo e cliente vira órfão.
            # A empresa do aparelho é RESTRICT: sem movê-lo o DELETE falha. A
            # troca é de uma duplicata para a sobrevivente do MESMO CNPJ — a
            # empresa do aparelho continua sendo a mesma empresa.
            for rotulo, tabela in (
                ("clientes", "users"),
                ("notas", "company_notes"),
                ("equipamentos", "equipments"),
            ):
                resultado = await conn.execute(
                    text(f"UPDATE {tabela} SET company_id = :fica WHERE company_id = ANY(:alvos)"),
                    {"fica": f.sobrevivente.id, "alvos": alvos},
                )
                movidos[rotulo] += resultado.rowcount
            await conn.execute(
                text("DELETE FROM companies WHERE id = ANY(:alvos)"),
                {"alvos": alvos},
            )
        await conn.commit()
    except BaseException:
        await conn.rollback()
        raise
    return movidos


async def _levanta(conn) -> list[Empresa]:
    linhas = (await conn.execute(text(_LEVANTAMENTO))).all()
    return [
        Empresa(
            r.id,
            r.doc,
            r.nome,
            r.group_id,
            r.criada_em,
            r.clientes,
            r.notas,
            r.equipamentos,
        )
        for r in linhas
    ]


async def _main(aplicar: bool) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Defina DATABASE_URL antes de rodar.")

    modo = "APLICANDO" if aplicar else "DRY-RUN (nada será gravado)"
    print(f"Fusão de empresas duplicadas — {modo}")

    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            fusoes, recusadas = planeja_fusao(await _levanta(conn))
            _relata(fusoes, recusadas)

            if not fusoes and not recusadas:
                print("\nNada a fazer — nenhum CNPJ repetido entre empresas.")
                return

            if aplicar and fusoes:
                try:
                    movidos = await _aplica(conn, fusoes)
                except PlanoDesatualizadoError as e:
                    print("\nNADA FOI GRAVADO: o banco mudou depois do levantamento acima.")
                    for diferenca in e.diferencas:
                        print(f"  - {diferenca}")
                    print("Rode de novo para ver o plano atual.")
                    raise SystemExit(1) from None
                except DBAPIError as e:
                    # Só a classe do erro: a mensagem do driver pode trazer
                    # valores das linhas.
                    print(
                        f"\nNADA FOI GRAVADO: o banco recusou a operação "
                        f"({type(e.orig).__name__}). Se foi espera por trava, há outra "
                        "operação em curso nessas empresas — rode de novo."
                    )
                    raise SystemExit(1) from None
                apagadas = sum(len(f.absorvidas) for f in fusoes)
                print(f"\nOK: {apagadas} empresa(s) absorvida(s) em {len(fusoes)} CNPJ(s).")
                print(
                    f"Movidos: {movidos['clientes']} cliente(s), {movidos['notas']} nota(s) e "
                    f"{movidos['equipamentos']} equipamento(s)."
                )
            elif fusoes:
                apagadas = sum(len(f.absorvidas) for f in fusoes)
                print(
                    f"\n{apagadas} empresa(s) seriam apagadas. "
                    "Rode de novo com --aplicar para gravar."
                )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="grava as mudanças; sem esta flag o script só relata",
    )
    asyncio.run(_main(parser.parse_args().aplicar))
