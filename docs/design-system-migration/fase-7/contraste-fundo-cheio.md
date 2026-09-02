# Texto sobre fundo cheio — varredura do JSX

Levantamento feito a partir do **JSX**, não do `colors.css`. A distinção é o
achado: medir o token prova que a paleta é sólida; não prova que as telas a
usam. As telas escrevem classe por cima do token, e `text-white` não é token
nenhum.

Foi o que deixou passar o link de pular e a `Pagination`: a conferência do
Checkpoint 1 mediu `--action` contra as superfícies e deu a casca por conforme.

Origem: pista da sessão do **ChamadosHS**, que achou o mesmo padrão do lado
dela. As duas varreduras trocaram método antes de qualquer conserto.

## As quatro armadilhas do método

As três primeiras vieram de lá, já com a correção; a quarta apareceu aqui.

1. **Filtrar diretório.** Excluir `components/ui/` ou olhar só `pages/` perde os
   casos que moram em primitivo e em casca — e são justamente os que aparecem em
   toda tela. Aqui, os três piores estavam em `components/layout/` e
   `components/ui/`.
2. **Casar linha a linha.** `className` quebra em várias linhas o tempo todo:
   `bg-danger` numa linha e `text-white` na seguinte não casam num `grep`. A
   varredura precisa juntar o atributo inteiro, com chaves balanceadas.
3. **Ignorar o prefixo de estado.** Casar um `hover:bg-*` com o `text-*` de
   repouso mede um par que não existe, e pode **transformar reprovação em
   aprovação**. Fundo e texto se pareiam pelo mesmo prefixo.
4. **Parear ramos de ternário.** Esta apareceu ao consertar a segunda: juntar
   todas as strings de um `cn(...)` põe lado a lado classes de ramos
   mutuamente exclusivos. Aqui isso inventou seis reprovações de **1,00:1** —
   `bg-primary text-white` num ramo contra `text-primary` no outro, que nunca
   coexistem em pixel nenhum. A varredura pareia dentro de **uma string
   literal**, e o preço é subcontar quando o fundo está no literal base e o
   texto num condicional.

## O padrão

O degrau **500** nunca serve para carregar texto; o **600/700** serve. É o que a
E2 reconheceu ao criar `--action-danger` e `--action-success`, e a razão de
`--action` sempre ter existido separado de `--color-primary-500`.

| Par escrito à mão | claro | escuro |
|---|---:|---:|
| `bg-primary` + `text-white` | 3,83 ❌ | 3,83 ❌ |
| `bg-danger` + `text-white` | 3,76 ❌ | 3,76 ❌ |
| `bg-action` + `text-white` | 5,29 ✅ | **2,69** ❌ |
| `bg-action` + `text-on-primary` (E1) | 5,29 ✅ | **5,11** ✅ |
| `Button` hoje | 5,29 ✅ | 5,11 ✅ |

O `bg-primary text-white` reprova nos **dois** temas: `--color-primary-500` é
degrau absoluto e não inverte. Não há tema em que ele se salve.

## A regra que estes documentos compraram com erro

**Valor de cor se lê do `colors.css`; não se digita de cabeça.** Três vezes
nesta fase eu publiquei número calculado sobre um hexadecimal que eu havia
digitado em vez de lido:

| O que digitei | O real | Efeito |
|---|---|---|
| `--surface` escuro `#0f1e2e` | `#132238` | quatro contrastes do `warning` errados |
| `--color-primary-900` `#0b3049` | `#0b3047` | 5,09 no lugar de **5,11** |

O corpo do commit `adbf7a0` carrega o 5,09; não foi reescrito para não mexer em
histórico já gravado. Vale o 5,11 daqui — que é também o que o `EMENDAS.md`
registra para a E1.

O segundo é o mais constrangedor: **5,11:1 já estava registrado** no commit da E1
e no `EMENDAS.md`, quatro vezes. Publiquei um número que contradizia o próprio
projeto porque recalculei em vez de consultar.

Os **testes nunca erraram** — eles medem pelo `helpers/contraste.ts`, que resolve
o `var()` a partir do arquivo. Errou a prosa escrita ao lado deles. Daí a regra:
número que vai para documento sai da varredura ou do helper, copiado da saída, e
não da conta feita à parte.

## Consertado agora: o link de pular

