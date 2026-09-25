// @vitest-environment jsdom
// Mesma razão do PoliticaPrivacidadePage.test.tsx: o `renderMarkdown` passa
// por DOMPurify, que sob o happy-dom não devolve HTML utilizável.
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import TermosDeUsoPage from "../../pages/legal/TermosDeUsoPage";

/**
 * Os Termos de Uso, com o texto real do arquivo versionado — o PGS-TI-032,
 * aprovado pela qualidade em 25/09/2026. Enquanto era rascunho, os marcadores
 * mantinham o aviso de "documento em elaboração"; aprovado, o aviso sai.
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

  it("aprovado, não mostra o aviso de rascunho", () => {
    monta();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("identifica o documento pelo código do Sistema de Gestão", () => {
    monta();
    expect(screen.getByText(/PGS-TI-032/)).toBeInTheDocument();
  });

  it("tem o Voltar das páginas legais", () => {
    monta();
    expect(screen.getByRole("button", { name: "Voltar" })).toBeInTheDocument();
  });
});
