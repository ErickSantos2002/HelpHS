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

os.environ["APP_ENV"] = "testing"
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")
