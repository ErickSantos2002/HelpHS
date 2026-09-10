# §29 — `pages/kb/KBArticlePage.tsx`

A maior concentração de `<svg>` solto da Fase 16: **11 desenhos em 14 lugares**,
numa tabela local chamada `IC` mais um chevron escrito no meio do JSX. Fora
isso, **três** mapas locais, 47 classes de paleta crua e dois pares de contraste
na catraca.

447 linhas antes, 665 depois. O arquivo cresceu por dois motivos, e nenhum é
código: a tabela de ícones virou chamada de primitivo (menos linhas) e o
**porquê** de três achados que ninguém mais vai reencontrar sozinho ficou
escrito (mais linhas).

---

## O que a tela tinha

| o que | quantos |
|---|---:|
| classes da paleta crua (todas `slate-*`) | **47** |
| `<svg>` solto | **11** desenhos, em **14** lugares |
| tabela local de ícones (`IC`) | **1**, com 10 entradas |
| mapas locais | **3** (`ROLE_LABEL`, `ROLE_COLOR`, `CATEGORY_LABEL`) |
| par `bg-primary` + `text-white` (3,83:1) | **1** lugar |
| par `bg-surface-elevated` + `text-slate-600` (2,34:1 claro / 1,79:1 escuro) | **1** lugar |
| cor cheia semântica como cor de TEXTO | **1** (`hover:text-danger`) |
| `text-white` | **1** |
| hexadecimal cravado | **0** |
| `useTheme()` | **0** — não havia gráfico nenhum |
| trilha vestida de botão | **1** |
| controle sem nome acessível | **2** (o botão de enviar e o campo de comentário) |

E três achados que nenhuma ferramenta desta migração pega, os três descritos
abaixo: **os polegares do pacote estão com os nomes trocados**, **o corpo do
artigo nunca teve estilo nenhum** e **o mapa de papel desta tela era o único das
seis cópias que divergia no texto**.

---

## O que passou a usar

| módulo / primitivo | onde | quantos |
|---|---|---:|
| `Icon` (E20/E21) | os 11 desenhos | **14** chamadas |
| `Card` | os dois cartões da coluna principal e os quatro da lateral | **6** |
| `Badge` | papel do autor, produtos, tags | **3** |
| `Button` | enviar comentário, "Editar artigo" | **2** |
| `Avatar` | a inicial do autor do comentário | **1** |
| `Link` | a trilha e o "Voltar à Base de Conhecimento" | **2** |
| `lib/categoria.ts` | `rotuloDeCategoria` | 1 |
| `lib/papel.ts` | `rotuloDePapel` + `varianteDePapel` | 1 |

### Os 11 `<svg>`, e como cada um casou

Os 11 eram `viewBox="0 0 24 24"` com `fill="none"` e `stroke="currentColor"` —
a mesma família do `Icon`, **conferido antes de trocar**. Nenhum era de escala
20×20 nem de preenchimento, e por isso nenhum ficou para trás.

| desenho | virou | como casou |
|---|---|---|
| seta para a esquerda | `arrowLeft` | traçado idêntico, caractere a caractere |
| lápis sobre folha | `edit` | traçado idêntico |
| olho | `eye` | traçado idêntico, os dois `d` (pupila + contorno) |
| avião de papel | `send` | traçado idêntico |
| usuário | `user` | traçado idêntico |
| calendário | `calendar` | traçado idêntico |
| balão de conversa | `chat` | por SIGNIFICADO: o traçado do pacote tem `a9.86 9.86` onde este tinha `a9.863 9.863` |
| etiqueta | `tag` | por SIGNIFICADO: desenho diferente, mesma etiqueta |
| chevron `M19 9l-7 7-7-7` | `chevronDown` | por SIGNIFICADO: o do pacote é `M6 9l6 6 6-6` |
| polegar para cima | `thumbsDown` (!) | por TRAÇADO — ver abaixo |
| polegar para baixo | `thumbsUp` (!) | por TRAÇADO — ver abaixo |

Nenhum ícone novo foi preciso.

### ⚠️ A E21 subiu os dois polegares com os nomes TROCADOS

