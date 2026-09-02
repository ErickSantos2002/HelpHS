# Fase 7 — Componentes core — HelpHS

Relatório no formato da seção 32. Cobre `Avatar`, `Card`, `Badge` e `Icon`;
`Button` e `Spinner` já haviam entrado em `a5f43d0`, `714961b` e `9837be4`.

## ⛔ Duas coisas para ler antes do resto

**1. Isto não é o Checkpoint 2.** A seção 26 fecha o Checkpoint 2 *após a Fase
10* — componentes core (7), formulários (8), dados (9) e feedback/navegação
(10). Esta fase entrega só a **7**. As Fases 8, 9 e 10 não começaram, e por isso
a matriz 7.1 vai aqui preenchida apenas nas linhas de `core/`. O que falta está
na seção 12.

**2. A emenda E4 chegou ao pacote sem autor conhecido.** Ela está aplicada em
`design-system/components/core/Avatar.jsx`, e **nenhuma das duas sessões a
escreveu**. Detalhe na seção 4. **Nada foi registrado no `EMENDAS.md`** — o
registro depende de uma decisão sua.

---

## 1. Estado anterior

| Arquivo | Linha | Valor |
|---|---|---|
| `frontend/src/components/ui/Avatar.tsx` | 41 | `"bg-surface-elevated text-conteudo-muted"` — sexto par de `COLORS` |
| `frontend/src/components/ui/Card.tsx` | 24 | `"rounded-xl border border-border bg-background-surface"` |
| `frontend/src/components/ui/Card.tsx` | 43 | `"… border-b border-border pb-4 mb-4"` |
| `frontend/src/components/ui/Card.tsx` | 60 | `cn("text-base font-semibold text-slate-100", className)` |
| `frontend/src/components/ui/Badge.tsx` | 20 | `secondary: "bg-background-elevated text-slate-300 border-border"` |
| `frontend/src/components/ui/Badge.tsx` | 22 | `warning: "bg-warning/20 text-warning-700 dark:text-warning-400 border-warning/30"` |
| `frontend/src/components/ui/Badge.tsx` | 25 | `muted: "bg-background-elevated text-slate-500 border-border"` |
| `frontend/src/components/ui/Icon.tsx` | — | **não existia**; 229 `<svg>` inline em 35 arquivos |
| `frontend/tailwind.config.js` | 65–76 | `on-primary`, `on-danger`, `on-success` — **nenhum `on-tint-*`** |
| `frontend/src/test/components/Card.test.tsx` | — | **não existia** |

## 2. Design System aplicável

- `DS/components/core/Avatar.jsx` — `COLORS`, `SIZES`, `FONT`
- `DS/components/core/Card.jsx` — `Card`, `CardHeader`, `CardTitle`
- `DS/components/core/Badge.jsx` — `VARIANTS`, `STATUS`, `PRIORITY`
- `DS/components/core/Icon.jsx` — `ICON_PATHS` (25) e defaults 20px / 1,75
- `DS/tokens/colors.css` — `--on-tint-neutral`, `--on-tint-warning`,
  `--text-heading`, `--surface`, `--border-color`, `--tint-*`
- `design-system/EMENDAS.md` — E2 (pendência do avatar) e **E4**

## 3. Alterações realizadas

