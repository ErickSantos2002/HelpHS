# Fase 16 — `ProductsPage.tsx`

```text
Página: /produtos — frontend/src/pages/products/ProductsPage.tsx
Teste:  frontend/src/test/pages/ProductsPage.test.tsx (novo)
```

Escopo: a tela inteira, como o briefing da Fase 16 fixou depois da divergência
entre os dois primeiros agentes — paleta crua, `<svg>` soltos, fontes únicas
faltando e as três linhas da catraca de contraste. Não há gráfico nesta tela.

---

## Checklist da §29

```text
FUNCIONALIDADE (§29 do prompt mestre)
[x] carrega dados — nenhuma chamada de serviço mudou de assinatura nem de
    parâmetro. `getProducts`, `getEquipments`, `setProductActive`,
    `setEquipmentActive`, `createProduct`/`updateProduct`,
    `createEquipment`/`updateEquipment` e `getUsers` estão como estavam;
    dois casos de teste prendem os parâmetros de `getEquipments`.
[x] filtra / busca / pagina / cria / edita — os três filtros de equipamento,
    o filtro de produto, "Sem dono", as duas buscas e as duas `Pagination`
    continuam iguais. Filtro e busca seguem sendo do SERVIDOR (validado por
    mutação: trocar `without_owner` por `undefined` reprova).
[ ] ordena / exclui / anexa — não existem nesta tela.
[x] abre detalhes — o clique na linha do equipamento abre o
    `EquipmentDetailModal`; o clique na linha do produto abre o painel de
    equipamentos DELE (validado por mutação com o id trocado).
[ ] respeita permissões — não reverificado: a tela não lê `useAuth`, o
    escopo é do roteador. Nada de permissão foi tocado.
[x] mostra erro (rede) — os dois ramos `.catch` seguem intactos; o de
    produtos tem caso de teste, validado por mutação.
[x] mostra estado vazio — os TRÊS vazios (produto, equipamento, equipamento
    sem dono) continuam distintos e com a ação certa em cada um. O de "sem
    dono" tem caso próprio, validado por mutação.
[x] mostra loading — os dois `Spinner` intactos.
[ ] funciona no mobile — não reverificado visualmente (sem captura nesta
    passagem). Nenhuma classe de layout ou breakpoint foi tocada: só cor,
    ícone e os atributos de nome acessível.
[x] funciona no tema escuro — é o ponto da fase. Saíram 29 classes `dark:`
    que invertiam à mão o que o token inverte sozinho; sobrou **zero**
    `dark:` de cor na tela.
[x] nenhum campo depende do placeholder — CORRIGIDO: os dois campos de busca
    só tinham `placeholder`. Ganharam `aria-label`; caso de teste com
    mutação.
[ ] toda barra desenhada tem papel declarado — não se aplica (sem barra).

ACRESCENTADOS PELAS DECISÕES REGISTRADAS
[x] estado interativo (visual = árvore) — o estado escolhido das abas de
    filtro passou a existir na ÁRVORE (`aria-pressed`) e não só na cor. Era
    o mesmo defeito que o botão "Sem dono" da mesma tela já não tinha.
[ ] nenhuma ação só por mouse — NÃO verificado como aprovação: as duas
    linhas clicáveis (`<div onClick>`, produto e equipamento) não têm
    `tabIndex` nem `onKeyDown`. Pré-existente, contado abaixo, não corrigido
    — dar papel e teclado a essas linhas é mudar o controle, não a cor.
[x] nenhuma classe `text-slate-*` sem `dark:` correspondente — zerado por
    remoção: não há mais `text-slate-*` nenhum.
[x] nenhuma cor fora do sistema — 90 → 0 classes de paleta crua; 0 → 0
    hexadecimais; 0 → 0 cores cheias semânticas como texto.
[ ] `Alert` com `live={false}` — não tocado; os dois `Alert variant="danger"`
    seguem como estavam.
[ ] foco alinhado ao outline do pacote — não reverificado. Os dois `<input>`
    à mão trazem `focus:outline-none focus:ring-2 focus:ring-primary`,
    pré-existente e não tocado.
[x] nenhum primitivo reinventado — os nove `<svg>` viraram `Icon`. Restam
    controles à mão contados abaixo, e um deles é primitivo faltando.
[x] a catraca desceu — 3 lugares (5 pares) → 0.
```

---

## 1. O que a tela tinha

1. **`IC` — tabela local de nove ícones** (linhas 35-84), nove `<svg>`
   desenhados à mão. Conferido caractere a caractere contra o `ICON_PATHS`:
   **oito eram cópia exata** de um traçado do pacote (`box`, `edit`, `plus`,
   `search`, `chevronRight`, `eye` — que são dois traçados, os dois iguais —,
   `user`, `building`). O nono era um **segundo desenho de chip**, `<rect>` mais
   pinos, sem par exato.
2. **90 classes de paleta crua do Tailwind** em 848 linhas: `slate-*` ×81 (nas
   variantes 100/200/300/400/500/600/700/800) e `emerald-*` ×9. **Vinte e nove
   delas tinham prefixo `dark:`**, invertendo à mão o que o token já inverte
   sozinho.
