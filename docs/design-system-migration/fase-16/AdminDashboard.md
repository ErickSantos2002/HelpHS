# Fase 16 — `AdminDashboard.tsx`

```text
Página: /dashboard (perfil admin) — frontend/src/pages/dashboard/AdminDashboard.tsx
```

Esta tela foi migrada em **duas passadas**, e a ficha guarda as duas.

A **primeira** (seções 1 a 6) tratou só o que o briefing daquele agente
atribuía: a cor dos três gráficos Recharts (`AreaChart`, `PieChart`/rosca,
`BarChart`/prioridade), o cromo à mão, e as duas listas da catraca de
contraste. Ela deixou de fora 57 classes de paleta crua e 12 `<svg>` soltos,
por uma divergência de escopo entre os prompts de dois agentes.

A **segunda** (seções 7 a 13, de 09/09/2026) fecha exatamente esse resto.
Os números da seção 4 são os de antes dela; a contagem válida hoje está na
**seção 10**.

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
[x] toda barra desenhada tem papel declarado (`progressbar`/`meter`) — a
    segunda passada declarou `progressbar` nas três, a suíte reprovou e a
    mudança foi REVERTIDA; a TERCEIRA passada aplicou a decisão do operador
    (seção 14): `meter` nas duas de conformidade de SLA, papel NENHUM e
    `aria-hidden` na de comparação por categoria, cujo máximo é o maior da
    lista. Fica de fora a faixa da `StatusBar`, que é distribuição empilhada
    — ver seção 9.

ACRESCENTADOS PELAS DECISÕES REGISTRADAS
[ ] estado interativo (visual = árvore) — não reverificado nesta passagem;
    nenhum estado novo foi introduzido.
[ ] nenhuma ação só por mouse — CONTINUA reprovando: o `<tr onClick>` do
    filtro por técnico segue sem `tabIndex` nem `onKeyDown`. Defeito de
    produto, não se conserta aqui. A segunda passada deu à linha um NOME
    acessível que diz o que o clique faz (seção 9) — o que não é a mesma
    coisa que dar-lhe teclado.
[x] nenhuma classe `text-slate-*` sem `dark:` correspondente — na segunda
    passada não sobrou `text-slate-*` NENHUMA, com ou sem par. Duas das que
    havia estavam abaixo do piso de contraste e a varredura não as via
    (seção 8).
[x] nenhuma cor fora do sistema — ZERADO por inteiro depois da segunda
    passada: os dois alvos da varredura (pares de contraste e cor cheia
    semântica como texto) e também as 57 classes de paleta crua que ela não
    mede. Sobra uma ocorrência dentro de um comentário — ver seção 10.
[ ] `Alert` com `live={false}` — não se aplica (o `Alert` de erro já existia
    e não foi tocado).
[ ] foco alinhado ao outline do pacote — não reverificado.
[x] nenhum primitivo reinventado — a cor não usa mapa local nenhum: vem de
    `lib/grafico.ts`, `lib/status.ts` (E18) e `lib/prioridade.ts` (E17). Na
    segunda passada, os 12 ícones passaram a vir de `Icon`/`ICON_PATHS`, sem
    nenhum traçado novo e sem tabela local.
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

## 4. A contagem do que resta à mão (números da PRIMEIRA passada)

> Superada pela **seção 10**. Fica como registro do que a divergência de
> escopo tinha deixado para trás.


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

---

# Segunda passada — 09/09/2026

A primeira passada (commit `cbf8990`) migrou a **cor dos gráficos** e parou
aí, por uma divergência de escopo do prompt: o de um agente pedia a tela
inteira, o do outro só os gráficos. Ficaram de fora **57** classes de paleta
crua do Tailwind (fora de comentário) e **12** `<svg>` soltos, contados na
seção 4 acima. Esta passada fecha os dois, mais a decisão D9.1 sobre a
estrela sólida.

Tudo o que a seção 4 contava agora está em zero, com uma exceção que segue
contada e não corrigida: o `<tr onClick>` sem teclado, que é defeito de
produto.

---

## 7. Os 12 `<svg>` soltos

Casados pelo traçado `d`, caractere a caractere, contra `ICON_PATHS` em
`components/ui/Icon.tsx`. **Dez** bateram exatamente e não precisaram de
nada novo:

