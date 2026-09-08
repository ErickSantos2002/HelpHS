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

### Os ícones: o pacote tem 62, e é quase certo que o seu já está lá

A **E21** subiu o conjunto de 46 para 62, feita a partir do inventário das 33
telas: dos 151 `<svg>` soltos, **105 usos já desenhavam traçado que existe**, e
dos 27 desenhos que faltavam, **10 eram o mesmo significado com outro traço** —
um "certo" sem círculo, outro triângulo de aviso, outra lupa. Foram unificados.

Então, ao encontrar um `<svg>`:

1. **Case pelo traçado `d`, não pela aparência.** Compare com `ICON_PATHS` em
   `components/ui/Icon.tsx`. Caractere a caractere.
2. **Se não bater, procure pelo SIGNIFICADO.** Um "certo" é `check`, mesmo com
   outro desenho. Um aviso é `warning`. Uma lupa é `search`. Quase sempre é isso.
3. **Só se o significado não existir** é ícone novo — e aí ele **não é seu**:
   pare, deixe o `<svg>` onde está e relate. Entrar no pacote é emenda, e emenda
   não se faz de dentro de uma tela.

⚠️ **Antes de trocar, confira o `viewBox` e o `fill` do `<svg>`.** O `Icon` é
24×24 com `fill="none"` e `stroke="currentColor"`. Um ícone `viewBox="0 0 20 20"`
ou com `fill="currentColor"` é de **outra família**: trocá-lo pelo `Icon`
renderiza na escala errada e sem preenchimento, e **nada no `tsc` ou em teste de
componente acusa** — `ICON_PATHS` é mapa de texto, e todo texto cabe. Foi assim
que a estrela sólida do `AdminDashboard` foi barrada. Achou um? Deixe, e relate.

### Paleta crua É escopo desta fase

Não é só cor de gráfico. As classes `slate-*`, `sky-*`, `amber-*` e companhia
saem todas, na mesma passada — os dois primeiros agentes divergiram nisto
porque o prompt de um pedia a tela inteira e o do outro não, e a divergência era
minha. A tela fecha com **zero** paleta crua fora de comentário.

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

### Mutação por CLASSE não vale, e isso já enganou o orquestrador

O jsdom **não aplica CSS nenhum**. Trocar `sr-only` por `hidden` não esconde
coisa alguma de um `getByText` — o elemento continua na árvore, o teste continua
passando, e o mutante sobrevive por um motivo que não tem nada a ver com o que o
caso mede. Um teste de acessibilidade que afirmasse `toHaveClass("sr-only")`
teria o mesmo defeito na direção oposta: passaria com a classe presente e o
elemento invisível de verdade.

Mute **o elemento**, não a classe dele: apague o `<span>`, inverta a condição,
troque o texto. E teste pelo que o usuário alcança — `getByRole`, `getByText`,
nome acessível —, nunca pela classe.

### As três mutações que NÃO são mutações

O orquestrador escreveu as três hoje e as três "sobreviveram" por motivo
nenhum. Uma mutação que não muda comportamento **acusa o teste de vazio quando o
vazio é ela**:

| o que parece mutação | por que é no-op |
|---|---|
| trocar uma classe (`sr-only` → `hidden`) | o jsdom não aplica CSS; o elemento continua na árvore |
| renomear um símbolo em todo o arquivo | o consumidor é renomeado junto, e o código faz o mesmo |
| `X && original(...)` | `&&` devolve o **segundo** operando; o mutante é o original. É `\|\|` |

Antes de concluir "sobreviveu", leia a mutação e pergunte: **isto muda o que a
tela faz?** Se não muda, o defeito é seu, não do caso.

### Como desfazer a mutação, e por que não é com git

Cópia do arquivo antes, restauração em `finally`. Nunca `git checkout`, nem
mesmo restrito ao caminho da sua tela: a árvore tem outros agentes e duas
sessões vizinhas, e um comando de escrita que "só toca o meu arquivo" já é um
comando de escrita que você não precisava. Se o processo morrer no meio, o
`finally` devolve o arquivo; o `git checkout` devolve outra coisa.

```js
const orig = readFileSync(A, "utf-8");
try {
  writeFileSync(A, orig.replace(de, para), "utf-8");
  // rode o teste; se ele PASSA, o mutante sobreviveu
} finally {
  writeFileSync(A, orig, "utf-8");
}
```

O `finally` não é estilo: a primeira versão do roteiro de mutação deste projeto
quebrou ao decodificar a saída do vitest e **deixou a mutação no disco**.

⚠️ **O roteiro precisa de um controle SEM mutação, e aqui está o porquê.** Um
agente rodou doze mutações com `execFileSync("npx.cmd", …)` e as doze
"sobreviveram" — em zero segundo. `npx.cmd` é um script de shell: sem `shell:
true`, o `execFileSync` não o executa no Windows, **o vitest nunca rodou**, e o
roteiro leu "não falhou" como "o mutante passou". Ele pegou sozinho e refez.

Duas defesas, e use as duas:

1. **Rode a suíte sem mutação nenhuma antes da primeira**, e exija que ela
   **passe**. Se o controle não passa, o seu medidor está quebrado e nenhum
   resultado depois dele vale.
2. **Chame o vitest sem passar por `.cmd`**: `process.execPath` com
   `node_modules/vitest/vitest.mjs`, ou `execSync` (que usa shell).

Um roteiro de mutação é uma régua, e régua não medida mente com confiança.

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
