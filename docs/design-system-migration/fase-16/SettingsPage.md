# §29 — `pages/settings/SettingsPage.tsx`

A tela **não aparecia** na varredura de contraste, e isso não era o mesmo que
estar certa: a varredura casa `bg-*` com `text-*` na mesma string de classe, e
**25 classes de paleta crua** mais **16 hexadecimais** passam inteiras por baixo
dela. Quem mede a tela é o checklist, não a catraca.

448 linhas antes, 482 depois. O arquivo cresceu porque a decisão sobre os
dezesseis hexadecimais precisava ficar escrita no lugar onde ela é lida.

---

## O que a tela tinha

| o que | quantos |
|---|---:|
| classes da paleta crua (`slate-*` ×18, `red-*` ×7) | **25** |
| hexadecimal cravado em código | **16** |
| `<svg>` solto, em duas funções locais e dois em linha | **4** |
| `text-white` | **1** |
| cor cheia semântica como cor de TEXTO | **0** |
| linhas da varredura de contraste | **0** |
| `theme` lido em JavaScript | **0** |
| mapa local | **1** (`PRESET_COLORS` — e ele **fica**, ver abaixo) |
| aviso de exclusão desenhado à mão | **1** |
| botão com `focus:outline-none` e nada no lugar | **16** (a paleta de cores) |
| campo sem nome acessível | **1** (`<input type="color">`) |

---

## Os 16 hexadecimais: o julgamento desta tela

O briefing manda separar em dois grupos antes de trocar qualquer coisa. Aqui a
separação deu **três**, e o terceiro é onde estão todos os dezesseis:

| grupo | quantos | destino |
|---|---:|---|
| cor que é **decisão de desenho** | **0** | sairia para token |
| cor que é **dado** (a etiqueta que o usuário já escolheu) | **0** literais | chega por `state`/`props`, nunca escrita |
| **paleta padrão oferecida ao usuário** | **16** | fica, e volta para o operador |

`PRESET_COLORS` não é tema: é o atalho para não obrigar ninguém a abrir o
seletor do sistema operacional. O valor escolhido viaja para o backend em
`tags.color` e volta para pintar o selo em toda a lista de tickets. Um token
semântico não cabe — `--tint-danger` não é uma opção que alguém possa escolher
para chamar de "Vermelho" —, e trocar estes dezesseis mudaria a cor das
etiquetas **que já existem no banco**. Escolher qual paleta oferecer é decisão
de desenho de quem cuida do produto, e por isso ela está na §7 do relatório.

**O que a migração resolveu foi o outro lado.** O "certo" que marcava a cor
escolhida era `text-white` cravado sobre uma cor arbitrária — sobre o `#eab308`
("Amarelo") isso é claro sobre claro. Passou a `readableTextColor(c.hex)`, de
`lib/colors.ts`, que decide branco ou quase-preto por luminância relativa
(WCAG) e é o mesmo que o `TagBadge` e a agenda já usavam. **É o único lugar da
tela onde a cor sai de função e não de token, e é legítimo: é o par de um fundo
que o sistema de design não conhece.**

---

## O que passou a usar

| módulo / primitivo | onde | quantos |
|---|---|---:|
| `Icon` (E21) | `edit`, `trash`, `plus`, `check` | 4 |
| `Alert` | erro de carregamento, erro de criação, erro de edição, aviso de exclusão | 4 |
| `readableTextColor` (`lib/colors`) | a marca da cor escolhida | 1 |
| `Card`, `Input`, `Modal`, `ModalFooter`, `Button`, `Pagination`, `Spinner`, `TagBadge` | já estavam | — |

### Os quatro `<svg>`, e como cada um casou

Os quatro eram `viewBox="0 0 24 24"` com `fill="none"` e `stroke="currentColor"`
— mesma família do `Icon`, conferido **antes** de trocar. Nenhum era `0 0 20 20`
nem preenchido, e nenhum ícone novo foi preciso.