| onde | virou |
|---|---|
| `KpiCard` "Total de tickets" | `Icon name="ticket"` |
| `KpiCard` "Abertos" | `Icon name="inbox"` (do pacote desde a E21) |
| `KpiCard` "Em andamento" | `Icon name="refresh"` |
| `KpiCard` "Aguardando" | `Icon name="clock"` |
| `KpiCard` "Resolvidos" | `Icon name="check"` |
| `KpiCard` "CSAT médio" | `Icon name="star"` (o contorno) |
| `KpiCard` "Tempo médio resolução" | `Icon name="chart"` |
| `KpiCard` "SLA Resposta violado" | `Icon name="clock"` |
| intervalo personalizado | `Icon name="calendar"` |

**Dois** não bateram caractere a caractere, e são o mesmo significado
desenhado de outro jeito — o triângulo de aviso dos cartões "SLA violado" e
"SLA Resolução violado":

```
tela    M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4…
pacote  M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3…
```

Unificados em `warning`, que é exatamente o que a E21 fez com dez casos
assim (um "certo" sem círculo, outra lupa, outro aviso). Nenhum ícone novo
foi criado, e nada fora de `AdminDashboard.tsx` foi escrito.

### O décimo segundo: a estrela sólida, e a decisão D9.1

O `<svg>` da média de satisfação por técnico era de **outra família**:

```jsx
<svg className="w-3.5 h-3.5 text-amber-400" viewBox="0 0 20 20" fill="currentColor">
```

`viewBox` de 20 e preenchimento cheio, contra os 24×24 `fill="none"
stroke="currentColor"` do `Icon`. A E21 **barrou** a troca automática — e
barrou pelo motivo certo: `ICON_PATHS` é mapa de texto, todo texto cabe, e
nem `tsc` nem teste de componente acusam a escala errada.

O operador decidiu (D9.1) no sentido inverso do que a E21 sugeria:

> **Ícone é só contorno.** A estrela preenchida vive dentro do `Rating` do
> pacote. Se um lugar precisar de estrela **como ícone**, é o contorno 24×24
> que já está no `ICON_PATHS`.

Então este caso virou `Icon name="star"`, e **a aparência muda**: a estrela
deixa de ser preenchida e passa a ser de traço. Mudança **prescrita**, não
decidida aqui — registrada tanto neste arquivo quanto no ponto de uso.

O `Rating` do pacote **não** foi portado, e a razão está verificada: ele é
de **cinco** estrelas e a pesquisa do HelpHS é de **1 a 10 com rótulo por
nota**. São instrumentos diferentes; portá-lo seria forçar outra escala
sobre um dado que não a tem.

O `text-amber-600 dark:text-amber-400` do número ao lado e o
`text-amber-400` da própria estrela saíram junto, para `text-on-tint-warning`.

---

## 8. As 57 classes de paleta crua

Zero fora de comentário. O mapeamento não foi por semelhança de nome — foi
pelo **pixel que o D5 realmente pinta**. O desvio D5 (em `index.css`, vale
só no tema claro) **inverte** a escada:

```
html:not(.dark) .text-slate-100 → slate-900     .text-slate-400 → slate-600
html:not(.dark) .text-slate-200 → slate-800     .text-slate-500 → slate-500
html:not(.dark) .text-slate-300 → slate-700     .text-slate-600 → slate-400
```

| classe crua | ×  | token | por quê |
|---|---:|---|---|
| `text-slate-700 dark:text-slate-200` | 10 | `text-conteudo` | `--text-body` é slate-800/slate-200 |
| `text-slate-500` | 6 | `text-conteudo-muted` | ver nota do colapso, abaixo |
| `text-slate-400` | 8 | `text-conteudo-muted` | **1:1 exato**: com o D5 é slate-600 no claro e slate-400 no escuro, que é `--text-muted` nos dois |
| `text-slate-600 dark:text-slate-300` | 3 | `text-conteudo-muted` | ver "o que ficou melhor", abaixo |
| `text-slate-900 dark:text-slate-100` | 1 | `text-conteudo-heading` | **1:1 exato** |
| `text-slate-100` (h1 "Dashboard") | 1 | `text-conteudo-heading` | ver "o que ficou melhor", abaixo |
| `border-slate-100 dark:border-borda/60` | 4 | `border-borda-muted` | `--border-muted` é slate-100 no claro, o mesmo valor cravado |
| `divide-slate-50 dark:divide-borda/30` | 1 | `divide-borda-muted` | o degrau mais suave que o pacote tem |
| `hover:bg-slate-50 dark:hover:bg-surface-elevated` | 1 | `hover:bg-surface-elevated` | o token já é branco-acinzentado no claro |
| `text-emerald-600 dark:text-emerald-400` | 1 | `text-on-tint-success` | regra 2: cor cheia como texto reprova |
| `text-sky-600 dark:text-sky-400` | 1 | `text-on-tint-info` | idem |
| `text-amber-600 dark:text-amber-400` + `text-amber-400` | 2 | `text-on-tint-warning` | idem |

