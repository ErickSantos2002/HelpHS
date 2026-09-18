import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { KpiCard } from "../../components/ui/KpiCard";
import type { KpiTone } from "../../components/ui/KpiCard";
import { AA, contraste } from "../helpers/contraste";

/**
 * O cartão de indicador, que existia em três cópias divergentes.
 *
 * A causa-raiz das três era a mesma: uma prop de **classe crua** — `color` num
 * painel, `valueCls` nos outros dois, mais `accent` e `iconBg`. Por ela
 * entraram `text-sky-600`, `text-violet-600`, `text-indigo-600` e
 * `bg-amber-500/10`, todos fora do sistema de tokens e nunca medidos.
 *
 * O que este arquivo prende não é o desenho: é o **tipo fechado**. Prop de
 * classe aberta não é atalho, é a porta pela qual a cor entra sem revisão.
 */

const TONS: KpiTone[] = ["neutral", "primary", "info", "success", "warning", "danger"];
const COLORIDOS = TONS.filter((t) => t !== "neutral");

describe("KpiCard — o tipo fechado", () => {
  it("não aceita classe crua: só o tom decide a cor", () => {
    // A prova é de TIPO, e ela roda no `tsc`, não aqui. O que este teste pode
    // prender é o efeito: nenhuma cor renderizada vem de fora do sistema.
    const { container } = render(
      <KpiCard label="Abertos" value={12} sub="hoje" tone="danger" icon={<i />} />,
    );

    expect(container.innerHTML).not.toMatch(
      /sky-|violet-|indigo-|amber-|emerald-|red-\d|slate-\d/,
    );
  });

  it.each(TONS)("o tom %s pinta filete, ícone e número com tokens", (tone) => {
    const { container } = render(
      <KpiCard label="Abertos" value={1} tone={tone} icon={<i />} />,
    );
    const html = container.innerHTML;

    if (tone === "neutral") {
      expect(html).toContain("border-l-borda-strong");
      expect(html).toContain("text-conteudo-heading");
      expect(html).toContain("bg-surface-elevated");
    } else {
      expect(html).toContain("border-l-" + tone);
      expect(html).toContain("bg-tint-" + tone);
      expect(html).toContain("text-on-tint-" + tone);
    }
  });

  it("o padrão é neutro", () => {
    const { container } = render(<KpiCard label="Abertos" value={1} />);

    expect(container.innerHTML).toContain("text-conteudo-heading");
  });
});

describe("KpiCard — o conteúdo", () => {
  it("mostra rótulo, valor e a segunda linha", () => {
    render(<KpiCard label="Abertos" value={42} sub="últimos 7 dias" />);

    expect(screen.getByText("Abertos")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("últimos 7 dias")).toBeInTheDocument();
  });

  it("sem sub, não renderiza a segunda linha vazia", () => {
    const { container } = render(<KpiCard label="Abertos" value={0} />);

    expect(container.querySelectorAll("p")).toHaveLength(2);
  });

  it("o ícone é decoração e sai da árvore de acessibilidade", () => {
    // O que o cartão mede está no rótulo. O ícone repete a mesma informação em
    // desenho, e anunciá-lo faria o leitor de tela dizer a coisa duas vezes.
    const { container } = render(
      <KpiCard label="Abertos" value={1} icon={<i data-testid="ic" />} />,
    );

    expect(container.querySelector('[aria-hidden="true"]')).not.toBeNull();
    expect(screen.getByTestId("ic")).toBeInTheDocument();
  });

  it("sem ícone, não sobra a caixa dele", () => {
    const { container } = render(<KpiCard label="Abertos" value={1} />);

    expect(container.querySelector('[aria-hidden="true"]')).toBeNull();
  });
});

describe("KpiCard — contraste do número colorido", () => {
  // O par `tint`/`on-tint` foi medido sobre a TINTA. Aqui o número colorido
  // fica sobre a superfície NUA do cartão, que é outra medição — e é ela que
  // justifica manter o sinal de cor que os painéis já davam.
  it.each(["claro", "escuro"] as const)(
    "o número de cada tom passa o piso de texto sobre a superfície, tema %s",
    (tema) => {
      for (const tone of COLORIDOS) {
        expect(
          contraste("--surface", "--on-tint-" + tone, tema),
        ).toBeGreaterThanOrEqual(AA);
      }
    },
  );

  it.each(["claro", "escuro"] as const)(
    "o par do ícone continua valendo sobre a própria tinta, tema %s",
    (tema) => {
      for (const tone of COLORIDOS) {
        expect(
          contraste("--tint-" + tone, "--on-tint-" + tone, tema),
        ).toBeGreaterThanOrEqual(AA);
      }
    },
  );
});
