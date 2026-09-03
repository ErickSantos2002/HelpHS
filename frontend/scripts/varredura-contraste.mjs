/**
 * Varredura de contraste que parte do **JSX**, não do `colors.css`.
 *
 * A distinção é o achado que criou este arquivo: medir o token prova que a
 * paleta é sólida; **não** prova que as telas a usam. As telas escrevem classe
 * por cima do token, e `text-white` não é token nenhum. Foi assim que passaram
 * o link de pular (2,69:1 no escuro) e a página ativa da `Pagination`, com a
 * conferência do Checkpoint 1 medindo `--action` contra as superfícies e dando
 * a casca por conforme.
 *
 * Uso:
 *   node scripts/varredura-contraste.mjs            varre src/ e lista
 *   node scripts/varredura-contraste.mjs --provar   roda os casos de prova
 *   node scripts/varredura-contraste.mjs --json     saída para outra ferramenta
 *   node scripts/varredura-contraste.mjs --catraca  compara com a linha de base
 *
 * O modo normal **relata** e sai 0 sempre. Quem reprova é o `--catraca`, que
 * falha em par novo **e** em par que sumiu sem a lista ser atualizada — é o que
 * a separa de um carimbo de linha de base. Desenho da sessão do ChamadosHS.
 *
 * ── AS ONZE ARMADILHAS ──────────────────────────────────────────────────
 *
 * Cada uma custou um falso resultado antes de ser vista. As três primeiras
 * vieram da sessão do ChamadosHS; as cinco seguintes apareceram no uso; as três
 * últimas saíram de um painel adversarial posto a caçá-las de propósito, que
 * levantou nove candidatas e derrubou cinco. Todas têm caso de prova no fim
 * deste arquivo — e os casos de controle existem porque, sem eles, "não conta"
 * e "não vê" são indistinguíveis.
 *
 * A lição de método, custe o que custar repetir: **as onze foram achadas por
 * acidente ou por alguém procurando de propósito, nenhuma por leitura do
 * código**. Três delas transformavam reprovação em aprovação.
 *
 * 1. FILTRAR DIRETÓRIO. Olhar só `pages/` perde o que mora em primitivo e em
 *    casca — e é justamente o que aparece em toda tela. Os três piores achados
 *    estavam em `components/layout/` e `components/ui/`.
 *
 * 2. CASAR LINHA A LINHA. `className` quebra em várias linhas o tempo todo, e
 *    `bg-danger` numa linha com `text-white` na seguinte não casa num `grep`.
 *
 * 3. IGNORAR O PREFIXO DE ESTADO. Casar `hover:bg-*` com o texto de repouso
 *    mede um par que não existe — e pode **transformar reprovação em
 *    aprovação**, que é o pior modo de falhar.
 *
 * 4. PAREAR RAMOS DE TERNÁRIO. Classes de ramos mutuamente exclusivos não
 *    co-ocorrem. Juntá-las inventou seis reprovações de **1,00:1** aqui. E um
 *    template com `${...}` é **um literal só**: os ramos lá dentro precisam ser
 *    recortados antes do pareamento.
 *
 * 5. MAPA DE TOKENS INCOMPLETO. A lógica da armadilha 3 estava certa e o mapa
 *    a sabotava: sem conhecer `text-conteudo-*`, um hover que troca o texto por
 *    um degrau dessa escada era lido como "hover sem texto próprio", caía no
 *    texto base e inventava o par. Mapa incompleto vira armadilha 3 pela porta
 *    dos fundos.
 *
 * 6. VARIANTE `dark:` SOBRESCREVENDO A CLASSE BASE. `hover:text-slate-900`
 *    junto de `dark:hover:text-slate-100`: no escuro vale a segunda. Medir a
 *    primeira no escuro devolveu **1,32:1** — texto escuro sobre superfície
 *    escura, que não existe em pixel nenhum.
 *
 * 7. LER SÓ `className=`. As variantes de componente moram em **tabela**
 *    (`const variantClasses = { ghost: "..." }`), e tabela não é atributo.
 *    Quem lê só o atributo fica cego exatamente onde um design system guarda
 *    as cores. Foi o que escondeu o `ghost` do `Button` — 4,34:1 no claro —
 *    num primitivo já dado por revisado. Por isso aqui a unidade é **o literal
 *    de string**, venha de onde vier.
 *
 * 8. LER COMENTÁRIO COMO CÓDIGO. Ao ganhar a armadilha 7, esta varredura passou
 *    a casar crase por expressão regular — e o aviso em JSDoc que este projeto
 *    escreveu no `Button.tsx`, «`bg-danger text-white` dá 3,76:1», virou um
 *    achado. **O texto que documenta o defeito foi lido como uma instância
 *    dele.** Daí o scanner de estado abaixo, que sabe quando está em comentário.
 *
 * 9. PERGUNTAR "ESTE ESTADO TEM TEXTO PRÓPRIO?" EM VEZ DE RESOLVER PRECEDÊNCIA.
 *    `dark:hover:bg-X` com `text-Y` sem prefixo nunca era medido no escuro: a
 *    busca procurava `dark:text-`, não achava e desistia. Escondia uma
 *    reprovação **viva em produção** — o botão de sair do `Topbar`, `text-danger`
 *    sobre `dark:hover:bg-background-elevated`, **3,60:1**. O modelo certo não é
 *    "o estado declara o seu?", é "qual classe vence nesta combinação": no
 *    escuro em hover, `dark:hover:` > `hover:` > `dark:` > sem prefixo.
 *
 * 10. IGNORAR O PREFIXO IMPORTANT. `dark:hover:!text-slate-100` não casava
 *    `dark:hover:text-` e deixava de contar como sobrescrita, ressuscitando o
 *    fantasma de 1,32:1 da armadilha 6. Confirmado compilando o caso com o
 *    Tailwind instalado: ele emite a regra com `!important`, e no escuro o texto
 *    é mesmo o do `dark:`.
 *
 * 11. RECORTAR INTERPOLAÇÃO COM REGEX CEGA A PROFUNDIDADE. A extensão do
 *    template era achada contando chaves, mas o recorte usava `/\$\{[^}]*\}/`,
 *    que para na primeira `}`. Uma chave interna — `cn({ ativo }, "…")`, a forma
 *    mais comum de classe condicional — cortava no lugar errado e costurava
 *    ramos exclusivos num literal só. **Nas duas direções**: inventava par
 *    (1,47:1 que não existe) e apagava par real.
 *
 * E a armadilha 5 voltou pela porta do conserto da 9: `vigente()` devolvia a
 * primeira classe que casava o prefixo, e `text-sm` vinha antes de `text-danger`
 * — o tamanho da fonte sombreava a cor e apagava o par. Custou 15 pares e o
 * próprio achado do `Topbar` antes de aparecer. Mapa incompleto e busca sem
 * filtro dão no mesmo lugar.
 *
 * ── O QUE ELA AINDA NÃO VÊ ──────────────────────────────────────────────
 *
 * Declarado para ninguém ler ausência como aprovação:
 *
 * - **Fundo declarado no ancestral.** O par é procurado no mesmo elemento. Um
 *   selo dentro de um `<button>` que pinta `elevated` no hover não aparece
 *   aqui; foi achado lendo o JSX. Fechar isso exige resolver a árvore.
 * - **Subcontagem por literal.** `cn("bg-danger px-2", cond && "text-white")`
 *   passa batido, porque o par se divide em dois literais. É deliberado:
 *   subcontar é melhor que inventar — um número a menos é uma tarefa
 *   esquecida, um número inventado é uma tarefa que não existe.
 * - **Opacidade.** `bg-danger/20` não é medido; a composição da tinta está nos
 *   testes de componente, pelo `helpers/contraste.ts`.
 * - **Só texto sobre fundo.** Ela mede o par `bg-*` + `text-*`, e por isso não
 *   enxerga nada do que a **WCAG 1.4.11** cobre: componente de interface e
 *   limite gráfico, cujo piso é **3:1** e não 4,5:1. O trilho de um interruptor
 *   contra o painel, a bolinha contra o trilho, a borda de um campo contra o
 *   fundo — nada disso passa por aqui. Achado na Fase 8: o alternador de tema
 *   tinha o trilho desligado em **1,48:1** e a bolinha em **1,10:1**, e a
 *   varredura marcava zero. `bg-slate-*` e `bg-white` sequer estão no mapa de
 *   fundos, porque o mapa foi feito para o caso de texto.
 */
