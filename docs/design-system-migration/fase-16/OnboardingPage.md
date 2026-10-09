# §29 — `pages/onboarding/OnboardingPage.tsx`

O passo a passo de primeiro acesso: empresa, equipamentos, pronto. É a primeira
tela que um cliente novo vê depois do cadastro, e a única das quatro desta
passada que **não tinha um único `<svg>`**.

Ela entra na Fase 16 por **28** classes de paleta crua e por **três** dos sete
pares que a catraca ainda cobrava do sistema inteiro — e os três moravam no
mesmo componente de 25 linhas: o indicador de passo.

538 linhas antes, 553 depois. Cresceu só de comentário.

---

## O que a tela tinha

| o que | quantos |
|---|---:|
| classes da paleta crua | **28** — todas `slate-*` |
| `<svg>` solto | **0** |
| `text-white` | **1** — a bola do passo cumprido |
| rampa semântica como cor de TEXTO | **2** — os dois asteriscos `text-danger-400` |
| linhas da varredura de contraste | **3** (todas na linha 33) |
| hexadecimal cravado | **0** |
| `useTheme()` | **0** |
| mapa local de vocabulário compartilhado | **0** |

### As três bolas do `StepIndicator`

As três reprovações estavam nas três bolas do indicador, e são o retrato das
regras §3.3 e §3.4 do briefing na mesma linha de código:

| bola | par antigo | claro | escuro |
|---|---|---:|---:|
| passo **cumprido** | `bg-primary` + `text-white` | 3,83 | 3,83 |
| passo **futuro** | `bg-surface-elevated` + `text-slate-500` | 4,34 | 2,85 |

O passo cumprido é a §3.3 escrita à mão: `bg-primary` é o degrau de **marca**, e
o par de branco dele dá 3,83:1. O degrau de **ação** existe separado justamente
para isto.

O passo futuro é a §3.4: `slate-500` sobre superfície elevada. O degrau mais
próximo que o pacote tem é `--text-faint`, e ele dá **2,34** no claro sobre a
mesma superfície — o par simplesmente não existe.

---

## O que passou a usar

| módulo / primitivo | onde | quantos |
|---|---|---:|
| `bg-action` + `text-on-primary` | bola do passo cumprido e traço de ligação | **2** |
| `bg-action-tint` + `border-action` + `text-on-tint-primary` | bola do passo corrente | **1** |
| `--action-tint` / `--action-tint-border` | o círculo do ✓ final | **1** |
| `text-conteudo-link` / `-link-hover` | o "Deslogar" do rodapé | **1** |
| tokens semânticos de texto e superfície | o resto | 24 classes |

### As três bolas, depois

| bola | par novo | claro | escuro |
|---|---|---:|---:|
| cumprido | `bg-action` + `text-on-primary` | **5,29** | **5,11** |
| corrente | `bg-action-tint` + `text-on-tint-primary` | **7,06** | **6,66** |
| futuro | `bg-surface-elevated` + `text-conteudo-muted` | **6,92** | **5,29** |

### Os dois asteriscos de obrigatório

Eram `<span className="text-danger-400">*</span>` — a rampa semântica pintada
como cor de texto, que a §3.2 reprova, **e** um elemento sem ligação nenhuma com
o campo que ele qualifica. Passaram para dentro do texto do rótulo (`CNPJ *`,
`CEP *`), que é o que o `ProfilePage` e o `ProductsPage` já fizeram nesta fase e
está anotado no `ProfilePage.tsx` com o motivo: quem usa leitor de tela ouve o
asterisco junto do nome do campo em vez de um `<span>` colorido solto.

### O círculo do ✓ final, e o que mudou nele

Era `bg-primary/20 border-2 border-primary/40` — dois modificadores de opacidade
escolhidos à mão sobre o degrau de marca. Nenhum dos dois é paleta crua, então a
catraca não reclamava; mas no escuro `primary/20` é 20% do degrau 500 sobre um
fundo escuro, que é outra cor que a do claro. Passou a `bg-action-tint
border-2 border-action-tint-border`, que é o par que o pacote publica para o
realce de ação e resolve por tema sozinho.

