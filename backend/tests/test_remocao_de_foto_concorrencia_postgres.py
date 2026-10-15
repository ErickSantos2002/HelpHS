"""
A remoção pelo admin e o upload do dono, disputando a trava da linha no
PostgreSQL de verdade.

A sessão falsa de `test_remocao_de_foto_pelo_admin.py` encena cada ordem; aqui
duas transações reais se cruzam, e quem decide quem espera é o `FOR UPDATE`.
Cada cenário pausa um dos pedidos no ponto mais perigoso, espera o outro ficar
bloqueado na trava (medido em `pg_stat_activity`, não com `sleep`) e só então
solta o primeiro.

Pula sem PostgreSQL à mão: `TEST_POSTGRES_URL` ou `pgserver`.
"""

import asyncio
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app
from app.models.models import AuditLog, Base, User, UserRole, UserStatus
from app.services import storage
from tests.test_dashboard_postgres import _sobe_postgres

_VELHA = b"\x89PNG velha"
_NOVA = b"\x89PNG nova"
_MOTIVO = "Foto imprópria, denúncia registrada."


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


@pytest.fixture()
def disco(tmp_path):
    settings = get_settings()
    original = settings.upload_dir
    settings.upload_dir = str(tmp_path)
    yield tmp_path
    settings.upload_dir = original


@pytest.fixture(autouse=True)
def _limpa_overrides():
    yield
    app.dependency_overrides.clear()


def _usuario(papel: UserRole) -> User:
    ontem = datetime.now(UTC) - timedelta(days=1)
    return User(
        id=uuid.uuid4(),
        name=f"Pessoa {papel.value}",
        email=f"{uuid.uuid4().hex[:10]}@test.invalid",
        password="x",
        role=papel,
        status=UserStatus.active,
        # `ck_users_cliente_ativo_tem_telefone`: cliente ativo sem telefone nem
        # entra no banco.
        phone="+5581999999999",
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
        created_at=ontem,
        updated_at=ontem,
    )


async def _prepara(fabrica, disco):
    """Um admin e um cliente com foto legítima gravada no disco e no banco."""
    admin = _usuario(UserRole.admin)
    dono = _usuario(UserRole.client)
    dono.avatar_url = f"avatars/{dono.id}.png"
    arquivo = disco / dono.avatar_url
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_bytes(_VELHA)
    async with fabrica() as s:
        s.add_all([admin, dono])
        await s.commit()

    async def _db():
        async with fabrica() as sessao:
            yield sessao

    atores = {
        str(admin.id): SimpleNamespace(id=admin.id, role=UserRole.admin),
        str(dono.id): SimpleNamespace(id=dono.id, role=UserRole.client),
    }

    def _ator(request: Request):
        return atores[request.headers["x-ator"]]

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _ator
    return admin, dono, arquivo


async def _remove(admin, dono):
    transporte = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://t") as cliente:
        return await cliente.post(
            f"/api/v1/users/{dono.id}/avatar/remove",
            # A versão que a tela do admin tinha: a de antes de qualquer upload.
            json={"justification": _MOTIVO, "expected_updated_at": dono.updated_at.isoformat()},
            headers={"x-ator": str(admin.id)},
        )


async def _envia(dono):
    transporte = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://t") as cliente:
        return await cliente.post(
            "/api/v1/users/me/avatar",
            files={"file": ("nova.png", _NOVA, "image/png")},
            headers={"x-ator": str(dono.id)},
        )


async def _espera_alguem_bloqueado(fabrica, segundos: float = 15.0) -> None:
    """Até haver uma transação parada esperando trava — prova, não palpite."""
    limite = asyncio.get_running_loop().time() + segundos
    while asyncio.get_running_loop().time() < limite:
        async with fabrica() as s:
            parados = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE wait_event_type = 'Lock' AND datname = current_database()"
                    )
                )
            ).scalar_one()
        if parados:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("ninguém ficou bloqueado na trava da linha")


async def _estado(fabrica, dono):
    async with fabrica() as s:
        linha = (await s.execute(select(User).where(User.id == dono.id))).scalar_one()
        auditorias = (
            (await s.execute(select(AuditLog).where(AuditLog.entity_id == dono.id))).scalars().all()
        )
    remocoes = [
        a for a in auditorias if (a.new_data or {}).get("operacao") == "remocao_de_foto_pelo_admin"
    ]
    return linha.avatar_url, remocoes


def _sobras(disco):
    return sorted(p.name for p in disco.rglob("*") if p.is_file())


@pytest.mark.asyncio
async def test_remocao_sozinha_grava_auditoria_no_banco_real(fabrica, disco):
    admin, dono, arquivo = await _prepara(fabrica, disco)

    resposta = await _remove(admin, dono)

    assert resposta.status_code == 200, resposta.text
    avatar, remocoes = await _estado(fabrica, dono)
    assert avatar is None
    assert not arquivo.exists()
    assert _sobras(disco) == []
    [auditoria] = remocoes
    assert auditoria.user_id == admin.id
    assert auditoria.new_data["justificativa"] == _MOTIVO