import { readFileSync, readdirSync, statSync, mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import path from "node:path";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const AA = 4.5;

// ── tokens, lidos do arquivo e nunca digitados ────────────────────────
//
// Regra comprada com três erros nesta fase: valor de cor sai do `colors.css`,
// não da memória. Publicar `#0f1e2e` como `--surface` do escuro (é `#132238`)
// e `#0b3049` como `--color-primary-900` (é `#0b3047`) gerou seis números
// errados em commit e em relatório — inclusive um que contradizia o número que
// o próprio `EMENDAS.md` já registrava.

function semComentarios(t) {
  return t.replace(/\/\*[\s\S]*?\*\//g, "");
}

function bloco(css, seletor) {
  const i = css.indexOf(seletor + " {");
  if (i === -1) throw new Error(`bloco "${seletor}" não encontrado`);
  const corpo = css.slice(i + seletor.length + 2, css.indexOf("}", i));
  const mapa = new Map();
  for (const linha of corpo.split(";")) {
    const m = linha.match(/^\s*(--[\w-]+)\s*:\s*(.+?)\s*$/s);
    if (m) mapa.set(m[1], m[2]);
  }
  return mapa;
}

const CSS = semComentarios(
  readFileSync(path.join(RAIZ, "src/design-system/tokens/colors.css"), "utf-8"),
);
const T_RAIZ = bloco(CSS, ":root");
const T_ESCURO = bloco(CSS, ".dark");

/**
 * Degraus de cinza reescritos pelo bloco de inversão do `index.css` (desvio
 * D5), que vale **só no tema claro**. São 876 usos de `text-slate-*` vivos por
 * causa dele; sem tratar isso, medir cinza no claro devolve a cor do escuro.
 * Lido do arquivo, não transcrito.
 */
const D5 = (() => {
  const idx = readFileSync(path.join(RAIZ, "src/index.css"), "utf-8");
  const mapa = new Map();
  const re = /html:not\(\.dark\)\s+\.text-slate-(\d{2,3})\s*\{\s*color:\s*rgb\(([^)]+)\)/g;
  let m;
  while ((m = re.exec(idx)) !== null) {
    const [r, g, b] = m[2].trim().split(/\s+/).map(Number);
    mapa.set(m[1], [r, g, b]);
  }
  return mapa;
})();

function resolve(token, tema, prof = 0) {
  if (prof > 10) return null;
  const mapa = tema === "escuro" ? T_ESCURO : T_RAIZ;
  const v = (mapa.get(token) ?? T_RAIZ.get(token))?.trim();
  if (!v) return null;
  const encadeado = v.match(/^var\((--[\w-]+)\)$/);
  if (encadeado) return resolve(encadeado[1], tema, prof + 1);
  const hex = v.match(/^#([0-9a-f]{6})$/i);
  if (hex) return [0, 2, 4].map((i) => parseInt(hex[1].slice(i, i + 2), 16));
  const rgb = v.match(/^rgb\(\s*(\d+)\s+(\d+)\s+(\d+)\s*(?:\/\s*[\d.]+\s*)?\)$/);
  if (rgb) return [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])];
  return null;
}

// ── WCAG 2.x, composição em ponto flutuante ───────────────────────────
//
// Sem arredondar para inteiro: o navegador não arredonda em passo nenhum, e
// `Math.round` em passo intermediário move o resultado na segunda casa.

const canal = (c) => {
  const v = c / 255;
  return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
};
const luminancia = ([r, g, b]) =>
  0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b);

