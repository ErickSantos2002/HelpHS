# Fase 16 — `SlaConfigPage`

Página: `/sla-config` (só `admin`, pelo `RoleGuard` do `App.tsx`)
— `frontend/src/pages/sla/SlaConfigPage.tsx`

Pequena — 331 linhas antes e depois — e com o defeito mais caro do lote: os
**três mapas locais de prioridade** de uma tela que existe justamente para
configurar prioridade, e o rótulo deles no **masculino**, contra o feminino que
a emenda E17 fixou. Zero gráfico, zero hexadecimal, e **nunca apareceu na
catraca de contraste** — as 71 classes de paleta crua passavam por baixo dela.

## Ficha da §29

```text
Página: /sla-config — src/pages/sla/SlaConfigPage.tsx

FUNCIONALIDADE
[x] carrega dados      — `getSLAConfigs`: mesmo método, URL e params de antes
[–] filtra               — a tela não tem filtro
[–] busca                — a tela não tem busca
[–] pagina               — são quatro linhas, sempre; não há paginação
[x] ordena               — por urgência. A ordem saía do `LEVEL_ORDER` local e
                          passa a sair do campo `ordem` do módulo; o resultado
                          é o mesmo, e agora o desconhecido tem lugar (fim)
[–] cria                 — SLA não se cria pela interface: os quatro níveis são
                          semeados pelo backend
[x] edita                — `updateSLAConfig` pelo modal, inalterado
[–] exclui
[–] abre detalhes        — a linha já mostra tudo que existe
[–] anexa/remove arquivo
[x] respeita permissões — a rota é do `RoleGuard` (`admin`); a tela não
                          ramifica por papel, e nada disso mudou
[x] mostra erro          — dois `Alert variant="danger"`: falha de carga e
                          falha de gravação. Os dois são MONTADOS por um
                          evento, então `live` fica no padrão `true` — é
                          mudança, e região viva anuncia mudança
[ ] mostra estado vazio — **NÃO fecha**: `configs = []` desenha um cartão com
                          cabeçalho e nada embaixo. Pré-existente; ver "O que
                          não fiz"
[x] mostra loading       — `Spinner size="lg"`, inalterado
[x] funciona no mobile   — a data de atualização segue `hidden md:block`; nada
                          mais depende de largura
[x] funciona no tema escuro — zero par `text-slate-* dark:text-slate-*` (eram
                          12) e zero `dark:` no arquivo (eram 28)
[x] nenhum campo depende do placeholder — os três `Input` do modal já vinham
                          com `label`
[ ] barras desenhadas    — a tela TEM uma, e ela não tem nome nem legenda; ver
                          "O que volta para o operador"

ACRESCENTADOS PELAS DECISÕES
[x] o que a interface MOSTRA é o que a árvore DIZ, por estado
    repouso    ok — o único controle só de ícone ganhou nome acessível
    hover      `hover:text-conteudo-link` + `hover:bg-action-tint`, mesmo
               efeito visual de antes, agora por token
    modal      `role="dialog"` + `aria-labelledby` vêm do `ui/Modal`
[x] nenhuma ação só de mouse — o único `onClick` é de `<button>`; nenhum
    `focus:outline-none` sem substituto foi introduzido
[x] nenhum `text-slate-*` sem `dark:` — zero `slate-*`, `red-*`, `orange-*` e
    `yellow-*` restantes (eram 71)
[x] nenhuma cor fora do sistema — zero hexadecimal (já eram zero), zero cor
    cheia semântica como texto (já eram zero), zero paleta crua
[x] `Alert` já montado leva `live={false}` — nenhum dos dois já está montado
[–] desvio F1 — a tela não tem `focus:outline-none`
[x] nenhum primitivo reinventado — o selo à mão virou `Badge`, os 5 `<svg>`
    viraram `Icon`, e os três mapas viraram `lib/prioridade.ts`
[x] a catraca desceu — a tela não tinha lugar nela, e continua sem
```

## O que a tela tinha

