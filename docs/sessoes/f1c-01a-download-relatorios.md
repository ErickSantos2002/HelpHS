# F1-C-01a — download de relatórios CSV e PDF (notas da sessão)

Arquivo exclusivo desta frente. O `Changelog.md`, o `frontend/src/data/changelog.ts`
e o `docs/decisoes-e-regras.md` NÃO foram tocados por haver sessões paralelas;
o texto abaixo é para quem consolidar.

## O defeito (FUN-50)

- `exportReportsUrl` montava `/api/v1/dashboard/reports/export/{csv|pdf}` RELATIVO.
  Medido em 04/11/2026: no domínio do front o nginx devolve `200 text/html`
  (o `index.html` da SPA, `try_files ... /index.html`).
- O `<a href download>` não leva `Authorization`: no host da API, `401`.
- O CORS expõe só `X-Request-ID, Retry-After` (medido): o `Content-Disposition`
  não é legível no JS.

## A correção (só front)

- `baixarRelatorio(formato, filtros)` em `services/reportService.ts`: `api.get`
  com `responseType: "blob"` (base `VITE_API_URL`, Bearer pelo interceptor,
  nada na query).
- Confere tipo e conteúdo antes de virar arquivo: PDF começa com `%PDF`; CSV
  não pode começar com `<`; corpo vazio é recusado (`ArquivoDeRelatorioInvalido`).
- Nome montado no front: `relatorio_helphs_<início>_a_<fim>[_categoria][_prioridade].<ext>`.
- URL temporária revogada no tique seguinte, inclusive se o clique falhar.
- Erro com corpo Blob volta a ser JSON para o `apiError`; corpo não-JSON
  (HTML de proxy) vira vazio e a mensagem sai pelo status.
- 428 do aceite: o interceptor não reconhece o `code` dentro de um Blob, então
  `baixarRelatorio` dispara `avisaAceitePoliticaPendente()` depois de desembrulhar.
  `api.ts` não foi alterado.
- Tela: "Gerando CSV/PDF…" com `disabled` e `aria-busy`; guarda síncrona contra
  download concorrente (inclusive o "Tentar de novo" de aviso antigo); aviso com
  motivo e "Tentar de novo"; nenhum aviso por cima da tela do aceite.
- Permissão inalterada: o botão continua só para admin.

## Rascunho para o changelog do produto (próxima versão)

> **Relatórios:** "Exportar CSV" e "Exportar PDF" voltaram a baixar o arquivo do
> período escolhido. Durante a geração o botão mostra o andamento, e uma falha
> explica o motivo com a opção de tentar de novo.

## Rascunho para decisoes-e-regras.md

> Download de arquivo autenticado sai pelo cliente `api` com `responseType:
> "blob"`, nunca por `<a href>` para a API: o link vai ao domínio do front e não
> leva o token. O token nunca vai na query. Erros com corpo Blob precisam ser
> desembrulhados antes do `apiError`, e o 428 do aceite avisado à mão.

## Pendências (fora da C-01a, NÃO alteradas)

- **SEC-12** (backend): título, responsável e justificativa entram no CSV sem
  neutralizar `= + - @`. Com a exportação funcionando, o risco passa de teórico
  a real. Correção separada no backend.
- **SEC-08**: `GET /dashboard/reports` e as exportações aceitam técnico na API;
  a tela só mostra ao admin. Decisão pendente, vale para JSON e exportação juntos.
- Mensagem do 500: o `apiError` mostra o `detail` em texto do servidor
  ("Internal Server Error") em vez do texto padrão. É o comportamento de todas
  as telas, não desta frente.

## Validação visual (04/11/2026)

Front em `vite dev` (localhost:5199) + API FALSA descartável (127.0.0.1:8799, no
scratchpad, fora do repositório) com o CORS de produção. Produção não foi
consultada. Medido no Chrome: CSV e PDF baixados com nome, tipo e conteúdo
corretos; URL revogada; pedido no host da API com Bearer e datas; período
personalizado; 403/422/500/HTML/rede com aviso e botão de volta; 428 com a tela
do aceite e sem aviso; 401 com a sessão limpa e ida ao `/login`.
Limites: a imagem do "Gerando…" não foi capturada a tempo (o estado foi lido no
DOM: texto, `disabled`, `aria-busy`); o Chrome salvou só os 2 primeiros arquivos
— os seguintes foram retidos pela trava de "vários downloads" do próprio
navegador, com o clique registrado; build de produção não foi servido.
