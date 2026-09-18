import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Catraca da ponte do desvio D5.
 *
 * ── Por que ela existe ────────────────────────────────────────────────
 *
 * O `index.css` tem seis linhas que espelham a rampa `slate` no tema claro, e
 * elas trazem o valor **cravado** em canais `rgb(R G B)`:
 *
 *   html:not(.dark) .text-slate-100 { color: rgb(15 23 42); }
 *
 * É uma **segunda fonte de verdade** para a paleta, e nenhuma recópia de token
 * a toca. Se o pacote mudar um degrau de `slate`, estas seis linhas continuam
 * dizendo o valor antigo e a tela pinta o valor antigo — sem erro, sem aviso,
 * sem diferença de hash.
 *
 * O modo de falhar veio da sessão do ChamadosHS, que tem uma ponte equivalente
 * (por outro motivo: converter para canais é o que o Tailwind exige para o
 * modificador de alfa). A recópia dela ficou **dois valores atrás por uma
 * tarde**: os seis arquivos batiam com o pacote e a tela pintava o de antes.
 *
 * ── De onde sai o valor esperado ──────────────────────────────────────
 *
 * **Do seletor, e não do comentário.** O espelho é uma reflexão em torno do
 * degrau 500: `text-slate-N` recebe a cor de `slate-(1000 − N)`. Isso é
 * estrutura, não anotação, e por isso é o que esta conferência usa.
 *
 * O comentário ao lado, que nomeia `slate-900`, é **ignorado de propósito**.
 * Se a conferência confiasse nele, bastaria alguém errar os dois lados juntos
 * para a checagem passar, e uma ferramenta cujo trabalho é detectar divergência
 * não pode aceitar a própria anotação como prova.
 *
 * ── O que ela NÃO cobre ───────────────────────────────────────────────
 *
 * As duas linhas da barra de rolagem — canais 148/163/184 a 50% e 100/116/139
 * a 80% — também são valor cravado, mas não pertencem à
 * reflexão: não há regra estrutural que diga qual degrau deveriam ser. Ficam
 * declaradas aqui como dívida conhecida, e não conferidas — conferi-las pelo
 * comentário seria exatamente o que o parágrafo acima recusa.
 */

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const CSS = path.join(RAIZ, "src", "index.css");
const TOKENS = path.join(RAIZ, "src", "design-system", "tokens", "colors.css");

/** `#rrggbb` para `r g b`. */
function canais(hex) {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)).join(" ");
}

/** Os degraus de `slate` declarados no pacote. */
export function degrausDoPacote(texto = readFileSync(TOKENS, "utf-8")) {
  const mapa = new Map();
  for (const m of texto.matchAll(/--color-slate-(\d{2,3})\s*:\s*(#[0-9a-fA-F]{6})/g)) {
    mapa.set(Number(m[1]), m[2].toLowerCase());
  }
  return mapa;
}

/** As linhas do espelho, lidas do CSS. */
export function linhasDoEspelho(texto = readFileSync(CSS, "utf-8")) {
  const linhas = [];
  texto.split("\n").forEach((linha, i) => {
    const m = linha.match(
      /html:not\(\.dark\)\s+\.text-slate-(\d{2,3})\s*\{\s*color:\s*rgb\(([\d\s]+)\)/,
    );
    if (m) {
      linhas.push({
        numero: i + 1,
        origem: Number(m[1]),
        canais: m[2].trim().replace(/\s+/g, " "),
      });
    }
  });
  return linhas;
}

/**
 * Confere o espelho contra o pacote.
 *
 * Os dois textos são injetáveis para que os **controles negativos** rodem em
 * memória, dentro da suíte, em vez de sujarem o disco: uma conferência que só
 * sabe dizer "está tudo bem" é indistinguível de uma que não olha nada, e a
 * única prova de que esta olha é vê-la acusar.
 */
export function conferirPonte({ textoCss, textoTokens } = {}) {
  const pacote = degrausDoPacote(textoTokens ?? readFileSync(TOKENS, "utf-8"));
  const espelho = linhasDoEspelho(textoCss ?? readFileSync(CSS, "utf-8"));
  const problemas = [];

  if (espelho.length === 0) {
    problemas.push(
      "nenhuma linha do espelho D5 encontrada em src/index.css — o bloco saiu, " +
        "ou o formato mudou. Se ele saiu de propósito (Fase 20), apague este script.",
    );
    return { espelho, problemas };
  }

  for (const l of espelho) {
    const esperadoDegrau = 1000 - l.origem;
    const hex = pacote.get(esperadoDegrau);
    if (!hex) {
      problemas.push(
        `linha ${l.numero}: .text-slate-${l.origem} deveria refletir em ` +
          `slate-${esperadoDegrau}, que NÃO existe no colors.css do pacote.`,
      );
      continue;
    }
    const esperado = canais(hex);
    if (l.canais !== esperado) {
      problemas.push(
        `linha ${l.numero}: .text-slate-${l.origem} pinta rgb(${l.canais}) e ` +
          `slate-${esperadoDegrau} vale ${hex} = rgb(${esperado}). ` +
          `A ponte está atrás do pacote.`,
      );
    }
  }

  return { espelho, problemas };
}

const ehPrincipal =
  process.argv[1] &&
  path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));

if (ehPrincipal) {
  const { espelho, problemas } = conferirPonte();
  console.log(`ponte D5: ${espelho.length} linha(s) conferida(s) contra o pacote`);
  for (const p of problemas) console.error(`\n  x ${p}`);
  if (problemas.length === 0) console.log("  ok - a ponte reflete o pacote.");
  process.exit(problemas.length ? 1 : 0);
}