| Arquivo | Alteração | Regra do Design System |
|---|---|---|
| `ui/Avatar.tsx` | sexto par → `text-on-tint-neutral` | `Avatar.jsx` COLORS, emenda E4 |
| `ui/Card.tsx` | `text-slate-100` → `text-conteudo-heading` | `Card.jsx` → `color: var(--text-heading)` |
| `ui/Card.tsx` | `bg-background-surface` → `bg-surface`; `border-border` → `border-borda` (2×) | nomes do pacote; sai da conta do D2 |
| `ui/Badge.tsx` | `secondary` e `muted` → `text-on-tint-neutral` | `Badge.jsx` VARIANTS (com desvio: ver 10) |
| `ui/Badge.tsx` | `warning` → `text-on-tint-warning`, sem `dark:` | `Badge.jsx` VARIANTS; o token já inverte |
| `ui/Icon.tsx` | **novo** — 25 traçados, `ICON_PATHS`, defaults do pacote | `Icon.jsx` |
| `ui/index.ts` | exporta `Icon`, `ICON_PATHS`, `IconProps`, `IconName` | — |
| `tailwind.config.js` | `+ on-tint-neutral`, `+ on-tint-warning` | par de tinta ≠ degrau de texto (como `on-primary`) |
| `dev/GaleriaPrimitivos.tsx` | **novo** — galeria dos quatro, sob guarda `DEV` | seção 26 (evidência) |
| `scripts/capturar-primitivos.mjs` | **novo** — captura com rede blindada | seção 26 |
| `App.tsx` | rota `/galeria-primitivos` dentro do `import.meta.env.DEV` | sai na Fase 20 |

Commits: `a9ff104` (Avatar) · `a5936cf` (Card) · `3554323` (Badge) ·
`e6e3623` (Icon). Nenhum deles tocou os cinco arquivos do `design-system/` que
estão modificados na árvore — são de outra sessão, e ficaram fora do índice.

## 4. A emenda E4 — aplicada no pacote, sem autor conhecido

O que está no pacote hoje:

```js
["var(--surface-elevated)", "var(--on-tint-neutral)"],
```

O que a **E2** registrou como pendência, e o que o export original tem:

```js
["var(--surface-elevated)", "var(--text-muted)"],
```

**Cronologia, por mtime:**

| Arquivo | mtime | |
|---|---|---|
| `_ds_bundle.js` e os outros 29 componentes | 02/09 **10:43** | export original |
| `components/core/Button.jsx` | 02/09 **16:00** | emenda E2, da sessão HelpHS |
| `EMENDAS.md` | 02/09 **16:05** | E1, E2, E3 — **sem E4** |
| `components/core/Avatar.jsx` | 02/09 **16:54** | ← a mudança |

**Não foi esta sessão:** cheguei ao arquivo às 17:0x e ele já estava assim.

**Não foi a sessão do ChamadosHS:** ela varreu os 9 transcripts do próprio
workflow por `Write`/`Edit` e por `Bash` com `sed -i`, redirecionamento, `tee`,
`cp`, `mv` e `writeFileSync` — zero escritas no pacote. O workflow dela só
começou a rodar às **16:57:11**, três minutos *depois* do mtime; o agente que
leu o `Avatar.jsx` reportou a mesma anomalia por conta própria.

**Hash de antes: reconstruído, não medido.** Ninguém leu o arquivo antes das
16:54, então não existe medição. O que existe é evidência independente do valor
anterior: o `_ds_bundle.js` (mtime 10:43, intocado) traz o `Avatar` transpilado
com `--text-muted` no sexto par. Reconstruindo o arquivo com esse único token
trocado de volta:

```
ARQUIVO ATUAL         833AF4040FF8A17FFC0C4BF30316FE6A1B1AFB568BB3F073D4BFDC18D0BB1154   1738 bytes   0 CR
RECONSTRUÍDO (antes)  7CF223928607A3ADBA0E67CEA8C0B74ACD6269D01FFDB86ECCCF7E99092DB2C9   1733 bytes   0 CR

diff: uma linha, o sexto par de COLORS
```

As duas sessões chegaram a esse hash **por caminhos independentes** e bateram.
Ele só é o hash real se a única alteração das 16:54 tiver sido esse token — o
que é compatível com tudo o que se pôde conferir contra o bundle (SIZES, FONT,
os cinco primeiros pares, `initials` e `colorFromName` idênticos), mas não é
demonstrável byte a byte, porque o bundle é transpilado.

**Por isso o `EMENDAS.md` não foi tocado.** Registrar como emenda deliberada uma
mudança de origem desconhecida transformaria "não sabemos quem fez" em fato
consumado, dentro do arquivo que existe justamente para impedir isso. Se foi
você quem aplicou, o registro sai em cinco minutos e com a sua autoria. Se não
foi, há uma quarta mão no pacote e isso é mais importante do que a emenda.