| desenho | virou | como casou |
|---|---|---|
| `IconEdit` (função local) | `edit` | **pelo traçado, caractere a caractere** |
| `IconTrash` (função local, 2 usos) | `trash` | **pelo traçado, caractere a caractere** |
| `+` do seletor de cor personalizada | `plus` | **pelo traçado**: `M12 4v16m8-8H4`, idêntico |
| "certo" da cor escolhida | `check` | **pelo significado** — ver abaixo |

O "certo" era `M5 13l4 4L19 7`, um V sem contorno; o `check` do pacote é
`M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z`, o mesmo V **dentro de um
círculo**. É exatamente o caso que a **E21** unificou por significado — «um
"certo" sem círculo» está citado no briefing —, mas ele **muda o que se
desenha** sobre a amostra escolhida. Está na §7 do relatório.

### O aviso de exclusão, que era um `Alert` desenhado à mão

O banner tinha tinta `red-900/20`, borda `red-800/40`, título `red-300` e corpo
`red-400/80`: **quatro degraus da paleta crua que só têm tom no tema escuro** —
no claro o bloco era uma mancha vermelha quase opaca com texto rosa por cima.
Mais uma medalha redonda `red-900/40` com o ícone de lixeira dentro.

Virou `<Alert variant="danger" live={false} title="Ação irreversível">`, que é a
mesma receita que o `EquipmentPage` já usa no modal irmão: par `--tint-danger` /
`--on-tint-danger`, medido nos dois temas, e o ícone que a variante escolhe.

**`live={false}` pela E12**: o aviso já está na tela quando o modal abre, e
região viva anuncia MUDANÇA — anunciá-lo atropelaria o anúncio do próprio
diálogo. Os outros três `Alert` da tela continuam vivos: os três aparecem em
resposta a alguma coisa (a requisição que falhou, o nome duplicado), e é isso
que uma região viva existe para dizer.

### As 25 classes cruas, por família

| era | virou | onde |
|---|---|---|
| `text-slate-400` / `-500` (escada de texto secundário) | `text-conteudo-muted` | 9 lugares |
| `text-slate-800 dark:text-slate-100` | `text-conteudo-heading` | o título |
| `text-slate-500 dark:text-slate-400` | `text-conteudo-muted` | a linha de apoio |
| `text-slate-100` / `text-slate-200` | `text-conteudo-heading` / `text-conteudo` | modal de exclusão |
| `border-slate-600 hover:border-primary` | `border-borda-control hover:border-action` | contorno da cor personalizada |
| `text-primary hover:underline` | `text-conteudo-link hover:text-conteudo-link-hover` | "Criar a primeira" |
| `text-slate-400 hover:text-primary hover:bg-primary/10` | `text-conteudo-muted hover:text-conteudo-link hover:bg-surface-elevated` | botão de editar |
| `text-slate-400 hover:text-red-400 hover:bg-red-900/20` | `text-conteudo-muted hover:text-on-tint-danger hover:bg-tint-danger` | botão de excluir |
| `red-900/20`, `red-800/40`, `red-900/40`, `red-300`, `red-400/80` | o `Alert` | aviso de exclusão |

Três observações sobre as escolhas:

- **`border-borda-control`, e não `border-borda`.** O contorno da cor
  personalizada é limite de CONTROLE, não separador de superfície. Os três
  `borda-*` de superfície ficam entre 1,13:1 e 1,48:1; a WCAG 1.4.11 pede 3:1
  para o limite de um componente, e é o que a **E7** criou.
- **`hover:border-action`, e não `hover:border-primary`.** `primary` é o degrau
  de MARCA; hover de controle é o degrau interativo.
- **`text-conteudo-link`, e não `text-primary`.** "Criar a primeira" é texto que
  se clica, e `text-primary` sobre a superfície dá 3,66:1 — reprova AA, e link
  é texto. `--text-link` dá 5,05:1 no claro e 6,47:1 no escuro.

### Três defeitos que nenhuma ferramenta desta migração acha

Não são cor, não são contraste, e a varredura passaria batido nos três.