O traçado guardado no pacote sob o nome **`thumbsUp`** é o polegar para **baixo**
(`M10 14H5.236…`, punho no alto à direita, dedão descendo até y=21), e o
guardado sob **`thumbsDown`** é o polegar para **cima** (`M14 10h4.764…`, punho
embaixo à esquerda, dedão subindo até y=3). São os traçados do Heroicons v1
`thumb-up`/`thumb-down` com os nomes invertidos, e a inversão é do pacote: esta
tela e a `KBListPage` sempre desenharam o de cima ao lado do "Sim" e da contagem
de "útil".

A regra do briefing é casar **pelo traçado, não pelo nome**, e é o que está
feito: o botão "Sim" pede `thumbsDown` e o "Não" pede `thumbsUp`. Fica absurdo
de ler e **certo de ver**. Duas constantes com o nome do que o desenho é
(`TRACO_POLEGAR_PARA_CIMA`, `TRACO_POLEGAR_PARA_BAIXO`) seguram a leitura no
lugar das quatro chamadas.

**Isso não se conserta aqui**: os nomes moram em `components/ui/Icon.tsx`, e
trocá-los é emenda. Enquanto não for, o caso de teste
*"o polegar do «Sim» aponta para CIMA"* reprova qualquer conserto ingênuo pelo
nome — que é exatamente o que se quer dele, porque `ICON_PATHS` é mapa de texto,
todo texto cabe, e **nem `tsc`, nem ESLint, nem teste de componente acusam** um
polegar invertido. Relatado ao operador.

### O degrau de ação, que é o motivo da tela estar na catraca

O botão de enviar comentário escrevia `bg-primary` com `text-white`: **3,83:1**,
nos dois temas, porque o degrau 500 é absoluto e não inverte. Virou `Button`,
que usa o par `--action` / `--text-on-primary` da E2 — branco no claro, navy no
escuro.

### A segunda linha da varredura

O círculo do estado "nenhum comentário ainda" era `bg-surface-elevated` com
`text-slate-600` no **mesmo elemento**: 2,34:1 no claro e 1,79:1 no escuro.
Virou `text-conteudo-muted`, que é o degrau que a **E5** levou a `slate-600` no
claro justamente para dar 6,92:1 sobre a superfície elevada. **Não** virou
`text-conteudo-faint`: `faint` sobre `elevated` é o par de 2,34:1 que a regra 4
do briefing nomeia.

### As duas cores de feedback

Os botões de voto e o bloco de contagem da lateral escreviam
`bg-success/10` com `text-success-700 dark:text-success-400` — a rampa a 10% com
o degrau de texto invertido à mão. Passaram para `bg-tint-success` com
`text-on-tint-success` (e o par de `danger`): são os mesmos valores que o
`Badge` usa desde a **E8**, a tinta já carrega os 15% no token (regra (a) do
D8-a, sem modificador de opacidade) e o par de texto inverte sozinho por tema.

O `hover:text-danger` do "Excluir" — a única cor cheia semântica como texto da
tela — virou `hover:text-on-tint-danger`.

### O papel, que era a sexta cópia

`ROLE_LABEL` e `ROLE_COLOR` saíram para `lib/papel.ts`, que nasceu enquanto esta
tela era migrada. **Muda texto na tela**: onde se lia "Admin" passa a se ler
"Administrador" — e a divergência era **desta** cópia, não das outras cinco
(`ProfilePage`, `Topbar` e três vezes dentro do `UsersPage`, todas por extenso).
Não é decisão nova: é a correção que o módulo existe para fazer.

O papel também deixou de ser texto colorido e virou `Badge` com a variante que o
módulo devolve — que é o vocabulário em que o `varianteDePapel` fala. Mudança
visível, registrada abaixo.

### ⚠️ O corpo do artigo nunca teve estilo nenhum

As 14 classes `prose-*` do `MarkdownContent` **não geram CSS neste projeto**: o
`@tailwindcss/typography` não está no `package.json`, `plugins` do
`tailwind.config.js` está vazio, e não existe regra `.prose` no `index.css` nem
no pacote. O corpo do artigo é injetado por `dangerouslySetInnerHTML` e
renderiza com o padrão do navegador — título no tamanho do agente, link azul
sublinhado, bloco de código sem fundo.

As classes ficaram, **traduzidas para os tokens**: são a única declaração
escrita de como o corpo deveria parecer, e trocar `slate-*` por token ali é o
que fecha a tela em zero paleta crua. Instalar o plugin mexe em `package.json` e
em `tailwind.config.js`, os dois fora do escopo. Relatado — e com dois avisos
para quem instalar, que estão no comentário do arquivo: `prose-invert` está
cravado **sem** `dark:`, o que inverteria o corpo no tema claro, e o bloco tem
altura limitada a 15rem com rolagem.

