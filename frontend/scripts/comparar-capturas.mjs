/**
 * Compara duas execuções da captura, por TOLERÂNCIA DECLARADA.
 *
 * `node scripts/comparar-capturas.mjs gravar`    guarda o estado atual
 * `node scripts/comparar-capturas.mjs conferir`  compara com o guardado
 *
 * ── Por que não é byte a byte ────────────────────────────────────────────
 *
 * Porque byte a byte é forte demais e diz pouco. Duas execuções da mesma tela
 * diferem por antialias: uma linha diagonal cai em subpixels ligeiramente
 * diferentes conforme o leiaute assenta, e centenas de pixels mudam de 3 a 6
 * unidades de cor. Isso não é a tela mudando — é o mesmo desenho, rasterizado
 * duas vezes.
 *
 * O critério do operador, e ele tem TRÊS partes porque duas não bastam:
 *
 *   1. nenhum pixel difere mais que **8 unidades** em canal nenhum;
 *   2. a área afetada fica em **~1% ou menos**;
 *   3. e a diferença tem de estar **ESPALHADA**.
 *
 * A terceira é a que fecha o buraco das outras duas. Um elemento pequeno que
 * aparece — um ponto de série, um selo, um cursor — pode caber em muito menos
 * de 1% da tela e, se a cor dele for parecida com o fundo, variar menos de 8
 * unidades. Passaria nas duas primeiras e seria **a tela mudando**.
 *
 * ── Como se mede "espalhado" ─────────────────────────────────────────────
 *
 * Pela DENSIDADE dentro da caixa que contém as diferenças: quantos dos pixels
 * daquela caixa realmente mudaram.
 *
 *   antialias      traço fino ao longo de uma linha → caixa grande, poucos
 *                  pixels dentro dela → densidade baixa
 *   elemento       região cheia → caixa pequena, quase toda alterada →
 *                  densidade alta
 *
 * Medido nos dois casos reais que produziram esta régua:
 *
 *   relatorios       458 px, caixa 978×103   → densidade  0,5%   antialias
 *   painel-tecnico  2948 px, caixa  28×138   → densidade 76,2%   ELEMENTO
 *
 * Duas ordens de grandeza separam os dois. O corte em 20% fica no meio do
 * vazio, e não em cima de nenhum deles.
 *
 * ── O que este script NÃO faz ────────────────────────────────────────────
 *
 * Não diz "idênticas". Ele reporta **pixels e variação máxima** de cada foto, e
 * é isso que vai para o checkpoint: um número que alguém pode conferir, e não
 * um adjetivo. Uma foto dentro da tolerância continua tendo diferença, e
 * esconder isso atrás de "igual" seria a mesma perda de informação que a régua
 * existe para evitar.
 */
import { readFileSync, writeFileSync, readdirSync, existsSync } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { PNG } from "pngjs";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const FASES = ["11", "16"];
const dirDaFase = (f) =>
  path.resolve(RAIZ, `../docs/design-system-migration/fase-${f}/screenshots`);
const GUARDA = path.resolve(RAIZ, "scripts/.capturas-anteriores.json");

/** A tolerância, declarada. Mudar qualquer número aqui muda o que "igual" quer dizer. */
const DELTA_MAXIMO = 8; // por canal
const AREA_MAXIMA = 0.01; // 1% dos pixels
const DENSIDADE_CONCENTRADA = 0.2; // acima disto é elemento, não antialias

function fotos() {
  const achadas = [];
  for (const f of FASES) {
    const d = dirDaFase(f);
    if (!existsSync(d)) continue;
    for (const nome of readdirSync(d)) {
      if (nome.endsWith(".png")) achadas.push([nome, path.join(d, nome)]);
    }
  }
  return achadas;
}

/** Guarda a imagem inteira, em base64, porque comparar exige os dois lados. */
function gravar() {
  const estado = {};
  for (const [nome, caminho] of fotos()) {
    const b = readFileSync(caminho);
    estado[nome] = {
      sha: createHash("sha256").update(b).digest("hex"),
      png: b.toString("base64"),
    };
  }
  writeFileSync(GUARDA, JSON.stringify(estado), "utf-8");
  console.log("gravadas %d foto(s) de referência.", Object.keys(estado).length);
}

