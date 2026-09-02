# Design System da Health & Safety — cópia local

> **Não edite `styles.css` nem `tokens/*.css` aqui.** Eles são cópia byte a
> byte do pacote oficial. Para mudar um valor: altere no design system,
> reexporte e recopie estes sete arquivos. Editar aqui quebra a rastreabilidade
> com o pacote e com o `_ds_manifest.json`.

| | |
|---|---|
| Pacote | `Health__amp__Safety_Design_System` |
| Namespace | `HealthAmpSafetyDesignSystem_ef9f35` |
| Data do export | 02/09/2026 |
| Origem | `C:\Users\ti_rickelme\Documents\GitHub\design-system` |
| Tokens | 180 custom properties em 6 arquivos |
| Copiado em | 02/09/2026 — Fase 1 da adoção |
| Pacote emendado em | **02/09/2026 — E1** (`.dark` ganha `--text-on-primary`) e **E2** (botões semânticos ganham degrau próprio; `--on-tint-neutral` e `--on-tint-warning` passam a AA). Registro em `design-system/EMENDAS.md`; decisões em `COMPARTILHADO/DECISOES.md` (D10 e E2). Recopiados os sete arquivos a cada emenda. |

## Hashes (SHA256)

Conferidos com `Get-FileHash` contra o pacote no momento da cópia. Os sete
arquivos são **idênticos ao original** — sem cabeçalho de origem, sem
reformatação, sem uma vírgula de diferença.

> ⚠️ **Neste commit, seis dos sete.** O `typography.css` do pacote mudou no
> mesmo dia (auto-hospedagem da fonte, `D1-a`), por outra sessão e por outro
> motivo. Não entra junto da E2: vem no commit seguinte, com os doze `.woff2`
> que ele passa a exigir. Até lá o `Compare-Object` acusa **uma** divergência,
> nesse arquivo, e ela é conhecida — o hash acima é o da cópia local de hoje,
> não o do pacote. Sem os arquivos de fonte, adotá-lo sozinho derruba a
> tipografia em produção **em silêncio**: o `dist` sai sem nenhum `.woff2`,
> o `url(../fonts/…)` chega literal ao bundle e o `font-display: swap` esconde
> o 404. Medido, não suposto. Foi decisão explícita
(D3 em `COMPARTILHADO/DECISOES.md`): a seção 5.2 do prompt mestre pede um
comentário de origem no topo de cada arquivo, mas a seção 33 e o operador pedem
conferência por hash — e as duas coisas não cabem juntas. O aviso mora aqui.

```
base.css         BDD047CE432E74B33FA7F752DA08CF025419E83EA18485BD947C889C0AC1C221
colors.css       696ABC6D1C468B17D4510B106517AEF37704663E06E008C38FC109FEEC2A5618
motion.css       C70D51A982AE0B91BD53ECE150D8D16E0E70BEF9CA59586541A9A7177228478E
shape.css        7BCFBBC585D3EA8C7F689A27EEB3AE13DE0C2A9DCC3C6CC0C8F41D440D193F7D
spacing.css      C093B261C6893A893A418CDF64798555326D4586A8ADB37CC7ECA457FABAE420
styles.css       1EF6324844AA066488F0D8A015B39E3CA0756C629512FCE4E1BD95CA8B93B9B2
typography.css   99D1A02B92B120C78000C0BC016C616680EFFB3E13B512E914F3F4F578CA916A
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
