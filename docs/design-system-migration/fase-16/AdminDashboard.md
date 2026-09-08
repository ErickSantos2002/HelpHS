# Fase 16 — `AdminDashboard.tsx`

```text
Página: /dashboard (perfil admin) — frontend/src/pages/dashboard/AdminDashboard.tsx
```

Escopo desta ficha: **só** o que o briefing da Fase 16 atribuiu a este agente —
a cor dos três gráficos Recharts (`AreaChart`, `PieChart`/rosca,
`BarChart`/prioridade), o cromo à mão, e as duas listas da catraca de
contraste nomeadas no briefing. `AdminDashboard` já tinha uma Etapa própria
anterior (Etapa 6, citada em `ESCOPO.md`) que tratou o resto da tela — esta
ficha não reabre nem reaudita aquele trabalho.

---

## Checklist da §29 — só os itens que este agente tocou ou verificou

```text
FUNCIONALIDADE (§29 do prompt mestre)
[x] carrega dados (chamada de API inalterada: método, URL, params) — nenhuma
    chamada de serviço mudou de assinatura; só a cor derivada dos dados.
[ ] filtra / busca / pagina / ordena / cria / edita / exclui / anexa —
    não se aplica a este painel (é leitura agregada).
[x] abre detalhes — filtro por técnico (clique na linha da tabela) intacto.
[ ] respeita permissões — não reverificado nesta passagem (fora do escopo:
    nenhuma cor de permissão foi tocada).
[x] mostra erro (rede) — branch `error || !stats || !report` intacto, não
    tocado.
[x] mostra estado vazio — os três "Sem dados"/"Nenhum ticket" continuam
    condicionados a `.length === 0`; validado por mutação (ver Testes).
[x] mostra loading — `Spinner` intacto, não tocado.
[ ] funciona no mobile — não reverificado visualmente nesta passagem (sem
    captura de tela); nenhuma classe de layout/breakpoint foi tocada.
[x] funciona no tema escuro — é o PONTO desta fase: os hexadecimais por
    `theme === "dark" ? A : B` saíram, e os tokens (`--chart-*`,
    `--text-muted`, `--on-tint-*`) resolvem por tema sozinhos no CSS. Não há
    mais como o cromo do gráfico e o tema divergirem.
[ ] nenhum campo depende do placeholder — não se aplica (sem formulário).
[ ] toda barra desenhada tem papel declarado (`progressbar`/`meter`) — NÃO
    verificado nesta passagem: a tela não tem `role=` nem `aria-*` em lugar
    nenhum (zero ocorrências), incluindo as barras de categoria, SLA e
    `StatusBar`. Pré-existente, fora do escopo de cor desta fase — contado
    abaixo, não corrigido.

ACRESCENTADOS PELAS DECISÕES REGISTRADAS
[ ] estado interativo (visual = árvore) — não reverificado nesta passagem;
    nenhum estado novo foi introduzido.
[ ] nenhuma ação só por mouse — NÃO verificado como aprovação: há um
    `<tr onClick>` (linha ~578, filtro por técnico) sem `tabIndex` nem
    `onKeyDown`. Pré-existente, fora do escopo de cor — contado abaixo.
[x] nenhuma classe `text-slate-*` sem `dark:` correspondente — não mexi em
    nenhuma; as que restam já tinham par (`text-slate-700 dark:text-slate-200`
    etc.), conferido por leitura.
[x] nenhuma cor fora do sistema — ZERADO para os dois alvos que a varredura
    mede nesta tela (pares de contraste e cor cheia semântica como texto).
    Continua havendo paleta crua do Tailwind fora desses dois alvos — contada
    abaixo, não é o que a varredura mede, e está fora do escopo desta fase.
[ ] `Alert` com `live={false}` — não se aplica (o `Alert` de erro já existia
    e não foi tocado).
[ ] foco alinhado ao outline do pacote — não reverificado.
[x] nenhum primitivo reinventado — a cor não usa mapa local nenhum: vem de
    `lib/grafico.ts`, `lib/status.ts` (E18) e `lib/prioridade.ts` (E17).
[x] a catraca desceu — as duas listas nomeadas no briefing foram a zero
    (números abaixo).
```

---

## 1. O que a tela tinha

1. `STATUS_COLORS` (linhas ~46-53) — mapa local de seis hexadecimais por
   rótulo de status, em português e no plural ("Abertos", "Resolvidos"...).
2. `PRIORITY_COLORS` (linhas ~55-60) — mapa local de quatro hexadecimais por
   rótulo de prioridade, no masculino ("Crítico", "Alto"...) — a mesma
   divergência que o `lib/prioridade.ts` documenta ter existido em seis
   telas diferentes.
