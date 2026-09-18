# §29 — `components/chat/ChatPanel.tsx`

Não é uma página: é o painel de conversa que vive dentro do `TicketDetailPage`.
Entra na Fase 16 pelo mesmo motivo que as telas — **45** classes de paleta crua,
**6** `<svg>` soltos, **2** mapas locais e **2** pares na catraca —, e traz um
problema que nenhuma tela tinha: **três autores diferentes distinguidos por
cor**. Migrar as tintas sem olhar isso teria sido trocar a única coisa que a
1.4.1 já não aceitava sozinha.

667 linhas antes, 626 depois. O que encolheu foram os seis `<svg>` escritos por
extenso, os três anéis de carregando desenhados à mão e dois mapas locais; o que
cresceu foi o **porquê** de três decisões que ninguém reencontra sozinho.

---

## O que o painel tinha

| o que | quantos |
|---|---:|
| classes da paleta crua | **45** — 34 `slate-*`, 10 `purple-*`, 1 `yellow-500` |
| `<svg>` solto | **6** |
| mapas locais | **2** (`ROLE_LABEL`, `ROLE_COLOR`) |
| par `bg-primary` + `text-white` (3,83:1) | **1** lugar |
| par `bg-surface-elevated` + `text-slate-500` (4,34:1 claro / 2,85:1 escuro) | **1** lugar |
| cor cheia semântica como cor de TEXTO | **3** (`text-info`, `text-primary`, `text-danger`) |
| `text-white` | **1** |
| anel de carregando desenhado à mão | **3** |
| controle sem nome acessível | **1** (o botão de enviar) |
| hexadecimal cravado | **0** |
| `useTheme()` | **0** — não há gráfico nenhum aqui |
| linhas da varredura de contraste | **4** (2 pares × 2 temas) |

O `purple-*` merece uma linha própria: **não existe `--color-purple-*` no
pacote**. Eram dez classes de uma paleta que o design system nunca teve — a
mesma constatação que o `Avatar.tsx` já registra sobre os pares antigos de
`purple` e `pink`.

---

## O que passou a usar

| módulo / primitivo | onde | quantos |
|---|---|---:|
| `Icon` (E20/E21) | os seis desenhos | **6** |
| `Button` | resumir, regenerar, fechar, sugerir, melhorar, enviar | **6** |
| `Avatar` | a inicial de quem escreveu | **1** |
| `lib/papel.ts` | `rotuloDePapel` + `varianteDePapel` | 1 |
| `lib/status.ts` | `TOM_STATUS` (tom do papel e ponto do socket) | 1 |

### Os 6 `<svg>`, e como cada um casou

Os seis eram `viewBox="0 0 24 24"` com `fill="none"` e `stroke="currentColor"` —
a **mesma família** do `Icon`, conferido antes de trocar. Nenhum era 20×20 nem
de preenchimento, e por isso nenhum ficou para trás. Os seis passam
`strokeWidth={2}`, que era o traço que eles tinham; o padrão do `Icon` é 1,75.

| desenho | onde | virou | como casou |
|---|---|---|---|
| folha com linhas | "Resumir" | `document` | traçado idêntico, caractere a caractere |
| setas em círculo | "Regenerar resumo" | `refresh` | idêntico |
| xis | "Fechar resumo" | `close` | idêntico |
| lâmpada | "Sugerir resposta (IA)" | `lightbulb` | idêntico — é um dos 16 que a **E21** subiu |
| lápis sobre folha | "Melhorar texto (IA)" | `edit` | idêntico |
| avião de papel | enviar | `send` | idêntico — também da **E21** |

Nenhum ícone novo foi preciso. Os dois da E21 (`send`, `lightbulb`) casaram
caractere a caractere: eram exatamente os traçados que o inventário das 33 telas
levantou daqui.

### O degrau de ação, que é o motivo do painel estar na catraca

O botão de enviar escrevia `bg-primary` com `text-white`: **3,83:1**, nos dois
temas, porque o degrau 500 é absoluto e não inverte. Virou `Button` primário,
que usa o par `--action` / `--text-on-primary` da E2 — branco no claro, navy no
escuro.

### A segunda linha da varredura

A mensagem do sistema — aquela pílula central e itálica — era
`bg-surface-elevated` com `text-slate-500` no **mesmo elemento**: 4,34:1 no
claro e 2,85:1 no escuro. Virou `text-conteudo-muted`, que a **E5** levou a
`slate-600` no claro justamente para dar ~6,9:1 sobre a superfície elevada.
**Não** virou `text-conteudo-faint`: `faint` sobre `elevated` é o par de 2,34:1
que a regra 4 do briefing nomeia.

