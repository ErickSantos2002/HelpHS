// @vitest-environment jsdom
// Mesma razão do markdown.test.ts: o `renderMarkdown` passa por DOMPurify, que
// sob o happy-dom padrão do projeto não devolve HTML utilizável. Sem jsdom a
// página renderiza vazia e os testes de conteúdo não provariam nada.
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { contemMarcadorPendente } from "../../pages/legal/marcadorPendente";

/**
 * A Política de Privacidade é renderizada a partir de um markdown versionado.
 * Enquanto a qualidade não fecha o texto, ele contém marcadores do tipo
 * `[validar prazos de retenção]` — trechos ainda em definição.
 *
 * O risco que estes testes cobrem: essa página é linkada da tela de cadastro,
 * ao lado da caixa que a pessoa marca declarando ter lido. Publicar com um
 * marcador aberto significaria pedir aceite de um texto jurídico incompleto.
 * O aviso de "documento em elaboração" é o que impede isso, e ele depende
 * inteiramente da detecção abaixo estar correta.
 */
describe("contemMarcadorPendente", () => {
  // Os seis formatos que existem de verdade no documento hoje. Não são
  // exemplos inventados: cada um foi tirado do texto da revisão 00.
  it.each([
    "Os prazos devem ser confirmados: [validar prazos de retenção].",
    "prevista para [definir data de implantação da rotina de expurgo].",
    "A plataforma [confirmar: utiliza / não utiliza] cookies de análise.",
    "Encarregado (DPO): [nome do Encarregado]",
    "Contato: [e-mail do Encarregado]",
    "Endereço: [endereço completo da sede – rua, número, cidade/UF, CEP]",
  ])("reconhece o marcador em %s", (trecho) => {
    expect(contemMarcadorPendente(trecho)).toBe(true);
  });

  it("não acusa marcador em texto já fechado", () => {
    const fechado =
      "Os dados serão eliminados ao término do prazo de retenção, " +
      "ressalvadas as hipóteses do art. 16 da LGPD.";
    expect(contemMarcadorPendente(fechado)).toBe(false);
  });

  it("não confunde link markdown com marcador pendente", () => {
    // `[texto](url)` é link, não lacuna. Sem essa distinção, uma revisão
    // futura que linkasse "Confirmar cadastro" deixaria o aviso de rascunho
    // preso na tela — e aviso que nunca sai deixa de ser lido.
    expect(
      contemMarcadorPendente("[Confirmar na ANPD](https://www.gov.br/anpd)"),
    ).toBe(false);
  });

  it("não confunde colchete comum com marcador pendente", () => {
    // Referência legal entre colchetes é escrita corrente num documento
    // jurídico. Se a detecção pegasse qualquer `[...]`, o aviso de rascunho
    // ficaria para sempre na tela e deixaria de significar alguma coisa.
    expect(contemMarcadorPendente("conforme o art. 33 [II, a] da LGPD")).toBe(
      false,
    );
  });
});

describe("PoliticaPrivacidadePage", () => {
  afterEach(() => {
    vi.resetModules();
    vi.doUnmock("../../content/politica-privacidade.md?raw");
  });

  async function renderizaCom(conteudo: string) {
    vi.resetModules();
    vi.doMock("../../content/politica-privacidade.md?raw", () => ({
      default: conteudo,
    }));
    const { default: Pagina } = await import(
      "../../pages/legal/PoliticaPrivacidadePage"
    );
    render(
      <MemoryRouter>
        <Pagina />
      </MemoryRouter>,
    );
  }

  it("avisa que é rascunho enquanto houver marcador em aberto", async () => {
    await renderizaCom(
      "# Política\n\nOs prazos: [validar prazos de retenção].",
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      /documento em elaboração/i,
    );
  });

  it("não mostra o aviso quando o texto está fechado", async () => {
    await renderizaCom("# Política\n\nOs dados serão eliminados no prazo.");

    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("renderiza o texto do documento, incluindo tabelas", async () => {
    await renderizaCom(
      "# Política de Privacidade\n\n" +
        "## 13. Retenção\n\n" +
        "| Dados | Prazo |\n|---|---|\n| Registro de aceite | 5 anos |\n",
    );

    expect(
      screen.getByRole("heading", { name: /Política de Privacidade/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Registro de aceite" })).
      toBeInTheDocument();
  });
});
