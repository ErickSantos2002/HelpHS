# §29 — `components/layout/Sidebar.tsx`

Não é uma página: é a barra lateral, e ela aparece em **todas** as 33 telas do
sistema. Um defeito aqui não é de uma tela, é do produto — e foi com esse peso
que cada troca foi conferida duas vezes antes de entrar.

Ela entra na Fase 16 por **12** classes de paleta crua, **2** `text-white` e
**13** `<svg>` soltos — a segunda maior concentração de desenho à mão do
inventário. E traz um detalhe que nenhuma outra tela tem: **foi daqui que
saíram os traçados do pacote**. O `Icon.jsx` do design system diz isso no
cabeçalho, com todas as letras. Migrar esta tela é o pacote fechando a volta.

293 linhas antes, 271 depois. O que encolheu foram os treze componentes de
ícone escritos por extenso; o que cresceu foi o **porquê** de três decisões que
ninguém reencontra sozinho — a dica que deixou de ser pastilha escura, o
crédito do rodapé que escureceu, e por que o grupo de menu passou a ter nome.

---

## O que a barra tinha

| o que | quantos |
|---|---:|
| classes da paleta crua | **12** — todas `slate-*` |
| `<svg>` solto | **13** |
| componente local de ícone | **13** (`IconDashboard` … `IconCalendar`) |
| `text-white` | **2** — as duas dicas |
| cor cheia semântica como cor de TEXTO | **0** |
| hexadecimal cravado | **0** |
| `useTheme()` | **0** — não há gráfico aqui |
| mapas locais de vocabulário compartilhado | **0** |
| linhas da varredura de contraste | **0** |
| par que reprova e a varredura NÃO via | **1** — o crédito do rodapé |

A última linha é a que importa. **A tela não aparecia na catraca, e isso não é
o mesmo que estar certa.** O crédito "© 2026 Health & Safety Tech" era
`text-slate-400 dark:text-slate-600`, e o fundo dele vem do `<aside>`, dois
níveis acima — "fundo declarado no ancestral" é limitação que a varredura
declara. Medido à mão sobre `--surface`: **2,56:1** no claro e **2,11:1** no
escuro. Texto de verdade, contra um piso de 4,5:1.

---

## O que passou a usar

| módulo / primitivo | onde | quantos |
|---|---|---:|
| `Icon` (E20/E21) | os treze desenhos do menu | **13** |
| tokens semânticos de texto | item em repouso, hover, dica, rodapé | 6 classes |

Nenhum módulo de `lib/` entrou: a barra não fala de status, prioridade,
categoria nem gráfico. O vocabulário dela é rota e papel, e os dois já vinham
de `types/auth`.

### Os 13 `<svg>`, e como cada um casou

Os treze tinham **exatamente** o envelope do primitivo — `viewBox="0 0 24 24"`,
`fill="none"`, `stroke="currentColor"`, `strokeWidth={1.75}` e `w-5 h-5`, que é
o `size={20}` padrão do `Icon`. Nenhum era 20×20, nenhum era de preenchimento;
a armadilha da estrela sólida do `AdminDashboard` não aparece aqui.

Conferidos por script, campo `d` contra `ICON_PATHS_PACOTE`, **caractere a
caractere**: 13 de 13 idênticos.

| componente local | virou | como casou |
|---|---|---|
| `IconDashboard` | `dashboard` | idêntico, caractere a caractere |
| `IconTicket` | `ticket` | idêntico |
| `IconUsers` | `users` | idêntico |
| `IconGroups` | `groups` | idêntico |
| `IconBox` | `box` | idêntico |
| `IconChart` | `chart` | idêntico |
| `IconShield` | `shield` | idêntico |
| `IconClock` | `clock` | idêntico |
| `IconCpu` | `cpu` | idêntico |
| `IconBook` | `book` | idêntico |
| `IconTag` | `tag` | idêntico |
| `IconChat` | `chat` | idêntico |
| `IconCalendar` | `calendar` | idêntico |