### Dois casos em que a troca CONSERTOU contraste, e não só nome

Os dois estavam abaixo do piso e a varredura não os via — ela pareia cor de
texto e cor de fundo **dentro do mesmo literal de classe**, e nenhum destes
dois elementos declara fundo no mesmo literal (herdam de um ancestral):

1. **`text-slate-600 dark:text-slate-300`** (nome da categoria, "Atribuídos"
   e "Tempo médio" da tabela de equipe). No tema claro o D5 pinta isso de
   **slate-400**, que sobre `--surface` branca dá **2,85:1**. Agora é
   `--text-muted`: **7,58:1**.
2. **`text-slate-100` no `<h1>` "Dashboard"**, sem par `dark:` nenhum. Ele é
   legível hoje **só** porque o D5 o repinta de slate-900 no claro — sem o
   desvio, é texto quase branco sobre superfície branca. Como
   `--text-heading` (slate-900/slate-100), o pixel é o mesmo nos dois temas
   por token, e não por remendo de fase.

### O que se perdeu: dois degraus de cinza colapsaram num só

`text-slate-400` e `text-slate-500` viraram os dois `text-conteudo-muted`.
Antes eles diferiam (slate-600 vs slate-500 no claro; slate-400 vs slate-500
no escuro) e marcavam uma hierarquia fraca entre "rótulo secundário" e
"número entre parênteses".

A escada de texto do pacote tem quatro degraus, e o degrau abaixo do `muted`
— `--text-faint` — dá **3,07:1** sobre `--surface` no tema claro, abaixo do
piso de texto (e a própria regra 4 do briefing já registra que ele reprova
sobre `--surface-elevated`, com 2,34:1). Escurecer é o único lado seguro. O
resultado é uma tela com **menos** variação de cinza do que tinha; é perda
decorativa, e nenhuma informação dependia da diferença.

---

## 9. Nome acessível e papel — o que deu para fazer sem redesenhar

O `<tr onClick>` **não** foi consertado: dar teclado a ele é redesenhar o
controle, e o defeito é de produto, já registrado. O que dava para fazer sem
tocar no desenho foi feito:

- **A linha da tabela de equipe passou a ter nome.** Antes ela se anunciava
  pela colagem das sete células ("Ana Silva 5 3 2 80% 4.0h 9.0 (2)") e não
  dizia em lugar nenhum que era clicável nem o que o clique faria. Agora o
  `aria-label` diz, e acompanha o estado: *"Ana Silva — clique para filtrar o
  painel por este técnico"* / *"Ana Silva — filtro ativo, clique para
  remover"*. **Isso não conserta o acesso por teclado** — quem navega por
  teclado continua sem alcançar a linha.
- **As barras desenhadas ganharam papel** — mas **não este**. Esta passada
  declarou `role="progressbar"` nas três (categoria, conformidade por
  prioridade, linha do técnico) e **quebrou a suíte**: `barra-de-sla.test.ts`
  já proibia esse papel neste arquivo, com o motivo escrito. Foi revertida.
  O papel certo de cada uma está na **seção 14**, e foi decidido pelo
  operador, não aqui.

Continua **sem** papel a faixa da `StatusBar` (a barra empilhada de
distribuição). Ela não é uma barra de progresso, e a legenda logo abaixo já
lista nome e valor de cada bloco em texto — o desenho é redundante, e que
papel dar a ele (`img` com resumo, ou `aria-hidden`) é decisão de desenho.
Vai no relato, não foi decidida aqui.

---

## 10. A contagem, revisada

| medida | 1ª passada | agora |
|---|---:|---:|
| classes de paleta crua do Tailwind, fora de comentário | 57 | **0** |
| `<svg>` soltos | 12 | **0** |
| hexadecimais cravados | 0 | 0 |
| `theme === "dark" ? A : B` | 0 | 0 |
| mapas locais de cor | 0 | 0 |
| linhas da `varredura-contraste.mjs` para esta tela | 0 | **0** |
| barras desenhadas sem papel declarado | 4 | **1** (a faixa da `StatusBar`) — ver seção 14 |
| controles alcançáveis só por mouse | 1 | **1** (o `<tr onClick>`) |
| casos em `AdminDashboard.test.tsx` | 5 | **11** (**14** depois da seção 14) |

