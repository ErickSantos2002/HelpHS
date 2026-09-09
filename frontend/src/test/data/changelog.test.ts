import { describe, it, expect } from "vitest";
import {
  APP_VERSION,
  CHANGELOG,
  type ChangelogEntry,
  type EntryType,
} from "../../data/changelog";

// O changelog é lido pelo usuário final e a regra da casa é que versão já
// publicada nunca é reescrita. Este arquivo não testa comportamento: ele
// guarda as invariantes de formato e de ordem do dado e, na TABELA_CONGELADA
// mais abaixo, o próprio conteúdo já publicado. Se um teste daqui quebrar,
// quem está errado é o changelog, não o teste.

// Sem zero à esquerda de propósito: "v01.9.0" e "v1.9.0" seriam duas grafias
// da mesma versão, e a segunda escapa tanto da comparação quanto da busca.
const FORMATO_VERSAO = /^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const FORMATO_DATA = /^(\d{2})\/(\d{2})\/(\d{4})$/;

/** Quebra "v1.12.0" em [1, 12, 0]. Devolve null se o formato não bate. */
function partesDaVersao(versao: string): [number, number, number] | null {
  const casou = FORMATO_VERSAO.exec(versao);
  if (!casou) return null;
  return [Number(casou[1]), Number(casou[2]), Number(casou[3])];
}

/**
 * Compara major/minor/patch numericamente. Positivo quando `a` é mais nova.
 * Existe porque comparar versão como string mente: "v1.9.0" > "v1.12.0".
 */
function comparaVersao(a: string, b: string): number {
  const pa = partesDaVersao(a);
  const pb = partesDaVersao(b);
  if (!pa || !pb) {
    throw new Error(`Versão fora do formato vX.Y.Z: ${!pa ? a : b}`);
  }
  for (let i = 0; i < 3; i++) {
    if (pa[i] !== pb[i]) return pa[i] - pb[i];
  }
  return 0;
}

/**
 * Converte "31/08/2026" em Date. Devolve null quando o formato não bate ou
 * quando a data não existe no calendário (31/02, 29/02 em ano comum).
 */
function parseDataBr(data: string): Date | null {
  const casou = FORMATO_DATA.exec(data);
  if (!casou) return null;
  const dia = Number(casou[1]);
  const mes = Number(casou[2]);
  const ano = Number(casou[3]);
  const d = new Date(ano, mes - 1, dia);
  // Se o dia não existe, o Date transborda para o mês seguinte e os
  // componentes deixam de bater com o que foi escrito.
  const real =
    d.getFullYear() === ano && d.getMonth() === mes - 1 && d.getDate() === dia;
  return real ? d : null;
}

/**
 * Resume o conteúdo de uma versão numa string curta. Serializa "type text"
 * de cada item, na ordem, e devolve soma polinomial de charCodeAt em 32 bits
 * (base 36) com o tamanho do serializado colado no fim. O tamanho é o que
 * garante que toda edição que encurte ou alongue o texto seja pega com
 * certeza, e não por sorte do hash.
 *
 * Existe só para congelar o conteúdo publicado sem despejar o changelog
 * inteiro aqui dentro. Não é hash criptográfico e não precisa ser.
 *
 * ATENÇÃO: mudar esta função invalida TODOS os resumos da tabela abaixo e
 * exige regerá-los rodando-a sobre os entries de cada versão.
 */
function resumoDosEntries(entries: readonly ChangelogEntry[]): string {
  const serial = entries.map((e) => `${e.type} ${e.text}`).join("");
  let h = 0;
  for (let i = 0; i < serial.length; i++) {
    h = (h * 31 + serial.charCodeAt(i)) >>> 0;
  }
  return `${h.toString(36)}-${serial.length.toString(36)}`;
}

// Tipado como Record<EntryType, true>: se a união EntryType ganhar ou perder
// um membro, este objeto para de compilar e o teste precisa ser revisto junto.
const TIPOS_VALIDOS: Record<EntryType, true> = {
  novidade: true,
  corrigido: true,
  melhoria: true,
};

/**
 * Todas as versões JÁ PUBLICADAS, congeladas: versão, data, quantidade de
 * itens e o resumo do conteúdo (type + text) de cada uma.
 *
 * CHANGELOG[0] fica FORA desta tabela de propósito: é a versão em preparo, a
 * única que ainda pode ganhar, perder ou reescrever itens até sair.
 *
 * Publicar uma versão nova custa, portanto, duas edições: a versão nova entra
 * no topo do CHANGELOG e a que era o topo entra AQUI, na primeira linha desta
 * tabela. Esse custo é o próprio guarda — a lista abaixo só muda por decisão
 * explícita de quem publica, nunca de raspão.
 */