### As três bolhas, e a 1.4.1

O painel pinta três autores: quem escreve, quem responde e a IA. Antes, as três
se separavam por **cor e lado** — e a bolha da IA por um roxo que não é do
sistema.

| bolha | antes | agora |
|---|---|---|
| do sistema | `bg-surface-elevated` + `text-slate-500` | `bg-surface-elevated` + `text-conteudo-muted` |
| da IA | `bg-purple-950` / `border-purple-800` / `text-purple-400` | `bg-tint-info` + `border-info/30` + `text-on-tint-info` |
| própria | `bg-primary/20` | `bg-tint-primary` (a tinta já carrega os 15%; regra (a) do D8-a) |
| de outra pessoa | `bg-surface-elevated` | igual, com o texto no degrau `conteudo` |

A escolha da tinta de **info** para a IA está registrada abaixo como decisão de
desenho: não há tom de "isto é IA" no pacote, e as duas bolhas da esquerda — a
da IA e a de outra pessoa — são as que precisam se separar por preenchimento,
porque estão do mesmo lado. A própria fica à direita.

**O que sustenta a 1.4.1 aqui é o texto, não a cor**: a bolha da IA diz
"Assistente IA" acima do conteúdo, a de outra pessoa diz o nome e o papel, e o
estado da conexão está escrito ("ao vivo", "conectando…", "desconectado") ao
lado do ponto colorido. Quatro casos de teste prendem exatamente isso.

⚠️ **A bolha própria continua sem autor escrito.** Ela se distingue por ficar à
direita e pintar a tinta primária — cor e posição, que é o que a 1.4.1 não
aceita sozinho. Não foi consertado: escrever "Você", e decidir se visível ou em
`sr-only`, muda o que a árvore de acessibilidade fala. Relatado.

### O papel, que era a sétima e a oitava cópias

`ROLE_LABEL` e `ROLE_COLOR` saíram para `lib/papel.ts`. **Muda texto na tela**:
onde se lia "Admin" passa a se ler "Administrador" — e a divergência era
**desta** cópia, como já tinha sido no `KBArticlePage`.

O `ROLE_COLOR` era pior que duplicação: as três cores eram **cor cheia da rampa
como texto**. `text-info` sobre a superfície branca dá **3,68:1** e `text-primary`
dá 3,66:1 — os dois abaixo do piso de 4,5:1 para texto. Agora o tom vem de
`TOM_STATUS[varianteDePapel(papel)].texto`, que é o par da tinta
(`on-tint-primary`, `on-tint-info`, `on-tint-neutral`): ≥6:1 nos dois temas, e
inverte sozinho.

### O ponto do socket

`bg-yellow-500` não é token nenhum — amarelo não existe no pacote. As três
cores passaram a sair do `TOM_STATUS`, com uma tabela local que mapeia
**estado de socket → variante** e deixa as classes no módulo:

| estado | antes | agora |
|---|---|---|
| conectando | `bg-yellow-500` | `warning` → `bg-fill-warning` |
| conectado | `bg-primary` | `primary` → `bg-primary` (é o mesmo; o `TOM_STATUS` já o escreve) |
| desconectado | `bg-slate-600` | `muted` → `bg-borda-control` |

A tabela é local **de propósito**: estado de WebSocket tem um consumidor só e não
é vocabulário compartilhado — é a mesma regra pela qual `lib/papel.ts` existe e
`lib/auditoria.ts` não. O que ela não faz é repetir classe: mapeia para a
variante, e o tom fica no módulo.

### A borda do campo, e o hover que saiu

O campo era `border-borda` com `hover:border-slate-500`. Virou
`border-borda-control` **sem hover** — pela razão que o próprio primitivo
`Textarea` registra: a **E7** levou a borda de repouso do controle a
`--border-control`, que é slate-500, exatamente onde o hover chegava. O campo
está sempre na força que antes dependia do ponteiro, e a 1.4.11 pede 3:1 para o
limite do componente, não 3:1 sob o mouse.

### Os três anéis de carregando

Eram `<span>` com `animate-spin` e borda desenhada à mão — inclusive o
`animate-spin` padrão do Tailwind, e não o `hs-spin` do pacote. Os três viraram
`loading` do `Button`, que já desabilita o controle junto.

---

## O que resta à mão — a contagem

**Contar, não julgar**: um número maior que zero significa que alguém tem de
olhar, não que há trabalho pendente.

