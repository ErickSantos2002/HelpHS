import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1", role: "admin", name: "Admin" } }),
}));
vi.mock("../../services/kbService", () => ({
  getKBArticle: vi.fn(),
  getKBComments: vi.fn(),
  createKBComment: vi.fn(),
  deleteKBComment: vi.fn(),
  submitKBFeedback: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { MemoryRouter, Route, Routes } from "react-router-dom";
import KBArticlePage from "../../pages/kb/KBArticlePage";
import * as kbService from "../../services/kbService";
import { toast } from "sonner";

/**
 * O que esta tela tinha, e o que estes casos prendem.
 *
 * **Três mapas locais.** `CATEGORY_LABEL` era a quarta cópia das categorias;
 * `ROLE_LABEL` e `ROLE_COLOR` eram a sexta do papel — e a sexta era a que
 * divergia no texto que o usuário lê: dizia "Admin" onde as outras cinco dizem
 * "Administrador".
 *
 * **Uma trilha vestida de botão**, com a página de onde se vem e a página onde
 * se está dentro do mesmo controle, e **um botão de enviar sem nome nenhum** —
 * dentro dele só havia um `<svg>`.
 *
 * **E o voto de utilidade**, que é o comportamento próprio desta tela e o
 * único que nenhuma outra tem: uma escolha única, irreversível, que soma no
 * contador da hora sem recarregar o artigo.
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
  products: [{ id: "p1", name: "Impressora HS-1" }],
} as unknown as Awaited<ReturnType<typeof kbService.getKBArticle>>;

const COMENTARIO = {
  id: "c1",
  article_id: "a1",
  author_id: "u2",
  author_name: "Ana Lima",
  author_role: "admin",
  content: "Funcionou aqui.",
  parent_id: null,
  created_at: "2026-09-03T12:00:00Z",
  updated_at: "2026-09-03T12:00:00Z",
  replies: [],
} as unknown as Awaited<ReturnType<typeof kbService.getKBComments>>[number];

async function montar(comentarios = [COMENTARIO]) {
  vi.mocked(kbService.getKBArticle).mockResolvedValue(ARTIGO as never);
  vi.mocked(kbService.getKBComments).mockResolvedValue(comentarios as never);
  vi.mocked(kbService.submitKBFeedback).mockResolvedValue(undefined as never);

  render(
    <MemoryRouter initialEntries={["/kb/a1"]}>
      <Routes>
        <Route path="/kb/:id" element={<KBArticlePage />} />
      </Routes>
    </MemoryRouter>,
  );
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "Como trocar o toner" }),
    ).toBeInTheDocument(),
  );
}

describe("KBArticlePage", () => {
  beforeEach(() => vi.clearAllMocks());

  // ── O voto de utilidade ─────────────────────────────────────

  it("votar «Sim» manda `helpful: true` e soma no contador da tela", async () => {
    const user = userEvent.setup();
    await montar();

    expect(
      screen.getByRole("button", { name: /Sim \(3\)/ }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Sim \(3\)/ }));

    expect(kbService.submitKBFeedback).toHaveBeenCalledWith("a1", true);
    await screen.findByRole("button", { name: /Sim \(4\)/ });
    // O outro contador não se mexe: um voto é um voto só.
    expect(screen.getByRole("button", { name: /Não \(1\)/ })).toBeInTheDocument();
  });

  it("votar «Não» manda `helpful: false` e soma no contador do «Não»", async () => {
    const user = userEvent.setup();
    await montar();

    await user.click(screen.getByRole("button", { name: /Não \(1\)/ }));

    expect(kbService.submitKBFeedback).toHaveBeenCalledWith("a1", false);
    await screen.findByRole("button", { name: /Não \(2\)/ });
    expect(screen.getByRole("button", { name: /Sim \(3\)/ })).toBeInTheDocument();
  });

  it("o voto é único: depois de votar os dois botões param de aceitar clique", async () => {
    const user = userEvent.setup();
    await montar();

    await user.click(screen.getByRole("button", { name: /Sim \(3\)/ }));
    await screen.findByText("Obrigado pelo feedback!");

    // Os dois, e não só o clicado — a escolha acabou, não a metade dela.
    expect(screen.getByRole("button", { name: /Sim \(4\)/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Não \(1\)/ })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /Não \(1\)/ }));
    expect(kbService.submitKBFeedback).toHaveBeenCalledTimes(1);
  });

  it("o voto dado fica anunciado, e não só pintado", async () => {
    const user = userEvent.setup();
    await montar();

    // Antes de votar nenhum dos dois está pressionado.
    expect(screen.getByRole("button", { name: /Sim \(3\)/ })).toHaveAttribute(
      "aria-pressed",
      "false",
    );

    await user.click(screen.getByRole("button", { name: /Sim \(3\)/ }));

    expect(screen.getByRole("button", { name: /Sim \(4\)/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /Não \(1\)/ })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("o polegar do «Sim» aponta para CIMA", async () => {
    // Este caso existe por causa de um defeito do pacote, não da tela: a E21
    // guardou o traçado do polegar para cima sob o nome `thumbsDown` e o de
    // baixo sob `thumbsUp`. A tela casa pelo TRAÇADO, e é o traçado que este
    // caso confere — trocar as chamadas pelos nomes "certos" inverteria o
    // desenho na cara do usuário sem que `tsc` ou ESLint dissessem nada.
    //
    // O `M14 10h4.764` é o punho embaixo à esquerda com o dedão subindo até
    // y=3; o polegar para baixo começa em `M10 14H5.236`.
    await montar();

    const sim = screen.getByRole("button", { name: /Sim \(3\)/ });
    expect(sim.querySelector("path")?.getAttribute("d")).toMatch(
      /^M14 10h4\.764/,
    );

    const nao = screen.getByRole("button", { name: /Não \(1\)/ });
    expect(nao.querySelector("path")?.getAttribute("d")).toMatch(
      /^M10 14H5\.236/,
    );
  });

  // ── Navegação ───────────────────────────────────────────────

  it("a trilha é um link para a base, e o título do artigo não finge ser clicável", async () => {
    await montar();

    expect(
      screen.getByRole("link", { name: "Base de Conhecimento" }),
    ).toHaveAttribute("href", "/kb");
    // O título aparece no `h1` e na trilha; em nenhum dos dois é controle.
    expect(
      screen.queryByRole("link", { name: /Como trocar o toner/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Como trocar o toner/ }),
    ).not.toBeInTheDocument();
  });

  it("«Editar artigo» é um LINK, e não um botão", async () => {
    await montar();

    expect(screen.getByRole("link", { name: /Editar artigo/ })).toHaveAttribute(
      "href",
      "/kb/a1/edit",
    );
  });

  // ── As fontes únicas ────────────────────────────────────────

  it("o papel do autor sai do módulo: «Administrador», e não «Admin»", async () => {
    // A cópia local desta tela era a única das seis que dizia "Admin".
    await montar();

    expect(await screen.findByText("Administrador")).toBeInTheDocument();
    expect(screen.queryByText("Admin")).not.toBeInTheDocument();
  });

  it("a categoria sai do módulo, e não da quarta cópia", async () => {
    await montar();

    expect(screen.getByText("Hardware")).toBeInTheDocument();
  });

  // ── Os controles que ninguém ouvia ──────────────────────────

  it("o campo de comentário e o botão de enviar têm nome próprio", async () => {
    // Os dois só se identificavam por `placeholder` e por desenho: quem usa
    // leitor de tela ouvia "campo de edição" e "botão", e mais nada.
    await montar();

    expect(screen.getByRole("textbox", { name: "Comentário" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Enviar comentário" }),
    ).toBeInTheDocument();
  });

  it("sem comentário nenhum, a tela convida em vez de ficar vazia", async () => {
    await montar([]);

    expect(
      screen.getByText("Nenhum comentário ainda. Seja o primeiro!"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Comentários (0)" }),
    ).toBeInTheDocument();
  });
  it("excluir comentário que FALHA não tira o comentário, e diz que falhou", async () => {
    // Mesmo defeito e mesmo conserto do `handleDelete` da NotificationsPage:
    // o `await` estava solto, e a lista era filtrada antes de a rede
    // confirmar. As irmas deste mesmo arquivo (`handleAddComment`,
    // `handleReply`) ja faziam certo — o estado muda DENTRO do try.
    //
    // As duas metades: o erro aparece, E o comentario continua na tela.
    await montar();
    vi.mocked(kbService.deleteKBComment).mockRejectedValueOnce(
      new Error("rede"),
    );

    await userEvent.click(screen.getByRole("button", { name: "Excluir" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.getByText(COMENTARIO.content)).toBeInTheDocument();
  });
});
