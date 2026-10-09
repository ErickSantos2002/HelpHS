# Fase 16 — `EquipmentPage.tsx`

```text
Página: /equipamentos — frontend/src/pages/equipment/EquipmentPage.tsx
Teste:  frontend/src/test/pages/EquipmentPage.test.tsx (novo)
```

Esta tela entrou com **66 classes de paleta crua em 482 linhas** e **cinco
`<svg>` soltos**. O briefing mandava procurar um mapa local de rótulo ou cor
por tipo/estado; o que existe aqui não é mapa de N chaves — é um **booleano**,
`is_active`, com o rótulo, a cor e o plural escritos em quatro lugares
diferentes do arquivo, sem nada ligando-os. A tabela local que nasceu desta
passagem existe para ligá-los, e a seção 2 diz por que ela ficou local.

O achado maior não estava na medição: o selo de ativo/inativo desta tela é
**uma de três cópias divergentes** do mesmo componente. O coordenador confirmou
durante a passagem, com a `ProductsPage` fechando ao lado.

---

## Checklist da §29

```text
FUNCIONALIDADE (§29 do prompt mestre)
[x] carrega dados — o `useEffect` é o mesmo: `api.get("/products")` com o
    mesmo filtro por `is_active`, `getMyEquipment()` sem parâmetro, o mesmo
    `Promise.all` e o mesmo `.finally`. Nada de rede mudou.
[x] filtra / pagina — os três filtros, o reset de página ao trocar de filtro
    e o `Pagination` seguem idênticos; validados por mutação (M3, M5).
[ ] busca / ordena — não se aplica: a tela não tem busca nem ordenação.
[x] cria / edita / exclui — os três modais seguem chamando os mesmos três
    serviços com a mesma carga. O de exclusão foi validado por mutação (M8);
    os de criar e editar, só na parte de nome de campo (M9).
[ ] anexa — não se aplica.
[ ] respeita permissões — não reverificado: a tela não decide permissão, e
    nada disso foi tocado. Os três endpoints são `/equipment/my`.
[ ] mostra erro (rede) — **a tela engole a falha**. O `.catch(() => {})` da
    linha 347 não guarda nada, e uma rede caída cai no estado vazio, que diz
    "Nenhum equipamento cadastrado ainda." Defeito de produto pré-existente,
    contado na seção 4, não consertado aqui.
[x] mostra estado vazio — os DOIS: sem cadastro e sem resultado de filtro,
    com textos diferentes; validados por mutação (M10, M11).
[x] mostra loading — `Spinner` intacto, não tocado.
[ ] funciona no mobile — não reverificado visualmente (sem captura de tela).
    Nenhum breakpoint mudou. O selo de produto continua `hidden sm:inline-flex`
    — o `Badge` traz `inline-flex` próprio, e o `hidden` continua vencendo no
    base porque o Tailwind emite `.hidden` DEPOIS de `.inline-flex`
    (`tailwindcss/src/corePlugins.js:855`, conferido no node_modules, não
    suposto).
[x] funciona no tema escuro — é o ponto da fase: os pares
    `text-slate-X dark:text-slate-Y` saíram e os tokens resolvem por tema
    sozinhos no CSS. Não há mais como o claro e o escuro divergirem por
    esquecimento de um `dark:` — e era isso que tinha feito o ponto do selo
    daqui ganhar um `dark:bg-emerald-400` que a cópia da `ProductsPage` não
    tem.
[x] nenhum campo depende do placeholder — o campo de produto não tinha nome
    NENHUM (o `<label>` não tinha `htmlFor`, o `<select>` não tinha `id`).
    Agora tem, pelo primitivo; validado por mutação (M9).
[ ] toda barra desenhada tem papel declarado — não se aplica: a tela não
    desenha barra nem medidor.

ACRESCENTADOS PELAS DECISÕES REGISTRADAS
[x] estado interativo (visual = árvore) — a aba escolhida existia em
    `border-primary text-primary` e em mais nada. Ganhou `aria-pressed`;
    validado por mutação (M4). Os dois botões de ícone da linha ganharam
    `aria-label` com o NOME do equipamento — dez linhas davam dez botões
    chamados "Editar"; validado por mutação (M7).
[x] nenhuma ação só por mouse — todas as seis ações da tela são `<button>`
    ou `<Button>`. Não há `<div onClick>` nesta tela.
[x] nenhuma classe `text-slate-*` sem `dark:` correspondente — ZERADO: não
    há mais nenhuma classe `text-slate-*`, com ou sem par.
[x] nenhuma cor fora do sistema — ZERADO: 66 → 0 classes de paleta crua,
    0 hexadecimais, 1 → 0 cor cheia de significado como texto.
[x] `Alert` com `live={false}` — o aviso "Ação irreversível" já está na tela
    quando o modal abre: ele não é mudança, e como região viva assertiva
    atropelaria o anúncio do próprio diálogo. O `Alert` de erro de submissão,
    logo acima dele, continua vivo — esse muda.
[ ] foco alinhado ao outline do pacote — não alterado. O campo de produto
    herdou `focus:ring-action` do `Select` (era `focus:ring-primary` escrito
    à mão); os quatro `<button>` à mão continuam sem foco declarado — mesmo
    desvio F1 da `AuditLogsPage`, com prazo no Checkpoint 4.
[x] nenhum primitivo reinventado — o `KpiCard` LOCAL (homônimo do primitivo)
    saiu; o `<select>` com classe à mão virou `Select`; a caixa de aviso do
    modal de exclusão virou `Alert`; o selo virou `Badge`; os cinco `<svg>`
    viraram `Icon`. Restam quatro `<button>` à mão (seção 4).
[x] a catraca desceu — as duas entradas de par e a de cor cheia foram a zero
    (seção 6).
```

