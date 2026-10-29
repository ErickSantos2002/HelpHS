"""
A situação da conta (`PATCH /users/{id}/status`), contra um PostgreSQL de
verdade e com o login de verdade (token assinado, `get_current_user` lendo o
banco do teste).

O contrato que este módulo prende:

- a rota só alterna os dois estados operacionais, `active` e `inactive`, que
  são reversíveis; `anonymized` e qualquer outro valor dão 422 no schema;
- a conta anonimizada é TERMINAL nesta rota: nem `active`, nem `inactive` (409),
  e nada na linha muda;
- anonimizar continua sendo só o `POST /users/{id}/anonymize`, com as guardas
  dele;
- o registro de auditoria da mudança leva o status anterior e o novo;
- o filtro `GET /users?status=anonymized` é outro contrato e continua valendo.

Pula sem PostgreSQL à mão: `TEST_POSTGRES_URL` ou `pgserver`.
"""

import asyncio
import shutil
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.models import AuditAction, AuditLog, Base, User, UserRole, UserStatus
from app.schemas.user import UserStatusUpdate
from tests.test_dashboard_postgres import _sobe_postgres

# ── O schema ──────────────────────────────────────────────────


@pytest.mark.parametrize("valor", ["active", "inactive"])
def test_schema_aceita_os_dois_estados_operacionais(valor):
    assert UserStatusUpdate(status=valor).status == UserStatus(valor)


@pytest.mark.parametrize("valor", ["anonymized", "suspended", "", None])
def test_schema_recusa_anonymized_e_qualquer_outro_valor(valor):
    with pytest.raises(ValidationError):
        UserStatusUpdate(status=valor)


def test_o_contrato_publicado_lista_so_os_dois_estados():
    """O OpenAPI é o que um cliente da API lê: `anonymized` não aparece lá."""
    propriedade = UserStatusUpdate.model_json_schema()["properties"]["status"]
    assert propriedade["enum"] == ["active", "inactive"]


# ── Banco e login ─────────────────────────────────────────────


@pytest.fixture(scope="module")
def url_do_banco():
    url, recurso = _sobe_postgres()
    if url is None:
        pytest.skip("sem PostgreSQL: defina TEST_POSTGRES_URL ou instale pgserver")

    async def _monta() -> None:
        motor = create_async_engine(url)
        async with motor.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        await motor.dispose()

    asyncio.run(_monta())
    yield url

    if recurso is not None:
        servidor, pasta = recurso
        try:
            servidor.cleanup()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(pasta, ignore_errors=True)


@pytest_asyncio.fixture
async def fabrica(url_do_banco):
    motor = create_async_engine(url_do_banco)
    yield async_sessionmaker(motor, expire_on_commit=False)
    await motor.dispose()


@pytest_asyncio.fixture
async def criados(fabrica):
    """Os usuários que o teste comitou — e a faxina deles, passe ou falhe.

    O banco do CI é um só para todos os módulos: apaga só o que é deste teste,
    as auditorias antes dos usuários (`audit_logs.user_id` é FK).
    """
    ids: list[uuid.UUID] = []
    yield ids
    if not ids:
        return
    async with fabrica() as s:
        try:
            await s.execute(text("SET LOCAL lock_timeout = '10s'"))
            await s.execute(
                delete(AuditLog).where(or_(AuditLog.user_id.in_(ids), AuditLog.entity_id.in_(ids)))
            )
            await s.execute(delete(User).where(User.id.in_(ids)))
            await s.commit()
        except BaseException:
            await s.rollback()
            raise
    async with fabrica() as s:
        sobra = (
            await s.execute(select(func.count()).select_from(User).where(User.id.in_(ids)))
        ).scalar_one()
    assert sobra == 0


class _RedisVazio:
    """Só a lista de tokens revogados — nenhum está revogado."""

    async def exists(self, chave):
        return 0


@pytest.fixture(autouse=True)
def _login_de_verdade(fabrica, monkeypatch):
    async def _db():
        async with fabrica() as sessao:
            yield sessao

    async def _redis():
        return _RedisVazio()

    monkeypatch.setattr("app.core.security.get_redis", _redis)
    app.dependency_overrides[get_db] = _db
    yield
    app.dependency_overrides.clear()


def _usuario(papel: UserRole, **extra) -> User:
    ontem = datetime.now(UTC) - timedelta(days=1)
    campos = {
        "id": uuid.uuid4(),
        "name": f"Pessoa {papel.value}",
        "email": f"{uuid.uuid4().hex[:10]}@test.invalid",
        "password": "x",
        "role": papel,
        "status": UserStatus.active,
        # `ck_users_cliente_ativo_tem_telefone`: cliente ativo sem telefone nem
        # entra no banco.
        "phone": "+5581999999999",
        "department": "Setor de teste",
        "lgpd_consent": True,
        "email_verified": True,
        "onboarding_completed": True,
        "created_at": ontem,
        "updated_at": ontem,
    }
    campos.update(extra)
    return User(**campos)


