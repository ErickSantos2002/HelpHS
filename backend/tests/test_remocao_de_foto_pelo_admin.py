"""
O admin tira a foto de perfil de outra conta (Fase 3A).

`POST /users/{id}/avatar/remove`, só admin, com justificativa obrigatória.
Nada da requisição escolhe o arquivo: a chave sai da linha do alvo e só vale
se for a legítima dele. Os arquivos vão para um `upload_dir` temporário de
verdade — o que se cobra é o arquivo existir ou não no fim, não só que uma
função foi chamada.

A concorrência com o upload do dono tem dois níveis de prova: aqui, com a
sessão falsa encenando cada ordem possível; e em
`test_remocao_de_foto_concorrencia_postgres.py`, com duas transações reais
disputando a trava da linha.
"""

import uuid
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from app.models.models import AuditAction, AuditLog, UserRole, UserStatus
from app.services import storage

_PNG = b"\x89PNG velho"
_NOVA = b"\x89PNG nova"
_MOTIVO = "Foto com conteúdo impróprio, denúncia do cliente."
_CAMINHO = "/users/{}/avatar/remove"


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
    u.created_at = datetime.now(UTC) - timedelta(days=30)
    u.updated_at = datetime.now(UTC) - timedelta(days=1)
    return u


class _Sessao:
    """Sessão falsa: guarda o que foi adicionado, as consultas e os commits.

    `ao_travar` roda quando a consulta da linha volta (o instante em que a
    trava seria concedida); `ao_comitar` roda dentro do commit. É por eles que
    os testes de concorrência encenam o que o outro pedido fez no meio.
    """

    def __init__(self, alvo, *, commit_falha=False, ao_travar=None, ao_comitar=None):
        self.alvo = alvo
        self.adicionados = []
        self.consultas = []
        self.commits = 0
        self.rollbacks = 0
        self.commit_falha = commit_falha
        self.ao_travar = ao_travar
        self.ao_comitar = ao_comitar

    async def execute(self, stmt, *args, **kwargs):
        self.consultas.append(stmt)
        if self.ao_travar:
            self.ao_travar()
        resultado = MagicMock()
        resultado.scalar_one_or_none.return_value = self.alvo
        return resultado

    def add(self, obj):
        self.adicionados.append(obj)

    async def commit(self):
        if self.ao_comitar:
            self.ao_comitar()
        if self.commit_falha:
            raise RuntimeError("banco fora do ar")
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    refresh = AsyncMock()

    def auditorias(self):
        return [o for o in self.adicionados if isinstance(o, AuditLog)]


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


def _arquivos(disco: Path) -> list[str]:
    """Tudo o que sobrou no volume, isolados e temporários inclusive."""
    return sorted(p.relative_to(disco).as_posix() for p in disco.rglob("*") if p.is_file())


async def _chama(caminho, *, ator, sessao, metodo="POST", **kwargs):
    from app.core.database import get_db
    from app.core.security import get_current_user

    async def _db():
        yield sessao

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: ator
    transporte = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://t") as cliente:
        return await cliente.request(metodo, f"/api/v1{caminho}", **kwargs)


def _versao(alvo) -> str:
    """O `updated_at` que a tela do admin tinha: o token de versão do pedido."""
    return alvo.updated_at.isoformat()


async def _remove(alvo, sessao, *, ator=None, motivo=_MOTIVO, versao=None, **kwargs):
    ator = ator or _user(UserRole.admin)
    return await _chama(
        _CAMINHO.format(alvo.id),
        ator=ator,
        sessao=sessao,
        json={"justification": motivo, "expected_updated_at": versao or _versao(alvo)},
        **kwargs,
    )


def _com_foto(disco: Path, extensao: str = ".png"):
    alvo = _user()
    alvo.avatar_url = f"avatars/{alvo.id}{extensao}"
    arquivo = _grava(disco, alvo.avatar_url)
    return alvo, arquivo


