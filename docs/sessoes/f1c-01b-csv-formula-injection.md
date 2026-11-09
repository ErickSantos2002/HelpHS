# F1-C-01b — SEC-12, injeção de fórmula no CSV (notas da sessão)

Arquivo exclusivo desta frente. `Changelog.md`, `frontend/src/data/changelog.ts`
e `docs/decisoes-e-regras.md` NÃO foram tocados por haver sessões paralelas.

## Campos

Único gerador de CSV do backend: `export_reports_csv` (`app/routers/dashboard.py`).

| Seção | Campo | Origem | Risco |
|---|---|---|---|
| Justificativas | Título | cliente (abertura do chamado) | **alto** |
| Justificativas | Motivo (`sla_breach_justification`) | técnico/admin | **alto** |
| Justificativas | Responsável (`User.name`) | a própria pessoa / admin | médio |
| Justificativas | Protocolo, prioridade, data | sistema | nenhum |
| Cabeçalho | período, filtros, "gerado em" | sistema (datas e enums) | nenhum |
| Por dia / categoria / SLA / CSAT | datas, enums, números | sistema | nenhum |

A proteção é aplicada a TODA célula (`EscritorCsvSeguro`), sem lista de campos:
seção nova não precisa lembrar de se proteger.

## Estratégia

`app/utils/csv_seguro.py`, por célula e antes da serialização:

1. Cada **linha** da célula ganha `'` na frente se começar por `= + - @`
   (também atrás de espaço, tabulação, controle, invisíveis Cf como
   `​`/BOM, e nas variantes ＝＋－＠ ﹦﹢﹣﹫), se começar por `\t`, ou
   se já começar por `'`.
2. O `csv` do Python cuida de aspas, vírgulas e quebras (QUOTE_MINIMAL, CRLF).
3. Número, nulo e texto comum passam intactos. O banco não é tocado.

**Por linha, e não só no começo da célula:** medido em 04/11/2026 no Excel 16,
clique duplo em pt-BR: o Excel ignora a quebra de linha entre aspas, e a linha
do meio de `"a⏎=1+1⏎b"` virava célula própria e era EXECUTADA, com ou sem
apóstrofo no começo da célula.

**Reversível:** `valor_original` tira um `'` do começo de cada linha. Como o
apóstrofo original também é prefixado, a volta é exata (testado).

**Custo visível:** o `'` aparece na planilha nessas linhas (o Excel não o
esconde ao abrir CSV). Texto como "-5 dias de atraso" sai "'-5 dias de atraso".

## Evidência em planilha (Excel 16, Windows, arquivos descartáveis, fórmulas benignas)

| Arquivo | Clique duplo (pt-BR) | OpenText com vírgula |
|---|---|---|
| `csv.writer` cru (antes) | 3 fórmulas executadas | 7 (inclui HYPERLINK) |
| `EscritorCsvSeguro` (depois) | **0** | **0** |

Não testado: LibreOffice (ausente na máquina), Google Sheets, Numbers, Excel
para Mac/web. Não se afirma proteção universal.

## Observação lateral (não corrigida)

No Excel pt-BR, o clique duplo abre o CSV do HelpHS **numa coluna só** (o
separador da localidade é `;`). É usabilidade, não segurança; mudar separador
ou BOM altera o formato e precisa de decisão.

## SEC-08 — diagnóstico (só leitura, nada alterado)

| Endpoint | Backend | Front que chama |
|---|---|---|
| `GET /dashboard/stats` | admin, técnico | AdminDashboard, TechnicianDashboard |
| `GET /dashboard/reports` (JSON) | admin, **técnico** | só admin (AdminDashboard; ReportsPage com `isAdmin`) |
| `GET /dashboard/reports/export/csv` | admin, **técnico** | só admin (botão com `isAdmin`) |
| `GET /dashboard/reports/export/pdf` | admin, **técnico** | só admin |
| `GET /dashboard/reports/technicians` | **admin** | admin |
| `GET /dashboard/reports/technician` | admin; técnico só o próprio | ambos |

O que o técnico obtém pelo relatório global e não tem pela tela:
- `technicians_dist`: total, resolvidos e abertos de CADA colega. Isso é um
  pedaço do `/reports/technicians`, que é só admin. É a inconsistência real.
- Comparação com o período anterior, conformidade de SLA e CSAT agregados.

O que ele JÁ vê por outros caminhos: todos os chamados com título e
responsável (`tickets.py:664-666` restringe só cliente), as pesquisas
(`GET /surveys` admin+técnico) e as justificativas no detalhe do chamado.

Nenhuma tela do técnico depende de `/dashboard/reports` nem das exportações.

**Recomendação:** JSON, CSV e PDF globais **só admin**, iguais ao
`/reports/technicians`. Não quebra tela nenhuma e fecha o vazamento do
desempenho dos colegas. Se a equipe quiser o técnico com relatório global,
a alternativa coerente é liberar e tirar o `technicians_dist` da resposta dele.
Decisão do operador; nada foi alterado.

## Gates desta rodada

- Específicos: `test_csv_seguro.py` (88) + `test_exportacao_csv_postgres.py` (6,
  Postgres real) + regressão do dashboard = 141 verdes.
- Mutação: 13/13 mortas. Cobertura do módulo: 100%.
- Black, Ruff, Mypy: verdes.
- **Suíte backend completa: NÃO executada**, por coordenação com a Sessão 0
  (testes pendentes da F1-D1).

## Rascunho para o changelog (próxima versão)

> **Relatórios:** a exportação CSV passou a proteger contra fórmulas escondidas
> em textos (título, responsável, justificativa). Essas células podem aparecer
> com um apóstrofo (') no início quando abertas na planilha.
