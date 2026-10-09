"""
Readiness do telefone: mede o legado que impede — ou que voltaria a impedir —
a constraint de presença no PostgreSQL.

**Somente leitura.** Não existe `--aplicar` aqui de propósito: este script não
decide nada, só conta. Roda à mão, na máquina de quem administra.

Por que ele existe
------------------
A regra "cliente ativo precisa de telefone" vive em duas camadas. Na
**aplicação** (Fase 1A, `app/utils/telefone.py` e `_guarda_telefone_do_cliente`)
ela valida e **normaliza** o número para E.164, e é **prospectiva**: proíbe a
perda do telefone, não a ausência dele, para que as contas legadas continuem
podendo editar nome e departamento. No **banco**, a Fase 1C acrescentou a
proteção estrutural de **PRESENÇA**: o `CHECK` validado
`ck_users_cliente_ativo_tem_telefone`, na tabela `users`.

Essa trava de banco só pôde nascer porque **nenhuma** linha a violava. O motivo
está medido em `docs/decisoes-e-regras.md`, na seção "Por que não usamos CHECK
NOT VALID para telefone": um `CHECK ... NOT VALID` aceita o legado na criação,
mas rejeita qualquer `UPDATE` posterior daquela linha — inclusive o que só
troca o nome. Seria o banco contradizendo a regra publicada.

Este script segue sendo a ferramenta operacional que mede `client + active`
sem telefone, e continua sendo pré-requisito de deploy: a migration da Fase 1C
falha se encontrar linha violando, então `LEGADO_INVALIDO` precisa estar em
zero antes de subir — e continua servindo para conferir o estado de qualquer
banco depois disso.

O que ele NÃO faz
-----------------
- **Não diz QUEM são as contas.** A saída é agregada de propósito: nome,
  e-mail, telefone e id de usuário ficam de fora, para que o relatório possa
  ser colado num chamado ou numa conversa sem vazar dado pessoal. Listar as
  linhas para saneamento é consulta separada e deliberada.
- **Não mede FORMATO.** A constraint da Fase 1C é de presença; o formato E.164
  fica **fora dela** e é garantido pelo tipo anotado em toda porta de escrita
  da aplicação. Os blocos informativos sobre formato continuam abaixo, mas
  **não entram no `LEGADO_INVALIDO` nem no código de saída**.
- **Não olha `companies.phone`.** A fonte da telefonia é `users.phone`
  (decisão registrada); `companies.phone` continua **fora do portão** e
  aparece adiante só como bloco informativo.
- **Não corrige nada.** Dado histórico se corrige em tarefa administrativa
  explícita, nunca por backfill automático e nunca por número inventado.

Saída para máquina
------------------
Imprime uma linha exata, fácil de casar por `grep`::

    LEGADO_INVALIDO=<N>

Códigos de saída::

    0  pronto        LEGADO_INVALIDO = 0 — a constraint pode ser criada
    1  há legado     LEGADO_INVALIDO > 0 — sanear antes
    2  erro          falha operacional: sem DATABASE_URL, conexão recusada,
                     consulta quebrada. NÃO confundir com "há legado".

O código 2 existe para que um operador nunca leia "o script quebrou" como
"ainda há legado", nem o contrário.

Uso::

    cd backend
    export DATABASE_URL='postgresql+asyncpg://usuario:senha@host:porta/banco'
    python -m scripts.diagnostico_telefone

⚠️ Exporte a `DATABASE_URL` explicitamente. Herdar o `.env` da árvore é o que
faz um script avulso bater em produção sem ninguém pedir: a trava
`exige_alvo_liberado` (`app/utils/migrations.py`) cobre só o alembic, não isto.

Este script **não** está no CI, e é deliberado: o CI não pode depender do banco
de produção, nem guardar credencial de produção em segredo de Actions.
"""

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# O console do Windows abre em cp1252 e estoura em qualquer acento — e este
# script roda na máquina de quem administra, não no container.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ── Códigos de saída ──────────────────────────────────────────

SAIDA_PRONTO = 0
SAIDA_HA_LEGADO = 1
SAIDA_ERRO = 2