function diferenca(bufA, bufB) {
  const A = PNG.sync.read(bufA);
  const B = PNG.sync.read(bufB);
  if (A.width !== B.width || A.height !== B.height) {
    return { dimensao: `${A.width}×${A.height} vs ${B.width}×${B.height}` };
  }
  let n = 0;
  let maiorDelta = 0;
  let minx = Infinity;
  let maxx = -1;
  let miny = Infinity;
  let maxy = -1;
  for (let y = 0; y < A.height; y++) {
    for (let x = 0; x < A.width; x++) {
      const i = (A.width * y + x) << 2;
      const d = Math.max(
        Math.abs(A.data[i] - B.data[i]),
        Math.abs(A.data[i + 1] - B.data[i + 1]),
        Math.abs(A.data[i + 2] - B.data[i + 2]),
      );
      if (!d) continue;
      n++;
      if (d > maiorDelta) maiorDelta = d;
      if (x < minx) minx = x;
      if (x > maxx) maxx = x;
      if (y < miny) miny = y;
      if (y > maxy) maxy = y;
    }
  }
  const total = A.width * A.height;
  const caixa = n ? (maxx - minx + 1) * (maxy - miny + 1) : 0;
  return {
    pixels: n,
    area: n / total,
    maiorDelta,
    densidade: caixa ? n / caixa : 0,
    caixa: n ? `${maxx - minx + 1}×${maxy - miny + 1}` : "—",
  };
}

/** O veredito, e cada reprovação diz QUAL das três partes falhou. */
function julgar(d) {
  if (d.dimensao) return { ok: false, porque: `dimensão mudou (${d.dimensao})` };
  if (d.pixels === 0) return { ok: true, porque: "idêntica" };
  if (d.maiorDelta > DELTA_MAXIMO)
    return { ok: false, porque: `variação ${d.maiorDelta} > ${DELTA_MAXIMO}` };
  if (d.area > AREA_MAXIMA)
    return { ok: false, porque: `área ${(d.area * 100).toFixed(2)}% > 1%` };
  if (d.densidade > DENSIDADE_CONCENTRADA)
    return {
      ok: false,
      porque:
        `concentrada: ${(d.densidade * 100).toFixed(0)}% da caixa ${d.caixa} ` +
        `mudou — isso é elemento, não antialias`,
    };
  return { ok: true, porque: "dentro da tolerância" };
}

function conferir() {
  if (!existsSync(GUARDA)) {
    console.log("não há referência gravada. Rode `gravar` primeiro.");
    process.exitCode = 1;
    return;
  }
  const antes = JSON.parse(readFileSync(GUARDA, "utf-8"));
  const agora = new Map(fotos());

  // ── O controle negativo da própria régua ────────────────────────────
  //
  // Contar os nomes dos DOIS lados, e reportar novas e sumidas à parte.
  // "Nenhuma diferença" e "nenhum arquivo" são indistinguíveis num contador
  // só — e um comparador com o caminho errado leria zero de cada lado e diria
  // que está tudo igual.
  const nomes = [...new Set([...Object.keys(antes), ...agora.keys()])].sort();
  const novas = nomes.filter((n) => !antes[n]);
  const sumidas = nomes.filter((n) => !agora.has(n));
  if (!nomes.length) {
    console.log("NENHUMA foto dos dois lados — a comparação não mediu nada.");
    process.exitCode = 1;
    return;
  }

  let dentro = 0;
  const fora = [];
  const comDiferenca = [];
  for (const nome of nomes) {
    if (!antes[nome] || !agora.has(nome)) continue;
    const d = diferenca(
      Buffer.from(antes[nome].png, "base64"),
      readFileSync(agora.get(nome)),
    );
    const v = julgar(d);
    if (v.ok) {
      dentro++;
      if (d.pixels) comDiferenca.push([nome, d]);
    } else {
      fora.push([nome, d, v.porque]);
    }
  }

  const comparadas = nomes.length - novas.length - sumidas.length;
  console.log(
    "%d/%d dentro da tolerância (≤%d de variação, ≤1%% de área, espalhada).",
    dentro,
    comparadas,
    DELTA_MAXIMO,
  );
  if (comDiferenca.length) {
    console.log("\nDentro da tolerância, mas COM diferença medida:");
    for (const [nome, d] of comDiferenca) {
      console.log(
        "  %s  %d px (%s%%), variação máx %d, densidade %s%%",
        nome.padEnd(38),
        d.pixels,
        (d.area * 100).toFixed(4),
        d.maiorDelta,
        (d.densidade * 100).toFixed(1),
      );
    }
  }
  for (const [nome, d, porque] of fora) {
    console.log("\n✖ %s\n    %s", nome, porque);
    if (d.pixels !== undefined) {
      console.log(
        "    %d px (%s%%), variação máx %d, caixa %s, densidade %s%%",
        d.pixels,
        (d.area * 100).toFixed(4),
        d.maiorDelta,
        d.caixa,
        (d.densidade * 100).toFixed(1),
      );
    }
  }
  for (const n of novas) console.log("  nova:  %s", n);
  for (const n of sumidas) console.log("  sumiu: %s", n);
  if (fora.length || novas.length || sumidas.length) process.exitCode = 1;
}

if (process.argv[2] === "gravar") gravar();
else conferir();
