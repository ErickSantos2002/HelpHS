"""
Preenche a empresa dos equipamentos que nasceram antes de ela existir (ECE-01).

**Avulso, rodado à mão, NUNCA em migration** — regra do projeto: dado
histórico se corrige em script, regra nova é prospectiva.

A revision `o1j2k3l4m5n6` criou `equipments.company_id` nula em todas as
linhas. Daí em diante o cadastro e o vínculo do cliente gravam a empresa; o
que já existia fica para este script.

O que ele NÃO presume
---------------------
"A empresa atual do responsável" não é, por si, a empresa do aparelho antigo.
O responsável pode ter sido trocado, a conta pode estar inativa, e de 26/08 a
09/10/2026 a série repetida ANEXAVA gente de outra empresa ao aparelho
(`equipment_users`). Por isso só é preenchido o caso sem nenhum sinal
contrário, e tudo o mais é MOSTRADO, não resolvido:

    preenchivel              responsável é cliente ativo, tem vínculo oficial, e
                             ninguém de outra empresa aparece ligado ao aparelho
                             — nem em `equipment_users`, nem abrindo chamado
    ambiguo                  o mesmo, mas alguém de OUTRA empresa aparece
    responsavel_inapto       responsável não é cliente ativo
    responsavel_sem_vinculo  responsável sem `users.company_id`
    sem_responsavel          `owner_id` nulo
    divergente               o aparelho JÁ tem empresa, diferente da do
                             responsável — só informado; nunca é tocado
    sem_empresa_por_decisao  a EQUIPE deixou o aparelho sem empresa de propósito
                             (`company_id: null` explícito) — só informado;
                             nunca é tocado, nem por este script nem pelo vínculo

O que não é `preenchivel` se resolve à mão, pela equipe, na tela ou em
`PATCH /equipments/{id}` com `company_id` — que audita o antes e o depois.

Uso::

    cd backend
    export DATABASE_URL='postgresql+asyncpg://usuario:senha@host:porta/banco'

    python -m scripts.preenche_empresa_do_equipamento                    # confere
    python -m scripts.preenche_empresa_do_equipamento --confere          # idem
    python -m scripts.preenche_empresa_do_equipamento --aplicar --esperados 4

Sem `--aplicar` nada é escrito. `--esperados` é o número de preenchíveis que o
`--confere` mostrou: se o levantamento de agora der outro número, o script
para sem gravar — o que se grava é o plano que alguém leu, não o que o banco
virou depois.

Cada linha gravada deixa o antes e o depois em `audit_logs` (ação `update`,
entidade `equipment`, origem `script_preenche_empresa_do_equipamento`, sem
`user_id`: script não é pessoa). A gravação refaz as duas conferências na
própria instrução — aparelho ainda sem empresa e sem a marca de decisão,
responsável ainda vinculado à mesma empresa — e PULA o que mudou desde o
levantamento.

Rodar de novo é seguro: o que já tem empresa sai do levantamento.
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from collections.abc import Iterable, Sequence
from typing import Any, NamedTuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# O console do Windows abre em cp1252 e estoura em qualquer acento — e este
# script roda na máquina de quem administra, não no container.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ORIGEM = "script_preenche_empresa_do_equipamento"

CATEGORIAS = (
    "preenchivel",
    "ambiguo",
    "responsavel_inapto",
    "responsavel_sem_vinculo",
    "sem_responsavel",
    "divergente",
    "sem_empresa_por_decisao",
)


class Linha(NamedTuple):
    """Um equipamento como o levantamento o enxerga."""

    id: Any
    nome: str
    serie: str | None
    empresa_atual: Any
    responsavel_id: Any
    responsavel_papel: str | None
    responsavel_situacao: str | None
    empresa_do_responsavel: Any
    # Empresas (oficiais, não nulas) de OUTRAS pessoas ligadas ao aparelho.
    empresas_de_usuarios: tuple[Any, ...]
    empresas_de_chamados: tuple[Any, ...]
    # A equipe deixou o aparelho sem empresa de propósito.
    por_decisao: bool = False


class Item(NamedTuple):
    id: Any
    nome: str
    serie: str | None
    responsavel_id: Any
    empresa: Any
    motivo: str


# Uma linha por equipamento que ainda interessa: os sem empresa e os que têm
# empresa diferente da do responsável. `array_agg(DISTINCT ...)` sem ORDER BY
# de propósito — a ordem não importa aqui, e `ORDER BY 1` dentro de agregado
# ordena pela constante, não pela coluna (bug já pago em 04/11).
_LEVANTAMENTO = """
    SELECT e.id,
           e.name                AS nome,
           e.serial_number       AS serie,
           e.company_id          AS empresa_atual,
           e.sem_empresa_por_decisao AS por_decisao,
           e.owner_id            AS responsavel_id,
           u.role::text          AS responsavel_papel,
           u.status::text        AS responsavel_situacao,
           u.company_id          AS empresa_do_responsavel,
           coalesce((
               SELECT array_agg(DISTINCT x.company_id)
                 FROM equipment_users eu
                 JOIN users x ON x.id = eu.user_id
                WHERE eu.equipment_id = e.id
                  AND x.company_id IS NOT NULL
                  AND x.id IS DISTINCT FROM e.owner_id
           ), '{}')              AS empresas_de_usuarios,
           coalesce((
               SELECT array_agg(DISTINCT x.company_id)
                 FROM ticket_equipments te
                 JOIN tickets t ON t.id = te.ticket_id
                 JOIN users x ON x.id = t.creator_id
                WHERE te.equipment_id = e.id
                  AND x.company_id IS NOT NULL
                  AND x.id IS DISTINCT FROM e.owner_id
           ), '{}')              AS empresas_de_chamados
      FROM equipments e
      LEFT JOIN users u ON u.id = e.owner_id
     WHERE e.company_id IS NULL
        OR (u.company_id IS NOT NULL AND e.company_id <> u.company_id)
     ORDER BY e.created_at, e.id
