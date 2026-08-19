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
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")

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