Nenhum ícone novo foi preciso, e nenhum precisou casar por significado: os
treze são os **originais**, e o pacote é a cópia deles.

### O mapa de menu ficou, com o nome do traçado no lugar do elemento

`NAV_GROUPS` é a estrutura natural desta tela — um item de menu é rótulo, rota,
desenho e quem vê — e continua inteiro. O que mudou é o tipo do campo `icon`:
era `React.ReactNode`, e era isso que obrigava a existir um componente local
por ícone. Agora é `IconName`, o tipo derivado do próprio mapa do pacote: nome
que o pacote não tem o TypeScript recusa, e o desenho não pode divergir em
silêncio.

### As seis classes de cor

| onde | antes | agora | por quê |
|---|---|---|---|
| item em repouso | `text-slate-500 dark:text-slate-400` | `text-conteudo-muted` | no escuro é o **mesmo valor**; no claro o token é um degrau mais escuro — 4,76:1 vira 7,58:1 |
| item sob o cursor | `hover:text-slate-900 dark:hover:text-slate-100` | `hover:text-conteudo-heading` | `--text-heading` é, valor por valor, slate-900 no claro e slate-100 no escuro. **Não muda um pixel** |
| dica: fundo | `bg-slate-900 dark:bg-slate-700` | `bg-surface-elevated` + `border border-borda` | ver abaixo |
| dica: texto | `text-white` | `text-conteudo-heading` | 16,30:1 no claro e 12,37:1 no escuro sobre a superfície elevada |
| rodapé: versão | `text-slate-500 dark:text-slate-400` | `text-conteudo-muted` | igual ao item em repouso |
| rodapé: crédito | `text-slate-400 dark:text-slate-600` | `text-conteudo-muted` | ver abaixo |

O `hover:text-action` do botão de versão **ficou como estava**: já é token, e
`--action` resolve para os mesmos valores que `--text-link` nos dois temas —
5,29:1 sobre `--surface` no claro, 5,95:1 no escuro.

O par do item **ativo** também ficou: `bg-action-tint` com `text-action` dá
**4,97:1** no claro e **4,92:1** no escuro. Aprova, e é o degrau de ação que o
`tailwind.config.js` manda usar para item ativo.

### A dica deixou de ser pastilha escura invertida — e é mudança visível

As duas dicas (a do menu recolhido e a do botão de versão) eram uma pastilha
`bg-slate-900 dark:bg-slate-700` com texto branco: um objeto que inverte o tema
em vez de acompanhá-lo, e não há nenhum token de "superfície invertida" no
pacote para expressá-lo.

O que existe é o cromo de **dica** que o próprio sistema já define, em
`CROMO` de `lib/grafico.ts`: `dicaFundo` = superfície, `dicaBorda` = borda,
`dicaTexto` = `--text-heading`. As duas passaram a falar essa língua, com
`bg-surface-elevated` no lugar de `--surface` porque a barra lateral **já é**
`bg-surface` e a dica do rodapé nasce dentro dela — dica da mesma cor do painel
que a hospeda não é dica.

**Isto muda a aparência da barra**, e está relatado.

### O crédito do rodapé escureceu, e é conserto de defeito medido

`text-slate-400 dark:text-slate-600` sobre `--surface`: **2,56:1** no claro,
**2,11:1** no escuro.

O degrau de nome óbvio também não serve — `--text-faint` dá **2,56** e
**3,36**, e a regra 4 do briefing já nomeia `faint` como um degrau que não faz
par. Quem aprova nos dois temas é `--text-muted`: **7,58** e **6,23**.

A consequência é que o crédito perde parte da diferença de peso que tinha em
relação à linha da versão logo acima. O que ainda os separa é o tamanho —
`text-[11px]` contra `text-xs`. É mudança visível, é conserto de defeito
medido, e está relatada.