## 5. Contraste medido

WCAG 2.x, valores lidos de `tokens/colors.css`. Conferido à mão e por teste.

**Avatar — sexto par (fundo `--surface-elevated`)**

| Tema | Antes | Depois |
|---|---:|---:|
| claro | 4,34:1 ❌ | **6,92:1** ✅ |
| escuro | 5,29:1 ✅ | **5,29:1** ✅ (idêntico) |

**Badge**

| Variante | Tema | Antes | Depois |
|---|---|---:|---:|
| `muted` | claro | 4,34:1 ❌ | **6,92:1** ✅ |
| `muted` | escuro | **2,85:1** ❌ | **5,29:1** ✅ |
| `warning` | claro | 4,32:1 ❌ | **6,10:1** ✅ |
| `warning` | escuro | 7,01:1 ✅ | 7,01:1 ✅ |
| `secondary` | claro | 9,45:1 ✅ | **6,92:1** ✅ ↓ |
| `secondary` | escuro | 9,13:1 ✅ | **5,29:1** ✅ ↓ |

**Card — título sobre `--surface`**

| Tema | Antes | Depois |
|---|---:|---:|
| claro | 17,85:1 ✅ | 17,85:1 ✅ |
| escuro | 14,59:1 ✅ | 14,59:1 ✅ |

Quatro reprovações saíram. O `secondary` **perdeu** contraste de propósito, e
segue acima de AA nos dois temas — ver seção 10.

## 6. Funcionalidades preservadas (seção 29)

**Nenhuma página foi alterada nesta fase**, então o checklist por rota da seção
29 não se aplica ainda; ele volta nas Fases 11–16. O que se preservou aqui:

```text
Primitivos: Avatar, Card, Badge, Icon
[x] API pública inalterada (nenhuma prop criada, removida ou renomeada)
[x] nenhuma chamada de API tocada — os quatro não fazem requisição
[x] nenhum comportamento alterado: só string de classe
[x] Avatar segue determinístico — mesma pessoa, mesma cor
[x] StatusBadge e PriorityBadge seguem mapeando os mesmos status
[x] tema claro e escuro conferidos por screenshot nos dois
[x] suíte inteira verde, inclusive os testes de página que consomem os quatro
```

`Icon` é adição pura: nenhuma chamada existente passou a usá-lo.

## 7. Testes executados

```text
lint:       npm run lint      → 1 problem (0 errors, 1 warning)
                                 o de sempre: react-refresh em ThemeContext.tsx:60
typecheck:  npm run typecheck → tsc -b, sem saída (limpo)
unit tests: npm test          → 44 arquivos, 416 testes, 100% verdes
                                 (eram 42 e 391 no início da fase: +2 arquivos, +25 testes)
build:      npm run build     → ✓ built in 10,95s
visual:     node scripts/capturar-primitivos.mjs
                              → 2 PNG, 75 ícones e 22 selos em cada, 0 fuga de rede
```

**Os 25 testes novos foram validados por mutação**, e cada mutação derrubou
exatamente o teste que devia:

| Mutação | Caiu |
|---|---|
| `--on-tint-neutral` → slate-500 (valor pré-E2) | 2 (`expected 4.343923406321176 …`) |
| `--on-tint-neutral` do `.dark` → `--text-faint` | 2 (`expected 2.848… to be 5.286005871414902`) |
| tamanho padrão do `Icon` 20 → 24 | 1 |
| `aria-hidden` removido do `Icon` | 1 |
| `shrink-0` removido do `Icon` | 1 |
| `return null` → `<svg />` em nome desconhecido | 1 |
| um pixel no traçado do `plus` | 1 (só depois do teste de hash — ver abaixo) |

O `colors.css` voltou byte a byte depois das duas primeiras: `696ABC6D…`, o
mesmo hash que o `VERSION.md` publica.