Sobra **uma** ocorrência de paleta crua no arquivo, `bg-emerald-500` na
linha 82 — **dentro de um comentário**, o que explica de qual classe
`slaBg()` saiu. A varredura ignora comentário de propósito (o `--catraca`
chegou a contar a explicação do conserto como se fosse o defeito, e isso
cria pressão para não explicar o que foi removido). Fica.

---

## 11. Testes

Cinco casos **acrescentados**, os cinco antigos intocados. Nenhum deles lê
classe: o jsdom não aplica CSS, então afirmação sobre classe passa com o
elemento invisível e reprova com ele visível. O que estes leem é o que
sobrevive sem CSS — o traçado do desenho, a escala, o papel declarado e o
nome acessível.

| caso | mutação que o matou |
|---|---|
| a estrela do CSAT é o contorno do pacote | `name="star"` → `name="check"` na linha do técnico |
| todo ícone desenha na escala do pacote | devolve o `<svg>` sólido `viewBox="0 0 20 20"` ao cartão de CSAT |
| o calendário do intervalo personalizado também | `name="calendar"` → `name="clock"` |
| a linha do técnico diz o que o clique faz | apaga o `aria-label` da `<tr>` |
| ~~cada barra declara papel e valor~~ | **removido junto com a reversão** — ver seção 14 |

**Controle antes da primeira mutação**: a suíte rodou sem mutação nenhuma e
passou (10 de 10) — sem isso, um roteiro que não executa o vitest lê "não
falhou" como "o mutante sobreviveu". O vitest foi chamado por
`process.execPath` + `node_modules/vitest/vitest.mjs`, nunca por `npx.cmd`.

**5 de 5 mutações morreram**, nenhuma com falha colateral (cada mutação
derrubou só o seu caso — isolamento limpo). A restauração grava, **relê para
conferir** e repete até oito vezes; a igualdade byte a byte com o original
foi confirmada no fim.

Uma dessas cinco (a do `role="progressbar"`) morria contra um caso que **não
existe mais**: ele foi retirado com a reversão. Uma mutação que mata um caso
errado é uma mutação bem-sucedida contra a régua errada — o que ela media
não era a acessibilidade da barra, era a existência do papel que a suíte
proibia. Ver seção 14.

`npx tsc --noEmit -p tsconfig.app.json` e `npx eslint` não relatam nada para
`AdminDashboard.tsx` nem para o teste.

---

## 12. O que NÃO foi feito nesta passada, e por quê

- **O `<tr onClick>` continua sem teclado.** Defeito de produto já
  registrado; consertá-lo é redesenhar o controle.
- **A faixa da `StatusBar` continua sem papel declarado** — que papel dar a
  uma barra empilhada de distribuição cuja legenda já está escrita embaixo é
  decisão de desenho.
- **A cor do bloco "Aguardando"** continua sendo o slot de `awaiting_client`,
  pela fusão que o backend faz em `tickets.awaiting`. Inalterado desde a
  primeira passada; segue no relato ao operador.
- **Nada fora de `AdminDashboard.tsx` e do seu teste foi escrito.** Nenhum
  ícone novo entrou no pacote, nenhum token novo foi criado, nenhum
  `ICON_PATHS` local nasceu.
- **Nenhuma captura de tela.** A verificação foi por leitura, `tsc`,
  `eslint`, o teste e a varredura — sem sessão de navegador nesta passagem.
  A mudança da estrela (preenchida → contorno) e o colapso dos dois degraus
  de cinza são visuais e **não** foram vistos em pixel.

---

## 13. Colisão na árvore compartilhada, durante esta passada

Registrado porque muda a leitura de qualquer `git diff` desta tela.

Enquanto esta passada corria, **outra sessão editou o mesmo arquivo**: a
decisão **D9.2** (o `FilterSelect` se parte em `Select` nativo para lista
curta e `Selector variant="filter"` para lista longa) chegou em
`AdminDashboard.tsx` às 08:13, sem commit. O primeiro roteiro desta passada
falhou por isso — a linha de `import` que ele esperava já não existia — e,
como a gravação só acontece no fim, **nada foi escrito pela metade**.

O trabalho da D9.2 foi **preservado inteiro**; esta passada foi refeita
sobre o arquivo já com ele. Os dois conjuntos de mudança são ortogonais
(controles de filtro de um lado, classes de cor e ícones do outro) e o
`git diff` desta tela hoje contém **os dois**.