# ── O caminho feliz ─────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("papel_do_alvo", [UserRole.client, UserRole.technician, UserRole.admin])
async def test_admin_remove_a_foto_de_outra_conta(papel_do_alvo, disco, apagados):
    alvo, arquivo = _com_foto(disco)
    alvo.role = papel_do_alvo
    sessao = _Sessao(alvo)

    resposta = await _remove(alvo, sessao)

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["avatar_url"] is None
    assert resposta.json()["id"] == str(alvo.id)
    assert alvo.avatar_url is None
    assert not arquivo.exists()
    # Nada sobra no volume: nem a chave pública, nem o nome isolado.
    assert _arquivos(disco) == []
    assert sessao.commits == 1
    assert sessao.rollbacks == 0


@pytest.mark.asyncio
async def test_a_exclusao_fisica_vem_depois_do_commit_e_pelo_nome_isolado(disco, apagados):
    """No commit a chave pública já está vazia (o arquivo foi isolado), mas o
    conteúdo ainda existe; só depois dele algo é apagado — e nunca a chave
    pública."""
    alvo, arquivo = _com_foto(disco)
    no_commit: dict = {}

    def _no_commit():
        no_commit["publica_existe"] = arquivo.exists()
        no_commit["arquivos"] = _arquivos(disco)
        no_commit["apagados"] = list(apagados)

    sessao = _Sessao(alvo, ao_comitar=_no_commit)

    resposta = await _remove(alvo, sessao)

    assert resposta.status_code == 200
    assert no_commit["publica_existe"] is False
    assert len(no_commit["arquivos"]) == 1
    assert no_commit["arquivos"][0].endswith(".removendo")
    assert no_commit["apagados"] == []
    assert apagados == [no_commit["arquivos"][0]]
    assert alvo.avatar_url not in apagados


@pytest.mark.asyncio
async def test_a_trava_da_linha_e_pedida(disco, apagados):
    alvo, _ = _com_foto(disco)
    sessao = _Sessao(alvo)

    await _remove(alvo, sessao)

    consulta = sessao.consultas[0]
    assert consulta._for_update_arg is not None
    assert consulta.get_execution_options().get("populate_existing") is True


# ── Permissões ──────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", [UserRole.technician, UserRole.client])
async def test_tecnico_e_cliente_recebem_403_e_nada_muda(papel, disco, apagados):
    alvo, arquivo = _com_foto(disco)
    chave = alvo.avatar_url
    sessao = _Sessao(alvo)

    resposta = await _remove(alvo, sessao, ator=_user(papel))

    assert resposta.status_code == 403
    assert alvo.avatar_url == chave
    assert arquivo.read_bytes() == _PNG
    assert sessao.consultas == []
    assert sessao.adicionados == []
    assert apagados == []


@pytest.mark.asyncio
async def test_sem_autenticacao_e_401(disco):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
        resposta = await cliente.post(
            f"/api/v1/users/{uuid.uuid4()}/avatar/remove",
            json={"justification": _MOTIVO, "expected_updated_at": datetime.now(UTC).isoformat()},
        )
    assert resposta.status_code == 401


@pytest.mark.asyncio
async def test_usuario_inexistente_e_404(disco, apagados):
    sessao = _Sessao(None)

    resposta = await _chama(
        _CAMINHO.format(uuid.uuid4()),
        ator=_user(UserRole.admin),
        sessao=sessao,
        json={"justification": _MOTIVO, "expected_updated_at": datetime.now(UTC).isoformat()},
    )

    assert resposta.status_code == 404
    assert sessao.adicionados == []
    assert apagados == []


@pytest.mark.asyncio
async def test_a_propria_foto_pela_rota_do_admin_e_400(disco, apagados):
    admin = _user(UserRole.admin)
    admin.avatar_url = f"avatars/{admin.id}.png"
    arquivo = _grava(disco, admin.avatar_url)
    sessao = _Sessao(admin)

    resposta = await _remove(admin, sessao, ator=admin)

    assert resposta.status_code == 400
    assert "perfil" in resposta.json()["detail"]
    assert arquivo.exists()
    assert sessao.consultas == []
    assert sessao.adicionados == []


