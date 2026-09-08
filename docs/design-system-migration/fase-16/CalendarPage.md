# §29 — `pages/calendar/CalendarPage.tsx`

A tela com **mais hexadecimal cravado** de toda a fase: 22 em 758 linhas. E o
julgamento desta migração não foi trocá-los — foi separá-los. **Vinte e um dos
vinte e dois são dado, não dívida**, e transformá-los em token teria escrito
`var(--chart-3)` dentro de uma coluna do banco.

757 linhas antes, 814 depois. Cresceu porque o que saiu era denso e o porquê
ficou escrito.

---

## O que a tela tinha

| o que | quantos |
|---|---:|
| classes da paleta crua (`slate-*` e `amber-*`) | **39** |
| funções `Icon*` locais — variante local do pacote | **6**, em **9** usos |
| hexadecimal cravado | **22** |
| par `bg-primary` + `text-white` (3,83:1) | **2** lugares |
| `text-white` sobre cor arbitrária do usuário | **1** |
| cor cheia semântica como cor de TEXTO | **2** (`text-danger` ×2) |
| classe de opacidade que **não existe** (`bg-primary/8`) | **1** |
| `<label>` sem `htmlFor` | **2** |
| controle sem nome acessível nenhum | **6** (2 setas, 2 seletores, 4 botões de ícone — em 2 receitas) |
| informação dita **só pela cor** | **3** (hoje, mês com eventos, mês atual) |

### Os 22 hexadecimais, nos três grupos

Este é o item que o briefing mandou separar antes de trocar qualquer coisa, e o
resultado é assimétrico:

| grupo | quantos | o que se fez |
|---|---:|---|
| **cor que é decisão de desenho** (o azul de "hoje", o cinza do fim de semana) | **0** | nada a fazer — não havia. Os estados da grade já vinham em token (`bg-primary`, `bg-surface-elevated/30`); o que estava errado neles era o token escolhido, não um hexadecimal |
| **cor que é dado** — `EVENT_TYPE_COLORS`, o padrão por tipo que vai para a coluna `color` do evento | **5** | **ficaram**. O usuário pode sobrescrever, e os cinco são membros da paleta abaixo |
| **paleta que o sistema oferece ao usuário** — `EVENT_COLOR_PALETTE` | **16** | **ficaram**, e relatadas: escolher a paleta de quem cria evento é decisão de desenho de produto |
| duplicata do primeiro grupo dentro do `useState` | **1** | virou `EVENT_TYPE_COLORS.event` — a mesma fonte, sem o valor repetido |

**Por que dado não vira token.** `color` é uma coluna de texto do backend. Um
`var(--chart-3)` gravado ali não é cor de gráfico: é uma string que sai no
relatório, na exportação e para quem ler a tabela. E o seletor de cores compara
`color === c.value`, comparação que um token quebraria em silêncio.

O que o sistema de design resolve aqui **não é o fundo — é o texto por cima
dele**, e isso era `text-white` cravado. A paleta oferece `#ffffff` e `#eab308`:
branco sobre branco não se lê. `readableTextColor` já existia em
`src/lib/colors.ts`, decide por luminância relativa (WCAG) e é exatamente o
mecanismo para o caso. Uma linha, e o defeito acabou.

---

## O que passou a usar

| módulo / primitivo | onde | quantos |
|---|---|---:|
| `Icon` (E21) | `calendar`, `plus` ×2, `chevronLeft`, `chevronRight`, `edit` ×2, `trash` ×2 | **9** usos |
| `readableTextColor` (`lib/colors.ts`) | o título do evento sobre a cor do usuário | 1 |
| tokens de texto (`conteudo-*`) | as 33 classes `slate-*` | 33 |
| tokens de tinta (`tint-*` + `on-tint-*`) | os 6 realces (primário ×3, warning ×2, danger ×2) | 7 |
| degrau de ação (`bg-action` + `text-on-primary`) | disco de "hoje", botão do mês atual | 2 |
| `--border-control` (E7) | o contorno das 16 amostras de cor | 1 |

### Os seis `<svg>`, e como cada um casou

Os seis eram `viewBox="0 0 24 24"` com `fill="none"` e `stroke="currentColor"` —
mesma família do `Icon`, **conferido antes de trocar**. E os seis casaram
**pelo traçado `d`, caractere a caractere**, sem precisar recorrer ao
significado:

| desenho | virou | tamanho |
|---|---|---|
| `IconCalendar` | `calendar` | `w-5 h-5` = `size={20}`, traço 1,75 (o padrão) |
| `IconChevronLeft` | `chevronLeft` (E21) | `w-4 h-4` = `size={16}`, traço 2,5 |
| `IconChevronRight` | `chevronRight` (E21) | `w-4 h-4` = `size={16}`, traço 2,5 |
| `IconPlus` | `plus` | `w-4 h-4` = `size={16}`, traço 2,5 |
| `IconPencil` | `edit` | `w-3 h-3` = `size={12}`, traço 2,5 |
| `IconTrash` | `trash` | `w-3 h-3` = `size={12}`, traço 2,5 |

Nenhum ícone novo foi preciso, e nenhuma tabela local ficou no arquivo.

### `bg-primary/8` — a classe que nunca existiu

O fundo do dia escolhido era `bg-primary/8`. **A regra nunca foi gerada.** A
escala de opacidade do Tailwind v3 vai de cinco em cinco (0, 5, 10, 15, 20 …) e
o 8 não está nela; sem colchetes não há valor arbitrário. Conferido compilando
o caso com o Tailwind instalado do projeto: `bg-primary/10` e `bg-amber-500/15`
saem, `bg-primary/8` não sai — e não há erro nem aviso.

Consequência: o dia escolhido vinha **só com o anel**, e o fundo que o autor
escreveu nunca pintou um pixel. Virou `bg-tint-primary`, que é o token da tinta
e já carrega o alfa de 15% — por isso **não** leva modificador de opacidade
(regra (a) do D8-a).

### Os dois pares de 3,83:1

`bg-primary` com `text-white`, no disco de "hoje" e no botão do mês aberto no
mapa dos meses. São os dois lugares da catraca, e o problema é o mesmo dos
outros: `primary` é o degrau de **marca**, absoluto, e não inverte por tema. O
par do degrau de **ação** é `--action` com `--text-on-primary` — branco no
claro, navy no escuro (emenda E1).

O número do dia escolhido era `text-primary` sobre a tinta primária: exatamente
o par que a **E8** mediu em 2,77:1. Virou `text-on-tint-primary`.

### O contorno das amostras de cor

As 16 amostras traziam `ring-inset ring-black/15`, com o comentário "para as
cores claras não sumirem no fundo". Ele não fazia isso: preto a 15% sobre a
superfície branca do tema claro dá cerca de **1,3:1**, e o limite do controle
desaparecia justamente onde fazia falta. `--border-control` é o token da **E7**
para limite de controle, medido em 4,76 / 4,55 / 4,34 no claro e
6,23 / 6,78 / 5,29 no escuro. Foi a última cor crua do arquivo a sair.

### As três informações que só a cor dizia

| o que | era | passou a ser |
|---|---|---|
| hoje | um disco azul | disco + `<span className="sr-only"> (hoje)</span>` |
| mês com eventos | um ponto no canto do botão | ponto + `— com eventos` no nome do botão |
| mês atual | um traço embaixo do botão | traço + `— mês atual` no nome do botão |

É a mesma regra que o `lib/prioridade.ts` documenta para o ponto de prioridade:
enquanto a cor é o único portador ela precisa de 3:1 (WCAG 1.4.11); **com o
texto ao lado a cor vira reforço, o piso deixa de se aplicar, e a informação
existe para todo mundo.**

### Os seis controles que não tinham nome

Duas setas (`<svg>` dentro de `<button>` vazio), dois `<select>` sem rótulo
nenhum, e quatro botões de ícone — editar e remover, em duas receitas — sem
texto, sem `title` e sem `aria-label`. O leitor de tela anunciava "botão" e nada
mais. Os de editar/remover passaram a dizer **de qual evento** são
(`Editar ${e.title}`), porque a tela mostra vários e "Editar" sozinho não
distingue.

O `<label>Cor</label>` não rotulava nada — não há um campo para apontar, são
dezesseis botões. Virou nome do **grupo** (`role="group"` +
`aria-labelledby`), que é o que a pessoa ouve antes de percorrer as opções.

---

## O que resta à mão — a contagem

**Contar, não julgar**: um número maior que zero significa que alguém tem de
olhar, não que há trabalho pendente.

