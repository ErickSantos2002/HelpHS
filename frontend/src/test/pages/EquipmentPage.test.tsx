import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/api", () => ({ api: { get: vi.fn() } }));
vi.mock("../../services/equipmentService", () => ({
  createMyEquipment: vi.fn(),
  deleteMyEquipment: vi.fn(),
  getMyEquipment: vi.fn(),
  updateMyEquipment: vi.fn(),
}));

import EquipmentPage from "../../pages/equipment/EquipmentPage";
import { api } from "../../services/api";
import * as equipmentService from "../../services/equipmentService";
import type { Equipment } from "../../services/equipmentService";

/**
 * O que esta tela tinha, e que estes casos prendem.
 *
 * **Sessenta e seis classes de paleta crua em 482 linhas**, sendo dezesseis só
 * no selo de ativo/inativo — `emerald` e `slate` com seis `dark:` invertendo à
 * mão o que o token inverte sozinho. **Cinco `<svg>` soltos** numa tabela `IC`
 * local, quatro deles iguais caractere a caractere a um traçado do pacote.
 * Um `KpiCard` **local**, homônimo do primitivo, com uma prop `accent` de
 * classe crua — a porta pela qual `text-emerald-600` entrou sem revisão. E um
 * `<select>` com classe à mão, cujo `<label>` não tinha `htmlFor`: campo sem
 * nome acessível.
 *
 * Nada disso é observável em happy-dom, que não aplica CSS nenhum. Por isso
 * nenhum caso aqui olha classe — trocar `sr-only` por `hidden` não esconde
 * coisa alguma de um `getByText`, e um caso que afirmasse a classe passaria com
 * o elemento invisível de verdade.
 *
 * O que os casos prendem é o que a migração podia ter quebrado sem ninguém
 * ver: o estado dito em PALAVRA e não só em cor, as contagens que as abas e os
 * indicadores mostram, a aba escolhida dizendo-se escolhida na árvore, o nome
 * acessível dos dois botões de ícone (dez linhas davam dez botões chamados
 * "Editar"), o aviso de exclusão, e os DOIS vazios, que dizem coisas
 * diferentes.
 */

const PRODUTO_ATIVO = {
  id: "p1",
  name: "Detector de Gases",
  version: "2.1.0",
  is_active: true,
};

const PRODUTO_INATIVO = {
  id: "p2",
  name: "Cinto Paraquedista",
  version: null,
  is_active: false,
};

const BASE = {
  product_id: "p1",
  owner_id: "u1",
  model: null,
  description: null,
  created_at: "2026-09-01T12:00:00Z",
  updated_at: "2026-09-01T12:00:00Z",
};

const ATIVO: Equipment = {
  ...BASE,
  id: "e1",
  name: "Detector 04",
  serial_number: "SN-001234",
  location: "Sala 201",
  is_active: true,
};

const INATIVO: Equipment = {
  ...BASE,
  id: "e2",
  name: "Detector 09",
  serial_number: null,
  location: null,
  is_active: false,
};

