"""
Entrega dos arquivos guardados em disco.

O acesso é por link temporário assinado (ver services/storage.py), e não pela
sessão do usuário: a foto de perfil e a pré-visualização de anexo são carregadas
pelo <img> do navegador, que não manda cabeçalho de autenticação.

Sem o token, ou com o token vencido, o arquivo não é servido.

Sobre exibir inline: os arquivos vêm de upload de cliente, então servi-los
inline no domínio da API é o mesmo que deixar terceiros publicarem conteúdo
nessa origem. Um .html ou .svg com script rodaria como se fosse do sistema
(XSS armazenado). Por isso só imagem de formato seguro abre inline; todo o
resto desce como download.
"""

import mimetypes
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.core.config import Settings, get_settings
from app.services import storage

router = APIRouter(tags=["Files"])

# Formatos que o navegador pode abrir direto, para o usuário ver o anexo sem
# baixar. Imagem e PDF renderizam em visualizador próprio; texto puro não
# executa nada.
#
# Ficam de fora de propósito:
#   - SVG: é imagem, mas aceita <script> dentro
#   - HTML/XHTML: viraria script rodando no domínio da API
_INLINE_MIMES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "application/pdf",
        "text/plain",
    }
)
_INLINE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".txt"})

_FALLBACK_MIME = "application/octet-stream"

# Mesmo baixado, o arquivo não deve rodar nada nem carregar recursos externos
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Referrer-Policy": "no-referrer",
}


def _safe_media_type(caminho: Path) -> tuple[str, bool]:
    """
    Devolve (media_type, pode_exibir_inline).

    O tipo sai da extensão e só é mantido se estiver na lista de formatos
    seguros; qualquer outra coisa vira octet-stream para o navegador não tentar
    interpretar.
    """
    extensao = caminho.suffix.lower()
    if extensao not in _INLINE_EXTENSIONS:
        return _FALLBACK_MIME, False

    adivinhado = mimetypes.guess_type(caminho.name)[0]
    if adivinhado not in _INLINE_MIMES:
        return _FALLBACK_MIME, False

    return adivinhado, True


@router.get("/files/{token}")
async def download_file(
    token: str,
    settings: Annotated[Settings, Depends(get_settings)],
    download: bool = Query(default=False, description="Força o download mesmo sendo imagem"),
    filename: str | None = Query(default=None, max_length=255),
) -> FileResponse:
    try:
        key = storage.read_file_token(token, settings)
        caminho = storage.resolve_path(key, settings)
    except storage.StorageError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    if not caminho.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo não encontrado no servidor. Ele pode ter sido removido.",
        )

    media_type, pode_inline = _safe_media_type(caminho)
    nome = filename or caminho.name
    headers = dict(_SECURITY_HEADERS)

    if pode_inline and not download:
        headers["Content-Disposition"] = f"inline; filename*=UTF-8''{quote(nome)}"
    else:
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(nome)}"

    return FileResponse(path=caminho, media_type=media_type, headers=headers)