@pytest.mark.asyncio
async def test_nao_existe_rota_de_upload_em_nome_de_terceiro(disco):
    """Requisito 7: o admin não envia foto por outra pessoa. Nenhuma rota de
    `/users/{id}/avatar` aceita arquivo."""
    alvo = _user()
    sessao = _Sessao(alvo)

    resposta = await _chama(
        f"/users/{alvo.id}/avatar",
        ator=_user(UserRole.admin),
        sessao=sessao,
        files={"file": ("x.png", _NOVA, "image/png")},
    )

    assert resposta.status_code in (404, 405)
    assert _arquivos(disco) == []


# ── Justificativa ───────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corpo",
    [
        None,
        {},
        {"justification": ""},
        {"justification": "     "},
        {"justification": "abcd"},
        {"justification": "  abcd  "},
        {"justification": "x" * 2001},
        {"justification": None},
        {"justification": 12345},
    ],
    ids=[
        "sem-corpo",
        "vazio",
        "string-vazia",
        "so-espacos",
        "4-chars",
        "4-com-espacos",
        "2001-chars",
        "nulo",
        "numero",
    ],
)
async def test_justificativa_invalida_e_422_e_nada_muda(corpo, disco, apagados):
    alvo, arquivo = _com_foto(disco)
    chave = alvo.avatar_url
    sessao = _Sessao(alvo)

    kwargs = {} if corpo is None else {"json": {**corpo, "expected_updated_at": _versao(alvo)}}
    resposta = await _chama(
        _CAMINHO.format(alvo.id), ator=_user(UserRole.admin), sessao=sessao, **kwargs
    )

    assert resposta.status_code == 422
    assert alvo.avatar_url == chave
    assert arquivo.read_bytes() == _PNG
    assert sessao.adicionados == []
    assert apagados == []


@pytest.mark.asyncio
@pytest.mark.parametrize("motivo", ["abcde", "x" * 2000])
async def test_justificativa_nos_limites_e_aceita(motivo, disco, apagados):
    alvo, _ = _com_foto(disco)
    sessao = _Sessao(alvo)

    resposta = await _remove(alvo, sessao, motivo=motivo)

    assert resposta.status_code == 200
    assert sessao.auditorias()[0].new_data["justificativa"] == motivo


@pytest.mark.asyncio
@pytest.mark.parametrize("campo", ["key", "avatar_url", "user_id"])
async def test_campo_alem_da_justificativa_e_recusado(campo, disco, apagados):
    """Nenhuma chave vinda do cliente controla a exclusão: o corpo com um
    campo a mais é recusado, e o arquivo de outra conta que ele nomeia fica."""
    alvo, arquivo = _com_foto(disco)
    outra = uuid.uuid4()
    alheio = _grava(disco, f"avatars/{outra}.png")
    sessao = _Sessao(alvo)

    resposta = await _chama(
        _CAMINHO.format(alvo.id),
        ator=_user(UserRole.admin),
        sessao=sessao,
        json={
            "justification": _MOTIVO,
            "expected_updated_at": _versao(alvo),
            campo: f"avatars/{outra}.png",
        },
    )

    assert resposta.status_code == 422
    assert arquivo.exists()
    assert alheio.exists()
    assert apagados == []


# ── Idempotência e arquivo ausente ──────────────────────────────


@pytest.mark.asyncio
async def test_alvo_sem_foto_e_200_sem_commit_nem_auditoria(disco, apagados):
    alvo = _user()
    sessao = _Sessao(alvo)

    resposta = await _remove(alvo, sessao)

    assert resposta.status_code == 200
    assert resposta.json()["avatar_url"] is None
    assert sessao.commits == 0
    assert sessao.adicionados == []
    assert apagados == []


@pytest.mark.asyncio
async def test_alvo_anonimizado_e_200_sem_mudanca(disco, apagados):
    alvo = _user()
    alvo.status = UserStatus.anonymized
    sessao = _Sessao(alvo)

    resposta = await _remove(alvo, sessao)

    assert resposta.status_code == 200
    assert sessao.commits == 0
    assert sessao.adicionados == []


@pytest.mark.asyncio
async def test_remover_duas_vezes_e_idempotente_com_uma_auditoria(disco, apagados):
    alvo, _ = _com_foto(disco)
    sessao = _Sessao(alvo)

    primeira = await _remove(alvo, sessao)
    segunda = await _remove(alvo, sessao)

    assert (primeira.status_code, segunda.status_code) == (200, 200)
    assert sessao.commits == 1
    assert len(sessao.auditorias()) == 1
    assert _arquivos(disco) == []