function contraste(a, b) {
  const [maior, menor] = [luminancia(a), luminancia(b)].sort((x, y) => y - x);
  return (maior + 0.05) / (menor + 0.05);
}

// ── classe do Tailwind → cor ──────────────────────────────────────────

const RAMPAS = "primary|danger|success|warning|info";

/** Escada de texto do pacote. Armadilha 5: sem ela o mapa sabota a lógica. */
const ESCADA = {
  conteudo: "--text-body",
  "conteudo-heading": "--text-heading",
  "conteudo-muted": "--text-muted",
  "conteudo-faint": "--text-faint",
};

const SUPERFICIES = {
  surface: "--surface",
  "surface-base": "--bg-base",
  "surface-elevated": "--surface-elevated",
  // Alias do D2, ainda vivos até a Fase 20.
  background: "--bg-base",
  "background-surface": "--surface",
  "background-elevated": "--surface-elevated",
};

/** Devolve um descritor de cor, ou null quando a classe não é cor. */
function alvoDe(classe, tipo) {
  const c = classe.slice(tipo.length + 1);
  if (tipo === "text" && c === "white") return { fixo: [255, 255, 255] };
  if (c === "action") return { token: "--action" };
  if (new RegExp(`^(${RAMPAS})$`).test(c)) return { token: `--color-${c}-500` };
  const degrau = c.match(new RegExp(`^(${RAMPAS})-(\\d{2,3})$`));
  if (degrau) return { token: `--color-${degrau[1]}-${degrau[2]}` };
  const par = c.match(/^on-(primary|danger|success)$/);
  if (par) return { token: `--text-on-${par[1]}` };
  const tinta = c.match(/^on-(tint-neutral|tint-warning)$/);
  if (tinta) return { token: `--on-${tinta[1]}` };
  if (tipo === "text" && ESCADA[c]) return { token: ESCADA[c] };
  if (tipo === "bg" && SUPERFICIES[c]) return { token: SUPERFICIES[c] };
  const cinza = c.match(/^slate-(\d{2,3})$/);
  if (cinza && tipo === "text") return { slate: cinza[1] };
  return null;
}

function corDe(alvo, tema) {
  if (!alvo) return null;
  if (alvo.fixo) return alvo.fixo;
  if (alvo.slate) {
    if (tema === "claro" && D5.has(alvo.slate)) return D5.get(alvo.slate);
    return resolve(`--color-slate-${alvo.slate}`, tema);
  }
  return resolve(alvo.token, tema);
}

// ── leitura do JSX ────────────────────────────────────────────────────

/**
 * Todo literal de string do arquivo — não só os de `className=` (armadilha 7).
 * Cada literal é uma unidade de pareamento (armadilha 4): classes que estão em
 * literais diferentes podem ser ramos de um ternário e não co-ocorrer.
 *
 * ARMADILHA 8: **comentário não é código.** A primeira versão disto casava
 * crase por expressão regular, e o aviso em JSDoc que este mesmo projeto
 * escreveu no `Button.tsx` — «`bg-danger text-white` dá 3,76:1» — virou um
 * achado. O texto que documenta o defeito passou a ser lido como uma instância
 * dele. Por isso aqui há um scanner de estado, e não uma expressão regular:
 * ele sabe quando está dentro de comentário, de string e de template.
 */