def decide_saida(legado_invalido: int) -> int:
    """Traduz a contagem em código de saída.

    Função pura e separada do resto porque é ela que um portão operacional
    consulta — e porque "há legado" (1) nunca pode ser confundido com "o
    script quebrou" (2), que é decidido no tratamento de erro, não aqui.
    """
    return SAIDA_PRONTO if legado_invalido == 0 else SAIDA_HA_LEGADO


# ── A definição de "telefone ausente" ─────────────────────────
#
# `btrim` só remove espaço; um telefone guardado como "\t" ou "\n" escaparia
# dele. O vazio de verdade é "não sobrou nada depois de tirar TODO espaço em
# branco", e é por isso que a expressão usa `\s` e não `btrim`.
#
# Esta é a definição auditada, e ela NÃO muda nesta fase: cobre NULL, string
# vazia, só espaços, tabulação e quebra de linha — e mais nada.

_AUSENTE = "regexp_replace(coalesce({col}, ''), '\\s', '', 'g') = ''"
_SO_DIGITOS = r"regexp_replace(coalesce({col}, ''), '\D', '', 'g')"


# O número que decide tudo. O recorte é escrito por extenso — `status <>
# 'inactive'` NÃO serve, porque o enum tem TRÊS valores e incluiria os
# anonimizados, que é justamente quem a anonimização acabou de deixar sem
# telefone de propósito.
_LEGADO_INVALIDO = f"""
    SELECT count(*) AS quantos
      FROM users
     WHERE role = 'client'
       AND status = 'active'
       AND {_AUSENTE.format(col="phone")}
"""

# Panorama por papel e situação: a única visão que não mente sobre o que é
# legado e o que é direito ao esquecimento.
_PANORAMA = f"""
    SELECT role::text                                         AS papel,
           status::text                                       AS situacao,
           count(*)                                           AS pessoas,
           count(*) FILTER (WHERE {_AUSENTE.format(col="phone")}) AS sem_telefone
      FROM users
     GROUP BY 1, 2
     ORDER BY 1, 2
"""

# ── INFORMATIVO — nada abaixo entra no LEGADO_INVALIDO ────────

# Dimensiona um eventual saneamento de formato. As colunas SE SOBREPÕEM:
# `com_ddi` é subconjunto de `com_mascara` (o '+' é caractere não numérico).
# Não somar.
_FORMATOS = f"""
    SELECT count(*)                                       AS preenchidos,
           count(*) FILTER (WHERE phone LIKE '+%%')       AS com_ddi,
           count(*) FILTER (WHERE phone ~ '[^0-9]')       AS com_mascara,
           count(*) FILTER (WHERE phone ~ '^[0-9]+$')     AS so_digitos,
           min(length({_SO_DIGITOS.format(col="phone")})) AS menor_qtd_digitos,
           max(length({_SO_DIGITOS.format(col="phone")})) AS maior_qtd_digitos
      FROM users
     WHERE NOT {_AUSENTE.format(col="phone")}
"""

_POR_TAMANHO = f"""
    SELECT length({_SO_DIGITOS.format(col="phone")}) AS digitos,
           count(*)                                  AS quantos
      FROM users
     WHERE NOT {_AUSENTE.format(col="phone")}
     GROUP BY 1
     ORDER BY 1
"""

# `companies.phone` NÃO é fonte da telefonia (decisão registrada) e não entra
# no portão. Fica no relatório porque o normalizador vale para as duas
# tabelas, e porque o PUT de empresa grava string vazia em vez de nulo.
_EMPRESAS = f"""
    SELECT count(*)                                          AS empresas,
           count(*) FILTER (WHERE {_AUSENTE.format(col="phone")}) AS sem_telefone,
           count(*) FILTER (WHERE phone = '')                AS string_vazia,
           max(length(coalesce(phone, '')))                  AS maior_texto
      FROM companies
"""


def _titulo(texto: str) -> None:
    print(f"\n-- {texto} " + "-" * max(4, 62 - len(texto)))


async def conta_legado_invalido(conn) -> int:
    """Quantos `role=client` + `status=active` estão sem telefone.

    É o `LEGADO_INVALIDO`. Separada do relatório para poder ser exercitada
    contra PostgreSQL de verdade sem passar pela saída de tela — é a SQL que
    precisa de teste, não o `print`.
    """
    return int((await conn.execute(text(_LEGADO_INVALIDO))).scalar_one())


