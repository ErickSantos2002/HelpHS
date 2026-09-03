import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SlaChip } from "../../components/ui/SlaChip";
import { AA, contraste } from "../helpers/contraste";

/**
 * Chip de prazo de SLA da página do chamado.
 *
 * Ele recebe três dados e cada um responde por uma coisa diferente:
 *   - `dueAt`: o prazo — de onde sai a CONTAGEM ("2h 10m") e o "Vencido";
 *   - `breached`: a flag do backend — de onde sai a COR;
 *   - `respondedAt`: quando a resposta foi dada — o que DESLIGA o relógio.
 *
 * O bug que motivou o teste: um chamado respondido no prazo e reaberto dias
 * depois mostrava "Resposta: Vencido" em âmbar. A cor estava certa (o backend
 * sabia que não houve violação) e a letra mentia, porque o chip comparava o
 * prazo com o relógio sem saber que a resposta já tinha sido dada.
 *
 * Por que não silenciar pelo `breached`: a flag só é recalculada em caminhos
 * de ESCRITA do backend, nunca na leitura. Um chamado que venceu há duas horas
 * e ninguém tocou tem `breached = false` — e é exatamente para ele que a
 * contagem ao vivo existe. Esconder o "Vencido" pela flag trocaria uma mentira
 * por outra, na direção mais perigosa.
 */

const AGORA = new Date("2026-08-21T12:00:00Z");

function emHoras(h: number) {
  return new Date(AGORA.getTime() + h * 3_600_000).toISOString();
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(AGORA);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("SlaChip — sem prazo", () => {
  it("não renderiza nada", () => {
    const { container } = render(<SlaChip label="Resposta" dueAt={null} breached={false} />);

    expect(container).toBeEmptyDOMElement();
  });
});

describe("SlaChip — relógio correndo", () => {
  it("mostra o tempo que falta", () => {
    render(<SlaChip label="Resposta" dueAt={emHoras(2.5)} breached={false} />);

    expect(screen.getByText("2h 30m")).toBeInTheDocument();
  });

  it("passado o prazo, diz Vencido", () => {
    render(<SlaChip label="Resposta" dueAt={emHoras(-1)} breached={true} />);

    expect(screen.getByText("Vencido")).toBeInTheDocument();
  });

  it("diz Vencido mesmo com breached=false — a flag é velha por construção", () => {
    // O backend só recalcula a flag quando alguém escreve no chamado. Um
    // chamado vencido e intocado chega com breached=false, e a contagem ao
    // vivo é o único lugar que conta a verdade sobre ele.
    render(<SlaChip label="Resposta" dueAt={emHoras(-1)} breached={false} />);

    expect(screen.getByText("Vencido")).toBeInTheDocument();
  });
});

describe("SlaChip — resposta já dada", () => {
  it("prazo passado mas respondido no ciclo anterior: Respondido, nunca Vencido", () => {
    // O caso do chamado reaberto: o prazo de resposta é o do primeiro ciclo,
    // muito no passado, e a resposta foi dada lá.
    render(
      <SlaChip
        label="Resposta"
        dueAt={emHoras(-72)}
        breached={false}
        respondedAt={emHoras(-80)}
      />,
    );

    expect(screen.getByText("Respondido")).toBeInTheDocument();
    expect(screen.queryByText("Vencido")).not.toBeInTheDocument();
  });

  it("respondido antes do prazo, com prazo ainda no futuro: Respondido, sem contagem", () => {
    // Respondeu às 9h, prazo às 14h, agora é meio-dia: o relógio não corre mais.
    render(
      <SlaChip label="Resposta" dueAt={emHoras(2)} breached={false} respondedAt={emHoras(-3)} />,
    );

    expect(screen.getByText("Respondido")).toBeInTheDocument();
    expect(screen.queryByText(/\d+h \d+m/)).not.toBeInTheDocument();
  });

  it("respondido mas com violação registrada: Respondido, e a cor continua de violação", () => {
    // Respondeu atrasado. A resposta existe (o relógio para) e a violação
    // também (a cor fica). Esconder uma das duas seria esconder história.
    render(
      <SlaChip label="Resposta" dueAt={emHoras(-5)} breached={true} respondedAt={emHoras(-1)} />,
    );

    expect(screen.getByText("Respondido")).toBeInTheDocument();
    // Fase 9: a asserção mira o TOKEN e não a paleta. Era /red/, da paleta crua
    // do Tailwind; hoje a tinta de violação é `tint-danger`/`on-tint-danger`, o
    // par que a E2 e a E8 mediram. A intenção do teste não mudou — a cor de
    // violação continua sendo exigida.
    expect(screen.getByText("Respondido").closest("span[class]")).toHaveClass(
      /danger/,
    );
  });
});

describe("SlaChip — Fase 9: as tintas saem da paleta crua", () => {
  it.each([
    ["violação", { breached: true }, "danger"],
    ["respondido", { breached: false, respondedAt: emHoras(-1) }, "success"],
    ["em andamento", { breached: false }, "warning"],
  ])("o estado de %s usa o par medido da tinta", (_nome, props, tinta) => {
    // Eram `bg-red-500/15 text-red-700 dark:text-red-400` e as irmãs: paleta
    // crua do Tailwind, fora do sistema de tokens, com a razão de contraste
    // nunca medida. Hoje são os pares `tint`/`on-tint` da E2 e da E8.
    const { container } = render(
      <SlaChip label="Resposta" dueAt={emHoras(3)} breached={false} {...props} />,
    );

    const chip = container.querySelector("span[class]")!;
    expect(chip.className).toContain("bg-tint-" + tinta);
    expect(chip.className).toContain("text-on-tint-" + tinta);
  });

  it("não sobra nenhuma cor da paleta crua", () => {
    const { container } = render(
      <SlaChip label="Resposta" dueAt={emHoras(3)} breached={true} />,
    );

    expect(container.innerHTML).not.toMatch(/red-\d|emerald-\d|amber-\d|slate-\d/);
  });

  it("o relógio não entra no nome acessível do chip", () => {
    // O ícone é decoração: a informação está no texto. Sem `aria-hidden` ele
    // vira parte do que o leitor de tela anuncia.
    //
    // A garantia mora no `Icon`, não aqui — este teste a prende no ponto de
    // uso. Validado por mutação NO `Icon`: tirar o atributo de lá derruba
    // este teste. Mutar o `SlaChip` não derrubava, e foi assim que se
    // descobriu que o `aria-hidden` repetido aqui era redundante.
    const { container } = render(
      <SlaChip label="Resposta" dueAt={emHoras(3)} breached={false} />,
    );

    expect(container.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
  });

  it.each(["claro", "escuro"] as const)(
    "as três tintas passam o piso de texto, tema %s",
    (tema) => {
      for (const tinta of ["danger", "success", "warning"] as const) {
        expect(
          contraste("--tint-" + tinta, "--on-tint-" + tinta, tema),
        ).toBeGreaterThanOrEqual(AA);
      }
    },
  );
});
