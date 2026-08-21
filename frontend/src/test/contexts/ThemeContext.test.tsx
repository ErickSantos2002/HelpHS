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
 * Quem nunca escolheu recebe a preferência do SISTEMA OPERACIONAL
 * (`prefers-color-scheme`); quem já escolheu manda, contra o sistema
 * inclusive. Por isso a preferência só é gravada quando alguém alterna: se
 * fosse gravada na primeira montagem, o valor do SO ficaria congelado ali e o
 * "seguir o sistema" valeria por uma visita só.
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

/**
 * Finge a preferência do SO. happy-dom não traz `matchMedia`, e sem stub o
 * provider cairia sempre no mesmo ramo — o teste passaria sem testar nada.
 */
function sistemaPrefere(modo: "light" | "dark" | "sem-suporte") {
  if (modo === "sem-suporte") {
    // @ts-expect-error — simula navegador/ambiente sem matchMedia
    window.matchMedia = undefined;
    return;
  }
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes("light") === (modo === "light"),
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    onchange: null,
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
  sistemaPrefere("dark");
});

describe("ThemeProvider — o que vale na primeira visita", () => {
  it("sem nada salvo, segue o sistema operacional no claro", () => {
    sistemaPrefere("light");

    renderComProvider();

    expect(screen.getByTestId("tema")).toHaveTextContent("light");
    expect(document.documentElement).not.toHaveClass("dark");
  });

  it("sem nada salvo, segue o sistema operacional no escuro", () => {
    sistemaPrefere("dark");

    renderComProvider();

    expect(screen.getByTestId("tema")).toHaveTextContent("dark");
    expect(document.documentElement).toHaveClass("dark");
  });

  it("valor salvo estragado não conta como escolha — vale o sistema", () => {
    // Chave escrita por uma versão antiga, ou mexida na mão pelo DevTools.
    sistemaPrefere("light");
    localStorage.setItem(CHAVE, "solarized");

    renderComProvider();

    expect(screen.getByTestId("tema")).toHaveTextContent("light");
  });

  it("sem matchMedia no ambiente, cai no escuro", () => {
    // Navegador antigo, ou renderização fora do browser: não dá para perguntar
    // a preferência, e o escuro é o visual de casa do HelpHS.
    sistemaPrefere("sem-suporte");

    renderComProvider();

    expect(screen.getByTestId("tema")).toHaveTextContent("dark");
  });

  it("não grava nada antes de o usuário escolher", () => {
    // Gravar na montagem congelaria o valor do SO daquele dia: quem trocasse o
    // tema do sistema depois nunca mais veria a mudança refletida, e "seguir o
    // sistema" valeria por uma visita só.
    sistemaPrefere("light");

    renderComProvider();

    expect(localStorage.getItem(CHAVE)).toBeNull();
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

  it("a escolha salva manda contra o sistema — nos dois sentidos", () => {
    // O SO é o palpite inicial, não uma ordem: quem já escolheu não é
    // sobrescrito por causa do relógio do computador virando a noite.
    sistemaPrefere("dark");
    localStorage.setItem(CHAVE, "light");
    const claro = renderComProvider();
    expect(screen.getByTestId("tema")).toHaveTextContent("light");
    claro.unmount();

    sistemaPrefere("light");
    localStorage.setItem(CHAVE, "dark");
    renderComProvider();

    expect(screen.getByTestId("tema")).toHaveTextContent("dark");
  });

  it("alternar grava a escolha nova", async () => {
    renderComProvider();

    await userEvent.click(screen.getByRole("button", { name: "Alternar" }));

    expect(screen.getByTestId("tema")).toHaveTextContent("light");
    expect(localStorage.getItem(CHAVE)).toBe("light");
  });

  it("o que foi gravado é o que a próxima montagem lê", async () => {
    // Este é o teste que fecha o ciclo: escolher, sair, voltar. O SO fica no
    // escuro de propósito — se a escolha não fosse gravada, a volta cairia
    // nele e o teste passaria pelo motivo errado.
    sistemaPrefere("dark");
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