**Um teste foi reescrito por ser tautológico.** O primeiro teste de traçados
comparava o `d` renderizado com `ICON_PATHS[nome]` — a tabela consigo mesma.
Medido: mudar um pixel do `plus` não derrubava nada. Ele foi mantido (ainda
prende a fiação e a unicidade dos 25) e ganhou um irmão que prende os 25 a um
`SHA256` calculado do pacote — `1B07BB04C263…` —, no mesmo idioma que o
`VERSION.md` usa com os sete arquivos de CSS. Com ele, a mesma mutação cai.

**Utilitários conferidos no CSS compilado, não só no teste.** Classe que o
Tailwind não gera é string sem regra: o teste passa e o pixel não muda de cor.
`.text-on-tint-neutral`, `.text-on-tint-warning`, `.bg-surface`, `.border-borda`
e `.text-conteudo-heading` — as cinco geram regra.

## 8. Screenshots

`docs/design-system-migration/fase-7/screenshots/`

| Arquivo | Tema | Resolução |
|---|---|---|
| `helphs-primitivos-claro-1366.png` | claro | 1366×900, página inteira, DPR 2 |
| `helphs-primitivos-escuro-1366.png` | escuro | 1366×900, página inteira, DPR 2 |

Conferido **olhando as imagens**, não só a existência dos arquivos: os seis
pares do avatar distintos, com o neutro (`E`) legível nos dois temas; as sete
variantes de selo, os sete status e as quatro prioridades; os quatro paddings de
card com o título claro no escuro e escuro no claro; e os 25 ícones em três
pesos de cor, provando a herança de `currentColor`.

**As mesmas três garantias do Checkpoint 1:**

1. **Rota só em DEV.** `/galeria-primitivos` fica dentro de
   `import.meta.env.DEV`, com o `lazy()` **dentro** da condição. Provado depois
   do build: nenhum `Galeria*` em `dist/assets`, e nenhuma ocorrência de
   `galeria-primitivos` nem de `GaleriaPrimitivos` em `dist/`.
2. **Sem dado nenhum.** Diferente da galeria da casca, esta não monta
   `AuthContext` nem usuário falso — os primitivos não leem sessão. Não há dado
   a vazar porque não há dado.
3. **Rede blindada.** `scripts/capturar-primitivos.mjs` intercepta `**/*` com
   lista de permissão e **falha com código 1** se algo escapar. Saída da
   execução: `0` requisições barradas, `0` chamadas de API, `0` fugas. A
   ausência de pedido a `fonts.googleapis.com` também confirma que a **E3**
   segue de pé — a fonte vem do pacote.

## 9. Matriz 7.1 — linhas de `core/`

| Componente oficial | HelpHS | Estado |
|---|---|---|
| `core/Button` | `ui/Button.tsx` | **feito** (`a5f43d0`, `9837be4` — 5 variantes, E2) |
| `core/Card` (+Header/Title) | `ui/Card.tsx` | **feito** — falta `clickable` e `CardBody` |
| `core/Badge` (+Status/Priority/Tag) | `ui/Badge.tsx` | **feito** — com desvio no `muted` |
| `core/Avatar` | `ui/Avatar.tsx` | **feito** (E4) |
| `core/Spinner` | `ui/Spinner.tsx` | **feito** (`714961b`) |
| `core/Icon` (+`ICON_PATHS`) | `ui/Icon.tsx` | **primitivo feito; 229 chamadas pendentes** |
| `core/Rotulo` | — | **não se aplica** — exceção do ChamadosHS |
| `core/Colchetes` | — | **não se aplica** — exceção do ChamadosHS |

## 10. Divergências restantes

**Desvio deliberado, com decisão a registrar:**

- **`Badge muted` não usa `--text-faint`.** O pacote pinta `muted` com
  `--text-faint` sobre `--tint-neutral`: **2,34:1** no claro — pior que o valor
  que o HelpHS já tinha. Seguir o pacote seria trocar uma reprovação por uma
  maior. `muted` recebeu `--on-tint-neutral`, e um teste prende o motivo: se o
  pacote corrigir o `--text-faint`, o teste cai e o desvio se revê.
