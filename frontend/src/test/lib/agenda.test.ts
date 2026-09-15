import { describe, expect, it } from "vitest";
import {
  chaveCivil,
  chaveDeOrdem,
  chaveFlutuante,
  descreveComData,
  descreveHorario,
  diaDaSemana,
  diasNoMes,
  horaCivil,
  instanteDe,
  jaTerminou,
  ocupaODia,
  ocupaOMes,
} from "../../lib/agenda";

/**
 * O relógio da agenda, com o fuso sempre EXPLÍCITO.
 *
 * Nenhum caso aqui lê o fuso da máquina. O CI roda em UTC e quem desenvolve roda
 * em Recife: um caso que usasse `getDate()` ou `getHours()` passaria num lugar e
 * reprovaria no outro — três horas por dia, que é o pior tipo de teste instável,
 * o que parece defeito de código e é defeito de relógio.
 *
 * As duas naturezas de evento, que a API também separa:
 *
 * - **Dia inteiro é data FLUTUANTE.** Vale a data em UTC, e o fuso de quem olha
 *   não a desloca. Todo evento que já existe foi gravado `00:00Z`–`23:59:59Z`; se
 *   o fuso o deslocasse, a agenda inteira andaria um dia para trás em Recife.
 * - **Evento com hora é um INSTANTE**, e cai no dia e na hora de quem olha.
 */

const RECIFE = "America/Recife";
const NOVA_YORK = "America/New_York";

const diaInteiro = (inicio: string, fim: string) => ({
  start_date: inicio,
  end_date: fim,
  all_day: true,
});
const comHora = (inicio: string, fim: string) => ({
  start_date: inicio,
  end_date: fim,
  all_day: false,
});

describe("chaveCivil e horaCivil — o dia e a hora no fuso de quem olha", () => {
  it("01:00Z do dia 1º de fevereiro é 22:00 do dia 31 de janeiro em Recife", () => {
    expect(chaveCivil("2026-02-01T01:00:00Z", RECIFE)).toBe("2026-01-31");
    expect(horaCivil("2026-02-01T01:00:00Z", RECIFE)).toBe("22:00");
  });

  it("o mesmo instante em UTC é o dia 1º", () => {
    expect(chaveCivil("2026-02-01T01:00:00Z", "UTC")).toBe("2026-02-01");
    expect(horaCivil("2026-02-01T01:00:00Z", "UTC")).toBe("01:00");
  });

  it("meia-noite sai como 00, e não como 24", () => {
    // Alguns motores devolvem "24:00" para meia-noite sem `hourCycle: "h23"`.
    expect(horaCivil("2026-01-15T03:00:00Z", RECIFE)).toBe("00:00");
  });
});

describe("chaveFlutuante — a data do dia inteiro não depende de fuso", () => {
  it("lê a data em UTC, inclusive a borda que a API grava", () => {
    expect(chaveFlutuante("2026-01-01T00:00:00Z")).toBe("2026-01-01");
    expect(chaveFlutuante("2026-01-01T23:59:59.999999Z")).toBe("2026-01-01");
  });
});