### Acessibilidade: o que já estava certo, e o que não estava

**O item ativo já se declarava.** O `NavLink` do react-router-dom 7 escreve
`aria-current="page"` sozinho quando a rota casa — conferido no código do
router, não suposto. Então a página atual **não** era comunicada só por cor, e
o achado de 1.4.1 que o briefing esperava aqui **não existe**. Três casos de
teste prendem isso, porque é comportamento de biblioteca e pode sumir num
upgrade sem ninguém notar.

**O item recolhido já tinha nome acessível.** A dica é um `<span>` com texto
real e `opacity-0` — opacidade não tira da árvore de acessibilidade, então o
rótulo é o nome do link nos dois modos. Frágil o bastante para merecer caso
próprio: trocar a dica por `title`, ou condicioná-la a hover de verdade,
deixaria **todos** os links do sistema sem nome.

**O que não estava certo:**

| achado | agora |
|---|---|
| o `<nav>` não tinha nome — o leitor anunciava só "navegação" | `aria-label="Navegação principal"` |
| no modo recolhido os três agrupamentos **desapareciam** para quem não vê: o rótulo da seção só é desenhado expandido, e no recolhido sobra um traço decorativo | cada grupo é `role="group"` com `aria-label`, anunciado nos dois modos |
| com o grupo nomeado, o `<p>` visível passaria a ser lido duas vezes | `aria-hidden="true"` no `<p>`, que agora é a versão visível de um nome que o grupo já declara |

---

## O que resta à mão — a contagem

**Contar, não julgar**: um número maior que zero significa que alguém tem de
olhar, não que há trabalho pendente.

| o que | quantos | observação |
|---|---:|---|
| `<svg>` solto | **0** | eram 13; a única ocorrência de `<svg` no arquivo é texto de comentário |
| componente local de ícone | **0** | eram 13 |
| classe de paleta crua em código | **0** | eram 12; as 5 ocorrências restantes são comentário citando o que saiu |
| `text-white` | **0** | eram 2 |
| cor cheia semântica como texto | **0** | não havia |
| hexadecimal em código | **0** | não havia |
| `theme` lido em JavaScript | **0** | não havia |
| linhas da varredura de contraste | **0** | eram 0 — e continuam 0 |
| par medido que reprova | **0** | era 1, o crédito do rodapé |
| mapas locais de vocabulário compartilhado | **0** | não havia |
| tabelas locais de conceito local | **1** | `NAV_GROUPS`, ver abaixo |
| controles à mão | **1** | o véu do menu no celular, ver abaixo |

**A tabela local.** `NAV_GROUPS` é local **de propósito**: menu de navegação
não é vocabulário compartilhado — não há outra tela que precise saber que
"Etiquetas" fica em "Administração". É a mesma régua pela qual `lib/papel.ts`
existe e um `NAV_GROUPS` em `lib/` não faria sentido. E ela não repete classe
nenhuma: guarda rótulo, rota, **nome** de ícone e papéis.

**O controle à mão.** O véu que fecha o menu no celular é um `<div>` com
`role="button"`, `tabIndex={0}` e `onKeyDown` para Enter e espaço — um botão
reconstruído sobre uma `div`. Não foi tocado: é anterior a esta fase, não tem
cor crua (usa `bg-[color:var(--overlay)]`, token) e trocá-lo por `<button>`
mexe na ordem de tabulação de todas as telas no celular. Relatado.

---

## O que mudou na TELA, e que alguém vai ver

