# Checkpoint 1 — Fundação (Fases 1–6) — HelpHS

> Escopo: **apenas HelpHS** (`frontend/`). O ChamadosHS é migrado por outra
> sessão; as colunas dele nas matrizes seguem vazias por decisão do operador.
>
> Branch: `chore/design-system-adoption`. **Nada foi enviado ao remoto.**

Aprovado com pendências. Este arquivo registra as evidências do que foi feito e
o que ficou em aberto — inclusive **uma pendência que não pôde ser cumprida**,
na seção "Emenda do token".

---

## 1. Commits (seção 31)

Sete commits, um por fase, do mais antigo ao mais novo:

| Commit | Fase | Mensagem |
|---|---|---|
| `d6de01c` | 0 | `docs(design-system): add phase 0 audit report for HelpHS` |
| `8e7282b` | 1 | `style(tokens): align HelpHS with official design system` |
| `63db66f` | 2 | `feat(fonts): load Plus Jakarta Sans once via design-system tokens` |
| `2161b2c` | 3 | `style(theme): replace dark: classes with semantic tokens` |
| `65eb152` | 5 | `fix(layout): group label uses --text-muted, not --text-faint` |
| `7f94b99` | 4–6 | `refactor(layout): adopt canonical shell in HelpHS` |
| `5b437b9` | — | `test(visual): add shell baseline screenshots behind a dev-only gallery` |

O `index.css` foi fatiado entre as Fases 1, 2 e 3 em vez de ir inteiro num
commit só. Cada estado intermediário é válido e conta a história real: na
Fase 1 o `@import` do Google Fonts e o do design system convivem — a fonte era
pedida duas vezes — e é a Fase 2 que fecha isso.

### Duas coisas que não saíram como deveriam

**A ordem entre `65eb152` e `7f94b99` está trocada, e a `Sidebar.tsx` da casca
foi parar no commit errado.** Outra sessão estava commitando nesta mesma árvore
de trabalho ao mesmo tempo. Enquanto meus três arquivos da casca estavam no
índice, um `git commit` dela os varreu para dentro de um commit de migrations.
Ela depois reescreveu os dois commits dela para devolvê-los, mas nesse intervalo
a `Sidebar.tsx` já tinha entrado no commit do rótulo. **O conteúdo está
inteiro** — o que ficou torto é a fronteira entre dois commits. Não reescrevi
nada: a seção 31 proíbe, e a outra sessão segue ativa na mesma árvore.

**Fora do escopo, deixado intocado:** `backend/alembic/versions/*`,
`backend/tests/test_migrations_postgres.py` e `docs/decisoes-e-regras.md` são
trabalho da outra sessão, e o `.docx` de política de privacidade na raiz não é
meu. Nada disso entrou em commit meu.

---

## 2. Tokens — os sete arquivos conferem por hash

Comando do `VERSION.md`, saída colada sem edição:

```
=== Compare-Object por hash (saida vazia = em dia) ===
=== (fim da saida do Compare-Object) ===

=== hashes lado a lado ===
base.css         BDD047CE432E74B3 IGUAL
colors.css       63D960841590A2CB IGUAL
motion.css       C70D51A982AE0B91 IGUAL
shape.css        7BCFBBC585D3EA8C IGUAL
spacing.css      C093B261C6893A89 IGUAL
styles.css       1EF6324844AA0664 IGUAL
typography.css   99D1A02B92B120C7 IGUAL
```

Saída do `Compare-Object` vazia: a cópia local e o pacote são idênticos.

### ⛔ Emenda do token — NÃO FOI POSSÍVEL CUMPRIR

O pedido era recopiar os sete arquivos com a emenda
`.dark { --text-on-primary: var(--color-primary-900) }` e registrar no
`VERSION.md` como "pacote emendado em 02/09/2026".

**A emenda não está no arquivo.** Apurado antes de copiar qualquer coisa:

- `design-system/tokens/colors.css` tem hash `63D9608415…` — o **mesmo** do
  export original, byte a byte. Última escrita: 02/09/2026 10:43:39, antes
  desta sessão.
- `--text-on-primary` aparece **uma vez** no arquivo, na linha 104, dentro do
  `:root`, com valor `var(--color-white)`. O bloco `.dark` (linha 153 em
  diante) **não** o redefine.
