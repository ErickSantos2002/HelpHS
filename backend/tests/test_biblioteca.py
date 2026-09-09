"""
Biblioteca de arquivos frequentes: quem alcança o quê, e o que fica registrado.

A regra que estes testes protegem é de conteúdo, não de código: manual não é
material público por definição — há manual técnico com senha de configuração em
texto aberto. Daí a coluna de visibilidade, cujo default é `internal`, para que
o esquecimento falhe do lado seguro.

Os três pontos onde a regra pode vazar, e um teste para cada:

1. **a listagem** — só staff. O cliente recebe o que o técnico manda, não
   escolhe da prateleira;
2. **o download** — o link tem validade, então conferir depois de emitir seria
   tarde. Cliente que tem o id de um item interno leva 404, e não 403: 403
   confirmaria que o item existe;
3. **o anexo no chat** — a conversa é lida pelo cliente. A recusa é da API e
   vem antes de gravar, porque a API é chamada por outros clientes além da
   tela.
"""

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.models.models import LibraryFile, LibraryVisibility, UserRole, UserStatus
from app.utils.library_access import (
    e_staff,
    ensure_pode_anexar_no_chat,
    ensure_pode_baixar,
    visivel_para_cliente,
)

_CHAT = Path(__file__).resolve().parent.parent / "app" / "routers" / "chat.py"
_LIBRARY = Path(__file__).resolve().parent.parent / "app" / "routers" / "library.py"


def _usuario(role: UserRole) -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.role = role
    u.status = UserStatus.active
    return u


def _arquivo(visibility: LibraryVisibility) -> MagicMock:
    a = MagicMock(spec=LibraryFile)
    a.id = uuid.uuid4()
    a.title = "Manual do Phoebus"
    a.original_name = "manual-phoebus.pdf"
    a.visibility = visibility
    a.s3_key = "library/abc.pdf"
    return a


# ═══════════════════════════════════════════════════════════════
# A regra, no nível em que ela mora
# ═══════════════════════════════════════════════════════════════


def test_so_o_que_foi_aberto_explicitamente_e_visivel_ao_cliente():
    assert visivel_para_cliente(_arquivo(LibraryVisibility.client)) is True
    assert visivel_para_cliente(_arquivo(LibraryVisibility.internal)) is False


def test_o_default_do_modelo_e_interno():
    """
    O default é a decisão inteira: quem subir um arquivo sem pensar na
    visibilidade sobe um arquivo que o cliente não vê. Default aberto faria o
    descuido vazar.
    """
    coluna = LibraryFile.__table__.c.visibility

    assert coluna.default.arg is LibraryVisibility.internal
    assert coluna.server_default.arg == "internal"


@pytest.mark.parametrize("papel", [UserRole.admin, UserRole.technician])
@pytest.mark.parametrize("visibilidade", [LibraryVisibility.internal, LibraryVisibility.client])
def test_staff_baixa_qualquer_um(papel, visibilidade):
    ensure_pode_baixar(_arquivo(visibilidade), _usuario(papel), "sumiu")  # não levanta


def test_cliente_baixa_o_que_e_de_cliente():
    ensure_pode_baixar(_arquivo(LibraryVisibility.client), _usuario(UserRole.client), "sumiu")


def test_cliente_leva_404_no_item_interno_e_nao_403():
    """
    404 e não 403 de propósito: o cliente não pode aprender que o item existe.
    403 seria a confirmação. Mesma escolha que os anexos de chamado já fazem.
    """
    with pytest.raises(HTTPException) as erro:
        ensure_pode_baixar(_arquivo(LibraryVisibility.internal), _usuario(UserRole.client), "sumiu")

    assert erro.value.status_code == 404
    assert erro.value.detail == "sumiu"


def test_anexar_item_interno_no_chat_e_recusado_com_explicacao():
    """
    Aqui é 422 e a razão aparece: quem age é o técnico, que precisa entender
    por que não pode mandar aquele arquivo. Esconder só faria ele tentar de
    novo.
    """
    with pytest.raises(HTTPException) as erro:
        ensure_pode_anexar_no_chat(_arquivo(LibraryVisibility.internal))

    assert erro.value.status_code == 422
    assert "interno" in erro.value.detail


def test_anexar_item_de_cliente_no_chat_passa():
    ensure_pode_anexar_no_chat(_arquivo(LibraryVisibility.client))  # não levanta


def test_e_staff_nao_inclui_cliente():
    assert e_staff(_usuario(UserRole.admin)) is True
    assert e_staff(_usuario(UserRole.technician)) is True
    assert e_staff(_usuario(UserRole.client)) is False


# ═══════════════════════════════════════════════════════════════
# Permissão por rota, lida do próprio roteador
# ═══════════════════════════════════════════════════════════════


def _decorador_de(fonte: str, rota: str, metodo: str) -> str:
    """O bloco da função que atende `metodo rota`, do decorador ao fim da assinatura."""
    padrao = re.compile(
        rf'@router\.{metodo}\(\s*"{re.escape(rota)}".*?\)\s*\nasync def \w+\((.*?)\n\) ->',
        re.S,
    )
    achado = padrao.search(fonte)
    assert achado, f"não achei {metodo.upper()} {rota}"
    return achado.group(1)


@pytest.mark.parametrize(
    ("metodo", "rota"),
    [("post", "/library"), ("patch", "/library/{arquivo_id}"), ("delete", "/library/{arquivo_id}")],
)
def test_escrita_na_biblioteca_e_so_de_admin(metodo, rota):
    """
    Enviar, editar e apagar são de administrador. O PATCH entra nesta lista
    porque é ele que ABRE um arquivo para o cliente — deixá-lo com o técnico
    devolveria por outra porta a decisão que a regra tirou dele.
    """
    assinatura = _decorador_de(_LIBRARY.read_text(encoding="utf-8"), rota, metodo)

    assert (
        "authorize(UserRole.admin)" in assinatura
    ), f"{metodo.upper()} {rota} deixou de exigir admin: {assinatura.strip()[:120]}"


