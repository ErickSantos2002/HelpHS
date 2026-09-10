# Fase 16 — `GroupsPage`

Página: `/grupos` (papéis `admin` e `technician`, pelo `RoleGuard` do `App.tsx`)
— `frontend/src/pages/groups/GroupsPage.tsx`

A maior do lote: 1295 linhas antes, 1245 depois. Nove componentes de ícone
locais, dois `<svg>` cravados no meio do JSX e 160 classes de paleta crua —
quase toda `slate-*` e `amber-*`, viva por causa do desvio D5.

## Ficha da §29

```text
Página: /grupos — src/pages/groups/GroupsPage.tsx

FUNCIONALIDADE
[x] carrega dados      — `listGroups`, `getGroup`, `getCompany`,
                          `listGroupNotes`, `listCompanyNotes`,
                          `getCompanySuggestions`, `listUnassignedClients`:
                          mesmo método, URL e params de antes
[–] filtra               — a tela não tem filtro por atributo
[x] busca                — três buscas de texto (grupos na barra lateral,
                          empresas sugeridas, clientes por vincular), todas
                          sobre a lista já em memória, inalteradas
[x] pagina               — `Pagination` em três listas, inalterada
[–] ordena               — a tela não ordena
[x] cria                 — grupo, empresa (manual e por sugestão), nota de
                          grupo, nota de empresa, vínculo de cliente
[x] edita                — grupo, empresa, notas do cliente
[x] exclui               — grupo, empresa, notas e vínculo, todos com
                          `confirm()` nativo (pré-existente; ver "O que não fiz")
[x] abre detalhes       — `CompanyDetailModal`, inalterado
[–] anexa/remove arquivo
[x] respeita permissões — a rota é do `RoleGuard`; a tela não ramifica por
                          papel, e nada disso mudou
[x] mostra erro          — `toastApiError` e `toast.error`, inalterados
[x] mostra estado vazio — sem grupo, sem resultado de busca, sem empresa,
                          sem cliente, sem nota: seis estados, todos mantidos
[x] mostra loading       — `Spinner` na lista, no detalhe e por linha
[x] funciona no mobile   — gaveta da barra lateral e painel de notas próprio,
                          inalterados
[x] funciona no tema escuro — zero par `text-slate-* dark:text-slate-*`
                          (eram 14) e zero classe escrita só para um tema
[x] nenhum campo depende do placeholder — os três campos de busca ganharam
                          `aria-label`; os demais já vinham com `label` do
                          `Input`/`Textarea`
[–] barras desenhadas    — a tela não tem `progressbar`/`meter`

ACRESCENTADOS PELAS DECISÕES
[ ] o que a interface MOSTRA é o que a árvore DIZ, por estado
    repouso    ok — os controles têm nome; os três botões só de ícone que não
               tinham ganharam `aria-label`/`title`
    selecionado  **NÃO fecha**: as duas tiras de abas são `<button>` à mão, e
               a aba ativa é dita só pela cor da borda. Não declarei
               `role="tab"` nem `aria-selected` — declarar o papel sem o
               contrato de teclado é o defeito que o próprio `ui/Tabs.tsx`
               documenta. Volta para o operador (ver "O que não fiz")
    hover      `hover:bg-tint-warning` / `hover:bg-action-tint`, mesmo efeito
               visual de antes, agora por token
[x] nenhuma ação só de mouse — os cartões de nota são `<div onClick>`, mas
    toda ação que eles abrem (ver, deletar) tem um `<button>` próprio dentro;
    nenhum `focus:outline-none` sem substituto foi introduzido
[x] nenhum `text-slate-*` sem `dark:` — zero `slate-*`, `amber-*` e `red-*`
    restantes (eram 160 no total)
[x] nenhuma cor fora do sistema — zero hexadecimal (já eram zero), zero cor
    cheia semântica como texto (já eram zero), zero paleta crua
[–] `Alert` já montado leva `live={false}` — a tela não renderiza `Alert`
[ ] desvio F1 — não tocado; o `<input>` da busca lateral segue com
    `focus:outline-none` + borda própria, como estava
[x] nenhum primitivo reinventado — as 9 funções `Icon*` locais saíram; 11
    `<svg>` soltos viraram 31 usos de `Icon`
[x] a catraca desceu — o único lugar desta tela foi a zero
```

## O que a tela tinha

- **Nove componentes de ícone locais** — `IconPlus`, `IconEdit`, `IconTrash`,
  `IconNote`, `IconX`, `IconChevronRight`, `IconChevronLeft`, `IconBuilding`,
  `IconUsers` — mais **dois `<svg>` escritos direto no JSX**: a lupa da busca
  lateral e a ilustração de 64px do estado "selecione um grupo". Onze desenhos,
  todos redesenhando traçado que o pacote já tem.
