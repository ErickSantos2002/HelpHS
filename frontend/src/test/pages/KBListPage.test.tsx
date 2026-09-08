import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

/**
 * O que esta tela tinha, e o que estes casos prendem.
 *
 * **Dois mapas locais e uma terceira lista escrita à mão.** `CATEGORY_LABEL`
 * traduzia o valor cru de volta para o rótulo, e as oito opções do filtro de
 * categoria estavam repetidas dentro do JSX — duas cópias das categorias na
 * mesma tela. As duas saem para `lib/categoria.ts`.
 *
 * **Três hexadecimais cravados** nas amostras do filtro de status, e um mapa de
 * status do artigo sem disciplina nenhuma (rótulo de um lado, classes de outro,
 * opções do filtro de um terceiro).
 *
 * **E uma lista inteira que o teclado não alcançava**: a linha era um `<div>`
 * com `onClick`, e o título era um `<span>` que só *parecia* link. Quem navega
 * sem mouse não conseguia abrir artigo nenhum a partir desta página.
 *
 * Nenhum caso aqui olha classe: o happy-dom não aplica CSS, e um mutante de
 * classe sobrevive por um motivo que não tem nada a ver com o que o caso mede.
 */

/** A sessão, trocável por caso — a tela mostra coisas diferentes por papel. */
let sessao: { id: string; role: string; name: string } = {
  id: "u1",
  role: "admin",
  name: "Admin",
};

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: sessao }),
}));
vi.mock("../../services/kbService", () => ({
  getKBArticles: vi.fn(),
  deleteKBArticle: vi.fn(),
}));
vi.mock("../../services/productService", () => ({
  getProducts: vi.fn(),
}));

import { MemoryRouter } from "react-router-dom";
import KBListPage from "../../pages/kb/KBListPage";
import * as kbService from "../../services/kbService";
import * as productService from "../../services/productService";

const ARTIGO = {
  id: "a1",
  title: "Como trocar o toner",
  content: "## Passo 1\nAbra a **tampa**.",
  slug: "como-trocar-o-toner",
  // "network" e não "hardware" de propósito: o rótulo ("Rede") não se parece
  // com o valor cru, então trocar o módulo pelo valor aparece na tela.
  category: "network",
  tags: ["toner", "impressora"],
  status: "draft",
  author_id: "u9",
  author_name: "Maria Souza",
  view_count: 12,
  helpful: 3,
  not_helpful: 1,
  created_at: "2026-09-01T12:00:00Z",
  updated_at: "2026-09-02T12:00:00Z",
  products: [{ id: "p1", name: "Impressora HS-1" }],
} as unknown as Awaited<
  ReturnType<typeof kbService.getKBArticles>
>["items"][number];

type OpcoesDeMontagem = {
  artigos?: (typeof ARTIGO)[];
  total?: number;
  papel?: string;
};

async function montar({
  artigos = [ARTIGO],
  total = artigos.length,
  papel = "admin",
}: OpcoesDeMontagem = {}) {
  sessao = { id: "u1", role: papel, name: "Fulano" };

  vi.mocked(kbService.getKBArticles).mockResolvedValue({
    items: artigos,
    total,
    limit: 20,
    offset: 0,
  } as never);
  vi.mocked(productService.getProducts).mockResolvedValue({
    items: [{ id: "p1", name: "Impressora HS-1" }],
    total: 1,
  } as never);

  render(
    <MemoryRouter initialEntries={["/kb"]}>
      <KBListPage />
    </MemoryRouter>,
  );

  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "Base de Conhecimento" }),
    ).toBeInTheDocument(),
  );
  // A lista só existe depois que a promessa do serviço resolve.
  await waitFor(() =>
    expect(kbService.getKBArticles).toHaveBeenCalled(),
  );
}

