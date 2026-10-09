# §29 — `pages/kb/KBListPage.tsx`

A tela irmã da `KBArticlePage`, e com os mesmos defeitos: a mesma tabela local
`IC` com **11 desenhos**, o mesmo par de 2,34:1, o mesmo polegar. Fora isso,
**dois** mapas locais mais uma terceira lista de categorias escrita à mão dentro
do JSX, **três hexadecimais cravados**, e uma lista inteira que o teclado não
alcançava.

367 linhas antes, 544 depois. O arquivo cresceu por dois motivos, e nenhum é
código: a tabela de ícones virou chamada de primitivo (menos linhas) e o
**porquê** de cada escolha ficou escrito (mais linhas).

---

## O que a tela tinha

| o que | quantos |
|---|---:|
| classes da paleta crua (`slate-*` e `red-*`) | **37** em 367 linhas |
| `<svg>` solto | **11** desenhos, em **14** lugares |
| tabela local de ícones (`IC`) | **1**, com 11 entradas |
| mapas locais | **2** (`CATEGORY_LABEL`, `STATUS_CONFIG`) |
| lista de categorias escrita à mão no JSX | **1**, com os 8 pares repetidos |
| hexadecimal cravado | **3** |
| par `bg-primary` + `text-white` (3,83:1) | **1** lugar |
| par `bg-surface-elevated` + `text-slate-500/600` | **4** lugares |
| cor cheia semântica como cor de TEXTO | **1** (`hover:text-danger`) |
| `text-white` | **1** |
| linhas na varredura de contraste | **10** (5 pares × 2 temas) |
| `useTheme()` | **0** — não há gráfico nenhum nesta tela |
| controle sem nome acessível | **4** (busca, «x» da busca, editar, excluir) |
| lista sem alcance por teclado | **1** (a linha inteira era `<div onClick>`) |

### Os 3 hexadecimais: 3 de decisão, 0 de dado

O briefing manda separar **decisão de desenho** (vira token) de **dado** (cor
escolhida pelo usuário, que fica). Aqui os três eram decisão:

| onde | era | virou |
|---|---|---|
| amostra do filtro «Publicado» | `#10b981` | `var(--fill-success)` |
| amostra do filtro «Rascunho» | `#f59e0b` | `var(--fill-warning)` |
| amostra do filtro «Arquivado» | `#64748b` | `var(--border-control)` |

**Nenhum era dado**: esta tela não desenha etiqueta com cor escolhida pelo
usuário, então `readableTextColor` de `lib/colors.ts` não tinha o que fazer aqui.

A amostra do `Selector` é `style={{ backgroundColor }}`, não classe — por isso
entra valor CSS e não utilitário. O caminho é o mesmo que o
`graficoDePrioridade()` de `lib/prioridade.ts` já fazia, **inclusive o neutro**:
lá também é `--border-control`, porque `--fill-muted` não existe e o pacote
resolve o neutro com o contorno de controle.

---

## O que passou a usar

| módulo / primitivo | onde | quantos |
|---|---|---:|
| `Icon` (E20/E21) | os 8 desenhos que sobraram | **11** chamadas |
| `Badge` | status, categoria, "Todos os produtos", produtos, tags | **5** |
| `Button` | "Novo artigo", "Cancelar", "Sim, excluir" | **3** |
| `Alert` | o aviso de exclusão irreversível | **1** |
| `Pagination` | o rodapé da lista | **1** |
| `Modal` + `ModalFooter` | o diálogo de exclusão | **1** |
| `FilterSelect` | categoria, produto, status | **3** |
| `Spinner` | o carregamento | **1** |
| `Link` | título, editar, "+ Criar primeiro artigo" | **3** |
| `lib/categoria.ts` | `rotuloDeCategoria` (×2) e `CATEGORIAS` (×1) | 1 módulo |

### Os 11 `<svg>`, e como cada um casou