O ✓ ganhou `text-on-tint-primary` — antes herdava o corpo do texto. **Isso é
visível**: o certo passa de cinza-escuro para o azul do par da tinta. Está no
relatório para o operador.

### A assinatura "HelpHS" ficou como estava

`text-primary` no "HS" é a **cor de marca**, e a assinatura fica em 24px negrito
— texto grande pela WCAG, piso de 3:1. Sobre o `--bg-base` desta tela o degrau
dá **3,66** no claro e **4,55** no escuro: passa em AA-grande nos dois, e
reprovaria em AA-normal no claro se um dia encolhesse. Trocar por `--text-link`
mudaria a assinatura do produto, e isso não se decide dentro de uma tela. Está
anotado no arquivo.

---

## O que resta à mão

| o que | quantos |
|---|---:|
| `<svg>` solto | **0** |
| classe de paleta crua fora de comentário | **0** |
| hexadecimal cravado | **0** |
| linhas da varredura de contraste | **0** |
| **controles à mão** | **1** |
| **rótulos sem `htmlFor`** | **0** |

O único controle à mão é o "Deslogar" do rodapé, um `<button>` estilizado como
link. O `Button` do pacote não tem variante de link, e criar uma é emenda.

---

## Segunda passada — os quatro rótulos soltos

Aprovado pelo operador depois do relatório da primeira passada. 553 linhas
antes, 550 depois: os quatro blocos de campo escritos à mão encolheram para
quatro chamadas de primitivo.

O defeito era o mesmo nos quatro: `<label>` sem `htmlFor` sobre um controle sem
`id`. Ficavam um em cima do outro na tela e **não tinham relação nenhuma na
árvore de acessibilidade** — quem usa leitor de tela ouvia "edição, em branco"
e nada mais, e quem clica no rótulo não focava o campo.

| campo | virou | o que resolveu |
|---|---|---|
| CNPJ | `Input` dentro de `div.relative` | rótulo ligado + `Spinner` por cima, receita do `ProfilePage` |
| CEP | `Input` dentro de `div.relative` | idem |
| Estado (UF) | `Input` | direto, sem envoltório |
| Produto | `Select` | com `id` explícito — ver abaixo |

O `Input` do pacote resolve três coisas de uma vez: o `id` vem do `useId`, o
`htmlFor` sai ligado, e vêm de brinde o `aria-invalid` e o `aria-describedby`.

**O `id` do `Select` vai explícito de propósito.** O primitivo, sem ele, deriva
o id do rótulo em minúsculas — e dois seletores de mesmo rótulo na mesma tela
gerariam o **mesmo** `id`. É o defeito que o `Input` já corrigiu com `useId` e
que o `Select` ainda tem. Aqui há um seletor só, mas o defeito nasce silencioso
e fechá-lo não custa nada. Vai no relatório como candidato a emenda no
primitivo.

### O efeito visível: a tela deixou de ter dois estilos de campo

Antes, "Nome da empresa", "Endereço" e "Cidade" já vinham do `Input` (rótulo de
14px, fundo `--surface`) e os quatro à mão tinham rótulo de 12px sobre fundo
`--surface-elevated`. Os dois estilos apareciam lado a lado na mesma coluna.
Agora são um só. Está no relatório para o operador.

---

## O que NÃO fiz, e por quê

- **Não mexi na assinatura da marca.** Decisão de desenho.
- **Não removi o ramo morto** da mensagem `"Nome da empresa é obrigatório."`
  (ver abaixo).
- **Achei um ramo morto e não o removi**: a mensagem `"Nome da empresa é
  obrigatório."` nunca aparece, porque o campo é um `Input` com `required` e o
  navegador barra o envio antes de o `handleSubmit` rodar. Removê-la seria
  apagar uma rede de segurança que volta a valer se alguém tirar o `required`.
  O caso de teste que existe hoje exercita o guarda **alcançável** (o do CNPJ) e
  documenta o morto no comentário.
