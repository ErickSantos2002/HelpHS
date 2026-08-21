import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SlaChip } from "../../components/ui/SlaChip";

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
    expect(screen.getByText("Respondido").closest("span[class]")).toHaveClass(/red/);
  });
});
