"""
O serviço de embedding da Helô — um contêiner à parte, não a API.

Vive dentro de `backend/` para ser um projeto Python só (uma suíte, uma
cobertura, um lint), mas é construído por um Dockerfile próprio e sobe como
serviço separado no EasyPanel. A API fala com ele por HTTP; ver
`app/services/helo_embedding.py` para o contrato e para o motivo da separação
(resumo: `--workers 1`, e cálculo de CPU no event loop já congelou esta API
por 151 segundos uma vez).

Este pacote NÃO é importado pela API. A dependência anda num sentido só.
"""