function literaisDe(texto) {
  const saida = [];
  let i = 0;
  const n = texto.length;

  while (i < n) {
    const c = texto[i];
    const prox = texto[i + 1];

    if (c === "/" && prox === "/") {
      while (i < n && texto[i] !== "\n") i++;
      continue;
    }
    if (c === "/" && prox === "*") {
      i += 2;
      while (i < n && !(texto[i] === "*" && texto[i + 1] === "/")) i++;
      i += 2;
      continue;
    }
    if (c === '"' || c === "'") {
      let j = i + 1;
      let conteudo = "";
      while (j < n && texto[j] !== c) {
        if (texto[j] === "\\") { j += 2; continue; }
        if (texto[j] === "\n") break; // string sem fechar: não é literal válido
        conteudo += texto[j];
        j++;
      }
      if (texto[j] === c) saida.push({ texto: conteudo, indice: i });
      i = j + 1;
      continue;
    }
    if (c === "`") {
      // ARMADILHA 11: a versão anterior achava a EXTENSÃO do template contando
      // profundidade, mas recortava as interpolações com `/\$\{[^}]*\}/`, que
      // para na primeira `}`. Uma chave interna — `cn({ ativo }, "…")`, a forma
      // mais comum de classe condicional — fazia a tesoura cortar no lugar
      // errado e costurar ramos exclusivos num literal só. Nas duas direções:
      // inventava par (1,47:1 que não existe em pixel nenhum) e apagava par real.
      // Extensão e recorte precisam contar a mesma profundidade.
      let j = i + 1;
      let estatico = "";
      const interpolacoes = [];
      while (j < n) {
        if (texto[j] === "\\") { j += 2; continue; }
        if (texto[j] === "`") break;
        if (texto[j] === "$" && texto[j + 1] === "{") {
          let prof = 1;
          let k = j + 2;
          let dentro = "";
          while (k < n && prof > 0) {
            if (texto[k] === "\\") { dentro += texto[k] + (texto[k + 1] ?? ""); k += 2; continue; }
            if (texto[k] === "{") prof++;
            else if (texto[k] === "}") { prof--; if (prof === 0) break; }
            dentro += texto[k];
            k++;
          }
          interpolacoes.push(dentro);
          estatico += " ";
          j = k + 1;
          continue;
        }
        estatico += texto[j];
        j++;
      }
      // O template sem as interpolações é um literal; o conteúdo de cada
      // interpolação é código, e volta pelo scanner (armadilha 4).
      saida.push({ texto: estatico, indice: i });
      for (const dentro of interpolacoes) {
        for (const l of literaisDe(dentro)) saida.push({ ...l, indice: i });
      }
      i = j + 1;
      continue;
    }
    i++;
  }
  return saida;
}

function arquivosTsx(dir) {
  const saida = [];
  for (const nome of readdirSync(dir)) {
    const p = path.join(dir, nome);
    const pu = p.split(path.sep).join("/");
    if (statSync(p).isDirectory()) {
      if (/\/(test|dev|node_modules)$/.test(pu)) continue;
      saida.push(...arquivosTsx(p));
    } else if (nome.endsWith(".tsx")) {
      saida.push(p);
    }
  }
  return saida;
}

const ESTADOS = ["", "hover:", "focus:", "focus-visible:", "active:", "disabled:", "group-hover:"];
const TEMAS = ["claro", "escuro"];

/**
 * Tira o `!` do prefixo important do Tailwind v3 (`dark:hover:!text-slate-100`).
 *
 * ARMADILHA 10: sem isto, `dark:hover:!text-*` nao casa `dark:hover:text-` e a
 * classe deixa de ser vista como sobrescrita — o fantasma de 1,32:1 que a
 * armadilha 6 tinha matado ressuscita. Confirmado compilando o caso com o
 * proprio Tailwind instalado: ele emite a regra com `!important`, e no escuro o
 * texto E o do `dark:`.
 */
function semImportant(classe) {
  const i = classe.lastIndexOf(":");
  const prefixo = i === -1 ? "" : classe.slice(0, i + 1);
  const util = classe.slice(i + 1);
  return prefixo + (util.startsWith("!") ? util.slice(1) : util);
}

/**
 * A classe que vale numa combinacao (tema, estado), por precedencia.
 *
 * ARMADILHA 9: a versao anterior varria por prefixo e perguntava "este estado
 * tem texto proprio?". Isso deixava um vao: `dark:hover:bg-X` com `text-Y` sem
 * prefixo nunca era medido no escuro, porque a busca pelo texto do estado
 * escuro procurava `dark:text-` e desistia. Escondia uma reprovacao viva — o
 * botao de sair do `Topbar`, `text-danger` sobre `dark:hover:bg-*`, 3,60:1.
 *
 * O modelo certo nao e "o estado declara o seu?", e sim: numa combinacao, vale
 * a classe mais especifica entre as que se aplicam. No escuro em hover:
 *   dark:hover:  >  hover:  >  dark:  >  (sem prefixo)
 * No claro em hover:
 *   hover:  >  (sem prefixo)
 */
function vigente(classes, tipo, tema, estado) {
  const candidatos = tema === "escuro"
    ? [`dark:${estado}`, estado, "dark:", ""]
    : [estado, ""];
  for (const pref of candidatos) {
    // Só vale a classe que o mapa reconhece como COR. `text-sm` casa
    // `text-` e vinha antes de `text-danger` na lista — a armadilha 5
    // reaparecendo pela porta do modelo novo: o tamanho da fonte sombreava a
    // cor e apagava o par inteiro. Mediu-se: de 72 pares para 57, com o
    // achado vivo do `Topbar` entre os que sumiram.
    const achada = classes.find(
      (c) => c.startsWith(`${pref}${tipo}-`) && alvoDe(c.slice(pref.length), tipo),
    );
    if (achada) return { classe: achada, semPrefixo: achada.slice(pref.length) };
  }
  return null;
}

