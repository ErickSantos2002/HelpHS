# §29 — `components/layout/ChangelogModal.tsx`

A janela "O que há de novo?", aberta pelo rodapé da barra lateral. É a menor das
quatro telas desta passada — 97 linhas antes, 107 depois — e a única em que a
cor **carregava informação**: o tipo de cada entrada (novidade, corrigido,
melhoria) era dito em azul, laranja e verde.

Isso muda o que os testes precisam medir. Numa tela em que a cor é decoração, um
erro de migração é feio; aqui ele seria **silencioso**: a janela continuaria
bonita e deixaria de informar quem não distingue as três cores.

---

## O que a janela tinha

| o que | quantos |
|---|---:|
| classes da paleta crua | **21** — `blue`, `orange`, `emerald`, `slate` |
| `<svg>` solto | **3** |
| `text-white` | **1** — a pastilha da versão vigente |
| linhas da varredura de contraste | **0** |
| hexadecimal cravado | **0** |
| `useTheme()` | **0** |
| mapa local | **1** — `ENTRY_CONFIG`, e ele **fica** |

**Zero linhas na varredura não é o mesmo que estar certa.** O par mais fraco
desta janela é a pastilha da versão vigente, `bg-emerald-500` com `text-white`:
**2,54:1**, o pior número das quatro telas desta passada. A varredura não a via
porque `emerald-500` não é token do pacote, e o mapa de cores dela conhece
tokens. Medida à mão, com o hexadecimal do `--color-success-500` que é o mesmo
valor.

---

## O que passou a usar

| módulo / primitivo | onde | quantos |
|---|---|---:|
| `Icon` (E20/E21) | os três desenhos | **3** |
| trio tinta / par-da-tinta / borda a 30% | os três selos de tipo e o "Versão atual" | **4** |
| `bg-action-success` + `text-on-success` | a pastilha da versão vigente | **1** |
| `bg-tint-neutral` + `text-on-tint-neutral` | as pastilhas das versões antigas | **1** |
| tokens semânticos de texto | datas, textos, rodapé | 5 classes |

### Os 3 `<svg>`, e como cada um casou

Envelope idêntico ao do primitivo — 24×24, `fill="none"`,
`stroke="currentColor"` —, com `strokeWidth={2.5}` e `w-3 h-3`, que viraram
`size={12} strokeWidth={2.5}`. Conferidos caractere a caractere:

| tipo | traçado | virou |
|---|---|---|
| novidade | `M12 4v16m8-8H4` | `plus` — idêntico |
| corrigido | `M11 5H6a2 2 0 00-2 2v11…` | `edit` — idêntico |
| melhoria | `M13 7h8m0 0v8m0-8l-8 8-4-4-6 6` | `trendingUp` — idêntico |

O `trendingUp` entrou no pacote na **E21**, e este arquivo é um dos usos que a
justificaram.

### Por que NÃO é o `Badge`

O selo de tipo tem geometria própria: `px-2 py-0.5 text-[10px] font-semibold`
com `gap-1` entre ícone e rótulo. O primitivo é `px-2.5 py-0.5 text-xs
font-medium` e sem `gap`.

Passar a diferença por `className` **não funciona neste projeto**: o `cn` de
`lib/utils.ts` é um `clsx` — ele concatena e não resolve conflito. `tailwind-merge`
não está instalado. Com `px-2.5` e `px-2` os dois vivos, quem vence é a ordem do
CSS gerado, que é interna ao Tailwind e não tem relação com a ordem no atributo.

Então as **três classes de cor** do `Badge` foram copiadas por extenso
(`bg-tint-* text-on-tint-* border-*/30`) e a geometria ficou como estava. Não é
cor local: é a mesma receita do pacote, escrita no lugar onde o primitivo não
cabe. Está anotado no arquivo, com o motivo.

### As cores medidas, sobre o fundo real do selo

Os selos assentam em `--surface-elevated` (o cartão de cada entrada), e as
tintas carregam alfa de 15% — sem a superfície por baixo o número é fantasia.

| selo | claro | escuro |
|---|---:|---:|
| Novidade — `tint-info` + `on-tint-info` | 5,20 | 6,21 |
| Corrigido — `tint-success` + `on-tint-success` | 6,15 | 5,51 |
| Melhoria — `tint-success` + `on-tint-success` | 6,15 | 5,51 |

A lista que o teste mede sai do **próprio arquivo**, e não escrita à mão: se
alguém trocar a variante de um tipo, é a tinta nova que passa a ser medida.

E a pastilha da versão:

| par | claro | escuro |
|---|---:|---:|
| `bg-emerald-500` + `text-white` (antes) | 2,54 | 2,54 |
| `bg-action-success` + `text-on-success` (depois) | **5,48** | **5,48** |

### Segunda passada — a variante sai do SIGNIFICADO, não da cor que estava aqui

A primeira passada traduziu **cor por cor**: azul→`info`, laranja→`warning`,
verde→`success`. Isso preserva a aparência e **não é o critério do pacote** — a
cor antiga não tinha sido decisão de ninguém, era o que estava lá. O operador
corrigiu o critério e decidiu `corrigido` → `success`.

