import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * A tabela de hashes do `VERSION.md` deixa de ser documento e vira régua.
 *
 * Os sete arquivos de `src/design-system/` são **cópia byte a byte** do pacote,
 * e o `VERSION.md` guarda o SHA256 de cada um. Era a única prova de que a cópia
 * não derivou — e ela **não era conferida por nada**.
 *
 * ── O defeito que comprou este arquivo ────────────────────────────────
 *
 * Em 09/09/2026 a linha do `colors.css` estava desatualizada por **quatro
 * emendas** — E16-b, E18, E19 e E23. O espelho fora recopiado nas quatro; o que
 * ninguém atualizou foi a tabela. Ela existe para detectar deriva, e tinha
 * derivado.
 *
 * O risco tem duas pontas, e a segunda é a que assusta:
 *
 * 1. quem reconferisse veria um **falso alarme** no `colors.css`;
 * 2. quem "consertasse" o espelho para bater com o hash registrado
 *    **reverteria quatro emendas** — sem erro, sem aviso, e com a tabela
 *    dizendo que agora está certo.
 *
 * ── Por que reprova nas DUAS direções ─────────────────────────────────
 *
 * Um caso que só verificasse "o arquivo bate com o hash" deixaria passar o
 * defeito real, que foi o inverso: **o hash parado enquanto o arquivo andava**.
 * Aqui, qualquer das duas pontas reprova, e a mensagem diz qual é.
 *
 * E há a terceira deriva, silenciosa: um arquivo novo em `design-system/` que
 * ninguém registre. Ele não bateria com nada porque não estaria na tabela — e
 * um `for` sobre a tabela nunca o veria. Por isso o caso conta os dois lados.
 */

const RAIZ = path.join(process.cwd(), "src/design-system");
const VERSION = path.join(RAIZ, "VERSION.md");

/** As linhas `nome.css   HASH` do bloco de conferência. */
function registrados(): Map<string, string> {
  const texto = readFileSync(VERSION, "utf-8");
  const mapa = new Map<string, string>();
  for (const m of texto.matchAll(/^([\w.-]+\.css)\s+([0-9A-F]{64})$/gm)) {
    mapa.set(m[1], m[2]);
  }
  return mapa;
}

/** Os `.css` que existem de fato, com o caminho relativo a `design-system/`. */
function emDisco(): Map<string, string> {
  const achados = new Map<string, string>();
  const varrer = (dir: string) => {
    for (const nome of readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, nome.name);
      if (nome.isDirectory()) varrer(p);
      else if (nome.name.endsWith(".css")) achados.set(nome.name, p);
    }
  };
  varrer(RAIZ);
  return achados;
}

const sha256 = (arquivo: string) =>
  createHash("sha256").update(readFileSync(arquivo)).digest("hex").toUpperCase();

describe("design-system — a tabela de hashes do VERSION.md", () => {
  it("registra exatamente os arquivos que existem — nem mais, nem menos", () => {
    // A terceira deriva: arquivo novo que ninguém registrou, ou linha que
    // sobreviveu a um arquivo removido. Um `for` sobre a tabela não vê a
    // primeira; um `for` sobre o disco não vê a segunda.
    const tabela = [...registrados().keys()].sort();
    const disco = [...emDisco().keys()].sort();
    expect(tabela).toEqual(disco);
  });

  it("cada um dos sete bate com o hash registrado", () => {
    // Reprova nos DOIS sentidos, e a mensagem diz qual é: arquivo editado sem
    // atualizar a tabela, ou tabela parada enquanto o arquivo andou. O segundo
    // foi o que aconteceu de verdade, por quatro emendas seguidas.
    const tabela = registrados();
    const disco = emDisco();
    const divergentes: string[] = [];

    for (const [nome, esperado] of tabela) {
      const arquivo = disco.get(nome);
      if (!arquivo) continue; // o caso acima já cobre a ausência
      const real = sha256(arquivo);
      if (real !== esperado) {
        divergentes.push(
          `${nome}\n    VERSION.md: ${esperado}\n    em disco:   ${real}`,
        );
      }
    }

    expect(
      divergentes,
      divergentes.length
        ? "A cópia e a tabela discordam. Se o arquivo mudou de propósito " +
            "(uma emenda), atualize a linha do VERSION.md. Se NÃO mudou de " +
            "propósito, alguém editou uma cópia à mão — e o conserto é " +
            "recopiar do pacote, nunca trocar o hash.\n\n" +
            divergentes.join("\n")
        : undefined,
    ).toEqual([]);
  });

  it("são sete, e o número está escrito porque ele mudar é notícia", () => {
    // Um oitavo arquivo em `design-system/` significa que o pacote cresceu e
    // alguém copiou mais coisa. Pode ser certo — mas não em silêncio.
    expect(registrados().size).toBe(7);
  });
});