Os 11 eram `viewBox="0 0 24 24"` com `fill="none"` e `stroke="currentColor"` —
a mesma família do `Icon`, **conferido antes de trocar**, como a regra do
briefing exige. Nenhum era 20×20 nem de preenchimento, e por isso nenhum ficou
para trás. Os traçados foram comparados caractere a caractere com
`ICON_PATHS_PACOTE`.

| desenho | virou | como casou |
|---|---|---|
| lupa | `search` | traçado idêntico |
| «×» | `close` | traçado idêntico (2 usos) |
| mais | `plus` | traçado idêntico |
| livro aberto | `book` | traçado idêntico (3 usos) |
| olho | `eye` | traçado idêntico, os dois `d` (pupila + contorno) |
| polegar para cima | `thumbsUp` | traçado idêntico — ver abaixo |
| lápis sobre folha | `edit` | traçado idêntico |
| lixeira (`w-4`) | `trash` | traçado idêntico |
| lixeira (`w-3.5`) | — | **absorvida**: o bloco virou `Alert` |
| chevron esquerdo | — | **absorvido**: o rodapé virou `Pagination` |
| chevron direito | — | **absorvido**: o rodapé virou `Pagination` |

Nenhum ícone novo foi preciso. Os três "absorvidos" existem no pacote
(`trash`, `chevronLeft`, `chevronRight`) e teriam casado por traçado; o que
tirou os três da tela foi trocar o desenho à mão pelo primitivo que já os
desenha por dentro.

### O polegar, e por que ele NÃO precisou de constante nomeada

A `KBArticlePage` mantém `TRACO_POLEGAR_PARA_CIMA` / `..._PARA_BAIXO` porque
mostra os dois lado a lado, num "Sim" e num "Não", e o ponto de uso precisa
dizer o que o desenho faz. Aqui há **um** polegar e ele é o de cima, com a
contagem de "útil" ao lado. Depois da **E21-b**, `thumbsUp` é o de cima — a
chamada direta já diz a verdade, e uma constante de uma linha para um uso só
seria indireção sem ganho.

O caso de teste que confere o traçado (`M14 10h4.764…`) fica: `ICON_PATHS` é
mapa de texto, todo texto cabe, e **nem `tsc`, nem ESLint, nem teste de
componente acusam** um polegar invertido.

### O degrau de ação, que é o motivo da tela estar na catraca

"Novo artigo" era `bg-primary` com `text-white`: **3,83:1 nos dois temas**,
porque o degrau 500 é absoluto e não inverte. E era um `<button>` chamando
`navigate()`. O `Button to=` resolve os dois — par `--action` /
`--text-on-primary` da E2, e um `<a>` de verdade.

### As quatro linhas de `bg-surface-elevated`

`text-slate-500` e `text-slate-600` sobre `bg-surface-elevated` no **mesmo**
elemento davam 4,34:1/2,85:1 e 2,34:1/1,79:1. As quatro viraram
`text-conteudo-muted` — o degrau que a **E5** levou a `slate-600` no claro
justamente para dar 6,92:1 sobre a superfície elevada. **Não** viraram
`text-conteudo-faint`: `faint` sobre `elevated` é o par de 2,34:1 que a regra 4
do briefing nomeia.

Três dos quatro nem existem mais como classe: eram os chips de status,
categoria e tag, que viraram `Badge`.

### O aviso de exclusão

Era um bloco à mão em `red-900/20` sobre `red-800/40`, com disco `red-900/40` e
texto `red-300`/`red-400/80` — **sete** classes da paleta crua, escritas só para
o tema escuro: no claro, um fundo vermelho quase preto sobre superfície branca.
Virou `Alert variant="danger" live={false}`, que é o mesmo caminho que o
`EquipmentPage` e o `SettingsPage` já usam no mesmo lugar. O `live={false}` é a
**E12**: o aviso já está na tela quando o modal abre, e região viva anuncia
mudança.

