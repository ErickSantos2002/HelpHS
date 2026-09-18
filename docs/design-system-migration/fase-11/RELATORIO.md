# Fase 11 — Templates — HelpHS

Relatório no formato da seção 32. **Em andamento.**

A §25 pede uma tela real de cada tipo — listagem, formulário e painel — montada
com os primitivos. Os candidatos, escolhidos pela síntese do mapeamento:

| tipo | tela | estado |
|---|---|---|
| painel | `ClientDashboard` | **fechada** |
| formulário | `TicketFormPage` | **fechada** |
| listagem | `TicketListPage` | **fechada** |

---

## Etapa 0 — o que veio antes de abrir tela

A síntese das seis telas foi taxativa: **quatro delas travavam no mesmo trabalho
de pacote**. Foi feito primeiro.

| | |
|---|---|
| `Selector` não estava no barril | quatro telas parariam na mesma linha faltante |
| `TableHeaderCell` sem `scope="col"` | é a associação cabeçalho-célula que faz a tabela ser tabela |
| `label` não chegava ao gatilho no `variant="filter"` | numa barra com quatro filtros, os quatro se anunciavam pelo valor escolhido |
| `KpiCard` em três cópias divergentes | prop de classe crua era a causa-raiz da cor fora do sistema nos painéis |
| prioridade em cinco mapas divergentes | virou `lib/prioridade.ts`, fonte única |
| `Button` não sabia ser link | a regra "navegação é link" vale em 16 lugares |

## Etapa 1 — a varredura mecânica

`1d1fca5`. **584 trocas em 44 arquivos, zero pixel** — os aliases do D2 apontavam
para os mesmos tokens. Uma ocorrência escapou e foi corrigida depois:
`ring-offset-background`, porque o utilitário é `ring-offset-` e o padrão só
previa `ring-`.

## Etapa 2 — `ClientDashboard`

### Ficha da §29

```text
Página: /dashboard — src/pages/dashboard/ClientDashboard.tsx

FUNCIONALIDADE
[x] carrega dados — duas chamadas a `getTickets`, mesmos params, mesmos limites
[–] filtra          — a tela não filtra
[–] busca           — a tela não busca
[x] pagina          — `Pagination`, mesma prop, mesmo PAGE_SIZE de 10
[–] ordena          — a tela não ordena
[–] cria            — o "Abrir chamado" leva ao formulário; não cria aqui
[–] edita  [–] exclui
[x] abre detalhes   — agora por link; ver "a área de clique" abaixo
[–] anexa/remove arquivo
[x] respeita permissões — a tela é do papel `client`; `creator_id` = usuário
[x] mostra erro     — `Alert variant="danger"`, `live` ligado (E12)
[x] mostra estado vazio — texto + botão-link "Abrir primeiro chamado"
[x] mostra loading  — `Spinner` na carga inicial e na troca de página
[x] funciona no mobile — coluna de protocolo `hidden sm:table-cell`, e o
                         protocolo reaparece dentro da célula do título
[x] funciona no tema escuro — zero classe sem `dark:` correspondente: não há
                         mais classe de cor crua nenhuma
[x] nenhum campo depende do placeholder — a tela não tem campo
[–] barras desenhadas — a tela não tem barra

ACRESCENTADOS PELAS DECISÕES
[x] o que a interface MOSTRA é o que a árvore DIZ, por estado
    repouso    tabela com cabeçalho de coluna, era pilha de botões
    foco       link por linha, nome = título do chamado
    hover      sublinhado no título, além da cor
    vazio      texto, não só ausência
    carregando `Spinner` (ver pendência)
[x] nenhuma ação só de mouse — a linha virou link; teclado alcança um por linha
[x] nenhum `text-slate-*` sem `dark:` — zero cor cravada
[x] nenhuma cor fora do sistema — zero
[x] `Alert` montado por ação leva `live` ligado — correto, é erro de carga
[ ] desvio F1 — a tela não tem campo; nada a alinhar
[x] nenhum primitivo reinventado — a tabela falsa virou `Table`
[x] a catraca desceu — 49 → 48
```

### Contagem do que resta à mão

```text
src/pages/dashboard/ClientDashboard.tsx: 2
```

**As duas ocorrências estão em comentário**, descrevendo o que a tela era antes.
Controles à mão de verdade: **zero**.

