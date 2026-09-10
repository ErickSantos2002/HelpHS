# Fase 16 — `NotificationsPage.tsx`

```text
Página: /notificacoes — frontend/src/pages/notifications/NotificationsPage.tsx
Teste:  frontend/src/test/pages/NotificationsPage.test.tsx (novo)
```

Esta tela entrou na fase com **13 `<svg>` soltos — a maior concentração do
sistema** — e com o defeito que a medição previu: um mapa `tipo → ícone` local,
`TYPE_META`, que também carregava a cor, escrita como classe. Ao lado dele havia
um segundo mapa, `TYPE_LABEL`, com as mesmas dez chaves e nada obrigando os dois
a concordar.

---

## Checklist da §29

```text
FUNCIONALIDADE (§29 do prompt mestre)
[x] carrega dados — `getNotifications` inalterado: mesmos parâmetros, mesmo
    `PAGE_SIZE`, mesmo cálculo de `offset`. Nada de rede mudou.
[x] filtra / pagina — as duas abas e o `Pagination` seguem idênticos; o filtro
    validado por mutação (M17), a paginação por mutação (M9).
[ ] ordena / cria / edita — não se aplica: a tela é leitura mais três ações.
[x] exclui — "Remover notificação" segue chamando `deleteNotification` e
    tirando a linha; validado por mutação (M15), e o `stopPropagation` que
    impede a exclusão de virar navegação por mutação (M7).
[ ] respeita permissões — não reverificado: a tela não decide permissão (só
    lista o que o backend devolve para o usuário do token), e nada disso foi
    tocado.
[x] mostra erro (rede) — o `catch` já existia e continua; passou a ter caso de
    teste, validado por mutação (M11).
[x] mostra estado vazio — as duas frases (com e sem o filtro de não lidas)
    condicionadas a `items.length === 0`; validado por mutação (M10).
[x] mostra loading — `Spinner` intacto, não tocado.
[ ] funciona no mobile — não reverificado visualmente (sem captura de tela).
    Nenhuma classe de layout ou breakpoint mudou; a única mudança de caixa é
    o selo do tipo, que passou do `<span>` à mão para o `Badge` (raio e altura
    iguais, padding horizontal de 8px para 10px).
[x] funciona no tema escuro — é o ponto da fase: os 10 pares
    `text-slate-X dark:text-slate-Y` / `bg-slate-X dark:bg-slate-Y` saíram e os
    tokens resolvem por tema sozinhos no CSS. Não há mais como o claro e o
    escuro divergirem por esquecimento de um `dark:`.
[ ] nenhum campo depende do placeholder — não se aplica: a tela não tem campo.
[ ] toda barra desenhada tem papel declarado — não se aplica: a tela não
    desenha barra nem medidor.

ACRESCENTADOS PELAS DECISÕES REGISTRADAS
[x] estado interativo (visual = árvore) — CORRIGIDO em dois lugares: a aba
    valendo ganhou `aria-pressed` (era dita só pelo fundo) e a linha não lida
    ganhou uma marca `sr-only` (era dita só pela barrinha, pelo fundo e pelo
    peso da fonte). Os dois validados por mutação (M6, M4, M5).
[ ] nenhuma ação só por mouse — NÃO verificado como aprovação. O botão de
    remover deixou de ser invisível para o teclado (`focus-visible:opacity-100`
    ao lado do `group-hover:opacity-100`), mas ele continua sendo um `<button>`
    DENTRO de um `<div role="button">`. Aninhamento inválido, pré-existente,
    contado abaixo e relatado ao operador.
[x] nenhuma classe `text-slate-*` sem `dark:` correspondente — ZERADO: não há
    mais nenhuma classe de paleta crua, com ou sem par.
[x] nenhuma cor fora do sistema — ZERADO: 32 → 0 classes de paleta crua,
    0 hexadecimais, 5 → 0 cores cheias de significado como cor de texto,
    2 → 0 `text-white`.
[x] `Alert` com `live={false}` — não se aplica em sentido estrito, e a omissão
    é a escolha certa: o aviso desta tela aparece DEPOIS de uma falha de rede,
    não no primeiro desenho. Região viva anuncia mudança, e aqui houve uma.
[ ] foco alinhado ao outline do pacote — não alterado. Os dois `<button>` à mão
    (as abas e o remover) continuam sem anel de foco declarado — desvio F1, com
    prazo no Checkpoint 4. O `focus-visible:opacity-100` acrescentado ao
    remover resolve a VISIBILIDADE do controle, não o anel.
[x] nenhum primitivo reinventado — o selo do tipo virou `Badge`, os 13 `<svg>`
    viraram `Icon`. Restam 2 `<button>` à mão (seção 4).
[x] a catraca desceu — as duas entradas desta tela foram a zero (seção 6).
```