### A cor cheia semântica como texto

`hover:text-danger` no botão "Limpar" — a única da tela — virou
`hover:text-on-tint-danger`. A borda continua `hover:border-danger/30`: cor
cheia a 30% é **forma**, não texto, e é como o `Badge` a escreve desde a E8.

### O status do artigo, que não é o status do chamado

`lib/status.ts` é a fonte única dos **sete status de chamado**. Estes três —
publicado, rascunho, arquivado — são outro domínio: o ciclo editorial. A tabela
ficou local, mas com a disciplina dos módulos de `lib/`: rótulo, variante do
`Badge` e amostra saem de um lugar só, e as opções do filtro são **derivadas**
dela em vez de escritas ao lado. Antes eram duas listas paralelas mantidas à
mão — o mesmo modo de falha que deu três cópias do mapa de papel dentro do
`UsersPage`.

⚠️ **Ela já tem um segundo consumidor** (`KBFormPage`). Ver "o que não foi
feito".

---

## O que resta à mão — a contagem

**Contar, não julgar**: um número maior que zero significa que alguém tem de
olhar, não que há trabalho pendente.

| o que | quantos | observação |
|---|---:|---|
| `<svg>` solto | **0** | eram 11 em 14 lugares |
| classe de paleta crua em código | **0** | eram 37; as 4 ocorrências restantes no arquivo são texto de comentário |
| hexadecimal em código | **0** | eram 3; as 3 ocorrências restantes citam o que saiu, num comentário |
| `text-white` | **0** | era 1 |
| cor cheia semântica como texto | **0** | era 1 |
| linhas da varredura de contraste | **0** | eram 10 |
| mapas locais | **1** | o status do artigo, ver abaixo |
| `theme` lido em JavaScript | **0** | não havia |
| controles à mão | **7** | 4 `<button>` + 3 `<Link>`, ver abaixo |
| cascas de cartão à mão | **3** | o cabeçalho, o estado vazio e a linha da lista |

**O mapa local que ficou.** `STATUS_DO_ARTIGO` — os três estados editoriais do
artigo. Não há módulo em `lib/` para eles, e `lib/status.ts` é de outro domínio.
Ficou local com a disciplina dos módulos; **devia subir**, e o porquê está em "o
que não foi feito".

**Os sete controles à mão, e por que cada um ficou:**

1. **o «x» que esvazia a busca** e **o «x» que limpa os filtros** — dois botões
   de ícone dentro de uma barra de filtros de 36px de altura. `Button` traz
   altura e preenchimento próprios e quebraria a barra. O que a migração trocou
   foi a cor e o **nome acessível**, que não existia em nenhum dos dois;
2. **"Limpar filtros" do estado vazio** — ação de texto de 12px no meio de um
   bloco vazio; `Button variant="ghost"` mudaria o leiaute do bloco;
3. **"Excluir" da linha** — botão de ícone de 1,5 de preenchimento numa linha
   densa, pelo mesmo motivo dos dois primeiros. Ganhou `aria-label` com o
   **título do artigo**: numa lista de vinte linhas, vinte controles chamados
   "Excluir" não dizem qual dos vinte;
4. **"Editar" da linha, o título do artigo e "+ Criar primeiro artigo"** — os
   três navegam, e por isso são `Link` e não botão. Nenhum deles cabe na
   geometria do `Button`: dois são ícone/texto de 12px dentro da linha, e o
   terceiro é texto de 12px no estado vazio.

**As três cascas à mão.** O cabeçalho é `rounded-2xl` e o `Card` é
`rounded-xl`; o `cn()` deste projeto é concatenação simples, **não**
`tailwind-merge`, então passar `rounded-2xl` por `className` deixaria as duas
classes no atributo e quem vence sairia da ordem do CSS gerado. Raio diferente é
decisão de desenho e não se decide aqui. O estado vazio e a linha da lista são
`rounded-xl` como o `Card`, mas com `border-borda/40` em vez de `border-borda` —
mesma razão, mesmo impedimento. As três usam os tokens do `Card`.

