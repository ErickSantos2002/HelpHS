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

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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


# ── Guarda do cabeçalho Range ─────────────────────────────────
#
# O `FileResponse` do starlette mescla as faixas do `Range` em laço aninhado,
# sem teto de quantidade. Medido na 0.51.0, com faixas crescentes e disjuntas
# (o pior caso, porque cada nova precisa varrer a lista inteira antes do
# `append`): 1000 faixas custam 43 ms, 4000 custam 821 ms, 16000 custam 11,9 s.
# Dobrar a quantidade quadruplica o tempo. Ponta a ponta, um cabeçalho de 625 KB
# com 50 mil faixas foi aceito e ocupou o processo por 180 segundos.
#
# Isso é CPU síncrona dentro do event loop, e o deploy roda `--workers 1`: uma
# requisição congela a API para todos. É o PYSEC-2026-1942, que o pip-audit
# deixou de reportar mas que continua no comportamento.
#
# A guarda abaixo é O(1) — mede o comprimento e procura uma vírgula. Não faz
# parsing, de propósito: parsing na nossa camada só moveria o custo de lugar.
_RANGE_TAMANHO_MAXIMO = 128
"""Bytes. `bytes=` mais duas casas de 20 dígitos cabem de sobra em 128."""


def _recusa_range_perigoso(range_bruto: str | None) -> None:
    """Barra o `Range` que sairia caro, ANTES de ele chegar ao `FileResponse`.

    Multi-range é recusado inteiro, e não apenas limitado a um número pequeno de
    faixas. Dois motivos: ele **já está quebrado** no starlette — `bytes=0-99,
    200-299` estoura `Response content longer than Content-Length` e derruba a
    conexão, tanto na 0.51.0 quanto na 0.46.2 anterior, então não há
    funcionalidade a preservar; e recusar por vírgula é uma checagem que não
    depende de contar nada.

    O uso legítimo continua inteiro: navegador e gerenciador de download pedem
    uma faixa por requisição (`bytes=0-`, `bytes=1024-2047`), que é o que
    sustenta retomada de download e busca em vídeo.
    """
    if not range_bruto:
        return

    if len(range_bruto) > _RANGE_TAMANHO_MAXIMO:
        raise HTTPException(
            status_code=status.HTTP_431_REQUEST_HEADER_FIELDS_TOO_LARGE,
            detail="Cabeçalho Range grande demais.",
        )

    if "," in range_bruto:
        raise HTTPException(
            status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
            detail="Este servidor atende uma faixa por requisição.",
        )


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
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    download: bool = Query(default=False, description="Força o download mesmo sendo imagem"),
    filename: str | None = Query(default=None, max_length=255),
) -> FileResponse:
    try:
        key = storage.read_file_token(token, settings)
        caminho = storage.resolve_path(key, settings)
    except storage.StorageError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    # Depois do token, de propósito: quem não tem link válido continua levando
    # 403 antes de qualquer outra coisa, e a recusa do Range não vira um oráculo
    # sobre a existência do arquivo.
    _recusa_range_perigoso(request.headers.get("range"))

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
