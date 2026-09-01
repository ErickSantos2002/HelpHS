"""
Pacote da API do HelpHS.

A versão vive aqui e em nenhum outro lugar do backend: já esteve escrita à mão
em dois pontos do main.py e as duas cópias congelaram em "1.0.0" enquanto o
produto seguiu.

Unificar a fonte não bastou. Em 31/08/2026 este número estava em 1.8.0 com o
produto em v1.11.0 — recongelou, e em silêncio: `__version__` só alimenta o
construtor do FastAPI, logo só o spec OpenAPI, e o spec está fechado em
produção. O único espelho que denunciaria a defasagem foi desligado por outro
motivo, e bom. Fonte única sem ninguém conferindo volta a congelar.

Quem manda no número é `APP_VERSION`, em frontend/src/data/changelog.ts: é a
versão que o cliente vê. Aqui ela entra **sem** o "v" — este valor vira o
`info.version` do OpenAPI e o dunder de um pacote Python, e os dois pedem o
número puro. A tradução do prefixo é do teste, não das pontas.

`test_a_versao_do_backend_acompanha_a_versao_do_produto`, em
tests/test_health.py, confere os dois lados: subir um sem o outro derruba a
suíte.
"""

__version__ = "1.12.0"
