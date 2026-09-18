# Fase 0 — Diagnóstico — HelpHS

> Escopo desta sessão: **apenas HelpHS** (`frontend/`). O ChamadosHS está sendo
> migrado em paralelo por outra sessão e não está acessível aqui; a coluna dele
> nas matrizes fica vazia por decisão do operador, não por falta de leitura.
>
> Design System lido em `C:\Users\ti_rickelme\Documents\GitHub\design-system`
> (somente leitura). Nada foi alterado nesta fase — nem no DS, nem no HelpHS.
> Este arquivo e a pasta que o contém são o único artefato criado.

## Estado anterior (linha de base)

Nada foi alterado. Os números abaixo são a régua contra a qual o Checkpoint 1
vai comparar.

| Medida | Valor | Como foi obtido |
|---|---|---|
| Hexadecimais cravados — código de produção | **228** em 13 arquivos | `grep -rnoE "#[0-9a-fA-F]{3,8}\b" src` menos `src/test/` |
| Hexadecimais cravados — fixtures de teste | **26** em 4 arquivos | idem, só `src/test/` |
| Hexadecimais cravados — total | **254** | soma |
| Ocorrências de `dark:` | **563** em 406 linhas / 28 arquivos | `grep -rho "dark:[a-zA-Z0-9_/-]*" src` |
| Classes `text-slate-*` (dependem do hack de inversão) | **~1.158** | contagem por utilitário |
| Utilitários com modificador de opacidade sobre cor remapeada | **398** em 38 arquivos | ver Decisão 2 |
| Tokens no DS | **179** | `grep -hoE "^\s+--[a-z0-9-]+:" tokens/*.css \| wc -l` — bate com `_ds_manifest.json` |
| Arquivos no DS | **158** | `find . -type f \| wc -l` — bate com o prompt |

### Hexadecimais por arquivo (produção)

```
103  src/pages/reports/ReportsPage.tsx
 34  src/pages/dashboard/AdminDashboard.tsx
 22  src/pages/calendar/CalendarPage.tsx
 18  src/pages/tickets/TicketListPage.tsx
 16  src/pages/settings/SettingsPage.tsx
 12  src/pages/dashboard/TechnicianDashboard.tsx
 10  src/index.css
  3  src/pages/kb/KBListPage.tsx
  3  src/pages/kb/KBFormPage.tsx
  3  src/pages/auth/LoginPage.tsx
  2  src/lib/colors.ts
  1  src/pages/auth/RegisterPage.tsx
  1  src/pages/auth/AuthShell.tsx
```

Nem todos são desvio. A separação importa porque muda a meta do Checkpoint 1:

- **Desvio real (a corrigir):** `#0ea5e9` (14×, a rampa antiga), os pares
  claro/escuro cravados em `tooltipStyle` de gráfico do Recharts
  (`#132238`/`#ffffff`, `#1E3A5F`/`#e2e8f0`, `#0f172a`/`#f1f5f9`), e os
  `#2d3748`/`#94a3b8`/`#475569` de eixo e grade — ~120 ocorrências.
- **Exceção documentada (preservar):** `#0D1623` em `AuthShell.tsx:21` e
  `LoginPage.tsx:224` — é o painel escuro do login previsto na seção 8.1.
  `#080F1A` (`LoginPage.tsx:173`, `RegisterPage.tsx:139`) é do mesmo painel e
  **não** está no pacote: entra como divergência a decidir.
- **Dado, não estilo (preservar):** as paletas de escolha do usuário em
  `SettingsPage.tsx:42-57` (16 cores de etiqueta) e `CalendarPage.tsx:26-53`
  (cores de categoria). O `TagBadge` do DS prevê exatamente isso — "cor livre
  do cadastro". `lib/colors.ts` (`#ffffff`/`#0f172a`) é a função de contraste
  que escolhe o texto sobre essas cores: é lógica, não paleta.