- **160 classes de paleta crua do Tailwind**, em três famílias:
  - `slate-*` (a maioria), boa parte em pares `text-slate-NNN dark:text-slate-MMM`
    reimplementando à mão a escada de texto do pacote;
  - `amber-*` (as notas, que são o tema visual da tela) — `bg-amber-50`,
    `dark:bg-amber-950/15`, `border-amber-200`, `text-amber-600/70`,
    `dark:text-amber-700/50` e mais nove variações, todas para dizer "isto é
    uma nota";
  - `red-*` nas ações destrutivas (`text-red-500`, `hover:text-red-400`,
    `hover:bg-red-900/20`).
- **`text-primary` e `bg-primary/10` como degrau de ação** em seis lugares — a
  aba ativa, o grupo selecionado, o botão de voltar do mobile, dois botões de
  ícone e o `focus:border` do campo de busca. `--color-primary-500` é o degrau
  de marca, e sobre `--bg-base` dá 3,66:1 como texto.
- **1 lugar na catraca de contraste**: `hover:text-slate-600` sobre
  `hover:bg-surface-elevated` no botão de fechar a barra lateral no mobile —
  **2,34:1** no tema claro. O par foi escrito para o escuro
  (`dark:hover:text-slate-200`) e o D5 inverte o cinza no claro, então o hover
  clareava o texto em vez de escurecê-lo.
- **Três campos de busca sem nome acessível**, com placeholder como única
  pista, e **três botões só de ícone sem nome nenhum** (adicionar nota no
  mobile, deletar nota de grupo, deletar nota de empresa) — o `Icon` do pacote
  é `aria-hidden`, então o leitor de tela anunciava "botão" e mais nada.
- **Nenhum mapa local de status, prioridade ou categoria**: esta tela não
  mostra chamado, e portanto não tinha o que unificar com `lib/status.ts`,
  `lib/prioridade.ts` ou `lib/categoria.ts`. Também não tem gráfico, e por isso
  nada de `lib/grafico.ts`, `SLOT_DE_STATUS` ou `useTheme()` — não havia
  import de tema para remover.

## O que passou a usar

- **`Icon` de `components/ui`** nos 11 desenhos, 31 usos. Nove bateram
  caractere a caractere com o `ICON_PATHS` do pacote (`plus`, `edit`, `trash`,
  `document`, `close`, `chevronRight`, `chevronLeft`, `building`, `users`, mais
  a ilustração `groups`). O décimo primeiro é **outra lupa** — traçado de outra
  família (`M21 21l-4.35-4.35M17 11A6 6 0 111 11…` contra o
  `M21 21l-6-6m2-5a7 7 0 11-14 0…` do pacote) — e foi unificado com `search`,
  que é o caso que a E21 mediu: mesmo significado, traço diferente. Os onze são
  `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`; nenhum é da
  família sólida, e nenhum precisou de traçado novo.
- **A escada de texto** — `text-conteudo-heading` (nome de empresa e de grupo),
  `text-conteudo` (corpo), `text-conteudo-muted` (secundário: e-mail, CNPJ,
  contagem) e `text-conteudo-faint` (só a ilustração de 64px, que é desenho e
  não texto).
- **A tinta `warning`** em todo o tema de notas: `bg-tint-warning`,
  `border-warning/20`, `hover:border-warning/40`, `text-on-tint-warning`. É o
  mesmo vocabulário já em produção no painel de notas internas do
  `TicketDetailPage`, linha por linha — as duas telas mostram a mesma coisa e
  agora falam a mesma cor.
- **A tinta `danger`** nas ações destrutivas: `text-on-tint-danger` e
  `hover:bg-tint-danger`, também espelhando o `TicketDetailPage`.
- **O degrau de ação** — `bg-action-tint` + `text-conteudo-link` no grupo
  selecionado e no botão de voltar do mobile (padrão já em produção no
  `ReportsPage` e no `FileUpload`), `border-action` na aba ativa e no
  `focus:border` do campo de busca.
- **`aria-label`** nos três campos de busca e nos dois botões de deletar nota;
  `title="Adicionar nota"` no botão do painel mobile, igualando o do desktop.

## Os números

| | antes | depois |
|---|---:|---:|
| linhas da varredura de contraste para este arquivo | 1 (2,34:1, claro) | 0 |
| paleta crua do Tailwind, fora de comentário | 160 | 0 |
| `<svg>` soltos | 11 | 0 |
| hexadecimal cravado | 0 | 0 |
| cor cheia semântica como texto | 0 | 0 |
| mapas locais de status/prioridade/categoria | 0 | 0 |
| campos de busca sem nome acessível | 3 | 0 |
| botões só de ícone sem nome acessível | 3 | 0 |
| linhas do arquivo | 1295 | 1245 |
| testes | 3 | 9 |

Os **6 casos novos** foram todos validados por mutação no arquivo da tela, uma
mutação por vez, restaurando de cópia (nunca por `git`):

