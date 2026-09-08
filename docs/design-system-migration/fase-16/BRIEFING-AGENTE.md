# Fase 16 — briefing de um agente por tela

Este arquivo é o contrato de quem migra **uma** tela. Ele existe porque a árvore
é compartilhada: três agentes rodam ao mesmo tempo, e mais duas sessões do
Claude trabalham em worktrees vizinhas. Escrita fora do escopo não é
desorganização — é corrida.

---

## 1. O escopo, e ele é estreito

Você pode escrever em **dois** arquivos:

| | |
|---|---|
| a tela | o `.tsx` que lhe foi dado |
| o teste dela | `src/test/pages/<Tela>.test.tsx` (ou o caminho equivalente) |

E em **um terceiro**, só no fim: a ficha da §29, em
`docs/design-system-migration/fase-16/<Tela>.md`.

**Proibido escrever em qualquer outro arquivo.** Em particular:

```
src/lib/**            src/components/**       src/design-system/**
scripts/**            tailwind.config.js      src/index.css
package.json          qualquer coisa em docs/ além da sua ficha
```

Se a tela precisa de algo que só existe num desses — um primitivo novo, um
token, uma entrada no módulo de status — **não crie uma versão local**. Pare
naquele ponto, siga com o resto da tela e **relate o que faltou** na resposta
final. Variante local é exatamente o defeito que esta migração existe para
eliminar; um `ICON_PATHS` local ou um segundo mapa de prioridade custa mais do
que a linha que ele economiza.

**Não rode nenhum comando `git` que escreva.** Sem `add`, `commit`, `checkout`,
`stash`, `restore`. Quem comita é o orquestrador, em série. Ler (`git diff`,
`git status`) é permitido.

---

## 2. As fontes únicas, e nada além delas

| o que | de onde | nunca |
|---|---|---|
| rótulo/variante/ordem de status | `lib/status.ts` | mapa local |
| **cor de série por status** | `SLOT_DE_STATUS` / `slotDeStatus()` — tabela da E18 | `--color-*` semântico |
| prioridade | `lib/prioridade.ts` | mapa local, hexadecimal |
| **cor de série por prioridade** | `graficoDePrioridade()` | `--chart-*` |
| categoria | `lib/categoria.ts` | mapa local |
| **eixo, grade, dica** | `CROMO`, `ESTILO_DICA`, `ENVOLTORIO_DICA` de `lib/grafico.ts` | `theme === "dark" ? … : …` |
| **série categórica** | `slotCategorico(i)` de `lib/grafico.ts` | hexadecimal, paleta crua |
| **série temporal de medida única** | `COR_SERIE_TEMPORAL` | uma cor por tela |
| **escala de satisfação** | `preenchimentoCsat(nota)` | rampa de dez cores |
| ícone | `Icon` de `components/ui` | `<svg>` solto |

### O `useTheme()` some dos gráficos

Escolher o hexadecimal no JavaScript pelo tema é reimplementar o seletor
`.dark`. `var(--surface)` já é branco no claro e `#132238` no escuro. Se depois
da migração o `theme` não for mais usado na tela, **remova o import** — variável
morta que lê contexto continua re-renderizando.

### A legenda de gráfico de status é obrigatória

Regra da E18. Enquanto o status pintava com a cor da §16, quem conhecia o
sistema lia "vermelho = cancelado" sem consultar nada. Com `--chart-*` a cor
deixou de significar: **todo gráfico de status leva legenda com o nome de cada
série.** Sem exceção.

### A nota do CSAT vai sempre no rótulo

Três faixas de cor não satisfazem 1.4.1 sozinhas — só menos passos que dez. O
que resolve é o número estar escrito. Se a barra perder o número, a migração
piorou a tela.

---

## 3. As regras de classe que a catraca cobra

1. **Nenhuma paleta crua do Tailwind**: `slate-*`, `sky-*`, `indigo-*`,
   `amber-*`, `emerald-*`, `violet-*`, `rose-*`. Use os tokens semânticos.
2. **`text-danger` / `text-warning` / `text-success` / `text-info` como cor de
   texto é reprovação**, inclusive com prefixo (`hover:text-danger`) e inclusive
   em `fill-` e `stroke-`. O substituto é `text-on-tint-*`. Motivo medido: 16 das
   24 combinações reprovam o piso de texto e 6 reprovam até o de forma.