- **Fixture de teste (preservar):** `src/test/**` e `#001` de patrimônio em
  `equipmentService.test.ts`.

### Testes — linha de base, executada de verdade

```
npm run lint       → ✔ 1 problem (0 errors, 1 warning)
                     ThemeContext.tsx:60 react-refresh/only-export-components
npm run typecheck  → ✔ tsc -b, sem saída, exit 0
npm test           → ✔ Test Files 40 passed (40) | Tests 352 passed (352) | 37.29s
npm run build      → ✔ built in 14.83s
```

Gerenciador: **npm** (`package-lock.json`). Não existe script `validar:paleta`
nem qualquer validador de cor — confirmado lendo o `package.json`.

## Design System aplicável

Confirmado por leitura direta, não pelo prompt:

- `styles.css` → só seis `@import` de `tokens/`.
- `tokens/{colors,typography,spacing,shape,motion,base}.css` → 179 custom
  properties. Todos os valores citados no prompt mestre conferem.
- `_ds_manifest.json` → namespace `HealthAmpSafetyDesignSystem_ef9f35`,
  179 tokens, 46 exports.
- `components/core/Icon.jsx` → `ICON_PATHS` com **25** nomes:
  `bell book box calendar chart chat check chevronDown clock close cpu
  dashboard error filter groups info logout menu plus search shield tag ticket
  users warning`.
- `guidelines/adocao.md` → Passos 1–4 e o bloco `theme.extend` (ver Decisão 2).

SHA256 dos arquivos que a Fase 1 deve copiar sem editar (`Get-FileHash`):

```
base.css         BDD047CE432E74B33FA7F752DA08CF025419E83EA18485BD947C889C0AC1C221
colors.css       63D960841590A2CB4DF3819E2CB4A55439C893578ABFE68C00927A7ABA0F307D
motion.css       C70D51A982AE0B91BD53ECE150D8D16E0E70BEF9CA59586541A9A7177228478E
shape.css        7BCFBBC585D3EA8C7F689A27EEB3AE13DE0C2A9DCC3C6CC0C8F41D440D193F7D
spacing.css      C093B261C6893A893A418CDF64798555326D4586A8ADB37CC7ECA457FABAE420
styles.css       1EF6324844AA066488F0D8A015B39E3CA0756C629512FCE4E1BD95CA8B93B9B2
typography.css   99D1A02B92B120C78000C0BC016C616680EFFB3E13B512E914F3F4F578CA916A
```

## Matriz de Diagnóstico (seção 3)