---

## 1. O que a tela tinha

1. **`IC`** (linhas 35-61) — objeto local com **5 `<svg>` soltos**: um chip,
   lápis, lixeira, mais, e o alfinete de mapa. Todos 24×24, `fill="none"`,
   `stroke="currentColor"` — mesma família do `Icon`, conferido antes de trocar.
2. **`ActivePill`** (linhas 87-100) — **16** classes de paleta crua, em
   `emerald` e `slate`, com **seis `dark:`** invertendo à mão o que o token
   inverte sozinho. É uma de três cópias divergentes (seção 2).
3. **`KpiCard` local** (linhas 104-111) — **homônimo do primitivo de
   `components/ui`**, e com a prop `accent?: string`: uma **classe crua** aberta
   por parâmetro. Foi por ela que `text-emerald-600 dark:text-emerald-400`
   entrou na tela sem passar por revisão nenhuma — exatamente o defeito que o
   comentário do primitivo registra como causa-raiz das três cópias anteriores.
4. **O `<select>` de produto** (linhas 146-156) — `<label>` sem `htmlFor`,
   `<select>` sem `id` (campo **sem nome acessível**) e nove classes à mão
   reproduzindo um campo de formulário, com `focus:ring-primary` — o degrau de
   marca, não o de ação.
5. **A caixa "Ação irreversível"** (linhas 263-269) — um `Alert` reinventado:
   12 classes cruas em `red`, ícone num círculo, título e corpo, sem papel de
   região viva declarado.
6. **`text-danger`** (linha 158) — a única cor cheia de significado como texto
   da tela, na mensagem de erro do campo de produto.
7. **As três abas escritas como três literais soltos** (linha 371), com o
   rótulo plural ("Ativos") num lugar e o rótulo singular do selo ("Ativo") em
   outro, sem nada dizendo que são a mesma coisa.
8. **Os dois botões de ícone da linha** (442-455) com `title` e sem
   `aria-label`: dez linhas na página davam dez controles chamados "Editar" e
   dez chamados "Excluir".