async def _relatorio(conn) -> int:
    print("Readiness do telefone - SOMENTE LEITURA")

    _titulo("1. Panorama por papel e situação")
    print(f"    {'papel':<12} {'situação':<12} {'pessoas':>8} {'sem tel.':>9}")
    for r in (await conn.execute(text(_PANORAMA))).all():
        print(f"    {r.papel:<12} {r.situacao:<12} {r.pessoas:>8} {r.sem_telefone:>9}")
    print()
    print("    Cliente anonimizado sem telefone é o esperado, não legado:")
    print("    a anonimização zera o campo de propósito.")

    _titulo("2. O portão: cliente ATIVO sem telefone")
    legado = await conta_legado_invalido(conn)
    print(f"    {legado} cliente(s) ativo(s) sem telefone")
    print()
    if legado:
        print("    > 0  ->  a constraint de presença NÃO pode ser criada ainda.")
        print("             Sanear é tarefa administrativa explícita: excluir,")
        print("             inativar ou cadastrar telefone real. NUNCA inventar")
        print("             número, nunca backfill automático.")
        print()
        print("    Quem são essas contas NÃO sai aqui de propósito: esta saída é")
        print("    agregada para poder ser colada num chamado sem vazar dado")
        print("    pessoal. Identificá-las é consulta separada e deliberada.")
    else:
        print("    nenhum ✅  a constraint de presença pode ser criada VALIDADA.")
        print("             O PostgreSQL ainda verifica as linhas existentes, mas")
        print("             com o volume atual da tabela esse custo é pequeno.")

    _titulo("3. INFORMATIVO - formato do que já está guardado")
    f = (await conn.execute(text(_FORMATOS))).one()
    print(f"    preenchidos ........ {f.preenchidos}")
    print(f"    com DDI (+) ........ {f.com_ddi}")
    print(f"    com máscara ........ {f.com_mascara}   (inclui os com DDI)")
    print(f"    só dígitos ......... {f.so_digitos}")
    print(f"    dígitos: menor {f.menor_qtd_digitos}, maior {f.maior_qtd_digitos}")
    print()
    print("    NÃO entra no LEGADO_INVALIDO: a constraint aprovada é de")
    print("    PRESENÇA. O formato é garantido pelo tipo anotado nas portas de")
    print("    escrita da aplicação, não pelo banco.")

    _titulo("4. INFORMATIVO - quantos dígitos cada um tem")
    for r in (await conn.execute(text(_POR_TAMANHO))).all():
        if r.digitos >= 12:
            nota = "já traz o DDI"
        elif r.digitos in (10, 11):
            nota = "nacional com DDD"
        else:
            nota = "INCOMPLETO - ninguém completa sem adivinhar"
        print(f"      {r.digitos:>2} dígito(s): {r.quantos:>6}   {nota}")

    _titulo("5. INFORMATIVO - companies.phone")
    c = (await conn.execute(text(_EMPRESAS))).one()
    print(f"    empresas ........... {c.empresas}")
    print(f"    sem telefone ....... {c.sem_telefone}")
    print(f"    string vazia ('') .. {c.string_vazia}")
    print(f"    maior texto ........ {c.maior_texto} caractere(s) (coluna é 20)")
    print()
    print("    Fora do portão: `companies.phone` não é fonte da telefonia.")

    print()
    print(f"LEGADO_INVALIDO={legado}")
    return legado


async def _main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERRO: defina DATABASE_URL antes de rodar.", file=sys.stderr)
        return SAIDA_ERRO

    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            legado = await _relatorio(conn)
    except Exception as e:  # noqa: BLE001
        # Falha operacional é código PRÓPRIO: sem isto, um banco fora do ar
        # sairia com o mesmo código de "ainda há legado", e o portão mentiria
        # para o lado de deixar passar. A mensagem não repete a URL.
        print(f"ERRO operacional: {type(e).__name__}", file=sys.stderr)
        return SAIDA_ERRO
    finally:
        await engine.dispose()

    return decide_saida(legado)


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
