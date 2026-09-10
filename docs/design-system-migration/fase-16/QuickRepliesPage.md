# §29 — `pages/settings/QuickRepliesPage.tsx`

As respostas rápidas: as mensagens prontas que a equipe insere no chat digitando
`/atalho`. Uma lista com busca, um modal de formulário e um de confirmação.

Ela entra na Fase 16 por **26** classes de paleta crua, **2** `<svg>` em
componentes locais de ícone e **um** par que a catraca cobrava — e esse par tem
um detalhe que os outros seis do sistema não têm: **ele só existe no tema
escuro**.

389 linhas antes, 382 depois.

---

## O que a tela tinha

| o que | quantos |
|---|---:|
| classes da paleta crua | **26** — `slate-*` e `red-*` |
| `<svg>` solto | **2** |
| componente local de ícone | **2** (`IconEdit`, `IconTrash`) |
| `text-white` | **0** |
| rampa semântica como cor de TEXTO | **3** — `text-danger-400`, `text-success-700`, `dark:text-success-400` |
| linhas da varredura de contraste | **1** |
| hexadecimal cravado | **0** |
| `useTheme()` | **0** |
| mapa local de vocabulário compartilhado | **0** |

### O par que só existia no escuro

O selo "Inativa" era:

```
"bg-slate-200 text-slate-600 dark:bg-surface-elevated dark:text-slate-500"
```

Quatro classes, duas por tema, para pintar o que um par de tokens pinta sozinho.
No claro passava; no escuro, `dark:text-slate-500` sobre
`dark:bg-surface-elevated` dá **2,85:1**.

O detalhe de método: **quem conferisse um tema só daria a tela por conforme**. É
o mesmo modo de falha da armadilha 6 da varredura, do outro lado — ali era o
scanner que media o tema errado, aqui seria a pessoa.

O selo "Ativa" tinha o defeito simétrico e mais barato: `bg-success/10` com
`text-success-700 dark:text-success-400` — a cor cheia da rampa com opacidade e
o degrau de texto escrito à mão com `dark:` para inverter. É exatamente o que a
E8 corrigiu no `Badge` e não alcançou aqui, porque **corrigir o token não
alcança quem não o usa**.

---

## O que passou a usar

| módulo / primitivo | onde | quantos |
|---|---|---:|
| `Icon` (E20/E21) | editar e excluir | **2** |
| `bg-tint-*` + `text-on-tint-*` | selo Ativa, selo Inativa, chip do atalho | **3** |
| `hover:bg-tint-*` + `hover:text-on-tint-*` | os dois botões de ação da linha | **2** |
| tokens semânticos de texto e superfície | o resto | 19 classes |

### Os 2 `<svg>`, e como cada um casou

Envelope idêntico ao do primitivo — 24×24, `fill="none"`,
`stroke="currentColor"`, `strokeWidth={2}`, `w-4 h-4` → `size={16}`.
Conferidos caractere a caractere contra `ICON_PATHS_PACOTE`:

| componente local | virou | como casou |
|---|---|---|
| `IconEdit` | `edit` | idêntico |
| `IconTrash` | `trash` | idêntico |

Os dois componentes locais saíram do arquivo.

### O selo de estado, medido

| selo | par novo | claro | escuro |
|---|---|---:|---:|
| Ativa | `bg-tint-success` + `text-on-tint-success` | **6,67** | **6,48** |
| Inativa | `bg-tint-neutral` + `text-on-tint-neutral` | **6,92** | **5,29** |

É o mesmo trio que o `Badge` do pacote pinta. O `Badge` não foi usado porque o
selo aqui é `text-[10px] rounded-md` e o primitivo é `text-xs rounded-full` — e
o `cn` deste projeto concatena em vez de resolver conflito, então passar a
diferença por `className` deixaria as duas regras vivas. Mesma situação do
`ChangelogModal`, com o mesmo motivo escrito lá.

### O botão de excluir deixou de ter quatro classes de hover