É o caso que a regra prevê — *conta, não julga*: número maior que zero significa
que alguém tem de olhar, não que há trabalho pendente. A sessão do ChamadosHS
encontrou o mesmo na primeira aplicação, com oito de 31.

### O defeito principal, e o que ele custava

A lista **parecia** uma tabela e não era nenhuma. O cabeçalho eram quatro
`<span>` numa grade CSS; cada linha era um `<button>`.

Quem enxerga lê "Protocolo | Título | Prioridade | Status" no topo e alinha a
coluna com o olho. Quem usa leitor de tela ouvia **dez botões** cujo nome era a
costura de tudo — *"HS-2024-0031 Impressora não imprime Alta Aberto"* — sem
"linha 3 de 10", sem nome de coluna, sem saber quantas colunas existem.

### A área de clique não se perdeu, e isso foi medido

Navegação é link, e um `<tr>` não pode ser um link. O acionável foi para dentro
da linha — o título — com um pseudo-elemento esticando-o sobre a linha inteira.

**Medido no navegador antes de escolher o desenho:** o pseudo-elemento cobre o
`<tr>` exatamente — 400×61 contra 400×61 — porque a linha é `relative`. Onde
isso falhar, o link continua funcionando e cobre apenas a própria célula:
degradação limpa, não quebra.

O nome do link é o **título do chamado**, não "Ver detalhes". Dez links chamados
"Ver detalhes" produzem uma lista em que nenhum diz para onde vai.

### O que a Etapa 2 ensina para as outras cinco

1. **Tabela falsa vira `Table`**, e o acionável vai dentro da linha.
2. **Botão que navega vira `Button to=`**, que é o primitivo e não uma classe
   copiada — 16 lugares, e as 16 divergiriam.
3. **`KpiCard` com `tone`**, nunca com classe.

### Pendência que a tela abre, e não é do sistema de design

Só o "Total" dos indicadores vem do servidor; "Em andamento" e "Resolvidos" são
contados **no cliente** sobre os 500 itens trazidos. Passando de 500 chamados a
tela mostra três números que não fecham, sem nenhum sinal de truncamento.

Está registrado no próprio arquivo. Entra na Fase 16, com o serviço — não viaja
num commit de token.

---

## Etapa 3 — `TicketFormPage`

É a tela de **formulário** que a §25 pede. 662 linhas, e o defeito principal
aparecia duas vezes na mesma página.

### Ficha da §29

```text
Página: /tickets/new e /tickets/:id/edit — src/pages/tickets/TicketFormPage.tsx

FUNCIONALIDADE
[x] carrega dados   — `getProducts` + `getMyEquipment`, e `getTicket` na edição
[–] filtra  [–] busca  [–] pagina  [–] ordena
[x] cria            — `createTicket`, mesmo corpo, mesma ordem
[x] edita           — `updateTicket`; `client_observation` segue só na criação
[–] exclui
[x] abre detalhes   — navega para o chamado criado
[x] anexa/remove arquivo — `FileUpload`, mesmos limites (10 arquivos, 25 MB)
[x] respeita permissões  — a tela é do cliente; nada de papel mudou
[x] mostra erro     — `Alert variant="danger"` dispensável, `live` implícito
[x] mostra estado vazio  — "Selecione um produto primeiro"
[x] mostra loading  — `Spinner` na carga de produtos e do chamado
[x] funciona no mobile   — grade de 4 colunas no telefone, 8 no desktop
[x] funciona no tema escuro — zero classe de cor crua no código
[x] nenhum campo depende do placeholder — todos com `label`
[–] barras desenhadas

ACRESCENTADOS PELAS DECISÕES
[x] o que a interface MOSTRA é o que a árvore DIZ, por estado
    repouso     12 rádios em 2 grupos nomeados, era 12 botões sem grupo
    escolhido   `checked` na árvore, era só cor
    foco        anel no cartão, vindo do foco do rádio nativo
    erro        `aria-describedby` do grupo + `aria-invalid` nos rádios
    etapa atual `aria-current="step"`, era só cor
    concluída   texto "(concluída)", era só o ✓ e a cor
[x] nenhuma ação só de mouse — o grupo inteiro é 1 parada de tabulação e as
    setas andam nele, tudo nativo
[x] nenhum `text-slate-*` sem `dark:` — 36 trocas, zero restante no código
[x] nenhuma cor fora do sistema — `bg-red-500`, `bg-amber-500`, `bg-emerald-600`
    e `text-white` saíram
[x] `Alert` montado por ação leva `live` ligado
[ ] desvio F1 — não se aplica
[x] nenhum primitivo reinventado — dois grupos falsos viraram `RadioCards`
[x] a catraca desceu — 48 → 46 pares, 28 → 26 cheias
```

