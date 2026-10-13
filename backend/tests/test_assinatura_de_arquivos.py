"""
Links de arquivo: chave carregada uma vez, token estável por janela, cache privado.

Por que este arquivo existe: medido em 13/10/2026, cada `create_file_token`
custava ~60 ms — não pela assinatura RS256 (~1 ms), mas por reinterpretar e
validar a chave PEM a cada chamada. Cem fotos numa lista seriam seis segundos.

O que se prende aqui:

1. **A chave é interpretada uma vez** por conteúdo de PEM, e não por assinatura.
2. **Mesmo arquivo, mesma versão, mesma janela → mesmo token.** É o que deixa o
   navegador reaproveitar a imagem e o processo não assinar de novo.
3. **A janela nunca alonga a validade:** `exp <= agora + TTL`, sempre.
4. **Conteúdo novo → URL nova.** A troca da própria foto com a MESMA extensão
   sobrescreve a mesma chave; sem a versão no token, a URL sairia idêntica e a
   tela mostraria a foto antiga.
5. **`/files` responde `Cache-Control: private`**, com `max-age` que não passa
   da validade restante do token.

O relógio é o `storage._agora`, trocado por monkeypatch — a janela é aritmética
sobre ele, e testar com o relógio real deixaria o caso de "virada de janela"
dependente de sorte.
"""

import os
import time

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt

from app.core.config import get_settings
from app.main import app
from app.services import storage

_JANELA = storage._JANELA_DO_TOKEN


@pytest.fixture()
def settings(tmp_path):
    s = get_settings()
    original = s.upload_dir
    s.upload_dir = str(tmp_path)
    yield s
    s.upload_dir = original


@pytest.fixture(autouse=True)
def _caches_limpos():
    storage._chave_jwt.cache_clear()
    storage._assina_token_de_arquivo.cache_clear()
    yield
    storage._chave_jwt.cache_clear()
    storage._assina_token_de_arquivo.cache_clear()


@pytest.fixture()
def relogio(monkeypatch):
    """Relógio controlado: começa no meio de uma janela, longe das bordas."""
    estado = {"agora": 1_800_000_000 - (1_800_000_000 % _JANELA) + 100}
    monkeypatch.setattr(storage, "_agora", lambda: estado["agora"])
    return estado


def _claims(token, s):
    return jwt.get_unverified_claims(token)


async def _grava(s, key, conteudo=b"x"):
    await storage.upload_file(conteudo, key, "image/png", s)


# ── 1. A chave é interpretada uma vez ──────────────────────────


def test_cem_assinaturas_interpretam_a_chave_uma_vez(settings, monkeypatch):
    chamadas = []
    real = storage.jwk.construct

    def _espiao(*args, **kwargs):
        chamadas.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(storage.jwk, "construct", _espiao)

    for i in range(100):
        storage.create_file_token(f"tickets/t/{i}.pdf", settings)

    assert len(chamadas) == 1


def test_verificar_tambem_nao_reinterpreta_a_chave_publica(settings, monkeypatch):
    token = storage.create_file_token("tickets/t/a.pdf", settings)
    chamadas = []
    real = storage.jwk.construct

    def _espiao(*args, **kwargs):
        chamadas.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(storage.jwk, "construct", _espiao)
    for _ in range(50):
        storage.read_file_token(token, settings)

    assert len(chamadas) <= 1


