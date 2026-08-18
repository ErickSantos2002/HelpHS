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
"""

import os
import threading

os.environ["APP_ENV"] = "testing"
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")


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