| Área | HelpHS atual | ChamadosHS | Design System | Ação necessária |
|---|---|---|---|---|
| **Versões** | React 19.2.4 · TS 5.8.3 · Vite 6.4.2 · **Tailwind 3.4.19 (v3)** · npm · Node ≥20 | *fora do escopo* | assume React+TS+Vite+Tailwind | Nenhuma. Não migrar versão de Tailwind (seção 30). |
| **Estratégia de tema** | classe `dark` no `<html>`; `ThemeContext.tsx` + script anti-flash duplicado no `index.html`; `localStorage["helphs-theme"]`; sem escolha → `prefers-color-scheme`, e **sem `matchMedia` cai no escuro** | — | `.dark` no `<html>` | Compatível. Preservar o par contexto/script (o comentário no código avisa que a regra é duplicada à mão). |
| **CSS global** | `src/index.css`: `@import` do Google Fonts → `@tailwind base/components/utilities` → `@layer base` com tokens | — | tokens **antes** do Tailwind | ⚠️ Ordem errada hoje. Tokens precisam vir antes das diretivas. |
| **Tailwind config** | `theme.extend.colors` com rampa `primary` **`#0EA5E9`**; `background.{DEFAULT,surface,elevated}` e `border.{DEFAULT,muted}` via `rgb(var(--x) / <alpha-value>)`; `fontFamily.sans` literal; `keyframes.logo-pulse` **3s** | — | bloco do `adocao.md` | Trocar rampa; ver **Decisão 2** antes de aplicar o bloco. |
| **Tokens de cor** | **5 variáveis**, guardadas como **tripla RGB** (`--bg-base: 248 250 252`) | — | ~40 aliases, cor completa (`--bg-base: var(--color-slate-50)`) | **Colisão de nome com formato incompatível** — ver **Decisão 1**. |
| **Fonte** | Plus Jakarta Sans, carregada **uma única vez** (`@import` no `index.css`; não há `<link>` no `index.html`) | — | mesma fonte, `@import` no token | ✅ Já bate. Só remover o `@import` local quando o token entrar, para não duplicar. Mono: **não configurada** no Tailwind. |
| **Ícones** | SVG inline. 13 funções `Icon*` em `Sidebar.tsx` (24 viewBox, stroke 1.75, 20px) + dezenas soltas em páginas. Sem `lucide-react`. | — | `Icon` + 25 `ICON_PATHS` | Extrair primitivo `Icon`. Traço e tamanho da sidebar **já batem** com a regra do DS. |
| **Gráficos** | `recharts` 3.8.1 em Admin/Technician Dashboard e ReportsPage; cores e `tooltipStyle` cravados em hex | — | série em `--color-primary-500`, grade `--border-color` | Ler os valores das CSS vars (seção 17). É a maior massa de hex (≈150). |
| **Toast** | **`sonner` 2.0.7**, configurado em `AppLayout.tsx`: `theme="dark"` fixo, `top-right`, `richColors`, `closeButton`, 4000ms | — | mesma lib, tokens `--toast-*`, 80px do topo | Confirmado. Passar tokens; `theme="dark"` fixo é bug de tema (não segue o app). |
| **Layout/casca** | `layout/{AppLayout,Sidebar,Topbar}.tsx` | — | `AppShell` | Ver matriz 7.1 e "Aderência da casca". |
| **Roteamento e permissões** | `react-router-dom` 7.18.3; `App.tsx` com `AuthGuard` → `OnboardingGuard` → `AppLayout` → `RoleGuard roles={[...]}`; 3 papéis (`admin`/`technician`/`client`) | — | não governa | **Não tocar.** Governado pelo projeto (seção 10). |
| **Componentes ui** | 18 arquivos em `components/ui/` | — | 30 primitivos | Ver matriz 7.1. |
| **Páginas** | 27 rotas (lista abaixo) | — | 3 templates | Fases 11–16. |
| **Testes** | Vitest 4.1.2 + Testing Library; **40 arquivos / 352 testes**; Playwright 1.59 em `e2e/` (**exige backend na 8001**); sem Storybook; sem `toHaveScreenshot` | — | — | Rodar suíte a cada checkpoint. Screenshots: ver **Decisão 4**. |
| **Lint** | ESLint 9 flat config; Prettier existe mas **CI não checa formato** | — | `_adherence.oxlintrc.json` como inspiração | Regra `no-restricted-syntax` de hex é opcional (seção 5.4). ⚠️ Não rodar `prettier --write`. |
| **Bibliotecas de componente** | Nenhuma. Sem Radix, sem shadcn, sem `cva`. Só `clsx` 2.1.1 via `lib/utils.ts` | — | — | Nada a fazer. |
| **`@tailwindcss/typography`** | **Não instalado.** KB usa `marked` + `dompurify` | — | não instalar | Estilizar à mão (seção 19). |

### Rotas e papéis (levantadas de `App.tsx`)