### Contagem do que resta à mão

```text
src/pages/tickets/TicketFormPage.tsx: 2
```

Os dois são **justificados**, e a regra manda contar, não julgar:

| controle | por que fica |
|---|---|
| "Selecionar todos / Limpar seleção" | é ação, não navegação; `<button>` é o certo |
| fichas de equipamento | seleção **múltipla** com `aria-pressed`, que é o que a especificação manda para alternância |

SVG solto no código: **0**. Eram treze.

### O defeito principal: dois grupos falsos na mesma tela

Categoria (oito cartões) e prioridade (quatro fichas) eram **pilhas de
`<button>`**. Quem enxerga vê um deles aceso; quem usa leitor de tela ouvia
doze botões chamados "Hardware", "Software", "Rede"… — sem "escolhido", sem
"1 de 8", e sem nenhuma relação com as palavras "Categoria" e "Prioridade"
escritas logo acima. **A escolha existia só na cor.**

Virou o primitivo `RadioCards`, com `<input type="radio">` de verdade dentro de
`fieldset`/`legend`. A alternativa — `role="radiogroup"` com `aria-checked` e
`tabindex` móvel — seria reimplementar em JavaScript quatro comportamentos que
o navegador já tem, e a `Tabs` do pacote precisou de emenda (E12) exatamente
nesse terreno.

O ganho é medido: o grupo inteiro passou a ser **uma** parada de tabulação. Eram
oito.

### O sexto mapa de prioridade, e o que ele dizia de errado

Além dos cinco já conhecidos, esta tela tinha o seu — e discordava em duas
frentes ao mesmo tempo: pintava `bg-red-500` e `bg-amber-500` **crus**, fora do
sistema, e dizia "Crítico", "Alto", "Médio", "Baixo" no **masculino**, contra o
feminino que a E17 fixou no pacote. No mesmo sistema, a mesma prioridade tinha
dois nomes.

Junto saiu a linha mais frágil do arquivo:

```tsx
pri.active.split(" ").filter(c => c.startsWith("text-")).join(" ")
```

Uma string de classes **fatiada em tempo de execução** para extrair a cor do
texto. Hoje é `PriorityBadge`, que é o primitivo.

### Três defeitos que só apareceram porque a ferramenta olhou

1. **A catraca acusou `bg-success text-on-success`.** O par de `text-on-success`
   é o degrau de **ação** da E2; sobre a cor cheia da rampa esse mesmo texto dá
   2,54:1. Era eu cometendo o defeito que a E2 existe para tornar impossível.

2. **O `<legend>` não estava no primeiro lugar.** Eu havia trocado o `<label>`
   pendurado por `fieldset`/`legend`, mas deixei o `legend` dentro de um `div`
   de layout — e ali ele **deixa de nomear o grupo**. O caso de teste caiu e
   nomeou.

3. **A galeria não veria a classe montada por concatenação.** `"peer-checked:" +
   tom` é invisível para a varredura do Tailwind: a regra não nasce e o cartão
   escolhido fica idêntico ao livre, sem erro nenhum. A medição de contraste
   **continua verde** nesse estado, porque medir duas vezes a mesma cor legítima
   não reprova nada. Só a comparação entre os dois estados distingue "aplicou"
   de "não gerou" — virou caso permanente na galeria, e a mutação confirmou que
   ele cai sozinho enquanto os outros três seguem verdes.

### O que entrou no pacote de primitivos

| | |
|---|---|
| `RadioCards` | escolha única em cartão ou ficha, com rádio nativo |
| `Icon` | nove traçados locais, em tabela **separada** da do pacote |

A separação em `ICON_PATHS_PACOTE` e `ICON_PATHS_LOCAIS` não é organização: o
teste prende os 25 do pacote a um hash tirado do `Icon.jsx` no dia da cópia, e
um acréscimo local misturado ali derrubaria essa conferência para sempre — o
conserto seria trocar o número, que é justamente o que o teste impede.