- **Três mapas locais de prioridade**, chamando-a de "nível":
  - `LEVEL_LABEL` — o **décimo primeiro** mapa de rótulo de prioridade da base,
    e no **masculino**: `"Crítico"`, `"Alto"`, `"Médio"`, `"Baixo"`. A emenda
    E17 fixou o feminino, que concorda com "prioridade";
  - `LEVEL_STYLE` — três classes por nível (`badge`, `bar`, `dot`), num
    esquema de cor que não batia com nenhuma outra tela: vermelho, laranja,
    amarelo e cinza da paleta crua, cada um com `dark:` escrito à mão. São
    **12 strings** e **36 das 71** classes cruas do arquivo;
  - `LEVEL_ORDER` — a ordem de urgência repetida à mão, e ordenada por
    `indexOf`: um nível que o backend passasse a mandar devolveria `-1` e
    apareceria **no topo**, como se fosse mais urgente que "crítica".
- **71 classes de paleta crua do Tailwind** em 331 linhas, em quatro famílias:
  `slate-*` (44 usos, 35 deles a escada de texto reimplementada à mão em 12
  pares `text-slate-N dark:text-slate-M`), `red-*`, `orange-*` e `yellow-*`
  (27, todas dentro do `LEVEL_STYLE`).
- **5 `<svg>` soltos**, num objeto `IC` de elementos prontos.
- **`hover:text-primary` e `hover:bg-primary/10`** no botão de editar —
  `--color-primary-500` é o degrau de marca, não o de ação.
- **`text-slate-500 dark:text-slate-600`** na data de atualização: o par
  ESCURECE no tema escuro. É o mesmo defeito que a catraca pegou no
  `GroupsPage`, aqui sem chegar a ser medido porque nada nele é hover.
- **Quatro botões de editar com o mesmo nome.** Só ícone, `Icon` é
  `aria-hidden`, e o único texto era `title="Editar"` — quem usa leitor de tela
  ouvia "Editar" quatro vezes, sem como saber qual linha.
- **Nenhum gráfico, nenhum `useTheme()`, nenhum hexadecimal.** Não havia
  import de tema para remover, e `lib/grafico.ts`, `SLOT_DE_STATUS` e
  `COR_SERIE_TEMPORAL` não têm o que fazer aqui.

## O que passou a usar

- **`lib/prioridade.ts`** nos três mapas, em 5 pontos de consumo:
  `rotuloDePrioridade` (selo da linha, selo do modal, título do modal, nome
  acessível do botão), `varianteDePrioridade` (o selo e a barra),
  `TOM_PRIORIDADE` (o ponto e o preenchimento da barra) e
  `PRIORIDADE`/`PRIORIDADES` (a ordem, com recuo).
  A troca de `LEVEL_LABEL` pelo módulo é **mudança de texto visível**: a tela
  dizia "Crítico/Alto/Médio/Baixo" e passa a dizer "Crítica/Alta/Média/Baixa".
- **`Badge` de `components/ui`** nos dois selos, num `PrioridadeChip` local de
  6 linhas que é o `Badge` com o ponto dentro. Não é o `PriorityBadge` porque
  este desenho leva o ponto colorido junto — e é o rótulo ao lado que faz a cor
  ser reforço, e não o único portador, que é a regra que o próprio módulo
  documenta.
- **`Icon` de `components/ui`** nos 5 `<svg>`, 5 usos. Todos são
  `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`,
  `strokeWidth={2}`, `w-4 h-4` — mesma família do `Icon`, nenhum sólido:
  - `shield`, `bell` e `edit` bateram **caractere a caractere** com o
    `ICON_PATHS` do pacote;
  - o relógio é **outro relógio**: `<circle r="10">` mais os dois ponteiros
    (`M12 6v6l4 2`), contra o traçado único do pacote (`M12 8v4l3 3m6-3a9 9…`).
    Mesmo significado, traço diferente — unificado com `clock`, que é o caso
    que a E21 mediu;
  - o "i" em círculo é **outro "i" em círculo**: a mesma haste
    (`M13 16h-1v-4h-1m1-4h.01`) com o círculo desenhado por `M12 2a10 10…` em
    vez de `M21 12a9 9 0 11-18 0…`. Unificado com `info`.
