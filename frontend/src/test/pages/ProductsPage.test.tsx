import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/productService", () => ({
  createEquipment: vi.fn(),
  createProduct: vi.fn(),
  getEquipments: vi.fn(),
  getProducts: vi.fn(),
  setEquipmentActive: vi.fn(),
  setProductActive: vi.fn(),
  updateEquipment: vi.fn(),
  updateProduct: vi.fn(),
}));
vi.mock("../../services/userService", () => ({ getUsers: vi.fn() }));

import ProductsPage from "../../pages/products/ProductsPage";
import * as productService from "../../services/productService";
import type { Equipment, Product } from "../../services/productService";

/**
 * O que esta tela tinha, e que estes casos prendem.
 *
 * **Nove `<svg>` desenhados à mão** numa tabela `IC` local — oito iguais
 * caractere a caractere a um traçado do pacote, e um segundo desenho de chip.
 * **Noventa classes de paleta crua**, sendo trinta e uma só no selo de
 * ativo/inativo, que pintava `emerald`/`slate` com oito `dark:` para inverter
 * à mão o que o token inverte sozinho. E **as três opções de filtro escritas
 * duas vezes** no mesmo arquivo, em duas formas diferentes (`{key,label}` e
 * `{value,label}`).
 *
 * Nada disso é observável em jsdom/happy-dom, que não aplica CSS nenhum. Por
 * isso nenhum caso aqui olha classe: os casos prendem o que a migração podia
 * ter quebrado sem ninguém ver — o estado dito em TEXTO e não só em cor, o
 * nome acessível dos controles de ícone, os filtros que continuam sendo do
 * SERVIDOR, e os dois vazios que dizem coisas diferentes.
 */

const PRODUTO_ATIVO: Product = {
  id: "p1",
  name: "Detector de Gases",
  description: "Linha portátil",
  version: "2.1.0",
  is_active: true,
};

const PRODUTO_INATIVO: Product = {
  id: "p2",
  name: "Cinto Paraquedista",
  description: null,
  version: null,
  is_active: false,
};

const EQUIPAMENTO: Equipment = {
  id: "e1",
  product_id: "p1",
  name: "Detector 04",
  serial_number: "SN-001234",
  model: "Detector de Gases",
  description: null,
  is_active: true,
  owner_name: "Maria Souza",
  owner_email: "maria@exemplo.com",
  company_name: "Construtora Alfa",
  company_cnpj: "12345678000190",
};

function comProdutos(items: Product[] = [PRODUTO_ATIVO, PRODUTO_INATIVO]) {
  vi.mocked(productService.getProducts).mockResolvedValue({
    items,
    total: items.length,
    limit: 10,
    offset: 0,
  });
}

function comEquipamentos(items: Equipment[] = [EQUIPAMENTO]) {
  vi.mocked(productService.getEquipments).mockResolvedValue({
    items,
    total: items.length,
    limit: 10,
    offset: 0,
  });
}

async function montar() {
  render(<ProductsPage />);
  await waitFor(() =>
    expect(productService.getProducts).toHaveBeenCalled(),
  );
}

/** Abre o painel de equipamentos do produto ativo e espera a lista chegar. */
async function abrirEquipamentos(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByText("Detector de Gases"));
  await waitFor(() =>
    expect(productService.getEquipments).toHaveBeenCalled(),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  comProdutos();
  comEquipamentos();
});