3. **`bg-primary` com `text-white` dá 3,83:1.** O par certo do degrau de ação é
   `bg-action` + `text-on-primary` — leia o comentário do `tailwind.config.js`
   antes de escolher pelo nome.
4. **`text-conteudo-faint` sobre `bg-surface-elevated` dá 2,34:1.** Não é par.
5. **Classe nunca por concatenação.** O Tailwind gera utilitário varrendo o
   texto do arquivo: `"bg-tint-" + variante` some da varredura, a regra não
   nasce, o elemento fica sem fundo, e **não há erro nem aviso**. Mapa com as
   classes escritas por extenso, sempre.

---

## 4. O que rodar, e o que NÃO rodar

Rode, do diretório `frontend/`:

```
npx vitest run <o seu arquivo de teste>
npx tsc --noEmit -p tsconfig.app.json
npx eslint <os seus arquivos>
node scripts/varredura-contraste.mjs 2>&1 | grep '<caminho/da/sua/tela>'
```

A varredura precisa terminar **sem nenhuma linha** com o seu arquivo. Ela relata
e sai 0 sempre — o `grep` vazio é a prova, não o código de saída.

**Não rode:**

| comando | por quê |
|---|---|
| `npm run build`, `npx tsc -b` | escrevem `.tsbuildinfo`; três agentes ao mesmo tempo corrompem |
| `npx vitest run` sem arquivo | a suíte inteira, três vezes em paralelo |
| `node scripts/varredura-contraste.mjs --catraca` | a linha de base é arquivo compartilhado; quem a atualiza é o orquestrador |
| `prettier --write` | os arquivos estão em 80 colunas, o `.prettierrc` em 100, o CI não confere formato — `--write` reformata o arquivo inteiro e enterra a sua mudança no diff |
| qualquer `git` que escreva | corrida no índice |

---

## 5. Teste que passa de primeira não vale nada

Regra da casa, sem exceção: **todo caso que passa na primeira execução tem de
ser validado por mutação.** Quebre de propósito o que ele afirma proteger,
confirme que ele reprova, desfaça. Se ele continuar passando, ele não mede o que
você acha que mede — quatro pontos cegos reais já foram achados assim nesta
migração, e nenhum por leitura do código.

Escreva casos sobre **o que a tela promete**, não sobre a implementação:
o rótulo que o usuário lê, o papel acessível do controle, a legenda existir.

---

## 6. A ficha da §29

Ao fim, escreva `docs/design-system-migration/fase-16/<Tela>.md` com:

- **o que a tela tinha** — mapas locais, hexadecimais, SVGs soltos, com número;
- **o que passou a usar** — os módulos e primitivos, com número;
- **a contagem do que resta à mão**: controles à mão, SVGs soltos, cores cruas.
  A regra é **contar, não julgar**: um número maior que zero significa que
  alguém tem de olhar, não que há trabalho pendente. Se sobrou um controle à
  mão, diga qual e por quê;
- **o que você NÃO fez e por quê** — inclusive o que dependia de arquivo fora do
  seu escopo.

---

## 7. O que volta para o operador, e não se decide sozinho

Na resposta final, numa seção própria, liste tudo que for:

- **decisão de desenho** — uma cor, um agrupamento, um nome de faixa, uma ordem
  que ninguém decidiu ainda;
- **mudança funcional** — o que a tela passa a fazer ou deixar de fazer, o que
  ela passa a mostrar ou esconder, qualquer coisa que mude o número que alguém
  lê;
- **defeito de produto** — dado que não fecha, estado sem lugar na interface,
  contagem feita no cliente sobre uma página do servidor. Isso não é defeito de
  sistema de design e **não se conserta aqui**.

Não decida nenhum dos três. Faça o resto da tela por inteiro, e relate.

---

## 8. A resposta final

Curta e factual, nesta ordem:

1. o que mudou, por gráfico/bloco;
2. os números: linhas da varredura antes → depois, hexadecimais antes → depois,
   testes que passaram, mutações que morreram;
3. o que ficou de fora, e por quê;
4. o que volta para o operador (§7).

Sem preâmbulo, sem recapitulação do briefing.