@pytest.mark.asyncio
async def test_arquivo_ja_ausente_do_disco_nao_trava(disco, apagados):
    alvo = _user()
    alvo.avatar_url = f"avatars/{alvo.id}.webp"
    sessao = _Sessao(alvo)

    resposta = await _remove(alvo, sessao)

    assert resposta.status_code == 200
    assert alvo.avatar_url is None
    assert apagados == []
    assert sessao.auditorias()[0].new_data["arquivo_encontrado"] is False
    assert sessao.auditorias()[0].new_data["referencia_indevida"] is False


# ── Referência adulterada ───────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tipo",
    ["chave-de-outra-conta", "url-externa", "travessia", "maiuscula", "extensao-estranha"],
)
async def test_referencia_indevida_e_zerada_sem_apagar_arquivo_de_ninguem(tipo, disco, apagados):
    alvo = _user()
    outra = uuid.uuid4()
    alheio = _grava(disco, f"avatars/{outra}.png")
    segredo = _grava(disco, "segredo.txt", b"nao apagar")
    referencias = {
        "chave-de-outra-conta": f"avatars/{outra}.png",
        "url-externa": "https://rastreador.example/p.png?token=abc",
        "travessia": f"avatars/../avatars/{outra}.png",
        "maiuscula": f"AVATARS/{alvo.id}.png",
        "extensao-estranha": f"avatars/{alvo.id}.svg",
    }
    alvo.avatar_url = referencias[tipo]
    sessao = _Sessao(alvo)

    resposta = await _remove(alvo, sessao)

    assert resposta.status_code == 200
    assert alvo.avatar_url is None
    assert apagados == []
    assert alheio.read_bytes() == _PNG
    assert segredo.read_bytes() == b"nao apagar"
    auditoria = sessao.auditorias()[0]
    assert auditoria.new_data["referencia_indevida"] is True
    assert auditoria.new_data["arquivo_encontrado"] is False
    # O valor da referência não vai para a auditoria nem para a resposta.
    assert referencias[tipo] not in repr(auditoria.new_data)
    assert referencias[tipo] not in repr(auditoria.old_data)
    assert referencias[tipo] not in resposta.text


# ── Falhas ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_falha_de_commit_devolve_o_arquivo_e_nao_apaga_nada(disco, apagados):
    alvo, arquivo = _com_foto(disco)
    sessao = _Sessao(alvo, commit_falha=True)

    resposta = await _remove(alvo, sessao)

    assert resposta.status_code == 500
    assert arquivo.read_bytes() == _PNG
    assert _arquivos(disco) == [arquivo.relative_to(disco).as_posix()]
    assert apagados == []
    assert sessao.rollbacks == 1


@pytest.mark.asyncio
async def test_falha_de_commit_nao_sobrescreve_upload_que_entrou_no_meio(disco, apagados):
    """Se um upload gravou a chave depois que a trava caiu, a devolução do
    arquivo isolado não pode passar por cima dele."""
    alvo, arquivo = _com_foto(disco)

    def _upload_no_meio():
        arquivo.write_bytes(_NOVA)

    sessao = _Sessao(alvo, commit_falha=True, ao_comitar=_upload_no_meio)

    resposta = await _remove(alvo, sessao)

    assert resposta.status_code == 500
    assert arquivo.read_bytes() == _NOVA
    assert _arquivos(disco) == [arquivo.relative_to(disco).as_posix()]


@pytest.mark.asyncio
async def test_falha_ao_isolar_o_arquivo_e_erro_sem_mudar_nada(disco, apagados, monkeypatch):
    alvo, arquivo = _com_foto(disco)
    chave = alvo.avatar_url
    sessao = _Sessao(alvo)

    def _rename_falha(*args, **kwargs):
        raise PermissionError("volume somente leitura")

    monkeypatch.setattr(storage.os, "rename", _rename_falha)

    resposta = await _remove(alvo, sessao)

    assert resposta.status_code >= 500
    assert alvo.avatar_url == chave
    assert arquivo.read_bytes() == _PNG
    assert sessao.commits == 0
    assert sessao.adicionados == []


