"""
A própria foto: remover, trocar sem deixar órfão, e sumir na anonimização.

O formato da chave é o de `test_avatar_url_so_pelo_upload.py`:
`avatars/{id}{.jpg|.png|.gif|.webp}`, e só a chave LEGÍTIMA do próprio
usuário é tocada no disco. Uma referência gravada antes do PR #85 (URL externa,
chave de outra conta) nunca vira `delete_file` — senão a remoção da minha foto
apagaria a de outra pessoa.

Os arquivos vão para um `upload_dir` temporário de verdade: o que se cobra é
o arquivo existir ou não depois da requisição, e não só que uma função foi
chamada. O `delete_file` é espionado por cima do real, para provar também
QUAL chave ele recebeu.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from app.models.models import AuditAction, AuditLog, UserRole, UserStatus
from app.services import storage

_PNG = b"\x89PNG velho"
_UM_BYTE_A_MAIS = 5 * 1024 * 1024 + 1


def _user(role=UserRole.client, avatar_url=None):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = "pessoa@test.com"
    u.name = "Nome Original"
    u.role = role
    u.status = UserStatus.active
    u.phone = "+5581999999999"
    u.department = "TI"
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


class _Sessao:
    """Sessão falsa que guarda o que foi adicionado e quantas vezes comitou."""

    def __init__(self, alvo, *, commit_falha=False):
        self.alvo = alvo
        self.adicionados = []
        self.commits = 0
        self.commit_falha = commit_falha

    async def execute(self, *args, **kwargs):
        resultado = MagicMock()
        resultado.scalar_one_or_none.return_value = self.alvo
        return resultado

    def add(self, obj):
        self.adicionados.append(obj)

    async def commit(self):
        if self.commit_falha:
            raise RuntimeError("banco fora do ar")
        self.commits += 1

    refresh = AsyncMock()

    def auditorias(self, acao):
        return [o for o in self.adicionados if isinstance(o, AuditLog) and o.action == acao]


@pytest.fixture(autouse=True)
def _limpa_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def disco(tmp_path):
    settings = get_settings()
    original = settings.upload_dir
    settings.upload_dir = str(tmp_path)
    yield tmp_path
    settings.upload_dir = original


@pytest.fixture()
def apagados(monkeypatch):
    """Espiona `storage.delete_file` sem trocar o comportamento real."""
    chamadas: list[str] = []
    real = storage.delete_file

    async def _espiao(key, settings):
        chamadas.append(key)
        await real(key, settings)

    monkeypatch.setattr(storage, "delete_file", _espiao)
    return chamadas


def _grava(disco: Path, chave: str, conteudo: bytes = _PNG) -> Path:
    caminho = disco / chave
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(conteudo)
    return caminho


async def _chama(metodo, caminho, *, ator, sessao, **kwargs):
    from app.core.database import get_db
    from app.core.security import get_current_user

    async def _db():
        yield sessao

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: ator
    transporte = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://t") as cliente:
        return await cliente.request(metodo, f"/api/v1{caminho}", **kwargs)


# ── DELETE /users/me/avatar ─────────────────────────────────────


@pytest.mark.asyncio
async def test_remover_a_propria_foto_apaga_o_arquivo_e_zera_a_referencia(disco, apagados):
    eu = _user()
    chave = f"avatars/{eu.id}.png"
    eu.avatar_url = chave
    arquivo = _grava(disco, chave)
    sessao = _Sessao(eu)

    resposta = await _chama("DELETE", "/users/me/avatar", ator=eu, sessao=sessao)

    assert resposta.status_code == 204, resposta.text
    assert resposta.content == b""
    assert eu.avatar_url is None
    assert not arquivo.exists()
    assert apagados == [chave]
    assert sessao.commits == 1
    assert len(sessao.auditorias(AuditAction.update)) == 1


@pytest.mark.asyncio
async def test_remover_sem_foto_e_204_e_nao_toca_em_nada(disco, apagados):
    eu = _user()
    sessao = _Sessao(eu)

    primeira = await _chama("DELETE", "/users/me/avatar", ator=eu, sessao=sessao)
    segunda = await _chama("DELETE", "/users/me/avatar", ator=eu, sessao=sessao)

    assert primeira.status_code == 204
    assert segunda.status_code == 204
    assert eu.avatar_url is None
    assert apagados == []
    # Nada mudou: nada a gravar, nada a auditar.
    assert sessao.commits == 0
    assert sessao.adicionados == []


@pytest.mark.asyncio
async def test_remover_duas_vezes_seguidas_e_idempotente(disco, apagados):
    eu = _user()
    eu.avatar_url = f"avatars/{eu.id}.jpg"
    _grava(disco, eu.avatar_url)
    sessao = _Sessao(eu)

    primeira = await _chama("DELETE", "/users/me/avatar", ator=eu, sessao=sessao)
    segunda = await _chama("DELETE", "/users/me/avatar", ator=eu, sessao=sessao)

    assert (primeira.status_code, segunda.status_code) == (204, 204)
    assert sessao.commits == 1


@pytest.mark.asyncio
async def test_remover_quando_o_arquivo_ja_sumiu_do_disco_nao_trava(disco, apagados):
    """O volume perdeu o arquivo, mas a linha ainda aponta para ele: a remoção
    precisa funcionar mesmo assim, senão a pessoa nunca mais limpa a foto."""
    eu = _user()
    chave = f"avatars/{eu.id}.webp"
    eu.avatar_url = chave
    sessao = _Sessao(eu)

    resposta = await _chama("DELETE", "/users/me/avatar", ator=eu, sessao=sessao)

    assert resposta.status_code == 204
    assert eu.avatar_url is None
    assert apagados == [chave]


@pytest.mark.asyncio
async def test_remover_sem_autenticacao_e_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
        resposta = await cliente.delete("/api/v1/users/me/avatar")
    assert resposta.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("tipo", ["chave-de-outra-conta", "url-externa"])
async def test_referencia_indevida_e_zerada_sem_apagar_arquivo_de_ninguem(tipo, disco, apagados):
    """Decisão: a referência indevida é da PRÓPRIA linha de quem pediu a
    remoção, então ela é zerada — mas nenhum arquivo é apagado por ela."""
    eu = _user()
    outra = uuid.uuid4()
    arquivo_alheio = _grava(disco, f"avatars/{outra}.png")
    eu.avatar_url = (
        f"avatars/{outra}.png"
        if tipo == "chave-de-outra-conta"
        else "https://rastreador.example/p.png"
    )
    sessao = _Sessao(eu)

    resposta = await _chama("DELETE", "/users/me/avatar", ator=eu, sessao=sessao)

    assert resposta.status_code == 204
    assert eu.avatar_url is None
    assert apagados == []
    assert arquivo_alheio.read_bytes() == _PNG


@pytest.mark.asyncio
async def test_remover_nao_aceita_chave_vinda_do_cliente(disco, apagados):
    """Não há corpo nem parâmetro: o que vier na requisição é ignorado."""
    eu = _user()
    outra = uuid.uuid4()
    arquivo_alheio = _grava(disco, f"avatars/{outra}.png")
    sessao = _Sessao(eu)

    resposta = await _chama(
        "DELETE",
        f"/users/me/avatar?key=avatars/{outra}.png",
        ator=eu,
        sessao=sessao,
    )

    assert resposta.status_code == 204
    assert apagados == []
    assert arquivo_alheio.exists()


# ── POST /users/me/avatar: troca sem órfão ──────────────────────


async def _envia(eu, sessao, nome, conteudo, tipo):
    return await _chama(
        "POST",
        "/users/me/avatar",
        ator=eu,
        sessao=sessao,
        files={"file": (nome, conteudo, tipo)},
    )


@pytest.mark.asyncio
async def test_trocar_png_por_jpg_apaga_o_png(disco, apagados):
    eu = _user()
    antigo = f"avatars/{eu.id}.png"
    eu.avatar_url = antigo
    arquivo_antigo = _grava(disco, antigo)
    sessao = _Sessao(eu)

    resposta = await _envia(eu, sessao, "nova.jpg", b"\xff\xd8 novo", "image/jpeg")

    assert resposta.status_code == 200, resposta.text
    assert eu.avatar_url == f"avatars/{eu.id}.jpg"
    assert (disco / "avatars" / f"{eu.id}.jpg").read_bytes() == b"\xff\xd8 novo"
    assert not arquivo_antigo.exists()
    assert apagados == [antigo]


@pytest.mark.asyncio
async def test_trocar_png_por_png_sobrescreve_e_nao_apaga_o_novo(disco, apagados):
    eu = _user()
    chave = f"avatars/{eu.id}.png"
    eu.avatar_url = chave
    _grava(disco, chave)
    sessao = _Sessao(eu)

    resposta = await _envia(eu, sessao, "nova.png", b"\x89PNG novo", "image/png")

    assert resposta.status_code == 200, resposta.text
    assert (disco / chave).read_bytes() == b"\x89PNG novo"
    assert apagados == []


@pytest.mark.asyncio
async def test_primeira_foto_nao_apaga_nada(disco, apagados):
    eu = _user()
    sessao = _Sessao(eu)

    resposta = await _envia(eu, sessao, "eu.gif", b"GIF89a", "image/gif")

    assert resposta.status_code == 200, resposta.text
    assert apagados == []


@pytest.mark.asyncio
async def test_troca_nunca_apaga_arquivo_apontado_por_referencia_indevida(disco, apagados):
    eu = _user()
    outra = uuid.uuid4()
    arquivo_alheio = _grava(disco, f"avatars/{outra}.png")
    eu.avatar_url = f"avatars/{outra}.png"
    sessao = _Sessao(eu)

    resposta = await _envia(eu, sessao, "eu.jpg", b"\xff\xd8", "image/jpeg")

    assert resposta.status_code == 200, resposta.text
    assert eu.avatar_url == f"avatars/{eu.id}.jpg"
    assert apagados == []
    assert arquivo_alheio.read_bytes() == _PNG


@pytest.mark.asyncio
async def test_falha_ao_gravar_o_novo_preserva_a_foto_anterior(disco, apagados, monkeypatch):
    eu = _user()
    antigo = f"avatars/{eu.id}.png"
    eu.avatar_url = antigo
    arquivo_antigo = _grava(disco, antigo)
    sessao = _Sessao(eu)

    async def _falha(*args, **kwargs):
        raise storage.StorageError("volume sem espaço")

    monkeypatch.setattr(storage, "upload_file", _falha)

    resposta = await _envia(eu, sessao, "nova.jpg", b"\xff\xd8", "image/jpeg")

    assert resposta.status_code >= 500
    assert eu.avatar_url == antigo
    assert arquivo_antigo.read_bytes() == _PNG
    assert apagados == []
    assert sessao.commits == 0


@pytest.mark.asyncio
async def test_falha_ao_gravar_no_banco_nao_apaga_a_foto_anterior(disco, apagados):
    """O arquivo novo já foi gravado, mas o banco não confirmou: a linha
    continua apontando para o antigo, então o antigo NÃO pode sumir."""
    eu = _user()
    antigo = f"avatars/{eu.id}.png"
    eu.avatar_url = antigo
    arquivo_antigo = _grava(disco, antigo)
    sessao = _Sessao(eu, commit_falha=True)

    resposta = await _envia(eu, sessao, "nova.jpg", b"\xff\xd8", "image/jpeg")

    assert resposta.status_code >= 500
    assert arquivo_antigo.read_bytes() == _PNG
    assert apagados == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tipo", "extensao"),
    [("image/jpeg", ".jpg"), ("image/png", ".png"), ("image/gif", ".gif"), ("image/webp", ".webp")],
)
async def test_upload_continua_aceitando_os_quatro_formatos(tipo, extensao, disco):
    eu = _user()
    sessao = _Sessao(eu)

    resposta = await _envia(eu, sessao, f"eu{extensao}", b"bytes", tipo)

    assert resposta.status_code == 200, resposta.text
    assert eu.avatar_url == f"avatars/{eu.id}{extensao}"
    assert (disco / "avatars" / f"{eu.id}{extensao}").exists()


@pytest.mark.asyncio
async def test_upload_continua_recusando_formato_invalido(disco, apagados):
    eu = _user()
    antigo = f"avatars/{eu.id}.png"
    eu.avatar_url = antigo
    sessao = _Sessao(eu)

    resposta = await _envia(eu, sessao, "x.svg", b"<svg/>", "image/svg+xml")

    assert resposta.status_code == 422
    assert eu.avatar_url == antigo
    assert apagados == []


@pytest.mark.asyncio
async def test_upload_continua_recusando_acima_de_5mb(disco, apagados):
    eu = _user()
    antigo = f"avatars/{eu.id}.png"
    eu.avatar_url = antigo
    sessao = _Sessao(eu)

    resposta = await _envia(eu, sessao, "grande.png", b"\0" * _UM_BYTE_A_MAIS, "image/png")

    assert resposta.status_code == 413, resposta.text
    assert eu.avatar_url == antigo
    assert apagados == []


# ── Anonimização ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anonimizar_apaga_o_arquivo_da_foto(disco, apagados):
    admin = _user(role=UserRole.admin)
    alvo = _user()
    chave = f"avatars/{alvo.id}.png"
    alvo.avatar_url = chave
    arquivo = _grava(disco, chave)
    sessao = _Sessao(alvo)

    resposta = await _chama("POST", f"/users/{alvo.id}/anonymize", ator=admin, sessao=sessao)

    assert resposta.status_code == 200, resposta.text
    assert not arquivo.exists()
    assert apagados == [chave]
    # O resto da anonimização continua igual.
    assert alvo.avatar_url is None
    assert alvo.status == UserStatus.anonymized
    assert alvo.name.startswith("Usuário Anonimizado")
    assert alvo.email.endswith("@anonymized.invalid")
    assert alvo.phone is None
    assert alvo.department is None
    assert len(sessao.auditorias(AuditAction.anonymize)) == 1


@pytest.mark.asyncio
async def test_anonimizar_sem_foto_nao_apaga_nada(disco, apagados):
    admin = _user(role=UserRole.admin)
    alvo = _user()
    sessao = _Sessao(alvo)

    resposta = await _chama("POST", f"/users/{alvo.id}/anonymize", ator=admin, sessao=sessao)

    assert resposta.status_code == 200, resposta.text
    assert apagados == []
    assert alvo.status == UserStatus.anonymized


@pytest.mark.asyncio
async def test_anonimizar_com_referencia_indevida_nao_apaga_arquivo_alheio(disco, apagados):
    admin = _user(role=UserRole.admin)
    alvo = _user()
    outra = uuid.uuid4()
    arquivo_alheio = _grava(disco, f"avatars/{outra}.png")
    alvo.avatar_url = f"avatars/{outra}.png"
    sessao = _Sessao(alvo)

    resposta = await _chama("POST", f"/users/{alvo.id}/anonymize", ator=admin, sessao=sessao)

    assert resposta.status_code == 200, resposta.text
    assert apagados == []
    assert arquivo_alheio.exists()
    assert alvo.avatar_url is None


@pytest.mark.asyncio
async def test_anonimizacao_recusada_nao_apaga_a_foto(disco, apagados):
    """Técnico não anonimiza admin (403): a foto não pode ir embora antes da
    guarda decidir."""
    tecnico = _user(role=UserRole.technician)
    alvo = _user(role=UserRole.admin)
    chave = f"avatars/{alvo.id}.png"
    alvo.avatar_url = chave
    arquivo = _grava(disco, chave)
    sessao = _Sessao(alvo)

    resposta = await _chama("POST", f"/users/{alvo.id}/anonymize", ator=tecnico, sessao=sessao)

    assert resposta.status_code == 403
    assert arquivo.exists()
    assert apagados == []


# ── Gravação atômica ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gravacao_que_falha_no_meio_nao_corrompe_o_arquivo_existente(disco, monkeypatch):
    """A troca com a MESMA extensão sobrescreve a mesma chave. Se a escrita
    falhar no meio (disco cheio), o arquivo anterior tem que sobreviver
    inteiro — senão a pessoa fica com uma foto truncada."""
    settings = get_settings()
    chave = f"avatars/{uuid.uuid4()}.png"
    arquivo = _grava(disco, chave)

    import app.services.storage as modulo

    def _falha(*args, **kwargs):
        raise OSError("No space left on device")

    monkeypatch.setattr(modulo.os, "replace", _falha)

    with pytest.raises(storage.StorageError):
        await storage.upload_file(b"\x89PNG novo", chave, "image/png", settings)

    assert arquivo.read_bytes() == _PNG
    sobras = [p.name for p in arquivo.parent.iterdir() if p.name != arquivo.name]
    assert sobras == []