| Rota | Arquivo | Quem acessa |
|---|---|---|
| `/login`, `/register`, `/esqueci-senha`, `/redefinir-senha` | `pages/auth/*` | público (só deslogado) |
| `/confirmar-email` | `auth/VerifyEmailPage` | público |
| `/privacidade` | `legal/PoliticaPrivacidadePage` | público |
| `/403`, `*` | `errors/{Forbidden,NotFound}Page` | qualquer |
| `/onboarding` | `onboarding/OnboardingPage` | autenticado, fora da casca |
| `/` | `HomePage` → dashboard por papel | admin · technician · client |
| `/tickets`, `/tickets/new`, `/tickets/:id`, `/tickets/:id/edit` | `tickets/*` | admin · technician · client |
| `/notifications` | `notifications/NotificationsPage` | admin · technician · client |
| `/kb`, `/kb/new`, `/kb/:id`, `/kb/:id/edit` | `kb/*` | admin · technician · client |
| `/profile` | `profile/ProfilePage` | admin · technician · client |
| `/equipment` | `equipment/EquipmentPage` | client (menu) |
| `/reports`, `/agenda` | `reports/`, `calendar/` | admin · technician |
| `/users`, `/products`, `/etiquetas`, `/respostas-rapidas`, `/grupos` | — | admin · technician |
| `/sla-config`, `/audit-logs` | `sla/`, `audit/` | admin |

## Matriz de componentes (seção 7.1) — coluna HelpHS

Caminhos confirmados com `ls`, não presumidos do `github.md`.