function paresDoLiteral(classes) {
  const limpas = classes.map(semImportant);
  const pares = [];
  const vistos = new Set();

  for (const tema of TEMAS) {
    for (const estado of ESTADOS) {
      const f = vigente(limpas, "bg", tema, estado);
      const t = vigente(limpas, "text", tema, estado);
      if (!f || !t) continue;

      const af = alvoDe(f.semPrefixo, "bg");
      const at = alvoDe(t.semPrefixo, "text");
      if (!af || af.fixo || !at) continue;

      const cf = corDe(af, tema);
      const ct = corDe(at, tema);
      if (!cf || !ct) continue;

      const razao = contraste(cf, ct);
      if (razao >= AA) continue;

      // A mesma dupla resolvida pode vir de varios estados (o fundo de repouso
      // segue valendo no hover que nao o troca). Uma linha por dupla e tema.
      const chave = `${f.classe}|${t.classe}|${tema}`;
      if (vistos.has(chave)) continue;
      vistos.add(chave);
      pares.push({
        estado: estado || "repouso",
        fundo: f.classe,
        texto: t.classe,
        tema,
        razao,
      });
    }
  }
  return pares;
}

export function varrer(raiz) {
  const achados = [];
  for (const arquivo of arquivosTsx(raiz)) {
    const texto = readFileSync(arquivo, "utf-8");
    const rel = path.relative(raiz, arquivo).split(path.sep).join("/");
    for (const literal of literaisDe(texto)) {
      const classes = literal.texto.split(/\s+/).filter(Boolean);
      if (classes.length === 0) continue;
      // A linha serve ao leitor, não à identidade do achado: uma edição acima
      // move todas, e catraca que grita por linha em branco é catraca que
      // alguém desliga na primeira semana. Por isso a chave de deduplicação
      // (abaixo) não a inclui, mas o relatório a mostra.
      const linha = texto.slice(0, literal.indice).split("\n").length;
      for (const p of paresDoLiteral(classes)) {
        achados.push({ arquivo: rel, linha, ...p });
      }
    }
  }
  const vistos = new Set();
  return achados
    .filter((a) => {
      const ch = `${a.arquivo}|${a.linha}|${a.fundo}|${a.texto}|${a.tema}`;
      if (vistos.has(ch)) return false;
      vistos.add(ch);
      return true;
    })
    .sort((a, b) => a.razao - b.razao || a.arquivo.localeCompare(b.arquivo));
}

// ── casos de prova ────────────────────────────────────────────────────
//
// Os cinco primeiros são o conjunto que a sessão do ChamadosHS propôs, com o
// **caso de controle** incluído: sem ele, "não conta" e "não vê" são
// indistinguíveis, e uma exclusão larga demais passaria por acerto. Os dois
// últimos guardam as armadilhas achadas aqui, que voltariam em silêncio.

const PROVAS = [
  {
    nome: "1. limpo — par que aprova não vira achado",
    jsx: `<b className="bg-surface-elevated text-conteudo-heading">x</b>`,
    espera: 0,
  },
  {
    nome: "2. par real novo — é achado",
    jsx: `<b className="bg-danger text-white">x</b>`,
    espera: 2, // claro e escuro: danger-500 é degrau absoluto
  },
  {
    nome: "3. ramos de ternário dentro de template — não co-ocorrem",
    jsx: "<b className={`p-1 ${a ? \"bg-danger\" : \"text-danger\"}`}>x</b>",
    espera: 0,
  },
  {
    nome: "4. hover que troca também o texto — vale o texto do hover",
    jsx: `<b className="text-white hover:bg-surface-elevated hover:text-conteudo-heading">x</b>`,
    espera: 0,
  },
  {
    // Só o claro: no escuro `--surface-elevated` é `#1a2f4a`, e branco por cima
    // dá 13,5:1. A assimetria é o resultado certo, não expectativa ajustada —
    // é o mesmo par de classes do caso 4, e a única diferença é o hover ter
    // deixado de declarar o próprio texto.
    nome: "5. CONTROLE — sem o texto de hover, o par volta a contar (só no claro)",
    jsx: `<b className="text-white hover:bg-surface-elevated">x</b>`,
    espera: 1,
  },
  {
    nome: "6. dark: sobrescrevendo a base — só o claro é medido",
    jsx: `<b className="hover:bg-surface-elevated hover:text-slate-900 dark:hover:text-slate-100">x</b>`,
    espera: 0,
  },
  {
    nome: "7. tabela de variantes — literal fora de className também é lido",
    jsx: `const V = { ghost: "bg-danger text-white" };`,
    espera: 2,
  },
  {
    // O aviso que este projeto escreveu no `Button.tsx` sobre o defeito virou,
    // por uma versão, um achado do próprio defeito. Comentário não é código.
    nome: "8. prosa em comentário — crase em JSDoc não é template literal",
    jsx: `<b className="p-1">x</b>);
/** Aviso: \`bg-danger text-white\` dá 3,76:1 e \`bg-primary text-white\` dá 3,83:1. */
// e também em linha: "bg-danger text-white"
const _ = (`,
    espera: 0,
  },
  {
    // O caso vivo: o botão de sair do `Topbar`. O texto não tem prefixo, o
    // fundo só existe em `dark:hover:`. A versão anterior procurava
    // `dark:text-` para o estado escuro, não achava e desistia — 3,60:1
    // invisível em código publicado.
    nome: "9. texto sem prefixo sob fundo dark: — o escuro tem de ser medido",
    jsx: `<b className="text-danger dark:hover:bg-surface-elevated">x</b>`,
    espera: 1,
  },
  {
    // Mesmo caso do 6, com um `!` a mais. Sem tratar o important, a classe
    // deixa de ser vista como sobrescrita e o fantasma de 1,32:1 volta.
    nome: "10. prefixo important — dark:hover:!text-* ainda é sobrescrita",
    jsx: `<b className="hover:bg-surface-elevated hover:text-slate-900 dark:hover:!text-slate-100">x</b>`,
    espera: 0,
  },
  {
    // Chave interna na interpolação. A tesoura antiga cortava na `}` do objeto
    // e costurava os dois ramos num literal só, inventando o par.
    nome: "11. chave interna na interpolação — ramos seguem separados",
    jsx: "<b className={`p-1 ${a ? `${d} bg-danger px-2` : `${d} text-conteudo-faint px-2`}`}>x</b>",
    espera: 0,
  },
  {
    // CONTROLE da 11, na direção oposta: o mesmo formato de interpolação, mas
    // com um par que reprova de verdade dentro de um ramo só. Sem ele, "a
    // varredura corretamente separou os ramos" e "a varredura perdeu o literal"
    // seriam indistinguíveis — foi exatamente o falso negativo que a tesoura
    // antiga produzia com `cn({ ... }, "…")`.
    // Achada consertando a 9: `text-sm` casa `text-` e vinha antes de
    // `text-danger` na lista de classes, sombreando a cor e apagando o par
    // inteiro. Custou 15 pares e o achado vivo do `Topbar` antes de aparecer.
    nome: "13. tamanho de fonte não sombreia a cor na busca por precedência",
    jsx: `<b className="text-sm text-danger dark:hover:bg-surface-elevated">x</b>`,
    espera: 1,
  },
  {
    nome: "12. CONTROLE — par real dentro de interpolação com chave é achado",
    jsx: `<b className={\`p-1 \${cn({ a }, "bg-danger text-white")}\`}>x</b>`,
    espera: 2,
  },
];

