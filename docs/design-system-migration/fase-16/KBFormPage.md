# §29 — `pages/kb/KBFormPage.tsx`

A tela irmã da `KBArticlePage`, e a **única de formulário** da dupla. O que ela
tinha de próprio não eram os `<svg>` — eram só quatro — mas **seis rótulos que
não pertenciam a campo nenhum**: dois `<select>` sem `id` sob `<label>` sem
`htmlFor`, o "Conteúdo", o "Tags" e um `<label>` posto sobre um **grupo** de
controles. É o mesmo defeito que a `ProfilePage` teve em dez lugares.

412 linhas antes, 613 depois. O arquivo cresceu por comentário, não por código:
o mapa de categoria, os dois `<select>` e o selo de estado sumiram, e no lugar
ficou escrito **por que** cada um saiu — inclusive os três achados que ninguém
reencontra sozinho, listados abaixo.

---

## O que a tela tinha

| o que | quantos |
|---|---:|
| classes da paleta crua (todas `slate-*`) | **46** |
| `<svg>` solto (tabela local `IC`) | **4** |
| hexadecimal cravado | **3** |
| par `bg-primary` + `text-white` (3,83:1, nos dois temas) | **1** lugar |
| par `bg-surface-elevated` + `text-slate-500` (4,34:1 claro / 2,85:1 escuro) | **1** lugar |
| cor cheia semântica como cor de TEXTO (`text-danger`) | **3** |
| `text-white` | **1** |
| mapas locais | **3** (`CATEGORIES`, `STATUS_OPTIONS`, `STATUS_CONFIG`) |
| `<label>` sem `htmlFor` | **4** (Categoria, Status, Conteúdo, Tags) |
| `<label>` posto sobre um GRUPO de controles | **1** (Produtos) |
| campo sem `id` | **2** (os dois `<select>`) |
| `<p>` de erro/ajuda solto, sem `aria-describedby` | **4** |
| alternador de dois estados sem estado anunciado | **2** (as abas Editar/Preview) |
| trilha vestida de botão | **1** |
| classe `prose-*` que não gera CSS nenhum | **23** |
| `useTheme()` | **0** — não há gráfico nesta tela |

---

## O que passou a usar

| módulo / primitivo | onde | quantos |
|---|---|---:|
| `Icon` (E20/E21) | os 4 desenhos da tabela `IC` + o visto do chip | **5** chamadas |
| `Select` | Categoria e Status | **2** |
| `Input` | Título e Tags | **2** |
| `Textarea` | o corpo do artigo | **1** |
| `Checkbox` | "Vale para todos os produtos" | **1** |
| `Badge` | selo de estado + as tags do resumo | **2** lugares |
| `Card` | as duas seções do formulário e os dois cartões da lateral | **4** |
| `Button` | Cancelar (como link) e Salvar | **2** |
| `Link` | os dois degraus da trilha | **2** |
| `lib/categoria.ts` | `CATEGORIAS` + `rotuloDeCategoria` | **1** |

### Os 4 `<svg>`, e como cada um casou

Os quatro eram `viewBox="0 0 24 24"` com `fill="none"` e `stroke="currentColor"`
— a mesma família do `Icon`, **conferido antes de trocar**. Nenhum era 20×20 nem
de preenchimento, e por isso nenhum ficou para trás.

| desenho | virou | como casou |
|---|---|---|
| seta para a esquerda | `arrowLeft` | traçado idêntico, caractere a caractere |
| lápis sobre folha | `edit` | traçado idêntico |
| olho | `eye` | traçado idêntico, os dois `d` (pupila + contorno) |
| "i" em círculo | `info` | por SIGNIFICADO: o círculo do pacote é `M12 2a10 10 0 100 20…`, este era `M21 12a9 9 0 11-18 0…` |

Nenhum ícone novo foi preciso.

**Um quinto desenho, que não era `<svg>`:** o visto do chip de produto era o
caractere `✓` num `<span>`. Virou `Icon name="check"` — o mesmo significado, e o
único "certo" que o pacote tem. **É o único lugar em que o desenho muda de
forma**: o `check` do pacote é um certo **dentro de um círculo**, e o glifo era
um certo simples. Registrado abaixo, na tabela do que alguém vai ver.