Um efeito colateral bom: o `<select>` nativo que a D9.2 trouxe é o que
permitiu ao novo caso do calendário alcançar o ramo `periodKey === "custom"`,
que nenhum teste alcançava.

## Mudança funcional: escolher período deixou de ser desfazível

**Registrada por decisão do operador em 09/09/2026.** O filtro de período
tinha uma linha de limpar, e ela **saiu**.

### O que quebrava

```ts
PERIOD_OPTIONS.find((p) => p.key === periodKey)!.days
```

Limpar devolvia `""`, que não é chave de nenhuma opção. O `find` devolvia
`undefined`, o `!` lia `days` dele, e **a tela inteira quebrava** — não
degradava, não mostrava erro: quebrava.

### Por que a saída foi tirar a opção, e não tratá-la

Porque o servidor não tem esse estado. O parâmetro é declarado assim:

```python
period: Annotated[int, Query(ge=1, le=365)] = 30
```

**`ge=1`.** Não existe "todo o período" — o mínimo é um dia, o máximo é um
ano. A linha de limpar não tinha para onde apontar: ela oferecia um estado que
a API recusa.

A regra do operador é essa: *tratar `""` como estado válido (sem recorte) ou
cair para o padrão — nunca ler `days` de `undefined`; a opção de limpar só sai
se "todo o período" não existir no backend.* **Este é o segundo caso.**

### E o `!` saiu junto, que era o defeito de verdade

Tirar a opção fecha o caminho **conhecido** até o estouro. O `!` estourava com
**qualquer** chave desconhecida — um valor guardado de uma versão anterior, um
link com parâmetro na URL, um estado restaurado. Agora recua para `30`, que é
o padrão declarado no backend: o que o servidor faria sozinho se o parâmetro
não fosse mandado.

Recuo para 30 e **não** para o primeiro da lista, de propósito: se alguém
reordenar `PERIOD_OPTIONS`, o recuo continua sendo o mesmo número.

### O que o usuário perde

A tela abre com um período escolhido e não há como voltar a "nenhum". Isso é
perda real de reversibilidade, e é o preço de a API não ter o estado — a
alternativa seria a tela oferecer algo que o servidor recusa.

---

## 14. `meter` não é `progressbar` — a decisão, e o que ela custou

**Decidida pelo operador em 09/09/2026, e aplicada numa terceira passada.**
Ela é o motivo de as seções 9 e 11 estarem corrigidas acima.

### O que aconteceu