- **Consequência: `secondary` e `muted` ficaram idênticos.** Mesma classe, mesmo
  pixel — visível nos dois screenshots. `muted` veste `StatusBadge closed` e
  `PriorityBadge low`, que deixam de se distinguir do selo neutro comum. O
  pacote separava os dois pelo tom do texto, e é essa separação que se perde.
  Recuperá-la exige um degrau que não existe (um `--on-tint-neutral-muted`), e
  isso é emenda de pacote com decisão própria. **Não foi feito.**
- **`secondary` perdeu contraste**: 9,45 → 6,92 no claro, 9,13 → 5,29 no escuro.
  Os dois seguem acima de AA. A troca compra um par único, com um nome só, igual
  ao do avatar neutro.

**Pendências de alinhamento, sem decisão pendente:**

- **229 `<svg>` inline em 35 arquivos** seguem onde estão. A troca por `<Icon>`
  mexe em tela e é das Fases 11–16, uma por vez, com captura antes e depois. Até
  lá o `Icon` não entra no bundle: nenhuma página o importa, e o tree-shaking o
  remove — conferido, `chevronDown` não aparece em `dist/`.
- **`Card` sem `clickable` e sem `CardBody`.** O pacote tem os dois; o HelpHS
  não. Fora do escopo desta fase.
- **`Badge` pinta a tinta a 20%, o pacote usa 15%** (`--tint-*`). Medido: o
  `warning` claro dá 6,10:1 a 20% contra 6,31:1 a 15%; os dois aprovam. A troca
  do fundo espera as outras variantes saírem do `bg-*/20`.
- **`Badge secondary` e `muted` seguem em `bg-background-elevated` e
  `border-border`**, os alias do D2. Só o `Card` saiu deles nesta fase.
- **`--text-muted` continua vivo e correto** onde é degrau de texto sobre
  `--surface`; o que mudou é só o uso dele como par de tinta.

## 11. Risco de regressão

**Baixo**, com uma ressalva.

A favor: nenhuma prop, nenhuma chamada de API e nenhum comportamento mudaram —
o diff dos três componentes existentes é de string de classe. A suíte inteira
(416 testes, incluindo os de página) está verde, o build passa, e os cinco
utilitários novos foram conferidos no CSS compilado.

A ressalva não é técnica, é de produto: **`secondary` e `muted` ficaram
visualmente iguais**. Nada quebra, mas "Fechado" e "Baixo" perderam a distinção
que tinham. Se isso importar, o conserto é uma emenda de pacote, não um ajuste
local.

## 12. O que falta para o Checkpoint 2

- [ ] **Fase 8** — formulários (`Input`, `Textarea`, `Select`, `SearchSelect` e
      a unificação dos três seletores, `Checkbox`, `Radio`, `Switch`,
      `FileUpload`)
- [ ] **Fase 9** — dados (`Table`, `Pagination`, `SlaChip`)
- [ ] **Fase 10** — feedback e navegação (`Alert`, `Modal`, `Toast`, `Tooltip`,
      `Tabs`)
- [ ] **Matriz 7.1 completa**, com as linhas de `forms/`, `data/`, `feedback/` e
      `navigation/` marcadas feito/pendente
- [ ] **Galeria estendida** aos primitivos dessas três fases, e recaptura
- [ ] **Mapa de status do ChamadosHS** (seção 16) — é da outra sessão, não desta
- [ ] **Decisão sobre a E4**: quem aplicou, e se o registro entra com hash
      reconstruído e declarado como tal

## 13. Commits sugeridos

Os quatro já estão feitos, no formato da seção 31:

```text
a9ff104  style(ui): o disco neutro do Avatar adota o par da E4
a5936cf  style(ui): Card larga o slate cravado e os alias do D2
3554323  style(ui): os selos neutro e âmbar passam a falar pelos tokens do par
e6e3623  feat(ui): Icon entra como primitivo, com os 25 tracos do pacote
```

Falta o deste relatório e da galeria:

```text
docs(design-system): relatorio da Fase 7 e galeria dos primitivos
```