Os nove vieram **verbatim** dos SVGs que estavam soltos na página. Trocar
`server` pelo `cpu` que já existia, ou `help` pelo `info`, mudaria o desenho da
tela dentro de um commit que promete não mudar pixel.

### A trilha, e por que ela deixou de voltar no histórico

Era um `<button onClick={navigate(-1)}>` com a linha inteira dentro, então o
nome acessível do controle era **"Tickets / Novo chamado"** — a página de onde
se vem e a página onde se está, num controle só.

Agora é `<nav>` com um link para `/tickets` e a página atual em
`aria-current="page"`. A volta deixou de ser `navigate(-1)` de propósito: de um
formulário, o histórico pode ter vindo do detalhe, da lista ou do painel, e
"para trás" não é um lugar.

---

## Etapa 4 — `TicketListPage`

É a tela de **listagem** que a §25 pede, e ela é um quadro kanban de seis
colunas. 489 linhas.

### Ficha da §29

```text
Página: /tickets — src/pages/tickets/TicketListPage.tsx

FUNCIONALIDADE
[x] carrega dados   — `getTickets`, mesmos params
[x] filtra          — prioridade e responsável, mesmos valores
[x] busca           — título, protocolo e nº de série; mesmo campo
[–] pagina          — o quadro traz tudo e rola por coluna
[x] ordena          — por urgência dentro da coluna; a ordem passou a vir do
                      módulo (`PRIORIDADE[p].ordem`) em vez de um mapa local
[–] cria            — o "Abrir chamado" leva ao formulário
[–] edita  [–] exclui
[x] abre detalhes   — agora por LINK; ver abaixo
[–] anexa/remove arquivo
[x] respeita permissões — sem mudança de papel
[x] mostra erro     — `Alert variant="danger"`
[x] mostra estado vazio — por coluna, com texto
[x] mostra loading  — `Spinner`
[x] funciona no mobile — colunas de 268px com rolagem horizontal
[x] funciona no tema escuro — zero cor crua no código
[x] nenhum campo depende do placeholder — a busca tem `title`; ver pendência
[x] barras desenhadas — a do SLA já era `progressbar` com `aria-valuetext`

ACRESCENTADOS PELAS DECISÕES
[x] o que a interface MOSTRA é o que a árvore DIZ, por estado
    repouso     6 regiões com `<h2>`, eram 6 parágrafos
    cartão      link com o título como nome, era botão
    contagem    "1 chamado", era "1"
    prioridade  selo em texto; o ponto saiu da árvore
    sem técnico texto em `sr-only`, era só um ícone
[x] nenhuma ação só de mouse
[x] nenhum `text-slate-*` sem `dark:` — zero cor crua no código
[x] nenhuma cor fora do sistema — 6 hexadecimais de status, 4 de prioridade,
    3 de limiar de SLA e a paleta crua do Tailwind saíram
[x] `Alert` montado por ação leva `live` ligado
[x] nenhum primitivo reinventado — `Avatar`, `Button to=`, `PriorityBadge`
[x] a catraca desceu — 46 → 43 pares
```

### Contagem do que resta à mão

```text
src/pages/tickets/TicketListPage.tsx: 3
```

Os três são **ação**, não navegação: limpar busca, limpar filtros e o arrasto
do quadro. SVG solto: **0**. Eram nove.

### Dois mapas divergentes, e eles eram os piores

**`PRIORITY_CFG` era o sétimo mapa de prioridade do sistema**, e o
`FilterSelect` da barra trazia o **oitavo** — quatro deles só nesta tela,
contando o do quadro e o do filtro. Diziam "Crítico", "Alto", "Médio", "Baixo"
no masculino, contra o feminino da E17, e pintavam `medium` de **índigo**
(`#818cf8`), que não é a variante `info` de nenhum dos outros seis.

**`COLUMNS` mapeava os seis status com a paleta crua do Tailwind** — sky,
indigo, amber, violet, emerald, slate — mais seis hexadecimais cravados, e com
rótulos próprios: "Ag. Técnico" onde o `Badge` dizia "Aguardando técnico".

Nasceu `lib/status.ts`, no mesmo molde de `lib/prioridade.ts`, e o `Badge`
passou a consumi-lo também.