function provar() {
  const base = mkdtempSync(path.join(tmpdir(), "varredura-"));
  let falhas = 0;
  try {
    for (const p of PROVAS) {
      const dir = mkdtempSync(path.join(base, "caso-"));
      writeFileSync(path.join(dir, "Caso.tsx"), `export const C = () => (${p.jsx});\n`, "utf-8");
      const achados = varrer(dir);
      const ok = achados.length === p.espera;
      if (!ok) falhas++;
      console.log(`  ${ok ? "✔" : "✖"} ${p.nome}`);
      if (!ok) {
        console.log(`      esperava ${p.espera} achado(s), veio ${achados.length}`);
        for (const a of achados) {
          console.log(`      · ${a.razao.toFixed(2)}:1 ${a.tema} ${a.fundo} + ${a.texto}`);
        }
      }
    }
  } finally {
    rmSync(base, { recursive: true, force: true });
  }
  return falhas;
}


// ──────────────────────────────────────────────────────────────────────
// Catraca
// ──────────────────────────────────────────────────────────────────────

/**
 * Os pares que reprovam hoje, e um mecanismo para eles so diminuirem.
 *
 * Desenho copiado da sessao do **ChamadosHS**, que o escreveu primeiro e
 * respondeu com ele a uma objecao minha — eu tinha recusado o guarda por achar
 * que lista de excecao vira permissao. Adaptados os caminhos e a chave; a
 * mecanica, as mensagens e os casos de controle sao dela. Registrado em
 * `COMPARTILHADO/DECISOES.md` como decisao que vale para os dois repositorios.
 *
 * -- Por que uma catraca, e nao uma lista de excecao --------------------
 *
 * Lista de excecao sobrevive ao problema que a criou: nasce como "os que ja
 * existiam" e em seis meses e uma permissao. Esta nao consegue, porque reprova
 * nos **dois** sentidos:
 *
 *   apareceu par novo   -> falha, e nomeia o arquivo
 *   sumiu par da lista  -> **tambem** falha, e entrega a lista nova pronta
 *
 * O segundo e o que impede o apodrecimento: consertar uma tela **obriga** a
 * mexer aqui, e o numero so anda para baixo. Quando chegar a zero, o bloco sai
 * e sobra a varredura, que ai reprova qualquer par.
 *
 * -- A chave e arquivo + fundo + estado, sem numero de linha ------------
 *
 * Linha muda a cada edicao acima dela, e catraca que grita por causa de uma
 * linha em branco e catraca que alguem desliga na primeira semana.
 *
 * A chave **nao** inclui a classe de texto, e isso e deliberado: medido no
 * corpus, ela colide em 4 das 35 chaves — sempre `text-slate-500` contra
 * `text-slate-600` no mesmo fundo e arquivo. A colisao nao atrapalha, porque o
 * que a catraca compara e a **contagem**: consertar um dos dois faz o numero
 * daquela chave cair de 2 para 1. A classe exata sai no relatorio da varredura,
 * que e onde ela serve.
 *
 * -- E quando alguem precisa subir uma tela com par novo, e tem prazo ---
 *
 * Acrescenta a linha aqui. Uma linha, num arquivo versionado, que aparece no
 * diff e alguem revisa. A catraca nao bloqueia o trabalho — forca a divida a
 * ser **declarada** em vez de entrar calada. O que ela impede e o caso comum:
 * ninguem sabia que estava adicionando um.
 *
 * -- A linha de base ---------------------------------------------------
 *
 * 51 pares em 35 chaves. Eram 52 ate o botao de sair do `Topbar` sair do degrau
 * 500 cru (`f9d67aa`); a catraca nasce um abaixo do numero que o relatorio da
 * Fase 7 publica, e e assim que ela deve nascer.
 *
 * Trinta deles sao `text-slate-*` sobre superficie, vivos por causa do desvio
 * D5, e saem tela a tela nas Fases 11-16 — cada pagina migrada zera os seus.
 */