### Os três hexadecimais, e de que tipo eram

Os três eram o ponto colorido do selo de estado, cravado em
`style={{ backgroundColor: … }}`:

| era | é | e é |
|---|---|---|
| `#f59e0b` (amber-500) | `bg-fill-warning` | decisão de desenho |
| `#10b981` (emerald-500) | `bg-fill-success` | decisão de desenho |
| `#64748b` (slate-500) | `bg-borda-control` | decisão de desenho |

**Três de três eram decisão de desenho; nenhum era dado.** Nada aqui vem da
rede: são cores escolhidas para três estados fixos. Foram para a força de
**preenchimento** da E19 e não para o degrau 500 cheio, que reprova o piso de
3:1 da WCAG 1.4.11 no tema claro (warning 1,96; success 2,54) e não inverte por
tema. O neutro do "Arquivado" caiu em `--border-control`, que **é** slate-500
desde a E7: mesmo valor, agora com nome.

As classes vão **por extenso** no mapa. `"bg-fill-" + tom` sumiria da varredura
do Tailwind, a regra não nasceria, o ponto ficaria sem cor — e sem erro nem
aviso.

### O degrau de ação, que é o motivo da tela estar na catraca

O chip de produto marcado escrevia `border-primary bg-primary text-white`:
**3,83:1** nos dois temas, porque o degrau 500 é absoluto e não inverte. Passou
para o degrau de **ação** com o par dele — `bg-action` + `text-on-primary`, que
é branco no claro e navy no escuro. Não marcado, a borda saiu de `borda/60` (um
separador de superfície, ≈1,2:1) para `--border-control` da E7, que é o contorno
de **controle** e cumpre os 3:1.

### A segunda linha da varredura

O selo "Arquivado" era `bg-surface-elevated` com `text-slate-500` no **mesmo
elemento**: 4,34:1 no claro e **2,85:1** no escuro. O selo inteiro virou `Badge`
com a variante `secondary` — `bg-tint-neutral` com `text-on-tint-neutral`, o par
medido da E8. Os outros dois estados escreviam `bg-success/10` com
`text-success-700 dark:text-success-400`: a rampa a 10% com a inversão de tema
escrita à mão, exatamente o que o `Badge` faz sozinho desde a E8.

### As três cores cheias semânticas como texto

Os dois asteriscos de campo obrigatório e a mensagem de erro dos produtos eram
`text-danger`. Viraram `text-on-tint-danger` — o mesmo degrau que o `Input` e o
`Textarea` do pacote usam para a linha de erro.

### O marcador das dicas

Os quatro `•` do cartão de dicas eram `text-primary`, o degrau de **marca**, que
sobre a superfície dá 3,66:1 e reprova AA para texto. Foram para
`--text-link`, o degrau legível da mesma família (5,05:1 no claro, 6,47:1 no
escuro), e ganharam `aria-hidden`: o marcador é desenho, o texto do item já diz
tudo.

### ⚠️ A pré-visualização de Markdown não pinta nada — e mente por isso

As **23** classes `prose-*` do bloco de pré-visualização **não geram CSS neste
projeto**. O `@tailwindcss/typography` não está no `package.json`, `plugins` do
`tailwind.config.js` está vazio, e não existe regra `.prose` em `index.css` nem
no pacote. É o mesmo achado da `KBArticlePage`, e aqui ele é pior: esta tela
existe para **mostrar ao autor como o artigo vai ficar**, e mostra uma aparência
que não é a de lugar nenhum.

As classes ficaram, **traduzidas para os mesmos tokens que a tela irmã usa** —
linha a linha, para que as duas não divirjam. É o que fecha a tela em zero
paleta crua, e é a única declaração escrita de como o corpo deveria parecer.
Instalar o plugin mexe em `package.json` e em `tailwind.config.js`, os dois fora
do escopo. Relatado.

