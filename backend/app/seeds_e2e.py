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

Uso: python -m app.seeds_e2e --ece01

Com `--ece01` entra TAMBÉM o cenário dos specs `ece01-*.spec.ts` (equipamento
compartilhado por empresa): um grupo, duas empresas, dois clientes da mesma
empresa, um produto e quatro equipamentos. É opcional de propósito — sem a
opção o banco do e2e nasce exatamente como antes, e os specs das outras
frentes não passam a contar com dado que não pediram.
"""

import asyncio
import sys
import uuid
from datetime import UTC, datetime

from loguru import logger
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.models import Company, Equipment, Group, Product, User, UserRole, UserStatus

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

E2E_CLIENT = {
    "email": "client.e2e@healthsafety.com",
    "password": "ClientE2E@123",
    "name": "Cliente E2E",
    "company_name": "E2E Comércio Ltda",
}

# ── Cenário da ECE-01 ─────────────────────────────────────────
#
# Tudo fictício e com "ECE01" no nome, para o spec achar o que é dele sem
# depender do que outro spec criou. Os nomes e as credenciais são os mesmos de
# `frontend/e2e/ece01.ts` — há teste garantindo que os dois lados batem.
#
# Ana e Bruno são colegas: os dois na Alfa. É o que o compartilhamento exige.

E2E_ECE01_GRUPO = "ECE01 Grupo de Teste"
E2E_ECE01_EMPRESA_ALFA = "ECE01 Alfa Ltda"
E2E_ECE01_EMPRESA_BETA = "ECE01 Beta Ltda"
E2E_ECE01_PRODUTO = "ECE01 Produto"

E2E_ECE01_ANA = {
    "email": "ana.ece01.e2e@healthsafety.com",
    "password": "AnaEce01@123",
    "name": "Ana ECE01",
    "phone": "+5581999990001",
}
E2E_ECE01_BRUNO = {
    "email": "bruno.ece01.e2e@healthsafety.com",
    "password": "BrunoEce01@123",
    "name": "Bruno ECE01",
    "phone": "+5581999990002",
}

# Um aparelho por situação que a tela precisa distinguir.
E2E_ECE01_APARELHO_DA_ANA = "ECE01 Aparelho da Ana"  # da Ana, na Alfa
E2E_ECE01_APARELHO_DO_BRUNO = "ECE01 Aparelho do Bruno"  # do Bruno, na Alfa
# Da Ana, mas na Beta: a empresa do equipamento diverge da do responsável, e o
# Bruno não o enxerga nem com o compartilhamento ligado.
E2E_ECE01_APARELHO_DIVERGENTE = "ECE01 Aparelho divergente"
# Sem responsável e sem empresa: é o que o filtro "Sem empresa" tem de trazer.
E2E_ECE01_APARELHO_A_CLASSIFICAR = "ECE01 Aparelho a classificar"


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
            # Cliente ativo precisa de telefone. Este seed monta o objeto
            # SQLAlchemy direto, sem passar por Pydantic, então nada aqui
            # falharia hoje — está explícito porque a conta que o e2e cria é
            # a única conta de cliente que o projeto cria por código, e ela
            # tem de nascer já no formato que a regra exige.
            phone="+5581999990000",
            lgpd_consent=True,
            lgpd_consent_at=now,
            email_verified=True,
            email_verified_at=now,
            company_name=E2E_CLIENT["company_name"],
            onboarding_completed=True,
        )
    )
    logger.info(f"E2E client created: {E2E_CLIENT['email']}")


def _cliente_da_ece01(dados: dict[str, str], empresa: Company, agora: datetime) -> User:
    """Cliente ativo, confirmado, com onboarding feito e VINCULADO à empresa."""
    return User(
        id=uuid.uuid4(),
        email=dados["email"],
        name=dados["name"],
        password=pwd_context.hash(dados["password"]),
        role=UserRole.client,
        status=UserStatus.active,
        phone=dados["phone"],
        lgpd_consent=True,
        lgpd_consent_at=agora,
        email_verified=True,
        email_verified_at=agora,
        company_name=empresa.name,
        # O vínculo oficial — é ele, e não `company_name`, que faz de dois
        # clientes colegas.
        company_id=empresa.id,
        onboarding_completed=True,
    )


async def seed_e2e_ece01(session: AsyncSession) -> None:
    """
    O cenário dos specs `ece01-*.spec.ts`. Tudo ou nada: o grupo é a marca de
    que já rodou, e o resto nasce na mesma transação.

    Não liga nem desliga o compartilhamento: isso é `EQUIPAMENTO_POR_EMPRESA`,
    que o workflow define por execução. O dado é o mesmo nos dois modos — o
    que muda é o que cada cliente enxerga dele.
    """
    result = await session.execute(select(Group).where(Group.name == E2E_ECE01_GRUPO))
    if result.scalar_one_or_none():
        logger.info("E2E ECE-01 scenario already exists — skipping")
        return

    agora = datetime.now(UTC)
    grupo = Group(id=uuid.uuid4(), name=E2E_ECE01_GRUPO)
    alfa = Company(id=uuid.uuid4(), group_id=grupo.id, name=E2E_ECE01_EMPRESA_ALFA)
    beta = Company(id=uuid.uuid4(), group_id=grupo.id, name=E2E_ECE01_EMPRESA_BETA)
    ana = _cliente_da_ece01(E2E_ECE01_ANA, alfa, agora)
    bruno = _cliente_da_ece01(E2E_ECE01_BRUNO, alfa, agora)
    produto = Product(id=uuid.uuid4(), name=E2E_ECE01_PRODUTO, is_active=True)

    def aparelho(nome: str, serie: str, dono: User | None, empresa: Company | None) -> Equipment:
        return Equipment(
            id=uuid.uuid4(),
            product_id=produto.id,
            name=nome,
            serial_number=serie,
            is_active=True,
            owner_id=dono.id if dono else None,
            company_id=empresa.id if empresa else None,
        )

    # Um `flush` por degrau da hierarquia: os ids nascem aqui, sem
    # relacionamento que dê a ordem à unidade de trabalho, e a FK de quem vem
    # depois precisa achar a linha de quem veio antes.
    for degrau in (
        [grupo],
        [alfa, beta],
        [ana, bruno, produto],
        [
            aparelho(E2E_ECE01_APARELHO_DA_ANA, "ECE01-ANA", ana, alfa),
            aparelho(E2E_ECE01_APARELHO_DO_BRUNO, "ECE01-BRUNO", bruno, alfa),
            aparelho(E2E_ECE01_APARELHO_DIVERGENTE, "ECE01-DIVERGE", ana, beta),
            aparelho(E2E_ECE01_APARELHO_A_CLASSIFICAR, "ECE01-CLASSIFICAR", None, None),
        ],
    ):
        for objeto in degrau:
            session.add(objeto)
        await session.flush()
    logger.info("E2E ECE-01 scenario created")


async def run_seeds_e2e(*, ece01: bool = False) -> None:
    garante_que_nao_e_producao()
    logger.info("Starting e2e seeds...")
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await seed_e2e_client(session)
            if ece01:
                await seed_e2e_ece01(session)
    logger.info("E2E seeds completed.")


if __name__ == "__main__":
    asyncio.run(run_seeds_e2e(ece01="--ece01" in sys.argv[1:]))