describe("instanteDe — o relógio de quem digita vira instante em UTC", () => {
  it("22:00 do dia 31 em Recife é 01:00Z do dia 1º", () => {
    expect(instanteDe("2026-01-31", "22:00", RECIFE)).toBe("2026-02-01T01:00:00.000Z");
  });

  it("acompanha o horário de verão de quem o tem", () => {
    // Nova York: -4 em julho, -5 em janeiro. Um deslocamento fixo erraria um dos
    // dois por uma hora, e só quem estivesse lá notaria.
    expect(instanteDe("2026-07-04", "09:00", NOVA_YORK)).toBe("2026-07-04T13:00:00.000Z");
    expect(instanteDe("2026-01-15", "09:00", NOVA_YORK)).toBe("2026-01-15T14:00:00.000Z");
  });

  it("na troca de horário de verão, a segunda passada corrige a primeira", () => {
    // Nova York adianta o relógio em 08/03/2026, às 07:00Z. "06:30" desse dia já
    // é horário de verão (-4): 10:30Z. A primeira passada lê o deslocamento no
    // instante errado (06:30Z, ainda -5) e daria 11:30Z — uma hora a mais. Só a
    // segunda acerta, e fora de uma troca as duas dão o mesmo número.
    expect(instanteDe("2026-03-08", "06:30", NOVA_YORK)).toBe("2026-03-08T10:30:00.000Z");
  });

  /*
    Achado da revisão: apagar um pedaço do `<input type="time">` deixa o valor
    vazio, e a conta lançava `RangeError: Invalid time value` — durante a
    renderização, sem ErrorBoundary: a tela inteira em branco, e o que a pessoa
    digitou, perdido. Entrada que não é hora devolve `null`, e quem chama decide.
  */
  it("hora vazia ou incompleta não lança: devolve null", () => {
    expect(() => instanteDe("2026-01-15", "", RECIFE)).not.toThrow();
    expect(instanteDe("2026-01-15", "", RECIFE)).toBeNull();
    expect(instanteDe("2026-01-15", "10:", RECIFE)).toBeNull();
    expect(instanteDe("", "10:00", RECIFE)).toBeNull();
  });

  it("hora e data que não existem no calendário também devolvem null", () => {
    // `Date.UTC` não recusa nada: 24:00 vira meia-noite do dia seguinte, e 30 de
    // fevereiro vira 2 de março — em silêncio, e gravado como se fosse o digitado.
    expect(instanteDe("2026-01-15", "24:00", RECIFE)).toBeNull();
    expect(instanteDe("2026-01-15", "10:60", RECIFE)).toBeNull();
    expect(instanteDe("2026-02-30", "10:00", RECIFE)).toBeNull();
    expect(instanteDe("2026-13-01", "10:00", RECIFE)).toBeNull();
  });

  it("hora que não existe (o relógio pulou) anda para a frente, como no Temporal", () => {
    // Los Angeles pula de 02:00 para 03:00 em 08/03/2026. "02:15" não existe; a
    // leitura convencional é 03:15 do horário de verão. Sem isso, 02:15 virava
    // 01:15 — ANTES de um início às 01:45, e o salvar travava com uma recusa que
    // a pessoa não tinha como entender.
    const LA = "America/Los_Angeles";
    expect(instanteDe("2026-03-08", "02:15", LA)).toBe("2026-03-08T10:15:00.000Z");
    expect(instanteDe("2026-03-08", "02:15", LA)! > instanteDe("2026-03-08", "01:45", LA)!).toBe(true);
    // E do lado leste do meridiano, onde a primeira passada erra para o outro lado.
    expect(instanteDe("2026-03-29", "02:30", "Europe/Berlin")).toBe("2026-03-29T01:30:00.000Z");
  });

  it("hora que se repete (o relógio voltou) fica com a primeira ocorrência", () => {
    // 01:30 acontece duas vezes em Los Angeles em 01/11/2026. A primeira é a do
    // horário de verão (08:30Z). É a escolha convencional — e a razão de a tela
    // não recalcular a hora que ninguém mexeu (ver o caso de ida e volta na tela).
    expect(instanteDe("2026-11-01", "01:30", "America/Los_Angeles")).toBe("2026-11-01T08:30:00.000Z");
  });

  it("em UTC é o próprio relógio", () => {
    expect(instanteDe("2026-01-15", "09:00", "UTC")).toBe("2026-01-15T09:00:00.000Z");
  });

  it("nunca produz segundos — a pegada do #17 é 23:59:59, e ela não pode sair daqui", () => {
    // O backend infere dia inteiro quando a chave não vem e o fim é 23:59:59
    // cravado. A tela nova sempre manda a chave, mas se um dia deixar de mandar,
    // este caso garante que o campo de hora não fabrica a pegada por acidente.
    expect(instanteDe("2026-01-15", "23:59", "UTC")).toBe("2026-01-15T23:59:00.000Z");
  });

  it("ida e volta: o instante gerado devolve o dia e a hora digitados", () => {
    for (const fuso of [RECIFE, NOVA_YORK, "UTC", "Asia/Tokyo"]) {
      for (const [dia, hora] of [
        ["2026-01-31", "22:00"],
        ["2026-03-01", "00:30"],
        ["2026-12-31", "23:59"],
      ]) {
        const instante = instanteDe(dia, hora, fuso)!;
        expect(chaveCivil(instante, fuso), `${fuso} ${dia} ${hora}`).toBe(dia);
        expect(horaCivil(instante, fuso), `${fuso} ${dia} ${hora}`).toBe(hora);
      }
    }
  });
});