---

## O que resta à mão — a contagem

**Contar, não julgar**: um número maior que zero significa que alguém tem de
olhar, não que há trabalho pendente.

| o que | quantos | observação |
|---|---:|---|
| `<svg>` solto | **0** | eram 11; as 2 ocorrências de `<svg` no arquivo são texto de comentário |
| classe de paleta crua | **0** | eram 47 |
| `text-white` | **0** | era 1 |
| cor cheia semântica como texto | **0** | era 1; as 2 ocorrências restantes são comentário citando o que saiu |
| linhas da varredura de contraste | **0** | eram 4 (2 pares × 2 temas) |
| hexadecimal em código | **0** | não havia |
| `theme` lido em JavaScript | **0** | não havia |
| mapas locais | **0** | eram 3 |
| controles à mão | **7** | 6 `<button>` + 1 `<textarea>`, ver abaixo |
| cascas de cartão à mão | **1** | o cabeçalho, ver abaixo |

**Os sete controles à mão, e por que cada um ficou:**

1. **os dois botões de voto ("Sim"/"Não")** — não há variante de `Button` para
   um alternador de contorno que ganha tinta ao ser escolhido. O `Button` traria
   fundo cheio nas cinco variantes, e o que a tela precisa é do contorno. O que
   a migração trocou foi a cor (tinta e par da tinta) e o estado anunciado
   (`aria-pressed`);
2. **o `<textarea>` do comentário** — o primitivo `Textarea` embrulha o campo
   num `div` de coluna e crava `resize-y min-h-[80px]`. O `cn()` deste projeto é
   concatenação simples, **não** `tailwind-merge`: mandar `resize-none` por
   `className` deixaria as duas classes no atributo e quem vencesse sairia da
   ordem do CSS gerado. Este campo é de **uma** linha que cresce até 6rem dentro
   de uma linha de flex, e a geometria não sobreviveria à troca. O que mudou foi
   a borda (`--border-control`, E7) e o nome acessível;
3. **"Cancelar", "Responder", "Ver N respostas", "Excluir"** — quatro ações de
   **texto**, na linha do conteúdo. `Button variant="ghost"` traz altura e
   preenchimento de botão e mudaria o leiaute de cada comentário. O que mudou
   foi a cor e, nos dois que abrem e fecham, o `aria-expanded`.

**A casca à mão.** O cabeçalho é `rounded-2xl` e o `Card` é `rounded-xl`. Como
o `cn()` não resolve conflito, passar `rounded-2xl` por `className` deixaria as
duas classes no atributo. Ficou desenhado à mão com os mesmos tokens do `Card`
(`border-borda/40 bg-surface`) — raio diferente é decisão de desenho, e não se
decide aqui.

---

## O que mudou na TELA, e que alguém vai ver

| onde | antes | agora |
|---|---|---|
| papel do autor do comentário | "**Admin**", em texto colorido | "**Administrador**", em `Badge` |
| inicial do autor | 1 letra, círculo neutro `bg-surface-elevated` | `Avatar` — até 2 iniciais, par de cor derivado do nome |
| trilha | um botão só, com "Base de Conhecimento / <título>" dentro | link "Base de Conhecimento" + separador + título como texto |
| "Editar artigo" | botão que chamava `navigate()` | link (`Button to=`), com aparência de botão secundário |
| "Voltar à Base de Conhecimento" (artigo não encontrado) | botão que chamava `navigate()` | link |
| produtos e tags | pílulas desenhadas à mão | `Badge` `primary` e `secondary` |
| borda do campo de comentário | `borda/60` (≈1,2:1) | `--border-control` (E7, ≥3:1) |
| voto dado | só a tinta dizia qual foi | `aria-pressed` diz, e "Obrigado pelo feedback!" é `role="status"` |
| campo de comentário e botão de enviar | sem nome acessível | "Comentário" / "Enviar comentário" (e "Resposta" / "Enviar resposta") |

Nenhuma dessas mexe em número que alguém lê. A **primeira** mexe em texto, e é a
correção que o `lib/papel.ts` existe para fazer.

---

## O que NÃO foi feito, e por quê