O aviso da tela irmã vale aqui: `prose-invert` está cravado **sem** `dark:`, o
que inverteria o corpo no tema CLARO.

### Os rótulos, que é o que uma tela de formulário promete

| campo | antes | agora |
|---|---|---|
| Categoria | `<label>` sem `htmlFor`, `<select>` sem `id` | `Select` com `label` — o primitivo amarra os dois |
| Status | idem | `Select` com `label` |
| Conteúdo | `<label>` sem `htmlFor` sobre um `Textarea` que gerava o próprio `id` | `id` nasce no `useId` da tela e vai para os dois |
| Tags | `<label>` sem `htmlFor` | `htmlFor` para o `id` que o `Input` recebe |
| Produtos | `<label>` sobre um GRUPO de controles | `<fieldset>` + `<legend>` — vira `role="group"` com nome |
| Título | já vinha com `label` | inalterado |

Os quatro `<p>` de ajuda e de erro eram irmãos dos campos: juntos na tela, sem
relação nenhuma na árvore de acessibilidade. Três viraram `hint`/`error` dos
primitivos, que os ligam por `aria-describedby` e marcam `aria-invalid`; o
quarto — a regra de exibição dos produtos — é descrição do **grupo**, e o
`<fieldset>` a recebe por `aria-describedby` escrito à mão, porque `<fieldset>`
não é primitivo e não faz isso sozinho.

A seta dos dois `<select>` também mudou de dono: era um data URI com
`stroke='%2394a3b8'` cravado — slate-400, **2,56:1** sobre o campo branco, abaixo
dos 3:1 da 1.4.11 — e data URI não aceita `var()`, então ela nunca seguiu o
tema. O `Select` desenha a seta com o `Icon`, que herda `currentColor`.

---

## O que resta à mão — a contagem

**Contar, não julgar**: um número maior que zero significa que alguém tem de
olhar, não que há trabalho pendente.

| o que | quantos | observação |
|---|---:|---|
| `<svg>` solto | **0** | eram 4 |
| classe de paleta crua em código | **0** | eram 46; restam 5 menções em **comentário**, citando o que saiu |
| `text-white` | **0** | era 1; a ocorrência restante é comentário |
| cor cheia semântica como texto | **0** | eram 3 |
| hexadecimal em código | **0** | eram 3; a linha restante é comentário |
| linhas da varredura de contraste | **0** | eram 4 (2 pares × 2 temas) |
| `theme` lido em JavaScript | **0** | não havia |
| `<label>` sem `htmlFor` | **0** | eram 4 |
| campo sem `id` | **0** | eram 2 |
| mapas locais | **1** | `ESTADOS_DO_ARTIGO`, ver abaixo |
| controles à mão | **3** | 2 abas + 1 chip de produto, ver abaixo |
| cascas de cartão à mão | **1** | o cabeçalho, ver abaixo |
| classe `prose-*` inerte | **23** | continuam inertes; ver acima |

**O mapa local que ficou, e por quê.** `ESTADOS_DO_ARTIGO` guarda os três
estados de um ARTIGO — rascunho, publicado, arquivado. `lib/status.ts` é a fonte
única do status de **chamado**: sete valores, outro vocabulário, outro ciclo de
vida. Estado de artigo não tem módulo nenhum, e criar um é escrever em
`src/lib/`, fora do escopo desta tela. Ficou local, com o rótulo, a **variante do
`Badge`** (o vocabulário do primitivo, não um segundo) e a classe do ponto por
extenso. **A `KBListPage` tem a segunda cópia, com os mesmos três
hexadecimais.** Relatado.

**Os três controles à mão, e por que cada um ficou:**

1. **as duas abas "Editar"/"Preview"** — são um alternador de dois estados
   dentro de uma pílula segmentada, com borda compartilhada e sem preenchimento.
   As cinco variantes de `Button` trazem fundo, raio e altura próprios, e a
   pílula deixaria de existir. O que a migração trocou foi a cor e o estado
   anunciado (`aria-pressed`);
