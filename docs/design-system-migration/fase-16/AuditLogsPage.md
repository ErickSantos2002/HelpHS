# Fase 16 — `AuditLogsPage.tsx`

```text
Página: /auditoria — frontend/src/pages/audit/AuditLogsPage.tsx
Teste:  frontend/src/test/pages/AuditLogsPage.test.tsx (novo)
```

Esta tela entrou na fase com **146 classes de paleta crua em 351 linhas** — a
maior densidade do sistema, quase uma a cada duas linhas. O briefing suspeitava
de um mapa local de cor por tipo de ação de auditoria, e a suspeita estava
certa: `ACTION_BADGE`, dez linhas, dez matizes crus, um por ação. Ele sozinho
respondia por mais de metade da contagem.

---

## Checklist da §29

```text
FUNCIONALIDADE (§29 do prompt mestre)
[x] carrega dados — `getAuditLogs` inalterado: mesmos parâmetros, mesma
    montagem de `date_from`/`date_to`, mesmo `PAGE_SIZE`. Nada de rede mudou.
[x] filtra / busca / pagina — os cinco filtros, o `Pagination` e o reset de
    página ao trocar filtro seguem idênticos; "Limpar filtros" validado por
    mutação (M8).
[ ] ordena / cria / edita / exclui / anexa — não se aplica: a tela é leitura.
[x] abre detalhes — o `DetailModal` abre pelos dois botões "Ver detalhes" e
    pelo clique na linha do celular; validado por mutação (M1, M4).
[ ] respeita permissões — não reverificado: a tela não decide permissão
    (quem chega aqui já passou pelo guarda de rota), e nada disso foi tocado.
[ ] mostra erro (rede) — **a tela não tem tratamento de erro**. O `.finally`
    desliga o `loading` e a promessa rejeitada não tem `catch`: uma falha de
    rede cai no estado vazio, indistinguível de "nenhum registro". Defeito de
    produto pré-existente, contado abaixo, não consertado aqui.
[x] mostra estado vazio — "Nenhum registro encontrado." condicionado a
    `logs.length === 0`; validado por mutação (M7).
[x] mostra loading — `Spinner` intacto, não tocado.
[ ] funciona no mobile — não reverificado visualmente (sem captura de tela).
    Nenhuma classe de layout ou breakpoint mudou; a única mudança de caixa é
    o `<div>` de largura em volta de cada campo de data (ver seção 3).
[x] funciona no tema escuro — é o ponto da fase: os 25 pares
    `text-slate-X dark:text-slate-Y` saíram e os tokens resolvem por tema
    sozinhos no CSS. Não há mais como o claro e o escuro divergirem por
    esquecimento de um `dark:`.
[x] nenhum campo depende do placeholder — CORRIGIDO nesta passagem: a busca
    só se nomeava pelo `placeholder`, que some na primeira letra digitada.
    Ganhou `aria-label`; validado por mutação (M6).
[ ] toda barra desenhada tem papel declarado — não se aplica: a tela não
    desenha barra nem medidor.

ACRESCENTADOS PELAS DECISÕES REGISTRADAS
[x] estado interativo (visual = árvore) — os dois botões "Ver detalhes"
    passaram a ter `aria-label`, e não mais só `title`.
[ ] nenhuma ação só por mouse — NÃO verificado como aprovação: a linha do
    celular é um `<div onClick>` sem `tabIndex` nem `onKeyDown` (linha 389).
    Não é uma ação inalcançável — o botão "Ver detalhes" dentro dela faz o
    mesmo e está no foco —, mas o `<div>` continua sendo uma superfície de
    clique só de mouse. Pré-existente, contado abaixo.
[x] nenhuma classe `text-slate-*` sem `dark:` correspondente — ZERADO: não
    há mais nenhuma classe `text-slate-*`, com ou sem par.
[x] nenhuma cor fora do sistema — ZERADO: 146 → 0 classes de paleta crua,
    0 hexadecimais, 0 cores cheias de significado como texto.
[ ] `Alert` com `live={false}` — não se aplica: a tela não usa `Alert`.
[ ] foco alinhado ao outline do pacote — não alterado. Os campos herdam o
    `focus:ring-action` do `Input` (era `focus:ring-primary` escrito à mão
    nas datas); os quatro `<button>` à mão continuam sem foco declarado —
    desvio F1, com prazo no Checkpoint 4.
[x] nenhum primitivo reinventado — os dois `<input type="date">` à mão
    passaram para o `Input`; os selos passaram para o `Badge`; os sete
    `<svg>` para o `Icon`. Restam quatro `<button>` à mão (seção 4).
[x] a catraca desceu — as três entradas desta tela foram a zero (seção 6).
```

