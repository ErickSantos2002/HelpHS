"""
Seeds do e2e (Playwright). NÃO entram em `app.seeds` — e isto é a regra.

`app.seeds` roda no boot de produção (start.sh). Colocar as contas de teste
lá criaria, no banco real, logins com senha em texto claro conhecida por
qualquer um que leia este repositório. Por isso elas vivem aqui, num módulo
que só o workflow de e2e chama — e que se recusa a rodar quando o ambiente é
de produção, para o dia em que alguém o chamar por engano.

Uso: python -m app.seeds_e2e   (só depois de `python -m app.seeds`)

O admin do e2e é o mesmo de `app.seeds`; aqui entra só o que os specs precisam
a mais: um cliente. Os valores são os defaults de `frontend/e2e/helpers.ts`, e
há teste garantindo que os dois lados batem.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from loguru import logger
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.models import User, UserRole, UserStatus

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

E2E_CLIENT = {
    "email": "client.e2e@healthsafety.com",
    "password": "ClientE2E@123",
    "name": "Cliente E2E",
    "company_name": "E2E Comércio Ltda",
}


def garante_que_nao_e_producao() -> None:
    """
    Fail-fast. A mensagem diz o que aconteceria se passasse.

    Avaliado antes de abrir sessão: em produção este módulo não toca no banco
    nem para ler.
    """
    if get_settings().is_production:
        raise RuntimeError(
            "seeds_e2e em ambiente de produção: isto criaria contas de teste com "
            "senha conhecida no banco real. Este módulo é só para o workflow de e2e."
        )


async def seed_e2e_client(session: AsyncSession) -> None:
    """
    Cliente já ativo, confirmado e com onboarding feito.

    Sem `onboarding_completed`, o OnboardingGuard o jogaria em /onboarding no
    primeiro login e o spec que espera /403 quebraria antes de começar.
    """
    result = await session.execute(select(User).where(User.email == E2E_CLIENT["email"]))
    if result.scalar_one_or_none():
        logger.info("E2E client already exists — skipping")
        return

    now = datetime.now(UTC)
    session.add(
        User(
            id=uuid.uuid4(),
            email=E2E_CLIENT["email"],
            name=E2E_CLIENT["name"],
            password=pwd_context.hash(E2E_CLIENT["password"]),
            role=UserRole.client,
            status=UserStatus.active,
            lgpd_consent=True,
            lgpd_consent_at=now,
            email_verified=True,
            email_verified_at=now,
            company_name=E2E_CLIENT["company_name"],
            onboarding_completed=True,
        )
    )
    logger.info(f"E2E client created: {E2E_CLIENT['email']}")


async def run_seeds_e2e() -> None:
    garante_que_nao_e_producao()
    logger.info("Starting e2e seeds...")
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await seed_e2e_client(session)
    logger.info("E2E seeds completed.")


if __name__ == "__main__":
    asyncio.run(run_seeds_e2e())