@pytest.mark.asyncio
async def test_falha_na_exclusao_fisica_nao_desfaz_a_remocao(disco, monkeypatch):
    """O disco falhou depois do commit: a linha já está sem foto e a chave
    pública já está vazia — sobra um órfão isolado, com aviso no log, nunca
    uma linha apontando para o vazio nem a foto ainda servida."""
    alvo, arquivo = _com_foto(disco)
    sessao = _Sessao(alvo)

    def _unlink_falha(self, *args, **kwargs):
        raise PermissionError("disco com defeito")

    monkeypatch.setattr(storage.Path, "unlink", _unlink_falha)

    resposta = await _remove(alvo, sessao)

    assert resposta.status_code == 200
    assert alvo.avatar_url is None
    assert not arquivo.exists()
    sobras = _arquivos(disco)
    assert len(sobras) == 1 and sobras[0].endswith(".removendo")


# ── Auditoria ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auditoria_registra_ator_alvo_justificativa_e_origem(disco, apagados):
    admin = _user(UserRole.admin)
    alvo, _ = _com_foto(disco)
    sessao = _Sessao(alvo)

    resposta = await _remove(
        alvo,
        sessao,
        ator=admin,
        motivo=f"  {_MOTIVO}  ",
        headers={"user-agent": "Navegador de teste"},
    )

    assert resposta.status_code == 200
    [auditoria] = sessao.auditorias()
    assert auditoria.user_id == admin.id
    assert auditoria.entity_id == alvo.id
    assert auditoria.entity_type == "user"
    assert auditoria.action == AuditAction.update
    assert auditoria.old_data == {"tinha_foto": True}
    assert auditoria.new_data == {
        "operacao": "remocao_de_foto_pelo_admin",
        "justificativa": _MOTIVO,
        "referencia_indevida": False,
        "arquivo_encontrado": True,
    }
    assert auditoria.user_agent == "Navegador de teste"
    assert auditoria.ip_address
    # Nem chave, nem link, nem token.
    texto = repr(auditoria.new_data) + repr(auditoria.old_data)
    assert "avatars/" not in texto
    assert "/files/" not in texto
    assert "token" not in texto.lower()


@pytest.mark.asyncio
async def test_user_agent_gigante_e_cortado_na_coluna(disco, apagados):
    alvo, _ = _com_foto(disco)
    sessao = _Sessao(alvo)

    await _remove(alvo, sessao, headers={"user-agent": "x" * 900})

    assert len(sessao.auditorias()[0].user_agent) == 500


# ── Token de versão ─────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "versao",
    [None, "", "ontem", "2026-10-14T12:00:00"],
    ids=["ausente", "vazia", "lixo", "sem-fuso"],
)
async def test_versao_ausente_ou_invalida_e_422_e_nada_muda(versao, disco, apagados):
    alvo, arquivo = _com_foto(disco)
    sessao = _Sessao(alvo)
    corpo = {"justification": _MOTIVO}
    if versao is not None:
        corpo["expected_updated_at"] = versao

    resposta = await _chama(
        _CAMINHO.format(alvo.id), ator=_user(UserRole.admin), sessao=sessao, json=corpo
    )

    assert resposta.status_code == 422
    assert arquivo.read_bytes() == _PNG
    assert sessao.adicionados == []


@pytest.mark.asyncio
async def test_versao_em_outro_fuso_mas_o_mesmo_instante_vale(disco, apagados):
    alvo, _ = _com_foto(disco)
    sessao = _Sessao(alvo)
    mesmo_instante = alvo.updated_at.astimezone(timezone(timedelta(hours=-3))).isoformat()

    resposta = await _remove(alvo, sessao, versao=mesmo_instante)

    assert resposta.status_code == 200