def test_a_listagem_e_de_staff_e_nao_do_cliente():
    """
    O acervo é ferramenta de atendimento, não catálogo público. Abrir a lista
    ao cliente deixaria ele navegar tudo o que existe, inclusive os títulos e
    descrições do que é interno.
    """
    assinatura = _decorador_de(_LIBRARY.read_text(encoding="utf-8"), "/library", "get")

    assert "authorize(UserRole.admin, UserRole.technician)" in assinatura


def test_o_download_e_autenticado_e_a_regra_e_a_visibilidade():
    """
    O download NÃO é restrito por papel na assinatura — se fosse, o anexo que
    chega na conversa não abriria para o cliente. Quem decide ali é
    `ensure_pode_baixar`, e ele precisa rodar ANTES de o link ser gerado.
    """
    fonte = _LIBRARY.read_text(encoding="utf-8")
    assinatura = _decorador_de(fonte, "/library/{arquivo_id}/download", "get")

    assert "get_current_user" in assinatura
    assert "authorize(" not in assinatura

    guarda = fonte.index("ensure_pode_baixar(")
    link = fonte.index("storage.get_presigned_url(")
    assert guarda < link, "a conferência precisa vir antes de emitir o link"


# ═══════════════════════════════════════════════════════════════
# O anexo no chat: a recusa vem antes de gravar
# ═══════════════════════════════════════════════════════════════


def test_no_chat_o_guarda_roda_antes_de_qualquer_gravacao():
    """
    Recusar depois de gravar deixaria a mensagem no banco e o pedido rejeitado.
    O teste compara posições na fonte porque é a ordem que importa, e ordem não
    aparece em teste de resposta HTTP.
    """
    fonte = _CHAT.read_text(encoding="utf-8")
    corpo = fonte[fonte.index("async def create_message(") :]

    guarda = corpo.index("ensure_pode_anexar_no_chat(")
    gravacao = corpo.index("db.add(msg)")

    assert guarda < gravacao


def test_a_mensagem_aponta_para_a_biblioteca_em_vez_de_copiar():
    """
    Copiar por mensagem multiplicaria o mesmo PDF no disco e criaria a dúvida
    de qual cópia vale quando o admin subir uma versão nova.
    """
    from app.models.models import ChatMessage

    fk = list(ChatMessage.__table__.c.library_file_id.foreign_keys)[0]

    assert fk.column.table.name == "library_files"
    # SET NULL: apagar um item da biblioteca não pode apagar a conversa.
    assert fk.ondelete == "SET NULL"


# ═══════════════════════════════════════════════════════════════
# Auditoria da visibilidade — nos DOIS sentidos
# ═══════════════════════════════════════════════════════════════


def _sessao_com(arquivo):
    """Sessão que responde ao lookup do PATCH e guarda o que foi adicionado."""
    sessao = MagicMock()
    sessao.adicionados = []

    async def execute(_stmt):
        r = MagicMock()
        r.scalar_one_or_none.return_value = arquivo
        return r

    sessao.execute = execute
    sessao.add = lambda obj: sessao.adicionados.append(obj)
    sessao.commit = MagicMock(side_effect=lambda: None)
    return sessao


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("de", "para"),
    [
        (LibraryVisibility.internal, LibraryVisibility.client),
        (LibraryVisibility.client, LibraryVisibility.internal),
    ],
)
async def test_mudar_visibilidade_deixa_rastro_na_auditoria(de, para):
    """
    Abrir um manual para o cliente é decisão de alguém, com nome e hora — e
    fechá-lo de novo também.

    Sem este teste, alguém poderia simplificar o PATCH para um `setattr` em
    laço e a auditoria sumiria sem nada cair. O registro precisa trazer o ANTES
    e o DEPOIS: saber que mudou, sem saber de quê para quê, não responde a
    pergunta que se faz meses depois.
    """
    from unittest.mock import AsyncMock, patch

    from app.models.models import AuditLog
    from app.routers.library import update_library_file
    from app.schemas.library import LibraryFileUpdate

    arquivo = _arquivo(de)
    arquivo.product = None
    arquivo.description = None
    arquivo.product_id = None
    arquivo.mime_type = "application/pdf"
    arquivo.size_bytes = 10
    arquivo.virus_scanned = True
    arquivo.virus_clean = True
    arquivo.uploaded_by = uuid.uuid4()
    arquivo.created_at = arquivo.updated_at = datetime.now(UTC)
    arquivo.stored_name = "abc.pdf"

    sessao = _sessao_com(arquivo)
    sessao.commit = AsyncMock()
    sessao.refresh = AsyncMock()
    admin = _usuario(UserRole.admin)

    with patch("app.routers.library._busca_ou_404", new=AsyncMock(return_value=arquivo)):
        await update_library_file(arquivo.id, LibraryFileUpdate(visibility=para), sessao, admin)

    registros = [o for o in sessao.adicionados if isinstance(o, AuditLog)]
    assert registros, "mudar visibilidade não gerou entrada no audit_log"

    log = registros[0]
    assert log.entity_type == "library_file"
    assert log.entity_id == arquivo.id
    assert log.user_id == admin.id
    assert log.old_data["visibility"] == de.value, "o audit_log não registrou o valor ANTERIOR"
    assert log.new_data["visibility"] == para.value, "o audit_log não registrou o valor NOVO"