---

## 1. O que a tela tinha

1. **`TYPE_META`** (linhas 32-114) — mapa local de **dez** linhas, cada uma com
   um `<svg>` inteiro escrito à mão e uma string de classe. As classes vinham de
   quatro famílias diferentes, e três delas são reprovação direta:
   `bg-primary/10 text-primary` (três tipos), `bg-green-500/10 text-green-600
   dark:text-green-400` (um), `bg-slate-100 dark:bg-slate-700/50 text-slate-500`
   (três) e a **cor cheia semântica como cor de texto** nos outros três
   (`text-info`, `text-warning` ×2, `text-danger`).
2. **`TYPE_LABEL`** (linhas 17-28) — segunda tabela para o mesmo dado, com as
   mesmas dez chaves. As duas concordavam hoje; nada além da atenção de quem
   editasse garantia que continuassem concordando.
3. **`DEFAULT_META`** (linhas 116-123) — o recuo, com o **décimo primeiro**
   `<svg>` (um sino) e mais uma string de classe crua.
4. **13 `<svg>` soltos**: os dez do `TYPE_META`, o do `DEFAULT_META`, o sino
   grande do estado vazio e o X do botão de remover.
5. **`bg-primary` + `text-white`** na aba ativa (linha 226) — **3,83:1**, a
   única entrada desta tela na catraca de contraste.
6. **`bg-white/20 text-white`** na contagem dentro da aba "Não lidas" (linha
   232), desenhada **sempre** — inclusive com a aba desligada, quando não há
   fundo escuro nenhum por baixo e o número ficava branco sobre a página.
7. **`text-primary` na contagem do cabeçalho** (linha 200) — o degrau de MARCA
   sobre `--bg-base`, que o próprio `tailwind.config.js` registra como
   **3,66:1**: reprova AA, e é texto.
8. **10 pares `slate` claro/escuro** e 12 `slate` sem par, em cinco degraus de
   cinza (900/100, 700/200, 600/400, 500, 400) sem regra distinguindo-os.
9. **`bg-primary/[0.03] dark:bg-primary/[0.05]`** na linha não lida — dois
   valores de opacidade escolhidos à mão, um por tema.
10. **Nada disso chegava à árvore de acessibilidade**: nem qual aba estava
    valendo, nem quais linhas estavam por ler.

| medida | antes |
|---|---:|
| classes de paleta crua | **32** em 332 linhas |
| `<svg>` soltos | **13** |
| cor cheia semântica como texto | **5** |
| `text-white` | **2** |
| hexadecimais cravados | 0 |
| tabelas locais para o mesmo dado | **2** (`TYPE_LABEL` + `TYPE_META`) |

---

## 2. O que passou a usar

- **`Icon` de `components/ui`** — 3 sítios de renderização cobrindo os 13
  `<svg>`, com **10 nomes** do pacote. Nenhum ícone novo foi necessário: os 13
  eram `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"` — a mesma
  família do `Icon`, conferida antes de trocar.

  | era | virou | como casou |
  |---|---|---|
  | `ticket_created` | `ticket` | traçado **idêntico**, caractere a caractere |
  | `ticket_assigned` | `user` | traçado **idêntico** |
  | `ticket_updated` | `refresh` | traçado **idêntico** |
  | `ticket_resolved` | `check` | traçado **idêntico** |
  | `ticket_closed` | `check` | `M5 13l4 4L19 7` — o "certo" **sem círculo**, um dos dez que a E21 unificou por significado |
  | `sla_warning` | `clock` | traçado **idêntico** |
  | `sla_breached` | `warning` | triângulo de aviso com outro cálculo de vértice — **mesmo significado**, o caso que a E21 nomeia |
  | `chat_message` | `chat` | um caractere de diferença no arco (`9.863` contra `9.86`); mesmo balão |
  | `satisfaction_survey` | `star` | traçado **idêntico** |
  | `system` | `settings` | os **dois** traçados idênticos — é o ícone de traçado múltiplo que a **E21** subiu |
  | `DEFAULT_META` | `bell` | traçado **idêntico** |
  | sino do estado vazio | `bell` | traçado **idêntico** |
  | X do botão remover | `close` | traçado **idêntico** |

- **`Badge` de `components/ui`** — 1 uso, o selo do tipo. Com ele vêm as
  variantes medidas pela **E8**: fundo na tinta, texto no par da tinta, borda a
  30%. Saíram as quatro famílias de classe crua e as cinco cores cheias.
