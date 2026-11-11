"""
A trava que impede migration de rodar contra banco remoto por acidente.

O `alembic/env.py` resolve a URL por `get_settings().database_url` — o mesmo
caminho da aplicação, e de propósito: duas fontes de verdade para "qual banco"
é como se acerta o banco errado. O efeito colateral é que qualquer `alembic`
disparado de um terminal aponta para onde o `.env` daquela árvore apontar, e
uma dessas árvores aponta para produção (ver "O `.env` de desenvolvimento
aponta para produção", em `docs/decisoes-e-regras.md`).

`alembic check` contra produção é uma consulta a `alembic_version`. `alembic
upgrade head` é outra história: roda DDL, e roda antes de qualquer pessoa
perceber que a URL não era a que ela pensava.

A trava é por ALVO, não por comando: o que decide é para onde a conexão vai,
não o que se pretendia fazer. Alvo local passa direto — banco local não é
produção, e travar o fluxo de quem desenvolve só ensinaria a desligar a trava.
Alvo remoto precisa de liberação explícita, e quem libera é o `start.sh`, que é
o único lugar onde migration remota é o comportamento pretendido.
"""

import os
import re
from collections.abc import Mapping

from sqlalchemy.engine import make_url

# Quem libera é o `start.sh`, dentro do contêiner. Fora dele, definir esta
# variável na mão é dizer "eu sei que estou apontando para um banco remoto" —
# que é exatamente a frase que o acidente não tem como dizer.
LIBERACAO = "ALEMBIC_ALVO_REMOTO_LIBERADO"

# `None` cobre SQLite e URLs sem host. O resto é a máquina de quem roda.
_ALVOS_LOCAIS = {None, "", "localhost", "127.0.0.1", "::1"}


class AlvoRemotoSemLiberacaoError(RuntimeError):
    """Migration apontada para banco remoto sem alguém ter dito que era para ir."""


def exige_alvo_liberado(url: str) -> None:
    """
    Deixa passar alvo local, ou remoto com liberação. Levanta no resto.

    Não valida credencial nem alcance: a pergunta é só "este host é a máquina
    de quem está rodando?". URL ilegível também passa — a trava não pode ser o
    motivo de o contêiner não subir, e um erro de URL o próprio alembic reporta
    melhor do que ela reportaria.
    """
    if os.environ.get(LIBERACAO) == "1":
        return

    try:
        host = make_url(url).host
    except Exception:  # noqa: BLE001 — URL quebrada é problema do alembic, não desta trava
        return

    if host in _ALVOS_LOCAIS:
        return

    raise AlvoRemotoSemLiberacaoError(
        f"Migration apontada para um banco REMOTO ({host}), e nada disse que era para ir.\n"
        "\n"
        "A URL sai do `.env` da árvore em que você está, pelo mesmo caminho que a\n"
        "aplicação usa. Confira antes de qualquer outra coisa:\n"
        "\n"
        '    python -c "from app.core.config import get_settings; '
        'print(get_settings().database_url)"\n'
        "\n"
        "Se era mesmo para rodar contra esse banco, diga isso de forma explícita:\n"
        "\n"
        f"    {LIBERACAO}=1 alembic upgrade head\n"
        "\n"
        "No contêiner quem faz isso é o `start.sh`, que é o único lugar onde\n"
        "migration contra banco remoto é o comportamento pretendido."
    )


# ── Limites de espera das migrations (F1-B-04c) ────────────────
#
# O boot roda `alembic upgrade head` com a instância ANTERIOR ainda atendendo
# (o EasyPanel só tira a antiga quando a nova sobe). Uma migration que precisa
# de bloqueio exclusivo espera qualquer transação aberta na tabela — e, enquanto
# espera, quem chega depois na mesma tabela fica parado atrás dela: o chat
# congela pelo tempo que a espera durar. Com limite, ela desiste, o PostgreSQL
# desfaz a transação INTEIRA das migrations (DDL é transacional nele) e o
# `set -e` do `start.sh` encerra o contêiner antes do uvicorn.
#
# Desligado por padrão: sem as variáveis nada muda, em ambiente nenhum. Quem
# liga é quem implanta, no ambiente do contêiner.
LIMITES_DA_MIGRATION = (
    ("lock_timeout", "ALEMBIC_LOCK_TIMEOUT"),
    ("statement_timeout", "ALEMBIC_STATEMENT_TIMEOUT"),
)
# Só número e unidade: o valor entra no SQL, e o SET não aceita parâmetro.
_DURACAO = re.compile(r"[0-9]+(ms|s|min)?")


class LimiteDeMigrationInvalidoError(ValueError):
    """Valor de `ALEMBIC_*_TIMEOUT` que não é uma duração simples."""


def comandos_de_limite(ambiente: Mapping[str, str] | None = None) -> list[str]:
    """Os `SET LOCAL` a rodar DENTRO da transação das migrations.

    `SET LOCAL` e não `SET`: vale só para esta transação e morre com ela —
    commit ou rollback —, sem vazar para nada que use a mesma conexão depois.
    Valor inválido levanta ANTES de conectar: um limite que a pessoa pensou ter
    ligado e não ligou é pior do que um boot que não sobe.
    """
    ambiente = os.environ if ambiente is None else ambiente
    comandos = []
    for parametro, variavel in LIMITES_DA_MIGRATION:
        valor = ambiente.get(variavel, "").strip()
        if not valor:
            continue
        if not _DURACAO.fullmatch(valor):
            raise LimiteDeMigrationInvalidoError(
                f"{variavel}={valor!r} não é uma duração (ex.: 3s, 500ms, 2min)."
            )
        comandos.append(f"SET LOCAL {parametro} = '{valor}'")
    return comandos