1. **Os dezesseis botões da paleta não diziam qual estava escolhido.** O único
   sinal era o desenho do "certo" por cima. Quem não vê a tela ouvia dezesseis
   botões idênticos e nenhum jeito de saber em qual a etiqueta estava. Ganharam
   `aria-pressed` — o item fixo do `CHECKLIST-29.md`, no estado **selecionado**.
2. **Os dezesseis tinham `focus:outline-none` e nada no lugar.** Dava para
   chegar a eles pelo teclado e não dava para ver onde se estava. Ganharam
   `focus-visible:ring-*` sobre `--action`, como o `Button` e o `Alert` fazem.
3. **O `<input type="color">` não tinha nome acessível.** O `<label>` que o
   envolve tem `title`, mas nenhum texto — o campo era "campo de edição, em
   branco". Ganhou `aria-label="Cor personalizada"`.

E um quarto, herdado do irmão `EquipmentPage`: os botões de editar e excluir
eram dez "Editar" e dez "Excluir" numa lista de dez. Ganharam
`aria-label={\`Editar ${tag.name}\`}` — o `title` sozinho não desempata para
quem navega pela lista de controles.

---

## O que resta à mão — a contagem

**Contar, não julgar**: um número maior que zero significa que alguém tem de
olhar, não que há trabalho pendente.

| o que | quantos | observação |
|---|---:|---|
| classe de paleta crua | **0** | eram 25; as 6 ocorrências restantes são texto de comentário, documentando o que saiu |
| `<svg>` solto | **0** | eram 4; nem em comentário |
| `text-white` | **0** | era 1; a ocorrência restante é comentário |
| cor cheia semântica como texto | **0** | não havia |
| linhas da varredura de contraste | **0** | eram 0 — a tela nunca esteve lá |
| `theme` lido em JavaScript | **0** | não havia |
| **hexadecimal em código** | **16** | a paleta oferecida ao usuário — ver acima e §7 |
| mapa local | **1** | `PRESET_COLORS`, que é dado do produto e não tabela de estilo |
| controles à mão | **3** | ver abaixo |
| estilo em linha que não é cor | **1** | `style={{ minHeight: 520 }}` na lista |

**Os três controles à mão:**

1. **O `ColorPicker`** — dezesseis amostras mais um seletor nativo. Não há
   primitivo para escolher cor, e nem deveria haver um genérico: o que ele
   escolhe é dado do produto, não token;
2. **os dois botões de ícone** (editar, excluir) — o `Button` traz borda, altura
   e preenchimento; aqui é ícone de 16px numa linha de lista. É a mesma decisão
   que o `EquipmentPage` tomou, com as mesmas classes;
3. **"Criar a primeira"** — ação de texto **dentro de um parágrafo**. Um `Button`
   ali quebraria a frase em duas linhas. O que a migração trocou foi a cor.

**O `minHeight: 520`** segura a altura da lista para a paginação não pular
quando a última página vem com menos de dez. É leiaute, não sistema de design, e
não há utilitário de altura mínima arbitrária no tema.

---

## O que NÃO foi feito, e por quê

- **Trocar os dezesseis hexadecimais.** Ver acima: são dado, não tema. Relatado.
- **O `+` do botão "+ Nova etiqueta".** É um sinal de mais escrito como TEXTO no
  rótulo, não um `<svg>`, e o irmão `EquipmentPage` resolve o mesmo caso com
  `icon={<Icon name="plus" />}`. Trocar mudaria o **nome acessível** do botão de
  "+ Nova etiqueta" para "Nova etiqueta" — o que a pessoa ouve. Isso é decisão
  de quem cuida do produto, e está na §7.
- **Paginar no servidor.** `getTags()` pede `/tags` sem `page` nem `limit`,
  descarta o `total` que a resposta traz e devolve `items` inteiro; a tela fatia
  em memória e passa `total={tags.length}` — a contagem **do que chegou**, não a
  do servidor. Hoje coincide; no dia em que o endpoint limitar a página, o
  rodapé passa a mentir sem nenhum erro. É defeito de produto, mexe em
  `services/`, e não se conserta aqui. Relatado.