| tipo | antes (por cor) | agora (por significado) | por quê |
|---|---|---|---|
| `novidade` | `info` | **`info`** | é um **anúncio**: algo passou a existir. Não é resultado bom nem ruim — é informação, que é o que `info` significa em toda a interface (o `Alert`, o papel "Técnico"). Mesma variante, motivo diferente. |
| `corrigido` | `warning` | **`success`** | um defeito foi **resolvido**. Decisão do operador, e é a leitura certa: o laranja dizia "atenção", e não há a que atentar num defeito que já saiu. |
| `melhoria` | `success` | **`secondary`** — resolvido pela **E23** | ver abaixo |

### `melhoria` esteve sem casa, e o motivo era medido — a E23 resolveu

> **Atualizado em 09/09/2026.** O que segue descreve o estado de ANTES da
> emenda **E23**, e fica porque é o raciocínio que a produziu: foi ao
> procurar uma sexta aparência que se descobriu que só havia quatro.
>
> **Depois da E23**, `--tint-neutral` é `rgb(100 116 139 / 0.15)` e separa
> 7,3 / 7,6 / 7,0 do fundo no claro e 6,5 / 5,8 / 4,8 no escuro. `melhoria`
> passou a `secondary`, e os três tipos têm três aparências distintas.
>
> ⚠️ A margem do escuro é de **0,05**: `--on-tint-neutral` sobre a tinta na
> superfície elevada dá 4,55:1 contra o piso de 4,5. Quem escurecer o
> `--text-muted` do escuro quebra este selo.

"Algo que já existia ficou melhor" não é nenhuma das seis tintas. E o problema
não é de gosto: sobre o cartão desta janela (`--surface-elevated`) as seis só
oferecem **quatro** aparências distintas.

| candidata | por que não serve | medida |
|---|---|---|
| `success` | é de `corrigido` agora | — |
| `primary` | é o **mesmo azul** de `info` | ΔE76 **4,5** claro / **5,7** escuro; razão **1,01:1**. O piso do próprio pacote para série distinguível (E16-b) é ΔE ≥ 20 |
| `neutral` | é **alias de `--surface-elevated`**, que é o fundo do cartão: o selo perderia a forma | ΔE76 **0,0**; razão **1,00:1** |
| `warning` | diz "atenção"; não há a que atentar numa melhoria | — |
| `danger` | tom errado | — |

Então `melhoria` fica em `success` e passa a ser **gêmea de `corrigido`**. O que
se perde é a cor *acrescentar* uma distinção entre as duas; o que **não** se
perde é a informação, porque o rótulo é escrito ao lado do ícone. **1.4.1
continua satisfeito — a cor nunca foi o único portador**, e há caso de teste que
prende os dois rótulos na tela justamente por causa da gêmea.

Sair disto é decisão de quem desenha o pacote: ou se aceita a gêmea, ou entra
uma sexta tinta distinguível por emenda. Está no relatório para o operador.

O caso de teste que trava `melhoria` em `success` é **trava deliberada, não
aprovação**: quem der casa própria a ela troca aquele número de propósito, e
não por acidente.

### A expressão do teste exige o trio INTEIRO, e isso não é detalhe

O caso lê `bg-tint-X text-on-tint-X border border-X/30` com retrovisão: fundo,
texto e borda têm de vir da **mesma** tinta. Meia troca — fundo novo com texto
velho — é exatamente o modo de falha que a **E8** documentou no `Badge`, e
passaria por uma verificação que olhasse só o fundo.

A mutação que provou isso também achou um defeito no próprio teste: a primeira
versão do leitor fatiava do tipo até o **fim do arquivo**, então uma entrada
mutada para um trio inconsistente devolvia em silêncio a variante da entrada
**seguinte**. O recorte agora termina no `icon:` da própria entrada.

### As opacidades: nenhuma fora da escala

O arquivo usava `/15` e `/25`, e as duas estão na escala padrão do Tailwind (de
cinco em cinco, 0 a 100) — **nenhuma classe morta sobrou aqui**. As novas usam
`/30`, que é a receita do `Badge`. Há caso de teste que varre o arquivo inteiro
atrás de modificador fora da escala, e ele foi validado por mutação: trocar
`/30` por `/8` o mata.

---

## O que resta à mão

| o que | quantos |
|---|---:|
| `<svg>` solto | **0** |
| classe de paleta crua fora de comentário | **0** |
| hexadecimal cravado | **0** |
| linhas da varredura de contraste | **0** |
| controles à mão | **0** — a janela é `Modal`, e não tem botão próprio |
| selos com geometria própria | **4** — motivo acima |

O `ENTRY_CONFIG` fica: é um mapa de **um** consumidor, e o vocabulário dele
(novidade / corrigido / melhoria) não existe em nenhuma outra tela.

---

## O que NÃO fiz, e por quê

- **Não usei o `Badge`.** Motivo acima; a alternativa seria mudar o tamanho dos
  quatro selos, e tamanho de selo é decisão de desenho.
- **Não instalei `tailwind-merge`.** `package.json` está fora do escopo, e a
  troca do `cn` mexeria em todo o front.
- **Não mexi em `data/changelog.ts`.** Fora do escopo, e nada nele é cor.