async def _grava(fabrica, criados, *usuarios: User) -> None:
    criados.extend(u.id for u in usuarios)
    async with fabrica() as s:
        s.add_all(usuarios)
        await s.commit()


async def _pede(metodo: str, url: str, quem: User, **kwargs):
    token = create_access_token(quem.id, quem.role.value, quem.email)
    transporte = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://t") as c:
        return await c.request(metodo, url, headers={"Authorization": f"Bearer {token}"}, **kwargs)


async def _muda(quem: User, alvo: User, valor):
    return await _pede("PATCH", f"/api/v1/users/{alvo.id}/status", quem, json={"status": valor})


async def _linha(fabrica, alvo: User) -> dict:
    """A linha inteira, como o banco a guarda — para provar que nada mudou."""
    async with fabrica() as s:
        u = (await s.execute(select(User).where(User.id == alvo.id))).scalar_one()
        return {c.key: getattr(u, c.key) for c in User.__table__.columns}


async def _auditoria(fabrica, alvo: User, acao: AuditAction) -> list[AuditLog]:
    async with fabrica() as s:
        return list(
            (
                await s.execute(
                    select(AuditLog)
                    .where(AuditLog.entity_id == alvo.id, AuditLog.action == acao)
                    .order_by(AuditLog.created_at, AuditLog.id)
                )
            )
            .scalars()
            .all()
        )


async def _anonimiza(admin: User, alvo: User) -> None:
    r = await _pede("POST", f"/api/v1/users/{alvo.id}/anonymize", admin)
    assert r.status_code == 200, r.text


# ── active <-> inactive: os estados operacionais ──────────────


@pytest.mark.asyncio
async def test_inativar_e_reativar_seguem_permitidos_e_o_registro_leva_os_dois_status(
    fabrica, criados
):
    admin = _usuario(UserRole.admin)
    alvo = _usuario(UserRole.client)
    await _grava(fabrica, criados, admin, alvo)

    r = await _muda(admin, alvo, "inactive")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "inactive"
    r = await _muda(admin, alvo, "active")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"

    registros = await _auditoria(fabrica, alvo, AuditAction.status_change)
    assert [(a.user_id, a.old_data, a.new_data) for a in registros] == [
        (admin.id, {"status": "active"}, {"status": "inactive"}),
        (admin.id, {"status": "inactive"}, {"status": "active"}),
    ]


@pytest.mark.parametrize("valor", ["anonymized", "suspended"])
@pytest.mark.asyncio
async def test_patch_recusa_anonymized_e_valor_arbitrario_sem_mexer_na_conta(
    fabrica, criados, valor
):
    """Anonimizar por aqui só trocaria o status e deixaria nome, e-mail,
    telefone e foto intactos: o schema recusa antes do handler."""
    admin = _usuario(UserRole.admin)
    alvo = _usuario(UserRole.technician)
    await _grava(fabrica, criados, admin, alvo)
    antes = await _linha(fabrica, alvo)

    r = await _muda(admin, alvo, valor)

    assert r.status_code == 422, r.text
    assert await _linha(fabrica, alvo) == antes
    assert await _auditoria(fabrica, alvo, AuditAction.status_change) == []


# ── A conta anonimizada é terminal no PATCH ───────────────────


@pytest.mark.parametrize("papel", [UserRole.client, UserRole.technician])
@pytest.mark.parametrize("destino", ["active", "inactive"])
@pytest.mark.asyncio
async def test_conta_anonimizada_nao_sai_desse_estado_pelo_patch(fabrica, criados, papel, destino):
    """O cliente entra de propósito: a anonimizada não tem telefone, e a
    resposta tem de ser a recusa por ser anonimizada (409), não a guarda do
    telefone (422) — que nem existiria para técnico."""
    admin = _usuario(UserRole.admin)
    alvo = _usuario(papel)
    await _grava(fabrica, criados, admin, alvo)
    await _anonimiza(admin, alvo)
    antes = await _linha(fabrica, alvo)

    r = await _muda(admin, alvo, destino)

    assert r.status_code == 409, r.text
    assert await _linha(fabrica, alvo) == antes
    assert antes["status"] == UserStatus.anonymized
    assert await _auditoria(fabrica, alvo, AuditAction.status_change) == []