describe("ocupaODia — em que células o evento aparece", () => {
  it("evento com hora que atravessa a meia-noite ocupa os dois dias", () => {
    const plantao = comHora("2026-02-01T01:00:00Z", "2026-02-01T05:00:00Z"); // 22:00 → 02:00 em Recife
    expect(ocupaODia(plantao, "2026-01-31", RECIFE)).toBe(true);
    expect(ocupaODia(plantao, "2026-02-01", RECIFE)).toBe(true);
    expect(ocupaODia(plantao, "2026-02-02", RECIFE)).toBe(false);
  });

  it("o mesmo evento, visto em UTC, ocupa só o dia 1º", () => {
    const plantao = comHora("2026-02-01T01:00:00Z", "2026-02-01T05:00:00Z");
    expect(ocupaODia(plantao, "2026-01-31", "UTC")).toBe(false);
    expect(ocupaODia(plantao, "2026-02-01", "UTC")).toBe(true);
  });

  it("terminar à meia-noite em ponto não ocupa o dia seguinte", () => {
    // 22:00 → 00:00. Sem o fim exclusivo, o evento apareceria numa célula onde
    // não dura um minuto sequer.
    const ateMeiaNoite = comHora("2026-01-16T01:00:00Z", "2026-01-16T03:00:00Z");
    expect(ocupaODia(ateMeiaNoite, "2026-01-15", RECIFE)).toBe(true);
    expect(ocupaODia(ateMeiaNoite, "2026-01-16", RECIFE)).toBe(false);
  });

  it("dia inteiro antigo do dia 1º não vaza para o dia 31 em Recife", () => {
    // A forma de toda linha de produção. Lida como instante, começaria às 21:00
    // do dia 31 — é o vazamento que a API também teve de separar.
    const antigo = diaInteiro("2026-01-01T00:00:00Z", "2026-01-01T23:59:59Z");
    expect(ocupaODia(antigo, "2025-12-31", RECIFE)).toBe(false);
    expect(ocupaODia(antigo, "2026-01-01", RECIFE)).toBe(true);
    expect(ocupaODia(antigo, "2026-01-02", RECIFE)).toBe(false);
  });

  it("dia inteiro de vários dias ocupa do primeiro ao último", () => {
    const semana = diaInteiro("2026-01-15T00:00:00Z", "2026-01-17T23:59:59.999999Z");
    expect(["2026-01-14", "2026-01-15", "2026-01-16", "2026-01-17", "2026-01-18"].map(
      (d) => ocupaODia(semana, d, RECIFE),
    )).toEqual([false, true, true, true, false]);
  });
});

describe("ocupaOMes — o mesmo corte que a API faz", () => {
  it("o evento das 22:00 de 31/01 é de janeiro em Recife, e de fevereiro em UTC", () => {
    const virada = comHora("2026-02-01T01:00:00Z", "2026-02-01T02:00:00Z");
    expect(ocupaOMes(virada, 2026, 0, RECIFE)).toBe(true);
    expect(ocupaOMes(virada, 2026, 1, RECIFE)).toBe(false);
    expect(ocupaOMes(virada, 2026, 0, "UTC")).toBe(false);
    expect(ocupaOMes(virada, 2026, 1, "UTC")).toBe(true);
  });

  it("dia inteiro do dia 1º é do mês dele, em qualquer fuso", () => {
    const antigo = diaInteiro("2026-01-01T00:00:00Z", "2026-01-01T23:59:59Z");
    for (const fuso of [RECIFE, "UTC", "Asia/Tokyo"]) {
      expect(ocupaOMes(antigo, 2025, 11, fuso), fuso).toBe(false);
      expect(ocupaOMes(antigo, 2026, 0, fuso), fuso).toBe(true);
    }
  });

  it("dezembro vira o ano", () => {
    const reveillon = comHora("2027-01-01T02:00:00Z", "2027-01-01T02:59:00Z"); // 23:00 de 31/12 em Recife
    expect(ocupaOMes(reveillon, 2026, 11, RECIFE)).toBe(true);
    expect(ocupaOMes(reveillon, 2027, 0, RECIFE)).toBe(false);
  });
});

describe("jaTerminou — o que sai da lista de próximos", () => {
  it("dia inteiro de HOJE não termina às 21:00 em Recife", () => {
    // O fim gravado é 23:59:59Z, que é 20:59 em Recife. Comparado como instante,
    // o treinamento de hoje sumiria da lista de próximos às nove da noite.
    const hoje = diaInteiro("2026-09-15T00:00:00Z", "2026-09-15T23:59:59.999999Z");
    const agora = new Date("2026-09-16T02:30:00Z"); // 23:30 de 15/09 em Recife
    expect(jaTerminou(hoje, agora, RECIFE)).toBe(false);
  });

  it("dia inteiro de ontem já terminou", () => {
    const ontem = diaInteiro("2026-09-14T00:00:00Z", "2026-09-14T23:59:59.999999Z");
    expect(jaTerminou(ontem, new Date("2026-09-15T12:00:00Z"), RECIFE)).toBe(true);
  });

  it("evento com hora termina no instante do fim", () => {
    const reuniao = comHora("2026-09-15T12:00:00Z", "2026-09-15T13:00:00Z");
    expect(jaTerminou(reuniao, new Date("2026-09-15T12:59:00Z"), RECIFE)).toBe(false);
    expect(jaTerminou(reuniao, new Date("2026-09-15T13:00:00Z"), RECIFE)).toBe(true);
  });
});