- **Consertar os nomes trocados de `thumbsUp`/`thumbsDown`.** É emenda a
  `components/ui/Icon.tsx`, fora do escopo. Enquanto não for feito, esta tela e
  a `KBListPage` chamam pelo nome invertido — de propósito, e com o teste
  segurando. Relatado.
- **Instalar o `@tailwindcss/typography`.** `package.json` e
  `tailwind.config.js`, os dois fora do escopo. Relatado.
- **Dar estilo real ao corpo do artigo** (com variantes de arbitrário, que
  funcionariam sem o plugin). O corpo hoje não tem estilo nenhum; escolher que
  aparência ele passa a ter é decisão de desenho. Relatado.
- **Tratar o erro do voto e o da exclusão de comentário.** `handleFeedback` e
  `handleDeleteComment` chamam a rede **sem `try`**: se a chamada falhar, a
  promessa rejeita sem tratamento, o contador não sobe e o usuário não vê aviso
  nenhum — enquanto `handleAddComment` e `handleReply`, ao lado, usam
  `toastApiError`. É defeito de produto e muda o que a tela faz. Relatado.
- **O `Card` no cabeçalho.** Raio diferente, e o `cn()` não resolve conflito de
  classe. Ver acima.
- **O desvio F1 (foco em `ring` e não em `outline`).** O campo de comentário
  continua com o anel do Tailwind. Alinhar ao `outline` interno do pacote é
  mudança em `components/ui/`, fora do escopo.
- **A `KBListPage`.** Ela tem a mesma tabela `IC`, o mesmo `text-slate-600`
  sobre `bg-surface-elevated` (linha 188, as mesmas 2 linhas na varredura) e o
  mesmo polegar. Não é a minha tela.

---

## Testes

`src/test/pages/KBArticlePage.test.tsx`, **11 casos**, todos validados por
mutação — o arquivo não existia. Nenhum caso olha classe: o happy-dom não aplica
CSS, e um mutante de classe sobrevive por um motivo que não tem nada a ver com o
que o caso mede.

Cinco dos onze são sobre o **voto de utilidade**, que é o comportamento próprio
desta tela.

**Onze mutações, todas no ELEMENTO ou no comportamento**, e o que cada uma
matou:

| mutação | caso que morreu |
|---|---|
| o botão "Sim" passa a registrar voto negativo | votar «Sim» manda `helpful: true` e soma no contador |
| o botão "Não" passa a registrar voto positivo | votar «Não» manda `helpful: false` |
| o "Sim" continua clicável depois do voto | o voto é único |
| o voto positivo deixa de ser anunciado (`aria-pressed={false}`) | o voto dado fica anunciado, e não só pintado |
| o conserto ingênuo pelo NOME do ícone (`thumbsDown` → `thumbsUp`) | o polegar do «Sim» aponta para CIMA |
| a trilha volta a ser um controle só, com o título dentro | a trilha é um link para a base |
| "Editar artigo" volta a ser botão | «Editar artigo» é um LINK |
| `rotuloDePapel(...)` volta a ser `"Admin"` | o papel do autor sai do módulo |
| a categoria vira o valor cru `"hardware"` | a categoria sai do módulo |
| some o `aria-label` do campo | o campo e o botão de enviar têm nome próprio |
| o convite do estado vazio nunca é desenhado | sem comentário nenhum, a tela convida |

O roteiro de mutação **confere que algum caso rodou** antes de declarar
"morreu": um filtro `-t` que não casa nome nenhum faz o `vitest` sair 0 com zero
testes, e sem essa checagem "morreu" e "nem rodou" seriam indistinguíveis — o
inverso exato da armadilha do briefing, e igual de barato de escrever.
Restauração em `finally`, cópia em memória, **nenhum `git`**.

---

## Verificação

| conferência | resultado |
|---|---|
| `npx vitest run src/test/pages/KBArticlePage.test.tsx` | 11 passaram |
| mutação | 11 mortas de 11, nenhuma sobrevivente |
| `npx tsc --noEmit -p tsconfig.app.json` | sem erro |
| `npx eslint` nos dois arquivos | limpo |
| `varredura-contraste.mjs` \| `grep KBArticlePage` | **nenhuma linha** (eram 4) |
| classes de paleta crua em código | **0** (eram 47) |
| `<svg>` solto | **0** (eram 11) |
| `text-white` | **0** (era 1) |
| cor cheia semântica como texto | **0** (era 1) |