`components/layout/AppLayout.tsx:15` — `focus:bg-action focus:text-white`, que
no escuro dava **2,69:1**.

Não foi deixado para as Fases 11–16 por três motivos que se somam: é **casca**,
não página; é o **primeiro foco de toda página**; e existe **exclusivamente para
quem navega por teclado** — ou seja, a única pessoa que chega a vê-lo era
justamente a que não conseguia lê-lo.

A troca é para `focus:text-on-primary`, o token que a **E1** criou: branco no
claro, `primary-900` no escuro. **5,11:1** onde havia 2,69. Preso por teste em
`test/components/AppLayout.test.tsx`, que lê o arquivo — montar o `AppLayout`
arrastaria roteador e sessão para prender uma linha de classe.

## Os 19 que ficam

Nenhum deles é da Fase 7, e nenhum foi tocado.

| Onde | Par | Estado | claro | escuro |
|---|---|---|---:|---:|
| `components/layout/Topbar.tsx:116` | `bg-danger + text-white` | repouso | 3,76 | 3,76 |
| `components/layout/Topbar.tsx:319` | `bg-danger + text-white` | repouso | 3,76 | 3,76 |
| `pages/profile/ProfilePage.tsx:289` | `bg-danger + text-white` | repouso | 3,76 | 3,76 |
| `components/chat/ChatPanel.tsx:637` | `bg-primary + text-white` | repouso | 3,83 | 3,83 |
| `components/ui/Pagination.tsx:129` | `bg-primary + text-white` | repouso | 3,83 | 3,83 |
| `pages/calendar/CalendarPage.tsx:334` | `bg-primary + text-white` | repouso | 3,83 | 3,83 |
| `pages/calendar/CalendarPage.tsx:690` | `bg-primary + text-white` | repouso | 3,83 | 3,83 |
| `pages/dashboard/AdminDashboard.tsx:604` | `bg-primary + text-white` | repouso | 3,83 | 3,83 |
| `pages/dashboard/ClientDashboard.tsx:143` | `bg-primary + text-white` | repouso | 3,83 | 3,83 |
| `pages/kb/KBArticlePage.tsx:103` | `bg-primary + text-white` | repouso | 3,83 | 3,83 |
| `pages/kb/KBFormPage.tsx:316` | `bg-primary + text-white` | repouso | 3,83 | 3,83 |
| `pages/kb/KBListPage.tsx:174` | `bg-primary + text-white` | repouso | 3,83 | 3,83 |
| `pages/notifications/NotificationsPage.tsx:223` | `bg-primary + text-white` | repouso | 3,83 | 3,83 |
| `pages/onboarding/OnboardingPage.tsx:33` | `bg-primary + text-white` | repouso | 3,83 | 3,83 |
| `pages/profile/ProfilePage.tsx:161` | `bg-primary + text-white` | repouso | 3,83 | 3,83 |
| `pages/reports/ReportsPage.tsx:1033` | `bg-primary + text-white` | repouso | 3,83 | 3,83 |
| `pages/tickets/TicketFormPage.tsx:89` | `bg-primary + text-white` | repouso | 3,83 | 3,83 |
| `pages/tickets/TicketFormPage.tsx:94` | `bg-primary + text-white` | repouso | 3,83 | 3,83 |
| `pages/tickets/TicketListPage.tsx:433` | `bg-primary + text-white` | repouso | 3,83 | 3,83 |

**`components/ui/Pagination.tsx:129` não é código de tela** — é primitivo, e cai
na **Fase 9**. Já entra medido e reprovando.

**Os dois do `Topbar` não são botões**: são os contadores de não lidas, um no
cabeçalho do painel de notificações e outro no sino. Pintam `bg-danger` com
branco. Contam como "fundo cheio com texto por cima" do mesmo jeito, e o
conserto é o mesmo degrau.

Os outros 16 são botões de tela, das Fases 11–16, e se resolvem **por tela** e
não por componente, como manda a §25 — com a captura antes e depois.

## O guarda que falta

Esta varredura roda à mão. O guarda de verdade seria um teste que a executa e
falha quando aparece par novo, com os 19 conhecidos numa lista de exceção que
encolhe a cada fase. Não foi feito: com 19 em aberto ele nasceria como carimbo
de linha de base, e a lista de exceção é o tipo de coisa que sobrevive ao
problema que a criou. Cabe melhor na fase que começar a derrubá-los.
