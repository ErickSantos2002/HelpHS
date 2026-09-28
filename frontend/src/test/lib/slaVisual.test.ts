import { describe, expect, it } from "vitest";
import {
  LIMIAR_PADRAO,
  getSlaVisualState,
  limiarDeAtencao,
} from "../../lib/slaVisual";

/**
 * A cor da barra de SLA, depois que ela parou de ter os limiares no código.
 *
 * O que estava errado: `pct >= 80` e `pct >= 60` fixos no `TicketListPage`, ao
 * lado de um `warning_threshold` configurável por prioridade que nenhum caminho
 * de produção lia. A Fase 2A fez o e-mail respeitar o campo; sem isto, o e-mail
 * sairia em 70% enquanto a barra só ficaria vermelha em 80% — duas réguas para
 * a mesma pergunta, e a tela discordando do aviso que a equipe recebeu.
 *
 * A régua nova preserva exatamente o visual de hoje quando o limiar é 80, que é
 * o default da coluna: âmbar em 60, vermelho em 80. Com 60, ela acompanha —
 * âmbar em 45, vermelho em 60.
 */

describe("limiarDeAtencao", () => {
  it("é 75% do limiar de alerta", () => {
    expect(limiarDeAtencao(80)).toBe(60);
    expect(limiarDeAtencao(60)).toBe(45);
    expect(limiarDeAtencao(100)).toBe(75);
  });

  it("não arredonda — a decisão de cor usa o valor exato", () => {
    // 70 * 0,75 = 52,5. Arredondar para 53 pintaria de verde um chamado que já
    // devia estar âmbar em 52,6.
    expect(limiarDeAtencao(70)).toBe(52.5);
  });
});

describe("getSlaVisualState com limiar 80 (o default de hoje)", () => {
  it("59,9 é verde", () => {
    expect(getSlaVisualState(59.9, 80, false)).toBe("verde");
  });

  it("60 é âmbar", () => {
    expect(getSlaVisualState(60, 80, false)).toBe("ambar");
  });

  it("79,9 é âmbar", () => {
    expect(getSlaVisualState(79.9, 80, false)).toBe("ambar");
  });

  it("80 é vermelho", () => {
    expect(getSlaVisualState(80, 80, false)).toBe("vermelho");
  });
});

describe("getSlaVisualState com limiar 60", () => {
  it("44,9 é verde", () => {
    expect(getSlaVisualState(44.9, 60, false)).toBe("verde");
  });

  it("45 é âmbar", () => {
    expect(getSlaVisualState(45, 60, false)).toBe("ambar");
  });

  it("59,9 é âmbar", () => {
    expect(getSlaVisualState(59.9, 60, false)).toBe("ambar");
  });

  it("60 é vermelho", () => {
    expect(getSlaVisualState(60, 60, false)).toBe("vermelho");
  });
});

describe("prioridades com limiares diferentes", () => {
  it("o mesmo percentual dá cores diferentes conforme o limiar", () => {
    // 55% consumido: já é âmbar para quem tem limiar 60, e ainda é verde para
    // quem tem 80. É o ponto inteiro desta fase.
    expect(getSlaVisualState(55, 60, false)).toBe("ambar");
    expect(getSlaVisualState(55, 80, false)).toBe("verde");
  });

  it("limiar crítico apertado antecipa o vermelho", () => {
    expect(getSlaVisualState(50, 50, false)).toBe("vermelho");
    expect(getSlaVisualState(50, 95, false)).toBe("verde");
  });
});

describe("vencido", () => {
  it("é vermelho em qualquer percentual", () => {
    expect(getSlaVisualState(0, 80, true)).toBe("vermelho");
    expect(getSlaVisualState(12, 80, true)).toBe("vermelho");
    expect(getSlaVisualState(100, 80, true)).toBe("vermelho");
  });

  it("é vermelho mesmo sem limiar nenhum", () => {
    expect(getSlaVisualState(0, null, true)).toBe("vermelho");
  });
});

describe("sem limiar do backend", () => {
  /**
   * `null` acontece em chamado sem prioridade — que nasce assim, esperando
   * triagem — e quando não há `SLAConfig` ativa para o nível.
   *
   * O fallback é 80, o DEFAULT DA COLUNA, e não uma escolha nova: assim o
   * chamado sem configuração é pintado exatamente como era antes desta fase.
   * Cair no verde esconderia urgência; cair no vermelho gritaria sem motivo.
   */
  it("usa o default da coluna", () => {
    expect(LIMIAR_PADRAO).toBe(80);
    expect(getSlaVisualState(59.9, null, false)).toBe("verde");
    expect(getSlaVisualState(60, null, false)).toBe("ambar");
    expect(getSlaVisualState(80, null, false)).toBe("vermelho");
  });

  it("undefined se comporta como null", () => {
    // Resposta antiga em cache não tem o campo novo.
    expect(getSlaVisualState(60, undefined, false)).toBe("ambar");
  });
});

describe("valores que não deviam chegar", () => {
  it("limiar zero ou negativo cai no default em vez de pintar tudo de vermelho", () => {
    // O banco tem CHECK de 1..100, mas a tela não pode depender disso para não
    // transformar um dado ruim numa barra vermelha em todo cartão da página.
    expect(getSlaVisualState(1, 0, false)).toBe("verde");
    expect(getSlaVisualState(1, -5, false)).toBe("verde");
  });

  it("percentual acima de 100 continua vermelho", () => {
    expect(getSlaVisualState(140, 80, false)).toBe("vermelho");
  });
});
