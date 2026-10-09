import { describe, expect, it } from "vitest";
import {
  formataUtil,
  precisaRecarregar,
  restanteUtil,
  textoDoVencimento,
  type Expediente,
} from "../../lib/tempoUtil";

/**
 * O contador de prazo, depois que ele parou de contar tempo corrido.
 *
 * O calendário NÃO está testado aqui, porque não está implementado aqui: dia
 * útil, jornada e feriado vivem no `backend/app/utils/sla.py`, e o teste deles
 * é `test_sla_tempo_util.py`. O que estes casos prendem é a aritmética da
 * tela — descontar enquanto a janela está aberta, congelar quando fecha, e não
 * misturar o relógio do servidor com o da máquina de quem olha.
 */

/** Quarta 23/09/2026, 09:39 em São Paulo, dentro do expediente. */
const ABERTO: Expediente = {
  agora: "2026-09-23T12:39:00Z", // 09:39 BRT
  aberto: true,
  proxima_virada: "2026-09-23T20:00:00Z", // 17:00 BRT
  fuso: "America/Sao_Paulo",
};

/** Mesma quarta, 22:00 — fora do expediente, reabre às 08:00 de quinta. */
const FECHADO: Expediente = {
  agora: "2026-09-24T01:00:00Z", // 22:00 BRT de quarta
  aberto: false,
  proxima_virada: "2026-09-24T11:00:00Z", // 08:00 BRT de quinta
  fuso: "America/Sao_Paulo",
};

const MINUTO = 60_000;

describe("restanteUtil", () => {
  it("no instante em que a resposta chega, mostra o que o backend mandou", () => {
    expect(restanteUtil(692, ABERTO, 0)).toBe(692);
  });

  it("durante o expediente, desconta um minuto por minuto", () => {
    expect(restanteUtil(692, ABERTO, 28 * MINUTO)).toBe(664);
  });

  it("fora do expediente, NÃO desconta nada — o valor congela", () => {
    // É a regra inteira num caso: a página aberta a noite toda mostra o mesmo
    // número às 22:00 e às 04:00.
    expect(restanteUtil(692, FECHADO, 0)).toBe(692);
    expect(restanteUtil(692, FECHADO, 6 * 60 * MINUTO)).toBe(692);
  });

  it("dentro do expediente, não desconta além do fim da janela", () => {
    // A janela do exemplo tem 7h21. Deixar a página aberta por 10h não pode
    // descontar 10h: das 17:00 em diante ninguém atende.
    const janelaMin = 7 * 60 + 21;
    expect(restanteUtil(692, ABERTO, 10 * 60 * MINUTO)).toBe(692 - janelaMin);
  });

  it("nunca devolve negativo", () => {
    expect(restanteUtil(5, ABERTO, 60 * MINUTO)).toBe(0);
  });

  it("prazo que já chegou a zero continua zero", () => {
    expect(restanteUtil(0, ABERTO, 0)).toBe(0);
  });

  it("relógio local atrasado não inventa tempo", () => {
    // `decorridoMs` negativo é o sintoma de relógio bagunçado; o contador não
    // pode AUMENTAR por causa disso.
    expect(restanteUtil(692, ABERTO, -30 * MINUTO)).toBe(692);
  });
});

describe("precisaRecarregar", () => {
  it("antes da virada, o dado ainda vale", () => {
    expect(precisaRecarregar(ABERTO, 60 * MINUTO)).toBe(false);
  });

  it("passada a virada, o dado envelheceu", () => {
    expect(precisaRecarregar(ABERTO, 8 * 60 * MINUTO)).toBe(true);
  });

  it("de noite, envelhece quando a jornada seguinte começa", () => {
    // É o que faz o contador voltar a diminuir às 08:00 sem a tela saber que
    // horas a jornada começa.
    expect(precisaRecarregar(FECHADO, 9 * 60 * MINUTO)).toBe(false);
    expect(precisaRecarregar(FECHADO, 11 * 60 * MINUTO)).toBe(true);
  });
});

describe("formataUtil", () => {
  it("horas e minutos", () => {
    expect(formataUtil(692)).toBe("11h 32m");
    expect(formataUtil(251)).toBe("4h 11m");
  });

  it("menos de uma hora mostra só os minutos", () => {
    expect(formataUtil(41)).toBe("41m");
  });

  it("hora cheia", () => {
    expect(formataUtil(120)).toBe("2h 0m");
  });
});

describe("textoDoVencimento", () => {
  it("mostra o vencimento no fuso da jornada, como o exemplo pedia", () => {
    // 12:11 em São Paulo é 15:11 UTC.
    expect(textoDoVencimento("2026-09-24T15:11:00Z", "America/Sao_Paulo")).toBe(
      "Vence em 24/09/2026 às 12:11",
    );
  });

  it("o fuso vem do backend — trocá-lo troca o horário mostrado", () => {
    // Prende a regra de D5: o fuso NÃO é literal do frontend. Se a jornada
    // mudar de fuso no motor, a tela acompanha sem ninguém editar isto aqui.
    expect(textoDoVencimento("2026-09-24T15:11:00Z", "UTC")).toBe(
      "Vence em 24/09/2026 às 15:11",
    );
  });

  it("o fuso vale para a DATA também, e não só para a hora", () => {
    // 02:00 UTC de quinta ainda é quarta-feira em São Paulo. Sem um instante
    // que VIRA O DIA, cravar o fuso só na data passava despercebido — foi o
    // que a mutação mostrou, com o caso acima verde.
    expect(textoDoVencimento("2026-09-24T02:00:00Z", "America/Sao_Paulo")).toBe(
      "Vence em 23/09/2026 às 23:00",
    );
    expect(textoDoVencimento("2026-09-24T02:00:00Z", "UTC")).toBe(
      "Vence em 24/09/2026 às 02:00",
    );
  });
});
