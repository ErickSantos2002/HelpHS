# Design System da Health & Safety — cópia local

> **Não edite `styles.css`, `tokens/*.css` nem `fonts/*.woff2` aqui.** São cópia
> byte a byte do pacote oficial. Para mudar um valor: altere no design system,
> reexporte e recopie estes sete arquivos — e, desde a E3, o diretório `fonts/`
> junto. Editar aqui quebra a rastreabilidade com o pacote e com o
> `_ds_manifest.json`.

| | |
|---|---|
| Pacote | `Health__amp__Safety_Design_System` |
| Namespace | `HealthAmpSafetyDesignSystem_ef9f35` |
| Data do export | 02/09/2026 |
| Origem | `C:\Users\ti_rickelme\Documents\GitHub\design-system` |
| Tokens | 180 custom properties em 6 arquivos |
| Copiado em | 02/09/2026 — Fase 1 da adoção |
| Pacote emendado em | **02/09/2026 — E1** (`.dark` ganha `--text-on-primary`) e **E2** (botões semânticos ganham degrau próprio; `--on-tint-neutral` e `--on-tint-warning` passam a AA). Registro em `design-system/EMENDAS.md`; decisões em `COMPARTILHADO/DECISOES.md` (D10 e E2). **E3** (a fonte passa a ser servida pelo pacote), escrita pela sessão do ChamadosHS a partir do `D1-a`. **E5** (03/09/2026 — `--text-muted` vai de slate-500 a slate-600 e `--on-tint-neutral` volta a ser o alias `var(--text-muted)`), escrita pela sessão do ChamadosHS. **E7** (03/09/2026 — nasce o `--border-control`, e sete componentes de `forms/` passam a delimitar controle com ele), escrita pela sessão do HelpHS. **E8** (03/09/2026 — os pares de `success`, `info` e `danger` saem da reprovação sobre `--surface-elevated`) e **E9** (`Checkbox` e `Switch` passam a mostrar foco), a primeira do ChamadosHS e a segunda do HelpHS. Recopiados os sete arquivos a cada emenda; a E3 traz também o diretório `fonts/`. |

## Hashes (SHA256)

Conferidos com `Get-FileHash` contra o pacote no momento da cópia. Os sete
arquivos são **idênticos ao original** — sem cabeçalho de origem, sem
reformatação, sem uma vírgula de diferença. Foi decisão explícita
(D3 em `COMPARTILHADO/DECISOES.md`): a seção 5.2 do prompt mestre pede um
comentário de origem no topo de cada arquivo, mas a seção 33 e o operador pedem
conferência por hash — e as duas coisas não cabem juntas. O aviso mora aqui.

```
base.css         BDD047CE432E74B33FA7F752DA08CF025419E83EA18485BD947C889C0AC1C221
colors.css       73550E08F6F951571068EEC741278FC2A7EDB5CEEC9CDDFC997111BC0F741139
motion.css       C70D51A982AE0B91BD53ECE150D8D16E0E70BEF9CA59586541A9A7177228478E
shape.css        7BCFBBC585D3EA8C7F689A27EEB3AE13DE0C2A9DCC3C6CC0C8F41D440D193F7D
spacing.css      C093B261C6893A893A418CDF64798555326D4586A8ADB37CC7ECA457FABAE420
styles.css       1EF6324844AA066488F0D8A015B39E3CA0756C629512FCE4E1BD95CA8B93B9B2
typography.css   1DD9B29E47D31005DA89BBE96F1C7883A89371173E0FA8862D868480EEE839C9
```

Para reconferir:

```powershell
$ds="C:\Users\ti_rickelme\Documents\GitHub\design-system"
$lo="src\design-system"
Compare-Object `
  (Get-ChildItem "$ds\styles.css","$ds\tokens\*.css" | Sort Name | % { (Get-FileHash $_).Hash }) `
  (Get-ChildItem "$lo\styles.css","$lo\tokens\*.css" | Sort Name | % { (Get-FileHash $_).Hash })
```

Saída vazia = em dia.

Desde a **E3** as fontes também são cópia do pacote, e conferem do mesmo jeito:

```powershell
Compare-Object `
  (Get-ChildItem "$ds\fonts\*.woff2" | Sort Name | % { (Get-FileHash $_).Hash }) `
  (Get-ChildItem "$lo\fonts\*.woff2" | Sort Name | % { (Get-FileHash $_).Hash })
```

## A E5, e o que ela desfez aqui

A **E5** corrigiu `--text-muted` na raiz: era `slate-500`, que sobre
`--surface-elevated` dava **4,34:1**. Passa a `slate-600`, e
`--on-tint-neutral` volta à condição de **alias** (`var(--text-muted)`) — o
valor resolvido é o mesmo `#475569` de antes, mas a expressão volta a dizer o
que significa. A E2 precisara cravar o degrau porque o alias apontava para o
valor errado; corrigido o alias, o desvio deixou de ser necessário.

Medido aqui depois da recópia, contra **as três superfícies** e nos **dois
temas** — que é a regra que a E5 deixou escrita no `EMENDAS.md`:

| Token | Tema | `--surface` | `--bg-base` | `--surface-elevated` |
|---|---|---:|---:|---:|
| `--text-muted` | claro | 4,76 → **7,58** | 4,55 → **7,24** | 4,34 → **6,92** |
| `--text-muted` | escuro | 6,23 | 6,78 | 5,29 — inalterado |
| `--on-tint-neutral` | ambos | idêntico a `--text-muted` | | |

O `.dark` não mudou por decisão, e não por esquecimento: lá o token é slate-400
e já aprovava nas três; escurecer pioraria, porque no escuro o contraste vem de
clarear.

**O que isso consertou no HelpHS sem tocar em componente:** o `ghost` do
`Button` consome `--text-muted` direto e pinta `--surface-elevated` no hover.
Estava em 4,34:1 no claro — achado na Fase 7, e **não** corrigido localmente de
propósito, para não recriar o desvio que a E2 tinha acabado de eliminar. A E5
o levou a **6,92:1** na origem. Nenhuma linha do `Button.tsx` mudou.

**A E4 está no `EMENDAS.md` como "não aplicada".** Em 03/09/2026 o operador
decidiu: a emenda não entra, porque a E5 a torna desnecessária — depois dela
`--text-muted` e `--on-tint-neutral` resolvem para o mesmo `#475569`, e adotar a
E4 seria trocar um token pelo seu próprio alias. A alteração de origem
desconhecida que o `Avatar.jsx` do pacote carregava desde 02/09 **foi
revertida**; o arquivo voltou ao valor do export, com hash
`7CF223928607A3ADBA0E67CEA8C0B74ACD6269D01FFDB86ECCCF7E99092DB2C9`.

O número **E4 fica gasto** no registro em vez de ser reaproveitado: uma sequência
sem buracos daria a entender que toda mudança no pacote passou por decisão
registrada, e uma não passou. **A pergunta de quem editou continua aberta** — a
reversão devolve o conteúdo, não responde a autoria.

## A E7 e o token que faltava

Nenhum dos três tokens de borda do pacote servia de **contorno de controle**.
Medido contra as três superfícies, nos dois temas, com o piso de **3:1** da
**WCAG 1.4.11** — que é o que vale para limite de componente, e não os 4,5:1 de
texto:

| Token | claro | escuro |
|---|---|---|
| `--border-color` | 1,23 · 1,18 · 1,13 ❌ | 1,39 · 1,51 · 1,18 ❌ |
| `--border-strong` | 1,48 · 1,42 · 1,36 ❌ | 2,29 · 2,50 · 1,94 ❌ |
| **`--border-control`** | **4,76 · 4,55 · 4,34** ✅ | **6,23 · 6,78 · 5,29** ✅ |

Seis de seis reprovavam no mais forte dos existentes. Eles são separadores de
superfície — a linha de cabelo entre um card e o fundo — e para isso 1,2:1 é o
desenho certo. O erro era usar o mesmo token para dizer "aqui começa um campo".

**A regra, que entra junto do token:** contorno de controle usa
`--border-control`; `--border-color` e `--border-strong` são separadores.

Sete componentes de `forms/` passaram a usá-lo na borda de repouso — `Input`,
`Textarea`, `Select`, `SearchSelect` (o controle e o campo de busca de dentro),
`Checkbox`, `Radio` e o trilho desligado do `Switch`. Foco e erro não mudaram.
O painel flutuante do `SearchSelect` também não: a borda dele delimita uma
camada, não um controle.

A bolinha do `Switch` saiu de `--color-white` para `--text-on-primary`: branco
cravado sobre o `--action` do escuro dava **2,69:1**, o mesmo número da E1.

## Desvios com prazo — expiram no Checkpoint 4

Diferente da tabela de desvios acima, que são de **método** e ficam, estes são
de **forma** e têm data para sair. Não são exceção visual: são dívida.

| # | Desvio | Onde | Expira |
|---|---|---|---|
| F1 | O foco dos campos é `ring` do Tailwind — `box-shadow` por **fora** da caixa. O `Input.jsx` e o `Textarea.jsx` do pacote desenham a borda em `--action` mais um `outline` de 2px com `outlineOffset: -1`, ou seja, indicador por **dentro**. | `ui/Input.tsx`, `ui/Textarea.tsx` — **7 telas** usam `Textarea`, 66 usam `Input` | **Checkpoint 4** |

**Por que não foi alinhado agora:** mudaria a geometria do foco em todas as telas
de uma vez, numa fase de componente, sem ganho de contraste — o anel de fora já
dá 5,29:1 contra a superfície, e o piso da 1.4.11 é 3:1.

**Como sai:** cada tela alinha ao `outline` interno **quando for migrada** nas
Fases 11–16, junto da captura antes e depois que a §25 já exige. Não é um commit
de sete telas no fim; é uma linha por tela, no momento em que a tela já está
sendo olhada.

**O que acontece se sobrar:** o Checkpoint 4 é onde isto é conferido. Um desvio
de forma que atravessa a migração inteira deixa de ser dívida e vira o desenho —
e aí a decisão é registrar como exceção ou pagar. O prazo existe para forçar essa
escolha a ser feita, e não a ser esquecida.