- **Alinhar o foco ao `outline` do pacote (desvio F1).** Os campos herdam o foco
  do primitivo `Input`; as amostras de cor ganharam `ring` porque é o que os
  primitivos vizinhos usam hoje. Alinhar os dois ao `outline` é mudança em
  `components/ui/` e no tema, fora do escopo desta tela.
- **Fazer da paleta um `radiogroup`.** Semanticamente dezesseis amostras
  mutuamente exclusivas são rádios, e rádio exige navegação por setas e um
  `tabIndex` móvel — máquina de teclado nova, num controle que hoje funciona
  por tabulação. `aria-pressed` resolve o que estava quebrado (o estado
  selecionado, mudo) sem inventar interação. Fica registrado como possível
  passo seguinte.

---

## Testes

`src/test/pages/SettingsPage.test.tsx`, **14 casos**, todos validados por
mutação. **Nenhum caso olha classe**: o happy-dom não aplica CSS, e um mutante
de classe sobrevive por um motivo que não tem nada a ver com o que o caso mede.

**Dezesseis mutações, todas no ELEMENTO ou no VALOR, e as dezesseis morreram:**

| mutação | caso que morreu |
|---|---|
| `TagBadge name={tag.name}` → `name={tag.id}` | a lista traz o nome de cada etiqueta |
| `aria-label={\`Editar ${tag.name}\`}` → `aria-label="Editar"` | cada botão de ícone diz DE QUAL etiqueta ele é |
| `canCreate` passa a valer sempre | cliente não cria, não edita e não exclui |
| `"Criar a primeira"` → `"Criar"` | sem etiqueta nenhuma, a tela convida a criar a primeira |
| o convite do vazio inverte a condição (`!canCreate`) | o convite do vazio não aparece para quem não pode criar |
| `setError("Não foi possível…")` → `setError(null)` | quando a lista não carrega, a tela DIZ que não carregou |
| o `label` do campo de nome vira `placeholder` | o campo de nome tem rótulo, e não só um placeholder |
| apaga o `title={c.label}` das amostras | cada cor da paleta é um botão com o nome da cor |
| `aria-pressed={value === c.hex}` → `aria-pressed={false}` | a cor escolhida se declara na árvore |
| apaga o `aria-label="Cor personalizada"` | a cor personalizada é um campo com nome |
| `setEditName(tag.name)` → `setEditName("")` | editar abre com o nome da etiqueta já preenchido |
| o `Alert` perde o `title="Ação irreversível"` | excluir avisa que a ação é irreversível e nomeia a etiqueta |
| `deleteTag(id)` → `Promise.resolve()` | confirmar a exclusão chama o serviço e tira a etiqueta da lista |
| `String("#ffffff") \|\| readableTextColor(` | o certo é claro sobre amostra escura e ESCURO sobre amostra clara |
| `String("#0f172a") \|\| readableTextColor(` | idem — este prova que o lado ESCURO também pesa |
| os dois lados trocados (ternário invertido) | idem |

### O mutante que escapou, e o caso que faltava

As treze primeiras mutações mataram treze casos, e mesmo assim **a conferência
independente achou um sobrevivente**, com o controle sem mutação passando antes:

```
readableTextColor(  →  String("#ffffff") || readableTextColor(
```

O "certo" voltava a ser branco fixo sobre qualquer amostra e **nenhum dos treze
casos reprovava** — exatamente o defeito que esta migração tinha tirado da tela.
A lição é a do próprio briefing, e ela se aplicou a mim: mutação que não muda
comportamento acusa o teste de vazio, mas mutação que muda comportamento **e
sobrevive** acusa o conjunto de casos de incompleto. Nenhuma das treze atacava o
VALOR daquela chamada.

O caso novo prende **os dois lados**, e não um:

| amostra | luminância | o certo tem de ser |
|---|---:|---|
| Royal, `#1d4ed8` | 0,107 | `#ffffff` |
| Amarelo, `#eab308` | 0,4975 | `#0f172a` |