---

## O que mudou na TELA, e que alguém vai ver

| onde | antes | agora |
|---|---|---|
| chips da linha (status, categoria, produtos, tags) | pílulas à mão, `text-[10px]`, `rounded-md` | `Badge`, `text-xs`, `rounded-full` — as linhas ficam um pouco mais altas |
| título do artigo | `<span>` com `hover:text-primary` | `Link` de verdade, alcançável por teclado |
| "Editar" da linha | botão que chamava `navigate()` | link |
| "Novo artigo" e "+ Criar primeiro artigo" | botões que chamavam `navigate()` | links |
| rodapé de paginação | "‹ Anterior" / "Próxima ›", sem `nav` e sem pular página | `Pagination`: região "Paginação", números da janela, `aria-current="page"`, "Mostrando 1 a 20 de N artigos" |
| aviso de exclusão | bloco vermelho à mão com disco de lixeira | `Alert` `danger` com o ícone de erro do pacote |
| contadores da linha | "12" e "3", sem unidade nenhuma | leitor de tela lê "12 visualizações" e "3 votos de útil" |
| campo de busca, «x», editar, excluir | sem nome acessível | "Buscar artigos", "Limpar busca", "Editar <título>", "Excluir <título>" |
| borda do campo de busca | `borda/60` (≈1,2:1) | `--border-control` (E7, ≥3:1) |

Nenhuma dessas mexe em número que alguém lê, e nenhuma muda texto de rótulo: os
oito rótulos de categoria e os três de status do módulo/tabela são iguais aos
que estavam escritos à mão. **A divergência aqui era estrutural, não textual** —
ao contrário da `KBArticlePage`, onde "Admin" virou "Administrador".

---

## O que NÃO foi feito, e por quê

- **Subir o status do artigo para `src/lib/kbStatus.ts`.** `pages/kb/KBFormPage.tsx`
  repete os três rótulos e os três hexadecimais — pela regra registrada no
  `lib/papel.ts` (tabela com **um** consumidor fica local, com **vários** sobe),
  esta devia subir. `src/lib/**` está fora do escopo desta tela. Relatado.
- **Trocar `FilterSelect` por `Selector`.** O invólucro é `@deprecated` e não
  aceita `label`, então os quatro filtros da barra se anunciam **só pelo valor
  escolhido**, sem dizer de que filtro são — o defeito que o próprio `Selector`
  documenta ter consertado. Trocar aqui e não nas outras sete telas que usam
  `FilterSelect` criaria justamente a divergência que esta fase existe para
  eliminar. Relatado.
- **Tratar o erro da busca e o da exclusão.** `getKBArticles` e `deleteKBArticle`
  são chamados **sem `catch`**: uma falha de rede deixa a lista anterior na tela
  sem aviso nenhum, e uma exclusão que falha fecha o `loading` e não fecha o
  modal, sem dizer o que houve. É o mesmo achado da `KBArticlePage`, e é defeito
  de produto — muda o que a tela faz. Relatado.
- **Tirar o `onClick` da linha inteira.** Ele continua como conveniência de
  mouse. O que a migração acrescentou foi o caminho acessível (o título virou
  link); remover o clique da linha mudaria o que a tela faz para quem usa mouse,
  e isso não se decide aqui.
- **Trocar `hover:border-primary/30`, `hover:bg-primary/[0.02]` e
  `hover:bg-primary/10` pelo degrau de ação.** São véus e contornos de realce,
  não texto nem fundo cheio com texto por cima; a catraca não os vê e o degrau
  certo para um realce de 2% é decisão de desenho. Ficaram como estavam, em
  token.
- **O `Card` nas três cascas.** Raio e opacidade de borda diferentes, e o `cn()`
  não resolve conflito de classe. Ver acima.