| mutação | quem morreu |
|---|---|
| a aba "Notas" passa a chamar `setActiveTab("clients")` | os 2 casos da aba de notas |
| o botão de deletar nota perde o `aria-label` | só o caso do nome acessível |
| a barra lateral escreve `{g.id}` no lugar de `{g.name}` | os 4 casos da página |
| o campo de busca perde o `aria-label` | o caso do nome + o da filtragem |
| o filtro da busca passa a aceitar tudo (`true \|\|`) | só o caso da filtragem |
| escolher o grupo deixa de chamar `loadGroupDetail(g)` | só o caso das empresas |

`npx vitest run src/test/pages/GroupsPage.test.tsx` (9 passando),
`npx tsc --noEmit -p tsconfig.app.json` (sem erro neste arquivo),
`npx eslint` (tela e teste) e a varredura de contraste sem uma linha sequer
deste arquivo.

## A contagem do que resta à mão

```text
src/pages/groups/GroupsPage.tsx: 0 <svg> soltos
                                 0 cores cruas
                                 19 <button> à mão
                                  1 <input> à mão
```

**Contar, não julgar** — os 20 controles à mão se dividem assim:

- **4 botões de aba**, em duas tiras (`AddCompanyModal` e `CompanyDetailModal`).
  O `ui/Tabs` existe e resolve teclado, `aria-selected` e painel, mas desenha
  **pílula sobre `bg-surface-elevated`**, e estas são **sublinhado com
  `border-b-2`**. Trocar muda a aparência das duas tiras: é decisão de desenho,
  e volta para o operador.
- **8 botões só de ícone** (novo grupo, fechar barra lateral, notas do cliente,
  desvincular cliente, deletar nota ×2, ver detalhes, deletar empresa) e
  **1 botão de ícone com texto** — todos com nome acessível agora, todos com o
  mesmo par de tinta. `Button variant="ghost"` os cobriria, mas mudaria
  espaçamento e raio; não é troca de token.
- **6 botões que são superfície clicável** — o item da lista de grupos, o
  cartão de empresa (nome, contagem), o alternador do mobile, "Criar primeiro
  grupo" e "Adicionar nota". São `<button>` corretos, com o texto dentro;
  nenhum primitivo do pacote cobre "linha inteira clicável".
- **1 `<input>` à mão**: a busca da barra lateral, `text-xs` com a lupa
  posicionada por cima. O `Input` do pacote não tem casa para ícone e é de
  outro tamanho — mesmo caso, e mesma escolha, do campo de busca do
  `TicketListPage`, que também ficou à mão depois de migrado.

## O que não fiz, e por quê

- **Não troquei as duas tiras de abas pelo `ui/Tabs`** — muda o desenho (ver
  acima), e por isso não declarei `role="tab"` nem `aria-selected` nos botões
  atuais: o comentário do próprio `ui/Tabs.tsx` registra que declarar o papel
  sem as setas prende quem usa leitor de tela esperando um comportamento que
  não vem. O estado "selecionado" da aba segue dito só pela cor. **É o único
  item da §29 que esta tela não fecha**, e está na lista do operador.
- **Não toquei o `confirm()` nativo** das quatro exclusões. Substituir por
  modal de confirmação é mudança funcional (o que a tela mostra e quando),
  não troca de token.
- **Não toquei o desvio F1.** O `<input>` da busca lateral tem
  `focus:outline-none` com `focus:border-action` no lugar — pré-existente; só
  troquei `primary` por `action` dentro da mesma string. Alinhar foco é decisão
  de interação registrada à parte (`VERSION.md`, Checkpoint 4).
- **Não mexi na opacidade** do `text-xs opacity-60` da contagem de empresas no
  item da lista. Sobre `text-conteudo-muted` isso derruba o contraste bem
  abaixo do piso, e a varredura não vê opacidade — mas tirar o `opacity-60`
  muda a hierarquia visual do item, que é desenho. Fica anotado.
- **Não criei nenhum token, primitivo ou entrada de módulo.** Tudo que a tela
  precisava já existia: `Icon` (com os três traçados da E21), as tintas, a
  escada de texto e o degrau de ação. Nada faltou no pacote.
- **Não reescrevi `src/test/pages/GroupsPage.test.tsx`**: os 3 casos que já
  prendiam o `useCallback` do `CompanyDetailModal` continuam como estavam, e
  os 6 novos entraram depois deles. A fábrica do `vi.mock` cresceu para cobrir
  a página inteira — um nome que falta ali só estoura quando a tela **chama** a
  função, que é por que a lista antiga passava sem eles.
- **Não toquei nenhum arquivo de outro agente.** `AuditLogsPage.tsx` e
  `ProductsPage.tsx` aparecem modificados na árvore compartilhada; são de
  outras sessões.