3. `StatusBar` (linhas ~86-121) — um **terceiro** mapa local, dentro do
   componente, com os mesmos seis hexadecimais de `STATUS_COLORS` reescritos
   à mão (evidência de que os dois já haviam divergido silenciosamente do
   ponto de vista de manutenção, mesmo com os mesmos valores).
4. O cromo do gráfico (linhas ~181-198) — `tooltipBg`, `tooltipBorder`,
   `tooltipColor`, `tooltipStyle`, `tooltipWrapper`, `axisColor`, `gridColor`,
   todos `theme === "dark" ? "#hex" : "#hex"` escritos à mão, dependentes de
   `useTheme()`.
5. `AreaChart` (linha ~392) — gradiente, traço e ponto ativo cravados em
   `#0ea5e9`, a mesma cor que `TechnicianDashboard` e outros três gráficos da
   mesma natureza (chamados por dia) usavam cada um com uma cor diferente.
6. `PieChart`/rosca (linha ~421) — fatias e legenda coloridas por
   `STATUS_COLORS[e.name] ?? "#475569"`; **travada** desde antes da E18, por
   uma tentativa anterior de migração com tokens de interface
   (`color-mix()`) ter quebrado o gráfico (o Recharts escreve a cor em
   atributo de SVG, onde `color-mix()` não resolve em todo motor).
7. `BarChart`/prioridade (linha ~479) — barras coloridas por
   `PRIORITY_COLORS[e.name] ?? "#475569"`, dica customizada com fundo/borda
   do cromo à mão e o texto **sempre** azul-cravado (`#0ea5e9`), sem relação
   com a cor da barra sob o cursor.
8. `slaColor`/`slaBg` (linhas ~64-69) — `text-warning`/`text-danger` (cor
   cheia de significado como cor de texto, reprovação da regra 2) e
   `bg-emerald-500`/`bg-warning`/`bg-danger` (paleta crua e degrau 500 cheio,
   que a E19 documenta reprovar 3:1 como preenchimento no tema claro).
9. Time de equipe (linha ~589, era ~560) — `bg-primary text-white` no avatar
   do técnico selecionado: 3,83:1, abaixo do piso de texto.

Total de hexadecimais cravados removidos: **34** (contados pelo `git diff`).
`useTheme()` e a variável `theme` saíram inteiras — não sobrou nenhum uso.

---

## 2. O que passou a usar

- **`lib/grafico.ts`**: `CROMO` (eixo, grade, dica), `ESTILO_DICA`,
  `ENVOLTORIO_DICA`, `COR_SERIE_TEMPORAL` — para o cromo dos três gráficos e
  para o traço único do `AreaChart` (chamados por dia é uma série temporal de
  medida única).
- **`lib/status.ts`**: `rotuloDeStatus()` e `slotDeStatus()` — a tabela fixa
  `SLOT_DE_STATUS` da E18 — para a cor e o rótulo da rosca e da `StatusBar`.
  As duas passaram a derivar do **mesmo** array (`BLOCOS_DE_STATUS`) e das
  **mesmas** duas funções, então não podem mais divergir uma da outra.
- **`lib/prioridade.ts`**: `rotuloDePrioridade()` (E17, feminino) e
  `graficoDePrioridade()` — para os rótulos e o preenchimento da barra de
  prioridade, e agora também para a cor do texto da dica customizada (antes
  cravada, sem relação com a barra sob o cursor).
- **Legenda obrigatória (E18)**: a rosca já tinha uma lista abaixo do
  gráfico com nome + valor por status; ela passou a mostrar o rótulo
  canônico e a cor real de cada fatia, cumprindo a regra "todo gráfico de
  status leva legenda com o nome de cada série".
- **`text-on-tint-*` / `bg-fill-*`**: `slaColor`/`slaBg` passaram a usar os
  pares medidos pela E8 (texto) e pela E19 (preenchimento) em vez de cor
  cheia crua.
- **`bg-action` + `text-on-primary`**: par do degrau de ação
  (`tailwind.config.js`) no avatar do técnico selecionado.

---

## 3. Mudanças visíveis, e por que não são decisão nova

A fonte única do rótulo é `lib/status.ts`/`lib/prioridade.ts` — nunca mapa
local (regra do briefing, seção 2). Trocar para ela muda texto que a pessoa
lê:

- Legenda de status: "Abertos" → **Aberto**, "Resolvidos" → **Resolvido**,
  "Fechados" → **Fechado**, "Cancelados" → **Cancelado** (singular, igual ao
  que o `Badge` e o quadro kanban já mostram em qualquer chamado individual).
  "Em andamento" não muda (mesma palavra no singular e no plural).
- Rótulo de prioridade: "Crítico"/"Alto"/"Médio"/"Baixo" →
  **Crítica/Alta/Média/Baixa** — prescrito pela emenda E17, já registrada;
  não é decisão nova desta tela, é a mesma tela que ainda não tinha sido
  atualizada.
