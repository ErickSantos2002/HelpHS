import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ErrorBoundary, ProtecaoDaRaiz } from "../../components/ErrorBoundary";

/**
 * Sem ErrorBoundary, qualquer erro de renderização apagava a aplicação inteira:
 * tela em branco, e o que a pessoa tinha digitado ia junto (auditoria F1-B-02).
 * A barreira não trata erro HTTP — esses têm mensagem própria pelo
 * `getApiError`; ela é a última rede para o que escapou.
 */

const SEGREDO = "detalhe-interno-que-nao-aparece";

let quebra = true;
function Instavel() {
  if (quebra) throw new Error(SEGREDO);
  return <p>conteúdo recuperado</p>;
}

let consoleError: ReturnType<typeof vi.spyOn>;
const locationMock = { reload: vi.fn(), href: "" };

beforeEach(() => {
  quebra = true;
  // O React também reclama no console de todo erro capturado: silenciado aqui
  // para a saída do teste não virar ruído, e lido para provar o registro.
  consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  locationMock.reload.mockClear();
  Object.defineProperty(window, "location", {
    value: locationMock,
    writable: true,
    configurable: true,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ErrorBoundary", () => {
  it("sem erro, desenha os filhos e nada mais", () => {
    quebra = false;
    render(
      <ErrorBoundary>
        <Instavel />
      </ErrorBoundary>,
    );
    expect(screen.getByText("conteúdo recuperado")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("um erro de renderização vira uma tela compreensível, não um branco", () => {
    render(
      <ErrorBoundary>
        <Instavel />
      </ErrorBoundary>,
    );
    const aviso = screen.getByRole("alert");
    expect(aviso).toHaveTextContent("Algo deu errado nesta tela");
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recarregar a página" })).toBeInTheDocument();
  });

  it("não mostra a mensagem do erro nem a pilha para a pessoa", () => {
    const { container } = render(
      <ErrorBoundary>
        <Instavel />
      </ErrorBoundary>,
    );
    expect(container.textContent).not.toContain(SEGREDO);
    expect(container.textContent).not.toMatch(/at \w+ \(|Error:|componentStack/);
  });

  it("registra o erro no console do navegador, para diagnóstico", () => {
    render(
      <ErrorBoundary>
        <Instavel />
      </ErrorBoundary>,
    );
    const registro = consoleError.mock.calls.find((args: unknown[]) => args[0] === "[ErrorBoundary]");
    expect(registro).toBeDefined();
    expect(String(registro?.[1])).toContain(SEGREDO);
  });

  it("Tentar novamente redesenha os filhos quando a causa passou", async () => {
    render(
      <ErrorBoundary>
        <Instavel />
      </ErrorBoundary>,
    );
    quebra = false;
    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(screen.getByText("conteúdo recuperado")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("se o erro persiste, a tela de aviso volta — sem laço e sem branco", async () => {
    render(
      <ErrorBoundary>
        <Instavel />
      </ErrorBoundary>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("Recarregar a página recarrega de verdade", async () => {
    render(
      <ErrorBoundary>
        <Instavel />
      </ErrorBoundary>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Recarregar a página" }));
    expect(locationMock.reload).toHaveBeenCalledTimes(1);
  });

  it("mudar a chave de reinício limpa o erro", () => {
    const { rerender } = render(
      <ErrorBoundary chaveDeReinicio="/a">
        <Instavel />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();

    quebra = false;
    rerender(
      <ErrorBoundary chaveDeReinicio="/b">
        <Instavel />
      </ErrorBoundary>,
    );
    expect(screen.getByText("conteúdo recuperado")).toBeInTheDocument();
  });
});

describe("ProtecaoDaRaiz", () => {
  it("Ir para o início sai da tela quebrada e a aplicação segue funcionando", async () => {
    render(
      <MemoryRouter initialEntries={["/quebrada"]}>
        <ProtecaoDaRaiz>
          <Routes>
            <Route path="/quebrada" element={<Instavel />} />
            <Route path="/" element={<p>início</p>} />
          </Routes>
        </ProtecaoDaRaiz>
      </MemoryRouter>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Ir para o início" }));

    expect(screen.getByText("início")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("a raiz da aplicação passa pela proteção", () => {
    const main = readFileSync(resolve(process.cwd(), "src/main.tsx"), "utf-8");
    expect(main).toMatch(/<ProtecaoDaRaiz>\s*<App \/>\s*<\/ProtecaoDaRaiz>/);
  });
});