"""


async def levanta(conn: AsyncConnection) -> list[Linha]:
    linhas = (await conn.execute(text(_LEVANTAMENTO))).all()
    return [
        Linha(
            r.id,
            r.nome,
            r.serie,
            r.empresa_atual,
            r.responsavel_id,
            r.responsavel_papel,
            r.responsavel_situacao,
            r.empresa_do_responsavel,
            tuple(r.empresas_de_usuarios),
            tuple(r.empresas_de_chamados),
            bool(r.por_decisao),
        )
        for r in linhas
    ]


def classifica(linha: Linha) -> tuple[str, str]:
    """Decide a categoria de UM equipamento, sem tocar no banco.

    Pura de propósito, como `planeja_fusao`: é aqui que um descuido mandaria o
    aparelho de uma empresa para outra. A ordem dos testes importa — o
    primeiro motivo de dúvida encerra a conversa.
    """
    if linha.empresa_atual is not None:
        return "divergente", "já tem empresa, diferente da empresa do responsável"
    # Antes de qualquer outra pergunta: este nulo não é lacuna. Mesmo com o
    # responsável ativo, vinculado e sem sinal contrário, a resposta é não.
    if linha.por_decisao:
        return "sem_empresa_por_decisao", "a equipe deixou sem empresa de propósito"
    if linha.responsavel_id is None:
        return "sem_responsavel", "sem responsável"
    if linha.responsavel_papel != "client" or linha.responsavel_situacao != "active":
        return (
            "responsavel_inapto",
            f"responsável {linha.responsavel_papel}/{linha.responsavel_situacao}",
        )
    if linha.empresa_do_responsavel is None:
        return "responsavel_sem_vinculo", "responsável sem empresa vinculada"

    de_fora_usuarios = [e for e in linha.empresas_de_usuarios if e != linha.empresa_do_responsavel]
    de_fora_chamados = [e for e in linha.empresas_de_chamados if e != linha.empresa_do_responsavel]
    if de_fora_usuarios or de_fora_chamados:
        sinais = []
        if de_fora_usuarios:
            sinais.append(f"usuário(s) do aparelho em outra(s) empresa(s): {de_fora_usuarios}")
        if de_fora_chamados:
            sinais.append(f"chamado(s) aberto(s) por outra(s) empresa(s): {de_fora_chamados}")
        return "ambiguo", "; ".join(sinais)

    return "preenchivel", "responsável ativo e vinculado, sem sinal contrário"


def planeja(linhas: Iterable[Linha]) -> dict[str, list[Item]]:
    plano: dict[str, list[Item]] = {categoria: [] for categoria in CATEGORIAS}
    for linha in linhas:
        categoria, motivo = classifica(linha)
        plano[categoria].append(
            Item(
                id=linha.id,
                nome=linha.nome,
                serie=linha.serie,
                responsavel_id=linha.responsavel_id,
                empresa=(
                    linha.empresa_atual
                    if categoria == "divergente"
                    else linha.empresa_do_responsavel
                ),
                motivo=motivo,
            )
        )
    return plano


_ROTULOS = {
    "preenchivel": "PREENCHÍVEIS — é o que --aplicar grava",
    "ambiguo": "AMBÍGUOS — decidir à mão",
    "responsavel_inapto": "RESPONSÁVEL NÃO É CLIENTE ATIVO — decidir à mão",
    "responsavel_sem_vinculo": "RESPONSÁVEL SEM EMPRESA — vincular o cliente resolve",
    "sem_responsavel": "SEM RESPONSÁVEL — decidir à mão",
    "divergente": "JÁ TÊM EMPRESA, DIFERENTE DA DO RESPONSÁVEL — só informado",
    "sem_empresa_por_decisao": "SEM EMPRESA POR DECISÃO DA EQUIPE — só informado",
}


def _relata(plano: dict[str, list[Item]]) -> None:
    for categoria in CATEGORIAS:
        itens = plano[categoria]
        print(f"\n── {_ROTULOS[categoria]}: {len(itens)}")
        for i in itens:
            print(f"   {i.id}  {i.nome!r}  série={i.serie!r}")
            print(f"      responsável={i.responsavel_id}  empresa={i.empresa}")
            print(f"      {i.motivo}")


# As duas conferências do levantamento, refeitas na hora de gravar: o aparelho
# ainda sem empresa e o responsável ainda o mesmo, ativo e na mesma empresa.
# `FOR KEY SHARE` no responsável é a trava que o vínculo e o desvínculo
# disputam (`FOR UPDATE` no cliente): ou esperam esta gravação, ou ela os vê.
_TRAVA_RESPONSAVEL = """
    SELECT company_id
      FROM users
     WHERE id = :responsavel
       AND role::text = 'client'
       AND status::text = 'active'
       FOR KEY SHARE
