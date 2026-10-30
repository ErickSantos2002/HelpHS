import { describe, expect, it } from "vitest";

import {
  OPCOES_DE_PERIODO,
  descreveIntervalo,
  diasNoIntervalo,
  ehDiaValido,
  hojeNosRelatorios,
  intervaloDoPreset,
  motivoDoIntervaloInvalido,
  resolvePeriodo,
  somaDias,
} from "../../lib/periodoRelatorio";

/**
 * Os períodos dos relatórios no calendário de Recife (F1-B-03b).
 *
 * Todo caso fixa o relógio com um instante UTC explícito. O CI roda em UTC e a
 * equipe em Recife (UTC−3): um caso que lesse `new Date()` sem fuso passaria
 * numa máquina e reprovaria na outra durante três horas por dia — exatamente o
 * defeito que este módulo existe para não ter.
 */

/** 30/10/2026 às 12:00 em Recife (15:00 UTC). */
const MEIO_DIA = new Date("2026-10-30T15:00:00Z");

describe("os presets, num dia comum", () => {
  it("Hoje é o dia de Recife, de ponta a ponta", () => {
    expect(intervaloDoPreset("hoje", MEIO_DIA)).toEqual({
      start_date: "2026-10-30",
      end_date: "2026-10-30",
    });
  });

  it("Ontem é um dia só — e não as últimas 48 horas", () => {
    // O "Ontem" antigo mandava `period=2`: dois dias contados de agora, que é
    // ontem E hoje juntos.
    expect(intervaloDoPreset("ontem", MEIO_DIA)).toEqual({
      start_date: "2026-10-29",
      end_date: "2026-10-29",
    });
  });

  it("Últimos 7 dias são 7 dias de calendário, hoje incluído (D2)", () => {
    const r = intervaloDoPreset("7-dias", MEIO_DIA);
    expect(r).toEqual({ start_date: "2026-10-24", end_date: "2026-10-30" });
    expect(diasNoIntervalo(r.start_date, r.end_date)).toBe(7);
  });

  it("Últimos 30 dias são 30 dias de calendário, hoje incluído", () => {
    const r = intervaloDoPreset("30-dias", MEIO_DIA);
    expect(r).toEqual({ start_date: "2026-10-01", end_date: "2026-10-30" });
    expect(diasNoIntervalo(r.start_date, r.end_date)).toBe(30);
  });

  it("Este mês vai do dia 1º até hoje", () => {
    expect(intervaloDoPreset("este-mes", MEIO_DIA)).toEqual({
      start_date: "2026-10-01",
      end_date: "2026-10-30",
    });
  });

  it("Mês passado é o mês civil anterior inteiro — e não os últimos 60 dias", () => {
    expect(intervaloDoPreset("mes-passado", MEIO_DIA)).toEqual({
      start_date: "2026-09-01",
      end_date: "2026-09-30",
    });
  });

  it("as sete opções são as da decisão D1, nesta ordem", () => {
    expect(OPCOES_DE_PERIODO.map((o) => o.label)).toEqual([
      "Hoje",
      "Ontem",
      "Últimos 7 dias",
      "Últimos 30 dias",
      "Este mês",
      "Mês passado",
      "Personalizado",
    ]);
  });
});

describe("UTC × Recife", () => {
  it("às 22:30 de Recife o dia em UTC já é amanhã, e Hoje continua sendo hoje", () => {
    // 31/10 01:30 UTC = 30/10 22:30 em Recife. `toISOString().slice(0, 10)`,
    // que as telas usavam, devolveria 31/10 — e a API recusaria o pedido como
    // "data final no futuro".
    const noite = new Date("2026-10-31T01:30:00Z");
    expect(new Date(noite).toISOString().slice(0, 10)).toBe("2026-10-31");
    expect(hojeNosRelatorios(noite)).toBe("2026-10-30");
    expect(intervaloDoPreset("hoje", noite)).toEqual({
      start_date: "2026-10-30",
      end_date: "2026-10-30",
    });
  });

  it("à meia-noite em ponto de Recife o dia já é o novo", () => {
    // 03:00 UTC = 00:00 em Recife: a meia-noite pertence ao dia que começa.
    expect(hojeNosRelatorios(new Date("2026-10-31T03:00:00Z"))).toBe("2026-10-31");
    expect(hojeNosRelatorios(new Date("2026-10-31T02:59:59Z"))).toBe("2026-10-30");
  });
});

