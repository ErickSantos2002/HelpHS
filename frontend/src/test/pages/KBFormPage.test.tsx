import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1", role: "admin", name: "Admin" } }),
}));
vi.mock("../../services/kbService", () => ({
  getKBArticle: vi.fn(),
  createKBArticle: vi.fn(),
  updateKBArticle: vi.fn(),
}));
vi.mock("../../services/productService", () => ({
  getProducts: vi.fn(),
}));
vi.mock("../../lib/toastError", () => ({ toastApiError: vi.fn() }));

import { MemoryRouter, Route, Routes } from "react-router-dom";
import KBFormPage from "../../pages/kb/KBFormPage";
import * as kbService from "../../services/kbService";
import * as productService from "../../services/productService";

/**
 * O que esta tela tinha, e o que estes casos prendem.
 *
 * **Dois mapas locais.** `CATEGORIES` era a quinta cópia das categorias;
 * `STATUS_OPTIONS`/`STATUS_CONFIG` carregavam os três hexadecimais do ponto de
 * estado.
 *
 * **E, sobretudo, seis rótulos que não pertenciam a campo nenhum**: dois
 * `<select>` sem `id`, o "Conteúdo", o "Tags" e um `<label>` posto sobre um
 * GRUPO de controles. Numa tela de FORMULÁRIO isso é o defeito principal —
 * quem navega por leitor de tela ouvia "caixa de combinação" e "campo de
 * edição", sem saber de quê.
 *
 * Nenhum caso olha classe: o happy-dom não aplica CSS nenhum, e um mutante de
 * classe sobrevive por um motivo que não tem nada a ver com o que o caso mede.
 */
const ARTIGO = {
  id: "a1",
  title: "Como trocar o toner",
  content: "Passo 1. Abra a tampa.",
  slug: "como-trocar-o-toner",
  category: "hardware",
  tags: ["toner", "impressora"],
  status: "published",
  author_id: "u9",
  author_name: "Maria Souza",
  view_count: 12,
  helpful: 3,
  not_helpful: 1,
  created_at: "2026-09-01T12:00:00Z",
  updated_at: "2026-09-02T12:00:00Z",
  products: [],
} as unknown as Awaited<ReturnType<typeof kbService.getKBArticle>>;

const PRODUTOS = [
  { id: "p1", name: "Impressora HS-1", active: true },
  { id: "p2", name: "Notebook HS-9", active: true },
] as unknown as Awaited<ReturnType<typeof productService.getProducts>>["items"];

