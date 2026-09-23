import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SlaChip } from "../../components/ui/SlaChip";
import type { Expediente } from "../../lib/tempoUtil";
import { AA, contraste } from "../helpers/contraste";

/**
 * Chip de prazo de SLA da página do chamado.
 *
 * Cada dado responde por uma coisa diferente:
 *   - `restanteMin` + `expediente`: a CONTAGEM ("4h 11m úteis") e o "Vencido";
 *   - `breached`: a flag do backend — de onde sai a COR;
 *   - `respondedAt`: quando a resposta foi dada — o que DESLIGA o relógio.
 *
 * ── O que mudou em 23/09/2026 ─────────────────────────────────────────
 *
 * Ele recebia `dueAt` e fazia `dueAt - Date.now()`: tempo CORRIDO. Um prazo de
 * 12h ÚTEIS carimbado às 09:11 aparecia como "27h", porque a conta incluía as
 * 15 horas entre 17:00 e 08:00. Agora o backend manda os minutos úteis que
 * faltam, e o chip só desconta o que passa enquanto o expediente está aberto.
 *
 * **O calendário não é testado aqui porque não está implementado aqui.**
 * Jornada, fim de semana e feriado vivem em `backend/app/utils/sla.py` e são
 * provados em `test_sla_tempo_util.py`. Estes casos prendem a aritmética da
 * tela e as três responsabilidades acima.
 *
 * ── O bug que motivou o `respondedAt` ─────────────────────────────────
 *
 * Um chamado respondido no prazo e reaberto dias depois mostrava "Resposta:
 * Vencido" em âmbar. A cor estava certa (o backend sabia que não houve
 * violação) e a letra mentia.
 *
 * Por que não silenciar pelo `breached`: a flag só é recalculada em caminhos
 * de ESCRITA do backend, nunca na leitura. Um chamado que venceu há duas horas
 * e ninguém tocou tem `breached = false` — e é exatamente para ele que a
 * contagem ao vivo existe. Esconder o "Vencido" pela flag trocaria uma mentira
 * por outra, na direção mais perigosa.
 */

const AGORA = new Date("2026-09-23T12:39:00Z"); // 09:39 em São Paulo

/** Expediente aberto, fechando às 17:00 (20:00 UTC). */
const ABERTO: Expediente = {
  agora: AGORA.toISOString(),
  aberto: true,
  proxima_virada: "2026-09-23T20:00:00Z",
  fuso: "America/Sao_Paulo",
};

/** Noite: fechado, reabre às 08:00 do dia seguinte. */
const FECHADO: Expediente = {
  agora: "2026-09-24T01:00:00Z",
  aberto: false,
  proxima_virada: "2026-09-24T11:00:00Z",
  fuso: "America/Sao_Paulo",
};