| o que | quantos | observação |
|---|---:|---|
| `<svg>` solto | **0** | eram 6; a única ocorrência de `<svg` no arquivo é texto de comentário |
| classe de paleta crua | **0** | eram 45; as 3 ocorrências restantes são comentário citando o que saiu |
| `text-white` | **0** | era 1 |
| cor cheia semântica como texto | **0** | eram 3 |
| linhas da varredura de contraste | **0** | eram 4 |
| hexadecimal em código | **0** | não havia |
| `theme` lido em JavaScript | **0** | não havia |
| anel de carregando à mão | **0** | eram 3 |
| `<button>` à mão | **0** | eram 6 |
| mapas locais de vocabulário compartilhado | **0** | eram 2 |
| tabelas locais de conceito local | **2** | `VARIANTE_DO_SOCKET` e `TITULO_DO_SOCKET`, ver acima |
| controles à mão | **1** | o `<textarea>`, ver abaixo |
| marcas à mão | **1** | o círculo "AI", ver abaixo |

**O controle à mão.** O `<textarea>` do compositor não virou o primitivo
`Textarea` por três razões que se somam: o primitivo embrulha o campo num `div`
de coluna — e aqui o campo é filho direto de uma linha de flex, com `flex-1`,
ao lado do botão de enviar; ele crava `resize-y min-h-[80px]` e `rows={4}`,
enquanto este é de **uma** linha que cresce sozinha até 200px; e o `cn()` deste
projeto é **concatenação simples**, não `tailwind-merge`, então mandar
`resize-none` por `className` deixaria as duas classes no atributo e quem
vencesse sairia da ordem do CSS gerado, não da ordem em que foram escritas. O
que a migração trocou foi o vocabulário: `text-conteudo`,
`placeholder:text-conteudo-muted`, `border-borda-control`, `focus:ring-action`.

**A marca à mão.** O círculo com "AI" continua desenhado, e não é `Avatar`: o
primitivo deriva a cor do **nome** de quem fala, e a IA não é uma pessoa entre
outras — a marca dela é fixa. Além disso `Avatar name="AI"` renderiza "A", não
"AI". Ele passou a usar `bg-tint-info` / `text-on-tint-info` e o tamanho do
`Avatar size="sm"` (32px), para as duas colunas de avatar ficarem alinhadas.

---

## O que mudou na TELA, e que alguém vai ver

| onde | antes | agora |
|---|---|---|
| papel de quem escreveu | "**Admin**" | "**Administrador**" |
| cor do papel | cor cheia da rampa (3,66:1 e 3,68:1) | par da tinta, ≥6:1 |
| inicial de quem escreveu | 1 letra, círculo neutro de 28px | `Avatar` de 32px, até 2 iniciais, par de cor derivado do nome |
| bolha da IA | roxa | tinta de **info** |
| "Sugerir resposta (IA)" e "Melhorar texto (IA)" | contorno **roxo** e contorno cinza | os dois no degrau secundário — perderam a cor que os separava |
| botão de enviar | `bg-primary` + `text-white` (3,83:1) | `bg-action` + `text-on-primary` |
| botão de enviar | **sem nome acessível** | "Enviar mensagem" |
| borda do campo | `--border-color`, chegando a slate-500 só no hover | `--border-control` sempre (E7) |
| ponto de "conectando" | amarelo | `--fill-warning` |
| ponto de "desconectado" | `slate-600` | `--border-control` |
| horários e textos secundários | slate-500/600 — 2,84:1 no claro nos horários | `conteudo-muted`, ≥4,9:1 |
| botões pequenos | `px-2 py-1` / `px-2.5 py-1` | tamanho `sm` do `Button` (`px-3 py-1.5`) |

Nenhuma dessas mexe em número que alguém lê. A primeira mexe em **texto**, e é a
correção que o `lib/papel.ts` existe para fazer; a sétima mexe no que um leitor
de tela **anuncia**, e as duas estão relatadas.

---

## O que NÃO foi feito, e por quê

- **Escrever o autor na bolha própria.** É o item de 1.4.1 acima. Acrescentar
  "Você" — e decidir entre texto visível e `sr-only` — muda o que a árvore de
  acessibilidade fala e é decisão de desenho. Relatado.
- **Dar um tom próprio à IA.** Não existe `--color-purple-*` nem qualquer token
  de "assistente" no pacote. Criar um é emenda, e emenda não se faz de dentro de
  uma tela. O que está no ar é a tinta de `info`, e ela precisa de confirmação.
  Relatado.
- **Migrar o `QuickReplyPicker.tsx`.** É o menu de "/" que este painel abre, mora
  no mesmo diretório e tem **5** classes de paleta crua, um `bg-primary/10` e
  **3 linhas na varredura** (2,11:1 e 2,56:1 na dica de rodapé, 3,36:1 no título
  da lista). **Não é o meu arquivo** — o escopo é o `.tsx` que me foi dado.
  Relatado.
