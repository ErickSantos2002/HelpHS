import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider, useTheme } from "../../contexts/ThemeContext";

/**
 * Tema da aplicação.
 *
 * O valor mora em dois lugares que precisam concordar: a classe `dark` no
 * `<html>` — que é o que o Tailwind lê — e a chave `helphs-theme` no
 * localStorage, que é o que sobrevive ao recarregar. Um sem o outro dá o bug
 * clássico de escolher claro, dar F5 e voltar escuro.
 *
 * O padrão do sistema aqui é o escuro, não a preferência do sistema
 * operacional: o HelpHS não lê `prefers-color-scheme`. Quem chega sem nada
 * salvo — e quem chega com um valor estragado — vê o escuro.
 */

const CHAVE = "helphs-theme";

function Consumidor() {
  const { theme, toggleTheme } = useTheme();
  return (
    <div>
      <span data-testid="tema">{theme}</span>
      <button type="button" onClick={toggleTheme}>
        Alternar
      </button>
    </div>
  );
}

function renderComProvider() {
  return render(
    <ThemeProvider>
      <Consumidor />
    </ThemeProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

describe("ThemeProvider — o que vale na primeira visita", () => {
  it("sem nada salvo, começa no escuro", () => {
    renderComProvider();

    expect(screen.getByTestId("tema")).toHaveTextContent("dark");
    expect(document.documentElement).toHaveClass("dark");
  });

  it("valor salvo estragado também cai no escuro", () => {
    // Chave escrita por uma versão antiga, ou mexida na mão pelo DevTools.
    localStorage.setItem(CHAVE, "solarized");

    renderComProvider();

    expect(screen.getByTestId("tema")).toHaveTextContent("dark");
    expect(document.documentElement).toHaveClass("dark");
  });

  it("grava o padrão já na primeira montagem", () => {
    renderComProvider();

    expect(localStorage.getItem(CHAVE)).toBe("dark");
  });
});

describe("ThemeProvider — a preferência sobrevive ao recarregar", () => {
  it("com 'light' salvo, monta no claro e tira a classe do html", () => {
    document.documentElement.classList.add("dark"); // como o index.html entrega
    localStorage.setItem(CHAVE, "light");

    renderComProvider();

    expect(screen.getByTestId("tema")).toHaveTextContent("light");
    expect(document.documentElement).not.toHaveClass("dark");
  });

  it("alternar grava a escolha nova", async () => {
    renderComProvider();

    await userEvent.click(screen.getByRole("button", { name: "Alternar" }));

    expect(screen.getByTestId("tema")).toHaveTextContent("light");
    expect(localStorage.getItem(CHAVE)).toBe("light");
  });

  it("o que foi gravado é o que a próxima montagem lê", async () => {
    // Este é o teste que fecha o ciclo: escolher, sair, voltar.
    const { unmount } = renderComProvider();
    await userEvent.click(screen.getByRole("button", { name: "Alternar" }));
    unmount();

    renderComProvider();

    expect(screen.getByTestId("tema")).toHaveTextContent("light");
    expect(document.documentElement).not.toHaveClass("dark");
  });
});

describe("ThemeProvider — alternar", () => {
  it("vai e volta entre escuro e claro", async () => {
    renderComProvider();

    await userEvent.click(screen.getByRole("button", { name: "Alternar" }));
    expect(document.documentElement).not.toHaveClass("dark");

    await userEvent.click(screen.getByRole("button", { name: "Alternar" }));

    expect(screen.getByTestId("tema")).toHaveTextContent("dark");
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem(CHAVE)).toBe("dark");
  });
});

describe("useTheme fora do provider", () => {
  it("estoura com mensagem clara em vez de devolver undefined", () => {
    const silencio = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(() => render(<Consumidor />)).toThrow(/useTheme must be used within ThemeProvider/);

    silencio.mockRestore();
  });
});