/** A tela de CRIAÇÃO — sem `:id` na rota, nenhum artigo é buscado. */
async function montarNovo() {
  vi.mocked(productService.getProducts).mockResolvedValue({
    items: PRODUTOS,
    total: PRODUTOS.length,
  } as never);

  render(
    <MemoryRouter initialEntries={["/kb/novo"]}>
      <Routes>
        <Route path="/kb/novo" element={<KBFormPage />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByRole("heading", { name: "Novo artigo" });
}

/** A tela de EDIÇÃO — com `:id`, e o artigo já carregado. */
async function montarEdicao() {
  vi.mocked(productService.getProducts).mockResolvedValue({
    items: PRODUTOS,
    total: PRODUTOS.length,
  } as never);
  vi.mocked(kbService.getKBArticle).mockResolvedValue(ARTIGO as never);

  render(
    <MemoryRouter initialEntries={["/kb/a1/edit"]}>
      <Routes>
        <Route path="/kb/:id/edit" element={<KBFormPage />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByRole("heading", { name: "Editar artigo" });
}

describe("KBFormPage", () => {
  beforeEach(() => vi.clearAllMocks());

  // ── Os rótulos que não pertenciam a campo nenhum ────────────

  it("os dois seletores têm nome próprio, e não só um texto ao lado", async () => {
    // Eram `<select>` sem `id` sob `<label>` sem `htmlFor`. Buscar por PAPEL e
    // NOME é o que um leitor de tela faz — se a ligação sumir, some o campo.
    await montarNovo();

    expect(
      screen.getByRole("combobox", { name: "Categoria" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Status" })).toBeInTheDocument();
  });

  it("os três campos de texto têm nome próprio", async () => {
    await montarNovo();

    expect(
      screen.getByRole("textbox", { name: "Título *" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: /^Conteúdo/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: /^Tags/ }),
    ).toBeInTheDocument();
  });

  it("a ajuda de Markdown descreve o campo, e não fica solta ao lado dele", async () => {
    // Era um `<p>` irmão do campo: junto na tela, sem relação nenhuma na
    // árvore de acessibilidade.
    await montarNovo();

    expect(
      screen.getByRole("textbox", { name: /^Conteúdo/ }),
    ).toHaveAccessibleDescription(/Suporta Markdown/);
  });

  // ── Produtos: um GRUPO, e não um campo ──────────────────────

  it("os produtos são um grupo com nome, e não um rótulo solto", async () => {
    // `<label>` nomeia UM campo. O que nomeia um conjunto de controles é
    // `<legend>` dentro de `<fieldset>` — e é isso que vira `role="group"`.
    await montarNovo();

    expect(
      screen.getByRole("group", { name: /Produtos/ }),
    ).toBeInTheDocument();
  });

  it("o erro dos produtos chega ao grupo, e não só à tela", async () => {
    const user = userEvent.setup();
    await montarNovo();

    await user.click(
      screen.getByRole("checkbox", { name: /Vale para todos os produtos/ }),
    );
    await user.type(
      screen.getByRole("textbox", { name: "Título *" }),
      "Título qualquer",
    );
    await user.type(
      screen.getByRole("textbox", { name: /^Conteúdo/ }),
      "Corpo qualquer",
    );
    await user.click(screen.getByRole("button", { name: "Criar artigo" }));

    expect(kbService.createKBArticle).not.toHaveBeenCalled();
    expect(
      screen.getByRole("group", { name: /Produtos/ }),
    ).toHaveAccessibleDescription(/Selecione ao menos um produto/);
  });

  it("o produto escolhido fica anunciado, e vai no que a tela envia", async () => {
    const user = userEvent.setup();
    await montarNovo();

    await user.click(
      screen.getByRole("checkbox", { name: /Vale para todos os produtos/ }),
    );

    const chip = await screen.findByRole("button", { name: /Impressora HS-1/ });
    expect(chip).toHaveAttribute("aria-pressed", "false");
    await user.click(chip);
    expect(
      screen.getByRole("button", { name: /Impressora HS-1/ }),
    ).toHaveAttribute("aria-pressed", "true");

    await user.type(
      screen.getByRole("textbox", { name: "Título *" }),
      "Trocar o toner",
    );
    await user.type(
      screen.getByRole("textbox", { name: /^Conteúdo/ }),
      "Abra a tampa.",
    );
    vi.mocked(kbService.createKBArticle).mockResolvedValue({
      id: "novo",
    } as never);
    await user.click(screen.getByRole("button", { name: "Criar artigo" }));

    await waitFor(() =>
      expect(kbService.createKBArticle).toHaveBeenCalledWith(
        expect.objectContaining({ product_ids: ["p1"] }),
      ),
    );
  });

  it("«todos os produtos» envia lista vazia, que é como o backend diz «todos»", async () => {
    const user = userEvent.setup();
    await montarNovo();

    await user.type(
      screen.getByRole("textbox", { name: "Título *" }),
      "Vale para tudo",
    );
    await user.type(
      screen.getByRole("textbox", { name: /^Conteúdo/ }),
      "Corpo.",
    );
    vi.mocked(kbService.createKBArticle).mockResolvedValue({
      id: "novo",
    } as never);
    await user.click(screen.getByRole("button", { name: "Criar artigo" }));

    await waitFor(() =>
      expect(kbService.createKBArticle).toHaveBeenCalledWith(
        expect.objectContaining({ product_ids: [] }),
      ),
    );
  });

  // ── As fontes únicas ────────────────────────────────────────

  it("a categoria sai do módulo: as oito, com o rótulo do módulo", async () => {
    await montarNovo();

    const seletor = screen.getByRole("combobox", { name: "Categoria" });
    expect(
      within(seletor)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual([
      "Hardware",
      "Software",
      "Rede",
      "Acesso",
      "E-mail",
      "Segurança",
      "Geral",
      "Outro",
    ]);
  });

  it("o resumo mostra o RÓTULO da categoria, e não o valor cru", async () => {
    // O artigo carregado vem com `category: "hardware"`; o painel lateral tem
    // de dizer "Hardware".
    await montarEdicao();

    const resumo = screen.getByText("Resumo").closest("div");
    expect(within(resumo as HTMLElement).getByText("Hardware")).toBeInTheDocument();
    expect(screen.queryByText("hardware")).not.toBeInTheDocument();
  });

  it("o resumo mostra o estado do artigo pelo rótulo, e acompanha o seletor", async () => {
    const user = userEvent.setup();
    await montarEdicao();

    // Escopado ao cartão: as três `<option>` do seletor de Status carregam
    // exatamente os mesmos três rótulos, e uma busca solta acharia as duas.
    const resumo = () => screen.getByText("Resumo").closest("div") as HTMLElement;

    // O artigo chega publicado.
    expect(within(resumo()).getByText("Publicado")).toBeInTheDocument();

    await user.selectOptions(
      screen.getByRole("combobox", { name: "Status" }),
      "archived",
    );
    expect(within(resumo()).getByText("Arquivado")).toBeInTheDocument();
    expect(within(resumo()).queryByText("Publicado")).not.toBeInTheDocument();
  });

  // ── Navegação ───────────────────────────────────────────────

  it("a trilha são dois links com destinos diferentes, e não um controle só", async () => {
    // Era UM botão com "Base de Conhecimento / <título>" dentro: as duas
    // páginas no mesmo nome acessível, e as duas indo para o MESMO lugar.
    await montarEdicao();

    expect(
      screen.getByRole("link", { name: "Base de Conhecimento" }),
    ).toHaveAttribute("href", "/kb");
    expect(
      screen.getByRole("link", { name: "Como trocar o toner" }),
    ).toHaveAttribute("href", "/kb/a1");
  });

  it("«Cancelar» é um LINK para a página de onde se veio", async () => {
    await montarEdicao();

    expect(screen.getByRole("link", { name: "Cancelar" })).toHaveAttribute(
      "href",
      "/kb/a1",
    );
  });

  // ── A pré-visualização ──────────────────────────────────────

  it("a aba aberta fica anunciada, e não só pintada", async () => {
    const user = userEvent.setup();
    await montarNovo();

    expect(screen.getByRole("button", { name: /Editar/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    await user.click(screen.getByRole("button", { name: /Preview/ }));

    expect(screen.getByRole("button", { name: /Preview/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /Editar/ })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("sem conteúdo, a pré-visualização avisa em vez de ficar vazia", async () => {
    const user = userEvent.setup();
    await montarNovo();

    await user.click(screen.getByRole("button", { name: /Preview/ }));

    expect(
      screen.getByText("Nada para pré-visualizar ainda…"),
    ).toBeInTheDocument();
  });

  it("com conteúdo, a pré-visualização mostra o artigo em vez do aviso", async () => {
    const user = userEvent.setup();
    await montarNovo();

    await user.type(
      screen.getByRole("textbox", { name: /^Conteúdo/ }),
      "Abra a tampa.",
    );
    await user.click(screen.getByRole("button", { name: /Preview/ }));

    // O caso afirma o RAMO — texto do artigo no lugar do aviso —, e não a
    // marcação gerada: neste ambiente de teste o `DOMPurify` sobre o DOM do
    // happy-dom devolve o markdown já sem as tags (`## Um título` volta como
    // `"Um título\n"`), então um `getByRole("heading")` reprovaria por causa
    // do sanitizador e não por causa da tela.
    expect(screen.getByText("Abra a tampa.")).toBeInTheDocument();
    expect(
      screen.queryByText("Nada para pré-visualizar ainda…"),
    ).not.toBeInTheDocument();
  });
});