---

## 1. O que a tela tinha

1. **`ACTION_BADGE`** (linhas 35-46) — mapa local de **dez** matizes crus do
   Tailwind, um por ação de auditoria: `emerald`, `blue`, `red`, `slate`,
   `yellow`, `cyan`, `orange`, `pink`, `purple`, mais `primary/10` no `login`.
   Cada linha escrevia seis classes (fundo, texto, borda, e as três de novo com
   `dark:`), nenhuma delas medida contra superfície nenhuma. Só esta tabela
   somava **54** classes de paleta crua.
2. **A mesma tabela repetida como recuo** (linhas 82 e 270) — o objeto
   `{ label: log.action, cls: "bg-slate-100 …" }` estava escrito **duas vezes**,
   literalmente idêntico, uma para o modal e outra para a lista.
3. **`ACTION_OPTIONS`** (linhas 13-24) — segunda tabela para o mesmo dado, e as
   duas **já discordavam**: o filtro dizia "Mudança de status" e "Troca de
   senha"; o selo dizia "Status" e "Senha". Nenhuma regra dizia qual valia onde.
4. **`ENTITY_OPTIONS` + `ENTITY_LABEL`** (linhas 26-51) — as mesmas seis chaves
   e os mesmos seis rótulos escritos duas vezes.
5. **`IC`** (linhas 55-63) — objeto local com **7 `<svg>` soltos**: busca, X,
   funil, relógio, usuário, olho e um globo. O globo **nunca era usado** —
   código morto desde algum recorte anterior.
6. **`dateInputCls`** (linha 194) — string de classe à mão reproduzindo um campo
   de formulário: borda, fundo, padding, cor de texto com `dark:`, anel de foco
   em `primary`. Um `Input` reinventado, e divergente do `Input` de verdade que
   a busca logo abaixo já usava (fundo elevado contra `surface`, anel em
   `primary` contra `action`).
7. **Os dois blocos de JSON do modal** (linhas 135 e 143) — `text-red-600
   bg-red-50 border-red-200 dark:text-red-300/80 …` e o par em `emerald`: 12
   classes cruas, e cor de significado carregada por degrau da rampa.
8. **25 pares `text-slate-X dark:text-slate-Y`** e **12 `text-slate-X` sem par**
   espalhados por toda a tela, em quatro degraus de cinza (700/200, 600/300,
   500/400, 400/600) sem regra distinguindo-os.
9. **Nenhum nome acessível** nos dois campos de data (o "De" e o "até" ao lado
   são `<span>`, não `<label>`) nem na busca (só `placeholder`).

| medida | antes |
|---|---:|
| classes de paleta crua | **146** |
| `<svg>` soltos | **7** |
| hexadecimais cravados | 0 |
| cor cheia semântica como texto | 0 |
| tabelas locais para dados duplicados | **4** (ação ×2, entidade ×2) |

---

## 2. O que passou a usar

- **`Badge` de `components/ui`** — 3 usos (modal, lista do celular, lista de
  mesa). Com ele vêm as sete variantes medidas pela **E8**: fundo na tinta,
  texto no par da tinta, borda a 30%. As dez matizes cruas saíram inteiras.
- **`Icon` de `components/ui`** — 10 usos, cobrindo os 7 `<svg>`. O casamento
  foi por traçado primeiro, `viewBox` conferido antes de trocar (todos os sete
  eram 24×24, `fill="none"`, `stroke="currentColor"` — mesma família do `Icon`):

  | era | virou | como casou |
  |---|---|---|
  | `Search` | `search` | traçado **idêntico**, caractere a caractere |
  | `X` | `close` | traçado **idêntico** |
  | `User` | `user` | traçado **idêntico** |
  | `Eye` | `eye` | os **dois** traçados idênticos (pupila + contorno) |
  | `Globe` | `globe` | traçado idêntico — mas era código morto, **removido** |
  | `Clock` | `clock` | traçado diferente (`<circle>` + ponteiros contra arco único), **mesmo significado** — é o caso que a E21 chama de "o mesmo desenho com outro traço" |
  | `Filter` | `filter` | traçado diferente no cálculo do funil, **mesmo significado** |

