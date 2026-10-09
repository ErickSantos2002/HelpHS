# Fase 8 — Formulários — HelpHS

Relatório no formato da seção 32. **Em andamento** — este arquivo cresce a cada
componente e fecha com a fase.

## ⛔ Correção de uma afirmação publicada errada

**O commit `32a3bb2` (`Textarea`) contém uma explicação falsa, e ela não foi
reescrita de propósito.** A correção mora aqui.

### O que eu publiquei

> O espelho do desvio D5 no `index.css` é `html:not(.dark) .text-slate-500`, e a
> classe aqui era `placeholder:text-slate-500` — **token de classe diferente, o
> seletor não casa**. Ao contrário do rótulo e do valor, o placeholder **não**
> era reescrito no tema claro.

### O que é verdade

**O espelho alcança as classes com prefixo.** O bloco vive em `@layer base`, e o
`@layer base` passa pela máquina de variantes do Tailwind. Conferido compilando
uma sonda com os três casos e lendo o CSS gerado:

```css
html:not(.dark) .placeholder\:text-slate-500::placeholder { color: rgb(100 116 139); }
html:not(.dark) .hover\:text-slate-500:hover             { color: rgb(100 116 139); }
```

A especificidade do espelho com prefixo — `(0,3,1)` — vence a do utilitário,
`(0,2,0)`. Ele vale.

### O que sobrevive

**Os números.** O placeholder era `#64748b` nos dois temas de qualquer forma,
porque o espelho é uma **reflexão em torno do 500** e o próprio `slate-500` é
**ponto fixo**: mapeia em si mesmo. Então 4,76:1 no claro e **3,36:1 no escuro**,
reprovando — e a troca por `--text-muted` continua certa, com o teste válido.

**Errou a explicação, não a medição.** Mas explicação errada em documento de
decisão contamina as fases seguintes, e é por isso que esta correção existe em
vez de uma emenda ao commit.

### Como o erro entrou

O mapeamento da fase concluiu "o seletor não casa" **lendo o seletor**, sem
compilar. Eu repassei sem conferir. E o pior: a passagem adversarial da própria
varredura **já havia refutado esse mesmo candidato**, com esta mesma explicação,
dias antes. A resposta certa estava em mãos e a errada foi publicada.

É exatamente o modo de falhar que a sessão do ChamadosHS relatou no mesmo dia —
um agente dela concluiu sobre uma função tendo lido outra, e ela repassou antes
de abrir o arquivo. **A passagem adversarial reduz o falso positivo; não o
elimina.** O que elimina é conferir antes de publicar.

### A regra que ficou

Registrada em `COMPARTILHADO/DECISOES.md`, com a consequência prática:

> Nas Fases 11–16, os usos de **`text-slate-500`** são os **primeiros a sair em
> cada tela**, porque são os únicos que reprovam com certeza — em qualquer
> prefixo e em qualquer superfície escura. Os outros degraus do espelho invertem
> e podem estar aprovando; o 500 não inverte, e não está.

---

## 1. Componentes fechados até aqui

| Componente | Commit | O que mudou |
|---|---|---|
| `Switch` | `d4f9d45` | **novo** — extraído do alternador de tema |
| `Checkbox` | `2ba8d81` | **novo** — extraído de 3 usos inline |
| `FileUpload` | `7c36642` | **novo** — extraído do `DropZone` do `TicketFormPage` |
| `Input` | `17baed9` | 7 trocas de token, 2 não-mudanças deliberadas |
| `Textarea` | `32a3bb2` | idem, e ganhou o teste que não tinha |
| `Select` | `7b8e72a` | os mesmos tokens, e a seta deixou de ser um data URI cravado |
| `Selector` | `35cdba0` | **novo** — unifica os três seletores; os nomes viram invólucros |