const TABELA_CONGELADA: ReadonlyArray<{
  version: string;
  date: string;
  itens: number;
  resumo: string;
}> = [
  { version: "v1.11.0", date: "31/08/2026", itens: 2, resumo: "e2ohce-hn" },
  { version: "v1.10.0", date: "27/08/2026", itens: 12, resumo: "1scs927-1lb" },
  { version: "v1.9.0", date: "26/08/2026", itens: 10, resumo: "b67mwd-19s" },
  { version: "v1.8.0", date: "21/08/2026", itens: 6, resumo: "pdacm7-w7" },
  { version: "v1.7.0", date: "19/08/2026", itens: 6, resumo: "c0dzrj-lp" },
  { version: "v1.6.0", date: "10/08/2026", itens: 3, resumo: "11pta1j-8l" },
  { version: "v1.5.0", date: "07/08/2026", itens: 2, resumo: "10mpxto-5f" },
  { version: "v1.4.0", date: "07/08/2026", itens: 9, resumo: "1cshmai-pv" },
  { version: "v1.3.0", date: "06/08/2026", itens: 10, resumo: "161641g-p8" },
  { version: "v1.2.0", date: "05/08/2026", itens: 9, resumo: "7i1a7u-k2" },
  { version: "v1.1.0", date: "04/08/2026", itens: 10, resumo: "1xep2qq-r5" },
  { version: "v1.0.0", date: "20/05/2026", itens: 6, resumo: "n22iik-da" },
  { version: "v0.9.0", date: "01/05/2026", itens: 5, resumo: "1soqgoo-a9" },
  { version: "v0.8.0", date: "15/04/2026", itens: 4, resumo: "1thvynt-7x" },
];

describe("o oráculo deste arquivo", () => {
  // Único teste do arquivo que NÃO olha para o changelog: ele testa os
  // auxiliares acima. Está aqui porque um comparador secretamente
  // alfabético, um formato que aceite "v01.9.0" ou um validador que aceite
  // 31/02 fariam todos os testes de baixo passarem sem checar nada.
  it("compara versão por número e recusa versão e data impossíveis", () => {
    expect(comparaVersao("v1.12.0", "v1.9.0")).toBeGreaterThan(0);
    expect(comparaVersao("v1.2.0", "v1.10.0")).toBeLessThan(0);
    expect(comparaVersao("v2.0.0", "v1.99.99")).toBeGreaterThan(0);
    expect(comparaVersao("v1.0.1", "v1.0.0")).toBeGreaterThan(0);
    expect(comparaVersao("v1.0.0", "v1.0.0")).toBe(0);

    expect(partesDaVersao("v01.9.0")).toBeNull();
    expect(partesDaVersao("v1.09.0")).toBeNull();
    expect(partesDaVersao("1.9.0")).toBeNull();
    expect(partesDaVersao("v0.9.0")).not.toBeNull();

    expect(parseDataBr("31/02/2026")).toBeNull();
    expect(parseDataBr("29/02/2026")).toBeNull();
    expect(parseDataBr("00/01/2026")).toBeNull();
    expect(parseDataBr("01/13/2026")).toBeNull();
    expect(parseDataBr("2026-08-31")).toBeNull();
    expect(parseDataBr("29/02/2024")).toBeInstanceOf(Date);
  });
});

describe("regra de ouro: versão publicada não é reescrita", () => {
  it("as versões publicadas são exatamente as da tabela congelada", () => {
    // Pega bloco de versão apagado, inserido no meio ou remanejado.
    const publicadas = CHANGELOG.slice(1).map((v) => v.version);
    expect(
      publicadas,
      "uma versão publicada foi alterada: a lista de versões abaixo de " +
        `${CHANGELOG[0].version} não é mais a congelada neste teste. Se ` +
        "alguma foi apagada ou trocada de lugar, desfaça. Se uma versão " +
        "nova foi publicada, acrescente a anterior à TABELA_CONGELADA.",
    ).toEqual(TABELA_CONGELADA.map((v) => v.version));
  });

  it("nenhuma versão publicada mudou de data, de itens ou de texto", () => {
    // Pega texto reescrito, type trocado (muda o selo que o usuário lê),
    // item duplicado, item acrescentado e item removido.
    for (const congelada of TABELA_CONGELADA) {
      const viva = CHANGELOG.find((v) => v.version === congelada.version);
      if (!viva) {
        throw new Error(
          `uma versão publicada foi alterada: ${congelada.version} sumiu ` +
            "do CHANGELOG",
        );
      }
      const alerta = `uma versão publicada foi alterada: ${congelada.version}`;
      expect(viva.date, `${alerta} mudou de data`).toBe(congelada.date);
      expect(viva.entries.length, `${alerta} mudou de tamanho`).toBe(
        congelada.itens,
      );
      expect(
        resumoDosEntries(viva.entries),
        `${alerta} teve o texto ou o selo (type) de algum item mexido`,
      ).toBe(congelada.resumo);
    }
  });
});