const PARES_CONHECIDOS = new Map([
  ['components/chat/ChatPanel.tsx  bg-background-elevated  repouso', 1],
  ['components/chat/ChatPanel.tsx  bg-primary  repouso', 1],
  ['components/chat/QuickReplyPicker.tsx  bg-background-surface  repouso', 2],
  ['components/layout/Topbar.tsx  bg-danger  repouso', 2],
  ['components/ui/Pagination.tsx  bg-primary  repouso', 1],
  ['components/ui/Select.tsx  bg-background-surface  repouso', 1],
  ['pages/audit/AuditLogsPage.tsx  bg-background-elevated  repouso', 2],
  ['pages/audit/AuditLogsPage.tsx  hover:bg-background-elevated  hover:', 1],
  ['pages/calendar/CalendarPage.tsx  bg-primary  repouso', 2],
  ['pages/dashboard/AdminDashboard.tsx  bg-primary  repouso', 1],
  ['pages/dashboard/ClientDashboard.tsx  bg-primary  repouso', 1],
  ['pages/dashboard/TechnicianDashboard.tsx  bg-background-elevated  repouso', 1],
  ['pages/equipment/EquipmentPage.tsx  bg-background-elevated  repouso', 1],
  ['pages/equipment/EquipmentPage.tsx  bg-background-surface  repouso', 1],
  ['pages/groups/GroupsPage.tsx  hover:bg-background-elevated  hover:', 1],
  ['pages/kb/KBArticlePage.tsx  bg-background-elevated  repouso', 1],
  ['pages/kb/KBArticlePage.tsx  bg-primary  repouso', 1],
  ['pages/kb/KBFormPage.tsx  bg-background-elevated  repouso', 1],
  ['pages/kb/KBFormPage.tsx  bg-primary  repouso', 1],
  ['pages/kb/KBListPage.tsx  bg-background-elevated  repouso', 4],
  ['pages/kb/KBListPage.tsx  bg-primary  repouso', 1],
  ['pages/notifications/NotificationsPage.tsx  bg-primary  repouso', 1],
  ['pages/onboarding/OnboardingPage.tsx  bg-background-elevated  repouso', 1],
  ['pages/onboarding/OnboardingPage.tsx  bg-primary  repouso', 1],
  ['pages/products/ProductsPage.tsx  bg-background-elevated  repouso', 3],
  ['pages/profile/ProfilePage.tsx  bg-danger  repouso', 1],
  ['pages/profile/ProfilePage.tsx  bg-primary  repouso', 3],
  ['pages/reports/ReportsPage.tsx  bg-primary  repouso', 1],
  ['pages/settings/QuickRepliesPage.tsx  dark:bg-background-elevated  repouso', 1],
  ['pages/tickets/TicketDetailPage.tsx  bg-background-elevated  repouso', 3],
  ['pages/tickets/TicketFormPage.tsx  bg-background-elevated  repouso', 1],
  ['pages/tickets/TicketFormPage.tsx  bg-primary  repouso', 2],
  ['pages/tickets/TicketListPage.tsx  bg-background-elevated  repouso', 2],
  ['pages/tickets/TicketListPage.tsx  bg-primary  repouso', 1],
  ['pages/users/UsersPage.tsx  bg-background-elevated  repouso', 2],
]);

/** A chave da catraca a partir de um achado da varredura. */
function chaveDe(a) {
  return `${a.arquivo}  ${a.fundo}  ${a.estado}`;
}

/**
 * Conta lugares por chave. Um "lugar" e `arquivo:linha` com um par — o mesmo
 * par nos dois temas e **um** lugar, porque e um conserto so.
 */
export function contarPorChave(achados) {
  const lugares = new Map();
  for (const a of achados) {
    const lugar = `${a.arquivo}|${a.linha}|${a.fundo}|${a.texto}`;
    if (!lugares.has(lugar)) lugares.set(lugar, chaveDe(a));
  }
  const contagem = new Map();
  for (const chave of lugares.values()) {
    contagem.set(chave, (contagem.get(chave) ?? 0) + 1);
  }
  return contagem;
}

export function catraca(raiz, base = PARES_CONHECIDOS) {
  const agora = contarPorChave(varrer(raiz));
  const chaves = [...new Set([...agora.keys(), ...base.keys()])].sort();

  const novos = [];
  const consertados = [];
  for (const k of chaves) {
    const a = agora.get(k) ?? 0;
    const b = base.get(k) ?? 0;
    if (a > b) novos.push(`${k}  ->  ${b} na linha de base, ${a} agora`);
    else if (a < b) consertados.push(k);
  }

  const listaNova = chaves
    .map((k) => ({ k, n: agora.get(k) ?? 0 }))
    .filter((x) => x.n > 0)
    .map((x) => `  ['${x.k}', ${x.n}],`);

  return {
    novos,
    consertados,
    listaNova,
    total: [...agora.values()].reduce((s, n) => s + n, 0),
    totalBase: [...base.values()].reduce((s, n) => s + n, 0),
  };
}


