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