const VENCE_EM = "2026-09-24T15:11:00Z"; // 12:11 em São Paulo

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(AGORA);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("SlaChip — sem prazo", () => {
  it("não renderiza nada", () => {
    const { container } = render(
      <SlaChip
        label="Resposta"
        restanteMin={null}
        venceEm={null}
        expediente={ABERTO}
        breached={false}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("sem expediente também não renderiza — melhor calado que errado", () => {
    const { container } = render(
      <SlaChip
        label="Resposta"
        restanteMin={251}
        venceEm={VENCE_EM}
        expediente={null}
        breached={false}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});

describe("SlaChip — relógio correndo", () => {
  it("mostra o tempo ÚTIL que falta, com a palavra", () => {
    // "úteis" não é enfeite: sem ela o número parece hora de relógio, e foi
    // essa leitura que deixou "27h" passar despercebido.
    render(
      <SlaChip
        label="Resolução"
        restanteMin={251}
        venceEm={VENCE_EM}
        expediente={ABERTO}
        breached={false}
      />,
    );

    expect(screen.getByText("4h 11m úteis")).toBeInTheDocument();
  });

  it("zerado o prazo, diz Vencido", () => {
    render(
      <SlaChip
        label="Resposta"
        restanteMin={0}
        venceEm={VENCE_EM}
        expediente={ABERTO}
        breached={true}
      />,
    );

    expect(screen.getByText("Vencido")).toBeInTheDocument();
  });

  it("diz Vencido mesmo com breached=false — a flag é velha por construção", () => {
    render(
      <SlaChip
        label="Resposta"
        restanteMin={0}
        venceEm={VENCE_EM}
        expediente={ABERTO}
        breached={false}
      />,
    );

    expect(screen.getByText("Vencido")).toBeInTheDocument();
  });

  it("o detalhe do vencimento vem no título, no fuso da jornada", () => {
    render(
      <SlaChip
        label="Resolução"
        restanteMin={251}
        venceEm={VENCE_EM}
        expediente={ABERTO}
        breached={false}
      />,
    );

    expect(screen.getByTitle("Vence em 24/09/2026 às 12:11")).toBeInTheDocument();
  });
});

describe("SlaChip — fora do expediente", () => {
  it("o valor congela e a tela diz por quê", () => {
    render(
      <SlaChip
        label="Resolução"
        restanteMin={251}
        venceEm={VENCE_EM}
        expediente={FECHADO}
        breached={false}
      />,
    );

    expect(screen.getByText("4h 11m úteis")).toBeInTheDocument();
    expect(screen.getByText("· fora do expediente")).toBeInTheDocument();
  });

  it("passada meia hora de noite, o número é o MESMO", () => {
    // É a regra inteira num caso: o contador não desce enquanto ninguém
    // atende. Antes ele descia a noite toda.
    render(
      <SlaChip
        label="Resolução"
        restanteMin={251}
        venceEm={VENCE_EM}
        expediente={FECHADO}
        breached={false}
      />,
    );
    expect(screen.getByText("4h 11m úteis")).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(30 * 60_000));

    expect(screen.getByText("4h 11m úteis")).toBeInTheDocument();
  });

  it("dentro do expediente, meia hora DESCE o contador", () => {
    // O contraponto do caso acima: sem ele, um chip que nunca anda passaria
    // pelos dois.
    render(
      <SlaChip
        label="Resolução"
        restanteMin={251}
        venceEm={VENCE_EM}
        expediente={ABERTO}
        breached={false}
      />,
    );
    expect(screen.getByText("4h 11m úteis")).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(30 * 60_000));

    expect(screen.getByText("3h 41m úteis")).toBeInTheDocument();
  });

  it("o sufixo não aparece em chamado já vencido", () => {
    render(
      <SlaChip
        label="Resolução"
        restanteMin={0}
        venceEm={VENCE_EM}
        expediente={FECHADO}
        breached={true}
      />,
    );

    expect(screen.queryByText("· fora do expediente")).not.toBeInTheDocument();
  });
});

describe("SlaChip — virada do expediente", () => {
  it("passada a virada, pede que a página busque de novo", () => {
    // É o que faz o contador voltar a andar quando a jornada seguinte começa:
    // a tela não sabe que horas a jornada abre, e não precisa saber.
    const aoExpirar = vi.fn();
    render(
      <SlaChip
        label="Resolução"
        restanteMin={251}
        venceEm={VENCE_EM}
        expediente={ABERTO}
        breached={false}
        onExpirou={aoExpirar}
      />,
    );

    expect(aoExpirar).not.toHaveBeenCalled();

    // A janela do exemplo tem 7h21; oito horas passam dela.
    act(() => vi.advanceTimersByTime(8 * 60 * 60_000));

    expect(aoExpirar).toHaveBeenCalledTimes(1);
  });

  it("pede UMA vez por virada, e não a cada minuto", () => {
    const aoExpirar = vi.fn();
    render(
      <SlaChip
        label="Resolução"
        restanteMin={251}
        venceEm={VENCE_EM}
        expediente={ABERTO}
        breached={false}
        onExpirou={aoExpirar}
      />,
    );

    act(() => vi.advanceTimersByTime(10 * 60 * 60_000));

    expect(aoExpirar).toHaveBeenCalledTimes(1);
  });
});

describe("SlaChip — resposta já dada", () => {
  it("prazo passado mas respondido no ciclo anterior: Respondido, nunca Vencido", () => {
    // O caso do chamado reaberto: o prazo de resposta é o do primeiro ciclo,
    // muito no passado, e a resposta foi dada lá.
    render(
      <SlaChip
        label="Resposta"
        restanteMin={0}
        venceEm={VENCE_EM}
        expediente={ABERTO}
        breached={false}
        respondedAt="2026-09-20T12:00:00Z"
      />,
    );

    expect(screen.getByText("Respondido")).toBeInTheDocument();
    expect(screen.queryByText("Vencido")).not.toBeInTheDocument();
  });

  it("respondido antes do prazo: Respondido, sem contagem", () => {
    render(
      <SlaChip
        label="Resposta"
        restanteMin={251}
        venceEm={VENCE_EM}
        expediente={ABERTO}
        breached={false}
        respondedAt="2026-09-23T11:00:00Z"
      />,
    );

    expect(screen.getByText("Respondido")).toBeInTheDocument();
    expect(screen.queryByText(/úteis/)).not.toBeInTheDocument();
  });

  it("respondido mas com violação registrada: Respondido, e a cor continua de violação", () => {
    // Respondeu atrasado. A resposta existe (o relógio para) e a violação
    // também (a cor fica). Esconder uma das duas seria esconder história.
    render(
      <SlaChip
        label="Resposta"
        restanteMin={0}
        venceEm={VENCE_EM}
        expediente={ABERTO}
        breached={true}
        respondedAt="2026-09-23T11:00:00Z"
      />,
    );

    expect(screen.getByText("Respondido")).toBeInTheDocument();
    // Fase 9: a asserção mira o TOKEN e não a paleta. Era /red/, da paleta crua
    // do Tailwind; hoje a tinta de violação é `tint-danger`/`on-tint-danger`, o
    // par que a E2 e a E8 mediram. A intenção do teste não mudou.
    expect(screen.getByText("Respondido").closest("span[class]")).toHaveClass(/danger/);
  });
});

describe("SlaChip — Fase 9: as tintas saem da paleta crua", () => {
  it.each([
    ["violação", { breached: true }, "danger"],
    ["respondido", { breached: false, respondedAt: "2026-09-23T11:00:00Z" }, "success"],
    ["em andamento", { breached: false }, "warning"],
  ])("o estado de %s usa o par medido da tinta", (_nome, props, tinta) => {
    // Eram `bg-red-500/15 text-red-700 dark:text-red-400` e as irmãs: paleta
    // crua do Tailwind, fora do sistema de tokens, com a razão de contraste
    // nunca medida. Hoje são os pares `tint`/`on-tint` da E2 e da E8.
    const { container } = render(
      <SlaChip
        label="Resposta"
        restanteMin={180}
        venceEm={VENCE_EM}
        expediente={ABERTO}
        {...props}
      />,
    );

    const chip = container.querySelector("span[class]")!;
    expect(chip.className).toContain("bg-tint-" + tinta);
    expect(chip.className).toContain("text-on-tint-" + tinta);
  });

  it("não sobra nenhuma cor da paleta crua", () => {
    const { container } = render(
      <SlaChip
        label="Resposta"
        restanteMin={180}
        venceEm={VENCE_EM}
        expediente={ABERTO}
        breached={true}
      />,
    );

    expect(container.innerHTML).not.toMatch(/red-\d|emerald-\d|amber-\d|slate-\d/);
  });

  it("o relógio não entra no nome acessível do chip", () => {
    // O ícone é decoração: a informação está no texto. Sem `aria-hidden` ele
    // vira parte do que o leitor de tela anuncia.
    //
    // A garantia mora no `Icon`, não aqui — este teste a prende no ponto de
    // uso. Validado por mutação NO `Icon`: tirar o atributo de lá derruba
    // este teste.
    const { container } = render(
      <SlaChip
        label="Resposta"
        restanteMin={180}
        venceEm={VENCE_EM}
        expediente={ABERTO}
        breached={false}
      />,
    );

    expect(container.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
  });

  it.each(["claro", "escuro"] as const)(
    "as três tintas passam o piso de texto, tema %s",
    (tema) => {
      for (const tinta of ["danger", "success", "warning"] as const) {
        expect(contraste("--tint-" + tinta, "--on-tint-" + tinta, tema)).toBeGreaterThanOrEqual(
          AA,
        );
      }
    },
  );
});
