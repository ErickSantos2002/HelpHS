"""
A autorização da foto para outras pessoas, contra um PostgreSQL de verdade.

O que só o banco prova, e por isso mora aqui e não em dublê:

- o padrão é falso para conta nova por ORM e por INSERT cru (`server_default`);
- cada papel muda só a própria escolha, e nada do corpo escolhe outra conta;
- PATCH genérico, edição pelo admin, onboarding, upload e aceite da Política
  não mexem na escolha;
- estado e evento vão no mesmo commit — se o evento não entra, o estado também
  não fica;
- repetir não duplica, e pedidos simultâneos se enfileiram na trava da linha
  sem deixar evento fantasma;
- revogar não depende de texto vigente nem de aceite novo;
- o que o WebSocket relê é o remetente ATUAL, mesmo com uma cópia velha dele
  no mapa de identidade da sessão;
- excluir a conta desvincula os eventos em vez de apagá-los, e anonimizar
  segue funcionando.

Versões e textos aqui são de TESTE e dizem isso no nome. Nenhum é o texto que
iria a produção.

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
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, get_current_user
from app.main import app
from app.models.models import (
    AuditAction,
    AuditLog,
    AvatarVisibilityEvent,
    Base,
    ChatMessage,
    LgpdConsent,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
)
from app.services import exibicao_da_foto
from app.utils.avatar import pode_aparecer_para_terceiros
from tests.test_dashboard_postgres import _sobe_postgres

_VERSAO_DE_TESTE = "TESTE-AVISO-01"
_ROTA = "/api/v1/users/me/avatar/exibicao"


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
    """Usuários e chamados que o teste comitou — e a faxina deles, passe ou falhe.

    O banco do CI é um só para todos os módulos. Apaga só o que é deste teste,
    filtrado pelos ids, na ordem das FKs. Os eventos saem pelo `user_id`
    ANTES dos usuários: depois, o `SET NULL` os deixaria sem dono e sem como
    achá-los.
    """
    ids: dict[str, list[uuid.UUID]] = {"usuarios": [], "chamados": []}
    yield ids
    usuarios, chamados = ids["usuarios"], ids["chamados"]
    async with fabrica() as s:
        try:
            await s.execute(text("SET LOCAL lock_timeout = '10s'"))
            if chamados:
                await s.execute(delete(ChatMessage).where(ChatMessage.ticket_id.in_(chamados)))
                await s.execute(delete(Ticket).where(Ticket.id.in_(chamados)))
            if usuarios:
                await s.execute(
                    delete(AvatarVisibilityEvent).where(AvatarVisibilityEvent.user_id.in_(usuarios))
                )
                await s.execute(delete(LgpdConsent).where(LgpdConsent.user_id.in_(usuarios)))
                await s.execute(
                    delete(AuditLog).where(
                        or_(AuditLog.user_id.in_(usuarios), AuditLog.entity_id.in_(usuarios))
                    )
                )
                await s.execute(delete(User).where(User.id.in_(usuarios)))
            await s.commit()
        except BaseException:
            await s.rollback()
            raise
    if usuarios:
        async with fabrica() as s:
            sobra = (
                await s.execute(select(func.count()).select_from(User).where(User.id.in_(usuarios)))
            ).scalar_one()
        assert sobra == 0


@pytest.fixture(autouse=True)
def _limpa_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def aviso_de_teste(monkeypatch):
    """Um texto de TESTE vigente — nunca a minuta, nunca um texto de produção."""
    aviso = exibicao_da_foto.Aviso(
        versao=_VERSAO_DE_TESTE,
        rotulo="TESTE — rótulo da autorização",
        # Texto de teste nunca é aprovado: em produção ele não vale.
        aprovado=False,
        explicacao_cliente=("TESTE — explicação para cliente",),
        explicacao_equipe=("TESTE — explicação para a equipe",),
    )
    monkeypatch.setitem(exibicao_da_foto.AVISOS, _VERSAO_DE_TESTE, aviso)
    monkeypatch.setattr(get_settings(), "avatar_aviso_exibicao_versao", _VERSAO_DE_TESTE)
    return aviso


@pytest.fixture
def sem_aviso(monkeypatch):
    monkeypatch.setattr(get_settings(), "avatar_aviso_exibicao_versao", None)


def _usuario(papel: UserRole, **extra) -> User:
    ontem = datetime.now(UTC) - timedelta(days=1)
    campos = {
        "id": uuid.uuid4(),
        "name": f"Pessoa {papel.value}",
        "email": f"{uuid.uuid4().hex[:10]}@test.invalid",
        "password": "x",
        "role": papel,
        "status": UserStatus.active,
        "phone": "+5581999999999",
        "lgpd_consent": True,
        "email_verified": True,
        "onboarding_completed": True,
        "created_at": ontem,
        "updated_at": ontem,
    }
    campos.update(extra)
    return User(**campos)


async def _grava(fabrica, criados, *objetos) -> None:
    for o in objetos:
        if isinstance(o, User):
            criados["usuarios"].append(o.id)
        elif isinstance(o, Ticket):
            criados["chamados"].append(o.id)
    async with fabrica() as s:
        s.add_all(objetos)
        await s.commit()


def _atende_como(fabrica, *usuarios: User) -> None:
    """Liga a app ao banco do teste; o cabeçalho `x-ator` diz quem pede."""

    async def _db():
        async with fabrica() as sessao:
            yield sessao

    atores = {str(u.id): SimpleNamespace(id=u.id, role=u.role, status=u.status) for u in usuarios}

    def _ator(request: Request):
        return atores[request.headers["x-ator"]]

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _ator


async def _pede(metodo: str, url: str, ator: User, **kwargs):
    transporte = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://t") as c:
        return await c.request(metodo, url, headers={"x-ator": str(ator.id)}, **kwargs)


async def _estado(fabrica, usuario: User) -> tuple[bool, list[AvatarVisibilityEvent]]:
    async with fabrica() as s:
        visivel = (
            await s.execute(select(User.avatar_visivel_a_terceiros).where(User.id == usuario.id))
        ).scalar_one()
        eventos = (
            (
                await s.execute(
                    select(AvatarVisibilityEvent)
                    .where(AvatarVisibilityEvent.user_id == usuario.id)
                    .order_by(AvatarVisibilityEvent.registrado_em, AvatarVisibilityEvent.id)
                )
            )
            .scalars()
            .all()
        )
    return visivel, list(eventos)


def _autoriza(versao: str | None = _VERSAO_DE_TESTE) -> dict:
    return {"autorizada": True, "versao_aviso": versao}


# ── O padrão é desligado ──────────────────────────────────────


@pytest.mark.asyncio
async def test_conta_nova_por_orm_e_por_insert_cru_nasce_sem_autorizacao(fabrica, criados):
    pela_orm = _usuario(UserRole.client, avatar_url=None)
    await _grava(fabrica, criados, pela_orm)

    crua = uuid.uuid4()
    criados["usuarios"].append(crua)
    async with fabrica() as s:
        await s.execute(
            text(
                "INSERT INTO users (id, name, email, password, role, status, phone,"
                " lgpd_consent, email_verified, mfa_enabled, onboarding_completed,"
                " ai_enabled, created_at, updated_at)"
                " VALUES (:id, 'Crua', :e, 'x', 'client', 'active', '+5581999999999',"
                " true, true, false, true, true, now(), now())"
            ),
            {"id": crua, "e": f"{crua.hex[:10]}@test.invalid"},
        )
        await s.commit()
        valores = (
            (
                await s.execute(
                    select(User.avatar_visivel_a_terceiros).where(User.id.in_([pela_orm.id, crua]))
                )
            )
            .scalars()
            .all()
        )
    assert valores == [False, False]


@pytest.mark.parametrize("papel", list(UserRole))
@pytest.mark.asyncio
async def test_a_leitura_comeca_desligada_e_traz_o_texto_do_servidor(
    papel, fabrica, criados, aviso_de_teste
):
    eu = _usuario(papel, avatar_url=None)
    await _grava(fabrica, criados, eu)
    _atende_como(fabrica, eu)

    r = await _pede("GET", _ROTA, eu)

    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["autorizada"] is False
    assert corpo["disponivel"] is True
    assert corpo["aviso"]["versao"] == _VERSAO_DE_TESTE
    esperado = (
        aviso_de_teste.explicacao_cliente
        if papel == UserRole.client
        else aviso_de_teste.explicacao_equipe
    )
    assert corpo["aviso"]["explicacao"] == list(esperado)


# ── Autorizar e revogar, cada um na própria conta ─────────────


@pytest.mark.parametrize("papel", list(UserRole))
@pytest.mark.asyncio
async def test_cada_papel_autoriza_e_revoga_so_a_propria_escolha(
    papel, fabrica, criados, aviso_de_teste
):
    eu = _usuario(papel)
    vizinho = _usuario(papel)
    await _grava(fabrica, criados, eu, vizinho)
    _atende_como(fabrica, eu, vizinho)

    r = await _pede("PUT", _ROTA, eu, json=_autoriza())
    assert r.status_code == 200, r.text
    assert r.json()["autorizada"] is True

    visivel, eventos = await _estado(fabrica, eu)
    assert visivel is True
    assert [(e.evento, e.versao_aviso, e.origem) for e in eventos] == [
        ("autorizacao", _VERSAO_DE_TESTE, "alteracao_propria")
    ]
    assert eventos[0].ip == "127.0.0.1"

    r = await _pede("PUT", _ROTA, eu, json={"autorizada": False})
    assert r.status_code == 200, r.text
    assert r.json()["autorizada"] is False

    visivel, eventos = await _estado(fabrica, eu)
    assert visivel is False
    assert [e.evento for e in eventos] == ["autorizacao", "revogacao"]
    # A revogação não reescreve a autorização anterior.
    assert eventos[0].versao_aviso == _VERSAO_DE_TESTE

    assert await _estado(fabrica, vizinho) == (False, [])


@pytest.mark.parametrize(
    "corpo",
    [
        {"autorizada": True, "versao_aviso": _VERSAO_DE_TESTE, "user_id": "{vizinho}"},
        {"autorizada": True, "versao_aviso": _VERSAO_DE_TESTE, "ip": "10.0.0.1"},
        {"autorizada": True, "versao_aviso": _VERSAO_DE_TESTE, "registrado_em": "2020-01-01"},
        {"autorizada": True, "versao_aviso": _VERSAO_DE_TESTE, "avatar_url": "avatars/x.png"},
        {"autorizada": "true", "versao_aviso": _VERSAO_DE_TESTE},
        {"autorizada": 1, "versao_aviso": _VERSAO_DE_TESTE},
        {"versao_aviso": _VERSAO_DE_TESTE},
    ],
)
@pytest.mark.asyncio
async def test_o_corpo_nao_escolhe_conta_data_ip_nem_coage_o_estado(
    corpo, fabrica, criados, aviso_de_teste
):
    eu = _usuario(UserRole.client)
    vizinho = _usuario(UserRole.client)
    await _grava(fabrica, criados, eu, vizinho)
    _atende_como(fabrica, eu, vizinho)
    corpo = {
        k: (v.format(vizinho=vizinho.id) if isinstance(v, str) else v) for k, v in corpo.items()
    }

    r = await _pede("PUT", _ROTA, eu, json=corpo)

    assert r.status_code == 422, r.text
    assert await _estado(fabrica, eu) == (False, [])
    assert await _estado(fabrica, vizinho) == (False, [])


@pytest.mark.parametrize("versao", [None, "", "MINUTA-2026-10-21", "outra", _VERSAO_DE_TESTE + "x"])
@pytest.mark.asyncio
async def test_versao_que_nao_e_a_vigente_nao_fabrica_autorizacao(
    versao, fabrica, criados, aviso_de_teste
):
    eu = _usuario(UserRole.technician)
    await _grava(fabrica, criados, eu)
    _atende_como(fabrica, eu)

    r = await _pede("PUT", _ROTA, eu, json=_autoriza(versao))

    assert r.status_code == 409, r.text
    assert await _estado(fabrica, eu) == (False, [])


@pytest.mark.asyncio
async def test_sem_texto_vigente_ninguem_autoriza_mas_revogar_funciona(fabrica, criados, sem_aviso):
    eu = _usuario(UserRole.client, avatar_visivel_a_terceiros=True)
    await _grava(fabrica, criados, eu)
    _atende_como(fabrica, eu)

    r = await _pede("GET", _ROTA, eu)
    assert r.json() == {"autorizada": True, "disponivel": False, "aviso": None}

    # Autorizar exige o texto vigente SEMPRE, até para repetir: a recusa vem
    # antes de olhar o estado, e não muda nada.
    r = await _pede("PUT", _ROTA, eu, json=_autoriza("MINUTA-2026-10-21"))
    assert r.status_code == 409, r.text
    assert await _estado(fabrica, eu) == (True, [])

    r = await _pede("PUT", _ROTA, eu, json={"autorizada": False})
    assert r.status_code == 200, r.text
    visivel, eventos = await _estado(fabrica, eu)
    assert visivel is False
    assert [(e.evento, e.versao_aviso) for e in eventos] == [("revogacao", None)]

    r = await _pede("PUT", _ROTA, eu, json=_autoriza("MINUTA-2026-10-21"))
    assert r.status_code == 409, r.text
    assert (await _estado(fabrica, eu))[0] is False


@pytest.mark.asyncio
async def test_revogar_nao_exige_aceite_novo_nem_o_texto_atual(fabrica, criados, aviso_de_teste):
    """Quem autorizou numa versão revoga mesmo depois de o texto ter mudado."""
    eu = _usuario(UserRole.client, avatar_visivel_a_terceiros=True, lgpd_consent=False)
    await _grava(fabrica, criados, eu)
    _atende_como(fabrica, eu)

    r = await _pede("PUT", _ROTA, eu, json={"autorizada": False, "versao_aviso": "VERSAO-ANTIGA"})

    assert r.status_code == 200, r.text
    visivel, eventos = await _estado(fabrica, eu)
    assert visivel is False
    # A tela não confirmou o texto vigente: o registro não afirma que confirmou.
    assert [(e.evento, e.versao_aviso) for e in eventos] == [("revogacao", None)]


# ── Repetição e concorrência ──────────────────────────────────


@pytest.mark.asyncio
async def test_repetir_a_mesma_escolha_nao_gera_outro_evento(fabrica, criados, aviso_de_teste):
    eu = _usuario(UserRole.admin)
    await _grava(fabrica, criados, eu)
    _atende_como(fabrica, eu)

    for _ in range(3):
        r = await _pede("PUT", _ROTA, eu, json=_autoriza())
        assert r.status_code == 200, r.text
    for _ in range(2):
        r = await _pede("PUT", _ROTA, eu, json={"autorizada": False})
        assert r.status_code == 200, r.text

    visivel, eventos = await _estado(fabrica, eu)
    assert visivel is False
    assert [e.evento for e in eventos] == ["autorizacao", "revogacao"]


@pytest.mark.asyncio
async def test_pedidos_iguais_simultaneos_gravam_um_evento_so(fabrica, criados, aviso_de_teste):
    eu = _usuario(UserRole.client)
    await _grava(fabrica, criados, eu)
    _atende_como(fabrica, eu)

    respostas = await asyncio.gather(*(_pede("PUT", _ROTA, eu, json=_autoriza()) for _ in range(8)))

    assert [r.status_code for r in respostas] == [200] * 8
    assert all(r.json()["autorizada"] is True for r in respostas)
    visivel, eventos = await _estado(fabrica, eu)
    assert visivel is True
    assert [e.evento for e in eventos] == ["autorizacao"]


@pytest.mark.asyncio
async def test_pedidos_opostos_simultaneos_deixam_estado_e_historico_coerentes(
    fabrica, criados, aviso_de_teste
):
    """Liga e desliga ao mesmo tempo, várias vezes: o histórico alterna, e o
    último evento é o estado gravado. Evento repetido seguido seria um pedido
    que gravou sem ver o que o anterior tinha gravado."""
    eu = _usuario(UserRole.technician)
    await _grava(fabrica, criados, eu)
    _atende_como(fabrica, eu)

    corpos = [_autoriza() if i % 2 == 0 else {"autorizada": False} for i in range(12)]
    respostas = await asyncio.gather(*(_pede("PUT", _ROTA, eu, json=c) for c in corpos))

    assert [r.status_code for r in respostas] == [200] * 12
    visivel, eventos = await _estado(fabrica, eu)
    tipos = [e.evento for e in eventos]
    assert tipos, "nenhum evento gravado"
    assert tipos[0] == "autorizacao"
    assert all(a != b for a, b in zip(tipos, tipos[1:])), tipos
    assert visivel is (tipos[-1] == "autorizacao")


# ── Atomicidade ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_se_o_evento_nao_entra_o_estado_tambem_nao_fica(
    fabrica, criados, aviso_de_teste, monkeypatch
):
    """Um evento que o CHECK do banco recusa derruba o commit inteiro."""
    eu = _usuario(UserRole.client)
    await _grava(fabrica, criados, eu)
    _atende_como(fabrica, eu)
    monkeypatch.setattr(exibicao_da_foto, "ORIGEM_ALTERACAO_PROPRIA", "origem-invalida")

    r = await _pede("PUT", _ROTA, eu, json=_autoriza())

    assert r.status_code == 500
    assert await _estado(fabrica, eu) == (False, [])


@pytest.mark.asyncio
async def test_o_banco_recusa_autorizacao_sem_o_texto_apresentado(fabrica, criados):
    eu = _usuario(UserRole.client)
    await _grava(fabrica, criados, eu)
    async with fabrica() as s:
        s.add(
            AvatarVisibilityEvent(
                user_id=eu.id, evento="autorizacao", versao_aviso=None, origem="alteracao_propria"
            )
        )
        with pytest.raises(Exception, match="ck_avatar_visibility_events_autorizacao_tem_aviso"):
            await s.commit()


# ── Outros caminhos não mexem na escolha ──────────────────────


@pytest.mark.asyncio
async def test_patch_generico_onboarding_e_edicao_do_admin_nao_mexem_na_escolha(
    fabrica, criados, aviso_de_teste
):
    eu = _usuario(UserRole.client, onboarding_completed=False)
    admin = _usuario(UserRole.admin)
    autorizado = _usuario(UserRole.client, avatar_visivel_a_terceiros=True)
    await _grava(fabrica, criados, eu, admin, autorizado)
    _atende_como(fabrica, eu, admin, autorizado)
    ligar = {"avatar_visivel_a_terceiros": True, "autorizada": True}

    r = await _pede("PATCH", "/api/v1/users/me", eu, json={"name": "Novo Nome", **ligar})
    assert r.status_code == 200, r.text
    r = await _pede("PATCH", f"/api/v1/users/{eu.id}", eu, json={"department": "TI", **ligar})
    assert r.status_code == 200, r.text
    r = await _pede(
        "PATCH",
        "/api/v1/users/me/onboarding",
        eu,
        json={
            "company_name": "Empresa",
            "cnpj": "11.222.333/0001-81",
            "company_cep": "50000000",
            **ligar,
        },
    )
    assert r.status_code == 200, r.text
    r = await _pede("PATCH", f"/api/v1/users/{eu.id}", admin, json={"name": "Pelo Admin", **ligar})
    assert r.status_code == 200, r.text
    # Trocar o papel não liga nem desliga nada.
    r = await _pede(
        "PATCH",
        f"/api/v1/users/{autorizado.id}",
        admin,
        json={"role": "technician", "avatar_visivel_a_terceiros": False},
    )
    assert r.status_code == 200, r.text

    assert await _estado(fabrica, eu) == (False, [])
    assert await _estado(fabrica, autorizado) == (True, [])
    assert "avatar_visivel_a_terceiros" not in r.json()


@pytest.mark.asyncio
async def test_admin_criando_conta_nao_autoriza_por_ela(fabrica, criados, aviso_de_teste):
    admin = _usuario(UserRole.admin)
    await _grava(fabrica, criados, admin)
    _atende_como(fabrica, admin)

    r = await _pede(
        "POST",
        "/api/v1/users",
        admin,
        json={
            "name": "Conta Nova",
            # O cadastro valida o domínio, e `.invalid` é recusado lá.
            "email": f"{uuid.uuid4().hex[:10]}@teste.com",
            "password": "Senha1234",
            "role": "client",
            "phone": "+5581999999999",
            # Falso de propósito: com `true`, esta rota dá 500 no PostgreSQL
            # desde antes da Fase 3B — o aceite é inserido antes do usuário e
            # bate na FK. Reproduzido em 21/10/2026 sobre a main e157034, fora
            # deste diff, e relatado em vez de corrigido aqui.
            "lgpd_consent": False,
            "avatar_visivel_a_terceiros": True,
        },
    )

    assert r.status_code == 201, r.text
    nova = await _usuario_por_id(fabrica, uuid.UUID(r.json()["id"]))
    criados["usuarios"].append(nova.id)
    assert nova.avatar_visivel_a_terceiros is False


async def _usuario_por_id(fabrica, uid: uuid.UUID) -> User:
    async with fabrica() as s:
        return (await s.execute(select(User).where(User.id == uid))).scalar_one()


@pytest.mark.asyncio
async def test_aceite_da_politica_e_upload_nao_ativam_a_escolha(
    fabrica, criados, aviso_de_teste, tmp_path, monkeypatch
):
    eu = _usuario(UserRole.client, lgpd_consent=False, avatar_url=None)
    await _grava(fabrica, criados, eu)
    _atende_como(fabrica, eu)
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))

    r = await _pede("PATCH", "/api/v1/users/me/lgpd-consent", eu, json={"lgpd_consent": True})
    assert r.status_code == 200, r.text
    r = await _pede(
        "POST", "/api/v1/users/me/avatar", eu, files={"file": ("f.png", b"\x89PNG", "image/png")}
    )
    assert r.status_code == 200, r.text
    assert r.json()["avatar_url"]

    assert await _estado(fabrica, eu) == (False, [])


@pytest.mark.asyncio
async def test_trocar_e_remover_a_foto_nao_desligam_quem_autorizou(
    fabrica, criados, aviso_de_teste, tmp_path, monkeypatch
):
    """A escolha é sobre a foto ATUAL do perfil, não sobre um arquivo."""
    eu = _usuario(UserRole.technician, avatar_url=None)
    await _grava(fabrica, criados, eu)
    _atende_como(fabrica, eu)
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    r = await _pede("PUT", _ROTA, eu, json=_autoriza())
    assert r.status_code == 200

    for nome in ("a.png", "b.png"):
        r = await _pede(
            "POST", "/api/v1/users/me/avatar", eu, files={"file": (nome, b"\x89PNG", "image/png")}
        )
        assert r.status_code == 200, r.text
    r = await _pede("DELETE", "/api/v1/users/me/avatar", eu)
    assert r.status_code == 204, r.text

    visivel, eventos = await _estado(fabrica, eu)
    assert visivel is True
    assert [e.evento for e in eventos] == ["autorizacao"]


# ── Exclusão e anonimização ───────────────────────────────────


@pytest.mark.asyncio
async def test_excluir_a_conta_desvincula_os_eventos_sem_bloquear(fabrica, criados, aviso_de_teste):
    eu = _usuario(UserRole.client, avatar_url=None)
    admin = _usuario(UserRole.admin)
    await _grava(fabrica, criados, eu, admin)
    _atende_como(fabrica, eu, admin)
    await _pede("PUT", _ROTA, eu, json=_autoriza())
    await _pede("PUT", _ROTA, eu, json={"autorizada": False})
    async with fabrica() as s:
        ids_dos_eventos = (
            (
                await s.execute(
                    select(AvatarVisibilityEvent.id).where(AvatarVisibilityEvent.user_id == eu.id)
                )
            )
            .scalars()
            .all()
        )
        # O `delete_user` recusa conta com auditoria; a exclusão que se testa
        # aqui é a do BANCO, que é o que o SET NULL decide.
        await s.execute(delete(AuditLog).where(AuditLog.entity_id == eu.id))
        await s.execute(delete(User).where(User.id == eu.id))
        await s.commit()

    async with fabrica() as s:
        sobras = (
            await s.execute(
                select(AvatarVisibilityEvent.user_id, AvatarVisibilityEvent.evento)
                .where(AvatarVisibilityEvent.id.in_(ids_dos_eventos))
                .order_by(AvatarVisibilityEvent.registrado_em)
            )
        ).all()
        await s.execute(
            delete(AvatarVisibilityEvent).where(AvatarVisibilityEvent.id.in_(ids_dos_eventos))
        )
        await s.commit()
    assert [tuple(x) for x in sobras] == [(None, "autorizacao"), (None, "revogacao")]


@pytest.mark.asyncio
async def test_excluir_conta_sem_rastro_continua_passando_com_eventos(
    fabrica, criados, aviso_de_teste
):
    """O DELETE da API não ganhou bloqueio novo: a tabela é SET NULL."""
    eu = _usuario(UserRole.client, avatar_url=None)
    admin = _usuario(UserRole.admin)
    await _grava(fabrica, criados, eu, admin)
    async with fabrica() as s:
        s.add(
            AvatarVisibilityEvent(
                user_id=eu.id,
                evento="autorizacao",
                versao_aviso=_VERSAO_DE_TESTE,
                origem="alteracao_propria",
            )
        )
        await s.commit()
    _atende_como(fabrica, admin)

    r = await _pede("DELETE", f"/api/v1/users/{eu.id}", admin)

    assert r.status_code == 204, r.text
    async with fabrica() as s:
        orfaos = (
            (
                await s.execute(
                    select(AvatarVisibilityEvent).where(
                        AvatarVisibilityEvent.user_id.is_(None),
                        AvatarVisibilityEvent.versao_aviso == _VERSAO_DE_TESTE,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(orfaos) >= 1
        await s.execute(
            delete(AvatarVisibilityEvent).where(
                AvatarVisibilityEvent.id.in_([o.id for o in orfaos])
            )
        )
        await s.commit()


@pytest.mark.asyncio
async def test_anonimizar_continua_funcionando_com_eventos_gravados(
    fabrica, criados, aviso_de_teste
):
    eu = _usuario(UserRole.client, avatar_url=None)
    admin = _usuario(UserRole.admin)
    await _grava(fabrica, criados, eu, admin)
    _atende_como(fabrica, eu, admin)
    await _pede("PUT", _ROTA, eu, json=_autoriza())

    r = await _pede("POST", f"/api/v1/users/{eu.id}/anonymize", admin)

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "anonymized"
    _, eventos = await _estado(fabrica, eu)
    assert [e.evento for e in eventos] == ["autorizacao"]


# ── A anonimização encerra a autorização ─────────────────────
#
# Diferente da conta só inativa (que guarda a escolha), a anonimizada perde a
# autorização de vez, na mesma transação. Não é revogação do titular: nenhum
# evento novo em nome dele — o registro é o AuditLog da anonimização, com o
# ator verdadeiro. Os eventos antigos ficam como estão.


async def _auditoria(fabrica, alvo: User, acao: AuditAction) -> list[AuditLog]:
    async with fabrica() as s:
        return list(
            (
                await s.execute(
                    select(AuditLog).where(AuditLog.entity_id == alvo.id, AuditLog.action == acao)
                )
            )
            .scalars()
            .all()
        )


@pytest.mark.asyncio
async def test_anonimizar_quem_autorizou_apaga_a_foto_e_encerra_a_autorizacao(
    fabrica, criados, aviso_de_teste, tmp_path, monkeypatch
):
    eu = _usuario(UserRole.technician, avatar_url=None)
    admin = _usuario(UserRole.admin)
    await _grava(fabrica, criados, eu, admin)
    _atende_como(fabrica, eu, admin)
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    r = await _pede(
        "POST", "/api/v1/users/me/avatar", eu, files={"file": ("f.png", b"\x89PNG", "image/png")}
    )
    assert r.status_code == 200, r.text
    assert [p for p in tmp_path.rglob("*") if p.is_file()]
    r = await _pede("PUT", _ROTA, eu, json=_autoriza())
    assert r.status_code == 200, r.text

    r = await _pede("POST", f"/api/v1/users/{eu.id}/anonymize", admin)

    assert r.status_code == 200, r.text
    relido = await _usuario_por_id(fabrica, eu.id)
    assert relido.avatar_url is None
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == []
    visivel, eventos = await _estado(fabrica, eu)
    assert visivel is False
    # Só a autorização que o titular deu; nenhuma "revogação" em nome dele.
    assert [(e.evento, e.origem) for e in eventos] == [("autorizacao", "alteracao_propria")]
    (registro,) = await _auditoria(fabrica, eu, AuditAction.anonymize)
    assert registro.user_id == admin.id
    assert registro.old_data == {"avatar_visivel_a_terceiros": True}
    assert registro.new_data["avatar_visivel_a_terceiros"] is False


@pytest.mark.asyncio
async def test_anonimizar_quem_nao_autorizou_continua_sem_autorizacao(fabrica, criados):
    eu = _usuario(UserRole.client, avatar_url=None)
    admin = _usuario(UserRole.admin)
    await _grava(fabrica, criados, eu, admin)
    _atende_como(fabrica, eu, admin)

    r = await _pede("POST", f"/api/v1/users/{eu.id}/anonymize", admin)

    assert r.status_code == 200, r.text
    assert await _estado(fabrica, eu) == (False, [])
    (registro,) = await _auditoria(fabrica, eu, AuditAction.anonymize)
    assert registro.old_data == {"avatar_visivel_a_terceiros": False}


@pytest.mark.asyncio
async def test_marcar_anonimizada_pelo_patch_de_status_tambem_encerra(fabrica, criados):
    """O `PATCH /status` aceita `anonymized`: é o segundo caminho real."""
    eu = _usuario(UserRole.technician, avatar_visivel_a_terceiros=True)
    admin = _usuario(UserRole.admin)
    await _grava(fabrica, criados, eu, admin)
    _atende_como(fabrica, eu, admin)

    r = await _pede("PATCH", f"/api/v1/users/{eu.id}/status", admin, json={"status": "anonymized"})

    assert r.status_code == 200, r.text
    assert await _estado(fabrica, eu) == (False, [])
    (registro,) = await _auditoria(fabrica, eu, AuditAction.status_change)
    assert registro.user_id == admin.id
    assert registro.old_data == {"avatar_visivel_a_terceiros": True}
    assert registro.new_data == {"avatar_visivel_a_terceiros": False}


@pytest.mark.asyncio
async def test_inativar_pelo_patch_de_status_guarda_a_escolha(fabrica, criados):
    """A regra da conta só inativa não muda: a escolha fica, e o registro
    do status continua sem dado da foto."""
    eu = _usuario(UserRole.technician, avatar_visivel_a_terceiros=True)
    admin = _usuario(UserRole.admin)
    await _grava(fabrica, criados, eu, admin)
    _atende_como(fabrica, eu, admin)

    r = await _pede("PATCH", f"/api/v1/users/{eu.id}/status", admin, json={"status": "inactive"})

    assert r.status_code == 200, r.text
    assert await _estado(fabrica, eu) == (True, [])
    (registro,) = await _auditoria(fabrica, eu, AuditAction.status_change)
    assert registro.old_data is None and registro.new_data is None


@pytest.mark.parametrize("caminho", ["anonymize", "patch_status"])
@pytest.mark.asyncio
async def test_reativar_a_conta_anonimizada_nao_ressuscita_a_autorizacao(
    fabrica, criados, aviso_de_teste, tmp_path, monkeypatch, caminho
):
    """O único reuso real do registro é o `PATCH /status` de volta a `active`.
    Foto nova depois dele continua sem aparecer até nova autorização."""
    eu = _usuario(UserRole.technician, avatar_url=None)
    admin = _usuario(UserRole.admin)
    await _grava(fabrica, criados, eu, admin)
    _atende_como(fabrica, eu, admin)
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    r = await _pede("PUT", _ROTA, eu, json=_autoriza())
    assert r.status_code == 200, r.text
    if caminho == "anonymize":
        r = await _pede("POST", f"/api/v1/users/{eu.id}/anonymize", admin)
    else:
        r = await _pede(
            "PATCH", f"/api/v1/users/{eu.id}/status", admin, json={"status": "anonymized"}
        )
    assert r.status_code == 200, r.text

    r = await _pede("PATCH", f"/api/v1/users/{eu.id}/status", admin, json={"status": "active"})
    assert r.status_code == 200, r.text
    r = await _pede(
        "POST", "/api/v1/users/me/avatar", eu, files={"file": ("n.png", b"\x89PNG", "image/png")}
    )
    assert r.status_code == 200, r.text

    relido = await _usuario_por_id(fabrica, eu.id)
    assert relido.status == UserStatus.active
    assert relido.avatar_url
    assert relido.avatar_visivel_a_terceiros is False
    assert pode_aparecer_para_terceiros(relido) is False
    _, eventos = await _estado(fabrica, eu)
    assert [e.evento for e in eventos] == ["autorizacao"]

    # Só uma autorização NOVA do titular volta a mostrar a foto.
    r = await _pede("PUT", _ROTA, eu, json=_autoriza())
    assert r.status_code == 200, r.text
    assert pode_aparecer_para_terceiros(await _usuario_por_id(fabrica, eu.id)) is True


async def _espera_alguem_parado_na_trava(fabrica) -> None:
    """Estado observável, não espera cega: até alguma sessão do banco estar
    bloqueada esperando uma trava de linha."""
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
    raise AssertionError("a anonimização não chegou a esperar pela trava")


@pytest.mark.parametrize("caminho", ["anonymize", "patch_status"])
@pytest.mark.asyncio
async def test_autorizacao_comitada_durante_a_anonimizacao_nao_sobrevive(fabrica, criados, caminho):
    """Outra transação segura a linha e grava `true`; a anonimização chega
    nesse meio-tempo. Com a trava ela espera e relê `true` antes de zerar.
    Sem a trava, leria `false` antes, e o UPDATE nem levaria a coluna."""
    eu = _usuario(UserRole.technician, avatar_url=None)
    admin = _usuario(UserRole.admin)
    await _grava(fabrica, criados, eu, admin)
    _atende_como(fabrica, eu, admin)

    async with fabrica() as segura:
        await segura.execute(text("SELECT 1 FROM users WHERE id = :id FOR UPDATE"), {"id": eu.id})
        await segura.execute(
            text("UPDATE users SET avatar_visivel_a_terceiros = true WHERE id = :id"),
            {"id": eu.id},
        )
        if caminho == "anonymize":
            pedido = asyncio.create_task(_pede("POST", f"/api/v1/users/{eu.id}/anonymize", admin))
        else:
            pedido = asyncio.create_task(
                _pede(
                    "PATCH",
                    f"/api/v1/users/{eu.id}/status",
                    admin,
                    json={"status": "anonymized"},
                )
            )
        await _espera_alguem_parado_na_trava(fabrica)
        await segura.commit()

    r = await pedido
    assert r.status_code == 200, r.text
    visivel, _ = await _estado(fabrica, eu)
    assert visivel is False


# ── O WebSocket relê o remetente atual ────────────────────────


@pytest.mark.asyncio
async def test_a_releitura_da_mensagem_traz_o_remetente_atual_e_nao_a_copia_velha(fabrica, criados):
    """A cópia velha do remetente está no mapa de identidade da sessão; outra
    transação revoga; a releitura usada pelo WebSocket e pelo POST tem de ver a
    revogação. Sem `populate_existing`, ela devolveria a cópia velha."""
    from app.routers.chat import _mensagem_com_remetente_atual

    autor = _usuario(UserRole.technician, avatar_visivel_a_terceiros=True)
    cliente = _usuario(UserRole.client)
    chamado = Ticket(
        id=uuid.uuid4(),
        protocol=f"TESTE-{uuid.uuid4().hex[:8]}",
        title="Teste",
        description="Teste",
        status=TicketStatus.open,
        priority=TicketPriority.medium,
        category=TicketCategory.general,
        creator_id=cliente.id,
    )
    await _grava(fabrica, criados, autor, cliente, chamado)
    msg = ChatMessage(id=uuid.uuid4(), ticket_id=chamado.id, sender_id=autor.id, content="oi")
    async with fabrica() as s:
        s.add(msg)
        await s.commit()

    async with fabrica() as sessao_do_socket:
        velho = (
            await sessao_do_socket.execute(select(User).where(User.id == autor.id))
        ).scalar_one()
        assert velho.avatar_visivel_a_terceiros is True

        async with fabrica() as outra:
            await outra.execute(
                text("UPDATE users SET avatar_visivel_a_terceiros = false WHERE id = :id"),
                {"id": autor.id},
            )
            await outra.commit()

        relida = await _mensagem_com_remetente_atual(sessao_do_socket, msg.id)

        assert relida.sender is velho  # o mesmo objeto do mapa de identidade...
        assert relida.sender.avatar_visivel_a_terceiros is False  # ...com o valor atual


# ── updated_at: a escolha não mexe no token de versão ────────
#
# `User.updated_at` tem `onupdate`. Mudar a preferência o preserva DE
# PROPÓSITO (é o token da remoção da foto pelo admin); o resto continua
# renovando. Toda leitura aqui é de uma sessão NOVA, depois do commit — o
# valor que o banco guardou, não o de um objeto na memória.


async def _updated_at(fabrica, usuario: User) -> datetime:
    async with fabrica() as s:
        return (await s.execute(select(User.updated_at).where(User.id == usuario.id))).scalar_one()


@pytest.mark.asyncio
async def test_conceder_revogar_e_repetir_preservam_updated_at(fabrica, criados, aviso_de_teste):
    eu = _usuario(UserRole.technician)
    await _grava(fabrica, criados, eu)
    _atende_como(fabrica, eu)
    antes = await _updated_at(fabrica, eu)

    assert (await _pede("PUT", _ROTA, eu, json=_autoriza())).status_code == 200
    assert await _updated_at(fabrica, eu) == antes
    assert (await _pede("PUT", _ROTA, eu, json={"autorizada": False})).status_code == 200
    assert await _updated_at(fabrica, eu) == antes
    assert (await _pede("PUT", _ROTA, eu, json={"autorizada": False})).status_code == 200
    assert await _updated_at(fabrica, eu) == antes

    visivel, eventos = await _estado(fabrica, eu)
    assert visivel is False
    assert [e.evento for e in eventos] == ["autorizacao", "revogacao"]
    # O momento da escolha mora no evento, com horário próprio.
    assert all(e.registrado_em > antes for e in eventos)


@pytest.mark.asyncio
async def test_patch_de_nome_continua_renovando_updated_at(fabrica, criados):
    eu = _usuario(UserRole.technician)
    await _grava(fabrica, criados, eu)
    _atende_como(fabrica, eu)
    antes = await _updated_at(fabrica, eu)

    r = await _pede("PATCH", "/api/v1/users/me", eu, json={"name": "Nome Novo de Teste"})

    assert r.status_code == 200, r.text
    assert await _updated_at(fabrica, eu) > antes


async def _versao_que_o_admin_ve(admin: User, alvo: User) -> str:
    r = await _pede("GET", f"/api/v1/users/{alvo.id}", admin)
    assert r.status_code == 200, r.text
    return r.json()["updated_at"]


async def _admin_remove(admin: User, alvo: User, versao: str):
    return await _pede(
        "POST",
        f"/api/v1/users/{alvo.id}/avatar/remove",
        admin,
        json={"justification": "TESTE — foto inadequada", "expected_updated_at": versao},
    )


@pytest.mark.asyncio
async def test_mudar_a_preferencia_nao_faz_a_remocao_pelo_admin_acusar_conflito(
    fabrica, criados, aviso_de_teste, tmp_path, monkeypatch
):
    """A tela do admin abriu; o dono autorizou e revogou; a remoção passa."""
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    dono = _usuario(UserRole.client)
    dono.avatar_url = f"avatars/{dono.id}.png"
    admin = _usuario(UserRole.admin)
    await _grava(fabrica, criados, dono, admin)
    _atende_como(fabrica, dono, admin)
    versao = await _versao_que_o_admin_ve(admin, dono)

    assert (await _pede("PUT", _ROTA, dono, json=_autoriza())).status_code == 200
    assert (await _pede("PUT", _ROTA, dono, json={"autorizada": False})).status_code == 200

    r = await _admin_remove(admin, dono, versao)
    assert r.status_code == 200, r.text
    assert r.json()["avatar_url"] is None


@pytest.mark.asyncio
async def test_upload_continua_invalidando_a_versao_da_remocao_pelo_admin(
    fabrica, criados, tmp_path, monkeypatch
):
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    dono = _usuario(UserRole.client)
    dono.avatar_url = f"avatars/{dono.id}.png"
    admin = _usuario(UserRole.admin)
    await _grava(fabrica, criados, dono, admin)
    _atende_como(fabrica, dono, admin)
    versao = await _versao_que_o_admin_ve(admin, dono)

    r = await _pede(
        "POST", "/api/v1/users/me/avatar", dono, files={"file": ("n.png", b"\x89PNG", "image/png")}
    )
    assert r.status_code == 200, r.text

    r = await _admin_remove(admin, dono, versao)
    assert r.status_code == 409, r.text
    async with fabrica() as s:
        chave = (await s.execute(select(User.avatar_url).where(User.id == dono.id))).scalar_one()
    assert chave == f"avatars/{dono.id}.png"


# ── Login de verdade: conta não ativa não chega à rota ────────
#
# Daqui para baixo, `get_current_user` é o REAL: token assinado de verdade,
# usuário lido do banco do teste, status conferido por ele. Só o Redis da
# lista de tokens revogados é um dublê vazio — nenhum token está revogado.


class _RedisVazio:
    async def exists(self, chave):
        return 0


def _atende_com_login_real(fabrica, monkeypatch) -> None:
    async def _db():
        async with fabrica() as sessao:
            yield sessao

    async def _redis():
        return _RedisVazio()

    monkeypatch.setattr("app.core.security.get_redis", _redis)
    app.dependency_overrides[get_db] = _db


async def _pede_logado(metodo: str, url: str, quem: User, **kwargs):
    token = create_access_token(quem.id, quem.role.value, quem.email)
    transporte = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://t") as c:
        return await c.request(metodo, url, headers={"Authorization": f"Bearer {token}"}, **kwargs)


@pytest.mark.asyncio
async def test_conta_ativa_concede_e_revoga_com_o_login_de_verdade(
    fabrica, criados, aviso_de_teste, monkeypatch
):
    eu = _usuario(UserRole.client)
    await _grava(fabrica, criados, eu)
    _atende_com_login_real(fabrica, monkeypatch)

    r = await _pede_logado("PUT", _ROTA, eu, json=_autoriza())
    assert r.status_code == 200, r.text
    r = await _pede_logado("PUT", _ROTA, eu, json={"autorizada": False})
    assert r.status_code == 200, r.text
    r = await _pede_logado("GET", _ROTA, eu)
    assert r.status_code == 200, r.text
    assert r.json()["autorizada"] is False

    _, eventos = await _estado(fabrica, eu)
    assert [e.evento for e in eventos] == ["autorizacao", "revogacao"]


@pytest.mark.parametrize("situacao", [UserStatus.inactive, UserStatus.anonymized])
@pytest.mark.asyncio
async def test_conta_nao_ativa_recebe_a_recusa_do_login_no_get_e_no_put(
    situacao, fabrica, criados, aviso_de_teste, monkeypatch
):
    """Nem autorizar nem revogar: a recusa vem do `get_current_user`, antes da
    rota. A escolha gravada fica como estava — nenhum evento em nome dela."""
    eu = _usuario(UserRole.technician, status=situacao, avatar_visivel_a_terceiros=True)
    await _grava(fabrica, criados, eu)
    _atende_com_login_real(fabrica, monkeypatch)

    respostas = [
        await _pede_logado("GET", _ROTA, eu),
        await _pede_logado("PUT", _ROTA, eu, json=_autoriza()),
        await _pede_logado("PUT", _ROTA, eu, json={"autorizada": False}),
    ]

    assert [r.status_code for r in respostas] == [403, 403, 403]
    assert all("inativa" in r.json()["detail"] for r in respostas)
    assert await _estado(fabrica, eu) == (True, [])


@pytest.mark.asyncio
async def test_desativada_entre_o_login_e_a_trava_nao_autoriza(fabrica, criados, aviso_de_teste):
    """A corrida que a conferência do handler cobre: o login viu a conta ativa,
    e quando a trava pega a linha ela já foi desativada."""
    eu = _usuario(UserRole.client, status=UserStatus.inactive)
    await _grava(fabrica, criados, eu)

    async def _db():
        async with fabrica() as sessao:
            yield sessao

    app.dependency_overrides[get_db] = _db
    # O login, um instante antes, ainda via a conta ativa.
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=eu.id, role=eu.role, status=UserStatus.active
    )

    r = await _pede("PUT", _ROTA, eu, json=_autoriza())

    assert r.status_code == 403, r.text
    assert await _estado(fabrica, eu) == (False, [])


# ── Conta não ativa não emite foto para terceiros ─────────────
#
# Suspensão por status, não revogação: a escolha gravada fica, nenhum evento
# é criado, e reativar volta a respeitar o que estava gravado.


def _chamado_de(cliente: User, tecnico: User) -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        protocol=f"TESTE-{uuid.uuid4().hex[:8]}",
        title="Teste",
        description="Teste",
        status=TicketStatus.open,
        priority=TicketPriority.medium,
        category=TicketCategory.general,
        creator_id=cliente.id,
        assignee_id=tecnico.id,
    )


async def _assina_de_teste(chave, settings, expires=3600):
    return f"/api/v1/files/tok-{chave}"


async def _fotos_que_o_cliente_recebe(cliente: User, chamado: Ticket) -> tuple:
    detalhe = await _pede_logado("GET", f"/api/v1/tickets/{chamado.id}", cliente)
    assert detalhe.status_code == 200, detalhe.text
    historico = await _pede_logado("GET", f"/api/v1/tickets/{chamado.id}/messages", cliente)
    assert historico.status_code == 200, historico.text
    da_equipe = [m for m in historico.json()["items"] if m["sender_id"] != str(cliente.id)]
    assert len(da_equipe) == 1
    return detalhe.json()["assignee_avatar_url"], da_equipe[0]["sender_avatar_url"]


@pytest.mark.asyncio
async def test_conta_desativada_nao_emite_foto_e_reativar_respeita_a_escolha_guardada(
    fabrica, criados, aviso_de_teste, monkeypatch
):
    from app.utils import avatar as av

    monkeypatch.setattr(av.storage, "get_presigned_url", _assina_de_teste)
    cliente = _usuario(UserRole.client)
    tecnico = _usuario(UserRole.technician, avatar_visivel_a_terceiros=True)
    tecnico.avatar_url = f"avatars/{tecnico.id}.png"
    admin = _usuario(UserRole.admin)
    chamado = _chamado_de(cliente, tecnico)
    await _grava(fabrica, criados, cliente, tecnico, admin, chamado)
    async with fabrica() as s:
        s.add(
            ChatMessage(id=uuid.uuid4(), ticket_id=chamado.id, sender_id=tecnico.id, content="oi")
        )
        await s.commit()
    _atende_com_login_real(fabrica, monkeypatch)
    foto = f"/api/v1/files/tok-avatars/{tecnico.id}.png"

    assert await _fotos_que_o_cliente_recebe(cliente, chamado) == (foto, foto)

    r = await _pede_logado(
        "PATCH", f"/api/v1/users/{tecnico.id}/status", admin, json={"status": "inactive"}
    )
    assert r.status_code == 200, r.text
    assert await _fotos_que_o_cliente_recebe(cliente, chamado) == (None, None)
    assert await _estado(fabrica, tecnico) == (True, [])

    r = await _pede_logado(
        "PATCH", f"/api/v1/users/{tecnico.id}/status", admin, json={"status": "active"}
    )
    assert r.status_code == 200, r.text
    assert await _estado(fabrica, tecnico) == (True, [])
    assert await _fotos_que_o_cliente_recebe(cliente, chamado) == (foto, foto)


@pytest.mark.asyncio
async def test_reativar_quem_nao_autorizou_continua_sem_foto(fabrica, criados, monkeypatch):
    from app.utils import avatar as av

    monkeypatch.setattr(av.storage, "get_presigned_url", _assina_de_teste)
    cliente = _usuario(UserRole.client)
    tecnico = _usuario(UserRole.technician, status=UserStatus.inactive)
    tecnico.avatar_url = f"avatars/{tecnico.id}.png"
    admin = _usuario(UserRole.admin)
    chamado = _chamado_de(cliente, tecnico)
    await _grava(fabrica, criados, cliente, tecnico, admin, chamado)
    async with fabrica() as s:
        s.add(
            ChatMessage(id=uuid.uuid4(), ticket_id=chamado.id, sender_id=tecnico.id, content="oi")
        )
        await s.commit()
    _atende_com_login_real(fabrica, monkeypatch)

    r = await _pede_logado(
        "PATCH", f"/api/v1/users/{tecnico.id}/status", admin, json={"status": "active"}
    )
    assert r.status_code == 200, r.text

    assert await _fotos_que_o_cliente_recebe(cliente, chamado) == (None, None)
    assert await _estado(fabrica, tecnico) == (False, [])


@pytest.mark.asyncio
async def test_a_releitura_do_websocket_ve_a_desativacao_feita_por_outra_transacao(
    fabrica, criados
):
    """Mesma prova da releitura acima, para o STATUS: a conexão guardou o
    remetente ativo; outra transação o desativa; a releitura vê a desativação,
    e a regra da conversa deixa de emitir a foto."""
    from app.routers.chat import _mensagem_com_remetente_atual
    from app.utils.avatar import foto_visivel_na_conversa

    autor = _usuario(UserRole.technician, avatar_visivel_a_terceiros=True)
    cliente = _usuario(UserRole.client)
    chamado = _chamado_de(cliente, autor)
    await _grava(fabrica, criados, autor, cliente, chamado)
    msg = ChatMessage(id=uuid.uuid4(), ticket_id=chamado.id, sender_id=autor.id, content="oi")
    async with fabrica() as s:
        s.add(msg)
        await s.commit()

    async with fabrica() as sessao_do_socket:
        velho = (
            await sessao_do_socket.execute(select(User).where(User.id == autor.id))
        ).scalar_one()
        assert foto_visivel_na_conversa(velho, chamado) is True

        async with fabrica() as outra:
            await outra.execute(
                text("UPDATE users SET status = 'inactive' WHERE id = :id"), {"id": autor.id}
            )
            await outra.commit()

        relida = await _mensagem_com_remetente_atual(sessao_do_socket, msg.id)

        assert relida.sender is velho
        assert relida.sender.status == UserStatus.inactive
        assert relida.sender.avatar_visivel_a_terceiros is True  # a escolha fica
        assert foto_visivel_na_conversa(relida.sender, chamado) is False


# ── Em produção, só texto aprovado autoriza ───────────────────


def _settings_de_producao(versao: str | None):
    """Uma cópia ISOLADA das configurações, só para esta rota. Não toca o
    objeto global, nem liga nada de produção fora da dependência."""
    copia = get_settings().model_copy(
        update={"app_env": "production", "avatar_aviso_exibicao_versao": versao}
    )
    app.dependency_overrides[get_settings] = lambda: copia
    return copia


@pytest.mark.parametrize("qual", ["minuta", "teste"])
@pytest.mark.asyncio
async def test_em_producao_minuta_e_texto_de_teste_nao_autorizam(
    qual, fabrica, criados, aviso_de_teste
):
    versao = "MINUTA-2026-10-21" if qual == "minuta" else _VERSAO_DE_TESTE
    eu = _usuario(UserRole.client)
    ja_autorizou = _usuario(UserRole.technician, avatar_visivel_a_terceiros=True)
    await _grava(fabrica, criados, eu, ja_autorizou)
    _atende_como(fabrica, eu, ja_autorizou)
    _settings_de_producao(versao)

    r = await _pede("GET", _ROTA, eu)
    assert r.status_code == 200, r.text
    assert r.json() == {"autorizada": False, "disponivel": False, "aviso": None}

    r = await _pede("PUT", _ROTA, eu, json=_autoriza(versao))
    assert r.status_code == 409, r.text
    assert await _estado(fabrica, eu) == (False, [])

    # Quem já autorizou não perde a escolha calado — e consegue revogar.
    r = await _pede("GET", _ROTA, ja_autorizou)
    assert r.json()["autorizada"] is True
    assert r.json()["disponivel"] is False
    r = await _pede("PUT", _ROTA, ja_autorizou, json={"autorizada": False, "versao_aviso": versao})
    assert r.status_code == 200, r.text
    visivel, eventos = await _estado(fabrica, ja_autorizou)
    assert visivel is False
    assert [(e.evento, e.versao_aviso) for e in eventos] == [("revogacao", None)]