| medida | antes |
|---|---:|
| classes de paleta crua | **66** |
| `<svg>` soltos | **5** |
| hexadecimais cravados | 0 |
| cor cheia semântica como texto | **1** |
| primitivos reinventados localmente | **3** (`KpiCard`, campo, aviso) |
| campos sem nome acessível | **1** |

---

## 2. O que passou a usar

- **`Icon` de `components/ui`** — 7 usos, cobrindo os 5 `<svg>`. O casamento foi
  por traçado primeiro, `viewBox` e `fill` conferidos antes de trocar (os cinco
  eram 24×24, `fill="none"`, `stroke="currentColor"`):

  | era | virou | como casou |
  |---|---|---|
  | `Edit` | `edit` | traçado **idêntico**, caractere a caractere |
  | `Trash` | `trash` | traçado **idêntico** |
  | `Plus` | `plus` | traçado **idêntico** |
  | `MapPin` | `mapPin` | os **dois** traçados idênticos (gota + furo) — é o traçado múltiplo que a **E21** subiu |
  | `Cpu` | `cpu` | traçado diferente (`<rect>` + pernas retas contra contorno com cantos arredondados), **mesmo significado**: é o caso que a E21 chama de "o mesmo desenho com outro traço" |

- **`Badge` de `components/ui`** — 2 usos (o selo de estado e o selo de
  produto). Com ele vêm as sete variantes medidas pela **E8**: fundo na tinta,
  texto no par da tinta, borda a 30%. O selo de produto pintava
  `bg-primary/10 border-primary/20 text-primary/80` — tinta por opacidade, que
  a regra (b) do D8-a proíbe.
- **`KpiCard` de `components/ui`** — 3 usos, com `tone` em vez da prop de
  classe crua. A união é fechada: não há como passar uma classe.
- **`Select` de `components/ui`** — o campo de produto. O `<label>` passou a ter
  `htmlFor` (via `id="equipamento-produto"`), o anel de foco virou
  `focus:ring-action`, e a mensagem de erro virou `text-on-tint-danger` dentro
  do próprio primitivo — que é o que zera a cor cheia.
- **`Alert` de `components/ui`** — 4 usos, sendo 1 novo: a caixa "Ação
  irreversível", com `live={false}` pela **E12**.
- **A escada de texto do pacote** — `text-conteudo-heading` (título e nome do
  equipamento no modal), `text-conteudo` (dado), `text-conteudo-muted`
  (secundário), `text-conteudo-link` / `text-conteudo-link-hover` (as duas ações
  em texto).
- **`bg-fill-success` e `bg-borda-control`** no ponto do selo — forma, não
  texto. `--fill-*` é a candidata **E19**, e existe porque o degrau 500 da rampa
  reprova o piso de 3:1 no tema claro (`success` a 2,54).

### Por que a tabela de estado ficou local, e não virou módulo

Ela **não** é uma fonte única que falta em `src/lib/`. `is_active` não é status
de chamado, prioridade nem categoria: é um booleano de equipamento, e nenhum
outro arquivo do front precisa saber como ele se chama. `src/lib/**` está fora
do escopo do briefing, e o módulo teria um consumidor só — a mesma conclusão
que a `AuditLogsPage` registrou ontem para a tabela de ação de auditoria.

O que ela ganhou foi a **disciplina** dos módulos: rótulo singular e plural
declarados lado a lado, variante do `Badge` em vez de classe de cor, classes
escritas por extenso, acessor com nome (`estadoDe`), e as três abas de filtro
**derivadas** dela em vez de reescritas. Antes, "Ativo" (o selo) e "Ativos" (a
aba) eram dois literais sem relação; trocar um e esquecer o outro era possível.

### ⚠️ O selo é uma de TRÊS cópias divergentes — e isso NÃO se resolve aqui

O mesmo componente existe em três telas, em três formas:

| tela | forma | rótulos |
|---|---|---|
| `ProductsPage` | **botão** que alterna o estado | Ativo / Inativo |
| `EquipmentPage` (esta) | `<span>` que só mostra | Ativo / Inativo |
| `UsersPage` | `StatusPill`, **três** estados, mapa próprio | — |