- **Usar o primitivo `Textarea`.** Ver acima: geometria, e o `cn()` não resolve
  conflito de classe.
- **O desvio F1 (foco em `ring` e não em `outline`).** O campo continua com o
  anel do Tailwind. Alinhar ao `outline` interno do pacote é mudança em
  `components/ui/`, fora do escopo.
- **Mexer no `useCallback` do `connect`.** A isenção do `exhaustive-deps` e os
  dois casos que a prendem são anteriores a esta fase e continuam intocados.

---

## Testes

`src/test/components/ChatPanel.test.tsx`. O arquivo **já existia**, com os dois
casos que prendem a isenção do `exhaustive-deps` — eles não foram tocados.
Foram acrescentados **11 casos** sobre o que o painel promete, e os 11 passaram
na primeira execução, então os 11 foram validados por mutação.

Nenhum caso olha classe: o happy-dom **não aplica CSS**, e um caso que
afirmasse `toHaveClass("bg-tint-info")` passaria com a classe presente e a bolha
invisível — e o mutante correspondente sobreviveria por um motivo que não tem
nada a ver com o que o caso mede.

**Onze mutações, todas no ELEMENTO ou no comportamento**, e o que cada uma matou:

| mutação | caso que morreu |
|---|---|
| `rotuloDePapel(...)` vira o valor cru do backend | o nome e o papel de quem escreveu ficam ESCRITOS |
| some o `<p>` "Assistente IA" | a bolha da IA diz quem falou, e não só de que cor é |
| a mensagem do sistema vira bolha de pessoa | a mensagem do sistema não ganha autor |
| o texto "ao vivo" some, sobrando só o ponto | o estado da conexão está em TEXTO |
| some o `aria-label` do botão de enviar | o botão de enviar tem nome acessível |
| enviar deixa de exigir texto (só espaço libera) | enviar só libera com o socket aberto E com texto |
| `isStaff` vira `true` | quem não é da equipe não vê nenhuma ação de IA |
| `isStaff` vira `false` | a equipe vê as três ações de IA |
| `locked` deixa de esconder o compositor | chamado encerrado tira o campo, e diz por quê |
| a falha ao carregar o histórico é engolida | histórico que não carrega vira aviso escrito |
| o resumo é gerado mas o painel não abre | o resumo aparece, e os dois controles têm nome |

Nenhuma delas é das três que **não** são mutações: nenhuma troca só classe,
nenhuma renomeia símbolo com o consumidor junto, e nenhuma usa `&&` — que
devolve o segundo operando e deixaria o original de pé.

O roteiro tem as duas defesas do briefing e mais três: **controle sem mutação**
antes da primeira (13 passaram — se não passasse, nada depois valeria); chamada
ao vitest por `process.execPath` + `vitest.mjs`, **nunca** por `npx.cmd`;
exigência de que cada alvo apareça **exatamente uma vez** no arquivo; exigência
de que o filtro `-t` case **algum** caso (filtro que não casa nada faz o vitest
sair 0 com zero testes, e "morreu" ficaria indistinguível de "nem rodou"); e
comparação do arquivo com o original no fim. Restauração em `finally`, cópia em
memória, **nenhum `git`**.

---

## Verificação

| conferência | resultado |
|---|---|
| `vitest run src/test/components/ChatPanel.test.tsx` | **13 passaram** (2 antigos + 11 novos) |
| mutação | **11 mortas de 11**, nenhuma sobrevivente, arquivo restaurado |
| `npx tsc --noEmit -p tsconfig.app.json` | sem erro nos meus arquivos |
| `npx eslint` nos dois arquivos | limpo |
| `varredura-contraste.mjs` \| `grep chat/ChatPanel` | **nenhuma linha** (eram 4) |
| classes de paleta crua em código | **0** (eram 45) |
| `<svg>` solto | **0** (eram 6) |
| `text-white` | **0** (era 1) |
| cor cheia semântica como texto | **0** (eram 3) |
| hexadecimal | **0** |

⚠️ Sobre o `tsc`: no momento da conferência, `src/pages/calendar/CalendarPage.tsx`
— arquivo de **outro agente**, na mesma árvore — estava com erro de sintaxe, e
são os únicos 8 erros que o compilador relata. `ChatPanel.tsx` e
`ChatPanel.test.tsx` não aparecem em nenhum deles, e o subconjunto
`components/ + lib/ + services/` compila com **zero** erros quando conferido em
isolado.
