# §29 — `pages/users/UsersPage.tsx`

A tela que lista e edita usuários: papel (admin/técnico/cliente), estado de
conta, três modais e a paginação do servidor. 626 linhas antes, 712 depois.

---

## O que a tela tinha

| o que | quantos |
|---|---:|
| classes da paleta crua do Tailwind | **81** |
| `<svg>` solto, num mapa local `IC` | **5** |
| hexadecimal cravado | 0 |
| cor cheia semântica como texto | 0 |
| linhas da varredura de contraste | **3** (2 lugares: `:136` e `:529`) |
| mapas locais | **8** |
| controles à mão | **7** |

Os oito mapas locais, em três grupos:

| grupo | constantes | o que duplicavam |
|---|---|---|
| papel | `ROLE_LABEL`, `ROLE_BADGE`, `ROLE_OPTIONS`, `FILTER_ROLE_OPTIONS` | quatro cópias no MESMO arquivo — as duas últimas idênticas linha a linha |
| estado da conta | `STATUS_LABEL`, `STATUS_DOT`, `STATUS_PILL` | três colunas da mesma tabela, separadas |
| ícone | `IC` | cinco traçados que já existiam no pacote |

As **31** classes cruas mais concentradas estavam na pílula de estado, que
pintava `emerald`/`slate` com **oito `dark:`** para inverter à mão o que o
token inverte sozinho.

Os dois pares que a varredura reprovava eram o mesmo: `bg-surface-elevated` +
`text-slate-600`, **2,34:1** no claro e **1,79:1** no escuro — o disco do avatar
local (`:136`) e o disco do vazio (`:529`).

---

## O que passou a usar

| módulo / primitivo | onde | quantos |
|---|---|---:|
| `Icon` (E21) | os 5 do mapa `IC` | 6 usos |
| `Avatar` | o `UserAvatar` local, na linha e no cartão do modal | 2 |
| `Badge` | o selo de papel, na linha e no cartão | 2 |
| `Input` | o campo de busca, que era `<input>` à mão | 1 (+8 que já eram) |
| `Button` com `icon=` | "Novo usuário" | 1 |
| tintas + pares (`bg-tint-*` / `text-on-tint-*`) | pílula de estado, painel de exclusão | 2 blocos |
| `bg-fill-success` (E19) | o ponto da pílula de "Ativo" | 1 |
| `bg-borda-control` | o ponto dos dois estados neutros | 2 |
| escada de texto (`text-conteudo*`) | todo o texto da tela | 22 lugares |
| `text-conteudo-link` | "Criar o primeiro usuário", hover de "Editar" | 2 |

`Card`, `Modal`, `ModalFooter`, `Pagination`, `Select`, `Spinner`, `Alert` e
`FilterSelect` já eram primitivos e ficaram como estavam.

### Os cinco ícones, e como cada um casou

Os cinco eram `viewBox="0 0 24 24"` com `fill="none"` e `stroke="currentColor"`
— mesma família do `Icon`, **conferido antes de trocar**. E os cinco casaram
**pelo traçado, caractere a caractere**: `edit`, `trash`, `user`, `plus` e
`search`. Nenhum precisou casar por significado, e nenhum ícone novo foi
preciso.

### O papel: quatro cópias viram uma, e a casa dela não é aqui

`PAPEIS` é uma tabela só, com `as const` para que `variante` infira os literais
do `Badge` em vez de `string` — um papel novo com variante inexistente para de
compilar. Os acessores (`rotuloDePapel`, `varianteDePapel`) **recuam para o dado
cru**, pela mesma razão dos módulos de `lib/`: `role` vem da rede, e um papel
novo no backend não pode derrubar a lista.

A variante de cada papel é a que as classes cruas já diziam, traduzida:
`primary` para admin (era `bg-primary/15 text-primary`), `info` para técnico
(era `bg-info/15 text-info-700`), `muted` para cliente (era `slate`). **Não é
escolha nova.**

⚠️ **A tabela continua local, e isso é uma fonte única que falta.** A mesma
existe em `layout/Topbar.tsx`, `profile/ProfilePage.tsx` e `kb/KBArticlePage.tsx`
— e as quatro **já divergem**: a da KB diz "Admin" onde as outras dizem
"Administrador". Um `lib/papel.ts` ao lado de `status.ts` e `prioridade.ts` é o
conserto, e criá-lo é escrita em `src/lib`, fora do escopo. O que dava para
fazer daqui foi reduzir quatro cópias locais a uma. Está no relatório.

