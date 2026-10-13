"""
Baixar todos os anexos do chamado num ZIP — contra banco e disco de verdade.

O desenho (auditoria de 09/10/2026, decisões do operador no mesmo dia):

1. ``POST /tickets/{id}/attachments/archive`` confere o acesso ao chamado como
   a listagem confere, congela os ids dos anexos num token assinado de tipo
   PRÓPRIO, registra o pedido na auditoria (`export`, só ids e contagens) e
   devolve o link mais a lista dos "não verificados", para o aviso da tela.
2. ``GET /files/archive/{token}`` confere de novo cada id e cada arquivo em
   disco. Faltou um: erro, e nenhum ZIP — nunca um ZIP parcial.

O que se prova aqui é o que um mock não alcança: os bytes que saem dentro do
ZIP, os nomes que o descompactador vai gravar no disco de quem baixou e o
temporário que não pode ficar para trás.
"""

import io
import itertools
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.main import app
from app.models.models import Attachment, AuditAction, AuditLog, UserRole
from app.services import storage
from tests import test_anexo_na_conversa as _base
from tests.test_anexo_na_conversa import _chamado, _como, _pessoa

# As fixtures de banco real são as do teste do evento de anexo. Atribuídas, e
# não importadas pelo nome: o pytest só precisa achá-las no módulo, e o import
# direto faz o ruff ler cada parâmetro `db`/`api` como redefinição (F811).
url_do_banco = _base.url_do_banco
conn = _base.conn
db = _base.db
api = _base.api


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    """`upload_dir` numa pasta do teste, e o temporário do ZIP noutra."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    temporarios = tmp_path / "tmp"
    temporarios.mkdir()
    monkeypatch.setenv("TMP", str(temporarios))
    monkeypatch.setenv("TEMP", str(temporarios))
    monkeypatch.setenv("TMPDIR", str(temporarios))
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(temporarios))

    base = get_settings()
    config = base.model_copy(update={"upload_dir": str(uploads)})
    app.dependency_overrides[get_settings] = lambda: config
    yield uploads, temporarios, config
    app.dependency_overrides.pop(get_settings, None)


# Instantes crescentes: dentro da transação do teste o `now()` do banco é o
# mesmo para todas as linhas, e a ordem do ZIP sairia do acaso.
_relogio = itertools.count()


async def _anexo(db, ticket, autor, uploads: Path, nome: str, conteudo: bytes, verificado=True):
    stored = f"{uuid.uuid4()}{Path(nome).suffix or '.bin'}"
    key = f"tickets/{ticket.id}/{stored}"
    destino = uploads / key
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(conteudo)
    a = Attachment(
        id=uuid.uuid4(),
        ticket_id=ticket.id,
        uploaded_by=autor.id,
        original_name=nome,
        stored_name=stored,
        mime_type="application/octet-stream",
        size_bytes=len(conteudo),
        s3_key=key,
        s3_bucket="local",
        virus_scanned=verificado,
        virus_clean=verificado,
        created_at=datetime(2026, 10, 9, 12, tzinfo=UTC) + timedelta(seconds=next(_relogio)),
    )
    db.add(a)
    await db.commit()
    return a


async def _pede(c, ticket_id):
    return await c.post(f"/api/v1/tickets/{ticket_id}/attachments/archive")


def _zip(resposta) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(resposta.content))


# ── O caminho feliz ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_varios_anexos_viram_um_zip_valido_com_os_bytes_certos(db, api, pasta):
    uploads, _, _ = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    await _anexo(db, ticket, dono, uploads, "laudo.pdf", b"%PDF-1 laudo")
    await _anexo(db, ticket, dono, uploads, "foto.png", b"\x89PNG foto")
    _como(dono)

    async with api as c:
        pedido = await _pede(c, ticket.id)
        assert pedido.status_code == 200, pedido.text
        corpo = pedido.json()
        assert corpo["total"] == 2
        assert corpo["nao_verificados"] == []
        assert corpo["url"].startswith("/api/v1/files/archive/")
        r = await c.get(corpo["url"])

    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    disposicao = r.headers["content-disposition"]
    assert disposicao.startswith("attachment;")
    assert f"chamado-{ticket.protocol}-anexos.zip" in disposicao
    assert r.headers["x-content-type-options"] == "nosniff"

    z = _zip(r)
    assert z.testzip() is None
    assert sorted(z.namelist()) == ["foto.png", "laudo.pdf"]
    assert z.read("laudo.pdf") == b"%PDF-1 laudo"
    assert z.read("foto.png") == b"\x89PNG foto"


@pytest.mark.asyncio
async def test_staff_baixa_o_zip_de_qualquer_chamado(db, api, pasta):
    uploads, _, _ = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    tecnico = await _pessoa(db, UserRole.technician, "Bruno Técnico")
    ticket = await _chamado(db, dono)
    await _anexo(db, ticket, dono, uploads, "laudo.pdf", b"x")
    _como(tecnico)

    async with api as c:
        pedido = await _pede(c, ticket.id)
        r = await c.get(pedido.json()["url"])
    assert r.status_code == 200
    assert _zip(r).namelist() == ["laudo.pdf"]


# ── Nomes dentro do ZIP ──────────────────────────────────────


@pytest.mark.asyncio
async def test_nomes_repetidos_nao_se_sobrescrevem(db, api, pasta):
    uploads, _, _ = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    await _anexo(db, ticket, dono, uploads, "laudo.pdf", b"primeiro")
    await _anexo(db, ticket, dono, uploads, "laudo.pdf", b"segundo")
    # Caixa diferente também colide: no Windows e no macOS é o mesmo arquivo.
    await _anexo(db, ticket, dono, uploads, "LAUDO.pdf", b"terceiro")
    _como(dono)

    async with api as c:
        r = await c.get((await _pede(c, ticket.id)).json()["url"])

    z = _zip(r)
    assert z.namelist() == ["laudo.pdf", "laudo (2).pdf", "LAUDO (3).pdf"]
    assert [z.read(n) for n in z.namelist()] == [b"primeiro", b"segundo", b"terceiro"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("original", "esperado"),
    [
        ("../../etc/passwd", "passwd"),
        ("..\\..\\Windows\\win.ini", "win.ini"),
        ("C:\\Users\\vitima\\relatorio.pdf", "relatorio.pdf"),
        ("/abs/caminho/foto.png", "foto.png"),
        # NUL não entra: o Postgres recusa gravá-lo em texto, então não chega aqui.
        ("sino\x07e\x1fseparador.txt", "sinoeseparador.txt"),
        ('a<b>c:d"e|f?g*h.txt', "a_b_c_d_e_f_g_h.txt"),
        ("  .oculto. ", "oculto"),
        ("..", None),
        ("", None),
    ],
)
async def test_nome_inseguro_vira_so_o_nome_do_arquivo(db, api, pasta, original, esperado):
    uploads, _, _ = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    anexo = await _anexo(db, ticket, dono, uploads, original, b"x")
    _como(dono)

    async with api as c:
        r = await c.get((await _pede(c, ticket.id)).json()["url"])

    [nome] = _zip(r).namelist()
    # Sem nome que preste, a reserva é o nome interno (uuid + extensão).
    assert nome == (esperado if esperado is not None else anexo.stored_name)
    assert "/" not in nome and "\\" not in nome and ".." not in nome


# ── O que NÃO pode entrar ────────────────────────────────────


@pytest.mark.asyncio
async def test_zip_leva_so_os_ids_congelados_no_pedido(db, api, pasta):
    """Anexo que chega DEPOIS do pedido não entra no lote já autorizado."""
    uploads, _, _ = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    await _anexo(db, ticket, dono, uploads, "antes.pdf", b"a")
    _como(dono)

    async with api as c:
        pedido = await _pede(c, ticket.id)
        await _anexo(db, ticket, dono, uploads, "depois.pdf", b"b")
        r = await c.get(pedido.json()["url"])

    assert _zip(r).namelist() == ["antes.pdf"]


@pytest.mark.asyncio
async def test_anexo_excluido_depois_do_pedido_nao_gera_zip_parcial(db, api, pasta):
    uploads, temporarios, _ = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    await _anexo(db, ticket, dono, uploads, "fica.pdf", b"a")
    sai = await _anexo(db, ticket, dono, uploads, "sai.pdf", b"b")
    _como(dono)

    async with api as c:
        pedido = await _pede(c, ticket.id)
        await db.delete(sai)
        await db.commit()
        r = await c.get(pedido.json()["url"])

    assert r.status_code == 409
    assert "removid" in r.json()["detail"]
    assert r.headers["content-type"].startswith("application/json")
    assert list(temporarios.iterdir()) == []


@pytest.mark.asyncio
async def test_arquivo_sumido_do_disco_vira_erro_com_o_nome(db, api, pasta):
    uploads, temporarios, _ = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    await _anexo(db, ticket, dono, uploads, "fica.pdf", b"a")
    sumido = await _anexo(db, ticket, dono, uploads, "sumido.pdf", b"b")
    _como(dono)

    async with api as c:
        url = (await _pede(c, ticket.id)).json()["url"]
        # Some entre o pedido e o clique — o pedido já tinha conferido o disco.
        (uploads / sumido.s3_key).unlink()
        r = await c.get(url)

    assert r.status_code == 409
    assert "sumido.pdf" in r.json()["detail"]
    assert list(temporarios.iterdir()) == []


@pytest.mark.asyncio
async def test_chamado_sem_anexos_recusa_o_pedido(db, api, pasta):
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    _como(dono)

    async with api as c:
        r = await _pede(c, ticket.id)

    assert r.status_code == 422
    assert (
        await db.execute(select(AuditLog).where(AuditLog.entity_id == ticket.id))
    ).scalars().all() == []


# ── Quem pode ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cliente_de_outro_chamado_leva_o_mesmo_404_do_chamado_inexistente(db, api, pasta):
    uploads, _, _ = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    intruso = await _pessoa(db, UserRole.client, "Outro Cliente")
    ticket = await _chamado(db, dono)
    await _anexo(db, ticket, dono, uploads, "segredo.pdf", b"x")
    _como(intruso)

    async with api as c:
        alheio = await _pede(c, ticket.id)
        inexistente = await _pede(c, uuid.uuid4())

    assert alheio.status_code == inexistente.status_code == 404
    assert alheio.json() == inexistente.json()
    assert "segredo" not in alheio.text
    # Recusa não deixa rastro de "exportou" na auditoria.
    assert (
        await db.execute(select(AuditLog).where(AuditLog.entity_id == ticket.id))
    ).scalars().all() == []


@pytest.mark.asyncio
async def test_token_de_arquivo_unico_nao_abre_zip_e_vice_versa(db, api, pasta):
    uploads, _, config = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    anexo = await _anexo(db, ticket, dono, uploads, "laudo.pdf", b"x")
    _como(dono)

    token_de_arquivo = storage.create_file_token(anexo.s3_key, config)
    async with api as c:
        url_do_zip = (await _pede(c, ticket.id)).json()["url"]
        token_do_zip = url_do_zip.rsplit("/", 1)[1]
        r1 = await c.get(f"/api/v1/files/archive/{token_de_arquivo}")
        r2 = await c.get(f"/api/v1/files/{token_do_zip}")
        r3 = await c.get(f"/api/v1/files/archive/{token_do_zip}x")

    assert r1.status_code == 403
    assert r2.status_code == 403
    assert r3.status_code == 403


@pytest.mark.asyncio
async def test_token_assinado_de_outro_tipo_nao_abre_zip_mesmo_com_ids(db, api, pasta):
    """O tipo é o que separa os tokens, não a falta de um campo.

    Um token de arquivo comum não traz `ids` e já cairia por isso. Este traz
    tudo o que o lote pede — chamado e ids certos, assinatura válida — e só o
    `type` está errado. Sem a checagem de tipo, ele abriria o ZIP.
    """
    from datetime import UTC, datetime, timedelta

    from jose import jwt

    uploads, _, config = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    anexo = await _anexo(db, ticket, dono, uploads, "laudo.pdf", b"x")
    agora = datetime.now(UTC)
    forjado = jwt.encode(
        {
            "sub": str(ticket.id),
            "ids": [str(anexo.id)],
            "type": "file",
            "iat": agora,
            "exp": agora + timedelta(minutes=5),
            "iss": config.jwt_issuer,
        },
        config.get_private_key(),
        algorithm=config.jwt_algorithm,
    )

    async with api as c:
        r = await c.get(f"/api/v1/files/archive/{forjado}")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_arquivo_sumido_ja_e_recusado_no_pedido_e_sem_auditoria(db, api, pasta):
    """A falha comum aparece na TELA, no pedido, e não numa aba com JSON de erro."""
    uploads, _, _ = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    await _anexo(db, ticket, dono, uploads, "fica.pdf", b"a")
    sumido = await _anexo(db, ticket, dono, uploads, "sumido.pdf", b"b")
    (uploads / sumido.s3_key).unlink()
    _como(dono)

    async with api as c:
        r = await _pede(c, ticket.id)

    assert r.status_code == 409
    assert "sumido.pdf" in r.json()["detail"]
    assert (
        await db.execute(select(AuditLog).where(AuditLog.entity_id == ticket.id))
    ).scalars().all() == []


@pytest.mark.asyncio
async def test_range_com_varias_faixas_e_recusado(db, api, pasta):
    uploads, _, _ = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    await _anexo(db, ticket, dono, uploads, "laudo.pdf", b"x")
    _como(dono)

    async with api as c:
        url = (await _pede(c, ticket.id)).json()["url"]
        r = await c.get(url, headers={"Range": "bytes=0-1,2-3"})
    assert r.status_code == 416


@pytest.mark.asyncio
async def test_temporario_some_depois_da_entrega(db, api, pasta):
    uploads, temporarios, _ = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    await _anexo(db, ticket, dono, uploads, "laudo.pdf", b"x" * 4096)
    _como(dono)

    async with api as c:
        r = await c.get((await _pede(c, ticket.id)).json()["url"])
    assert r.status_code == 200
    assert list(temporarios.iterdir()) == []


# ── Aviso e auditoria ────────────────────────────────────────


@pytest.mark.asyncio
async def test_pedido_lista_os_nao_verificados_e_eles_vao_no_zip(db, api, pasta):
    uploads, _, _ = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    await _anexo(db, ticket, dono, uploads, "ok.pdf", b"a")
    duvidoso = await _anexo(db, ticket, dono, uploads, "duvidoso.pdf", b"b", verificado=False)
    _como(dono)

    async with api as c:
        corpo = (await _pede(c, ticket.id)).json()
        r = await c.get(corpo["url"])

    assert corpo["nao_verificados"] == [{"id": str(duvidoso.id), "original_name": "duvidoso.pdf"}]
    assert sorted(_zip(r).namelist()) == ["duvidoso.pdf", "ok.pdf"]


@pytest.mark.asyncio
async def test_pedido_registra_export_na_auditoria_sem_nome_de_arquivo(db, api, pasta):
    uploads, _, _ = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    a1 = await _anexo(db, ticket, dono, uploads, "laudo-sigiloso.pdf", b"a")
    a2 = await _anexo(db, ticket, dono, uploads, "foto.png", b"b", verificado=False)
    _como(dono)

    async with api as c:
        await _pede(c, ticket.id)

    [log] = (
        (await db.execute(select(AuditLog).where(AuditLog.entity_id == ticket.id))).scalars().all()
    )
    assert log.action == AuditAction.export
    assert log.entity_type == "ticket"
    assert log.user_id == dono.id
    assert sorted(log.new_data["attachment_ids"]) == sorted([str(a1.id), str(a2.id)])
    assert log.new_data["total"] == 2
    assert log.new_data["nao_verificados"] == 1
    assert "sigiloso" not in str(log.new_data)


def test_settings_do_teste_isolam_o_upload_dir(pasta):
    """Guarda do próprio arranjo: o teste não pode gravar no upload_dir real."""
    uploads, _, config = pasta
    assert isinstance(config, Settings)
    assert Path(config.upload_dir) == uploads


# ── O link de um anexo só (visualizador e Baixar) ────────────


@pytest.mark.asyncio
async def test_link_de_anexo_sumido_do_disco_e_o_mesmo_404_do_inexistente(db, api, pasta):
    """Sem isto o visualizador recebia um link válido e mostrava, dentro do
    quadro do PDF, o JSON cru do 404 do `/files` — o `<iframe>` não avisa erro
    HTTP. Visto no navegador em 09/10/2026."""
    uploads, _, _ = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    sumido = await _anexo(db, ticket, dono, uploads, "laudo.pdf", b"x")
    presente = await _anexo(db, ticket, dono, uploads, "foto.png", b"y")
    (uploads / sumido.s3_key).unlink()
    _como(dono)

    async with api as c:
        r_sumido = await c.get(f"/api/v1/attachments/{sumido.id}")
        r_inexistente = await c.get(f"/api/v1/attachments/{uuid.uuid4()}")
        r_presente = await c.get(f"/api/v1/attachments/{presente.id}")

    assert r_sumido.status_code == r_inexistente.status_code == 404
    assert r_sumido.json() == r_inexistente.json()
    assert r_presente.status_code == 200


# ── Rate limit do pedido do ZIP ──────────────────────────────
#
# O limiter fica DESLIGADO sob APP_ENV=testing (ver app/core/rate_limit.py).
# Aqui ele é ligado de propósito, como em test_rate_limit.py, e zerado antes e
# depois — a contagem em memória não pode vazar para outro teste.


@pytest.fixture
def limiter_ligado():
    from app.core.rate_limit import limiter

    limiter.enabled = True
    limiter.reset()
    yield
    limiter.reset()
    limiter.enabled = False


def _teto_do_zip() -> int:
    from limits import parse

    return parse(get_settings().rate_limit_zip_anexos).amount


def _bearer(usuario) -> dict[str, str]:
    """Token de acesso de verdade: a chave do balde sai do `sub` dele.

    O `get_current_user` continua sobrescrito por `_como` — quem decide o
    usuário da ROTA é o override; o cabeçalho existe para a `chave_por_usuario`,
    que é exatamente como ela lê em produção.
    """
    from app.core.security import create_access_token

    return {
        "Authorization": f"Bearer {create_access_token(usuario.id, usuario.role.value, usuario.email)}"
    }


async def _exports(db, ticket_id) -> int:
    rows = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == ticket_id, AuditLog.action == AuditAction.export
        )
    )
    return len(rows.scalars().all())


@pytest.mark.asyncio
async def test_pedidos_dentro_do_limite_passam_e_o_excedente_e_recusado_sem_efeito(
    db, api, pasta, limiter_ligado
):
    uploads, temporarios, _ = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    await _anexo(db, ticket, dono, uploads, "laudo.pdf", b"x")
    _como(dono)
    teto = _teto_do_zip()

    async with api as c:
        for _ in range(teto):
            r = await c.post(
                f"/api/v1/tickets/{ticket.id}/attachments/archive", headers=_bearer(dono)
            )
            assert r.status_code == 200, r.text
        excedente = await c.post(
            f"/api/v1/tickets/{ticket.id}/attachments/archive", headers=_bearer(dono)
        )

    assert excedente.status_code == 429
    # O formato de rate limit do projeto: `detail` em português e Retry-After.
    assert excedente.json() == {
        "detail": "Muitas tentativas. Aguarde alguns minutos e tente novamente."
    }
    assert int(excedente.headers["retry-after"]) > 0
    # Sem token, sem auditoria, sem temporário.
    assert "url" not in excedente.text and "archive" not in excedente.text
    assert await _exports(db, ticket.id) == teto
    assert list(temporarios.iterdir()) == []


@pytest.mark.asyncio
async def test_cada_usuario_tem_o_proprio_balde(db, api, pasta, limiter_ligado):
    uploads, _, _ = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    tecnico = await _pessoa(db, UserRole.technician, "Bruno Técnico")
    ticket = await _chamado(db, dono)
    await _anexo(db, ticket, dono, uploads, "laudo.pdf", b"x")

    async with api as c:
        _como(dono)
        for _ in range(_teto_do_zip()):
            await c.post(f"/api/v1/tickets/{ticket.id}/attachments/archive", headers=_bearer(dono))
        dono_bloqueado = await c.post(
            f"/api/v1/tickets/{ticket.id}/attachments/archive", headers=_bearer(dono)
        )
        _como(tecnico)
        tecnico_livre = await c.post(
            f"/api/v1/tickets/{ticket.id}/attachments/archive", headers=_bearer(tecnico)
        )

    assert dono_bloqueado.status_code == 429
    assert tecnico_livre.status_code == 200


@pytest.mark.asyncio
async def test_o_limite_nao_vira_oraculo_de_chamado_alheio(db, api, pasta, limiter_ligado):
    """Alheio e inexistente gastam o MESMO balde e recebem a MESMA resposta.

    Dentro do limite, os dois são o 404 de sempre. Fora dele, os dois são o
    mesmo 429. Nenhuma das respostas distingue o chamado que existe.
    """
    uploads, _, _ = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    intruso = await _pessoa(db, UserRole.client, "Outro Cliente")
    ticket = await _chamado(db, dono)
    await _anexo(db, ticket, dono, uploads, "segredo.pdf", b"x")
    _como(intruso)
    teto = _teto_do_zip()
    inexistente = uuid.uuid4()

    async with api as c:
        respostas = []
        for i in range(teto + 2):
            alvo = ticket.id if i % 2 == 0 else inexistente
            respostas.append(
                await c.post(
                    f"/api/v1/tickets/{alvo}/attachments/archive", headers=_bearer(intruso)
                )
            )

    dentro, fora = respostas[:teto], respostas[teto:]
    assert {r.status_code for r in dentro} == {404}
    assert len({r.text for r in dentro}) == 1
    assert {r.status_code for r in fora} == {429}
    assert len({r.text for r in fora}) == 1
    assert "segredo" not in "".join(r.text for r in respostas)
    assert await _exports(db, ticket.id) == 0


@pytest.mark.asyncio
async def test_o_limite_do_zip_nao_toca_listagem_link_individual_upload_nem_entrega(
    db, api, pasta, limiter_ligado
):
    uploads, _, _ = pasta
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    anexo = await _anexo(db, ticket, dono, uploads, "laudo.pdf", b"x")
    _como(dono)
    h = _bearer(dono)

    async with api as c:
        urls = []
        for _ in range(_teto_do_zip()):
            urls.append(
                (
                    await c.post(f"/api/v1/tickets/{ticket.id}/attachments/archive", headers=h)
                ).json()["url"]
            )
        assert (
            await c.post(f"/api/v1/tickets/{ticket.id}/attachments/archive", headers=h)
        ).status_code == 429

        lista = await c.get(f"/api/v1/tickets/{ticket.id}/attachments", headers=h)
        link = await c.get(f"/api/v1/attachments/{anexo.id}", headers=h)
        envio = await c.post(
            f"/api/v1/tickets/{ticket.id}/attachments",
            headers=h,
            files=[("files", ("novo.pdf", io.BytesIO(b"%PDF"), "application/pdf"))],
        )
        # Um link já emitido continua valendo: a entrega não tem limite próprio.
        entrega = await c.get(urls[0])

    assert lista.status_code == 200
    assert link.status_code == 200
    assert envio.status_code == 201, envio.text
    assert entrega.status_code == 200


def test_inventario_o_limite_mora_so_no_pedido_do_zip():
    """Fixa o número, como `test_o_inventario_de_endpoints_limitados_e_este`.

    Só o PEDIDO leva limite: a entrega (`GET /files/archive/{token}`) é por
    token curto, assinado e de tipo próprio, e confere tudo de novo.
    """
    from app.core.rate_limit import limiter

    rotas = {
        nome: str(limites[0].limit)
        for nome, limites in limiter._route_limits.items()
        if nome.startswith(("app.routers.attachments.", "app.routers.files."))
    }
    assert rotas == {
        "app.routers.attachments.request_attachments_archive": "5 per 15 minute",
    }