async function montar(
  equipamentos: Equipment[] = [ATIVO, INATIVO],
  produtos: unknown[] = [PRODUTO_ATIVO, PRODUTO_INATIVO],
) {
  vi.mocked(api.get).mockResolvedValue({ data: { items: produtos } } as never);
  vi.mocked(equipmentService.getMyEquipment).mockResolvedValue(equipamentos);

  render(<EquipmentPage />);

  // O `Spinner` sai quando as duas promessas fecham; o título só existe
  // depois disso.
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "Meus equipamentos" }),
    ).toBeInTheDocument(),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("EquipmentPage", () => {
  it("cada linha traz o nome, a série e a localização", async () => {
    await montar();
    expect(screen.getByText("Detector 04")).toBeInTheDocument();
    expect(screen.getByText("SN-001234")).toBeInTheDocument();
    expect(screen.getByText("Sala 201")).toBeInTheDocument();
  });

  it("o estado do equipamento está escrito, e não só pintado", async () => {
    // O selo era um ponto colorido mais a palavra. A cor saiu de `emerald`/
    // `slate` crus para as tintas medidas e o ponto virou forma decorativa
    // (`aria-hidden`); o que não pode ter mudado é o que sobra para quem não
    // enxerga a cor: a PALAVRA.
    await montar();
    expect(screen.getByText("Ativo")).toBeInTheDocument();
    expect(screen.getByText("Inativo")).toBeInTheDocument();
  });

  it("as três abas contam, e cada uma conta a sua fatia", async () => {
    await montar();
    expect(screen.getByRole("button", { name: "Todos (2)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ativos (1)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Inativos (1)" })).toBeInTheDocument();
  });

  it("a aba escolhida se declara na árvore, e não só na cor", async () => {
    // Antes o selecionado existia em `border-primary text-primary` e em mais
    // nada: quem não vê a cor não tinha como saber qual filtro estava valendo.
    const user = userEvent.setup();
    await montar();

    expect(
      screen.getByRole("button", { name: "Todos (2)", pressed: true }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Inativos (1)" }));

    expect(
      screen.getByRole("button", { name: "Inativos (1)", pressed: true }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Todos (2)", pressed: false }),
    ).toBeInTheDocument();
  });

  it("filtrar por Inativos tira o ativo da lista", async () => {
    const user = userEvent.setup();
    await montar();

    await user.click(screen.getByRole("button", { name: "Inativos (1)" }));

    expect(screen.getByText("Detector 09")).toBeInTheDocument();
    expect(screen.queryByText("Detector 04")).not.toBeInTheDocument();
  });

  it("os três indicadores dizem o mesmo que as abas", async () => {
    await montar();
    const total = screen.getByText("Total").parentElement as HTMLElement;
    const ativos = screen.getByText("Ativos").parentElement as HTMLElement;
    const inativos = screen.getByText("Inativos").parentElement as HTMLElement;

    expect(within(total).getByText("2")).toBeInTheDocument();
    expect(within(ativos).getByText("1")).toBeInTheDocument();
    expect(within(inativos).getByText("1")).toBeInTheDocument();
  });

  it("cada botão de ícone diz DE QUAL equipamento ele é", async () => {
    // Dez linhas na página davam dez botões chamados "Editar" — e o `title`
    // sozinho não desempata para quem navega pela lista de controles.
    await montar();
    expect(
      screen.getByRole("button", { name: "Editar Detector 04" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Excluir Detector 09" }),
    ).toBeInTheDocument();
  });

  it("excluir avisa que a ação é irreversível e nomeia o equipamento", async () => {
    const user = userEvent.setup();
    await montar();

    await user.click(
      screen.getByRole("button", { name: "Excluir Detector 04" }),
    );

    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByText("Ação irreversível")).toBeInTheDocument();
    expect(
      within(dialogo).getByText("Este equipamento será removido permanentemente."),
    ).toBeInTheDocument();
    expect(
      within(dialogo).getAllByText("Detector 04").length,
    ).toBeGreaterThan(0);
    expect(
      within(dialogo).getByRole("button", { name: "Excluir permanentemente" }),
    ).toBeInTheDocument();
  });

  it("o campo de produto tem nome, e só oferece produto ativo", async () => {
    // O `<label>` não tinha `htmlFor` e o `<select>` não tinha `id`: o campo
    // não tinha nome acessível nenhum.
    const user = userEvent.setup();
    await montar();

    await user.click(
      screen.getByRole("button", { name: /Adicionar equipamento/ }),
    );

    const campo = await screen.findByLabelText("Produto *");
    expect(within(campo).getByText("Detector de Gases (2.1.0)")).toBeInTheDocument();
    expect(within(campo).queryByText(/Cinto Paraquedista/)).not.toBeInTheDocument();
  });

  it("o vazio de tela sem cadastro não é o vazio de filtro", async () => {
    const user = userEvent.setup();
    await montar([INATIVO]);

    // Com um inativo cadastrado, o filtro "Ativos" fica vazio — mas há
    // cadastro, e a tela não pode dizer que não há.
    await user.click(screen.getByRole("button", { name: "Ativos (0)" }));
    expect(screen.getByText("Nenhum equipamento neste filtro.")).toBeInTheDocument();
    expect(
      screen.queryByText("Nenhum equipamento cadastrado ainda."),
    ).not.toBeInTheDocument();
  });

  it("sem nenhum cadastro, a tela convida a cadastrar o primeiro", async () => {
    await montar([]);
    expect(
      screen.getByText("Nenhum equipamento cadastrado ainda."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Adicionar primeiro equipamento" }),
    ).toBeInTheDocument();
  });

  it("sem produto ativo no sistema, não há como adicionar", async () => {
    // O produto inativo é filtrado antes de chegar à tela: sem produto não há
    // a que vincular um equipamento, e o convite mentiria.
    await montar([], [PRODUTO_INATIVO]);
    expect(
      screen.getByText("Nenhum produto disponível no sistema ainda."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Adicionar/ }),
    ).not.toBeInTheDocument();
  });
});
