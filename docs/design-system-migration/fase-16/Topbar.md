# §29 — `components/layout/Topbar.tsx`

Não é uma página: é a casca, e ela aparece em **todas** as 33 telas — a mesma
condição da `Sidebar`. Um defeito aqui não é de uma tela, é do produto.

Ela entra na Fase 16 por **34** classes de paleta crua, **7** `<svg>` soltos e
**2** `text-white` — e os dois `text-white` não eram decoração: eram os **dois
lugares** que a catraca de contraste ainda cobrava deste arquivo, o contador de
não lidas do sino e o contador do cabeçalho do painel, ambos `bg-danger` com
branco por cima, **3,76:1** nos dois temas.

421 linhas antes, 404 depois. O que encolheu foram os sete desenhos escritos por
extenso; o que cresceu foi o **porquê** de duas decisões — por que o
`theme === "dark"` fica e por que o realce de "não lida" mudou de cor.

---

## O que a casca tinha

| o que | quantos |
|---|---:|
| classes da paleta crua | **34** — todas `slate-*` |
| `<svg>` solto | **7** |
| `text-white` | **2** — os dois contadores |
| linhas da varredura de contraste | **4** (2 lugares × 2 temas) |
| hexadecimal cravado | **0** |
| mapa local de vocabulário compartilhado | **0** — `rotuloDePapel` já vinha de `lib/papel.ts` |
| `useTheme()` | **1**, e ele **fica** — ver abaixo |

O `NOTIF_TYPE_LABEL` continua local, e de propósito: ele tem **um** consumidor
(este arquivo) e é o rótulo de um tipo de notificação, não vocabulário
compartilhado. A regra que os agentes desta fase vinham aplicando — tabela com
um consumidor fica local, tabela com vários sobe — o deixa onde está. A
`NotificationsPage` tem o seu porque tem outro repertório de tipos e outra
apresentação; se um dia os dois divergirem em rótulo, aí é hora de subir.

---

## O que passou a usar

| módulo / primitivo | onde | quantos |
|---|---|---:|
| `Icon` (E20/E21) | os sete desenhos | **7** |
| `bg-action-danger` + `text-on-danger` | os dois contadores | **2** |
| `--action-tint` | o realce da notificação não lida | **1** |
| `text-conteudo-link` / `-link-hover` | "Marcar todas" e "Ver todas" | **2** |
| tokens semânticos de texto e superfície | o resto | 31 classes |

### Os 7 `<svg>`, e como cada um casou

Os sete tinham **exatamente** o envelope do primitivo — `viewBox="0 0 24 24"`,
`fill="none"`, `stroke="currentColor"`, `strokeWidth={2}`. Nenhum era 20×20,
nenhum era de preenchimento: a armadilha da estrela sólida do `AdminDashboard`
não aparece aqui. Conferidos campo `d` contra `ICON_PATHS_PACOTE`, caractere a
caractere.

| onde | virou | tamanho |
|---|---|---|
| recolher menu (desktop) | `menu` | `size={20}` |
| abrir menu (mobile) | `menu` | `size={20}` |
| sino de notificações | `bell` | `size={20}` |
| seta do menu do usuário | `chevronDown` | `size={16}` |
| "Meu perfil" | `user` | `size={16}` |
| "Modo escuro" | `moon` | `size={16}` |
| "Sair" | `logout` | `size={16}` |

A seta era `d="M19 9l-7 7-7-7"` e o pacote publica `chevronDown` como
`d="M6 9l6 6 6-6"`: **mesmo significado, traçado diferente** — uma seta de 14
unidades de largura contra uma de 12. Unificado pelo significado, que é o passo
2 do briefing. É a única troca desta tela que muda pixel, e ela muda para o
desenho que as outras 32 telas já usam.

### Os dois contadores, medidos

| par | claro | escuro |
|---|---:|---:|
| `bg-danger` + `text-white` (antes) | 3,76 | 3,76 |
| `bg-action-danger` + `text-on-danger` (depois) | **4,83** | **4,83** |

`--action-danger` é `--color-danger-600`, e o par dele é branco nos dois temas —
o fundo é um degrau absoluto da rampa, então ele não inverte. É a emenda E2 do
pacote, escrita para exatamente este caso.