- **`Input` de `components/ui`** — os dois campos de data deixaram de ser
  `<input>` com classe à mão. Com isso o anel de foco virou `focus:ring-action`
  (o degrau de ação) em vez de `focus:ring-primary` (o degrau de marca), e os
  três campos do painel de filtro passaram a ter o mesmo desenho.
- **A escada de texto do pacote** — `text-conteudo-heading` (título),
  `text-conteudo` (dado), `text-conteudo-muted` (secundário),
  `text-conteudo-link` / `text-conteudo-link-hover` (as duas ações em texto).
- **`bg-tint-danger` + `text-on-tint-danger`** e o par em `success` nos dois
  blocos de JSON — a mesma receita que o `Badge` usa, e não a cor cheia.
- **Uma tabela local por dado, e as listas derivadas dela** — `ACAO` (rótulo,
  forma curta, variante) e `ENTIDADE` (rótulo). `ACTION_OPTIONS` e
  `ENTITY_OPTIONS` agora saem delas por `map`; acrescentar uma ação num lugar e
  esquecê-la no outro deixou de ser possível.

A tabela é **exportada** da tela — só para que o teste a compare literal. Isso
liga o `react-refresh/only-export-components`, silenciado na linha, com o motivo
escrito ao lado: o remédio da regra é arquivo próprio, e arquivo próprio está
fora do escopo desta fase. Quando a tabela virar módulo, o silêncio sai com ela.

### Por que a tabela de ação ficou local, e não virou módulo

Ela **não** é uma fonte única que falta em `src/lib/`. Ação de auditoria não é
status, prioridade nem categoria: é dado desta tela e só desta — nenhum outro
arquivo do front lê `AuditAction`. Criar `lib/auditoria.ts` seria escrita fora
do escopo do briefing, e o módulo teria um consumidor só. O que ela ganhou foi
a **disciplina** dos módulos: rótulo longo e forma curta declarados lado a lado,
variante em vez de classe, acessores com recuo para o neutro, e as listas de
filtro derivadas em vez de reescritas.

---

## 3. Mudanças visíveis, e de onde saem

Nenhuma é arbitrária, mas três precisam ser vistas antes de subir:

1. **Os selos perderam nove matizes.** Dez cores cruas viraram seis variantes do
   `Badge`, agrupadas pelo que o evento significa para quem audita:
   `danger` (exclusão, anonimização), `warning` (exportação, troca de senha),
   `info` (atualização, atribuição, mudança de status), `success` (criação),
   `primary` (login), `muted` (logout). **O agrupamento é decisão de desenho —
   está na seção 5 e no relato ao operador.** O rótulo continua escrito dentro
   de cada selo, então a informação não depende da cor (é o mesmo argumento que
   `lib/status.ts` registra para os dois "aguardando").
2. **O modal passou a dizer o nome por extenso.** Onde as duas tabelas
   discordavam, a divergência virou regra: a lista mostra a forma curta
   ("Status", "Senha") porque a coluna tem 110px; o modal, que não tem essa
   restrição, mostra "Mudança de status" e "Troca de senha" — as mesmas palavras
   que o filtro sempre ofereceu. Antes o modal dizia "Status" e o filtro dizia
   "Mudança de status", sem regra.
3. **O cinza mais fraco subiu um degrau.** Os quatro degraus de cinza viraram
   três: `text-slate-400 dark:text-slate-600` (os UUIDs em `font-mono`, o IP
   secundário) foi para `text-conteudo-muted`, e não para `text-conteudo-faint`,
   porque `faint` sobre a superfície elevada dá **2,34:1** no claro e **2,85:1**
   no escuro — não é par, e um UUID é dado, não decoração. Os UUIDs ficam
   visivelmente mais legíveis.