@pytest.mark.asyncio
async def test_versao_que_a_propria_api_devolveu_volta_e_casa(fabrica, disco):
    """O token de versão faz a viagem inteira: banco → JSON da API → corpo do
    pedido → pydantic → comparação. Com microssegundos diferentes de zero, que
    é onde um corte para milissegundos (ou um formato sem fração) quebraria a
    igualdade e daria 409 para sempre."""
    admin, dono, arquivo = await _prepara(fabrica, disco)
    async with fabrica() as s:
        await s.execute(
            text("UPDATE users SET updated_at = :v WHERE id = :id"),
            {"v": datetime(2026, 10, 14, 9, 30, 15, 123457, tzinfo=UTC), "id": dono.id},
        )
        await s.commit()

    transporte = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://t") as cliente:
        lido = await cliente.get(f"/api/v1/users/{dono.id}", headers={"x-ator": str(admin.id)})
        assert lido.status_code == 200, lido.text
        versao = lido.json()["updated_at"]
        assert "123457" in versao

        resposta = await cliente.post(
            f"/api/v1/users/{dono.id}/avatar/remove",
            json={"justification": _MOTIVO, "expected_updated_at": versao},
            headers={"x-ator": str(admin.id)},
        )

    assert resposta.status_code == 200, resposta.text
    avatar, remocoes = await _estado(fabrica, dono)
    assert avatar is None
    assert not arquivo.exists()
    assert len(remocoes) == 1


@pytest.mark.asyncio
async def test_upload_em_andamento_faz_a_remocao_esperar_e_recusar(fabrica, disco, monkeypatch):
    """O upload gravou o arquivo novo e ainda não comitou. Sem a trava no
    upload, o admin isolaria e apagaria a foto nova, e o commit do upload
    apontaria a linha para o vazio. Com ela, o admin espera, vê a linha
    alterada depois do pedido dele e devolve 409 sem tocar em nada."""
    admin, dono, arquivo = await _prepara(fabrica, disco)
    gravou = asyncio.Event()
    solta = asyncio.Event()
    real = storage.upload_file

    async def _grava_e_pausa(*args, **kwargs):
        chave = await real(*args, **kwargs)
        gravou.set()
        await solta.wait()
        return chave

    monkeypatch.setattr(storage, "upload_file", _grava_e_pausa)

    upload = asyncio.create_task(_envia(dono))
    await asyncio.wait_for(gravou.wait(), 15)
    remocao = asyncio.create_task(_remove(admin, dono))
    await _espera_alguem_bloqueado(fabrica)
    solta.set()
    resposta_upload, resposta_remocao = await asyncio.gather(upload, remocao)

    assert resposta_upload.status_code == 200, resposta_upload.text
    assert resposta_remocao.status_code == 409, resposta_remocao.text
    avatar, remocoes = await _estado(fabrica, dono)
    assert avatar == f"avatars/{dono.id}.png"
    assert arquivo.read_bytes() == _NOVA
    assert _sobras(disco) == [arquivo.name]
    assert remocoes == []


@pytest.mark.asyncio
async def test_upload_que_chega_durante_a_remocao_espera_e_sobrevive(fabrica, disco, monkeypatch):
    """O admin já isolou o arquivo e ainda não comitou; o dono envia uma foto
    nova na MESMA chave. O upload espera a trava, grava depois do commit da
    remoção — e a exclusão física do admin, que vem por último, só alcança o
    nome isolado."""
    admin, dono, arquivo = await _prepara(fabrica, disco)
    isolou = asyncio.Event()
    solta = asyncio.Event()
    real = storage.isola_arquivo

    async def _isola_e_pausa(*args, **kwargs):
        isolado = await real(*args, **kwargs)
        isolou.set()
        await solta.wait()
        return isolado

    monkeypatch.setattr(storage, "isola_arquivo", _isola_e_pausa)

    remocao = asyncio.create_task(_remove(admin, dono))
    await asyncio.wait_for(isolou.wait(), 15)
    upload = asyncio.create_task(_envia(dono))
    await _espera_alguem_bloqueado(fabrica)
    solta.set()
    resposta_remocao, resposta_upload = await asyncio.gather(remocao, upload)

    assert resposta_remocao.status_code == 200, resposta_remocao.text
    assert resposta_upload.status_code == 200, resposta_upload.text
    avatar, remocoes = await _estado(fabrica, dono)
    assert avatar == f"avatars/{dono.id}.png"
    assert arquivo.read_bytes() == _NOVA
    assert _sobras(disco) == [arquivo.name]
    assert len(remocoes) == 1