### O `theme === "dark"` FICA, e o motivo importa

O briefing manda tirar `theme === "dark"` de dentro do JavaScript quando ele
**escolhe cor** — reimplementar o seletor `.dark` à mão. Aqui ele não escolhe
cor nenhuma: é o `checked` do `Switch`, ou seja, o **estado** do controle. Sem
ele o interruptor deixa de refletir o tema vigente, e o leitor de tela anuncia
"desmarcado" com o tema escuro ligado.

Também não é o caso de "qual ícone mostrar": a tela desenha **só** a lua, nos
dois temas, porque o rótulo é "Modo escuro" e o ícone ilustra o rótulo, não o
estado. O `sun` do pacote não é usado aqui.

Há caso de teste para isso (`o interruptor reflete o tema vigente`), e ele foi
validado por mutação: trocar `checked={theme === "dark"}` por `checked={false}`
o mata.

### O realce da notificação não lida mudou de cor, e isso é visível

Era `bg-slate-50` no claro e `bg-surface-elevated/40` no escuro — dois valores
escolhidos à mão, um por tema. No escuro ele **empatava com o hover**, que é
`--surface-elevated`: passar o mouse numa linha lida e numa não lida dava o
mesmo fundo.

Passou a ser `--action-tint`, que é o realce de ação do pacote, resolve por tema
sozinho e é **o mesmo token que a `NotificationsPage` usa para a mesma linha**
(migrada antes desta, com a mesma justificativa escrita no arquivo). Contraste
do corpo do texto sobre ele: 13,74 no claro, 10,73 no escuro.

O ponto azul de "não lida" acompanhou: era `bg-primary` (degrau de **marca**) e
passou a `bg-action` (degrau de **ação**), como a barra lateral de não lida da
`NotificationsPage`.

### O hover do menu deixou de ter dois valores

Três controles do painel do usuário pintavam `hover:bg-slate-50
dark:hover:bg-surface-elevated`. Agora é `hover:bg-surface-elevated` nos dois
temas — o token já inverte. O caso de contraste do botão "Sair" continua medindo
as **três** superfícies (`--surface`, `--bg-base`, `--surface-elevated`), de
propósito: `--bg-base` deixou de ser alcançado pelo hover, mas continua sendo o
fundo que a página desenha atrás do painel, e manter a medida impede que a
próxima passagem reintroduza um hover que reprove ali.

---

## O que resta à mão

**Contando, não julgando** — número maior que zero significa que alguém tem de
olhar, não que há trabalho pendente.

| o que | quantos |
|---|---:|
| `<svg>` solto | **0** |
| classe de paleta crua fora de comentário | **0** |
| hexadecimal cravado | **0** |
| linhas da varredura de contraste | **0** |
| **controles à mão** | **11** |

Os onze: **nove `<button>`** (recolher, abrir, sino, gatilho do menu do usuário,
"Marcar todas", cada linha de notificação, "Ver todas", "Meu perfil", "Sair") e
**dois painéis suspensos** (o de notificações e o do usuário), cada um com o seu
`useRef` + `mousedown` para fechar no clique de fora.

Por que ficaram: **o pacote não tem primitivo de menu suspenso**. Não existe
`Menu`, `Dropdown` nem `Popover` em `components/ui`. Criar um aqui seria
exatamente a variante local que esta migração existe para eliminar, e entrar no
pacote é emenda — que não se faz de dentro de uma tela. Os dois painéis estão
marcados com `aria-haspopup` e `aria-expanded`, então o defeito é de reuso, não
de acessibilidade.

---

## O que NÃO fiz, e por quê

- **Não criei um primitivo de menu suspenso.** Fora do escopo (`src/components/ui/**`);
  vai no relatório para o operador.
- **Não mexi no `NOTIF_TYPE_LABEL`.** Um consumidor só; subir para `lib/` seria
  decidir por outra tela que não é minha.
- **Não liguei os painéis ao teclado além do que já existe.** As linhas de
  notificação e os itens do menu são `<button>` de verdade, então `Tab` e
  `Enter` funcionam; o que falta é `Escape` fechar e o foco ficar preso dentro
  do painel. Isso é comportamento, não cor, e é o tipo de mudança que o briefing
  manda relatar em vez de decidir.