E já tinham divergido em silêncio: a cópia daqui trazia um `dark:bg-emerald-400`
no ponto que a da `ProductsPage` não tem. Nada obriga três cópias a concordar.

O componente compartilhado **não nasce dentro de uma tela**: `components/ui`
está fora do escopo, e três agentes inventando três abstrações é o defeito que
esta migração existe para eliminar. Fica registrado, e é item da seção 7.

---

## 3. Mudanças visíveis, e de onde saem

Nenhuma é arbitrária, mas cinco precisam ser vistas antes de subir:

1. **Os três indicadores mudaram de caixa.** O cartão local era `p-4`,
   `text-2xl`, rótulo em cinza; o primitivo é `p-5`, `text-3xl`, rótulo em
   maiúsculas espaçadas e com um **filete de 4px à esquerda**. É o desenho que
   os três painéis já usam. O número de "Ativos" continua verde, agora em
   `--on-tint-success` (medido sobre superfície nua, entre 5,29:1 e 9,58:1) em
   vez de `emerald-600`.
2. **"Inativos" perdeu o cinza mais fraco.** O cartão local pintava o número
   com `text-slate-500` para rebaixá-lo; o primitivo não tem tom "apagado", e o
   tom `neutral` põe o número em `--text-heading`, igual ao de "Total". **O que
   se perde é ênfase decorativa, não informação** — o que o cartão conta está
   escrito no rótulo. É decisão de desenho, e está na seção 7.
3. **A caixa "Ação irreversível" trocou de ícone.** Era uma lixeira dentro de
   um círculo; o `Alert` da variante `danger` desenha o `error` (círculo com
   ×). A lixeira ali repetia a ação que o botão embaixo já nomeia; o círculo com
   × é o desenho que as outras telas usam para "isto é grave".
4. **A aba escolhida trocou de degrau.** Era `border-primary text-primary` — o
   degrau de MARCA, que sobre `--bg-base` dá 3,66:1 e reprova AA para texto.
   Virou `border-action text-conteudo-link`, que é o que a `GroupsPage` já
   usa nas duas tiras de aba dela.
5. **O campo de produto trocou de fundo.** Era `bg-surface-elevated` com anel
   `primary`; o `Select` é `bg-surface` com borda `borda-control` (a **E7**, que
   é a única borda de controle que passa os 3:1 da WCAG 1.4.11) e anel `action`.
   Os três campos do modal passam a ter o mesmo desenho.