### A consequência visível, e por que ela fica

`awaiting_technical` e `awaiting_client` passam a **compartilhar o âmbar**, onde
antes eram âmbar e violeta.

Isso é a §16, não descuido: os dois **são** o mesmo estado para quem olha o
quadro — o chamado está parado esperando alguém — e o que os separa é quem está
devendo resposta, que é informação de texto e está no título da coluna.

E a medição da E18 mostrou que nem daria para mantê-los distintos com rigor: no
tema claro, dois degraus de `warning` que passem 3:1 nas três superfícies ficam
a **12,2** de ΔE, contra um piso de 20. A cor não consegue carregar essa
distinção.

### O cartão era um botão

Navegação é link, e o botão tirava do cartão tudo o que um link tem: não abre em
aba nova com Ctrl, não aparece no menu de contexto, não mostra o destino na
barra de status, e o leitor de tela anuncia "botão" para algo que muda de
página.

### Três defeitos menores que a migração encontrou

1. **O botão de limpar busca não tinha nome.** Só o `<svg>` dentro, e o `Icon` é
   `aria-hidden`: quem usa leitor de tela ouvia "botão".
2. **A contagem da coluna era um número solto.** "Aberto … 1" não diz o quê.
3. **O ponto de prioridade usava `title`** como único portador do rótulo, e
   `title` não é nome acessível confiável. O selo do rodapé já mostra em texto,
   então o ponto virou o que sempre foi na prática: decoração.

### O `--fill-*` completou-se aqui

A barra de SLA pintava por limiar com `#ef4444`, `#f59e0b` e `#10b981` —
preenchimento com hexadecimal cravado, e o âmbar dando 1,96 no claro. Passou aos
`--fill-*`, e o conjunto local ganhou `info`, `success` e `danger` ao lado do
`warning` que já existia. Continuam candidatos à **E19**.

### Pendência que a tela abre, e não é do sistema de design

**O status `cancelled` não tem coluna.** O quadro mostra seis dos sete, e um
chamado cancelado simplesmente **desaparece** da lista — sem coluna, sem aviso, e
sem aparecer na busca por protocolo. É anterior a esta migração e não foi
mexido: acrescentar uma sétima coluna é decisão de produto.

Foi para `COMPARTILHADO/achados-helphs-frontend.md`, e **não** para a Fase 16 —
é defeito de produto, não de sistema de design, e sai com o frontend depois do
Checkpoint 3. Lá está registrada a consequência que só apareceu ao escrever: os
cancelados **consomem o limite de 500** da carga e depois são descartados, então
chamados ativos podem ficar de fora do quadro por causa de chamados que o quadro
não mostra.

---

## Etapa 7 — `TicketDetailPage`

A maior tela do sistema: **2.258 linhas**. É a tela de **detalhe**, e fecha as
três que a §25 pede.

### Ficha da §29

```text
Página: /tickets/:id — src/pages/tickets/TicketDetailPage.tsx

FUNCIONALIDADE
[x] carrega dados   — `getTicket`, `getTicketHistory`, `getAttachments`,
                      `listTicketNotes` (só staff), `getTicketSurvey`,
                      `getTechnicians`, `getTags`
[–] filtra  [–] busca  [–] pagina  [–] ordena
[–] cria            — a criação é do formulário
[x] edita           — observação do cliente, notas internas, etiquetas, status,
                      responsável, e o link para o formulário de edição
[x] exclui          — nota interna, com confirmação
[x] abre detalhes   — é o detalhe
[x] anexa/remove arquivo — `uploadAttachments`, mesmos limites
[x] respeita permissões — notas internas só para staff; "Editar ticket" só admin
[x] mostra erro     — `Alert variant="danger"` com `role="alert"`
[x] mostra estado vazio — por aba, com texto
[x] mostra loading  — `Spinner` na carga e por ação
[x] funciona no mobile — abas roláveis, coluna única
[x] funciona no tema escuro — zero cor crua no código
[x] nenhum campo depende do placeholder
[x] barras desenhadas — o SLA usa `SlaChip`, que é primitivo

ACRESCENTADOS PELAS DECISÕES
[x] o que a interface MOSTRA é o que a árvore DIZ, por estado
    trilha        `<nav>` + `aria-current="page"`, era um botão só
    editar        link com destino, era `onClick={navigate}`
    prioridade    `PriorityBadge` no histórico, era texto colorido
    abas          `Tabs` do pacote, com o contrato da E12
[x] nenhuma ação só de mouse
[x] nenhum `text-slate-*` sem `dark:` — 108 trocas, zero restante
[x] nenhuma cor fora do sistema — zero
[x] `Alert` montado por ação leva `live` ligado
[x] nenhum primitivo reinventado — 22 ícones do bloco `IC` viraram `Icon`
[x] a catraca desceu — 43 → 42 pares
```