- **`TOM_STATUS` de `lib/status.ts`** — 1 uso, o quadrado de 36px do ícone. A
  chave dele é a **variante**, não o status, e as classes lá estão escritas por
  extenso, que é o que o Tailwind exige. Reimplementá-lo aqui com outro nome
  seria a variante local que esta migração existe para eliminar. O nome carrega
  a origem, não o limite do uso — está relatado ao operador como observação.
- **`bg-action` + `text-on-primary`** na aba ativa, em vez de `bg-primary` +
  `text-white`.
- **`bg-action-hover` + `text-on-primary`** na contagem dentro da aba ativa: no
  claro é `primary-700` sob branco, no escuro `primary-300` sob navy — nos dois
  casos um degrau **mais** contrastado que o par base do fundo de ação.
- **`bg-tint-primary` + `text-on-tint-primary`** na mesma contagem quando a aba
  está desligada, que é o par `primary` do `Badge`.
- **`bg-action-tint`** na linha não lida e **`bg-action`** na barrinha da
  esquerda, no lugar dos dois valores de opacidade à mão.
- **A escada de texto do pacote** — `text-conteudo-heading` (título da página,
  título não lido, contagem), `text-conteudo` (texto do estado vazio),
  `text-conteudo-muted` (todo o resto).
- **Uma tabela local por dado** — `TIPO`, com rótulo, ícone e variante na mesma
  linha, e três acessores com recuo (`rotuloDeTipo`, `iconeDeTipo`,
  `varianteDeTipo`). Acrescentar um tipo num lugar e esquecê-lo no outro deixou
  de ser possível.

A tabela é **exportada** da tela, só para que o teste a compare literal. Isso
liga o `react-refresh/only-export-components`, silenciado na linha com o motivo
ao lado: o remédio da regra é arquivo próprio, e arquivo próprio está fora do
escopo desta fase.

### Por que a tabela de tipo ficou local, e não virou módulo

Ela **não** é uma fonte única que falta em `src/lib/`. Tipo de notificação não é
status, prioridade nem categoria: é dado desta tela e só desta — nenhum outro
arquivo do front lê `NotificationType`. Criar `lib/notificacao.ts` seria escrita
fora do escopo do briefing, e o módulo teria um consumidor só. O que ela ganhou
foi a **disciplina** dos módulos, no espírito do que a `AuditLogsPage` fez com
as ações de auditoria: rótulo, ícone e variante lado a lado, variante em vez de
classe, acessores que recuam para o neutro.

---

## 3. Mudanças visíveis, e de onde saem

Nenhuma é arbitrária, mas seis precisam ser vistas antes de subir:

1. **Resolvido e encerrado passaram a usar o mesmo ícone.** O desenho do
   encerrado era um "certo" sem círculo, e a E21 unificou os dois traçados de
   "certo" num nome só — é literalmente o caso que a emenda nomeia. O que separa
   os dois tipos passou a ser a variante (`success` contra `muted`) e o rótulo,
   que está escrito dentro do selo. **É consequência de decisão de desenho já
   tomada**, não decisão nova, mas muda o que se vê.
2. **Os selos perderam quatro famílias de classe e ganharam seis variantes.** O
   agrupamento é pelo que o evento pede de quem lê: `primary` (criado,
   atualizado, nova mensagem), `info` (atribuído), `success` (resolvido),
   `warning` (aviso de SLA, pesquisa de satisfação), `danger` (SLA violado),
   `muted` (encerrado, sistema). **O agrupamento é decisão de desenho** — está
   na seção 5 e no relato ao operador.
3. **O destaque da linha não lida ficou mais forte, sobretudo no escuro.** Era
   3% de `primary` no claro e 5% no escuro; passou a `--action-tint`, que no
   claro é `primary-50` (comparável) e no escuro é `primary` a 15% (três vezes
   mais presente). Os 5% do escuro eram praticamente invisíveis — a linha não
   lida se distinguia só pelo negrito.
4. **A contagem do cabeçalho perdeu o azul.** Era `text-primary` sobre o fundo
   da página: **3,66:1**, reprova AA. Não é link, então o degrau de link também
   não servia — quem o lesse pensaria que dá para clicar. A ênfase passou para o
   degrau de título mais `font-semibold`, que é contraste e peso, não cor.
5. **A contagem dentro da aba "Não lidas" ficou legível com a aba desligada.**
   Ela desenhava `bg-white/20 text-white` **sempre**: com a aba ativa isso é
   branco sobre azul; com a aba desligada é branco sobre a página. Agora ela
   acompanha o estado (seção 2).