/**
 * Os tres controles da catraca, do roteiro da sessao do ChamadosHS.
 *
 * O terceiro e o que a diferencia de um carimbo de linha de base: um guarda
 * comum falha em par novo; este falha tambem quando um par e CONSERTADO e a
 * lista nao desce junto. Sem ele a lista fossiliza e vira permissao.
 */
function provarCatraca() {
  const base = mkdtempSync(path.join(tmpdir(), "catraca-"));
  let falhas = 0;
  const conferir = (nome, ok, detalhe) => {
    if (!ok) falhas++;
    console.log(`  ${ok ? "OK " : "X  "} ${nome}`);
    if (!ok && detalhe) console.log(`      ${detalhe}`);
  };

  try {
    const um = mkdtempSync(path.join(base, "um-"));
    writeFileSync(
      path.join(um, "Caso.tsx"),
      'export const C = () => (<b className="bg-danger text-white">x</b>);',
      "utf-8",
    );
    const chave = "Caso.tsx  bg-danger  repouso";

    const emDia = catraca(um, new Map([[chave, 1]]));
    conferir(
      "1. limpo - nao acusa nada, e o total bate com a linha de base",
      emDia.novos.length === 0 && emDia.consertados.length === 0 && emDia.total === 1,
      JSON.stringify(emDia),
    );

    const comNovo = catraca(um, new Map());
    conferir(
      "2. par novo - acusa e nomeia o arquivo",
      comNovo.novos.length === 1 && comNovo.novos[0].includes("Caso.tsx"),
      JSON.stringify(comNovo.novos),
    );

    const vazio = mkdtempSync(path.join(base, "vazio-"));
    writeFileSync(
      path.join(vazio, "Caso.tsx"),
      'export const C = () => (<b className="bg-surface-elevated text-conteudo-heading">x</b>);',
      "utf-8",
    );
    const desceu = catraca(vazio, new Map([[chave, 1]]));
    conferir(
      "3. CONTROLE - par consertado tambem falha, e entrega a lista nova",
      desceu.consertados.length === 1 && desceu.listaNova.length === 0 && desceu.total === 0,
      JSON.stringify(desceu),
    );
  } finally {
    rmSync(base, { recursive: true, force: true });
  }
  return falhas;
}

// ── execução ──────────────────────────────────────────────────────────
//
// Fica no fim do arquivo de propósito: a linha de base é um `const`, e um
// bloco de execução acima dela cairia na zona morta temporal.

const ehPrincipal = process.argv[1] &&
  path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));

if (ehPrincipal) {
  if (process.argv.includes("--provar")) {
    console.log("Casos de prova da varredura:\n");
    console.log("");
    const falhas = provar() + provarCatraca();
    console.log(
      falhas === 0
        ? `\n✔ os ${PROVAS.length} casos e os 3 controles da catraca passam.`
        : `\n✖ ${falhas} de ${PROVAS.length} caso(s) falharam.`,
    );
    process.exit(falhas === 0 ? 0 : 1);
  }

  if (process.argv.includes("--catraca")) {
    const r = catraca(path.join(RAIZ, "src"));
    const problemas = [];

    if (r.novos.length) {
      problemas.push(
        "PAR NOVO abaixo de 4,5:1 (fundo com texto por cima):\n      " +
          r.novos.join("\n      ") +
          "\n      Use o token do par (--on-tint-*, --text-on-*) ou o degrau de acao," +
          "\n      nunca o degrau 500 da rampa com uma cor cravada por cima.",
      );
    }

    if (r.consertados.length) {
      problemas.push(
        "a catraca precisa descer - par(es) consertado(s), atualize PARES_CONHECIDOS em\n" +
          "      scripts/varredura-contraste.mjs. A lista inteira, ja pronta:\n" +
          (r.listaNova.length
            ? r.listaNova.join("\n")
            : "  (vazia - apague o bloco inteiro e faca a varredura reprovar sempre)"),
      );
    }

    console.log(
      `catraca: ${r.total} par(es) abaixo de 4,5:1, linha de base ${r.totalBase}`,
    );
    for (const problema of problemas) console.error(`\n  x ${problema}`);
    if (problemas.length === 0) console.log("  ok - em dia.");
    process.exit(problemas.length ? 1 : 0);
  }

  const achados = varrer(path.join(RAIZ, "src"));

  if (process.argv.includes("--json")) {
    console.log(JSON.stringify(achados, null, 2));
  } else {
    console.log("Pares abaixo de AA (4,5:1), lidos do JSX:\n");
    for (const a of achados) {
      console.log(`  ${a.razao.toFixed(2).padStart(5)}:1  ${a.tema.padEnd(6)}  ${a.arquivo}:${a.linha}`);
      console.log(`           ${a.estado.padEnd(16)} ${a.fundo}  +  ${a.texto}`);
    }
    const lugares = new Set(achados.map((a) => `${a.arquivo}|${a.linha}|${a.fundo}|${a.texto}`));
    const arquivos = new Set(achados.map((a) => a.arquivo));
    console.log(
      `\n${achados.length} pares (${lugares.size} lugares distintos) em ${arquivos.size} arquivos`,
    );
    console.log("\nIsto relata, não reprova: a saída é sempre 0.");
  }
}