def test_outra_chave_na_configuracao_e_outra_entrada_no_cache(settings):
    """O cache é por CONTEÚDO do PEM: trocar a chave não reaproveita a velha."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    outra = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        .private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        .decode()
    )
    primeira = storage._chave_jwt(settings.get_private_key(), settings.jwt_algorithm)
    segunda = storage._chave_jwt(outra, settings.jwt_algorithm)

    assert primeira is not segunda
    assert storage._chave_jwt.cache_info().currsize == 2


# ── 2. Estabilidade dentro da janela ───────────────────────────


@pytest.mark.asyncio
async def test_mesmo_arquivo_na_mesma_janela_gera_o_mesmo_token(settings, relogio):
    await _grava(settings, "avatars/a.png")

    primeiro = storage.create_file_token("avatars/a.png", settings, expires=604800)
    relogio["agora"] += 60
    segundo = storage.create_file_token("avatars/a.png", settings, expires=604800)

    assert primeiro == segundo


@pytest.mark.asyncio
async def test_a_segunda_vez_na_janela_nao_assina_de_novo(settings, relogio, monkeypatch):
    await _grava(settings, "avatars/a.png")
    assinaturas = []
    real = storage.jwt.encode

    def _espiao(*args, **kwargs):
        assinaturas.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(storage.jwt, "encode", _espiao)
    for _ in range(20):
        storage.create_file_token("avatars/a.png", settings, expires=604800)

    assert len(assinaturas) == 1


@pytest.mark.asyncio
async def test_virada_de_janela_gera_token_novo(settings, relogio):
    await _grava(settings, "avatars/a.png")

    antes = storage.create_file_token("avatars/a.png", settings, expires=3600)
    relogio["agora"] += _JANELA
    depois = storage.create_file_token("avatars/a.png", settings, expires=3600)

    assert antes != depois


@pytest.mark.asyncio
async def test_arquivos_diferentes_nunca_compartilham_token(settings, relogio):
    await _grava(settings, "avatars/a.png")
    await _grava(settings, "avatars/b.png")

    a = storage.create_file_token("avatars/a.png", settings)
    b = storage.create_file_token("avatars/b.png", settings)

    assert a != b
    assert storage.read_file_token(a, settings) == "avatars/a.png"
    assert storage.read_file_token(b, settings) == "avatars/b.png"


def test_token_de_arquivo_e_de_lote_nao_se_confundem(settings, relogio):
    arquivo = storage.create_file_token("tickets/t/a.pdf", settings)
    lote = storage.create_archive_token("tickets/t/a.pdf", ["x"], settings)

    assert arquivo != lote
    with pytest.raises(storage.StorageError):
        storage.read_file_token(lote, settings)
    with pytest.raises(storage.StorageError):
        storage.read_archive_token(arquivo, settings)


# ── 3. A janela nunca alonga a validade ────────────────────────


@pytest.mark.parametrize("ttl", [3600, 604800, 2 * _JANELA])
@pytest.mark.parametrize("deslocamento", [0, 1, _JANELA // 2, _JANELA - 1])
def test_validade_nunca_passa_do_ttl_configurado(settings, relogio, ttl, deslocamento):
    relogio["agora"] = relogio["agora"] - (relogio["agora"] % _JANELA) + deslocamento
    agora = relogio["agora"]

    claims = _claims(storage.create_file_token("tickets/t/a.pdf", settings, expires=ttl), settings)

    assert claims["exp"] <= agora + ttl
    # E a janela tira no máximo uma janela da validade — nunca a zera.
    assert claims["exp"] - agora > ttl - _JANELA
    assert claims["iat"] <= agora


@pytest.mark.parametrize("ttl", [-10, 0, 1, 60, 2 * _JANELA - 1])
def test_ttl_curto_mantem_o_comportamento_sem_janela(settings, relogio, ttl):
    """Abaixo de duas janelas a janela comeria a validade — fica como era."""
    agora = relogio["agora"]
    claims = _claims(storage.create_file_token("tickets/t/a.pdf", settings, expires=ttl), settings)

    assert claims["iat"] == agora
    assert claims["exp"] == agora + ttl


def test_token_da_janela_vencida_continua_recusado(settings, relogio):
    """Volta o relógio para emitir um token cuja janela inteira já passou: o
    memo não pode ressuscitá-lo, e a verificação usa o relógio real."""
    relogio["agora"] = int(time.time()) - 3600 - 2 * _JANELA
    vencido = storage.create_file_token("tickets/t/a.pdf", settings, expires=3600)

    with pytest.raises(storage.StorageError):
        storage.read_file_token(vencido, settings)


def test_token_adulterado_continua_recusado(settings):
    token = storage.create_file_token("tickets/t/a.pdf", settings)
    cabecalho, corpo, assinatura = token.split(".")
    adulterado = ".".join([cabecalho, corpo, assinatura[:-4] + "AAAA"])

    with pytest.raises(storage.StorageError):
        storage.read_file_token(adulterado, settings)


# ── 4. Conteúdo novo → URL nova ────────────────────────────────


@pytest.mark.asyncio
async def test_sobrescrever_a_mesma_chave_muda_o_token(settings, relogio):
    """A troca da própria foto com a mesma extensão grava na MESMA chave."""
    await _grava(settings, "avatars/a.png", b"foto velha")
    antes = storage.create_file_token("avatars/a.png", settings, expires=604800)

    caminho = storage.resolve_path("avatars/a.png", settings)
    mtime_antes = caminho.stat().st_mtime_ns
    await _grava(settings, "avatars/a.png", b"foto nova")
    if caminho.stat().st_mtime_ns == mtime_antes:  # sistema de arquivos de resolução grossa
        os.utime(caminho, ns=(mtime_antes + 1_000_000, mtime_antes + 1_000_000))

    depois = storage.create_file_token("avatars/a.png", settings, expires=604800)

    assert antes != depois


def test_arquivo_inexistente_tambem_gera_token_estavel(settings, relogio):
    a = storage.create_file_token("tickets/t/nunca-gravado.pdf", settings)
    b = storage.create_file_token("tickets/t/nunca-gravado.pdf", settings)

    assert a == b


# ── 5. /files: cache privado, sem perder a proteção ────────────


async def _baixa(token, **params):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.get(f"/api/v1/files/{token}", params=params)


def _max_age(resposta):
    partes = [p.strip() for p in resposta.headers["cache-control"].split(",")]
    assert "private" in partes
    assert "public" not in partes
    assert "immutable" not in partes
    return int(next(p for p in partes if p.startswith("max-age=")).split("=")[1])


@pytest.mark.asyncio
async def test_files_responde_cache_privado_dentro_da_validade(settings):
    await _grava(settings, "tickets/t/foto.png")
    token = storage.create_file_token("tickets/t/foto.png", settings, expires=3600)
    restante = _claims(token, settings)["exp"] - int(time.time())

    r = await _baixa(token)

    assert r.status_code == 200
    assert 0 < _max_age(r) <= restante


@pytest.mark.asyncio
async def test_link_longo_de_avatar_tem_cache_limitado_ao_teto(settings):
    await _grava(settings, "avatars/a.png")
    token = storage.create_file_token("avatars/a.png", settings, expires=604800)

    r = await _baixa(token)

    assert r.status_code == 200
    assert _max_age(r) <= settings.file_url_expires_seconds


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "params"),
    [
        ("tickets/t/foto.png", {}),
        ("tickets/t/laudo.pdf", {}),
        ("tickets/t/nota.txt", {}),
        ("tickets/t/planilha.zip", {}),
        ("tickets/t/foto.png", {"download": "true"}),
    ],
    ids=["imagem", "pdf", "txt", "binario", "download-forcado"],
)
async def test_protecoes_continuam_em_toda_resposta(settings, key, params):
    await _grava(settings, key)
    token = storage.create_file_token(key, settings)

    r = await _baixa(token, **params)

    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert r.headers["referrer-policy"] == "no-referrer"
    _max_age(r)


@pytest.mark.asyncio
async def test_link_ainda_valido_continua_abrindo_depois_do_cache(settings):
    await _grava(settings, "avatars/a.png", b"\x89PNG")
    url = await storage.get_presigned_url("avatars/a.png", settings, expires=604800)

    r = await _baixa(url.rsplit("/", 1)[1])

    assert r.status_code == 200
    assert r.content == b"\x89PNG"