@pytest.mark.asyncio
async def test_tela_desatualizada_e_409_sem_apagar_a_foto(disco, apagados):
    """O admin abriu a tela, o dono trocou a foto enquanto ele escrevia a
    justificativa, e só então ele confirmou: a foto que está lá não é a que
    ele decidiu remover."""
    alvo, arquivo = _com_foto(disco)
    versao_da_tela = _versao(alvo)
    arquivo.write_bytes(_NOVA)
    alvo.updated_at = datetime.now(UTC)
    sessao = _Sessao(alvo)

    resposta = await _remove(alvo, sessao, versao=versao_da_tela)

    assert resposta.status_code == 409
    assert "tente de novo" in resposta.json()["detail"]
    assert alvo.avatar_url == f"avatars/{alvo.id}.png"
    assert arquivo.read_bytes() == _NOVA
    assert sessao.commits == 0
    assert sessao.adicionados == []
    assert apagados == []


@pytest.mark.asyncio
async def test_alvo_sem_foto_e_200_mesmo_com_versao_velha(disco, apagados):
    """Nada a remover: a versão não importa, e não há o que proteger."""
    alvo = _user()
    sessao = _Sessao(alvo)

    resposta = await _remove(alvo, sessao, versao="2020-01-01T00:00:00+00:00")

    assert resposta.status_code == 200
    assert sessao.adicionados == []


# ── Concorrência com o upload do dono ───────────────────────────


@pytest.mark.asyncio
async def test_linha_alterada_durante_a_espera_pela_trava_e_409_sem_apagar(disco, apagados):
    """O admin esperou a trava de um upload que terminou no meio: a foto que
    está lá agora é nova, e a decisão dele foi tomada antes dela."""
    alvo, arquivo = _com_foto(disco)
    chave = alvo.avatar_url

    def _upload_terminou_no_meio():
        arquivo.write_bytes(_NOVA)
        alvo.updated_at = datetime.now(UTC)

    sessao = _Sessao(alvo, ao_travar=_upload_terminou_no_meio)

    resposta = await _remove(alvo, sessao)

    assert resposta.status_code == 409
    assert "tente de novo" in resposta.json()["detail"]
    assert alvo.avatar_url == chave
    assert arquivo.read_bytes() == _NOVA
    assert _arquivos(disco) == [arquivo.relative_to(disco).as_posix()]
    assert sessao.commits == 0
    assert sessao.rollbacks == 1
    assert sessao.adicionados == []
    assert apagados == []


@pytest.mark.asyncio
async def test_upload_logo_apos_o_commit_nao_e_apagado(disco, apagados):
    """A trava caiu no commit e o dono gravou a MESMA chave antes da exclusão
    física: o que se apaga é o nome isolado, então a foto nova fica."""
    alvo, arquivo = _com_foto(disco)

    def _upload_depois_do_commit():
        arquivo.write_bytes(_NOVA)

    sessao = _Sessao(alvo, ao_comitar=_upload_depois_do_commit)

    resposta = await _remove(alvo, sessao)

    assert resposta.status_code == 200
    assert arquivo.read_bytes() == _NOVA
    assert _arquivos(disco) == [arquivo.relative_to(disco).as_posix()]


@pytest.mark.asyncio
async def test_upload_trava_a_linha_antes_de_gravar_o_arquivo(disco, monkeypatch):
    """Sem esta ordem, o admin podia isolar o arquivo recém-gravado enquanto o
    upload ainda não tinha comitado — e o commit do upload apontaria a linha
    para um arquivo apagado."""
    eu = _user()
    ordem: list[str] = []
    sessao = _Sessao(eu, ao_travar=lambda: ordem.append("trava"))
    real = storage.upload_file

    async def _grava_e_anota(*args, **kwargs):
        ordem.append("grava")
        return await real(*args, **kwargs)

    monkeypatch.setattr(storage, "upload_file", _grava_e_anota)

    resposta = await _chama(
        "/users/me/avatar",
        ator=eu,
        sessao=sessao,
        files={"file": ("nova.png", _NOVA, "image/png")},
    )

    assert resposta.status_code == 200, resposta.text
    assert ordem == ["trava", "grava"]
    consulta = sessao.consultas[0]
    assert consulta._for_update_arg is not None
    assert consulta.get_execution_options().get("populate_existing") is True