describe("KBListPage", () => {
  beforeEach(() => vi.clearAllMocks());

  // ── As fontes únicas ────────────────────────────────────────

  it("a categoria do artigo sai do módulo: «Rede», e não «network»", async () => {
    await montar();

    expect(await screen.findByText("Rede")).toBeInTheDocument();
    expect(screen.queryByText("network")).not.toBeInTheDocument();
  });

  it("as opções do filtro de categoria saem do módulo, e não da cópia do JSX", async () => {
    const user = userEvent.setup();
    await montar();

    await user.click(
      screen.getByRole("button", { name: "Todas as categorias" }),
    );

    // As oito de `CATEGORIAS`, conferidas nas pontas da lista.
    expect(screen.getByRole("option", { name: /Hardware/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Segurança/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Outro/ })).toBeInTheDocument();
  });

  it("o selo de status diz o rótulo da tabela, e o filtro repete os mesmos três", async () => {
    const user = userEvent.setup();
    await montar();

    // Na linha do artigo.
    expect(await screen.findByText("Rascunho")).toBeInTheDocument();

    // E no filtro, DERIVADO da mesma tabela — não escrito ao lado dela.
    await user.click(screen.getByRole("button", { name: "Todos os status" }));
    expect(screen.getByRole("option", { name: /Publicado/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Rascunho/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Arquivado/ })).toBeInTheDocument();
  });

  // ── O que cada papel vê ─────────────────────────────────────

  it("cliente não vê status, nem filtro de status, nem «Novo artigo»", async () => {
    await montar({ papel: "client" });

    expect(await screen.findByText("Rede")).toBeInTheDocument();
    expect(screen.queryByText("Rascunho")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Todos os status" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Novo artigo/ }),
    ).not.toBeInTheDocument();
  });

  it("técnico edita mas não exclui: excluir é só do admin", async () => {
    await montar({ papel: "technician" });

    expect(
      await screen.findByRole("link", { name: "Editar Como trocar o toner" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Excluir Como trocar o toner" }),
    ).not.toBeInTheDocument();
  });

  // ── Navegação é link ────────────────────────────────────────

  it("«Novo artigo» é um LINK para /kb/new, e não um botão", async () => {
    await montar();

    expect(screen.getByRole("link", { name: /Novo artigo/ })).toHaveAttribute(
      "href",
      "/kb/new",
    );
    expect(
      screen.queryByRole("button", { name: /Novo artigo/ }),
    ).not.toBeInTheDocument();
  });

  it("o título do artigo é um link alcançável, e não um `span` que finge", async () => {
    // Antes, a única forma de abrir um artigo era clicar num `<div>` com
    // `onClick`: fora da ordem de tabulação e sem papel nenhum na árvore de
    // acessibilidade.
    await montar();

    expect(
      await screen.findByRole("link", { name: "Como trocar o toner" }),
    ).toHaveAttribute("href", "/kb/a1");
  });

  it("os controles da linha dizem de QUAL artigo são", async () => {
    // Numa lista de vinte linhas, vinte controles chamados "Editar" não dizem
    // qual dos vinte.
    await montar();

    expect(
      await screen.findByRole("link", { name: "Editar Como trocar o toner" }),
    ).toHaveAttribute("href", "/kb/a1/edit");
    expect(
      screen.getByRole("button", { name: "Excluir Como trocar o toner" }),
    ).toBeInTheDocument();
  });

  // ── Os números que ninguém ouvia ────────────────────────────

  it("os dois contadores dizem o que contam", async () => {
    // O `Icon` é `aria-hidden`: sem o texto invisível, um leitor de tela lia
    // "12" e "3" e mais nada.
    await montar();

    expect(await screen.findByText("visualizações")).toBeInTheDocument();
    expect(screen.getByText("votos de útil")).toBeInTheDocument();
  });

  it("o polegar da contagem de «útil» aponta para CIMA", async () => {
    // O `ICON_PATHS` é mapa de texto e todo texto cabe: trocar o nome do ícone
    // inverte o desenho na cara do usuário sem que `tsc`, ESLint ou teste de
    // componente digam nada. O `M14 10h4.764` é o punho embaixo à esquerda com
    // o dedão subindo; o polegar para baixo começa em `M10 14H5.236`.
    await montar();

    const uteis = (await screen.findByText("votos de útil")).parentElement;
    expect(uteis?.querySelector("path")?.getAttribute("d")).toMatch(
      /^M14 10h4\.764/,
    );
  });

  // ── Filtros ─────────────────────────────────────────────────

  it("o campo de busca tem nome próprio e o «x» o esvazia", async () => {
    const user = userEvent.setup();
    await montar();

    const campo = screen.getByRole("textbox", { name: "Buscar artigos" });
    await user.type(campo, "toner");

    await waitFor(() =>
      expect(kbService.getKBArticles).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: "toner" }),
      ),
    );

    await user.click(screen.getByRole("button", { name: "Limpar busca" }));
    expect(campo).toHaveValue("");
  });

  it("«Limpar» zera os QUATRO filtros de uma vez", async () => {
    const user = userEvent.setup();
    await montar();

    await user.type(
      screen.getByRole("textbox", { name: "Buscar artigos" }),
      "toner",
    );
    await user.click(screen.getByRole("button", { name: "Todos os status" }));
    await user.click(screen.getByRole("option", { name: /Publicado/ }));

    await waitFor(() =>
      expect(kbService.getKBArticles).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: "toner", status: "published" }),
      ),
    );

    await user.click(screen.getByRole("button", { name: /Limpar$/ }));

    await waitFor(() =>
      expect(kbService.getKBArticles).toHaveBeenLastCalledWith(
        expect.objectContaining({
          search: undefined,
          status: undefined,
          category: undefined,
          product_id: undefined,
        }),
      ),
    );
  });

  // ── Estado vazio ────────────────────────────────────────────

  it("sem artigo nenhum, a tela convida a criar o primeiro", async () => {
    await montar({ artigos: [], total: 0 });

    expect(
      await screen.findByText("Nenhum artigo encontrado."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "+ Criar primeiro artigo" }),
    ).toHaveAttribute("href", "/kb/new");
  });

  // ── Paginação ───────────────────────────────────────────────

  it("a paginação é uma região nomeada, e a página 2 pede o segundo lote", async () => {
    const user = userEvent.setup();
    await montar({ artigos: [ARTIGO], total: 45 });

    expect(
      screen.getByRole("navigation", { name: "Paginação" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "2" }));

    await waitFor(() =>
      expect(kbService.getKBArticles).toHaveBeenLastCalledWith(
        expect.objectContaining({ offset: 20 }),
      ),
    );
  });

  // ── Exclusão ────────────────────────────────────────────────

  it("excluir avisa, mostra o artigo e some com a linha", async () => {
    const user = userEvent.setup();
    vi.mocked(kbService.deleteKBArticle).mockResolvedValue(undefined as never);
    await montar();

    await user.click(
      await screen.findByRole("button", {
        name: "Excluir Como trocar o toner",
      }),
    );

    expect(await screen.findByText("Ação irreversível")).toBeInTheDocument();
    // A prévia fala pelos módulos: categoria pelo rótulo, status pela tabela.
    expect(screen.getByText(/Rede · Rascunho/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Sim, excluir" }));

    expect(kbService.deleteKBArticle).toHaveBeenCalledWith("a1");
    await waitFor(() =>
      expect(
        screen.queryByRole("link", { name: "Como trocar o toner" }),
      ).not.toBeInTheDocument(),
    );
  });
});