- **A escada de texto** — `text-conteudo-heading` (o `h1`, o título do cartão e
  os três números de cada linha, que são o dado), `text-conteudo` (o corpo do
  cartão "Como funciona" e os quatro termos em destaque dentro dele) e
  `text-conteudo-muted` (subtítulos, rótulos de 10px, ícones e a data).
  `text-conteudo-faint` não entrou em lugar nenhum: a regra 4 do briefing o
  mede em 2,34:1 sobre `--surface-elevated`, e a linha tem hover justamente
  para essa superfície.
- **O degrau de ação** no botão de editar: `hover:text-conteudo-link` (o degrau
  de LINK, 5,05:1 no claro contra os 3,66:1 do `text-primary` que estava lá) e
  `hover:bg-action-tint` no lugar de `bg-primary/10`.
- **`aria-label`** no botão de editar, com a prioridade dentro:
  `Editar SLA da prioridade Crítica`. Os quatro passam a ter nome próprio.
  O `title="Editar"` ficou, para a dica de mouse.

## Os números

| | antes | depois |
|---|---:|---:|
| linhas da varredura de contraste para este arquivo | 0 | 0 |
| paleta crua do Tailwind, fora de comentário | 71 | 0 |
| `<svg>` soltos | 5 | 0 |
| hexadecimal cravado | 0 | 0 |
| cor cheia semântica como texto | 0 | 0 |
| mapas locais de prioridade | 3 | 0 |
| botões só de ícone sem nome acessível | 4 | 0 |
| linhas do arquivo | 331 | 331 |
| testes | 0 | 8 |

Os **8 casos são novos** — não havia teste desta tela — e passaram todos na
primeira execução, então os 8 foram validados por mutação no arquivo da tela,
uma por vez, restaurando de cópia em `finally` (nunca por `git`). As 8
mutações morreram:

| mutação | quem reprovou |
|---|---|
| o selo escreve `level` cru no lugar de `rotuloDePrioridade` | os 3 casos de rótulo e ordem |
| a tela deixa de ordenar (comparador vira `() => 0`) | os 2 casos de ordem |
| o recuo da ordem vira `?? -1` (desconhecido no topo) | só o caso da prioridade desconhecida |
| o botão de editar perde o `aria-label` | os 3 casos que alcançam a linha pelo nome |
| editar abre sempre `configs[0]` | o caso do modal e o de salvar |
| `handleSaved` deixa de trocar a linha (`(prev) => prev`) | só o caso de salvar |
| `formatHours` engole o resto (`1d 4h` vira `1d`) | só o caso do formato |
| a falha de carga chama `setError(null)` | só o caso do aviso |

`npx vitest run src/test/pages/SlaConfigPage.test.tsx` (8 passando),
`npx tsc --noEmit -p tsconfig.app.json` (sem erro), `npx eslint` nos dois
arquivos (sem achado) e a varredura de contraste sem uma linha sequer deste
arquivo — antes e depois.

## A contagem do que resta à mão

```text
src/pages/sla/SlaConfigPage.tsx: 0 <svg> soltos
                                 0 cores cruas
                                 1 <button> à mão
                                 0 <input> à mão
                                 1 barra desenhada sem nome
```

**Contar, não julgar:**

- **1 `<button>` à mão** — o de editar, só ícone, 28px. `Button variant="ghost"`
  o cobriria, mas mudaria espaçamento e raio dentro de uma linha de 4px de
  respiro; não é troca de token. Tem nome acessível, `type="button"` e o par de
  tinta do sistema.
- **1 barra desenhada** — a de `response/resolve`. Continua sem `role` e sem
  nome; ganhou `aria-hidden="true"` explícito, que **não muda o que a árvore de
  acessibilidade diz** (um `<div>` vazio já não dizia nada) e registra no
  código que ela é decorativa. Os dois números que ela compara estão escritos
  logo abaixo dela, em texto. O que ela mede não está escrito em lugar nenhum —
  ver a seção do operador.