| Componente oficial | HelpHS — arquivo real | Situação |
|---|---|---|
| `core/Button` | `ui/Button.tsx` ✔ | Tamanhos `sm/md/lg` **batem exatamente**. Faltam variante `success`, props `icon` e `fullWidth`. `secondary` diverge (sem borda; DS pede `--surface` + borda 1px). `ghost` usa `text-slate-300` em vez de `--text-muted`. |
| `core/Card` (+Header/Title/**Body**) | `ui/Card.tsx` ✔ | `rounded-xl` + borda 1px + sem sombra ✔. Paddings md/lg batem; `sm` é 12px (DS não fixa). **Faltam `CardBody` e `clickable`.** `CardHeader` é slot, não aceita `title`/`description`/`action`. |
| `core/Badge` (+Status/Priority/Tag) | `ui/Badge.tsx` ✔ | **`statusVariant` e `statusLabel` batem 1:1 com o mapa do DS** (seção 16), idem prioridade. Pílula, borda 30% ✔. Tinta a **20%**, DS pede 15%. Texto usa `text-primary-700 dark:text-primary`, DS pede `--on-tint-*`. |
| `core/Avatar` | `ui/Avatar.tsx` ✔ | Tamanhos `xs/sm/md/lg` ✔, cor derivada do nome ✔. Conferir os 4 valores de px. |
| `core/Spinner` | `ui/Spinner.tsx` ✔ | `sm/md/lg` ✔. |
| `core/Rotulo` | — | **Exceção ChamadosHS. Não introduzir.** |
| `core/Colchetes` | — | **Exceção ChamadosHS. Não introduzir.** |
| `core/Icon` | SVG inline: 13 funções em `layout/Sidebar.tsx` + soltos nas páginas | Extrair `Icon` com `ICON_PATHS`. Tamanho/stroke da sidebar já corretos. |
| `forms/Input` | `ui/Input.tsx` ✔ (48 linhas, `forwardRef`) | Preservar API. Alinhar label/erro/hint/ícone/foco. |
| `forms/Textarea` | `ui/Textarea.tsx` ✔ | Idem. |
| `forms/Select` | `ui/Select.tsx` ✔ | Nativo ✔. |
| `forms/SearchSelect` | `ui/SearchSelect.tsx` + `FilterSelect.tsx` + `FormDropdown.tsx` (**3 arquivos**) | Unificar em um com `variant="form"\|"filter"` **sem mexer nas props que as páginas passam**. Os três têm teste próprio — os testes travam a API. |
| `forms/Checkbox` | **inline** em `auth/RegisterPage`, `kb/KBFormPage`, `settings/QuickRepliesPage` | Extrair primitivo. |
| `forms/Radio` (+Group) | **não existe** (`type="radio"`: 0 ocorrências) | Não criar sem necessidade (seção 30). |
| `forms/Switch` | **inline** em `layout/Topbar.tsx` (toggle de tema) | Extrair primitivo. |
| `forms/FileUpload` | **inline** em `profile/ProfilePage`, `tickets/TicketDetailPage`, `tickets/TicketFormPage` | Extrair preservando o fluxo de antivírus. |
| `data/Table` (+6) | `ui/Table.tsx` ✔ com `TableEmpty` | `TableEmpty` já traz "Nenhum resultado encontrado." ✔. **Cabeçalho não é mono**, usa `tracking-wider` (0,05em) em vez de `--tracking-label` (0,1em), e não tem fundo `--surface-elevated`. |
| `data/Pagination` | `ui/Pagination.tsx` ✔ | Janela de 5 ✔ e texto **`Mostrando X a Y de N {itens}` já exatamente como o DS pede** ✔. |
| `data/SlaChip` | `ui/SlaChip.tsx` ✔ | Props `label/dueAt/breached/respondedAt` batem com o DS. |
| `data/Progress` | — | Só ChamadosHS. |
| `data/Rating` | `ScoreRating` **inline** em `tickets/TicketDetailPage.tsx:832` — escala numérica 1–5, não estrelas | Divergência funcional legítima. Não converter em estrelas sem aprovação (seção 30). |
| `feedback/Alert` | `ui/Alert.tsx` ✔ | Variantes `info/success/warning/danger` ✔. |
| `feedback/Modal` (+Footer) | `ui/Modal.tsx` ✔ | **Já quase idêntico**: `z-[200]` ✔, `bg-black/60` ✔, `backdrop-blur-sm` ✔, `max-h-[92vh]` ✔, `role="dialog" aria-modal` ✔, 5 tamanhos ✔. |
| `feedback/Toast` | config do `sonner` em `layout/AppLayout.tsx` | Não trocar lib. Passar tokens; corrigir `theme="dark"` fixo; 80px do topo. |
| `feedback/Tooltip` | **inline** em `Sidebar.tsx` (recolhida e rodapé) e `Topbar.tsx` | Extrair primitivo. Uso já é o legítimo. |
| `navigation/Tabs` | `ui/Tabs.tsx` ✔ | Controlado ✔. |
| `navigation/AppShell` | `layout/{AppLayout,Sidebar,Topbar}.tsx` | Ver abaixo. |

### Aderência da casca (seção 9) — o que já bate e o que não

**Já conforme:** largura 256px (`md:w-64`) / 72px (`md:w-[72px]`); topbar 64px
(`h-16`); área do logo 64px com `px-5`; nav `px-2 py-3` com grupos em
`space-y-4`; item `rounded-lg px-3 py-2 text-sm font-medium gap-3` com barra
esquerda de 2px; rótulo de grupo `text-[10px] font-semibold uppercase
tracking-widest`; ícones 20px stroke 1.75; rodapé com versão (`text-xs medium`)
e © em 11px, oculto quando recolhida; `main` com `p-4 md:p-6` (16/24px);
transição da sidebar em 300ms; `aria-current="page"` (vem do `NavLink`);
tooltip só na recolhida; monograma 36×36 `rounded-lg`; skip link para
`#main-content`.

**Divergente:**

| Item | Hoje | DS |
|---|---|---|
| `<h1>` da página na topbar | **não existe** — cada página desenha seu título | `h1` 16px semibold `--text-heading` na topbar |
| Botão de recolher | só `aria-label` | exige também `aria-expanded` |
| Backdrop da gaveta | `bg-black/50` | `--overlay` = 60% |
| Logo na sidebar | `h-8` (32px) | 28px |
| Rótulo de grupo no escuro | `dark:text-slate-600` | `--text-faint` = slate-500 |
| Item ativo | `bg-primary/10 text-primary` | `--action-tint` + `--action` |
| Transição do item | `transition-all` | `--transition-colors` (só cor) |
| `main` | sem largura máxima | `--container-max` 1400px *(o DS diz "quando o projeto já limita" — o HelpHS não limita, então **manter como está**)* |
| Pulso do logo | `logo-pulse` **3s** no `tailwind.config.js` | `hs-logo-pulse` **5s** no `readme.md` |

**Breakpoint que alterna sidebar ↔ gaveta: `md` (768px)** — registrado
conforme a seção 2.2. Observação: o `index.css` usa `max-width: 1023px` (`lg`)
para esconder a barra de rolagem do `#main-content`; são breakpoints diferentes
para coisas diferentes, mas vale registrar a inconsistência.

**Escala de z-index existente** (seção 2.2 — levantar e manter, não criar
token): `z-[35]` backdrop da gaveta · `z-[40]` sidebar · `z-50` dropdowns de
notificação e usuário e tooltips · `z-[100]` skip link · **`z-[200]` modal**.
O modal já fica acima da topbar e da sidebar. ✔

## Divergências entre o pacote e a realidade

O prompt manda tratar os caminhos do `github.md` como pistas. Três afirmações
do pacote **não se confirmaram**:

1. **`adocao.md`:** *"HelpHS — o que já bate: tokens claro/escuro. O que muda:
   só a rampa primária e o `--action`. É a migração mais barata."*
   **Falso.** O HelpHS tem 5 variáveis, não os ~40 aliases do pacote, e as
   guarda em formato incompatível. Ver Decisão 1.
2. **`readme.md` / seção 12 do prompt:** *"Elimine `dark:` por classe onde
   existir token semântico."* O HelpHS tem 563 `dark:` **e** um segundo
   mecanismo de tema por inversão de classe no `index.css`. Ver Decisão 3.
3. **`tokens/motion.css`** documenta `hs-logo-pulse` como herdado do
   `tailwind.config.js` do HelpHS, mas lá a animação dura **3s**, não os 5s que
   o `readme.md` afirma. O `drop-shadow` usa `rgb(14 165 233 / …)` — o azul
   antigo. O prompt manda manter como está e anotar: **anotado**.

Micro-divergência que o prompt já previa: o rótulo de grupo da sidebar é sans
no `AppShell.jsx` e mono no template de listagem. O HelpHS usa **sans** — está
alinhado com o componente publicado, que é quem vence.

## Funcionalidades preservadas

Nenhum arquivo de código foi tocado. `git status` do `frontend/` permanece
limpo; o único acréscimo é esta pasta de documentação.

## Risco de regressão

**Nulo nesta fase.** As decisões 1 a 3 abaixo, porém, classificam a Fase 1 como
**risco alto** se executada com o bloco do `adocao.md` aplicado literalmente.

## Commit sugerido

```
docs(design-system): add phase 0 audit report for HelpHS
```

---

## Decisões derivadas pendentes (bloqueiam a Fase 1)

`COMPARTILHADO/DECISOES.md` **não existe** — a pasta só contém o prompt mestre.
Não há decisão anterior a seguir. As quatro abaixo precisam de aprovação antes
da Fase 1, conforme a seção 26 ("pare sempre que precisar de decisão que o
pacote não cobre").

### Decisão 1 — colisão de nome e formato nos tokens

`--bg-base`, `--border-color` e `--border-muted` existem nos dois lados com
**significado igual e formato incompatível**:

```css
/* HelpHS hoje — tripla RGB, para o Tailwind aplicar opacidade */
--bg-base: 248 250 252;
/* consumido como: rgb(var(--bg-base) / <alpha-value>) */

/* DS — cor completa */
--bg-base: var(--color-slate-50);
```

Importar `styles.css` como está redefine `--bg-base` para `#f8fafc`, o Tailwind
gera `rgb(#f8fafc / 1)` — inválido — e **`bg-background` (319 usos) perde o
fundo**. O mesmo vale para `border-border` (144 usos).

Os arquivos do DS não podem ser editados. Recomendo uma **ponte local**:
`src/design-system/local-bridge.css`, importado *depois* de `styles.css`,
declarando só as triplas que o Tailwind precisa
(`--tw-bg-base: 248 250 252` etc.), com comentário apontando o token de origem.
Os arquivos copiados do DS ficam byte a byte idênticos e o hash continua
batendo. A ponte some no fim da migração, quando as classes antigas saírem.

### Decisão 2 — o bloco `theme.extend` do `adocao.md` apaga 398 utilitários

**Provado, não suposto.** Compilei o Tailwind 3.4.19 do próprio projeto com as
quatro formas possíveis:

| Cor declarada como | `bg-x` | `bg-x/10` |
|---|---|---|
| `var(--action)` — **o que o `adocao.md` manda** | `background-color: var(--action)` | **classe não é gerada** |
| `rgb(var(--trip) / <alpha-value>)` — padrão atual do HelpHS | ✔ | ✔ `rgb(var(--trip) / 0.1)` |
| `color-mix(in srgb, var(--action) calc(<alpha-value> * 100%), transparent)` | ✔ | ✔ |
| `#1a71a8` literal | ✔ | ✔ |

Com o bloco literal, **398 ocorrências em 38 arquivos** deixam de produzir CSS —
entre elas `bg-primary/10` (51×, o fundo do item ativo da sidebar),
`border-border/40` (82×) e `text-primary/80` (28×). Falha silenciosa: lint,
typecheck, testes e build continuam verdes.

Recomendo declarar as cores com **`color-mix`** em vez de `var()` puro. Mantém
os nomes de token do pacote (seção 5.1), preserva os 398 usos e permite migrar
`bg-primary/10` → `bg-action-tint` por tela nas Fases 7–16, como o `adocao.md`
pede. Custo: exige Chrome 111+/Safari 16.2+/Firefox 113+.

O bloco também renomeia `background-*` → `surface-*` e `border-*` → `borda-*`,
o que atinge ~700 usos. Recomendo **manter os nomes antigos como alias** e
migrar por tela, registrando o remapeamento no relatório (a seção 5.3 pede
exatamente isso).

### Decisão 3 — o hack de inversão de tema

O `index.css` tem, além dos 563 `dark:`, um segundo mecanismo:

```css
html:not(.dark) .text-slate-100 { color: rgb(15 23 42); }  /* vira slate-900 */
html:not(.dark) .text-slate-400 { color: rgb(71 85 105); } /* vira slate-600 */
html:not(.dark) .text-slate-600 { color: rgb(148 163 184); } /* vira slate-400 */
```

Os componentes escrevem a cor **do tema escuro** e o claro espelha em torno do
500. São ~1.158 classes `text-slate-*` dependendo disso. A Fase 3, como
escrita, presume só o problema dos `dark:` — aqui são dois mecanismos
concorrentes.

Recomendo **não** remover o hack na Fase 3. Ele é a rede que segura o tema
claro. Caminho: introduzir `text-conteudo`/`text-conteudo-muted` na Fase 1,
migrar por tela nas Fases 11–16 e apagar o bloco de inversão só quando a última
classe `text-slate-*` sair — com a contagem indo a zero como prova.

### Decisão 4 — screenshots de linha de base

A seção 28 pede screenshots tirados **na Fase 0**. O Playwright do projeto
exige backend na porta 8001 com credenciais reais, e o `backend/.env` deste
ambiente aponta para o banco de **produção**. Não subo isso por conta própria.

Opções: (a) rodar o front sozinho e capturar só as telas públicas — login,
registro, privacidade, 404; (b) você me indicar um backend de teste; (c) pular
a linha de base visual e comparar só contra os UI kits do DS. Sem resposta,
sigo por (a) e registro a limitação.