3. **`ActivePill` — mapa local de cor por estado**: 31 classes cruas em duas
   receitas (`emerald` para ativo, `slate` para inativo), mais duas para o
   ponto. Tem **duas cópias divergentes** em outras telas (ver §5).
4. **As três opções de filtro escritas duas vezes no mesmo arquivo**: em
   `FilterTabs` como `{ key, label }` e no `FilterSelect` dos produtos como
   `{ value, label }`. Concordavam hoje — que é exatamente como prioridade
   começou antes de virar dez mapas divergentes.
5. **Três lugares na catraca de contraste** (5 pares): `text-slate-600` sobre
   `bg-surface-elevated` — 2,34:1 no claro e 1,79:1 no escuro — nos dois
   círculos de ícone dos estados vazios e no botão "Sem dono" desligado.
6. **Dois campos de busca sem nome acessível**, só com `placeholder`.
7. **Três abas de filtro cujo estado escolhido era só cor** (`bg-primary/20`),
   sem nada na árvore.
8. **`text-primary` como cor de três links de texto** — o degrau de MARCA, que
   o `tailwind.config.js` registra em 3,66:1 sobre `--bg-base`.

Hexadecimais cravados: **0** antes, **0** depois. `useTheme()`: nunca existiu
nesta tela.

---

## 2. O que passou a usar

- **`Icon` de `components/ui`** — 15 usos, cobrindo os nove desenhos. Os oito
  exatos foram trocados por identidade; o chip foi **unificado com `cpu` pelo
  significado**, como a §2 do briefing manda, em vez de virar ícone novo. Os
  nove `<svg>` originais eram `viewBox="0 0 24 24"`, `fill="none"`,
  `stroke="currentColor"` — a mesma família do `Icon`, conferido antes da
  troca. `size` preserva o tamanho de cada um (16 nos sete de `w-4 h-4`, 14
  nos dois de `w-3.5 h-3.5`) e `strokeWidth={2}` preserva o traço.
- **A escada de texto do pacote** — `text-conteudo-heading` (título),
  `text-conteudo` (corpo e valores), `text-conteudo-muted` (apagado). Os pares
  `text-slate-X dark:text-slate-Y` desapareceram: o token inverte sozinho, e
  três deles já divergiam entre os temas (`slate-800/slate-100`,
  `slate-600/slate-300`, `slate-400/slate-600`).
- **`text-conteudo-link` / `hover:text-conteudo-link-hover`** nos três links de
  texto ("Criar o primeiro produto", "Ver todos", "Adicionar equipamento").
- **As tintas e seus pares medidos** — `bg-tint-success` + `text-on-tint-success`
  e `bg-tint-neutral` + `text-on-tint-neutral` no `ActivePill`,
  `bg-tint-primary` + `text-on-tint-primary` na aba escolhida e no "Sem dono"
  ligado. São as mesmas receitas do `Badge`, que a E8 mediu.
- **`bg-fill-success` e `bg-borda-control`** nos dois pontos do selo. O degrau
  500 de `success` reprova 2,54:1 como preenchimento no tema claro (E19), e o
  neutro precisa **inverter por tema** — é o raciocínio que `lib/prioridade.ts`
  registra para a prioridade baixa, aplicado aqui.
- **`FILTROS`, uma lista só** para as abas e para o seletor de produtos.

`lib/status.ts`, `lib/prioridade.ts` e `lib/categoria.ts` **não entram aqui**:
produto e equipamento não têm status de chamado, prioridade nem categoria. O
único estado é ativo/inativo, que não tem módulo — e não deveria ganhar um
(§5).

---

## 3. Mudanças visíveis, e o que cada uma custa

- **A cor do selo de ativo/inativo mudou de tom.** `emerald-50/300/600` virou a
  tinta de `success` e o seu par medido; `slate-100/300/500` virou a tinta
  neutra. A palavra "Ativo"/"Inativo" e o ponto continuam onde estavam.
- **O hover do selo mudou de lugar: era o fundo, passou a ser a borda.** A
  regra (a) do D8-a proíbe modificador de opacidade sobre as tintas — elas já
  carregam 15% no token, e `bg-tint-success/20` multiplicaria os dois. Sem
  `bg-tint-*` mais escuro para onde ir, a resposta ao ponteiro foi para a
  borda, que é cor cheia e aceita o modificador. **Isto é decisão de desenho e
  volta para o operador.**
- **Os três links de texto ficaram um degrau mais escuros no claro e mais
  claros no escuro** (`--text-link` em vez do 500 de marca).
- **A aba de filtro escolhida passa a se anunciar** (`aria-pressed`). Nada
  muda na tela; muda o que um leitor de tela diz.
- **Os dois campos de busca ganharam nome** (`aria-label`). Idem.
- **O travessão "—" de dono/empresa ausente ficou um degrau menos apagado**:
  era `slate-600` dentro de um `slate-500`, e os dois viraram
  `text-conteudo-muted`. `text-conteudo-faint` seria o degrau equivalente e
  **não é par** de nenhuma das superfícies desta tela (2,34:1 sobre a
  elevada, regra 4 do briefing).