- Os dois `Button` do modal, os três `Input`, o `Modal`, o `Card`, o `Spinner`
  e os dois `Alert` são todos primitivos do pacote, e já eram.

## O que não fiz, e por quê

- **Não mexi no `opacity-60` da barra.** Os `--fill-*` da E19 são medidos a
  100%, e 60% derruba o número — mas tirar a opacidade muda a hierarquia
  visual da linha, que é desenho. Mesma escolha, e mesma razão, do
  `opacity-60` que ficou no `GroupsPage`. Fica anotado.
- **Não escrevi estado vazio.** Com `configs = []` a tela desenha o cartão
  "Níveis de SLA" com o cabeçalho e nada embaixo. É pré-existente, e escrever a
  frase que aparece ali é decisão de texto — ainda mais numa tela cujo vazio só
  acontece se a semente do backend falhar, que é outro problema.
- **Não troquei o `Badge` por `PriorityBadge`.** O `PriorityBadge` desenha só o
  rótulo, e este desenho tem o ponto colorido junto; usar o `Badge` com o ponto
  dentro preserva a tela e continua consumindo o módulo. Trocar tiraria o ponto
  dos dois selos — mudança visual sem ganho.
- **Não toquei no `SlaChip`, e ele não se aplica aqui.** Ele é o chip de
  **prazo** de um chamado: recebe `dueAt`, `breached` e `respondedAt`, conta o
  tempo que falta e diz "Vencido" ou "Respondido". Esta tela configura
  **durações** (4h, 1d 4h), não prazos, e não tem chamado nenhum na mão. A
  tela não reinventa nada dele.
- **Não criei nenhum token, primitivo ou entrada de módulo.** Tudo que a tela
  precisava já existia: os quatro rótulos e as quatro variantes em
  `lib/prioridade.ts`, os cinco traçados no `Icon` da E20/E21, a escada de
  texto, o degrau de ação e as tintas. **Nada faltou no pacote.**
- **Não toquei nenhum arquivo de outro agente.** `EquipmentPage.tsx`,
  `ProfilePage.tsx` e `UsersPage.tsx` aparecem modificados na árvore
  compartilhada; são de outras sessões.

## O que volta para o operador

1. **Mudança de texto visível: o masculino vira feminino.** "Crítico", "Alto",
   "Médio" e "Baixo" passam a "Crítica", "Alta", "Média" e "Baixa", em toda a
   tela — as quatro linhas, o selo do modal e o título do modal. É o que a E17
   decidiu, e é o que o resto do sistema já diz; fica registrado porque quem
   usa a tela vê palavra diferente.
2. **Mudança de texto visível: o selo do modal perde a palavra "Nível".** Ele
   dizia `Nível Crítico`; "Nível Crítica" não concorda, e prefixar qualquer
   outro substantivo seria escrever um rótulo novo. O selo passa a dizer o que
   o módulo diz, e nada mais: `Crítica`. É a mesma frase do selo da linha.
3. **A tela chama de "nível" o que o resto do sistema chama de "prioridade".**
   O backend manda os mesmos quatro valores (`critical`/`high`/`medium`/`low`)
   que o chamado usa. Os títulos ("Níveis de SLA", "por nível de prioridade")
   ficaram como estavam — renomear é decisão de vocabulário do produto.
4. **A barra de progresso não diz o que mede.** Ela desenha
   `resposta ÷ resolução × 100` — a fatia da janela de resolução que o prazo de
   resposta ocupa —, sem rótulo, sem legenda e sem escala. Não dá para nomeá-la
   sem primeiro decidir o que ela deveria comunicar, e por isso ela **não**
   ganhou `role="progressbar"`: declarar o papel obriga a declarar `aria-label`
   e `aria-valuenow`, e os dois seriam invenção minha. Decisão de desenho.
5. **O estado vazio não existe** (item 2 de "O que não fiz"): é o único item da
   §29 que esta tela não fecha, além da barra.
