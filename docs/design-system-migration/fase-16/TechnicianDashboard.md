# Fase 16 — `TechnicianDashboard`

Página: `/dashboard` (papel `technician`) — `frontend/src/pages/dashboard/TechnicianDashboard.tsx`

## Ficha da §29

```text
Página: /dashboard (technician) — src/pages/dashboard/TechnicianDashboard.tsx

FUNCIONALIDADE
[x] carrega dados      — `getTechnicianDetailReport`, `getDashboardStats`,
                          5× `getTickets`: mesmo método, URL e params de antes
[x] filtra              — seletor de período + intervalo personalizado, inalterado
[–] busca                — a tela não busca
[–] pagina               — listas com `limit: 200`, sem paginação
[–] ordena               — a tela não ordena
[–] cria  [–] edita  [–] exclui
[x] abre detalhes       — cada linha navega para `/tickets/:id`, inalterado
[–] anexa/remove arquivo
[x] respeita permissões — `myTickets` filtra por `assignee_id = user.id`
[x] mostra erro          — `Alert variant="danger"`, `live` no padrão (ver nota)
[x] mostra estado vazio — as três `TicketListCard` têm mensagem própria
[x] mostra loading       — `Spinner` na carga inicial
[x] funciona no mobile   — grade responsiva inalterada
[x] funciona no tema escuro — zero classe de cor que dependa de `theme` em JS
                          ou de par `text-slate-* dark:text-slate-*`
[x] nenhum campo depende do placeholder — `FilterSelect` sempre parte com
                          "mes" selecionado; os `<input type="date">` são nativos
[–] barras desenhadas    — a tela não tem `progressbar`/`meter`

ACRESCENTADOS PELAS DECISÕES
[x] o que a interface MOSTRA é o que a árvore DIZ, por estado
    repouso    ponto de prioridade tinha cor sem nome — ganhou `sr-only`
    hover      linha da lista: `hover:bg-surface-elevated`, mesmo efeito visual
[x] nenhuma ação só de mouse — a linha já era `<button>`, inalterado
[x] nenhum `text-slate-*` sem `dark:` — zero `text-slate-*`/`bg-slate-*`/
                          `border-slate-*` restante (eram 21 ocorrências)
[x] nenhuma cor fora do sistema — zero hexadecimal cravado (eram 8: a cor do
                          gráfico + 7 do cromo de tema) e zero cor cheia
                          semântica como texto (eram 2)
[x] `Alert` já montado leva `live={false}` — não se aplica: os dois `Alert`
    desta tela aparecem em RESPOSTA a uma falha de carga, não já montados —
    `live` no padrão (`true`) é o correto, mesma leitura do `ClientDashboard`
[ ] desvio F1 — não tocado; ver "O que não fiz"
[x] nenhum primitivo reinventado — `PRIORITY_DOT` (6º mapa de prioridade) saiu;
    3 dos 6 `<svg>` soltos viraram `Icon`
[x] a catraca desceu — os dois números que esta tela devia zerar foram a zero
    (ver "Os números")
```

## O que a tela tinha

- **Um sexto mapa de prioridade**, `PRIORITY_DOT` (linhas 56–61 antes da
  migração), com `medium: "bg-primary"` — divergindo do canônico
  `lib/prioridade.ts`, que diz `bg-info`. O ponto também não tinha nome
  acessível: era a única fonte da prioridade na linha, sem rótulo visível nem
  `sr-only`, contra a regra que o próprio `lib/prioridade.ts` documenta.
- **Cromo de gráfico à mão**, `theme === "dark" ? A : B` repetido cinco vezes
  (`tooltipBg`, `tooltipBorder`, `tooltipStyle`, `tooltipWrapper`, `axisColor`),
  com sete hexadecimais cravados: `#132238`, `#1E3A5F`, `#f1f5f9`, `#0f172a`,
  `#e2e8f0`, `#475569`, `#94a3b8`.
- **Uma cor de série cravada**, `#0ea5e9`, usada no gradiente, no traço e no
  ponto ativo do `AreaChart` — a quarta cor diferente entre cinco gráficos da
  mesma natureza (chamados por dia) nas três telas do painel.
- **21 ocorrências de paleta crua do Tailwind** (`slate-*`), a maioria em pares
  `text-slate-NNN dark:text-slate-MMM` reimplementando à mão o que um token
  já resolve sozinho.
- **2 ocorrências de cor cheia semântica como texto** (`text-danger`): o selo
  "SLA" da linha (com `bg-danger/10`, também fora do sistema) e o valor do
  indicador "SLA violados" no card de desempenho.
- **6 `<svg>` soltos**: ícone de "vazio" na lista, calendário do intervalo
  personalizado, e 4 ícones dos `KpiCard`.