describe("APP_VERSION", () => {
  // Basta esta: como o CHANGELOG está em ordem estritamente decrescente
  // (testado abaixo), ser a primeira já implica ser a maior de todas.
  it("é igual à version da primeira entrada do CHANGELOG", () => {
    expect(APP_VERSION).toBe(CHANGELOG[0].version);
  });
});

describe("versões do CHANGELOG", () => {
  it("toda version segue o formato vMAJOR.MINOR.PATCH", () => {
    for (const versao of CHANGELOG) {
      expect(
        partesDaVersao(versao.version),
        `version fora do formato: ${versao.version}`,
      ).not.toBeNull();
    }
  });

  it("está em ordem decrescente de verdade, comparando número a número", () => {
    // Estritamente decrescente: versão repetida também cai aqui.
    for (let i = 1; i < CHANGELOG.length; i++) {
      const anterior = CHANGELOG[i - 1].version;
      const atual = CHANGELOG[i].version;
      expect(
        comparaVersao(anterior, atual),
        `${anterior} deveria vir depois de ${atual} na lista, não antes`,
      ).toBeGreaterThan(0);
    }
  });
});

describe("datas do CHANGELOG", () => {
  it("toda date está em dd/mm/aaaa e é uma data que existe", () => {
    for (const versao of CHANGELOG) {
      expect(
        parseDataBr(versao.date),
        `date inválida em ${versao.version}: ${versao.date}`,
      ).not.toBeNull();
    }
  });

  it("nenhuma versão está datada no futuro", () => {
    // O teto que faltava. Sem ele, um dígito trocado no ano ou no mês da
    // versão em preparo — a única sem data congelada — passa batido.
    const agora = new Date();
    const hoje = new Date(
      agora.getFullYear(),
      agora.getMonth(),
      agora.getDate(),
    );
    for (const versao of CHANGELOG) {
      const d = parseDataBr(versao.date);
      if (!d) {
        throw new Error(`date inválida em ${versao.version}: ${versao.date}`);
      }
      expect(
        d.getTime(),
        `${versao.version} está datada em ${versao.date}, depois de hoje`,
      ).toBeLessThanOrEqual(hoje.getTime());
    }
  });

  it("não anda para trás conforme a lista desce", () => {
    // A lista é a mais nova primeiro, então cada data precisa ser menor ou
    // igual à de cima. Igual é permitido: duas versões saíram no mesmo dia.
    for (let i = 1; i < CHANGELOG.length; i++) {
      const acima = CHANGELOG[i - 1];
      const abaixo = CHANGELOG[i];
      const dAcima = parseDataBr(acima.date);
      const dAbaixo = parseDataBr(abaixo.date);
      if (!dAcima || !dAbaixo) {
        throw new Error(
          `data inválida entre ${acima.version} e ${abaixo.version}`,
        );
      }
      expect(
        dAbaixo.getTime(),
        `${abaixo.version} (${abaixo.date}) é mais nova que ` +
          `${acima.version} (${acima.date}), mas aparece abaixo dela`,
      ).toBeLessThanOrEqual(dAcima.getTime());
    }
  });
});

describe("entries do CHANGELOG", () => {
  // Estes três valem sobretudo para CHANGELOG[0], a versão em preparo: as
  // publicadas já estão presas pela tabela congelada lá em cima.
  it("toda versão tem ao menos um entry", () => {
    for (const versao of CHANGELOG) {
      expect(
        versao.entries.length,
        `${versao.version} foi publicada sem nenhum item`,
      ).toBeGreaterThan(0);
    }
  });

  it("todo type está dentro da união EntryType", () => {
    for (const versao of CHANGELOG) {
      for (const entry of versao.entries) {
        expect(
          Object.prototype.hasOwnProperty.call(TIPOS_VALIDOS, entry.type),
          `type desconhecido em ${versao.version}: "${entry.type}"`,
        ).toBe(true);
      }
    }
  });

  it("nenhum text é vazio ou só espaço", () => {
    for (const versao of CHANGELOG) {
      for (const entry of versao.entries) {
        expect(
          entry.text.trim().length,
          `entry sem texto em ${versao.version} (type "${entry.type}")`,
        ).toBeGreaterThan(0);
      }
    }
  });
});