| o que | quantos | observação |
|---|---:|---|
| linhas da varredura de contraste | **0** | eram 4 |
| classe de paleta crua | **0** | eram 39; as 3 ocorrências restantes são texto de comentário |
| `text-white` | **0** | eram 3; as 3 restantes são comentário |
| `<svg>` solto | **0** | eram 6; a única ocorrência de `<svg` é comentário |
| cor cheia semântica como texto | **0** | eram 2 |
| `theme` lido em JavaScript | **0** | não havia |
| hexadecimal em código | **21** | **todos dado** — 5 padrões por tipo + 16 da paleta oferecida. Ver acima |
| mapas locais | **5** | vocabulário de calendário, não do sistema de design |
| receitas de controle à mão | **8** | ver abaixo |
| `<div onClick>` | **2** | ver "o que NÃO foi feito" |

**Os cinco mapas locais** são `EVENT_TYPE_LABELS`, `MONTHS`, `MONTHS_SHORT`,
`WEEKDAYS` e `WEEKDAYS_FULL` — nome de mês, dia da semana e tipo de evento.
Nenhum é fonte única do sistema de design (não há `lib/agenda.ts`), nenhum
carrega classe e nenhum duplica `status`, `prioridade` ou `categoria`.

**As oito receitas de controle à mão**, e por que cada uma ficou:

1. **três `<select>` nativos** (tipo do evento, mês, ano) — o `Selector` é uma
   lista com caixa própria, de 40px; os dois da navegação são de 32px e ficam
   numa fita horizontal com as setas. Trocar muda a altura da barra inteira, que
   é leiaute e não sistema de design. Ganharam `aria-label` / `htmlFor`;
2. **as duas setas de mês** — botão de 32px quadrado com só o ícone; não há
   primitivo para isso;
3. **o botão "Hoje"** — tinta primária com borda, 32px, ao lado das setas. O
   `Button` traz outra altura e outro preenchimento;
4. **os doze botões do mapa dos meses** — grade de 3 colunas com dois
   marcadores posicionados em cima do texto;
5. **os quatro botões de editar/remover** (2 receitas) — 24px redondo com o
   ícone de 12px dentro;
6. **o botão de adicionar do detalhe do dia** — 32px, tinta primária;
7. **o `✕` que fecha o detalhe do dia** — é um caractere, não um `<svg>`, e é
   ele que dá o nome do botão hoje. Ganhou `aria-label="Fechar o dia"`. Trocar
   pelo `Icon name="close"` é mudança visual sem ganho de acessibilidade, e não
   se decide de dentro da tela;
8. **as dezesseis amostras de cor** — botão quadrado pintado com o valor do
   dado. Não há primitivo de seletor de cor.

---

## O que NÃO foi feito, e por quê

- **A paleta de 16 cores oferecidas ao usuário.** É dado que o **sistema**
  define, e escolher que cores se oferece a quem cria evento é decisão de
  desenho de produto. Ficou como está, e está relatada.
- **As células do dia continuam `<div onClick>`.** É o item do `CHECKLIST-29`
  sobre ação alcançável só pelo mouse, e ele **não se resolve trocando a tag**:
  hoje há um clicável **dentro** de outro — o chip do evento abre a edição, a
  célula abre o detalhe do dia. Dois `<button>` aninhados são HTML inválido, e
  desatar isso é redesenhar o fluxo de teclado da grade (a grade vira `grid` com
  navegação por setas? o chip sai da célula para uma lista abaixo?). Isso é
  desenho, e não se decide aqui. **Relatado.**
- **O `bg-primary/60` e o `bg-primary/40` dos dois marcadores do mapa dos
  meses.** São tokens com opacidade, não paleta crua, e a varredura não os
  aponta. O que faltava neles — a informação existir fora da cor — foi
  resolvido com o texto `sr-only`.
- **Alinhar o foco ao `outline` do pacote (desvio F1).** Os três `<select>` e os
  botões usam `focus:ring-2 focus:ring-primary`, que é o que as telas vizinhas
  já migradas também usam. Mudar isso é `components/ui/` e `index.css`, fora do
  escopo.
- **`lib/agenda.ts` com o vocabulário de calendário.** Os nomes de mês e de dia
  da semana existem também em outras telas. Criar o módulo é escrever em
  `lib/`, que o contrato proíbe. **Relatado.**

---

## Testes

`src/test/pages/CalendarPage.test.tsx`, **12 casos**, todos validados por
mutação. **Nenhum caso olha classe**: o happy-dom não aplica CSS, e um mutante
de classe sobrevive por um motivo que não tem nada a ver com o que o caso mede.
O único caso que lê `style` lê o **valor final que o navegador pinta** — a cor
do texto que `readableTextColor` calcula —, e não uma classe.