- Procurado em todo o `design-system/`, em todo o `frontend/src/` e em
  `chamadoshs-sistema/`: não existe nenhuma declaração de
  `--text-on-primary: var(--color-primary-900)` em lugar nenhum.

Copiar agora só reproduziria o arquivo antigo, e escrever "pacote emendado em
02/09/2026" no `VERSION.md` registraria como feito algo que não está no código.
**Não escrevi.** O `VERSION.md` segue dizendo a verdade: export de 02/09/2026,
sem emenda.

Provável causa: a edição não chegou a ser salva. Salve e me avise — a recópia,
a reconferência por hash e a linha no `VERSION.md` são um comando só.

### A emenda está certa, e é urgente

Medido com a mesma ferramenta (WCAG 2.x: luminância relativa e
`(L1+0,05)/(L2+0,05)`), lendo os valores resolvidos do próprio `colors.css`:

```
alvo                                           fundo     texto     razao      WCAG
----------------------------------------------------------------------------------------
botao primario — CLARO (--action / on-primary) #1a71a8   #ffffff    5.29:1  AA
botao primario — CLARO hover                   #155984   #ffffff    7.52:1  AA
----------------------------------------------------------------------------------------
botao primario — ESCURO, token como esta hoje  #47a6e1   #ffffff    2.69:1  REPROVA
botao primario — ESCURO hover, como esta hoje  #7bc0ea   #ffffff    1.99:1  REPROVA
----------------------------------------------------------------------------------------
emenda proposta pelo operador (.dark --text-on-primary = --color-primary-900):
botao primario — ESCURO, com a emenda          #47a6e1   #0b3047    5.11:1  AA
botao primario — ESCURO hover, com a emenda    #7bc0ea   #0b3047    6.92:1  AA
----------------------------------------------------------------------------------------
alternativas para o texto sobre --action no escuro (#47a6e1):
  texto = --color-primary-900                  #47a6e1   #0b3047    5.11:1  AA
  texto = --color-primary-800                  #47a6e1   #104565    3.79:1  AA-g
  texto = --color-slate-900                    #47a6e1   #0f172a    6.64:1  AA
  texto = --bg-base                            #47a6e1   #0d1b2a    6.47:1  AA
  texto = --color-white                        #47a6e1   #ffffff    2.69:1  REPROVA
```

Hoje o botão primário no escuro está em **2,69:1** — reprova AA por larga
margem, e o hover piora para 1,99:1. A emenda leva a **5,11:1** e o hover a
6,92:1. `--color-primary-900` é a melhor das opções que mantêm a família azul;
`--color-slate-900` daria mais contraste (6,64:1) mas troca o matiz.

O `Button` do design system (`components/core/Button.jsx`) pinta a variante
primária com `background: var(--action)` e `color: var(--text-on-primary)` —
é exatamente esse par que está medido acima.

---

## 3. Contraste da casca (seção 3, Fase 3)

Mesma ferramenta. Cor translúcida é composta sobre o fundo antes de medir — o
`--action-tint` do tema escuro é `rgb(31 137 202 / 0.15)` e medi-lo sem compor
daria número errado.