2. **o chip de produto** — mesma razão: é um alternador de contorno que ganha
   tinta ao ser escolhido, e o `Button` traria fundo cheio nas cinco variantes.
   Trocaram a cor (degrau de ação com o par dele), a borda (E7) e o visto (que
   virou `Icon`). O `aria-pressed` já existia.

**A casca à mão.** O cabeçalho é `rounded-2xl` e o `Card` é `rounded-xl`. Como o
`cn()` deste projeto é concatenação simples e **não** `tailwind-merge`, passar
`rounded-2xl` por `className` deixaria as duas classes no atributo e quem
vencesse sairia da ordem do CSS gerado. Ficou desenhado à mão com os mesmos
tokens do `Card` — raio diferente é decisão de desenho, e não se decide aqui. É
a mesma escolha da `KBArticlePage`.

---

## O que mudou na TELA, e que alguém vai ver

| onde | antes | agora |
|---|---|---|
| trilha | **um** botão com "Base de Conhecimento / \<título\>" dentro, levando os dois para o MESMO destino | dois links: "Base de Conhecimento" → `/kb` e o título do artigo → `/kb/:id` |
| "Cancelar" | botão que chamava `navigate()` | link (`Button to=`), com aparência de botão secundário |
| visto do chip de produto | o caractere `✓` | `Icon name="check"` — certo **dentro de um círculo** |
| selo de estado | pílula à mão, `font-semibold`, com ponto em hexadecimal | `Badge` (`font-medium`), com o ponto em token |
| tags do resumo | pílulas à mão | `Badge variant="secondary"` |
| fundo dos dois seletores | `bg-surface-elevated` | `bg-surface`, que é o que o `Select` desenha |
| borda das seções | `borda/40` | `borda` cheia, que é o que o `Card` desenha |
| ajuda de Markdown | `<p>` sempre visível ao lado do campo | `hint` do primitivo — **some enquanto há erro**, que é a regra do `Input`/`Textarea` |
| abas Editar/Preview | só a tinta dizia qual estava aberta | `aria-pressed` diz |
| grupo Produtos | rótulo solto | grupo com nome, e o erro descrevendo o grupo |

Nenhuma dessas mexe em número que alguém lê, nem no que a tela envia ao backend.
As duas primeiras são a regra "navegação é link, ação é botão"; a terceira e a
oitava são as únicas que alteram o que se vê sem corrigir um defeito, e estão
relatadas.

---

## O que NÃO foi feito, e por quê

- **Criar `lib/estado-do-artigo.ts`.** É escrita em `src/lib/`, fora do escopo.
  Enquanto não existir, esta tela e a `KBListPage` carregam a mesma tabela em
  duplicata. Relatado.
- **Consertar a `KBListPage`.** Ela tem a mesma tabela `IC`, o mesmo
  `STATUS_CONFIG` com `text-slate-500` sobre `bg-surface-elevated` e os mesmos
  três hexadecimais do ponto (linhas 22–24 e 154–156). Não é a minha tela.
- **Instalar o `@tailwindcss/typography`.** `package.json` e
  `tailwind.config.js`, os dois fora do escopo. Relatado.
- **Dar aparência real à pré-visualização.** Ela hoje não tem estilo nenhum;
  escolher que aparência ela passa a ter é decisão de desenho. Relatado.
- **Marcar o Título como obrigatório no HTML (`required`).** O atributo dispara
  a validação nativa do navegador, que bloqueia o `submit` antes do
  `handleSubmit` e mostra o balão do agente — a tela tem validação própria, e as
  duas juntas mudariam o que ela faz.
- **Tratar o `getProducts` que falha.** O `.catch(() => setProducts([]))`
  engole o erro: quem desmarcar "todos os produtos" com a rede fora lê "Nenhum
  produto cadastrado", que é a informação errada. É defeito de produto e muda o
  que a tela diz. Relatado.
- **O desvio F1 (foco em `ring` e não em `outline`).** Os campos continuam com o
  anel do Tailwind. Alinhar ao `outline` interno do pacote é mudança em
  `components/ui/`, fora do escopo.

---

## Testes

