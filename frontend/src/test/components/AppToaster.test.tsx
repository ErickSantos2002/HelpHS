import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * A configuração do `sonner`.
 *
 * O `Toaster` da biblioteca é substituído por um espião: o que se quer prender
 * são as **props que chegam nele**, e montar o de verdade só testaria o sonner.
 * Interceptar é mais forte que ler o arquivo — pega também o caso de a
 * configuração existir no código e não chegar ao componente.
 */
let recebidas: Record<string, unknown> = {};

vi.mock("sonner", () => ({
  Toaster: (props: Record<string, unknown>) => {
    recebidas = props;
    return <div data-testid="toaster" />;
  },
}));

const { AppToaster } = await import("../../components/ui/AppToaster");
const { ThemeProvider } = await import("../../contexts/ThemeContext");

const CHAVE = "helphs-theme";

function montar() {
  render(
    <ThemeProvider>
      <AppToaster />
    </ThemeProvider>,
  );
  return recebidas;
}

beforeEach(() => {
  recebidas = {};
  localStorage.clear();
});

describe("AppToaster — o tema deixa de estar cravado", () => {
  it("segue a escolha guardada: claro", () => {
    // Estava `theme="dark"` cravado. No tema claro o toast continuava escuro —
    // a única peça da interface que não acompanhava o resto.
    localStorage.setItem(CHAVE, "light");

    expect(montar().theme).toBe("light");
  });

  it("segue a escolha guardada: escuro", () => {
    localStorage.setItem(CHAVE, "dark");

    expect(montar().theme).toBe("dark");
  });

  it("nunca manda 'system' para a biblioteca", () => {
    // `system` também não serve: o app tem escolha própria no armazenamento
    // local, e `system` ignoraria a escolha da pessoa para seguir o sistema
    // operacional.
    localStorage.setItem(CHAVE, "light");

    expect(montar().theme).not.toBe("system");
  });
});

describe("AppToaster — richColors sai, os tokens entram", () => {
  it("richColors não é passado", () => {
    // Ele pinta o fundo inteiro com a paleta PRÓPRIA da biblioteca, fora do
    // sistema de tokens e sem contraste medido.
    expect(montar().richColors).toBeUndefined();
  });

  it("o estilo do toast sai inteiro de tokens", () => {
    const style = (montar().toastOptions as { style: Record<string, string> }).style;

    expect(style.background).toBe("var(--toast-bg)");
    expect(style.color).toBe("var(--toast-color)");
    expect(style.border).toBe("1px solid var(--toast-border)");
    expect(style.boxShadow).toBe("var(--shadow-lg)");
    expect(style.borderRadius).toBe("var(--radius-lg)");
  });

  it("nenhum valor do estilo é cor literal", () => {
    const style = (montar().toastOptions as { style: Record<string, string> }).style;

    for (const valor of Object.values(style)) {
      expect(valor).not.toMatch(/#[0-9a-f]{3,8}\b|rgba?\(/i);
    }
  });
});

describe("AppToaster — a posição e o tempo", () => {
  it("canto superior direito, 80px de recuo, 4 segundos", () => {
    const p = montar();

    expect(p.position).toBe("top-right");
    expect(p.offset).toBe(80);
    expect((p.toastOptions as { duration: number }).duration).toBe(4000);
  });

  it("mantém o botão de fechar", () => {
    // Quatro segundos é pouco para um erro que a pessoa precisa ler duas vezes.
    expect(montar().closeButton).toBe(true);
  });
});

describe("AppToaster — a cor do tipo vai para o ícone", () => {
  function corDo(tipo: string) {
    const icones = montar().icons as Record<string, { props: { style: { color: string }; size: number } }>;
    return icones[tipo].props;
  }

  it.each([
    ["success", "var(--on-tint-success)"],
    ["error", "var(--on-tint-danger)"],
    ["warning", "var(--on-tint-warning)"],
    ["info", "var(--action)"],
  ])("o ícone de %s usa %s", (tipo, esperado) => {
    expect(corDo(tipo).style.color).toBe(esperado);
  });

  it("os quatro ícones têm 18px", () => {
    for (const tipo of ["success", "error", "warning", "info"]) {
      expect(corDo(tipo).size).toBe(18);
    }
  });

  it("nenhum ícone usa a cor cheia da rampa", () => {
    // O palpite óbvio para "a cor do tipo" reprova no tema claro:
    // `--color-warning-500` dá 2,15:1 contra `--toast-bg` e
    // `--color-success-500` dá 2,54:1, abaixo do piso de 3:1 da WCAG 1.4.11.
    // E `--action-success` reprova no ESCURO (2,71) pela mesma razão que o
    // `Input` não usa `--action-danger`: o bloco `.dark` não os redefine.
    for (const tipo of ["success", "error", "warning", "info"]) {
      expect(corDo(tipo).style.color).not.toMatch(/--color-\w+-500|--action-(success|danger)/);
    }
  });
});