6. **O horário relativo escureceu um degrau.** Era `text-slate-400`, que é
   exatamente `--text-faint`; ficou em `--text-muted`, porque a linha pinta
   `hover:bg-surface-elevated` e `faint` sobre a superfície elevada dá
   **2,34:1** — não é par, e é o mesmo motivo pelo qual a `AuditLogsPage` subiu
   os UUIDs dela.

E três que não mudam pixel, mas mudam o que um leitor de tela anuncia:

- **`aria-pressed` nas duas abas.** Qual filtro está valendo era dito só pela
  cor de fundo; um botão que liga e desliga é um botão de alternância, e a
  árvore tem palavra para isso.
- **Uma marca `sr-only` "Não lida." em cada linha por ler.** O estado era dito
  pela barrinha, pelo fundo e pelo peso — três coisas que não chegam à árvore.
- **`focus-visible:opacity-100` no botão de remover.** Ele só aparecia no hover
  do mouse: quem chegava nele pelo teclado recebia o foco num controle
  invisível.

---

## 4. A contagem do que resta à mão

Contar, não julgar:

- **0** classes de paleta crua do Tailwind (eram 32).
- **0** `<svg>` soltos (eram 13).
- **0** hexadecimais cravados.
- **0** cores cheias de significado como cor de texto (eram 5).
- **0** `text-white` (eram 2). As duas ocorrências que restam no arquivo estão
  **dentro de comentário**, documentando o par que saiu — a varredura de pares
  sabe quando está em comentário, e confirma zero.
- **2** `<button>` à mão, não pelo primitivo `Button`: as abas de filtro e o
  remover. As abas são um grupo de alternância com fundo e altura próprios, e o
  remover é um botão de ícone de 28px sem fundo em repouso; passá-los pelo
  `Button` mudaria desenho em dois lugares, o que é decisão de desenho e não
  troca de cor. Os dois têm nome acessível e os dois são alcançáveis pelo
  teclado.
- **1** `<div role="button">` — a linha inteira da notificação. Ele tem
  `tabIndex={0}` e trata Enter e Espaço, então a ação é alcançável; o problema é
  outro e está abaixo.
- **1** aninhamento interativo inválido: o `<button>` de remover vive **dentro**
  do `<div role="button">`. Pré-existente. Contado, não consertado.
- **1** contagem que não fecha: `handleDelete` desconta de `total` e **não**
  desconta de `unread`. Apagar uma notificação por ler deixa o cabeçalho
  dizendo um número a mais e o botão "Marcar todas como lidas" na tela sem ter o
  que marcar, até a página recarregar. Defeito de produto pré-existente.
- **1** relógio que não anda: `timeAgo` é calculado no desenho e nunca mais.
  Uma aba aberta há duas horas segue dizendo "agora". Pré-existente.
- **1** exclusão sem confirmação, e sem desfazer.

---

## 5. O que não foi feito, e por quê

- **Não criei `lib/notificacao.ts`.** `src/lib/**` está fora do escopo do
  briefing, e a tabela tem um consumidor só (seção 2).
- **Não acrescentei ícone nenhum ao pacote.** Não foi preciso: os 13 `<svg>`
  couberam em 10 nomes que já existiam, 9 por traçado e 2 por significado (o
  "certo" sem círculo e o triângulo de aviso) — exatamente os dois casos que a
  E21 previu.
- **Não desfiz o aninhamento `<button>` dentro de `role="button"`.** Consertar
  isso é redesenhar a linha (a superfície clicável vira um `<a>`/`<button>` que
  não contém o remover, ou o remover sai da linha), o que é decisão de desenho
  e mudança estrutural, não troca de cor.
- **Não corrigi a contagem de não lidas ao excluir**, nem o relógio parado, nem
  a exclusão sem confirmação. Os três são defeitos de produto e não se
  consertam aqui.
- **Não dei anel de foco às abas nem ao remover** — desvio F1, com prazo no
  Checkpoint 4, e vale para as 33 telas de uma vez.
- **Nenhuma captura de tela.** A verificação foi por leitura, `tsc`, `eslint`,
  os 16 casos de teste com as 19 mutações, a varredura de contraste e a
  contagem de cores cheias — não houve sessão de navegador nesta passagem.
- **O agrupamento dos dez tipos em seis variantes não foi decidido por mim como
  fato consumado**: fiz a escolha menos surpreendente para que a tela fechasse
  em zero paleta crua e zero cor cheia, mas ela está relatada ao operador como
  decisão de desenho. Reverter é trocar palavras na tabela `TIPO`.