describe("ProductsPage", () => {
  it("o estado do produto está escrito, e não só pintado", async () => {
    // O selo era um ponto colorido mais a palavra. A cor saiu de `emerald`/
    // `slate` crus para as tintas medidas, e o que não pode ter mudado é o
    // que sobra para quem não enxerga a cor: a PALAVRA.
    await montar();
    expect(await screen.findByText("Ativo")).toBeInTheDocument();
    expect(screen.getByText("Inativo")).toBeInTheDocument();
  });

  it("o selo de estado é um botão, e desativa o produto que ele mostra", async () => {
    const user = userEvent.setup();
    vi.mocked(productService.setProductActive).mockResolvedValue({
      ...PRODUTO_ATIVO,
      is_active: false,
    });
    await montar();

    // O nome acessível do selo é a PALAVRA que ele mostra — o `title` é dica
    // de ponteiro e só vira nome quando não há conteúdo, que é o caso dos
    // botões de ícone abaixo.
    const selo = await screen.findByRole("button", { name: "Ativo" });
    expect(selo).toHaveAttribute("title", "Clique para desativar");
    await user.click(selo);

    expect(productService.setProductActive).toHaveBeenCalledWith("p1", false);
    await waitFor(() =>
      expect(screen.getAllByText("Inativo")).toHaveLength(2),
    );
  });

  it("escolher um produto carrega os equipamentos DELE", async () => {
    const user = userEvent.setup();
    await montar();
    await abrirEquipamentos(user);

    expect(productService.getEquipments).toHaveBeenCalledWith(
      "p1",
      expect.anything(),
    );
    expect(await screen.findByText("Detector 04")).toBeInTheDocument();
    expect(screen.getByText("SN-001234")).toBeInTheDocument();
  });

  it("o filtro de equipamento anuncia qual dos três está escolhido", async () => {
    // As três opções passaram a sair de uma lista só (`FILTROS`), consumida
    // pelas abas e pelo seletor de produtos. O `aria-pressed` é o que separa
    // a aba do gatilho do seletor, que mostra o mesmo texto.
    const user = userEvent.setup();
    await montar();
    await abrirEquipamentos(user);

    expect(
      screen.getByRole("button", { name: "Ativos", pressed: true }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Todos", pressed: false }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Todos" }));

    await waitFor(() =>
      expect(productService.getEquipments).toHaveBeenLastCalledWith(
        "p1",
        expect.objectContaining({ is_active: undefined }),
      ),
    );
  });

  it("'Sem dono' peneira no SERVIDOR, e não na página aberta", async () => {
    // A lista é paginada: peneirar no cliente só acharia o órfão que por
    // acaso caiu na página aberta. O parâmetro precisa chegar na chamada.
    const user = userEvent.setup();
    await montar();
    await abrirEquipamentos(user);

    const botao = screen.getByRole("button", { name: "Sem dono" });
    expect(botao).toHaveAttribute("aria-pressed", "false");

    await user.click(botao);

    await waitFor(() =>
      expect(productService.getEquipments).toHaveBeenLastCalledWith(
        "p1",
        expect.objectContaining({ without_owner: true }),
      ),
    );
    expect(botao).toHaveAttribute("aria-pressed", "true");
  });

  it("os botões só de ícone continuam com nome, e o ícone é decorativo", async () => {
    // O `<svg>` solto não tinha `aria-hidden`; o `Icon` tem. Nos dois casos o
    // nome do controle vem do `title` — e é ele que o leitor de tela anuncia.
    const user = userEvent.setup();
    await montar();
    await abrirEquipamentos(user);

    expect(
      screen.getAllByRole("button", { name: "Editar" }).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByRole("button", { name: "Visualizar" }),
    ).toBeInTheDocument();
  });

  it("os dois campos de busca têm nome próprio, sem depender do placeholder", async () => {
    const user = userEvent.setup();
    await montar();
    expect(
      await screen.findByRole("textbox", { name: "Buscar produto" }),
    ).toBeInTheDocument();

    await abrirEquipamentos(user);
    expect(
      screen.getByRole("textbox", { name: "Buscar equipamento" }),
    ).toBeInTheDocument();
  });

  it("o CNPJ do dono sai formatado pela fonte única", async () => {
    const user = userEvent.setup();
    await montar();
    await abrirEquipamentos(user);

    expect(await screen.findByText(/12\.345\.678\/0001-90/)).toBeInTheDocument();
    expect(screen.getByText("Maria Souza")).toBeInTheDocument();
  });

  it("o vazio de 'sem dono' diz outra coisa, e oferece voltar", async () => {
    // Dois vazios diferentes na mesma caixa: "não há equipamento" e "não há
    // equipamento SEM DONO". Trocar um pelo outro manda a pessoa cadastrar o
    // que já existe.
    const user = userEvent.setup();
    await montar();
    await abrirEquipamentos(user);

    comEquipamentos([]);
    await user.click(screen.getByRole("button", { name: "Sem dono" }));

    expect(
      await screen.findByText("Nenhum equipamento sem dono para este produto."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Nenhum equipamento para este produto."),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Ver todos" }));
    await waitFor(() =>
      expect(productService.getEquipments).toHaveBeenLastCalledWith(
        "p1",
        expect.objectContaining({ without_owner: undefined }),
      ),
    );
  });

  it("sem produto nenhum, a tela convida a criar o primeiro", async () => {
    const user = userEvent.setup();
    comProdutos([]);
    await montar();

    expect(
      await screen.findByText("Nenhum produto encontrado."),
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Criar o primeiro produto" }),
    );
    const dialogo = await screen.findByRole("dialog");
    expect(
      within(dialogo).getByRole("heading", { name: "Novo produto" }),
    ).toBeInTheDocument();
  });

  it("a falha de rede vira aviso, e não lista vazia", async () => {
    vi.mocked(productService.getProducts).mockRejectedValue(new Error("rede"));
    await montar();
    expect(
      await screen.findByText("Não foi possível carregar os produtos."),
    ).toBeInTheDocument();
  });
});
