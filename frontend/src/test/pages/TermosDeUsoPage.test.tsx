// @vitest-environment jsdom
// Mesma razão do PoliticaPrivacidadePage.test.tsx: o `renderMarkdown` passa
// por DOMPurify, que sob o happy-dom não devolve HTML utilizável.
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import TermosDeUsoPage from "../../pages/legal/TermosDeUsoPage";

/**
 * Os Termos de Uso, com o texto real do arquivo versionado. O rascunho de
 * 25/09 foi redigido pela TI e ainda depende da aprovação da qualidade — os
 * marcadores do cabeçalho e da tabela de revisão mantêm o aviso na tela até lá.
 */
describe("TermosDeUsoPage", () => {
  function monta() {
    render(
      <MemoryRouter>
        <TermosDeUsoPage />
      </MemoryRouter>,
    );
  }

  it("renderiza o documento", () => {
    monta();
    expect(
      screen.getByRole("heading", { level: 1, name: /Termos de Uso/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /Assistente Virtual Helô/i }),
    ).toBeInTheDocument();
  });

  it("avisa que é rascunho enquanto a qualidade não aprovar", () => {
    monta();
    expect(screen.getByRole("alert")).toHaveTextContent(/documento em elaboração/i);
  });

  it("tem o Voltar das páginas legais", () => {
    monta();
    expect(screen.getByRole("button", { name: "Voltar" })).toBeInTheDocument();
  });
});
