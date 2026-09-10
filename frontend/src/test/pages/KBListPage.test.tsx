import { render, screen, waitFor, within } from "@testing-library/react";
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
vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));
vi.mock("../../services/productService", () => ({
  getProducts: vi.fn(),
}));

import { MemoryRouter } from "react-router-dom";
import KBListPage from "../../pages/kb/KBListPage";
import * as kbService from "../../services/kbService";
import * as productService from "../../services/productService";
import { toast } from "sonner";
import { CATEGORIAS } from "../../lib/categoria";

/**
 * Dois dos três filtros da barra viraram `<select>` nativo pela D9.2, e o
 * `<select>` desenha TODAS as opções na árvore o tempo todo — o painel do
 * `FilterSelect` só existia enquanto aberto. "Rede" e "Rascunho" passam a
 * estar em dois lugares: a linha do artigo e a opção do filtro.
 *
 * Os casos que falam da LINHA tiram a opção da busca por `ignore`, e não por
 * `getAllByText(...)[0]` — este continuaria passando com o texto da linha
 * apagado, que é o que eles existem para reprovar.
 */
const FORA_DO_FILTRO = { ignore: "script, style, option" } as const;

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

    expect(await screen.findByText("Rede", FORA_DO_FILTRO)).toBeInTheDocument();
    // Nem na linha nem dentro do filtro: no `<option>` o valor cru é o
    // `value`, e nunca o texto.
    expect(screen.queryByText("network")).not.toBeInTheDocument();
  });

  it("as opções do filtro de categoria saem do módulo, e não da cópia do JSX", async () => {
    await montar();

    const filtro = screen.getByRole("combobox", { name: "Categoria" });
    const rotulos = within(filtro)
      .getAllByRole("option")
      .map((o) => o.textContent);

    // As oito de `CATEGORIAS`, mais a linha de "todas".
    expect(rotulos).toContain("Hardware");
    expect(rotulos).toContain("Segurança");
    expect(rotulos).toContain("Outro");
    expect(rotulos).toHaveLength(CATEGORIAS.length + 1);
  });

  it("o selo de status diz o rótulo da tabela, e o filtro repete os mesmos três", async () => {
    await montar();

    // Na linha do artigo.
    expect(
      await screen.findByText("Rascunho", FORA_DO_FILTRO),
    ).toBeInTheDocument();

    // E no filtro, DERIVADO da mesma tabela — não escrito ao lado dela.
    const filtro = screen.getByRole("combobox", { name: "Status do artigo" });
    const rotulos = within(filtro)
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(rotulos).toEqual([
      "Todos os status",
      "Publicado",
      "Rascunho",
      "Arquivado",
    ]);
  });

  it("cada um dos três filtros tem nome próprio, e não se anuncia pelo valor", async () => {
    // O defeito que a D9.2 fecha. O `FilterSelect` não repassava `label`, e
    // numa barra com TRÊS filtros os três se anunciavam pelo valor escolhido —
    // "Hardware", "Impressora HS-1", "Publicado" — sem dizer de que filtro
    // cada um era.
    //
    // Os dois curtos são `<select>` nativo e se leem por `combobox`; o de
    // produto é o `Selector`, cujo nome soma o rótulo ao valor visível, e por
    // isso é "Produto Todos os produtos" e não só "Produto".
    await montar();

    expect(screen.getByRole("combobox", { name: "Categoria" })).toBeInTheDocument();
    expect(
      screen.getByRole("combobox", { name: "Status do artigo" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Produto Todos os produtos" }),
    ).toBeInTheDocument();
  });

  it("escolher a categoria no filtro pede ao serviço aquela categoria", async () => {
    await montar();

    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "Categoria" }),
      "network",
    );

    await waitFor(() =>
      expect(kbService.getKBArticles).toHaveBeenLastCalledWith(
        expect.objectContaining({ category: "network" }),
      ),
    );
  });

  // ── O que cada papel vê ─────────────────────────────────────

  it("cliente não vê status, nem filtro de status, nem «Novo artigo»", async () => {
    await montar({ papel: "client" });

    expect(await screen.findByText("Rede", FORA_DO_FILTRO)).toBeInTheDocument();
    expect(screen.queryByText("Rascunho")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: "Status do artigo" }),
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
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Status do artigo" }),
      "published",
    );

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

    const dialogo = await screen.findByRole("dialog");
    // Pela D9.3 o `Alert` de aviso saiu e o "não volta" virou prosa. As duas
    // afirmações caem NO MESMO parágrafo: a prévia do artigo também escreve o
    // título, e contar ocorrências na tela deixaria passar uma frase muda.
    const frase = within(dialogo).getByText(/não pode ser desfeita/);
    expect(frase).toHaveTextContent("Como trocar o toner");
    // A prévia fala pelos módulos: categoria pelo rótulo, status pela tabela.
    expect(within(dialogo).getByText(/Rede · Rascunho/)).toBeInTheDocument();

    await user.click(within(dialogo).getByRole("button", { name: "Excluir" }));

    expect(kbService.deleteKBArticle).toHaveBeenCalledWith("a1");
    await waitFor(() =>
      expect(
        screen.queryByRole("link", { name: "Como trocar o toner" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("exclusão que FALHA mostra o erro, e não some com a linha", async () => {
    // O caminho de falha desta tela nunca teve dono: `handleDelete` só tinha
    // `try/finally`, então uma exclusão recusada fazia o botão parar de girar
    // e mais nada — nem toast, nem `Alert`, e o artigo seguia na lista sem
    // explicação. O caso prende as duas metades: o erro APARECE, e a lista
    // NÃO finge que a exclusão deu certo.
    const user = userEvent.setup();
    vi.mocked(kbService.deleteKBArticle).mockRejectedValue({
      response: { data: { detail: "Artigo vinculado a um chamado." } },
    });
    await montar();

    await user.click(
      await screen.findByRole("button", {
        name: "Excluir Como trocar o toner",
      }),
    );
    const dialogo = await screen.findByRole("dialog", { name: "Excluir artigo" });
    await user.click(within(dialogo).getByRole("button", { name: "Excluir" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Não foi possível excluir o artigo.",
        { description: "Artigo vinculado a um chamado." },
      ),
    );
    expect(
      screen.getByRole("link", { name: "Como trocar o toner" }),
    ).toBeInTheDocument();
  });

  it("o diálogo se anuncia nomeando o que será excluído", async () => {
    // O título do `Modal` é o NOME ACESSÍVEL do diálogo: o componente põe
    // `role="dialog"` com `aria-labelledby` apontando para o `<h2>` do título.
    // É a primeira coisa que o leitor de tela anuncia — e um título "Excluir"
    // seco deixaria quem não vê a tela sem saber o quê. O corpo também nomeia,
    // mas o corpo vem DEPOIS do nome, e só se a pessoa continuar.
    const user = userEvent.setup();
    await montar();

    await user.click(
      await screen.findByRole("button", {
        name: "Excluir Como trocar o toner",
      }),
    );

    expect(
      await screen.findByRole("dialog", { name: "Excluir artigo" }),
    ).toBeInTheDocument();
  });

  it("cancelar fecha o diálogo e o artigo continua na lista", async () => {
    const user = userEvent.setup();
    await montar();

    await user.click(
      await screen.findByRole("button", {
        name: "Excluir Como trocar o toner",
      }),
    );
    const dialogo = await screen.findByRole("dialog");
    await user.click(within(dialogo).getByRole("button", { name: "Cancelar" }));

    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(kbService.deleteKBArticle).not.toHaveBeenCalled();
    expect(
      screen.getByRole("link", { name: "Como trocar o toner" }),
    ).toBeInTheDocument();
  });
});