"""

_GRAVA = """
    UPDATE equipments
       SET company_id = :empresa
     WHERE id = :id
       AND company_id IS NULL
       AND NOT sem_empresa_por_decisao
       AND owner_id = :responsavel
 RETURNING id
"""

_AUDITA = """
    INSERT INTO audit_logs (id, user_id, action, entity_type, entity_id, old_data, new_data)
    VALUES (:audit_id, NULL, 'update', 'equipment', :id,
            CAST(:antes AS jsonb), CAST(:depois AS jsonb))
"""


async def aplica(conn: AsyncConnection, itens: Sequence[Item]) -> tuple[list[Any], list[Any]]:
    """Grava os preenchíveis numa transação só. Devolve (gravados, pulados)."""
    gravados: list[Any] = []
    pulados: list[Any] = []
    # Em ordem de responsável e de aparelho: duas execuções simultâneas — que
    # não deveriam existir — esperam uma pela outra em vez de em círculo.
    for item in sorted(itens, key=lambda i: (str(i.responsavel_id), str(i.id))):
        empresa_agora = (
            await conn.execute(text(_TRAVA_RESPONSAVEL), {"responsavel": item.responsavel_id})
        ).scalar_one_or_none()
        if empresa_agora != item.empresa:
            pulados.append(item.id)
            continue
        gravou = (
            await conn.execute(
                text(_GRAVA),
                {"empresa": item.empresa, "id": item.id, "responsavel": item.responsavel_id},
            )
        ).scalar_one_or_none()
        if gravou is None:
            pulados.append(item.id)
            continue
        await conn.execute(
            text(_AUDITA),
            {
                "audit_id": uuid.uuid4(),
                "id": item.id,
                "antes": json.dumps({"company_id": None}),
                "depois": json.dumps({"company_id": str(item.empresa), "origem": ORIGEM}),
            },
        )
        gravados.append(item.id)
    await conn.commit()
    return gravados, pulados


async def _main(aplicar: bool, esperados: int | None) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Defina DATABASE_URL antes de rodar.")
    if aplicar and esperados is None:
        raise SystemExit(
            "--aplicar exige --esperados N: o número de preenchíveis que o --confere mostrou."
        )

    modo = "APLICANDO" if aplicar else "CONFERINDO (nada será gravado)"
    print(f"Empresa dos equipamentos — {modo}")

    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            plano = planeja(await levanta(conn))
            _relata(plano)
            preenchiveis = plano["preenchivel"]

            if not aplicar:
                print(
                    f"\n{len(preenchiveis)} equipamento(s) seriam preenchidos. Para gravar: "
                    f"--aplicar --esperados {len(preenchiveis)}"
                )
                return

            if len(preenchiveis) != esperados:
                await conn.rollback()
                raise SystemExit(
                    f"\nNADA GRAVADO: o levantamento de agora tem {len(preenchiveis)} "
                    f"preenchível(is), e --esperados diz {esperados}. Confira de novo."
                )

            gravados, pulados = await aplica(conn, preenchiveis)
            print(f"\nOK: {len(gravados)} equipamento(s) preenchido(s).")
            if pulados:
                print(
                    f"⚠️  {len(pulados)} pulado(s) — mudaram entre o levantamento e a gravação: "
                    + ", ".join(str(p) for p in pulados)
                )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument(
        "--confere",
        action="store_true",
        help="só relata (é o padrão; a flag existe para o comando dizer o que faz)",
    )
    modo.add_argument(
        "--aplicar",
        action="store_true",
        help="grava os preenchíveis; exige --esperados",
    )
    parser.add_argument(
        "--esperados",
        type=int,
        default=None,
        help="número de preenchíveis que o --confere mostrou",
    )
    argumentos = parser.parse_args()
    asyncio.run(_main(argumentos.aplicar, argumentos.esperados))