## A E8, e o que ela ensinou sobre medir

A **E8** foi escrita pela sessão do ChamadosHS e corrige os pares
`--tint-*` / `--on-tint-*` que reprovavam sobre `--surface-elevated`. Cinco
linhas: dois degraus novos na rampa (`--color-danger-300`, `--color-info-300`) e
três reatribuições.

**A direção não é a mesma nos dois temas**, e essa é a parte contraintuitiva. No
claro os pares são degraus 700 — texto escuro sobre tinta clara — e a correção é
**subir** para o 800. No escuro são degraus 400 — texto claro sobre tinta escura
— e ali o 800 seria quase preto sobre quase preto: a correção é **descer** para o
300, clareando. É o mesmo que a **E1** fixou para `--action`: o degrau que
carrega um papel inverte com o tema.

| | antes | depois |
|---|---:|---:|
| `on-tint-success`, claro, elevada | 4,39 ❌ | **6,15** ✅ |
| `on-tint-danger`, escuro, elevada | 4,38 ❌ | **6,38** ✅ |
| `on-tint-info`, escuro, elevada | 4,40 ❌ | **6,21** ✅ |

### Ela não alcançou o HelpHS sozinha

O `Badge` daqui não lia nenhum dos três tokens: pintava `bg-<cor>/20` e escrevia
`text-<cor>-700 dark:text-<cor>-400` à mão. **A emenda passou por cima do
componente sem tocá-lo.**

Medido nos tokens depois da recópia: **zero reprovações**. Medido no
**componente**: **sete**, em 42 combinações, a pior em 2,77:1. O componente só
entrou na conta quando passou a consumir as tintas e seus pares (`a1e9559`).

**A regra que fica**, registrada em `COMPARTILHADO/DECISOES.md`: evidência de
contraste se mede no **componente renderizado**, nunca no token. Token medido
prova que a paleta é sólida — a mesma frase que abriu a varredura de contraste,
agora provada uma segunda vez, por dentro.

## Como isto entra na aplicação

`src/index.css` importa `design-system/styles.css` **antes** das diretivas
`@tailwind` (Passo 1 de `guidelines/adocao.md`). O `tailwind.config.js` mapeia
o tema para esses tokens.

## Desvios locais aprovados

Nenhum desvio de **valor**. Os tokens são consumidos exatamente como o pacote
os define. Os itens abaixo são desvios de **método**, todos registrados em
`COMPARTILHADO/DECISOES.md`:

| # | Desvio | Motivo |
|---|---|---|
| D1 | As cores no `tailwind.config.js` usam `color-mix(…)` em vez do `var(--token)` puro do `adocao.md` | Com `var()` puro o Tailwind v3 **não gera** os utilitários com opacidade. Verificado compilando: apagaria 398 usos, em silêncio. |
| D2 | Os nomes antigos `background-*` e `border-*` seguem como alias dos novos `surface-*` e `borda-*` | ~700 usos. A troca é por tela (Fases 11–16); os alias saem na Fase 20. |
| D3 | Sem comentário de origem nos arquivos copiados | Conflita com a conferência por hash. O aviso está no topo deste arquivo. |
| D5 | O bloco de inversão de tema do `index.css` continua no lugar | É o que segura o tema claro hoje; sai na Fase 20, quando `text-slate-*` chegar a zero. |

**O `D1-a` deixou de existir aqui.** Era o desvio que trocava o `@import` do Google Fonts por `@fontsource` dentro do consumidor, e que fazia o `typography.css` local não bater com o do pacote. A **E3** resolveu na raiz: o arquivo volta a ser cópia byte a byte, e a fonte vem de `fonts/`.

**O `.gitattributes` ganhou uma linha por causa da E3.** A regra do `D7-a` (`frontend/src/design-system/** text eol=lf`) é um `text` **explícito** e vence a detecção automática do `* text=auto` — ela alcançava os `.woff2` e o git normalizaria fim de linha **dentro da fonte**. Não era risco teórico: quatro dos doze arquivos contêm a sequência `0D 0A`, e cada um perderia um byte no commit. A linha `frontend/src/design-system/fonts/*.woff2 -text` desliga isso; conferido com `git check-attr` (passa a `text: unset`) e com os doze blobs gravados, todos idênticos byte a byte ao arquivo em disco.

## Exceções visuais do HelpHS (seção 8.1 do prompt mestre)

Preservadas de propósito. Não são desvio de token:

- **Login com painel escuro sólido `#0D1623`** — `pages/auth/AuthShell.tsx` e
  `pages/auth/LoginPage.tsx`. Uma das duas exceções à regra "cor chapada".
- **Pulso do logo no login** (`animate-logo-pulse`) — a única animação em laço
  permitida fora do `Spinner`.
- **Setas de ordenação `↑ ↓ ↕`** e o **`×` do `TagBadge`** — caracteres de
  texto no papel de ícone, tolerados por herança.

Pendente de decisão (não está no pacote): o `#080F1A` do painel de branding do
login e do registro. O `readme.md` só documenta o `#0D1623`.