| onde | antes | agora |
|---|---|---|
| dica do menu recolhido | pastilha escura, texto branco | superfície elevada com borda, texto de título |
| dica do botão de versão | idem | idem |
| item de menu em repouso, **tema claro** | slate-500 (4,76:1) | `--text-muted`, slate-600 (7,58:1) — um degrau mais escuro |
| crédito do rodapé | slate-400 / slate-600 (2,56:1 e 2,11:1) | `--text-muted` (7,58:1 e 6,23:1) — visivelmente mais escuro |
| item de menu sob o cursor | slate-900 / slate-100 | **igual** — o token tem o mesmo valor |
| item ativo, logo recolhido, ícones | — | **iguais** |
| o que um leitor de tela anuncia | "navegação", sem nome; nenhum agrupamento no modo recolhido | "Navegação principal"; os três grupos anunciados nos dois modos |

Nenhuma delas mexe em número que alguém lê, e nenhuma altera o que a barra
mostra ou esconde: os mesmos itens, para os mesmos papéis, nas mesmas rotas.
As duas primeiras e a quarta mexem em **aparência**; a última mexe no que a
árvore de acessibilidade **fala**. As quatro estão relatadas.

---

## O que NÃO foi feito, e por quê

- **Criar um token de superfície invertida para a dica.** É o que expressaria a
  pastilha escura sem paleta crua, e não existe no pacote. Criá-lo é emenda, e
  emenda não se faz de dentro de uma tela. O que está no ar é o cromo de dica
  que o sistema já define, e ele precisa de confirmação. Relatado.
- **Trocar o véu do celular por `<button>`.** Ver acima: muda ordem de
  tabulação em todas as telas no celular.
- **Mexer no `ChangelogModal`.** É outro arquivo, aberto por esta barra. Não é
  o meu arquivo.
- **Mexer no `Topbar` e no `AppLayout`.** Idem — e os dois já têm caso próprio
  na suíte, de fases anteriores.
- **Dar nome ao logotipo do modo recolhido.** O quadrado com "H" é lido como a
  letra "H" solta; no modo expandido é um `<img alt="HelpHS">`. Corrigir é
  decidir entre `sr-only`, `aria-label` e `alt` — muda o que a árvore fala, e é
  o mesmo tipo de decisão que a bolha própria do `ChatPanel` deixou em aberto.
  Relatado.
- **Transformar a lista de itens em `<ul>`/`<li>`.** Seria a marcação
  convencional de um menu, mas é reestruturação de árvore na tela que aparece
  em toda parte, e o ganho sobre `role="group"` + links nomeados é marginal.

---

## Testes

`src/test/components/Sidebar.test.tsx`, novo, **24 casos**. Todos passaram na
primeira execução, então todos foram validados por mutação.

Os casos são sobre o que a barra **promete**: que cada destino tem nome
alcançável, que a página atual se declara, que o menu de um cliente não expõe
rota de administrador, que os desenhos vêm do pacote. Nenhum caso afirma
`toHaveClass` — o jsdom **não aplica CSS**, e um caso assim passaria com a
classe presente e o elemento invisível de verdade.

As duas exceções são declaradas: os casos de **cor** leem o arquivo, porque cor
não existe no jsdom; e cada linha deles prende as **duas** metades do par — a
classe que o arquivo escreve **e** o número que os tokens dela dão. Medir só o
token prova que a paleta é sólida e não prova que esta tela a usa. Foi assim
que passaram o link de pular e a página ativa da `Pagination`.

Um caso mereceu atenção: "não lê o rótulo da seção duas vezes" consulta por
**papel** (`queryAllByRole("paragraph")`), não por texto. `getByText` varre o
DOM e não consulta a árvore de acessibilidade — ele acharia o parágrafo
`aria-hidden` e o caso não mediria nada. A primeira versão fazia exatamente
isso, e falhou; a correção foi trocar a consulta, não o alvo.

**Treze mutações, todas no ELEMENTO ou no comportamento:**