E três que não mudam pixel, mas mudam o que um leitor de tela anuncia: as três
abas de filtro passaram a se declarar por `aria-pressed`, os dois botões de
ícone de cada linha passaram a dizer **de qual equipamento** são ("Editar
Detector 04"), e o campo de produto passou a ter nome.

---

## 4. A contagem do que resta à mão

Contar, não julgar:

- **0** classes de paleta crua do Tailwind (eram 66).
- **0** `<svg>` soltos (eram 5).
- **0** hexadecimais cravados.
- **0** cores cheias de significado como cor de texto (era 1).
- **0** campos sem nome acessível (era 1).
- **0** `<input>` e **0** `<select>` à mão.
- **4** `<button>` à mão, não pelo primitivo `Button`: a aba de filtro (uma no
  código, três na tela), o "Adicionar primeiro equipamento" do estado vazio, e
  os dois botões de ícone da linha. São controles de texto e de ícone, sem
  fundo; passá-los pelo `Button` mudaria padding e altura, o que é decisão de
  desenho e não troca de cor. Os quatro têm nome acessível e os quatro são
  alcançáveis pelo teclado.
- **1** tira de abas **sem o contrato de teclado** do `ui/Tabs`: as três são
  `<button>` em sequência, sem ←/→ nem tabulação móvel. Mesma escolha que a
  `GroupsPage` registrou — o `ui/Tabs` desenha uma tira de pílulas sobre
  `surface-elevated`, e trocar o desenho é decisão de desenho.
- **1** caminho de erro engolido: `.catch(() => {})` (linha 347). Rede caída cai
  no estado vazio, e a tela diz "Nenhum equipamento cadastrado ainda." para uma
  falha. Defeito de produto pré-existente.
- **1** paginação feita no cliente sobre a lista inteira do servidor:
  `getMyEquipment()` traz tudo e `PAGE_SIZE` fatia em memória. As contagens das
  abas e dos indicadores só fecham porque tudo está carregado. Pré-existente.
- **1** informação escondida no celular: o selo de produto é
  `hidden sm:inline-flex`, então abaixo de 640px a linha não diz a que produto o
  equipamento pertence. Pré-existente, não alterado.

---

## 5. O que não foi feito, e por quê

- **Não criei um componente compartilhado para o selo de ativo/inativo**, apesar
  de ele existir em três cópias divergentes. `components/ui/**` está fora do
  escopo do briefing, e a instrução do coordenador foi explícita: tokenizar a
  cópia local e registrar. Está na seção 7.
- **Não criei `lib/equipamento.ts`.** `src/lib/**` está fora do escopo, e a
  tabela tem um consumidor só (seção 2).
- **Não troquei a tira de abas pelo `ui/Tabs`** — muda o desenho, e o desenho
  não é meu para trocar. O ganho seria o contrato de teclado, que continua em
  aberto.
- **Não passei os quatro `<button>` pelo `Button`**, nem acrescentei `catch` na
  chamada de rede, nem mexi na paginação de cliente. Os três são eixos
  diferentes do que esta fase migra, e os dois últimos são defeito de produto.
- **Nenhuma captura de tela.** A verificação foi por leitura, `tsc`, `eslint`,
  os doze casos de teste com as doze mutações, e a varredura de contraste — não
  houve sessão de navegador nesta passagem.

---

## 6. Números

| medida | antes | depois |
|---|---:|---:|
| classes de paleta crua do Tailwind | 66 | **0** |
| `<svg>` soltos | 5 | **0** |
| hexadecimais cravados | 0 | 0 |
| cor cheia semântica como texto | 1 | **0** |
| linhas da `varredura-contraste.mjs` para esta tela | **3** (2 lugares) | **0** |
| entradas em `PARES_CONHECIDOS` para esta tela | 2 (`bg-surface`, `bg-surface-elevated`) | 0 |
| entrada em `CHEIAS_CONHECIDAS` | 1 | 0 |
| primitivos reinventados localmente | 3 | 0 |
| campos sem nome acessível | 1 | 0 |
| `<button>` à mão | 4 | 4 |
| linhas do arquivo | 482 | 549 |
| testes em `EquipmentPage.test.tsx` | — (não existia) | **12**, todos passando |
| mutações aplicadas e mortas | — | **12 de 12** |

As duas entradas da catraca eram, em detalhe:

```text
1,79:1  escuro  linha 386   text-slate-600 sobre bg-surface-elevated (ícone do vazio)
2,34:1  claro   linha 386   idem
3,36:1  escuro  linha 271   text-slate-500 sobre bg-surface (ícone do modal de exclusão)
```

O par claro da linha 271 passava (4,76:1, por causa do bloco de inversão D5) e
o escuro não — é o caso em que só metade do problema aparece, e a razão de a
varredura medir os dois temas.

Os substitutos foram medidos com os mesmos tokens do `colors.css`, e não
escolhidos pelo nome:

| par | claro | escuro |
|---|---:|---:|
| `--text-muted` sobre `--surface-elevated` | 6,92:1 | 5,29:1 |
| `--text-muted` sobre `--surface` | 7,58:1 | 6,23:1 |
| `--text-link` sobre `--surface-elevated` | 4,83:1 | 5,04:1 |

O `text-conteudo-faint` **não** foi usado em lugar nenhum: sobre a superfície
elevada ele dá 2,34:1 no claro, e a série do equipamento é dado, não decoração.

### As doze mutações

Todas mutam **o elemento ou o comportamento**, nunca a classe — o ambiente de
teste não aplica CSS, e classe trocada não move nada do que os casos medem.

Antes delas rodou um **controle sem mutação nenhuma**, e ele foi necessário: a
primeira execução do roteiro chamava `npx.cmd` pelo `execFileSync`, que o
`CreateProcess` do Windows não executa sem shell. As doze "sobreviveram" em 0
segundo, porque o vitest **nunca rodou**. O controle é o que separa "o teste não
pegou" de "o roteiro não mediu".

| # | mutação | casos que morreram |
|---|---|---:|
| M1 | a localização some da linha | 1 |
| M2 | o selo perde a palavra e fica só o ponto | 1 |
| M3 | toda aba conta o total, e não a sua fatia | 4 |
| M4 | a aba escolhida deixa de se declarar (`aria-pressed`) | 1 |
| M5 | o filtro "Inativos" deixa de filtrar | 1 |
| M6 | o indicador de "Ativos" conta o total | 1 |
| M7 | o botão de editar volta a se chamar só "Editar" | 1 |
| M8 | o aviso de exclusão perde o título | 1 |
| M9 | o campo de produto perde o nome | 1 |
| M10 | os dois vazios trocam de lugar | 2 |
| M11 | o convite de primeiro cadastro some | 1 |
| M12 | o produto inativo deixa de ser filtrado | 2 |

Cada um dos doze casos morreu para pelo menos uma mutação daquilo que ele
afirma proteger.

`npx tsc --noEmit -p tsconfig.app.json` e `npx eslint` não relatam nada para
`EquipmentPage.tsx` nem para o teste novo. A varredura de contraste não devolve
nenhuma linha com este caminho.

---

## 7. O que volta para o operador

**Decisão de desenho**

1. O componente compartilhado do selo **ativo/inativo**, hoje em três cópias
   divergentes (`ProductsPage`, esta, `UsersPage` como `StatusPill` de três
   estados). As três foram tokenizadas em separado; unificá-las é escrita em
   `components/ui`, e nenhum agente de tela pode fazê-la.
2. O número de **"Inativos"** deixou de ser cinza-fraco e ficou igual ao de
   "Total": o `KpiCard` do pacote não tem tom "apagado". Reverter exige um tom
   novo no primitivo — emenda, não conserto local.
3. O ícone do aviso de exclusão deixou de ser a **lixeira** e passou a ser o
   **`error`** do `Alert`.
4. Os três indicadores mudaram de caixa (filete à esquerda, `p-5`, `text-3xl`,
   rótulo em maiúsculas) por adotarem o primitivo.

**Mudança funcional**

5. As três abas de filtro passaram a anunciar-se como **botões de alternância**
   (`aria-pressed`). Nenhum pixel muda; o que muda é o que um leitor de tela
   diz. Se a preferência for a tira de abas WAI-ARIA de verdade, o caminho é o
   `ui/Tabs`, e aí o desenho muda.
6. Os dois botões de ícone de cada linha passaram a ter nome acessível com o
   **nome do equipamento** dentro. Antes, dez linhas davam dez botões de mesmo
   nome.

**Defeito de produto** — não é defeito de sistema de design e não se conserta
aqui:

7. `.catch(() => {})` na carga: **rede caída é indistinguível de lista vazia**,
   e a tela afirma "Nenhum equipamento cadastrado ainda." para uma falha.
8. **Paginação de cliente sobre a lista inteira**: `getMyEquipment()` traz tudo
   e a tela fatia em memória. As contagens das abas e dos indicadores dependem
   disso; no dia em que o endpoint paginar, os três números passam a mentir.
9. O **produto do equipamento some abaixo de 640px** (`hidden sm:inline-flex`),
   e no celular a linha não diz a que produto o equipamento pertence.