Os casos não congelam o relógio: eles derivam o mês e o dia do próprio
`new Date()` e escolhem um dia que **não** é hoje, para o clique não colidir com
o sufixo "(hoje)". Relógio falso e `waitFor` do Testing Library não se entendem
no vitest — a biblioteca procura os temporizadores do jest, não acha, e espera
em tempo real enquanto o relógio está parado.

**Dezoito mutações, todas no ELEMENTO ou no comportamento**, e as dezoito
morreram:

| mutação | caso que morreu |
|---|---|
| a seta "Mês anterior" perde o `aria-label` | as setas de mês têm nome, e mudam o mês |
| a seta "Próximo mês" perde o `aria-label` | as setas de mês têm nome, e mudam o mês |
| o `<select>` de mês perde o nome | as setas … / os dois seletores dizem o que selecionam |
| o `<select>` de ano perde o nome | os dois seletores dizem o que selecionam |
| o `<span>` " (hoje)" some | o dia de hoje é dito em texto, e não só pelo disco |
| `readableTextColor(e.color)` volta a `"#ffffff"` | o título do evento é legível sobre a cor do usuário |
| o `sr-only` "— com eventos" vira `<span />` | o mês com eventos e o mês atual são ditos no nome |
| o `sr-only` "— mês atual" vira `<span />` | o mês com eventos e o mês atual são ditos no nome |
| "Editar" do **detalhe do dia** deixa de dizer qual evento | editar e remover dizem de QUAL evento são |
| "Remover" do **detalhe do dia** deixa de dizer qual evento | editar e remover dizem de QUAL evento são |
| "Editar" deixa de dizer qual evento, **nos dois lugares** | editar e remover dizem de QUAL evento são |
| "Remover" deixa de dizer qual evento, **nos dois lugares** | editar e remover … / remover pede confirmação |
| `confirm(...)` sai do `handleDelete` | remover pede confirmação antes de chamar o serviço |
| `canEdit` vira `true` | o cliente não encontra controle de edição nenhum |
| a grade de cores perde o `aria-labelledby` | a grade de cores é um grupo com nome |
| `aria-pressed` some das amostras | a grade de cores … e a cor em uso está marcada |
| o `htmlFor` do rótulo "Tipo" some | o tipo do evento é alcançável pelo próprio rótulo |
| `monthEvents.length === 0` deixa de esconder o bloco | sem evento nenhum, a tela diz que não há |

**A mutação achou um ponto cego real, e o defeito era do teste.** Os pares
editar/remover existem **duas vezes** na tela — no detalhe do dia e na lista de
gerenciar do mês — e a primeira versão do caso só alcançava a segunda: trocar o
nome do par do detalhe do dia não reprovava nada, porque o caso nunca abria o
dia. O caso passou a abrir o dia e a exigir **duas** ocorrências de cada nome.
Foi por isso que o roteiro ganhou as duas variantes "nos dois lugares": a
substituição de string troca só a primeira ocorrência, e uma mutação que não
alcança o que o caso mede acusa o teste de vazio quando o vazio é ela.

**As duas defesas do roteiro**, e as duas foram usadas: um **controle sem
mutação nenhuma** antes da primeira (ele passou — a régua mede), e a chamada do
vitest por `process.execPath` + `node_modules/vitest/vitest.mjs`, nunca por
`npx.cmd`. O roteiro também recusa uma "mutação" cujo texto resultante seja
igual ao original, que é o no-op mais fácil de não perceber. A mutação é
desfeita em `finally`, e não com `git`.

---

## Verificação

| conferência | resultado |
|---|---|
| `npx vitest run src/test/pages/CalendarPage.test.tsx` | **12 passaram** (3 execuções, estável) |
| mutação | **18 de 18 morreram**, com controle passando antes |
| `npx tsc --noEmit -p tsconfig.app.json` | sem erro nesta tela |
| `npx eslint` nos dois arquivos | limpo |
| `varredura-contraste.mjs` \| `grep calendar` | **nenhuma linha** (eram 4) |
| classes de paleta crua em código | **0** (eram 39) |
| `<svg>` solto | **0** (eram 6) |
| `text-white` em código | **0** (eram 3) |
| cor cheia semântica como texto | **0** (eram 2) |
| hexadecimal em código | **21** (eram 22) — todos dado, por decisão |