**A fase está fechada.** `Radio` não entrou por decisão do operador ("Radio:
nada"), e o `Toast` é da Fase 10.

## 1.1 A unificação dos três seletores

`FilterSelect` (17 chamadas), `FormDropdown` (2) e `SearchSelect` (1) faziam a
mesma coisa com três desenhos. Viraram um `Selector` com dois eixos, e os três
nomes continuam como invólucros finos `@deprecated`. **Nenhuma das 20 chamadas
mudou** — os testes de contrato que já existiam passam, inclusive os de portal,
scroll, resize e ancoragem pela borda, que eram o comportamento mais frágil.

Os eixos são dois porque medem coisas independentes: `variant` decide **onde o
painel é ancorado** (o `"filter"` precisa de portal porque vive dentro de
contêiner com `overflow`; o `"form"` é `absolute` sob o campo), e `searchable`
decide **de onde vêm as opções**. Um filtro pode ser buscável e um formulário
pode não ser.

### Quatro defeitos que só apareceram ao unificar

| | O que era |
|---|---|
| **Tokens** | nenhum dos três usava um token do pacote — **45 cores `slate` cravadas**, hoje zero |
| **Tema** | `FormDropdown` e `SearchSelect` eram escritos **só para o escuro**: `text-slate-300` no rótulo, sem um único `dark:` |
| **Foco** | os dois traziam `focus:outline-none` **e nada no lugar** — o defeito da E9, foco ausente e não fraco |
| **Teclado** | **nenhum dos três tinha** — e o `SearchSelect` ainda declarava `role="listbox"` e `role="option"` sem honrar o contrato |

O último é o mais grave, e não por ser o mais visível: declarar o papel
**promete** o contrato do widget a quem usa leitor de tela — setas andam, `Enter`
escolhe, `Escape` fecha. Prometer e não cumprir é pior que não declarar nada,
porque a pessoa espera um comportamento que nunca vem.

### O que a catraca não via, e por quê

**45 cores cravadas saíram e o número da catraca não mudou** — 50, linha de base
50. Isso não é a catraca falhando: é a prova de que ela nunca as viu. Ela casa
`bg-*` com `text-*` **na mesma string**, e nestes componentes o fundo vinha do
elemento pai. A varredura achava 7 pares nos três arquivos, todos aprovados.

Fica registrado como limite conhecido da ferramenta: **cor de texto sem fundo
co-locado é invisível para a catraca**. Nas Fases 11–16 isso vale para toda tela
cujo fundo esteja no contêiner e o texto no filho.

### Uma mudança de papel, deliberada

As linhas de opção eram `<button>` sem papel e hoje são `role="option"`. O papel
explícito **substitui** o implícito, então sete consultas dos testes de contrato
acompanharam — sem que nenhuma asserção enfraquecesse. Para o mouse, nada mudou.

### O que não foi unificado

`dot` e `hint` continuam dois campos. Um é amostra de cor, o outro é linha de
texto secundária; juntá-los num "campo secundário" seria a armadilha de **token
certo, propósito errado** — a terceira aparição dela nesta migração, depois do
`--border-strong` como contorno (E7) e das barras de comparação como `progressbar`.

### Pendência que a fase abre

Os **20 `dot:` das telas são hex cru** (`#f59e0b`, `#10b981`), fora do sistema de
tokens. Não mexi: é decisão de desenho, e entra nas Fases 11–16 com cada tela.

## 2. As emendas que a fase gerou

Quatro, e nenhuma estava prevista:

| Emenda | O que faltava no pacote |
|---|---|
| **E7** | `--border-control` — nenhum token de borda alcançava 3:1 como contorno de controle |
| **E7-b** | o visto do `Checkbox` em `--color-white` sobre `--action`: 2,69:1 no escuro |
| **E9** | `Checkbox` e `Switch` não mostravam **foco nenhum** |
| **E10** | a seta do `Select` era um data URI com `stroke='%2394a3b8'` — data URI não aceita `var()`, então ela nunca seguiu o tema |

E uma pendência aberta: o vocabulário de estado do `FileUpload.d.ts`
(`scanning`/`rejected` não descrevem varredura síncrona).

**A E8 é do ChamadosHS**, e desde então foi escrita e adotada — os pares
`tint`/`on-tint` de `success`, `info` e `danger` sobre `--surface-elevated`. O
`colors.css` foi recopiado e o `Badge` foi o componente que a fez valer.

## 2.1 A catraca desceu pela primeira vez

O `Select` produziu o **primeiro disparo da catraca no sentido que importa**:
**51 → 50**. Os disparos anteriores foram todos de subida — código novo trazendo
par novo abaixo de 4,5:1, e a catraca barrando. Este foi o inverso: um par
reprovado deixou de existir, e a linha de base **desceu junto**, porque a catraca
falha nos **dois** sentidos.

A descida é o ponto: uma catraca que só sobe vira teto. Ao baixar a base quando o
número melhora, ela transforma cada conserto em piso novo — o par consertado não
pode voltar sem que a varredura acuse.

Hoje: `catraca: 50 par(es) abaixo de 4,5:1, linha de base 50 — ok, em dia.`

## 3. Desvio com prazo

O foco dos campos usa `ring` do Tailwind (`box-shadow` por fora) e o pacote usa
`outline` por dentro. **Não é exceção: é dívida com prazo**, registrada no
`VERSION.md` como desvio **F1**, e expira no **Checkpoint 4**. Cada uma das telas
alinha quando for migrada nas Fases 11–16, junto da captura antes e depois.

## 4. Acréscimo à checklist da §29

Entrou uma linha na conferência por tela, e ela nasceu deste caso:

```text
[ ] nenhum campo depende do placeholder para ser entendido
```

Placeholder some ao digitar, tem contraste menor por desenho, e em vários
navegadores não é lido como nome acessível. Campo cujo único identificador é o
placeholder fica sem nome para quem usa leitor de tela e sem referência para quem
já começou a digitar.

## 5. As quatro barras que ficam para as Fases 11–16

O `Progress.jsx` do pacote tem `role="progressbar"` e nasceu do `SlaProgresso` do
ChamadosHS — **o pacote melhorou o que copiou, e a melhoria nunca voltou**. A
barra de prazo da lista de chamados foi corrigida agora (`fc0162c`), por estar
na tela mais usada e haver uma por chamado. As outras quatro entram tela a tela,
e **duas delas não levam papel de progresso**:

| Onde | O que mostra | Papel | Por quê |
|---|---|---|---|
| `AdminDashboard.tsx:566` | taxa de conformidade por prioridade | **`meter`** | é medida de um valor num intervalo, sem alvo a atingir |
| `SlaConfigPage.tsx:256` | razão de resposta | **`meter`** | idem |
| `AdminDashboard.tsx:511` | contagem por categoria | **nenhum** | vai de zero ao **maior valor da lista**, não a 100 — não há escala de porcentagem |
| `AdminDashboard.tsx:129` | distribuição empilhada por status | **nenhum** | é gráfico de partes de um todo, não progresso |

Para as duas últimas, o desenho registrado é: barra `aria-hidden` com o valor em
texto ao lado, ou `role="img"` com `aria-label` no grupo inteiro.

**Por que isso importa mais que o conserto:** `role="progressbar"` numa barra de
comparação anuncia um número numa escala que não existe. É a terceira aparição
de "token certo, propósito errado" nesta migração — depois do `--border-strong`
como contorno de controle (E7) e da paleta categórica carregando texto no
ChamadosHS. O conserto por analogia é o modo de falhar desta família.

Um teste guarda isso: `test/pages/barra-de-sla.test.ts` exige que o
`AdminDashboard` **não** ganhe `role="progressbar"`.

A §29 ganhou o item correspondente, para valer em toda tela migrada daqui em
diante.