- **1 lugar na catraca de contraste**: `bg-surface-elevated` + `text-slate-500`
  no selo de contagem da `TicketListCard` — medido em 4,34:1, abaixo do piso
  de 4,5:1.

## O que passou a usar

- **`lib/prioridade.ts`** (`PRIORIDADE`) para o ponto de prioridade da linha —
  `PRIORITY_DOT` saiu inteiro.
- **`lib/grafico.ts`**: `COR_SERIE_TEMPORAL` no gradiente/traço/ponto ativo do
  `AreaChart`; `CROMO.eixo` nos dois eixos; `ESTILO_DICA`/`ENVOLTORIO_DICA` no
  tooltip. Como consequência, `useTheme()` deixou de ser necessário nesta tela
  e o import saiu.
- **`text-conteudo` / `text-conteudo-heading` / `text-conteudo-muted`** no
  lugar de todo `text-slate-*`, seguindo o padrão já em produção em
  `ClientDashboard.tsx` e `TicketListPage.tsx` (mesmo `h1`, mesmo
  cumprimento "Olá, `<nome>`!", mesmo título de card).
- **`text-on-tint-danger` + `bg-tint-danger`** no selo "SLA" (idêntico ao
  `TicketListPage`); **`text-on-tint-danger`** sozinho no valor "SLA violados",
  seguindo o padrão já em produção no `SlaIndicator` do `TicketListPage`
  (texto sobre `bg-surface`, sem tinta por trás — par já validado ali).
- **`Icon`** (`components/ui`) para o ícone de lista vazia (`check`), o
  calendário do intervalo personalizado (`calendar`) e o ícone do CSAT
  (`star`) — os três traçados batiam caractere a caractere com o pacote.
- **`border-borda/60`** no lugar de `border-slate-100 dark:border-borda/60`
  nos três cabeçalhos de card.

## Os números

| | antes | depois |
|---|---|---|
| linhas da varredura de contraste para este arquivo | 1 (`bg-surface-elevated`/`text-slate-500`, 4,34:1) | 0 |
| cor cheia semântica como texto | 2 | 0 |
| hexadecimal cravado | 8 | 0 |
| `slate-*` cru | 21 | 0 |
| mapas locais de prioridade/status/categoria | 1 (`PRIORITY_DOT`) | 0 |
| `<svg>` soltos | 6 | 3 (sem equivalente no pacote — ver abaixo) |
| testes | não existiam | 6, todos mortos por mutação e revividos |

`npx tsc --noEmit -p tsconfig.app.json`, `npx eslint` (tela e teste) e
`npx vitest run src/test/pages/TechnicianDashboard.test.tsx` sem erro.

## A contagem do que resta à mão

```text
src/pages/dashboard/TechnicianDashboard.tsx: 3 <svg> soltos
```

Os três são os ícones de "Meus tickets ativos", "Fila geral aberta" e "SLA em
risco" nos `KpiCard`. Nenhum dos três bate, caractere a caractere, com um
traçado do `ICON_PATHS` do pacote — são um clipboard, uma caixa de entrada e um
triângulo de aviso desenhado com curva diferente da `warning` do pacote (a do
pacote usa arco, este usa Bézier cúbica). Escolher outro ícone do pacote para
substituí-los é decisão de desenho (qual glifo representa "meus tickets
ativos"), e adicionar um traçado novo ao `Icon.tsx` é escrita em
`src/components/ui/**`, fora do escopo desta tela. **Contagem, não
julgamento**: ficam para quem decidir a forma, não para esta migração.

Zero controle à mão, zero cor crua, zero mapa local restante.

## O que não fiz, e por quê

- **Não toquei os três `<svg>` dos `KpiCard`** — ver acima.
- **Não toquei o desvio F1** (foco por `outline` vs `ring`). Os dois
  `<input type="date">` do intervalo personalizado têm `outline-none` sem
  substituto — pré-existente, não nasceu desta edição (só troquei a cor do
  texto dentro da mesma string de classe). Alinhar foco é uma decisão de
  interação registrada à parte (`VERSION.md`, expira no Checkpoint 4), não uma
  troca de token de cor, e listas de dashboard fora deste campo não têm o
  mesmo problema — não achei motivo para expandir o escopo.
- **Não toquei `AdminDashboard.tsx` nem `ReportsPage.tsx`**, mesmo tendo lido
  os dois como referência (o primeiro repete o mesmo `#0ea5e9` e o mesmo
  `text-slate-100` sem `dark:` no `h1`; o segundo tinha erros de `tsc` já
  antes desta sessão). São telas de outros agentes na mesma árvore
  compartilhada.
- **Não criei nenhum primitivo, token ou entrada de módulo** que não existisse
  — tudo que a tela precisava já estava em `lib/grafico.ts`, `lib/prioridade.ts`
  ou `components/ui`.