@pytest.mark.asyncio
async def test_anonymized_de_novo_pelo_patch_para_no_schema(fabrica, criados):
    admin = _usuario(UserRole.admin)
    alvo = _usuario(UserRole.technician)
    await _grava(fabrica, criados, admin, alvo)
    await _anonimiza(admin, alvo)
    antes = await _linha(fabrica, alvo)

    r = await _muda(admin, alvo, "anonymized")

    assert r.status_code == 422, r.text
    assert await _linha(fabrica, alvo) == antes


async def _espera_alguem_parado_na_trava(fabrica) -> None:
    """Estado observável, não espera cega."""
    for _ in range(400):
        async with fabrica() as s:
            parados = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() AND wait_event_type = 'Lock'"
                    )
                )
            ).scalar_one()
        if parados:
            return
        await asyncio.sleep(0.025)
    raise AssertionError("o PATCH não chegou a esperar pela trava")


@pytest.mark.asyncio
async def test_inativar_enquanto_a_anonimizacao_comita_recebe_409(fabrica, criados):
    """Outra transação segura a linha e a deixa `anonymized` — o que o
    `POST /anonymize` faz; o PATCH chega nesse meio-tempo. Com a trava, ele
    espera, relê `anonymized` e recusa. Sem ela, leria `active` antes e
    gravaria `inactive` POR CIMA da anonimização."""
    admin = _usuario(UserRole.admin)
    alvo = _usuario(UserRole.technician)
    await _grava(fabrica, criados, admin, alvo)

    async with fabrica() as segura:
        await segura.execute(text("SELECT 1 FROM users WHERE id = :id FOR UPDATE"), {"id": alvo.id})
        await segura.execute(
            text("UPDATE users SET status = 'anonymized' WHERE id = :id"), {"id": alvo.id}
        )
        pedido = asyncio.create_task(_muda(admin, alvo, "inactive"))
        await _espera_alguem_parado_na_trava(fabrica)
        await segura.commit()

    r = await pedido
    assert r.status_code == 409, r.text
    assert (await _linha(fabrica, alvo))["status"] == UserStatus.anonymized


# ── O POST /anonymize continua como era ───────────────────────


@pytest.mark.asyncio
async def test_post_anonymize_continua_anonimizando_e_a_segunda_vez_e_409(fabrica, criados):
    admin = _usuario(UserRole.admin)
    alvo = _usuario(UserRole.client)
    await _grava(fabrica, criados, admin, alvo)

    await _anonimiza(admin, alvo)
    linha = await _linha(fabrica, alvo)
    assert linha["status"] == UserStatus.anonymized
    assert linha["name"].startswith("Usuário Anonimizado")
    assert linha["email"].endswith("@anonymized.invalid")
    assert (linha["phone"], linha["department"], linha["avatar_url"]) == (None, None, None)
    (registro,) = await _auditoria(fabrica, alvo, AuditAction.anonymize)
    assert registro.user_id == admin.id
    # O POST não vira `status_change`: são registros diferentes.
    assert await _auditoria(fabrica, alvo, AuditAction.status_change) == []

    r = await _pede("POST", f"/api/v1/users/{alvo.id}/anonymize", admin)

    assert r.status_code == 409, r.text
    assert await _linha(fabrica, alvo) == linha
    assert len(await _auditoria(fabrica, alvo, AuditAction.anonymize)) == 1


@pytest.mark.asyncio
async def test_tecnico_continua_sem_poder_anonimizar_admin(fabrica, criados):
    tecnico = _usuario(UserRole.technician)
    alvo = _usuario(UserRole.admin)
    await _grava(fabrica, criados, tecnico, alvo)
    antes = await _linha(fabrica, alvo)

    r = await _pede("POST", f"/api/v1/users/{alvo.id}/anonymize", tecnico)
    assert r.status_code == 403, r.text
    # E o PATCH não é mais atalho para a mesma coisa.
    r = await _muda(tecnico, alvo, "anonymized")
    assert r.status_code == 422, r.text

    assert await _linha(fabrica, alvo) == antes


@pytest.mark.asyncio
async def test_o_filtro_da_listagem_continua_aceitando_anonymized(fabrica, criados):
    admin = _usuario(UserRole.admin)
    alvo = _usuario(UserRole.technician)
    await _grava(fabrica, criados, admin, alvo)
    await _anonimiza(admin, alvo)

    r = await _pede(
        "GET",
        "/api/v1/users",
        admin,
        params={"status": "anonymized", "search": str(alvo.id).replace("-", "")[:20]},
    )

    assert r.status_code == 200, r.text
    assert [u["id"] for u in r.json()["items"]] == [str(alvo.id)]