- **O desvio F1 (foco em `ring` e não em `outline`).** O campo de busca continua
  com o anel do Tailwind. Alinhar ao `outline` interno do pacote é mudança em
  `components/ui/`, fora do escopo.

---

## Testes

`src/test/pages/KBListPage.test.tsx`, **15 casos**, todos validados por mutação —
o arquivo não existia. Nenhum caso olha classe: o happy-dom não aplica CSS, e um
mutante de classe sobrevive por um motivo que não tem nada a ver com o que o
caso mede.

**Dezesseis mutações, todas no ELEMENTO ou no comportamento**, e o que cada uma
matou:

| mutação | caso que morreu |
|---|---|
| `rotuloDeCategoria(...)` volta a ser o valor cru | a categoria do artigo sai do módulo |
| o filtro de categoria perde sete das oito opções | as opções do filtro de categoria saem do módulo |
| o rótulo de `draft` vira "Draft" | o selo de status diz o rótulo da tabela |
| `isStaff` passa a valer sempre | cliente não vê status, nem filtro, nem "Novo artigo" |
| `user?.role === "admin"` vira `isStaff` | técnico edita mas não exclui |
| "Novo artigo" volta a ser botão com `navigate()` | "Novo artigo" é um LINK |
| o título aponta para `/kb` e não para o artigo | o título do artigo é um link alcançável |
| o `aria-label` de "Editar" perde o título do artigo | os controles da linha dizem de QUAL artigo são |
| some o texto invisível "visualizações" | os dois contadores dizem o que contam |
| `thumbsUp` vira `thumbsDown` | o polegar da contagem de "útil" aponta para CIMA |
| o campo de busca é renomeado para "Busca" | o campo de busca tem nome próprio |
| "Limpar" deixa de zerar a busca | "Limpar" zera os QUATRO filtros de uma vez |
| a paginação erra por um (`p * PAGE_SIZE`) | a página 2 pede o segundo lote |
| o estado vazio nunca é desenhado | sem artigo nenhum, a tela convida a criar o primeiro |
| a exclusão não tira a linha da lista | excluir avisa, mostra o artigo e some com a linha |
| o `Alert` perde o título "Ação irreversível" | excluir avisa, mostra o artigo e some com a linha |

O roteiro roda um **controle sem mutação nenhuma** antes da primeira e exige que
ele passe; chama o vitest por `process.execPath` + `node_modules/vitest/vitest.mjs`,
nunca por `npx.cmd`; e confere que **algum caso rodou** antes de declarar
"morreu" — um `-t` que não casa nome nenhum faz o vitest sair 0 com zero testes.
Restauração em `finally`, cópia em memória, **nenhum `git`**.

---

## Verificação

| conferência | resultado |
|---|---|
| `npx vitest run src/test/pages/KBListPage.test.tsx` | 15 passaram |
| mutação | 16 mortas de 16, nenhuma sobrevivente |
| `npx tsc --noEmit -p tsconfig.app.json` | sem erro **nos dois arquivos desta tela** (ver nota) |
| `npx eslint` nos dois arquivos | limpo |
| `varredura-contraste.mjs` \| `grep KBListPage` | **nenhuma linha** (eram 10) |
| classes de paleta crua em código | **0** (eram 37) |
| `<svg>` solto | **0** (eram 11) |
| hexadecimal em código | **0** (eram 3) |
| `text-white` | **0** (era 1) |
| cor cheia semântica como texto | **0** (era 1) |

**Nota sobre o `tsc`.** A árvore é compartilhada: durante esta migração o
`tsc` do projeto passou a acusar dois erros, um em
`src/test/components/Sidebar.test.tsx` e outro em `src/pages/kb/KBFormPage.tsx`.
Os dois arquivos são de outros agentes, apareceram no `git status` no meio do
trabalho, e nenhum dos dois é desta tela. Na primeira execução, antes de eu
escrever qualquer coisa, o `tsc` estava limpo.