### Contagem do que resta à mão

```text
src/pages/tickets/TicketDetailPage.tsx: 18
```

**Os dezoito são ação**, e nenhum ficou sem nome acessível — auditados um a um.
São: enviar nota, excluir nota, editar observação, salvar, cancelar, alternar
seção, alternar aba, baixar anexo, pré-visualizar, resolver, reabrir, atribuir,
avaliar, e as confirmações de modal.

SVG solto: **0**. Eram 31. Cor crua no código: **0**. Eram ~110.

### Quatro mapas locais, e o nono e o décimo da prioridade

| mapa | o que era |
|---|---|
| `STATUS_LABEL` | duplicava `lib/status.ts` |
| `PRIORITY_LABEL` | o **nono** mapa de prioridade |
| `PRIORITY_COLOR` | o **décimo**, e um quarto esquema: sky, yellow, orange, red |
| `CATEGORY_LABEL` | a **terceira** cópia das oito categorias |

O `PRIORITY_LABEL` daqui **já dizia o feminino certo** — foi este mapa que a
emenda E17 citou como o lado correto da divergência. O que saiu foi a
duplicação, não o texto.

Nasceu `lib/categoria.ts`, e o `TicketFormPage` passou a consumi-lo também. As
três cópias de categoria **concordavam** — e é exatamente assim que prioridade
começou, antes de virar dez mapas divergentes.

### Os 22 ícones, mapeados por traçado

O bloco `IC` foi migrado **por desenho, não por nome**: cada traçado foi
comparado com o `ICON_PATHS`, e **oito já existiam** — `arrowLeft`, `user`,
`calendar`, `paperclip`, `box`, `cpu`, `close`, `plus`. Reusar o nome de lá em
vez de criar um novo é o que o teste do `Icon` exige, porque ele proíbe traçado
duplicado.

Os outros catorze entraram em `ICON_PATHS_LOCAIS`, verbatim. E o `Icon` passou a
aceitar **traçado múltiplo**: o olho é pupila mais contorno, e o conjunto do
pacote é todo de traçado único, então isto é acréscimo local que não muda nada
do que já existia.

**Vários são parentes de ícones do pacote com traçado diferente** —
`checkMark` contra `check` (o do pacote é o visto dentro do círculo), `alert`
contra `warning` (outro triângulo), `tagOutline` contra `tag`. Ficam separados
de propósito: unificar muda o desenho da tela, e isso é decisão de produto.
**Fica anotado para o operador.**

### As duas navegações vestidas de botão

A trilha era um `<button onClick={navigate(-1)}>` com a linha inteira dentro, e
o nome acessível do controle era **"Tickets / HS-2026-0001"** — a página de onde
se vem e a página onde se está, num controle só. Mesma correção do
`TicketFormPage`.

E o "Editar ticket" navegava por `onClick`. O `SidebarAction` ganhou `to`, do
mesmo jeito que o `Button` do pacote ganhou.

### A linha do tempo era o caso mais claro de série categórica

O ponto pintava por **tipo de campo** — criação, status, responsável,
prioridade — com `sky`, `violet`, `emerald` e `orange` crus. Tipo de campo não
significa nada em si, então foi para `--chart-1..4`, que é a paleta medida para
série sem significado próprio. A cor é reforço: o rótulo do campo está ao lado.

### O que ficou de propósito

**A escala CSAT** foi tokenizada mas **não** ganhou as três faixas decididas
(1–4 `danger`, 5–7 `warning`, 8–10 `success`). Ela tem Etapa marcada na Fase 16,
e antecipá-la aqui seria mudar o desenho fora do lugar combinado. O amarelo cru
virou o par `tint`/`on-tint` de warning, e nada mais.
