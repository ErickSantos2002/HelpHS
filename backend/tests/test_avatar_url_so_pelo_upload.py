"""
A foto de perfil só muda pelo upload, e só a do próprio dono vira link.

Por que este arquivo existe: até 09/10/2026, `avatar_url` era campo do
`UserUpdate`, o schema compartilhado por `PATCH /users/me` e
`PATCH /users/{id}`. Qualquer usuário gravava ali o texto que quisesse, e
duas coisas saíam disso:

1. **Foto de outra pessoa.** Gravar `avatars/<id-de-outro>.jpg` fazia o
   `GET /users/me` assinar e entregar o arquivo de OUTRA conta — o link
   assinado autoriza por posse do token, não por dono.
2. **URL externa.** Gravar `https://...` voltava cru na resposta, e o
   `resolveFileUrl` do front deixa URL completa passar intacta: o `<img>` de
   quem visse a foto bateria num servidor de terceiros.

São duas defesas, e este arquivo cobra as duas:

- **Entrada:** o campo saiu do `UserUpdate`. Campos extras são ignorados pelo
  comportamento padrão do Pydantic, herdado por `UserUpdate` — o
  `AppBaseModel` não configura `extra` (ver `test_escalacao_por_users_me.py`).
  Por isso o PATCH que manda `avatar_url` responde 200 e o campo não é
  persistido — o mesmo tratamento de `status`, `email` e `password`. O
  único caminho de escrita é `POST /users/me/avatar`.
- **Saída:** o que já estiver gravado só é devolvido — e só é assinado — se
  for exatamente a chave que o upload produz para AQUELE usuário. O resto
  vira `null`, e o front cai nas iniciais.

Como em `test_escalacao_por_users_me.py`, a escrita é conferida no ATRIBUTO
depois da requisição, e todo PATCH altera o `name` junto: "nada mudou" não
pode ser confundido com "a requisição não chegou".
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from app.models.models import UserRole, UserStatus
from app.services import storage

_URL_EXTERNA = "https://rastreador.example/pixel.png"


def _user(role=UserRole.client, avatar_url=None):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = "pessoa@test.com"
    u.name = "Nome Original"
    u.role = role
    u.status = UserStatus.active
    u.phone = "+5581999999999"
    u.department = None
    u.avatar_url = avatar_url
    u.last_login = None
    u.lgpd_consent = True
    u.lgpd_consent_at = None
    u.company_name = None
    u.cnpj = None
    u.company_cep = None
    u.company_address = None
    u.company_city = None
    u.company_state = None
    u.onboarding_completed = True
    u.api4com_extension = None
    u.ai_enabled = True
    u.email_verified = True
    u.mfa_enabled = False
    u.password = "hash-original"
    u.company_id = None
    u.created_at = datetime.now(UTC)
    u.updated_at = datetime.now(UTC)
    return u


def _db(alvo):
    async def _execute(*args, **kwargs):
        resultado = MagicMock()
        resultado.scalar_one_or_none.return_value = alvo
        resultado.scalars.return_value.all.return_value = [alvo] if alvo else []
        resultado.scalar_one.return_value = 1 if alvo else 0
        return resultado

    sessao = AsyncMock()
    sessao.execute = _execute
    sessao.add = MagicMock()
    sessao.commit = AsyncMock()
    sessao.refresh = AsyncMock()

    async def _gen():
        yield sessao

    return _gen


@pytest.fixture(autouse=True)
def _limpa_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def settings_com_upload_dir(tmp_path):
    settings = get_settings()
    original = settings.upload_dir
    settings.upload_dir = str(tmp_path)
    yield settings
    settings.upload_dir = original


async def _chama(metodo, caminho, *, ator, alvo, **kwargs):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _db(alvo)
    app.dependency_overrides[get_current_user] = lambda: ator
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
        return await cliente.request(metodo, f"/api/v1{caminho}", **kwargs)


def _chave_do_upload(user, extensao=".png"):
    """A chave que `POST /users/me/avatar` grava — o único formato que existiu
    desde a criação do upload (`de2aa09`, 18/05/2026)."""
    return f"avatars/{user.id}{extensao}"


# ── Entrada: o PATCH não grava avatar_url ──────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "valor",
    [_URL_EXTERNA, f"avatars/{uuid.uuid4()}.jpg", None],
    ids=["url-externa", "chave-de-outro-usuario", "nulo"],
)
async def test_patch_me_descarta_avatar_url(valor):
    original = "avatars/original.png"
    cliente = _user(avatar_url=original)

    resposta = await _chama(
        "PATCH",
        "/users/me",
        ator=cliente,
        alvo=cliente,
        json={"name": "Nome Novo", "avatar_url": valor},
    )

    assert resposta.status_code == 200, resposta.text
    assert cliente.name == "Nome Novo"
    assert cliente.avatar_url == original


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "valor",
    [_URL_EXTERNA, f"avatars/{uuid.uuid4()}.jpg", None],
    ids=["url-externa", "chave-de-outro-usuario", "nulo"],
)
async def test_patch_de_terceiro_pelo_admin_edita_o_resto_mas_nao_a_foto(valor):
    """O admin PODE editar a conta alheia — e é justamente por isso que o
    campo precisa cair: a edição autorizada dos outros campos não pode
    carregar a foto junto."""
    admin = _user(role=UserRole.admin)
    alvo = _user()
    original = _chave_do_upload(alvo)
    alvo.avatar_url = original

    resposta = await _chama(
        "PATCH",
        f"/users/{alvo.id}",
        ator=admin,
        alvo=alvo,
        json={"name": "Nome Novo", "department": "Qualidade", "avatar_url": valor},
    )

    assert resposta.status_code == 200, resposta.text
    assert alvo.name == "Nome Novo"
    assert alvo.department == "Qualidade"
    assert alvo.avatar_url == original


@pytest.mark.asyncio
async def test_patch_de_si_mesmo_pela_rota_de_id_tambem_descarta():
    """O cliente alcança `PATCH /users/{id}` com o próprio id — é o segundo
    caminho para o mesmo schema."""
    cliente = _user()

    resposta = await _chama(
        "PATCH",
        f"/users/{cliente.id}",
        ator=cliente,
        alvo=cliente,
        json={"name": "Nome Novo", "avatar_url": _URL_EXTERNA},
    )

    assert resposta.status_code == 200, resposta.text
    assert cliente.name == "Nome Novo"
    assert cliente.avatar_url is None


@pytest.mark.asyncio
async def test_permissao_nao_foi_ampliada_cliente_continua_barrado_em_terceiro():
    cliente = _user()
    alvo = _user()
    original = _chave_do_upload(alvo)
    alvo.avatar_url = original

    resposta = await _chama(
        "PATCH",
        f"/users/{alvo.id}",
        ator=cliente,
        alvo=alvo,
        json={"name": "Invasor", "avatar_url": _URL_EXTERNA},
    )

    assert resposta.status_code == 403
    assert alvo.name == "Nome Original"
    assert alvo.avatar_url == original


def test_o_campo_nao_existe_mais_no_schema_de_edicao():
    """Defesa estrutural: voltar com o campo exige apagar este teste."""
    from app.schemas.user import UserCreate, UserUpdate

    assert "avatar_url" not in UserUpdate.model_fields
    assert "avatar_url" not in UserCreate.model_fields


# ── Saída: só a chave legítima do dono vira foto ────────────────


def _invalidas(user):
    outro = uuid.uuid4()
    return [
        _URL_EXTERNA,
        f"avatars/{outro}.png",
        f"avatars/{user.id}/../{outro}.png",
        f"avatars/../tickets/{uuid.uuid4()}/laudo.pdf",
        f"tickets/{uuid.uuid4()}/{uuid.uuid4()}.png",
        f"avatars/{user.id}.svg",
        f"avatars/{user.id}.PNG",
        f"avatars/{user.id}",
        f"/avatars/{user.id}.png",
        "",
    ]


_IDS_INVALIDAS = [
    "url-externa",
    "chave-de-outro-usuario",
    "travessia-para-outro",
    "travessia-para-anexo",
    "chave-de-anexo",
    "extensao-que-o-upload-nao-produz",
    "extensao-em-maiuscula",
    "sem-extensao",
    "caminho-absoluto",
    "vazia",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("indice", range(len(_IDS_INVALIDAS)), ids=_IDS_INVALIDAS)
async def test_get_me_nao_assina_referencia_invalida(indice):
    cliente = _user()
    cliente.avatar_url = _invalidas(cliente)[indice]

    resposta = await _chama("GET", "/users/me", ator=cliente, alvo=cliente)

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["avatar_url"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("indice", range(len(_IDS_INVALIDAS)), ids=_IDS_INVALIDAS)
async def test_resposta_de_terceiro_nao_expoe_referencia_invalida(indice):
    admin = _user(role=UserRole.admin)
    alvo = _user()
    alvo.avatar_url = _invalidas(alvo)[indice]

    resposta = await _chama("GET", f"/users/{alvo.id}", ator=admin, alvo=alvo)

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["avatar_url"] is None


@pytest.mark.asyncio
async def test_resposta_do_patch_tambem_nao_expoe_referencia_invalida():
    """A resposta do próprio PATCH sai pelo mesmo `_to_response` — gravado
    antes da correção, o valor velho não pode voltar por ela."""
    cliente = _user(avatar_url=_URL_EXTERNA)

    resposta = await _chama(
        "PATCH", "/users/me", ator=cliente, alvo=cliente, json={"name": "Nome Novo"}
    )

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["avatar_url"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("extensao", [".jpg", ".png", ".gif", ".webp"])
async def test_get_me_assina_a_chave_legitima_do_proprio_usuario(extensao):
    cliente = _user()
    cliente.avatar_url = _chave_do_upload(cliente, extensao)

    resposta = await _chama("GET", "/users/me", ator=cliente, alvo=cliente)

    assert resposta.status_code == 200, resposta.text
    link = resposta.json()["avatar_url"]
    assert link.startswith("/api/v1/files/")
    token = link.removeprefix("/api/v1/files/")
    assert storage.read_file_token(token, get_settings()) == cliente.avatar_url


@pytest.mark.asyncio
async def test_resposta_de_terceiro_mantem_a_chave_legitima_como_era():
    """Contrato preservado: fora do `/me`, a chave legítima continua saindo
    crua, como sempre saiu. Assinar foto de terceiros é decisão da próxima
    fase, não desta correção."""
    admin = _user(role=UserRole.admin)
    alvo = _user()
    alvo.avatar_url = _chave_do_upload(alvo, ".jpg")

    resposta = await _chama("GET", f"/users/{alvo.id}", ator=admin, alvo=alvo)

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["avatar_url"] == alvo.avatar_url


# ── O upload legítimo continua funcionando ──────────────────────


@pytest.mark.asyncio
async def test_upload_continua_gravando_e_assinando_a_propria_foto(
    settings_com_upload_dir, tmp_path
):
    cliente = _user(avatar_url=_URL_EXTERNA)

    resposta = await _chama(
        "POST",
        "/users/me/avatar",
        ator=cliente,
        alvo=cliente,
        files={"file": ("eu.png", b"\x89PNG fake", "image/png")},
    )

    assert resposta.status_code == 200, resposta.text
    assert cliente.avatar_url == _chave_do_upload(cliente, ".png")
    assert (tmp_path / "avatars" / f"{cliente.id}.png").read_bytes() == b"\x89PNG fake"
    link = resposta.json()["avatar_url"]
    token = link.removeprefix("/api/v1/files/")
    assert storage.read_file_token(token, get_settings()) == cliente.avatar_url


@pytest.mark.asyncio
async def test_upload_continua_recusando_formato_fora_da_lista(settings_com_upload_dir):
    cliente = _user()

    resposta = await _chama(
        "POST",
        "/users/me/avatar",
        ator=cliente,
        alvo=cliente,
        files={"file": ("x.svg", b"<svg/>", "image/svg+xml")},
    )

    assert resposta.status_code == 422
    assert cliente.avatar_url is None