- Cor do texto da dica da barra de prioridade: antes um azul cravado sempre
  igual; agora acompanha a cor real da barra sob o cursor. Conserto
  colateral, na mesma linha de código que a migração já estava tocando.

---

## 4. A contagem do que resta à mão

Contar, não julgar — um número maior que zero pede olhar, não é
necessariamente pendência desta fase:

- **57** classes de paleta crua do Tailwind fora dos dois alvos que a
  varredura mede (`text-slate-*` ×50, `text-amber-*` ×3, `text-sky-*` ×2,
  `text-emerald-*` ×2 — estas últimas numa coluna da tabela de equipe,
  diferentes das que `slaColor` tinha e que FORAM corrigidas). O `slate-*` é
  o desvio D5 já conhecido e documentado no próprio `varredura-contraste.mjs`
  ("876 usos... vivos por causa do desvio D5"); os `amber-*`/`sky-*`/
  `emerald-*` da tabela de equipe não têm essa cobertura e ficaram de fora
  por não fazerem parte do escopo nomeado (gráficos + as duas listas da
  catraca).
- **12** `<svg>` soltos (ícones dos `KpiCard`, calendário, estrela de CSAT),
  nenhum usando `Icon` de `components/ui`.
- **1** `<tr onClick>` (linha ~578, filtro por técnico) sem `tabIndex` nem
  `onKeyDown` — ação só alcançável por mouse.
- **0** `role=`/`aria-*` na tela inteira — nenhuma das barras desenhadas
  (categoria, SLA, `StatusBar`) declara `progressbar` ou `meter`.

Nenhum desses quatro pontos foi tocado: são eixos diferentes do que esta
fase migra (cor de série de gráfico), e alguns (o `<tr>`, os `role=`)
já existiam antes da Etapa 6 sem terem sido corrigidos nela.

---

## 5. O que não foi feito, e por quê

- **A cor do bloco "Aguardando" da rosca/`StatusBar` é uma aproximação, não
  uma medição.** O `DashboardStats` funde `awaiting_client` e
  `awaiting_technical` num só número (`tickets.awaiting`) — fusão do
  backend, anterior a esta migração. Sem um `TicketStatus` próprio para o
  bloco fundido, o código usa o slot de `awaiting_client` (`--chart-3`).
  Qual dos dois "pesa" mais nessa leitura é decisão de desenho que este
  agente não toma — ver seção "volta para o operador" no relato final.
- **Os 57 usos de paleta crua fora dos dois alvos da varredura, os 12 `<svg>`
  soltos, o `<tr onClick>` sem teclado e a ausência de `role=`** não foram
  tocados — nenhum é cor de série de gráfico, e o briefing desta fase escopa
  só isso mais as duas listas nomeadas. Contados na seção 4.
- **Nenhuma captura de tela foi feita.** A verificação foi por leitura de
  código, `tsc`, `eslint`, o teste automatizado e a varredura de contraste —
  sem uma sessão de navegador disponível nesta passagem.
- **O rótulo/cor do gráfico de prioridade (`BarChart`) não tem caso de teste
  automatizado que leia o DOM renderizado.** `ResponsiveContainer` mede o
  contêiner em 0×0 no ambiente de teste (happy-dom não faz layout de
  verdade), então o eixo, a barra e a dica do Recharts nunca chegam a
  desenhar texto legível para o `@testing-library`. A mesma limitação já
  existe em `TechnicianDashboard.test.tsx`, que pela mesma razão nunca lê
  conteúdo de dentro de um gráfico. As funções que a tela chama
  (`rotuloDePrioridade`, `graficoDePrioridade`) já têm caso de prova em
  `test/lib/prioridade.test.ts`; o que fica sem prova automatizada é que
  ESTA tela as chama com a chave certa — verificado por leitura e por
  `tsc`/`eslint`, não por teste de comportamento.

---

## 6. Números

| medida | antes | depois |
|---|---|---|
| `varredura-contraste.mjs` — pares reprovados nesta tela | 1 (`bg-primary` + `text-white`, repouso) | 0 |
| cor cheia semântica como texto nesta tela (`CHEIAS_CONHECIDAS`) | 2 | 0 |
| hexadecimais cravados na tela | 34 | 0 |
| `theme === "dark" ? A : B` na tela | 5 | 0 |
| mapas locais de cor (status/prioridade) | 3 | 0 |
| testes em `AdminDashboard.test.tsx` | — (arquivo não existia) | 5, todos passando |
| mutações aplicadas e mortas | — | 5 de 5 |

`npx tsc --noEmit -p tsconfig.app.json` e `npx eslint` não relatam nada para
`AdminDashboard.tsx` nem para o teste novo.