@pytest.mark.asyncio
@pytest.mark.parametrize("situacao", [UserStatus.anonymized, UserStatus.inactive])
async def test_upload_em_conta_que_saiu_de_ativa_no_meio_nao_grava(situacao, disco):
    """O `get_current_user` viu a conta ativa; com a trava na mão, ela já foi
    anonimizada (ou desativada). Gravar agora devolveria dado pessoal."""
    eu = _user()
    na_trava = _user()
    na_trava.id = eu.id
    na_trava.status = situacao
    sessao = _Sessao(na_trava)

    resposta = await _chama(
        "/users/me/avatar",
        ator=eu,
        sessao=sessao,
        files={"file": ("nova.png", _NOVA, "image/png")},
    )

    assert resposta.status_code == 403
    assert _arquivos(disco) == []
    assert na_trava.avatar_url is None
    assert sessao.commits == 0


@pytest.mark.asyncio
async def test_upload_para_usuario_sumido_nao_grava_arquivo(disco):
    eu = _user()
    sessao = _Sessao(None)

    resposta = await _chama(
        "/users/me/avatar",
        ator=eu,
        sessao=sessao,
        files={"file": ("nova.png", _NOVA, "image/png")},
    )

    assert resposta.status_code == 404
    assert _arquivos(disco) == []


# ── storage.isola_arquivo / devolve_arquivo ─────────────────────


@pytest.mark.asyncio
async def test_isolar_arquivo_ausente_devolve_none(disco):
    assert await storage.isola_arquivo("avatars/nao-existe.png", get_settings()) is None


@pytest.mark.asyncio
async def test_isolar_recusa_chave_fora_do_volume(disco):
    with pytest.raises(storage.StorageError):
        await storage.isola_arquivo("../fora.png", get_settings())


@pytest.mark.asyncio
async def test_isolar_e_devolver_restaura_o_conteudo(disco):
    _grava(disco, "avatars/a.png")
    settings = get_settings()

    isolado = await storage.isola_arquivo("avatars/a.png", settings)

    assert isolado is not None
    assert isolado.startswith("avatars/.a.png.") and isolado.endswith(".removendo")
    assert not (disco / "avatars/a.png").exists()

    await storage.devolve_arquivo(isolado, "avatars/a.png", settings)

    assert (disco / "avatars/a.png").read_bytes() == _PNG
    assert _arquivos(disco) == ["avatars/a.png"]


@pytest.mark.asyncio
async def test_devolver_em_volume_sem_link_fisico_cai_no_rename(disco, monkeypatch):
    _grava(disco, "avatars/a.png")
    settings = get_settings()
    isolado = await storage.isola_arquivo("avatars/a.png", settings)

    def _sem_link(*args, **kwargs):
        raise OSError(95, "Operation not supported")

    monkeypatch.setattr(storage.os, "link", _sem_link)

    await storage.devolve_arquivo(isolado, "avatars/a.png", settings)

    assert (disco / "avatars/a.png").read_bytes() == _PNG
    assert _arquivos(disco) == ["avatars/a.png"]


@pytest.mark.asyncio
async def test_devolver_sem_link_nao_sobrescreve_arquivo_novo(disco, monkeypatch):
    _grava(disco, "avatars/a.png")
    settings = get_settings()
    isolado = await storage.isola_arquivo("avatars/a.png", settings)
    _grava(disco, "avatars/a.png", _NOVA)

    def _sem_link(*args, **kwargs):
        raise OSError(95, "Operation not supported")

    monkeypatch.setattr(storage.os, "link", _sem_link)

    await storage.devolve_arquivo(isolado, "avatars/a.png", settings)

    assert (disco / "avatars/a.png").read_bytes() == _NOVA
    assert _arquivos(disco) == ["avatars/a.png"]


@pytest.mark.asyncio
async def test_devolver_com_disco_quebrado_nao_levanta(disco, monkeypatch):
    _grava(disco, "avatars/a.png")
    settings = get_settings()
    isolado = await storage.isola_arquivo("avatars/a.png", settings)

    def _falha(*args, **kwargs):
        raise PermissionError("sem permissão")

    monkeypatch.setattr(storage.os, "link", _falha)
    monkeypatch.setattr(storage.os, "rename", _falha)

    await storage.devolve_arquivo(isolado, "avatars/a.png", settings)

    assert (disco / isolado).exists()