describe("chaveDeOrdem — a ordem é a do calendário, não a do instante", () => {
  it("o evento das 22:00 de 14/01 vem antes do dia inteiro de 15/01", () => {
    // Pelo instante seria o contrário: 15/01 00:00Z é anterior a 15/01 01:00Z.
    // Quem lê a lista em Recife vê o dia 14 antes do 15.
    const noite = comHora("2026-01-15T01:00:00Z", "2026-01-15T02:00:00Z");
    const dia15 = diaInteiro("2026-01-15T00:00:00Z", "2026-01-15T23:59:59Z");
    expect(chaveDeOrdem(noite, RECIFE) < chaveDeOrdem(dia15, RECIFE)).toBe(true);
  });

  it("no mesmo dia, dia inteiro vem antes de qualquer horário, até meia-noite", () => {
    const dia15 = diaInteiro("2026-01-15T00:00:00Z", "2026-01-15T23:59:59Z");
    const meiaNoite = comHora("2026-01-15T03:00:00Z", "2026-01-15T04:00:00Z"); // 00:00 em Recife
    expect(chaveDeOrdem(dia15, RECIFE) < chaveDeOrdem(meiaNoite, RECIFE)).toBe(true);
  });
});

describe("descreveHorario e descreveComData — o que a tela escreve", () => {
  it("dia inteiro de um dia só", () => {
    const e = diaInteiro("2026-01-15T00:00:00Z", "2026-01-15T23:59:59Z");
    expect(descreveHorario(e, RECIFE)).toBe("Dia inteiro");
    expect(descreveComData(e, RECIFE)).toBe("15/01 · Dia inteiro");
  });

  it("dia inteiro de vários dias", () => {
    const e = diaInteiro("2026-01-15T00:00:00Z", "2026-01-17T23:59:59.999999Z");
    expect(descreveHorario(e, RECIFE)).toBe("Dia inteiro · 15/01 → 17/01");
    expect(descreveComData(e, RECIFE)).toBe("15/01 → 17/01 · Dia inteiro");
  });

  it("evento com hora no mesmo dia, no relógio de Recife", () => {
    const e = comHora("2026-01-15T12:00:00Z", "2026-01-15T20:00:00Z");
    expect(descreveHorario(e, RECIFE)).toBe("09:00–17:00");
    expect(descreveComData(e, RECIFE)).toBe("15/01 · 09:00–17:00");
  });

  it("evento com hora que atravessa a meia-noite diz as duas datas", () => {
    const e = comHora("2026-02-01T01:00:00Z", "2026-02-01T05:00:00Z");
    expect(descreveHorario(e, RECIFE)).toBe("31/01 22:00 → 01/02 02:00");
    expect(descreveComData(e, RECIFE)).toBe("31/01 22:00 → 01/02 02:00");
  });

  it("terminar à meia-noite de um dia distante escreve o dia do fim, e não a véspera", () => {
    // 14/01 22:00 → 17/01 00:00. O último dia OCUPADO é 16/01 (o fim é exclusivo),
    // mas o fim ESCRITO é 17/01 00:00 — confundir os dois faria a tela dizer que o
    // evento acaba um dia antes.
    const e = comHora("2026-01-15T01:00:00Z", "2026-01-17T03:00:00Z");
    expect(descreveHorario(e, RECIFE)).toBe("14/01 22:00 → 17/01 00:00");
  });

  it("terminar à meia-noite em ponto continua sendo um dia só", () => {
    const e = comHora("2026-01-16T01:00:00Z", "2026-01-16T03:00:00Z"); // 22:00 → 00:00
    expect(descreveHorario(e, RECIFE)).toBe("22:00–00:00");
  });
});

describe("a grade — contas que não podem depender de fuso", () => {
  it("dia da semana de uma data civil", () => {
    expect(diaDaSemana("2026-09-15")).toBe(2); // terça
    expect(diaDaSemana("2026-02-01")).toBe(0); // domingo
  });

  it("dias no mês, com bissexto", () => {
    expect(diasNoMes(2026, 1)).toBe(28);
    expect(diasNoMes(2028, 1)).toBe(29);
    expect(diasNoMes(2026, 11)).toBe(31);
  });
});
