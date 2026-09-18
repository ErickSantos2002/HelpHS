"""
A trava que impede migration de rodar contra banco remoto por acidente.

Por que este arquivo existe
---------------------------
O `alembic/env.py` resolve a URL por `get_settings().database_url`, e uma das
árvores de trabalho tem `.env` apontando para produção. `alembic check` ali é
uma consulta; `alembic upgrade head` é DDL, disparada antes de alguém perceber
que a URL não era a que pensava.

Os testes de baixo rodam o alembic como SUBPROCESSO de verdade, e não chamam a
função direto. O que interessa provar não é que a função levanta — é que o
`env.py` a chama, e a chama **antes** de conectar. Uma trava escrita e não
ligada passaria num teste de unidade e não impediria nada.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.utils.migrations import LIBERACAO, AlvoRemotoSemLiberacaoError, exige_alvo_liberado

_BACKEND = Path(__file__).resolve().parents[1]

# Endereço reservado para documentação (RFC 5737). Se a trava falhar, a conexão
# não vai a lugar nenhum — o teste estoura no timeout em vez de bater numa
# máquina de alguém.
_REMOTO = "postgresql+asyncpg://usuario:senha@203.0.113.10:5432/qualquer"


def _roda_alembic(url: str, liberado: bool) -> subprocess.CompletedProcess[str]:
    ambiente = {**os.environ, "DATABASE_URL": url, "APP_ENV": "testing"}
    ambiente.pop(LIBERACAO, None)
    if liberado:
        ambiente[LIBERACAO] = "1"

    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND,
        env=ambiente,
        capture_output=True,
        text=True,
        errors="replace",
        # Se a trava não disparar, o alembic tenta conectar num endereço que não
        # responde. O timeout é o que transforma "trava quebrada" em teste
        # vermelho em vez de suíte pendurada.
        timeout=90,
    )


# ── A trava, ligada de verdade ────────────────────────────────


def test_o_alembic_recusa_banco_remoto_sem_liberacao():
    """
    O caso que motivou tudo, exercitado pelo comando de verdade.

    Não é `pytest.raises` numa função: é `python -m alembic upgrade head`,
    exatamente como sai de um terminal, com a URL vindo do ambiente pelo mesmo
    caminho que o `.env` usaria.
    """
    resultado = _roda_alembic(_REMOTO, liberado=False)

    assert resultado.returncode != 0
    saida = resultado.stdout + resultado.stderr
    assert "203.0.113.10" in saida, "a mensagem diz PARA ONDE ia, senão não ajuda ninguém"
    assert LIBERACAO in saida, "e diz como liberar, para quem realmente quis"


def test_a_liberacao_do_start_sh_deixa_passar():
    """
    A trava não pode impedir o deploy — ali o banco remoto é o alvo pretendido.

    Passa da trava e morre depois, sem conseguir conectar: é o que se espera de
    um endereço reservado. O que se afirma aqui é que a mensagem da trava NÃO
    aparece; o erro é de conexão, que é problema de outra natureza.
    """
    resultado = _roda_alembic(_REMOTO, liberado=True)

    assert resultado.returncode != 0, "o endereço é reservado; conectar seria surpresa"
    assert LIBERACAO not in resultado.stdout + resultado.stderr


# ── A regra, caso a caso ──────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://postgres:@127.0.0.1:51780/helpdesk_db",
        "postgresql+asyncpg://postgres:@localhost:5432/helpdesk_db",
        "postgresql+asyncpg://postgres:@[::1]:5432/helpdesk_db",
        "sqlite+aiosqlite:///./local.db",
    ],
)
def test_alvo_local_passa_sem_liberacao_nenhuma(url, monkeypatch):
    """
    Banco local não é produção, e travar quem desenvolve ensina a desligar trava.

    O `pgserver` da suíte cai aqui: sem esta passagem livre, todo teste de
    migration precisaria carregar a variável, e a primeira pessoa a esbarrar
    nisso exportaria a liberação no shell — matando a trava para tudo.
    """
    monkeypatch.delenv(LIBERACAO, raising=False)

    exige_alvo_liberado(url)


def test_url_ilegivel_nao_e_problema_da_trava(monkeypatch):
    """
    Ela não pode ser o motivo de o contêiner não subir.

    URL quebrada o alembic reporta melhor do que ela reportaria, e uma trava que
    transforma erro de digitação em erro de segurança só ensina a desconfiar da
    mensagem.
    """
    monkeypatch.delenv(LIBERACAO, raising=False)

    exige_alvo_liberado("isto não é uma URL")


def test_a_liberacao_e_exatamente_um(monkeypatch):
    """
    `"true"`, `"sim"` e `"0"` NÃO liberam.

    Uma variável de ambiente sobrevivente no shell de alguém não pode valer
    liberação por acidente de valor. O contrato é um caractere, e o `start.sh`
    escreve esse caractere.
    """
    for valor in ("true", "sim", "0", "", "yes"):
        monkeypatch.setenv(LIBERACAO, valor)
        with pytest.raises(AlvoRemotoSemLiberacaoError):
            exige_alvo_liberado(_REMOTO)


def test_o_start_sh_libera_a_trava():
    """
    O acoplamento entre um shell script e um nome de variável em Python.

    Se alguém renomear a constante e não o `start.sh`, a trava passa a barrar o
    DEPLOY — e o sintoma é o contêiner não subir, com o EasyPanel mostrando
    build verde. É o mesmo modo de falha do `alembic heads`, e é caro na mesma
    medida.
    """
    start = (_BACKEND / "start.sh").read_text(encoding="utf-8")

    assert f"{LIBERACAO}=1 alembic upgrade head" in start