E duas que não mudam pixel, mas mudam o que um leitor de tela anuncia: os dois
campos de data ganharam `aria-label` ("Data inicial", "Data final") e a busca
ganhou o dela ("Buscar por User ID"). Antes, os três eram campos sem nome — o
"De" e o "até" nunca foram `<label>` de coisa alguma.

---

## 4. A contagem do que resta à mão

Contar, não julgar:

- **0** classes de paleta crua do Tailwind (eram 146).
- **0** `<svg>` soltos (eram 7).
- **0** hexadecimais cravados.
- **0** cores cheias de significado como cor de texto.
- **0** `<input>` à mão.
- **4** `<button>` à mão, não pelo primitivo `Button`: dois "Limpar filtros" (o
  do cabeçalho do filtro e o do estado vazio) e dois "Ver detalhes" (celular e
  mesa). São controles de texto e de ícone, sem fundo; passá-los pelo `Button`
  mudaria padding e altura em quatro lugares, o que é decisão de desenho e não
  troca de cor. Todos têm nome acessível e todos são alcançáveis pelo teclado.
- **1** `<div onClick>` sem teclado (linha 389, a linha inteira do celular). A
  ação não fica inalcançável — o botão "Ver detalhes" dentro dela faz o mesmo e
  está na ordem de foco —, mas a superfície de clique em si é só de mouse.
- **1** caminho de erro ausente: `getAuditLogs(...).then(...).finally(...)` sem
  `catch`. Rede caída cai no estado vazio, e a tela diz "Nenhum registro
  encontrado." para uma falha. Defeito de produto pré-existente.

---

## 5. O que não foi feito, e por quê

- **Não criei `lib/auditoria.ts`.** `src/lib/**` está fora do escopo do briefing,
  e a tabela tem um consumidor só (ver seção 2). Se algum dia um relatório
  passar a mostrar ação de auditoria, é ali que ela vira módulo.
- **Não troquei `FilterSelect` pelo `Selector`.** O invólucro é `@deprecated` e
  a chamada nova deveria usar o `Selector` direto — mas **nenhuma das oito
  telas** que usam `FilterSelect` migrou ainda, e o próprio componente registra
  que o nome sai "quando a última sair". Migrar esta tela sozinha a poria fora
  de passo com as outras sete sem fechar nada.
- **Não passei os quatro `<button>` pelo `Button`**, nem dei teclado ao `<div>`
  da linha do celular, nem acrescentei `catch` na chamada de rede. Os três são
  eixos diferentes do que esta fase migra, e o último é defeito de produto.
- **Nenhuma captura de tela.** A verificação foi por leitura, `tsc`, `eslint`,
  os dez casos de teste com as dez mutações, e a varredura de contraste — não
  houve sessão de navegador nesta passagem.
- **O agrupamento das dez ações em seis variantes não foi decidido por mim como
  fato consumado**: fiz a escolha menos surpreendente para que a tela fechasse
  em zero paleta crua, mas ela está relatada ao operador como decisão de
  desenho. Reverter é trocar seis palavras na tabela `ACAO`.

---

## 6. Números

| medida | antes | depois |
|---|---:|---:|
| classes de paleta crua do Tailwind | 146 | **0** |
| `<svg>` soltos | 7 | **0** |
| hexadecimais cravados | 0 | 0 |
| cor cheia semântica como texto | 0 | 0 |
| linhas da `varredura-contraste.mjs` para esta tela | **5** (3 lugares) | **0** |
| entradas em `PARES_CONHECIDOS` para esta tela | 3 (`bg-surface-elevated` ×2, `hover:bg-surface-elevated` ×1) | 0 |
| tabelas locais duplicando o mesmo dado | 4 | 0 |
| `<input>` à mão | 2 | 0 |
| `<button>` à mão | 4 | 4 |
| campos sem nome acessível | 3 | 0 |
| testes em `AuditLogsPage.test.tsx` | — (não existia) | **13**, todos passando |
| mutações aplicadas e mortas | — | **16 de 16** |

As três entradas da catraca eram, em detalhe:

```text
1,79:1  escuro  linha 261   text-slate-600 sobre bg-surface-elevated (ícone do vazio)
2,34:1  claro   linha 261   idem
2,34:1  claro   linha 329   text-slate-400 sobre hover:bg-surface-elevated (botão do olho)
2,85:1  escuro  linha 205   text-slate-500 sobre bg-surface-elevated (chip de contagem)
4,34:1  claro   linha 205   idem
```

Os substitutos foram medidos com o próprio script, e não escolhidos pelo nome:
`--text-muted` sobre `--surface-elevated` dá **6,92:1** no claro e **5,29:1** no
escuro; `--text-link` sobre a mesma superfície dá **4,83:1** e **5,04:1**. O
`text-primary` que o botão do olho usaria por inércia daria **3,49:1** e
**3,54:1** — reprovaria; por isso o degrau de link, e não o de marca.

### As dez mutações

Todas mutam **o elemento ou o comportamento**, nunca a classe — o ambiente de
teste não aplica CSS, e classe trocada não move nada do que os casos medem.

| # | mutação | casos que morreram |
|---|---|---:|
| M1 | selo renderiza `null` no lugar do rótulo | 3 |
| M2 | `ACAO[a].curto` sem o recuo `?? a` | 1 |
| M3 | entidade desconhecida vira "—" em vez do valor cru | 1 |
| M4 | modal usa a forma curta, como a lista | 1 |
| M5 | campo de data inicial perde o `aria-label` | 1 |
| M6 | busca perde o `aria-label` | 2 |
| M7 | estado vazio perde o `<p>` de aviso | 1 |
| M8 | "Limpar filtros" deixa de limpar a busca | 1 |
| M9 | contagem desloca em um | 2 |
| M10 | plural invertido no chip de contagem | 2 |

Cada um dos dez casos morreu para pelo menos uma mutação daquilo que ele
afirma proteger.

### A segunda rodada, e o buraco que ela fechou

A conferência independente rodou duas mutações de comportamento que
**sobreviveram** às dez acima, e as duas caíam exatamente sobre o que esta ficha
devolve ao operador:

1. `delete.variante`: `"danger"` → `"muted"` — a exclusão deixa de ser grave, e
   nenhum caso reprovava.
2. `create.rotulo`: `"Criação"` → `"xxx"` — o nome longo vira lixo, e nenhum caso
   reprovava, porque nenhum caso abria o modal de uma ação `create`.

As dez mutações originais não estavam erradas: elas matavam o que os dez casos
afirmavam. O defeito era outro — **os casos não afirmavam o agrupamento nem a
regra dos dois rótulos**. Uma decisão de desenho que o operador vai aprovar
precisa de um caso que a prenda, senão o registro nesta ficha vira ficção na
primeira edição distraída.

Três casos novos, e `ACAO` passou a ser exportada da tela para que o primeiro
possa compará-la por igualdade — literal, e não derivada, pelo mesmo motivo que
`SLOT_DE_STATUS` é comparada literal em `test/lib/status.test.ts`: **nada no
código deduz este agrupamento**.

| # | mutação (sempre de **valor**, nunca de nome de símbolo) | casos que morreram |
|---|---|---:|
| N1 | `delete.variante` `danger` → `muted` | 2 |
| N2 | `create.rotulo` → `"xxx"` | 1 |
| N3 | `password_change.variante` `warning` → `info` | 2 |
| N4 | modal usa a forma curta, como a lista | 2 |
| N5 | `status_change.curto` vira igual ao `rotulo` | 2 |
| N6 | `anonymize.variante` `danger` → `warning` | 2 |

N5 é o caso instrutivo: ele **não** mata "onde as duas formas diferem…", porque
esse caso percorre a tabela e `password_change` continua divergindo — a lista de
divergentes só encolhe. Quem o mata é a comparação literal. Os dois casos se
cobrem em direções diferentes, e nenhum dos dois substitui o outro.

Mutar **valor** e não nome de símbolo é o que separa esta rodada de um
no-op: renomear uma chave em todo o arquivo renomeia o consumidor junto, o caso
continua passando, e o mutante sobrevive por um motivo que não tem relação
nenhuma com o que o caso mede.

`npx tsc --noEmit -p tsconfig.app.json` e `npx eslint` não relatam nada para
`AuditLogsPage.tsx` nem para o teste novo.
