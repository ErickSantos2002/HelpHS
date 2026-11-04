"""
Ambiente da suíte, aplicado antes de qualquer import de `app`.

Sem isto, rodar `pytest` na máquina de quem desenvolve pega o `.env` de
desenvolvimento: `APP_ENV` vira `development`, o rate limiter sobe **ligado** e
os testes que batem em `/auth/login` passam a competir com o limite de
5/15min — verde no CI, vermelho (ou intermitente) local.

`APP_ENV` é forçado porque a suíte só faz sentido em `testing`. `DATABASE_URL`
usa `setdefault` para que o CI (ou quem quiser apontar para outro banco) possa
sobrescrever — o banco é mockado em todos os testes, o valor só precisa exister
para o `Settings` validar.

Precedência que faz isto funcionar: variável de ambiente vence o `.env` lido
pelo pydantic-settings.

As chaves JWT são geradas aqui, efêmeras, a cada sessão: os testes de login e
de token de arquivo assinam RS256 de verdade, e `backend/keys/` é gitignored —
sem isto, 54 testes morrem com FileNotFoundError em qualquer máquina sem o par
(o CI ficou vermelho exatamente assim). Gerar sempre, em vez de usar as chaves
do dev quando existem, também isola a suíte de material real.
"""

import os
import tempfile
import threading
from pathlib import Path

os.environ["APP_ENV"] = "testing"
# Atribuicao, NAO setdefault: com setdefault, quem tivesse `DATABASE_URL`
# exportado no shell rodaria a suite contra aquele banco -- e o `.env` de
# desenvolvimento deste projeto aponta para producao. Nenhum teste usa esta
# URL para valer (os que precisam de Postgres sobem `pgserver` ou leem
# `TEST_POSTGRES_URL`), entao forcar o valor falso nao tira capacidade de
# nada e fecha o unico caminho pelo qual a suite tocaria dado real.
os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@localhost/db"

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

_dir_de_chaves = Path(tempfile.mkdtemp(prefix="helphs-test-keys-"))
_privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)

(_dir_de_chaves / "private.pem").write_bytes(
    _privada.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
)
(_dir_de_chaves / "public.pem").write_bytes(
    _privada.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
)

os.environ["JWT_PRIVATE_KEY_PATH"] = str(_dir_de_chaves / "private.pem")
os.environ["JWT_PUBLIC_KEY_PATH"] = str(_dir_de_chaves / "public.pem")


import pytest  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "mensagem_sem_seq: o teste grava mensagem do chat sem seq de propósito"
        " (ver tests/_mensagem_sem_seq.py)",
    )


@pytest.fixture(autouse=True)
def _guarda_do_seq(request, monkeypatch):
    """Reprova o teste em que a guarda do commit avisou de mensagem sem `seq`
    fora de `sem_seq_intencional()` e sem a marca `mensagem_sem_seq`.

    Embrulha a função do aviso — o log de produção continua saindo, e nada no
    commit muda: a guarda não barra, não escreve, não consulta.

    Não importa nada do `app`: sem o módulo carregado, o listener da guarda
    também não existe — e o teste que mexe no ambiente antes de importar o
    `app` segue no controle do próprio import.
    """
    import sys

    from tests._mensagem_sem_seq import intencional

    chat_sequencia = sys.modules.get("app.services.chat_sequencia")
    if chat_sequencia is None:
        yield []
        return
    original = chat_sequencia._avisa_mensagens_sem_seq
    flagradas: list[str] = []

    def _observa(mensagens):
        if not intencional.get():
            flagradas.extend(f"{m.id} no chamado {m.ticket_id}" for m in mensagens)
        original(mensagens)

    monkeypatch.setattr(chat_sequencia, "_avisa_mensagens_sem_seq", _observa)
    yield flagradas
    if flagradas and request.node.get_closest_marker("mensagem_sem_seq") is None:
        pytest.fail(
            "mensagem do chat foi para o commit SEM seq (guarda F1-B-04c): "
            + ", ".join(flagradas)
            + ". Escritor novo: chame numera_mensagens_do_chat antes do commit. Legado"
            " de propósito: sem_seq_intencional() ou @pytest.mark.mensagem_sem_seq."
        )


class EspiaDeThread:
    """
    Substitui uma função síncrona e registra em qual thread ela rodou.

    Serve para provar que o bcrypt (síncrono, ~250 ms) não roda na thread do
    event loop: ali ele travaria a API inteira a cada chamada. Comparar threads
    é determinístico — cronometrar seria instável.

    Uso::

        espia = EspiaDeThread(retorno=True)
        with patch("app.routers.x.verify_password", new=espia):
            ...
        assert espia.rodou_fora_da_thread(threading.get_ident())
    """

    def __init__(self, retorno=None):
        self.retorno = retorno
        self.threads: list[int] = []

    def __call__(self, *_args, **_kwargs):
        self.threads.append(threading.get_ident())
        return self.retorno

    @property
    def chamado(self) -> bool:
        return bool(self.threads)

    def rodou_fora_da_thread(self, thread_id: int) -> bool:
        return self.chamado and thread_id not in self.threads