| mutação | caso que morreu |
|---|---|
| some o `aria-label` do `<nav>` | o marco de navegação tem nome próprio |
| some `role="group"` e o nome do grupo | os grupos são nomeados nos dois modos |
| some o `aria-hidden` do rótulo da seção | o rótulo não é lido duas vezes |
| o item ativo anuncia `aria-current="location"` | a página atual se declara por `page` |
| todo item fecha a rota (`end={true}`) | na tela de um chamado, quem fica marcado é Tickets |
| a dica do modo recolhido fica sem texto | cada item tem nome acessível com a barra recolhida |
| o papel deixa de filtrar os itens | o cliente não alcança rota de gestão; o técnico não vê rota de admin; grupo vazio não é anunciado |
| um `<svg>` escrito à mão volta ao arquivo | nenhum `<svg>` é escrito à mão |
| o traço do ícone vira 2 | o ícone mantém a escala e o traço da navegação |
| paleta crua volta no item em repouso | não sobrou paleta crua fora de comentário |
| `text-white` volta na dica | idem |
| o crédito volta ao degrau que reprova | o crédito usa o degrau que aprova |
| o hover do item perde o token | o item sob o cursor aprova em AA |

⚠️ **Duas mutações sobreviveram na primeira rodada, e as duas eram no-op —
defeito do roteiro, não dos casos.** Estão registradas porque o modo de falha é
sutil e vai reaparecer:

1. `aria-current={undefined}` no `NavLink`. O router faz
   `"aria-current": ariaCurrentProp = "page"` — desestruturação **com valor
   padrão**, e valor padrão se aplica justamente quando o campo é `undefined`.
   O mutante era o original. Substituído por `aria-current="location"`.
2. `end={false}` na rota `/`. O `isActive` do router é
   `locationPathname === toPathname || !end && startsWith(...) &&
   charAt(endSlashPosition) === "/"`; para `toPathname === "/"`,
   `endSlashPosition` é 1, e `"/tickets".charAt(1)` é `"t"`. O ramo do `end`
   **nunca** liga para a raiz, então tirar o `end` não muda nada ali.
   Substituído por `end={true}` — que muda, e mata o caso da sub-rota
   `/tickets/t1`, acrescentado por causa disto.

Nenhuma das treze finais é das três que **não** são mutações: nenhuma troca só
classe, nenhuma renomeia símbolo com o consumidor junto, e nenhuma usa `&&`.

O roteiro tem as duas defesas do briefing: **controle sem mutação** antes da
primeira, exigido passar (se ele não passa, nada depois dele vale); e chamada
ao vitest por `process.execPath` + `node_modules/vitest/vitest.mjs`, **nunca**
por `npx.cmd`. Mais uma terceira: alvo que não é encontrado no arquivo conta
como **sobrevivente**, para que "mutação não aplicada" não se disfarce de
"mutante morto". Restauração em `finally`, cópia em memória, **nenhum `git`**.

---

## Verificação

| conferência | resultado |
|---|---|
| `vitest run src/test/components/Sidebar.test.tsx` | **24 passaram** |
| `vitest run` + `AppLayout.test.tsx` (o vizinho que lê esta casca) | **28 passaram** |
| mutação | **13 mortas de 13**, nenhuma sobrevivente, arquivo restaurado e conferido |
| `npx tsc --noEmit -p tsconfig.app.json` | sem erro nos meus arquivos |
| `npx eslint` nos dois arquivos | limpo |
| `varredura-contraste.mjs` \| `grep Sidebar` | **nenhuma linha** (eram 0, e continuam 0) |
| classes de paleta crua em código | **0** (eram 12) |
| `<svg>` solto | **0** (eram 13) |
| `text-white` | **0** (eram 2) |
| hexadecimal | **0** (era 0) |
| par medido que reprova AA | **0** (era 1) |

⚠️ Sobre o `tsc`: no momento da conferência, `src/pages/kb/KBFormPage.tsx` —
arquivo de **outro agente**, na mesma árvore — relatava `TS6133` numa variável
não usada. É o único erro do compilador, e `Sidebar.tsx` e `Sidebar.test.tsx`
não aparecem nele.