A segunda passada declarou `role="progressbar"` nas **três** barras
desenhadas da tela citando a §29 ("toda barra desenhada tem papel
declarado"). Isso **quebrou a suíte**: `barra-de-sla.test.ts` — mais antigo —
proíbe esse papel neste arquivo, e o motivo está escrito lá desde que foi
criado. As três foram revertidas e a distinção subiu ao operador.

### A decisão

| barra | papel | por quê |
|---|---|---|
| **conformidade de SLA** (por prioridade, e a da linha do técnico) | `role="meter"` com `aria-valuenow`/`aria-valuemin`/`aria-valuemax` e **nome** | é medição dentro de faixa **conhecida e fixa**, 0 a 100 |
| **comparação** (contagem por categoria) | **sem papel**, `aria-hidden`, com o valor **em texto** | o máximo é `categoryMax` — o maior da lista —, não é progresso nem medição de faixa fixa |
| **distribuição** (a faixa da `StatusBar`) | continua sem papel, e continua **pendente de decisão** | seção 12, inalterada |

`meter` é o papel de **medição**; `progressbar` é o de **tarefa avançando**.
A distinção não é sutileza de vocabulário: um leitor de tela anuncia "60 por
cento **concluído**" para `progressbar`, e a conformidade de SLA não está
concluindo nada. Uma barra que vai a "o maior que aparecer hoje" não tem
escala nenhuma para anunciar, e declarar qualquer um dos dois papéis nela
poria um número numa escala que não existe.

### O que entrou no código

```
role="meter"  aria-valuenow={Math.round(item.compliance_rate)}
              aria-valuemin={0}  aria-valuemax={100}
              aria-label={`Conformidade de SLA — ${item.priority}`}

role="meter"  aria-valuenow={Math.round(t.sla_compliance_rate)}
              aria-valuemin={0}  aria-valuemax={100}
              aria-label={`Conformidade de SLA de ${t.technician_name}`}
```

E na de comparação, só `aria-hidden="true"`. **A contagem já estava escrita**
em texto ao lado do nome da categoria (`{cat.count}`, na linha de cima), e
foi conferida antes de esconder o desenho: `aria-hidden` numa barra só é
honesto se o número estiver em algum lugar que o leitor de tela alcance. Não
foi preciso escrever nada — mas o caso de teste passou a **prender** esse
par, para que esconder o desenho nunca vire esconder o dado.

Zero mudança visual nas três.

### Onde a decisão ficou gravada

Nos dois lados, porque a próxima pessoa pode chegar por qualquer um:

- **`barra-de-sla.test.ts`**, no caso *"as barras de comparação NÃO viraram
  progressbar"* — que **fica**, e passou a prender a decisão inteira em vez
  de só a proibição: `progressbar` segue proibido no `AdminDashboard` inteiro
  (para as duas coisas), a de comparação não tem papel e é `aria-hidden`, e
  as duas de conformidade são `meter` com valor, escala e nome. O comentário
  do caso explica **por que** os papéis são diferentes, que é o que faltava:
  quem lia só a proibição não tinha como saber que `meter` era permitido, e
  foi isso que custou a reversão.
- **`AdminDashboard.test.tsx`**, em três casos novos que provam o mesmo pelo
  **DOM** (o outro arquivo prova pelo texto do `.tsx`), e no comentário que
  substituiu a nota "não existe aqui um caso de `progressbar`".
- **No próprio `.tsx`**, num comentário acima de cada uma das três barras.

### Testes e mutação

14 casos em `AdminDashboard.test.tsx` (11 → 14) e 5 em `barra-de-sla.test.ts`
(o mesmo número; o quinto cresceu). **19 de 19 passam.**

**Controle sem mutação nenhuma antes da primeira**, e ele passou — sem isso,
um roteiro que não executa o vitest lê "não falhou" como "o mutante
sobreviveu". Chamada por `process.execPath` + `node_modules/vitest/vitest.mjs`.

**9 de 9 mutações morreram.** Nenhuma é de classe — o jsdom não aplica CSS, e
trocar classe não muda o que o caso mede:

| # | mutação | o que ela quebra |
|---|---|---|
| M1 | a conformidade vira `progressbar` | papel |
| M2 | a barra do técnico perde o `role` | papel |
| M3 | a barra de comparação ganha um `role` | papel |
| M4 | `aria-valuenow` da conformidade passa a anunciar `item.breached` | valor |
| M5 | `aria-valuenow` do técnico passa a anunciar `t.total_assigned` | valor |
| M6 | some o `aria-valuemax={100}` da conformidade | escala |
| M7 | o `aria-label` da conformidade deixa de dizer a prioridade | nome |
| M8 | some o `aria-hidden` da comparação | elemento |
| M9 | some o `<span>` com `{cat.count}` | elemento |

M9 é a que importa mais: ela prova que o par *"esconder o desenho"* + *"o
número em texto"* é medido junto, e não só metade dele.

O roteiro de M6 **abortou na primeira tentativa, de propósito**: o padrão
`aria-valuemax={100}` com recuo de 20 espaços é **substring** do de 28
espaços da linha do técnico, e casava com os dois. A contagem de ocorrências
antes de gravar pegou; o padrão foi ancorado no `aria-valuemin` de cima e a
mutação passou a atingir uma barra só. Sem essa contagem, uma "mutação" que
muda dois lugares mede outra coisa.

Restauração com repetição (até oito vezes), releitura para conferir e
igualdade byte a byte confirmada no fim — o `finally` protege contra o
processo morrer, não contra a gravação falhar.

`tsc --noEmit`, `eslint` nos três arquivos e `varredura-contraste.mjs` (zero
linhas para esta tela) ficaram limpos.

### O que esta passada NÃO fez

- **Não tocou na faixa da `StatusBar`.** Ela segue sem papel e segue pendente
  de decisão (seção 12); a decisão do operador cobriu comparação e
  conformidade, não distribuição.
- **Não mexeu no rótulo visível da prioridade.** A seção "Conformidade SLA"
  escreve `{item.priority}` cru — `critical`, `low` —, com `capitalize` no
  CSS, e não `rotuloDePrioridade()`. O `aria-label` da barra repete esse
  mesmo texto **de propósito**, para o nome acessível não divergir do que
  está na tela. Trocar o rótulo visível é mudança funcional, e vai no relato
  ao operador.
- **Nada fora dos três arquivos do escopo.**