| Alvo | Tema | Fundo | Texto | Razão | Exigido | |
|---|---|---|---|---:|---:|---|
| Botão primário (texto) | claro | `#1a71a8` | `#ffffff` | 5.29:1 | 4.5:1 | ✅ |
| Botão primário (texto) | escuro | `#47a6e1` | `#ffffff` | 2.69:1 | 4.5:1 | ❌ |
| Botão primário — hover | claro | `#155984` | `#ffffff` | 7.52:1 | 4.5:1 | ✅ |
| Botão primário — hover | escuro | `#7bc0ea` | `#ffffff` | 1.99:1 | 4.5:1 | ❌ |
| Rótulo de grupo da sidebar | claro | `#ffffff` | `#64748b` | 4.76:1 | 4.5:1 | ✅ |
| Rótulo de grupo da sidebar | escuro | `#132238` | `#94a3b8` | 6.23:1 | 4.5:1 | ✅ |
| Item ativo da sidebar | claro | `#f1f9fe` | `#1a71a8` | 4.97:1 | 4.5:1 | ✅ |
| Item ativo da sidebar | escuro | `#15314e` | `#47a6e1` | 4.94:1 | 4.5:1 | ✅ |
| Título da página na topbar | claro | `#ffffff` | `#0f172a` | 17.85:1 | 4.5:1 | ✅ |
| Título da página na topbar | escuro | `#132238` | `#f1f5f9` | 14.59:1 | 4.5:1 | ✅ |
| Texto de corpo sobre a página | claro | `#f8fafc` | `#1e293b` | 13.98:1 | 4.5:1 | ✅ |
| Texto de corpo sobre a página | escuro | `#0d1b2a` | `#e2e8f0` | 14.11:1 | 4.5:1 | ✅ |
| Versão no rodapé da sidebar | claro | `#ffffff` | `#64748b` | 4.76:1 | 4.5:1 | ✅ |
| Versão no rodapé da sidebar | escuro | `#132238` | `#94a3b8` | 6.23:1 | 4.5:1 | ✅ |
| Borda do card (não-texto) | claro | `#ffffff` | `#e2e8f0` | 1.23:1 | 3.0:1 | ⚠️ |
| Borda do card (não-texto) | escuro | `#132238` | `#1e3a5f` | 1.39:1 | 3.0:1 | ⚠️ |

As duas linhas de borda estão marcadas com ⚠️, não com ❌, e a diferença é
proposital: o critério 1.4.11 de 3:1 vale para componente de interface que
**transmite informação** — borda de campo que sinaliza foco ou erro, por
exemplo. A borda do card é separador decorativo, e o card já se distingue do
fundo pela superfície. Registrei o número em vez de omitir a linha, porque
omitir seria escolher a régua depois de ver o resultado. Quando as Fases 8 e 9
chegarem em `Input` e `Table`, as bordas **informativas** entram nesta tabela
com ❌ de verdade se reprovarem.

As duas linhas ❌ do botão primário são a emenda pendente da seção 2.

### Rótulo de grupo da sidebar — por que `--text-muted`

O relatório da Fase 0 tinha apontado `--text-faint`. Estava errado, e a medição
mostra por quê:

| Opção para o rótulo de grupo | Tema | Fundo (`--surface`) | Texto | Razão | |
|---|---|---|---|---:|---|
| antes — `text-slate-400 dark:text-slate-600` | claro | `#ffffff` | `#94a3b8` | 2.56:1 | ❌ |
| antes — `text-slate-400 dark:text-slate-600` | escuro | `#132238` | `#475569` | 2.11:1 | ❌ |
| `--text-faint` (recusado) | claro | `#ffffff` | `#94a3b8` | 2.56:1 | ❌ |
| `--text-faint` (recusado) | escuro | `#132238` | `#64748b` | 3.36:1 | ❌ |
| `--text-muted` (adotado) | claro | `#ffffff` | `#64748b` | 4.76:1 | ✅ |
| `--text-muted` (adotado) | escuro | `#132238` | `#94a3b8` | 6.23:1 | ✅ |

`--text-faint` fica reservado para **placeholder, ícone decorativo e texto não
informativo** — onde reprovar em AA é aceitável porque nada se perde ao não ler.
Rótulo que nomeia um grupo de navegação não é isso.

Hoje `--text-faint` não é usado em lugar nenhum do `src/` (fora de
`design-system/`). A regra é prospectiva.

---

## 4. Contagens antes e depois

| Medida | Antes (`b863b96`) | Depois | Como foi obtido |
|---|---:|---:|---|
| Hexadecimais cravados — produção | **228** | **217** | `grep -rnoE "#[0-9a-fA-F]{3,8}\b" src` menos `src/test/` e `src/design-system/` |
| Ocorrências de `dark:` | **563** | **467** | `grep -rho "dark:"` em `src` |
| Tokens no `src/design-system/` | 0 | **179** | 6 arquivos, cópia byte a byte |

Os 11 hexadecimais que saíram: os **10 do `index.css`** (as triplas RGB de
superfície e borda, agora vindas de `tokens/colors.css`) e **1 do
`LoginPage.tsx`** (`text-[#0ea5e9]`, a rampa antiga).

Os 217 que restam, por arquivo — nenhum é desvio a corrigir agora:

```
103  src/pages/reports/ReportsPage.tsx      cores e tooltipStyle de gráfico  → Fase 16
 34  src/pages/dashboard/AdminDashboard.tsx idem                             → Fase 12
 22  src/pages/calendar/CalendarPage.tsx    cores de categoria (dado)        → preservar
 18  src/pages/tickets/TicketListPage.tsx   gráfico                          → Fase 14
 16  src/pages/settings/SettingsPage.tsx    paleta de etiqueta (dado)        → preservar
 12  src/pages/dashboard/TechnicianDashboard.tsx gráfico                     → Fase 12
  6  src/pages/kb/KB{List,Form}Page.tsx                                      → Fase 16
  2  src/lib/colors.ts                      função de contraste (lógica)     → preservar
  4  src/pages/auth/*                       #0D1623 e #080F1A do painel      → exceção 8.1
```

A maior massa (≈150) é `tooltipStyle` e eixo do Recharts, que a seção 17 manda
resolver lendo as CSS vars — trabalho das Fases 12 a 16, não desta.

O `#080F1A` do painel de branding do login e do registro **segue pendente de
decisão**: o `readme.md` do pacote só documenta o `#0D1623`.

---

## 5. Testes — executados, saída colada

```
npm run lint       → ✔ 1 problem (0 errors, 1 warning)
                     ThemeContext.tsx:60 react-refresh/only-export-components
                     (o mesmo warning da linha de base — não subiu)

npm run typecheck  → ✔ tsc -b, sem saída, exit 0

npm test           → ✔ Test Files 40 passed (40)
                       Tests 352 passed (352)
                       Duration 23.61s

npm run build      → ✔ built in 13.48s
                     dist/assets/index-B4rrVQcO.js  318.01 kB │ gzip: 100.63 kB
```

Idêntico à linha de base da Fase 0: 40 arquivos, 352 testes, 1 warning. Nenhum
teste precisou ser atualizado — nenhum deles afirma sobre classe CSS.

---

## 6. Screenshots

`docs/design-system-migration/fase-0/screenshots/`, no nome da seção 28:

| Arquivo | Estado | Tema | Resolução |
|---|---|---|---|
| `helphs-sidebar-expandida-claro-1366.png` | sidebar 256px | claro | 1366×768 |
| `helphs-sidebar-expandida-escuro-1366.png` | sidebar 256px | escuro | 1366×768 |
| `helphs-sidebar-recolhida-claro-1366.png` | sidebar 72px | claro | 1366×768 |
| `helphs-sidebar-recolhida-escuro-1366.png` | sidebar 72px | escuro | 1366×768 |
| `helphs-gaveta-mobile-claro-390.png` | drawer aberto | claro | 390×844 |
| `helphs-gaveta-mobile-escuro-390.png` | drawer aberto | escuro | 390×844 |

Conferido olhando as imagens, não só a existência dos arquivos: sidebar de
256px com os três grupos rotulados, topbar de 64px com o `<h1>` "Chamados" e o
badge de 3 não lidas, bloco de usuário com o nome falso, rodapé com
`HelpHS v1.12.0`, e a gaveta escurecendo o fundo com o `--overlay` a 60%.

### Como foram tirados, e por que dá para confiar

Três garantias, conforme combinado:

**1. Rota só em desenvolvimento.** `/galeria-ds` é registrada no `App.tsx`
dentro de `import.meta.env.DEV`, com o `lazy()` **dentro** da condição — se
ficasse fora, o Rollup emitiria o chunk mesmo sem rota que o usasse. Provado
depois do `npm run build`:

```
=== chunk de galeria no dist? ===
  nenhum arquivo Galeria* em dist/assets
=== string 'galeria-ds' ou 'GaleriaCasca' em qualquer asset? ===
  nenhuma ocorrencia em dist/
=== usuario falso vazou? ===
  nenhuma ocorrencia do dado falso em dist/
```

**2. Dado falso.** A galeria monta `Sidebar` e `Topbar` — os componentes reais,
não cópias — sobre um `AuthContext.Provider` local com um usuário inventado
(`Ana Ferreira`, `@exemplo.invalid`). Sem `AuthProvider`, sem token, sem
`/auth/me`.

