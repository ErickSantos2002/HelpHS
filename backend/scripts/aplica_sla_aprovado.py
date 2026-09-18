"""
Grava os prazos de SLA aprovados pelo SGI direto no banco — cada prazo anterior
pela metade.

**Avulso, rodado à mão.** Não é chamado por ninguém, não é migration, não entra
no boot do container. Prazo de SLA é configuração do cliente: mudá-lo por
migration alteraria o contrato de atendimento sozinho, no deploy seguinte, sem
ninguém clicar.

POR QUE ELE EXISTE, se a tela de SLA já edita esses valores
------------------------------------------------------------
Por causa de **um** dos oito valores. Metade da resposta do nível crítico é 30
minutos, e a tela de hoje envia horas inteiras com mínimo 1 — 30 min não existe
naquele contrato. Os outros sete são hora cheia e a tela aplica sem problema.

Então o caminho normal é a tela, e este script é a saída para o valor que ela
ainda não alcança. Ele aplica os oito de qualquer forma, e é **idempotente**:
o que já estiver certo aparece como "já está" e não é reescrito. Rodar depois
de ter usado a tela é seguro.

Sai de cena quando a tela de SLA passar a aceitar minutos (pendência de
frontend, registrada para depois da migração do design system).

O QUE ELE NÃO FAZ
-----------------
**Não toca chamado nenhum.** Os prazos de um chamado são colunas dele
(`sla_response_due_at` / `sla_resolve_due_at`), carimbadas na criação; nada no
sistema os recalcula a partir da política. Mudar a configuração vale para quem
nascer depois — os abertos hoje mantêm o prazo com que nasceram. Este script
escreve só em `sla_configs`.

A única exceção é a reabertura, que dá ao ciclo novo o prazo vigente. É
decisão registrada, não efeito colateral daqui.

Deixa rastro em `audit_logs` com a ação `update`, porque mudança de SLA em
produção sem registro é pior que o problema que veio resolver.

Uso::

    cd backend
    export DATABASE_URL='postgresql+asyncpg://usuario:senha@host:porta/banco'

    python -m scripts.aplica_sla_aprovado
    python -m scripts.aplica_sla_aprovado --aplicar --por voce@empresa.com

Sem `--aplicar` nada é escrito: o script lê, mostra o antes/depois e sai.
"""

import argparse
import asyncio
import json
import os
import sys
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# O console do Windows abre em cp1252 e estoura em qualquer acento — e este
# script roda na máquina de quem administra, não no container.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# Os valores aprovados, em minutos. A mesma tabela que vive em `app/seeds.py`;
# aqui ela é repetida de propósito, e a repetição é conferida por teste
# (`test_o_script_avulso_e_a_semente_carregam_os_mesmos_valores`): o script
# precisa rodar contra produção sem depender de importar o app inteiro, e
# duas listas que ninguém compara divergem no primeiro dia.
APROVADOS: dict[str, dict[str, int]] = {
    "critical": {"response_time_minutes": 30, "resolve_time_minutes": 120},
    "high": {"response_time_minutes": 60, "resolve_time_minutes": 240},
    "medium": {"response_time_minutes": 120, "resolve_time_minutes": 720},
    "low": {"response_time_minutes": 240, "resolve_time_minutes": 1440},
}

_ORDEM = ("critical", "high", "medium", "low")
_ROTULO = {"critical": "crítico", "high": "alto", "medium": "médio", "low": "baixo"}


def _humano(minutos: int) -> str:
    """`90` vira `1h30`, `240` vira `4h`, `30` vira `30min`."""
    horas, resto = divmod(minutos, 60)
    if horas and resto:
        return f"{horas}h{resto:02d}"
    if horas:
        return f"{horas}h"
    return f"{resto}min"


async def principal() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--por", help="e-mail de quem está executando (vai para o audit_log)")
    parser.add_argument("--aplicar", action="store_true", help="grava (sem isto, só relata)")
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL não definida. Exporte-a antes de rodar.")
        return 1

    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            linhas = (
                await conn.execute(
                    text(
                        "SELECT id, level, response_time_minutes, resolve_time_minutes "
                        "FROM sla_configs"
                    )
                )
            ).all()

            if not linhas:
                print("Nenhuma linha em sla_configs. O seed do boot ainda não rodou?")
                return 1

            atual = {
                str(nivel): {"id": cid, "resposta": resp, "resolucao": reso}
                for cid, nivel, resp, reso in linhas
            }

            faltando = [n for n in _ORDEM if n not in atual]
            if faltando:
                print(f"Níveis ausentes em sla_configs: {', '.join(faltando)}.")
                print("Rode o seed antes — este script só edita o que já existe.")
                return 1

            print(f"{'nível':<10} {'resposta':>18}   {'resolução':>18}")
            print("─" * 52)

            mudancas: list[tuple[str, dict, dict]] = []
            for nivel in _ORDEM:
                agora = atual[nivel]
                alvo = APROVADOS[nivel]
                muda_resp = agora["resposta"] != alvo["response_time_minutes"]
                muda_reso = agora["resolucao"] != alvo["resolve_time_minutes"]

                def _col(de: int, para: int, muda: bool) -> str:
                    if not muda:
                        return f"{_humano(de):>8}  (já está)"
                    return f"{_humano(de):>8} → {_humano(para):<7}"

                print(
                    f"{_ROTULO[nivel]:<10} "
                    f"{_col(agora['resposta'], alvo['response_time_minutes'], muda_resp):>18}   "
                    f"{_col(agora['resolucao'], alvo['resolve_time_minutes'], muda_reso):>18}"
                )
                if muda_resp or muda_reso:
                    mudancas.append((nivel, agora, alvo))

            print()
            if not mudancas:
                print("Nada a fazer: os quatro níveis já estão com os valores aprovados.")
                return 0

            if not args.aplicar:
                print(f"{len(mudancas)} nível(is) a alterar. Nada foi escrito.")
                print("Rode de novo com --aplicar para gravar.")
                return 0

            ator_id = None
            if args.por:
                ator_id = (
                    await conn.execute(
                        text("SELECT id FROM users WHERE lower(email) = lower(:email)"),
                        {"email": args.por},
                    )
                ).scalar_one_or_none()
                if ator_id is None:
                    print(f"Nenhuma conta com o e-mail {args.por!r} — o registro ficará sem autor.")

            for nivel, agora, alvo in mudancas:
                await conn.execute(
                    text(
                        "UPDATE sla_configs SET response_time_minutes = :resp, "
                        "resolve_time_minutes = :reso, updated_at = now() WHERE id = :id"
                    ),
                    {
                        "resp": alvo["response_time_minutes"],
                        "reso": alvo["resolve_time_minutes"],
                        "id": agora["id"],
                    },
                )
                await conn.execute(
                    text(
                        "INSERT INTO audit_logs (id, user_id, action, entity_type, entity_id,"
                        " old_data, new_data)"
                        " VALUES (:id, :ator, 'update', 'sla_config', :alvo,"
                        " CAST(:antes AS jsonb), CAST(:depois AS jsonb))"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "ator": ator_id,
                        "alvo": agora["id"],
                        "antes": json.dumps(
                            {
                                "response_time_minutes": agora["resposta"],
                                "resolve_time_minutes": agora["resolucao"],
                            }
                        ),
                        "depois": json.dumps(alvo),
                    },
                )
                print(f"gravado: {_ROTULO[nivel]}")

            print()
            print(f"{len(mudancas)} nível(is) atualizado(s).")
            print("Chamado já aberto NÃO muda de prazo: o dele foi carimbado na criação.")
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