---

## 4. A contagem do que resta à mão

Contar, não julgar. Nenhum destes é pendência declarada — são números para
alguém olhar:

- **6 controles à mão**, nenhum deles primitivo do pacote:
  1. `ActivePill` — botão-selo de ativo/inativo. **É primitivo faltando** (§5).
  2. `FilterTabs` — segmentado de três opções. O `Tabs` de `components/ui`
     existe, mas declara `role="tablist"`/`role="tab"` e navega por setas; é
     outro controle, não este.
  3. o botão "Sem dono" — alternador de um estado, com `aria-pressed`.
  4. e 5. os **dois `<input>` de busca**, com ícone à esquerda. O `Input` do
     pacote não tem posição para ícone e traz `<label>` visível; trocar mudaria
     o desenho da barra de filtros.
  6. o botão "Limpar filtros".
- **3 chamadas a invólucro `@deprecated`**: `FilterSelect`, `FormDropdown` e
  `SearchSelect`, um de cada. Os três delegam ao `Selector` da Fase 8 e o
  JSDoc diz que o nome sai "quando a última tela sair". **Nenhuma tela do
  repositório chama o `Selector` direto ainda** — inclusive as já migradas
  nesta fase. Não migrei para não divergir do que os agentes vizinhos fizeram.
- **2 `<div onClick>` sem teclado** (linha do produto, linha do equipamento),
  sem `tabIndex` nem `onKeyDown`. A linha do equipamento tem um botão
  "Visualizar" que chega ao mesmo lugar; **a linha do produto não tem
  alternativa nenhuma** — selecionar um produto para ver os equipamentos dele
  é hoje uma ação só de mouse.
- **1 seletor de filtro sem nome acessível**: o `FilterSelect` de produtos não
  recebe `label` (a prop não existe no invólucro), então se anuncia pelo valor
  escolhido — "Ativos" — sem dizer de que filtro é. O próprio `Selector`
  documenta esse defeito e o resolve com `label`; o invólucro não repassa.
- **0** `<svg>` soltos, **0** classes de paleta crua, **0** hexadecimais,
  **0** cores cheias semânticas como texto, **0** `dark:` de cor.

---

## 5. O que não foi feito, e por quê

- **`ActivePill` não virou primitivo, e são TRÊS cópias divergentes.**
  `components/ui/**` está fora do escopo de escrita deste agente, e criar uma
  quarta variante local seria o defeito que a fase existe para eliminar. As
  três:
  | onde | o que é | diverge em |
  |---|---|---|
  | `pages/products/ProductsPage.tsx` | `<button>`, alterna, tem estado de carga | — |
  | `pages/equipment/EquipmentPage.tsx` | `<span>`, só mostra | o ponto inativo tem `dark:bg-emerald-400`, que o daqui não tinha |
  | `pages/users/UsersPage.tsx` (`StatusPill`) | `<button>`, três estados | tem `anonymized`, e os rótulos vêm de um `STATUS_LABEL` local |
  Só migrei a daqui. As outras duas continuam em paleta crua, e a de
  `EquipmentPage` é uma das linhas vivas da catraca.
- **Os três invólucros `@deprecated` não migraram para o `Selector`.** Ver §4.
- **As duas linhas clicáveis não ganharam teclado.** É mudar o controle, não a
  cor, e a linha do produto não tem alternativa — o conserto é desenho, não
  token.
- **Nenhuma captura de tela.** Verificação por leitura, `tsc`, `eslint`, os 11
  casos de teste com as 11 mutações, e a varredura de contraste.
- **Nada foi comitado**, como o briefing manda.

---

## 6. Números

| medida | antes | depois |
|---|---:|---:|
| `varredura-contraste.mjs` — lugares nesta tela | 3 (5 pares) | **0** |
| classes de paleta crua do Tailwind | 90 | **0** |
| `<svg>` soltos | 9 | **0** |
| usos de `Icon` | 0 | 15 |
| hexadecimais cravados | 0 | 0 |
| cor cheia semântica como texto (`CHEIAS_CONHECIDAS`) | 0 | 0 |
| classes `dark:` de cor | 29 | **0** |
| mapas locais (ícones, opções de filtro, cor por estado) | 3 | **0** |
| atributos de nome/estado acessível (`aria-*`) | 1 | 4 |
| linhas do arquivo | 848 | 843 |
| testes em `ProductsPage.test.tsx` | — (não existia) | **11**, todos passando |
| mutações aplicadas e mortas | — | **11 de 11** |

Cada uma das 11 mutações foi conferida duas vezes: que a suíte reprova, e que
quem reprova é **o caso alvo** — uma mutação que mata o caso vizinho e deixa o
alvo vivo passaria pela primeira conferência e mentiria.

`npx tsc --noEmit -p tsconfig.app.json` e `npx eslint` não relatam nada para
`ProductsPage.tsx` nem para o teste novo.