---

## 6. Números

| medida | antes | depois |
|---|---:|---:|
| linhas do arquivo | 332 | 425 |
| classes de paleta crua do Tailwind | 32 | **0** |
| `<svg>` soltos | 13 | **0** |
| cor cheia semântica como cor de texto | 5 | **0** |
| `text-white` (fora de comentário) | 2 | **0** |
| hexadecimais cravados | 0 | 0 |
| linhas da `varredura-contraste.mjs` para esta tela | **2** (1 lugar) | **0** |
| entradas em `PARES_CONHECIDOS` | 1 (`bg-primary` repouso) | 0 |
| entradas em `CHEIAS_CONHECIDAS` | 5 | 0 |
| tabelas locais para o mesmo dado | 2 | 1 |
| primitivos reinventados (selo) | 1 | 0 |
| `<button>` à mão | 2 | 2 |
| estados ditos só pela cor | 2 (aba ativa, linha não lida) | 0 |
| testes em `NotificationsPage.test.tsx` | — (não existia) | **16**, todos passando |
| mutações aplicadas e mortas | — | **19 de 19** |

A entrada da catraca era, em detalhe:

```text
3,83:1  claro   linha 226   bg-primary + text-white (aba ativa)
3,83:1  escuro  linha 226   idem
```

E as cinco cores cheias eram `text-info` (linha 47), `text-warning` (79 e 103),
`text-danger` (87) e `hover:text-danger` (314) — as quatro últimas dentro do
`TYPE_META`, que é a razão de a tela liderar essa contagem.

### As 19 mutações

Todas mutam **o elemento, a condição ou o valor** — nunca a classe, e nunca o
nome de um símbolo. O ambiente de teste não aplica CSS, então classe trocada não
move nada do que os casos medem; e renomear um símbolo renomeia o consumidor
junto, o que faz o mutante sobreviver por um motivo que não tem relação com o
que o caso mede.

| # | mutação | o que ela quebra |
|---|---|---|
| M1 | `sla_breached.variante` `danger` → `muted` | o agrupamento |
| M2 | `ticket_closed.icone` `check` → `close` | a unificação da E21 |
| M3 | `ticket_resolved.rotulo` → `"xxx"` | o rótulo escrito |
| M4 | a marca `sr-only` "Não lida." some | o estado na árvore |
| M5 | a condição da marca inverte (`!n.read` → `n.read`) | a marca na linha certa |
| M6 | `aria-pressed={ativa}` → `{!ativa}` | a aba anunciada |
| M7 | o `stopPropagation` do remover some | excluir passa a navegar |
| M8 | plural sempre no plural | "1 não lida" |
| M9 | `total > PAGE_SIZE` → `> 1000` | a paginação |
| M10 | as duas frases do estado vazio trocam de lugar | qual vazio é |
| M11 | o `.catch` da carga some | a falha de rede vira lista vazia |
| M12 | `?.rotulo ?? t` → `?? "Notificação"` | o recuo para o valor cru |
| M13 | `await markRead(...)` some | o clique não marca |
| M14 | o `setItems` do clique some | a linha não repinta |
| M15 | o `setItems` do remover some | a linha não sai |
| M16 | `unread > 0` → `>= 0` no botão | "Marcar todas" com tudo lido |
| M17 | `unread_only: unreadOnlyFilter` → `false` | o filtro não chega ao serviço |
| M18 | o selo perde o rótulo (`{""}`) | o tipo dito por escrito |
| M19 | o `setItems` do "marcar todas" some | as marcas não somem |

**19 de 19 morreram.** Duas delas existem por causa de um ponto cego achado
enquanto o roteiro era escrito, e vale registrar os dois:

- **M5** foi desenhada de propósito contra o primeiro formato do caso da marca,
  que só contava (`toHaveLength(1)`). Inverter a condição continua produzindo
  **uma** marca — na linha errada. O caso passou a dizer em qual linha ela está.
- **M14** não era morta por nenhum caso da primeira rodada: os casos do clique
  afirmavam que `markRead` foi chamado e que a navegação aconteceu, e nenhum
  afirmava que a **tela** mudou. Um clique que avisa o servidor e não mexe em
  nada deixaria a pessoa vendo a notificação em negrito até recarregar. O caso
  ganhou a afirmação que faltava.

`npx tsc --noEmit -p tsconfig.app.json`, `npx eslint`, `node
scripts/varredura-contraste.mjs` e a contagem de cores cheias não relatam nada
para `NotificationsPage.tsx` nem para o teste novo.