describe("viradas de calendário", () => {
  it("virada de mês: Ontem no dia 1º é o último dia do mês anterior", () => {
    const primeiro = new Date("2026-11-01T12:00:00Z");
    expect(intervaloDoPreset("ontem", primeiro)).toEqual({
      start_date: "2026-10-31",
      end_date: "2026-10-31",
    });
    expect(intervaloDoPreset("este-mes", primeiro)).toEqual({
      start_date: "2026-11-01",
      end_date: "2026-11-01",
    });
    expect(intervaloDoPreset("7-dias", primeiro)).toEqual({
      start_date: "2026-10-26",
      end_date: "2026-11-01",
    });
  });

  it("virada de ano: Mês passado em janeiro é dezembro do ano anterior", () => {
    const janeiro = new Date("2027-01-15T12:00:00Z");
    expect(intervaloDoPreset("mes-passado", janeiro)).toEqual({
      start_date: "2026-12-01",
      end_date: "2026-12-31",
    });
    expect(intervaloDoPreset("ontem", new Date("2027-01-01T12:00:00Z"))).toEqual({
      start_date: "2026-12-31",
      end_date: "2026-12-31",
    });
  });

  it("virada de ano pela noite: 31/12 às 23:00 de Recife ainda é 2026", () => {
    // 01/01 02:00 UTC.
    const reveillon = new Date("2027-01-01T02:00:00Z");
    expect(intervaloDoPreset("hoje", reveillon)).toEqual({
      start_date: "2026-12-31",
      end_date: "2026-12-31",
    });
    expect(intervaloDoPreset("este-mes", reveillon).start_date).toBe("2026-12-01");
  });

  it("Mês passado em março pega fevereiro com 28 ou 29 dias", () => {
    expect(intervaloDoPreset("mes-passado", new Date("2027-03-10T12:00:00Z")).end_date)
      .toBe("2027-02-28");
    expect(intervaloDoPreset("mes-passado", new Date("2028-03-10T12:00:00Z")).end_date)
      .toBe("2028-02-29");
  });

  it("somaDias atravessa mês e ano sem tropeçar", () => {
    expect(somaDias("2026-12-31", 1)).toBe("2027-01-01");
    expect(somaDias("2026-03-01", -1)).toBe("2026-02-28");
  });
});

describe("Personalizado", () => {
  it("manda as datas escolhidas, sem convertê-las em quantidade de dias", () => {
    expect(
      resolvePeriodo("personalizado", { inicio: "2026-08-03", fim: "2026-08-17" }, MEIO_DIA),
    ).toEqual({ ok: true, intervalo: { start_date: "2026-08-03", end_date: "2026-08-17" } });
  });

  it("datas invertidas são recusadas antes de pedir, com a frase da API", () => {
    expect(
      resolvePeriodo("personalizado", { inicio: "2026-10-20", fim: "2026-10-10" }, MEIO_DIA),
    ).toEqual({ ok: false, erro: "A data inicial não pode ser posterior à data final." });
  });

  it("uma ponta vazia é recusada", () => {
    expect(motivoDoIntervaloInvalido("2026-10-01", "", MEIO_DIA)).toBe(
      "Informe a data inicial e a data final.",
    );
  });

  it("fim no futuro é recusado — o futuro medido em Recife", () => {
    expect(motivoDoIntervaloInvalido("2026-10-01", "2026-10-31", MEIO_DIA)).toBe(
      "A data final não pode estar no futuro.",
    );
    // Às 22:30 de Recife, 31/10 ainda é amanhã, mesmo já sendo 31/10 em UTC.
    expect(
      motivoDoIntervaloInvalido("2026-10-01", "2026-10-31", new Date("2026-10-31T01:30:00Z")),
    ).toBe("A data final não pode estar no futuro.");
    expect(motivoDoIntervaloInvalido("2026-10-01", "2026-10-30", MEIO_DIA)).toBeNull();
  });

  it("aceita até 366 dias e recusa 367", () => {
    expect(motivoDoIntervaloInvalido("2025-10-30", "2026-10-30", MEIO_DIA)).toBeNull();
    expect(diasNoIntervalo("2025-10-30", "2026-10-30")).toBe(366);
    expect(motivoDoIntervaloInvalido("2025-10-29", "2026-10-30", MEIO_DIA)).toBe(
      "O intervalo pode ter no máximo 366 dias.",
    );
  });

  it("data que não existe no calendário é recusada", () => {
    expect(ehDiaValido("2026-02-30")).toBe(false);
    expect(ehDiaValido("2028-02-29")).toBe(true);
    expect(motivoDoIntervaloInvalido("2026-02-30", "2026-03-10", MEIO_DIA)).toBe(
      "Data inválida. Use o formato AAAA-MM-DD.",
    );
  });

  it("os presets nunca passam pela validação do personalizado", () => {
    expect(resolvePeriodo("hoje", { inicio: "", fim: "" }, MEIO_DIA)).toEqual({
      ok: true,
      intervalo: { start_date: "2026-10-30", end_date: "2026-10-30" },
    });
  });
});

describe("o que a tela escreve", () => {
  it("um dia só, sem ano quando é o ano corrente", () => {
    expect(descreveIntervalo({ start_date: "2026-10-30", end_date: "2026-10-30" }, MEIO_DIA))
      .toBe("30/10");
  });

  it("um intervalo, com as duas pontas", () => {
    expect(descreveIntervalo({ start_date: "2026-10-24", end_date: "2026-10-30" }, MEIO_DIA))
      .toBe("24/10 – 30/10");
  });

  it("o ano aparece quando não é o corrente — dezembro visto de janeiro", () => {
    expect(
      descreveIntervalo(
        { start_date: "2026-12-01", end_date: "2026-12-31" },
        new Date("2027-01-15T12:00:00Z"),
      ),
    ).toBe("01/12/2026 – 31/12/2026");
  });
});