Um caso que só olhasse Royal passaria com `text-white` de volta. Por isso as
duas afirmações, e por isso as **três** mutações acima: branco fixo, quase-preto
fixo e os dois trocados. Ele mede estilo **em linha**, não classe — o happy-dom
não aplica CSS, mas aplica `style`, e é o valor que a pessoa vê.

**⚠️ E aqui está o achado que a escolha das duas cores revelou.** Medida a
luminância relativa (WCAG) das dezesseis, **quinze caem do mesmo lado do limiar
de 0,45**; só o `#eab308` ("Amarelo", 0,4975) o cruza — e por pouco. Ou seja: o
`text-white` cravado que estava aqui era **perfeito em quinze amostras e
ilegível numa**, que é o pior modo de um defeito de cor existir, porque quem
testa à mão quase nunca clica justamente naquela. Duas consequências para quem
vier depois:

1. **o caso depende do Amarelo existir na paleta.** Se um dia ele sair, o caso
   perde o lado claro e passa a medir metade do que diz medir — está escrito no
   próprio caso;
2. **se a paleta ganhar outras cores claras**, o desequilíbrio some e o caso
   fica mais forte, não mais fraco.

**As duas defesas do briefing, e as duas foram usadas.** O roteiro roda um
**controle sem mutação** do arquivo inteiro (que tem de PASSAR, senão nada
depois dele vale) e mais um controle **por caso**, com o mesmo filtro `-t` da
rodada mutante — sem ele, um filtro que não casa devolve "não falhou" e o
roteiro leria isso como mutante morto pelo motivo errado. E o vitest é chamado
por `process.execPath` + `node_modules/vitest/vitest.mjs`, **nunca** por
`npx.cmd`, que é script de shell e não roda por `execFileSync` no Windows.

A restauração é por cópia em `finally`, nunca por `git checkout`: a árvore tem
outros agentes e duas sessões vizinhas.

### Uma terceira defesa, que este projeto comprou com incidente

Na rodada das dezesseis, uma gravação falhou com `UNKNOWN` (errno **-4094**) —
o Windows devolvendo isso quando outro processo segura o arquivo por um instante
(antivírus, indexador, o watcher de uma sessão vizinha; a árvore tem três
worktrees). O roteiro morreu no meio, e o `finally` **também** falhou ao
restaurar.

Desta vez o arquivo escapou íntegro — a restauração de dentro do laço tinha
acontecido antes, e a do `finally` era a mesma escrita repetida —, mas isso foi
sorte de ordenação, não desenho. **Numa árvore compartilhada, um roteiro de
mutação que não consegue gravar é um roteiro que deixa o mutante no disco de
outra pessoa.** O `finally` protege contra o processo morrer; não protege contra
a gravação em si falhar.

O roteiro passou a gravar com repetição (40 tentativas, relendo para confirmar o
conteúdo) e a conferir o arquivo no fim. A integridade foi verificada por
`sha256sum` antes e depois da rodada — mesmo valor —, e pelo `git diff
--numstat`, que continuou em `89 55`.

Nenhum ponto cego apareceu nos treze casos originais: eles mediam o que diziam
medir. O que faltava era um caso, não um caso errado.

---

## Verificação

| conferência | resultado |
|---|---|
| `npx vitest run src/test/pages/SettingsPage.test.tsx` | **14 passaram** (4 execuções, estável) |
| mutação | **16/16 mutantes mortos**, controle geral e por caso passando |
| integridade da tela após a mutação | `sha256` igual ao de antes; `git diff --numstat` em `89 55` |
| `npx tsc --noEmit -p tsconfig.app.json` | sem erro |
| `npx eslint` nos dois arquivos | limpo |
| `varredura-contraste.mjs` \| `grep SettingsPage.tsx` | **nenhuma linha** (eram 0) |
| classes de paleta crua em código | **0** (eram 25) |
| `<svg>` solto | **0** (eram 4) |
| `text-white` | **0** (era 1) |
| hexadecimal em código | **16** (eram 16 — todos paleta oferecida ao usuário) |