Era `hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20
dark:hover:text-red-400` — paleta crua, quatro classes, dois temas à mão.
Passou a `hover:bg-tint-danger hover:text-on-tint-danger`, que é o par do
pacote e é o mesmo que o `SettingsPage` e o `GroupsPage` já usam para o mesmo
botão.

### O asterisco de obrigatório

`text-danger-400` — rampa semântica como cor de texto, §3.2. Foi para dentro do
rótulo (`Atalho *`), como no `ProfilePage`.

---

## O que resta à mão

| o que | quantos |
|---|---:|
| `<svg>` solto | **0** |
| classe de paleta crua fora de comentário | **0** |
| hexadecimal cravado | **0** |
| linhas da varredura de contraste | **0** |
| **controles à mão** | **4** |
| **rótulos sem `htmlFor`** | **0** |
| **campos sem rótulo nenhum** | **1** — a busca da lista |

Os quatro: dois `<input>` crus (o campo de atalho e a busca da lista) e dois
`<button>` de ícone (editar e excluir). Os dois botões têm `aria-label` com o
atalho dentro, então são alcançáveis; o que falta neles é o `Button` do pacote,
que não tem variante de ícone-só nesta escala.

A **busca** não tem `<label>` nenhum — o nome acessível dela vem do
`placeholder`, que é um recuo, não um rótulo: some quando a pessoa digita. Isso
é diferente do defeito de rótulo solto que o operador mandou consertar, e vai no
relatório.

O restante da tela já era do pacote: `Card`, `Modal`, `ModalFooter`, `Button`,
`Input`, `Textarea`, `Checkbox`, `Alert`, `Spinner` e `Pagination`.

---

## Segunda passada — o rótulo do atalho, ligado à mão

Aprovado pelo operador. 382 linhas antes, 411 depois.

O `<label>` do atalho não tinha `htmlFor` e o `<input>` não tinha `id`. **Este é
o único campo das duas telas que não foi para o primitivo**, e a regra que o
operador deu era essa: se o primitivo couber, use-o; se não couber, ligue à mão
e diga por quê.

### Por que o `Input` não cabe aqui

O `/` à esquerda é **irmão do campo** dentro de uma linha `flex`, e o `Input`
não tem slot de prefixo: ele desenha `div.flex-col > label + input + p`, então a
barra ficaria ao lado do **bloco inteiro** (rótulo, campo e dica), centrada
verticalmente contra os três.

A saída de posicionar a barra por cima do campo — como o `ProfilePage` faz com o
`Spinner` — também não serve: lá o `bottom-2.5` acerta o campo porque **não há
dica embaixo**; aqui há, e o mesmo deslocamento cairia sobre o texto da dica.

### O que a ligação manual repôs

| do primitivo | reposto? |
|---|---|
| `htmlFor` + `id` do `useId` | sim |
| `aria-describedby` amarrando a dica ao campo | sim |
| `aria-invalid` | **não**, e não teria uso: o erro deste formulário é um `Alert` no topo, não uma mensagem por campo |

Há caso próprio para os três — e ele existe justamente por ser manual: a ligação
do primitivo é conferida no teste do primitivo, esta não seria conferida em
lugar nenhum.

O caso que clica no rótulo **tira o foco do campo antes**: ele nasce com
`autoFocus`, e sem esse passo o caso passaria com o `htmlFor` apagado.

---

## O que NÃO fiz, e por quê

- **Não usei o `Badge` nos selos.** Geometria diferente e `cn` sem
  `tailwind-merge`; motivo detalhado na ficha do `ChangelogModal`.
- **Não troquei os dois `<input>` crus pelos primitivos.** O de atalho não cabe
  (motivo acima); o da busca não tem rótulo para ligar — dar um a ele é decisão
  de desenho (rótulo visível? `aria-label`?) e vai no relatório.
- **Não mexi no `sanitizeShortcut` nem no `quickReplyService`.** Fora do escopo
  e nada neles é cor.
