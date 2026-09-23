import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../services/productService", () => ({ getProducts: vi.fn() }));
vi.mock("../../services/equipmentService", () => ({ getMyEquipment: vi.fn() }));
vi.mock("../../services/attachmentService", () => ({ uploadAttachments: vi.fn() }));
vi.mock("../../services/ticketService", () => ({
  createTicket: vi.fn(),
  getTicket: vi.fn(),
  updateTicket: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { MemoryRouter } from "react-router-dom";
import TicketFormPage from "../../pages/tickets/TicketFormPage";
import { getProducts } from "../../services/productService";
import { getMyEquipment } from "../../services/equipmentService";

/**
 * O que esta tela tinha, e que estes casos prendem.
 *
 * A categoria e a prioridade eram **pilhas de `<button>`**: doze botões cujo
 * nome era só o rótulo, sem "escolhido", sem grupo e sem relação com as
 * palavras "Categoria" e "Prioridade" escritas acima deles. A escolha existia
 * apenas na cor.
 *
 * A prioridade SAIU desta tela em 22/09/2026: quem abre o chamado descreve o
 * problema, quem classifica a urgência é a triagem. O que ficou aqui é o caso
 * que prende a ausência — o seletor não volta por descuido, e o POST não leva
 * o campo.
 *
 * E a trilha era um `<button>` com a linha inteira dentro, então o nome
 * acessível do controle era "Tickets / Novo chamado": a página de onde se vem
 * e a página onde se está, num controle só.
 */
async function montar() {
  vi.mocked(getProducts).mockResolvedValue({ items: [], total: 0 } as never);
  vi.mocked(getMyEquipment).mockResolvedValue([] as never);

  render(
    <MemoryRouter initialEntries={["/tickets/new"]}>
      <TicketFormPage />
    </MemoryRouter>,
  );
  await waitFor(() =>
    expect(screen.getByRole("group", { name: "Categoria" })).toBeInTheDocument(),
  );
}

describe("TicketFormPage", () => {
  it("categoria é grupo de rádio, com nome", async () => {
    await montar();
    expect(screen.getByRole("group", { name: "Categoria" })).toBeInTheDocument();
    // Oito categorias, e nenhuma delas é botão. Eram doze enquanto as quatro
    // prioridades moravam aqui.
    expect(screen.getAllByRole("radio")).toHaveLength(8);
  });

  it("quem abre o chamado não escolhe prioridade", async () => {
    await montar();
    expect(screen.queryByRole("group", { name: "Prioridade" })).not.toBeInTheDocument();
    for (const rotulo of ["Crítica", "Alta", "Média", "Baixa"]) {
      expect(screen.queryByRole("radio", { name: rotulo })).not.toBeInTheDocument();
    }
    // Nem escondido num campo: a palavra não aparece na tela de abertura.
    expect(screen.queryByText("Prioridade")).not.toBeInTheDocument();
  });

  it("escolher categoria muda o que a árvore diz, não só a cor", async () => {
    await montar();
    const rede = screen.getByRole("radio", { name: "Rede" });
    expect(rede).not.toBeChecked();
    await userEvent.click(rede);
    expect(rede).toBeChecked();
  });

  it("a trilha é um link para a lista, e não um botão", async () => {
    await montar();
    const link = screen.getByRole("link", { name: "Tickets" });
    expect(link).toHaveAttribute("href", "/tickets");
    // E a página atual não finge ser clicável.
    expect(screen.queryByRole("link", { name: /Novo chamado/ })).not.toBeInTheDocument();
  });

  it("a etapa atual é dita, e não apenas pintada", async () => {
    await montar();
    const atual = screen.getByText("Formulário");
    expect(atual).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("Revisão")).not.toHaveAttribute("aria-current");
  });

  it("o grupo de equipamentos tem nome", async () => {
    // Era um `<label>` sem `htmlFor`: rótulo pendurado no vazio.
    await montar();
    expect(screen.getByRole("group", { name: "Equipamentos" })).toBeInTheDocument();
  });
});

/**
 * A descrição da categoria (18/09/2026).
 *
 * Cada categoria ganhou uma frase dizendo o que ela abrange, e o Resumo mostra
 * a da escolhida. O que estes casos prendem não é o texto — esse mora em
 * `lib/categoria.test.ts` — e sim a costura: a frase chega a quem NÃO está
 * vendo o painel (leitor de tela, e tela estreita, onde o Resumo desce para o
 * fim da página).
 */
describe("TicketFormPage — a descrição da categoria", () => {
  /** O parágrafo que fica logo abaixo das fichas, irmão do grupo. */
  function fraseAbaixoDasFichas() {
    return screen.getByRole("group", { name: "Categoria" }).nextElementSibling;
  }

  it("sem escolha, não há frase — e o grupo não é descrito por um vazio", async () => {
    await montar();
    const grupo = screen.getByRole("group", { name: "Categoria" });

    expect(grupo).not.toHaveAttribute("aria-describedby");
    // O parágrafo existe mesmo assim: região viva só anuncia mudança se já
    // estava na página antes dela.
    expect(fraseAbaixoDasFichas()).toHaveTextContent("");
    expect(fraseAbaixoDasFichas()).toHaveAttribute("aria-live", "polite");
  });

  it("escolher a categoria descreve o GRUPO, não só pinta a ficha", async () => {
    await montar();
    const grupo = screen.getByRole("group", { name: "Categoria" });

    await userEvent.click(screen.getByRole("radio", { name: "Rede" }));

    const id = grupo.getAttribute("aria-describedby");
    expect(id).toBeTruthy();
    const frase = document.getElementById(id as string);
    expect(frase).toHaveTextContent("Dificuldade de conexão.");
    // Quem chega às fichas pelo teclado ouve o nome do grupo, a opção e isto.
    expect(frase).toBe(fraseAbaixoDasFichas());
  });

  it("clicar noutra categoria troca a frase no MESMO parágrafo", async () => {
    // Trocar o elemento de lugar (desmontar e montar outro) mataria o anúncio:
    // região viva anuncia a mudança de conteúdo de quem já estava lá.
    await montar();
    const antes = fraseAbaixoDasFichas();

    await userEvent.click(screen.getByRole("radio", { name: "Rede" }));
    expect(fraseAbaixoDasFichas()).toHaveTextContent("Dificuldade de conexão.");

    await userEvent.click(screen.getByRole("radio", { name: "Hardware" }));
    expect(fraseAbaixoDasFichas()).toHaveTextContent("Algum problema físico detectado.");
    expect(fraseAbaixoDasFichas()).toBe(antes);
  });

  it("a frase aparece em dois lugares, e cada um serve a uma largura", async () => {
    // Na tela larga o Resumo fica ao lado do formulário e mostra a frase; na
    // estreita ele desce para o fim da página, longe das fichas, e quem mostra
    // é o parágrafo de baixo. `hidden` é `display:none`: em cada largura só uma
    // das cópias está na árvore de acessibilidade, então só uma é lida e só uma
    // anuncia.
    await montar();
    await userEvent.click(screen.getByRole("radio", { name: "Segurança" }));

    const copias = screen.getAllByText(
      "Sua senha vazou ou está sendo usada por terceiros (LGPD).",
    );
    expect(copias).toHaveLength(2);

    const [abaixoDasFichas, noResumo] = copias;
    expect(abaixoDasFichas).toBe(fraseAbaixoDasFichas());
    expect(abaixoDasFichas.className).toContain("lg:hidden");
    expect(abaixoDasFichas.closest("form")).not.toBeNull();

    expect(noResumo.className).toContain("hidden");
    expect(noResumo.className).toContain("lg:block");
    expect(noResumo).toHaveAttribute("aria-live", "polite");
    // O Resumo é painel, não formulário.
    expect(noResumo.closest("form")).toBeNull();
  });

  it("a cópia do Resumo fica junto da linha Categoria", async () => {
    await montar();
    await userEvent.click(screen.getByRole("radio", { name: "Acesso" }));

    const [, noResumo] = screen.getAllByText("Senha.");
    const bloco = noResumo.parentElement;
    expect(bloco).not.toBeNull();
    expect(bloco).toHaveTextContent("Categoria");
    expect(bloco).toHaveTextContent("Acesso");
  });

  it("'Outro' não tem frase, e a tela não inventa uma", async () => {
    // Ele se sobrepõe a "Geral" e pode sair da lista; enquanto existir, o
    // Resumo mostra o nome e cala sobre o significado.
    await montar();
    const grupo = screen.getByRole("group", { name: "Categoria" });

    await userEvent.click(screen.getByRole("radio", { name: "Geral" }));
    expect(grupo).toHaveAttribute("aria-describedby");

    await userEvent.click(screen.getByRole("radio", { name: "Outro" }));
    expect(grupo).not.toHaveAttribute("aria-describedby");
    expect(fraseAbaixoDasFichas()).toHaveTextContent("");
    expect(screen.queryByText(/Qualquer ocorrência/)).not.toBeInTheDocument();
  });
});