`src/test/pages/KBFormPage.test.tsx`, **15 casos**, todos validados por mutação —
o arquivo não existia. Nenhum caso olha classe: o happy-dom não aplica CSS, e um
mutante de classe sobrevive por um motivo que não tem nada a ver com o que o
caso mede.

Seis dos quinze são sobre os **rótulos e o grupo**, que é o defeito próprio de
uma tela de formulário.

**Quinze mutações, todas no ELEMENTO ou no comportamento**, e o que cada uma
matou:

| mutação | caso que morreu |
|---|---|
| o `Select` de Categoria perde o `label` | os dois seletores têm nome próprio |
| o rótulo de Tags perde o `htmlFor` | os três campos de texto têm nome próprio |
| a ajuda de Markdown deixa de ser `hint` | a ajuda de Markdown descreve o campo |
| `<legend>` volta a ser `<div>` | os produtos são um grupo com nome |
| o `aria-describedby` do grupo vira `data-*` | o erro dos produtos chega ao grupo |
| a tela passa a enviar sempre `product_ids: []` | o produto escolhido vai no que a tela envia |
| "todos os produtos" passa a enviar TODOS os ids | «todos os produtos» envia lista vazia |
| as opções de categoria voltam ao valor cru | a categoria sai do módulo: as oito |
| `catLabel` volta a ser o valor cru | o resumo mostra o RÓTULO da categoria |
| o selo mostra `estado.value` no lugar do rótulo | o resumo mostra o estado pelo rótulo |
| os dois links da trilha voltam ao mesmo destino | a trilha são dois links com destinos diferentes |
| "Cancelar" volta a ser botão | «Cancelar» é um LINK |
| a aba Preview deixa de anunciar que está aberta | a aba aberta fica anunciada |
| o aviso da pré-visualização vazia nunca é desenhado | sem conteúdo, a pré-visualização avisa |
| a pré-visualização passa a injetar HTML vazio | com conteúdo, mostra o artigo em vez do aviso |

O roteiro tem as **duas** defesas do briefing, e uma terceira que o `-t` do
vitest exigiu:

1. um **controle sem mutação nenhuma**, que precisa passar antes da primeira;
2. o vitest chamado por `process.execPath` + `node_modules/vitest/vitest.mjs`,
   **nunca** por `npx.cmd` — no Windows o `.cmd` é script de shell, o
   `execFileSync` sem `shell: true` não o executa, e o roteiro leria "não
   falhou" como "o mutante passou";
3. a conferência de que o filtro **casou algum caso**. O `-t` do vitest não
   remove os outros: ele os marca `skipped`, e o total continua 15. Quem prova
   que a mutação foi medida é o número de casos **executados** — total menos
   pulados. As quinze rodadas executaram exatamente **1** caso cada.

Restauração em `finally`, a partir do **buffer** original (não da string), e
**nenhum `git`**: a árvore é compartilhada.

Uma nota do ambiente que virou comentário no teste: neste projeto o `DOMPurify`
sobre o DOM do happy-dom devolve o markdown **sem as tags** (`## Um título` volta
como `"Um título\n"`). O caso da pré-visualização afirma por isso o **ramo** —
texto do artigo no lugar do aviso — e não a marcação gerada; um
`getByRole("heading")` reprovaria por causa do sanitizador, e não por causa da
tela.

---

## Verificação

| conferência | resultado |
|---|---|
| `npx vitest run src/test/pages/KBFormPage.test.tsx` | 15 passaram |
| mutação | **15 mortas de 15**, nenhuma sobrevivente |
| `npx tsc --noEmit -p tsconfig.app.json` | sem erro |
| `npx eslint` nos dois arquivos | limpo |
| `varredura-contraste.mjs` \| `grep KBFormPage` | **nenhuma linha** (eram 4) |
| classes de paleta crua em código | **0** (eram 46) |
| `<svg>` solto | **0** (eram 4) |
| hexadecimal em código | **0** (eram 3) |
| `text-white` | **0** (era 1) |
| cor cheia semântica como texto | **0** (eram 3) |