**3. Nenhuma requisição a produção.** `scripts/capturar-casca.mjs` intercepta
`**/*` com **lista de permissão**: `localhost:5173`, `data:` e `blob:` passam;
chamada de API é respondida ali com dado falso; qualquer outra coisa é abortada
**e registrada como fuga**. Havendo fuga, o script sai com código 1 e recusa os
screenshots como evidência. Saída da execução:

```
Capturando a casca de http://localhost:5173 — toda a rede está interceptada.
  ✔ helphs-sidebar-expandida-claro-1366.png
  ✔ helphs-sidebar-expandida-escuro-1366.png
  ✔ helphs-sidebar-recolhida-claro-1366.png
  ✔ helphs-sidebar-recolhida-escuro-1366.png
  ✔ helphs-gaveta-mobile-claro-390.png
  ✔ helphs-gaveta-mobile-escuro-390.png

Requisições barradas de propósito (1):
  · https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap

6 screenshot(s) em ...\docs\design-system-migration\fase-0\screenshots

✔ Nenhuma requisição escapou. Nada saiu para a rede.
```

O script também verifica, antes de cada captura, que `<html>` está na classe de
tema pedida — sem isso, uma corrida entre o `localStorage` e o
`prefers-color-scheme` poderia gravar o tema errado com o nome certo.

**Limitação a registrar:** a fonte do Google é barrada como qualquer outra rede
externa, então os screenshots usam a pilha de fallback declarada no próprio
token. Isso muda a **forma das letras** — não cor, medida, espaçamento nem
contraste, que é o que estes screenshots existem para comparar.

**Sai na Fase 20:** a rota, `src/dev/GaleriaCasca.tsx`, o bloco `DEV` do
`App.tsx` e o `export` do `AuthContext` (que só existe para isto).

---

## 7. Funcionalidades preservadas (seção 29)

| Item | Como foi conferido |
|---|---|
| Rotas e papéis | `App.tsx` não teve rota alterada nem `RoleGuard` tocado; só o acréscimo condicional de `/galeria-ds` |
| Sessão e login | `AuthProvider` intacto; o `export` do contexto não muda comportamento |
| Alternância de tema | `ThemeContext` e o script anti-flash do `index.html` intactos; screenshots provam os dois temas |
| Sidebar recolher/expandir | screenshots dos dois estados |
| Gaveta mobile | screenshot com a gaveta aberta e o backdrop |
| Contador de não lidas | `Topbar` segue chamando `getNotifications` e engolindo o erro; badge com 3 no screenshot |
| Changelog no rodapé | botão e versão presentes no screenshot |
| Suíte de testes | 352 testes verdes, nenhum atualizado |

---

## 8. Divergências restantes

| Item | Situação |
|---|---|
| `--text-on-primary` no escuro | ⛔ **bloqueia**: emenda não está no pacote. Botão primário em 2,69:1 |
| `#080F1A` do painel de login/registro | pendente de decisão; o pacote só documenta `#0D1623` |
| 217 hexadecimais | ~150 são gráfico (Fases 12–16); o resto é dado ou exceção |
| 467 `dark:` | os que ainda não têm token: cor de sinal por estado e `text-slate-*` |
| Bloco de inversão do `index.css` | fica até a Fase 20 (D5) — é o que segura o tema claro |
| `background-*` / `border-*` | alias até a Fase 20 (D2) |
| `logo-pulse` 3s vs `hs-logo-pulse` 5s | mantido em 3s e anotado, como a seção 4.2 manda |
| Título único na topbar | `pageTitle` existe e está vazio nas 27 páginas; cada tela solta o próprio `<h1>` ao migrar |

## 9. Risco de regressão

**Baixo**, com uma ressalva. Build, testes e lint iguais à linha de base; a
casca foi conferida visualmente nos dois temas e nos três estados. A ressalva é
o `color-mix` (D1): exige Chrome 111+, Safari 16.2+ ou Firefox 113+. Abaixo
disso as cores de token não resolvem. Não foi medido qual fatia da base
instalada isso representa — é decisão de produto, não de implementação.

## 10. Para liberar a Fase 7

1. Salvar a emenda em `design-system/tokens/colors.css` e avisar. **Sem isso o
   botão primário do escuro entra na Fase 7 reprovando AA** — e é justamente o
   `Button` que abre a fase.
2. Decidir o `#080F1A` do painel de login e registro.