### O estado da conta: local de propósito, com a disciplina dos módulos

`ESTADO_DA_CONTA` **não** consome `lib/status.ts`, e não é descuido: aquele
módulo é dos sete estados de um **chamado**, e `active`/`inactive`/`anonymized`
são estado de **conta**. Mesmo nome, coisa diferente — consumir de lá faria a
tela pintar conta com a tabela de chamado. É a mesma decisão que a
`AuditLogsPage` tomou com as ações de auditoria, pelo mesmo motivo: um
consumidor só.

O que ela ganhou foi a **disciplina** dos módulos: rótulo, classes e ponto na
mesma linha, classes **por extenso** (`"bg-tint-" + estado` some da varredura do
Tailwind, a regra não nasce e a pílula fica sem fundo, sem erro nem aviso), e um
acessor `estadoDaConta()` que recua para o neutro com o valor cru no rótulo. Os
valores continuam saindo de `UserStatus`, que o teste do `userService` compara
com o enum do backend.

**O hover é de borda, e não de fundo.** Regra (a) do D8-a: os `--tint-*` já
trazem 15% de alfa no token, então `hover:bg-tint-success/30` multiplicaria
0,15 × 0,30 e daria um realce praticamente invisível — e subir para /50
continua multiplicando.

**Anonimizado pinta igual a inativo**, e é deliberado: quem carrega a diferença
é a palavra, não a cor. Duas faixas de cinza a distinguiriam para quem enxerga e
para mais ninguém, e o que o estado tem de próprio — não dá para alternar — está
no botão desabilitado, que é canal não visual.

### O painel de exclusão

`bg-red-50` / `border-red-200` / `bg-red-100` / `text-red-700` / `text-red-500/80`
com cinco `dark:` viraram `bg-tint-danger` + `border-danger/30` +
`text-on-tint-danger`. O disco repete `bg-tint-danger` de propósito: a tinta tem
alfa, então a segunda camada **soma** sobre a primeira e dá o degrau mais forte
que o `red-100` sobre `red-50` dava — sem modificador de opacidade, que nas
tintas multiplicaria em vez de somar.

### O que a migração acrescentou de acessibilidade

Três coisas, e nenhuma delas é enfeite:

1. **O campo de busca não tinha nome.** Só `placeholder`, que não é nome
   acessível: quem navega por leitor de tela chegava num campo de texto anônimo
   no meio da barra de filtros. Ganhou `aria-label="Buscar usuários"`.
2. **Os controles de linha eram N com o mesmo nome.** Dez cadastros davam dez
   botões chamados "Editar" e dez chamados "Excluir". O nome do usuário entrou
   no `aria-label`; o `title` ficou curto, porque é dica de mouse e o mouse já
   sabe em que linha está. Mesmo conserto que o `ReportsPage` fez com "Detalhes".
3. **O foco não estava fraco, estava ausente** nos cinco botões à mão — o mesmo
   defeito da emenda **E9**. Todos ganharam `focus-visible:ring-action`.

---

## O que resta à mão — a contagem

**Contar, não julgar**: um número maior que zero significa que alguém tem de
olhar, não que há trabalho pendente.

| o que | quantos | observação |
|---|---:|---|
| classe de paleta crua | **0** | era 81 |
| `<svg>` solto | **0** | era 5 |
| hexadecimal em código | **0** | era 0 |
| linhas da varredura de contraste | **0** | eram 3, em 2 lugares |
| `theme` lido em JavaScript | **0** | nunca houve |
| mapas locais | **2** | `PAPEIS` e `ESTADO_DA_CONTA`, de 8 — ver acima por que continuam locais |
| `<input>` à mão | **0** | a única ocorrência restante é texto de comentário |
| controles à mão | **5** | ver abaixo |

Os cinco controles à mão:

1. **`StatusPill`** — o selo que alterna ativo/inativo. Continua botão escrito à
   mão porque `Badge` é um `<span>`, e envolvê-lo num botão seria empilhar duas
   cascas. ⚠️ **É uma de três cópias divergentes do mesmo componente no
   sistema**: existe como botão que alterna aqui e na `ProductsPage`, e como
   `<span>` que só mostra na `EquipmentPage`. A daqui é a única com **três**
   estados. Unificá-las é escrita em `components/ui`, fora do escopo — e três
   agentes inventando três abstrações é exatamente o defeito que esta migração
   elimina. Registrado, não consertado;
2. **"Limpar filtros"** — botão de texto de 12px na barra de filtros. `Button
   variant="ghost" size="sm"` traz padding e altura próprios e empurraria a
   barra; é mudança de leiaute, não de sistema de design;
3. **"Criar o primeiro usuário"** — link de texto dentro do estado vazio, mesmo
   motivo;
4. **"Editar"** e **5. "Excluir"** — botões de ícone de 16px. O `Button` do
   pacote não tem variante só-ícone; usá-lo aqui daria um alvo com o dobro do
   tamanho e quebraria a densidade da linha.

Os cinco ganharam `type="button"` e anel de foco.

---

## O que NÃO foi feito, e por quê

- **`lib/papel.ts`.** É a fonte única que falta, com quatro consumidores e uma
  divergência já viva ("Admin" × "Administrador"). Criá-lo é escrita em
  `src/lib`, fora do escopo de uma tela. **A decisão de onde ele mora não é do
  agente da tela.** Relatado ao operador.
- **Unificar os três `StatusPill` do sistema.** Escrita em `components/ui`,
  fora do escopo. Registrado acima.
- **Trocar a lista por `Table`.** A lista **não é uma `<table>`**: é uma pilha
  de linhas em flex, com quatro colunas que somem por breakpoint
  (`hidden sm:`, `hidden md:`, `hidden xl:`). Convertê-la é redesenho de
  leiaute responsivo, que é decisão de desenho e não de sistema de design.
- **Mostrar a foto do usuário.** `UserSummary.avatar_url` existe e a tela nunca
  o usou; o `Avatar` do pacote aceita `src`. Passá-lo faria a tela mostrar algo
  que ela não mostrava — mudança funcional. Relatado.
- **`Selector` no lugar de `FilterSelect`.** O invólucro `@deprecated` continua
  em uso nas telas já migradas (`AuditLogsPage`, `TechnicianDashboard`,
  `AdminDashboard`), e o próprio `FilterSelect` diz que o nome sai quando a
  última chamada sair. Trocar só esta tela deixaria a frota em dois idiomas.

---

## Testes

`src/test/pages/UsersPage.test.tsx`, **10 casos**, todos validados por mutação.
Nenhum caso olha classe: happy-dom não aplica CSS, então asserção de classe
mede o contrário do que interessa — passaria com `sr-only` presente e o
elemento invisível de verdade. Todos os casos leem pelo que o usuário alcança:
papel acessível, nome acessível, texto na tela.

Onze mutações, todas **no elemento**, e o que cada uma matou:

| mutação | casos que morreram |
|---|---|
| `rotuloDePapel` devolve o valor cru | o papel escrito |
| a pílula perde a palavra e fica só com o ponto | o estado escrito; a conta anonimizada |
| some a guarda de `anonymized` no `toggle` | a conta anonimizada |
| as ações de linha voltam ao nome genérico "Editar"/"Excluir" | os controles por linha; excluir; editar |
| o campo de busca perde o `aria-label` | a busca; os dois vazios |
| a busca deixa de ir ao servidor (`search: undefined`) | a busca |
| o convite "Criar o primeiro usuário" aparece também com filtro | os dois vazios |
| o contador perde a concordância de número | o contador |
| o cartão de pré-visualização sai dos dois modais | excluir; editar |
| o filtro de estado ganha "Anonimizado" | o filtro de estado |
| a lixeira da linha exclui direto, sem o modal | excluir |

Cada um dos 10 casos morreu em pelo menos uma mutação. As duas de nome
acessível (a das ações e a da busca) mataram **mais** casos do que os seus —
sinal de que os casos de excluir, editar e vazio dependem do nome do controle
para alcançá-lo, o que é o comportamento certo: se o nome sumir, a tela deixa de
ser navegável por quem não a vê, e os testes param junto.

---

## Verificação

| conferência | resultado |
|---|---|
| `npx vitest run src/test/pages/UsersPage.test.tsx` | **10 passaram** |
| `npx tsc --noEmit -p tsconfig.app.json` | sem erro nesta tela |
| `npx eslint` nos dois arquivos | limpo |
| `varredura-contraste.mjs` \| `grep UsersPage` | **nenhuma linha** (eram 3, em 2 lugares) |
| paleta crua | **0** (eram 81) |
| `<svg>` solto | **0** (eram 5) |
| hexadecimal | **0** (era 0) |
| cor cheia semântica como texto | **0** (era 0) |
