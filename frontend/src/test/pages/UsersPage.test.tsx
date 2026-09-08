import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/userService", () => ({
  createUser: vi.fn(),
  deleteUser: vi.fn(),
  getUsers: vi.fn(),
  setUserStatus: vi.fn(),
  updateUser: vi.fn(),
}));

import UsersPage from "../../pages/users/UsersPage";
import * as userService from "../../services/userService";
import type { UserSummary } from "../../services/userService";

/**
 * O que esta tela tinha, e que estes casos prendem.
 *
 * **Oitenta e uma classes de paleta crua** em 626 linhas, sendo trinta e uma
 * só na pílula de estado da conta, que pintava `emerald`/`slate` com oito
 * `dark:` para inverter à mão o que o token inverte sozinho. **Cinco `<svg>`
 * soltos** num mapa local `IC`, os cinco iguais caractere a caractere a um
 * traçado do pacote. E **quatro cópias da mesma tabela de papel** no mesmo
 * arquivo — `ROLE_LABEL`, `ROLE_BADGE`, `ROLE_OPTIONS` e
 * `FILTER_ROLE_OPTIONS`, as duas últimas idênticas linha a linha.
 *
 * Nada disso é observável em happy-dom, que não aplica CSS nenhum. Por isso
 * nenhum caso aqui olha classe — olhar classe mediria o contrário do que
 * interessa: passaria com `sr-only` presente e o elemento invisível de
 * verdade. Os casos prendem o que a migração podia ter quebrado sem ninguém
 * ver: o papel e o estado ditos em TEXTO e não só em cor, o nome acessível dos
 * N controles de ícone por página, o campo de busca que só tinha
 * `placeholder`, os dois vazios que dizem coisas diferentes, e a lista curta
 * do filtro de estado — que já derrubou a tela com 422 quando ofereceu um
 * valor que o backend não conhecia.
 */

const BASE: Omit<UserSummary, "id" | "name" | "email" | "role" | "status"> = {
  phone: null,
  department: null,
  avatar_url: null,
  last_login: null,
  lgpd_consent: true,
  lgpd_consent_at: null,
  company_name: null,
  cnpj: null,
  company_cep: null,
  company_address: null,
  company_city: null,
  company_state: null,
  onboarding_completed: true,
  created_at: "2026-03-04T12:00:00Z",
  updated_at: "2026-03-04T12:00:00Z",
};

const ANA: UserSummary = {
  ...BASE,
  id: "u1",
  name: "Ana Souza",
  email: "ana@exemplo.com",
  role: "admin",
  status: "active",
};

const BRUNO: UserSummary = {
  ...BASE,
  id: "u2",
  name: "Bruno Lima",
  email: "bruno@exemplo.com",
  role: "technician",
  status: "inactive",
};

/** Anonimizado existe na lista, mas não no filtro — e nem alterna. */
const CARLA: UserSummary = {
  ...BASE,
  id: "u3",
  name: "Carla Dias",
  email: "carla@exemplo.com",
  role: "client",
  status: "anonymized",
};

function comUsuarios(items: UserSummary[] = [ANA, BRUNO, CARLA], total = items.length) {
  vi.mocked(userService.getUsers).mockResolvedValue({
    items,
    total,
    limit: 10,
    offset: 0,
  });
}

async function montar() {
  render(<UsersPage />);
  await waitFor(() => expect(userService.getUsers).toHaveBeenCalled());
}

beforeEach(() => {
  vi.clearAllMocks();
  comUsuarios();
});

describe("UsersPage", () => {
  it("o papel de cada usuário está escrito, e não só pintado", async () => {
    // O selo saiu de um mapa local de classes cruas para o `Badge` do pacote.
    // O que não pode ter mudado é o que sobra para quem não enxerga a cor: a
    // PALAVRA — e que ela seja a palavra do rótulo, e não o valor do backend.
    await montar();
    expect(await screen.findByText("Administrador")).toBeInTheDocument();
    expect(screen.getByText("Técnico")).toBeInTheDocument();
    expect(screen.getByText("Cliente")).toBeInTheDocument();
    expect(screen.queryByText("admin")).not.toBeInTheDocument();
    expect(screen.queryByText("technician")).not.toBeInTheDocument();
  });

  it("o estado da conta está escrito, e o selo desativa quem ele mostra", async () => {
    const user = userEvent.setup();
    vi.mocked(userService.setUserStatus).mockResolvedValue({
      ...ANA,
      status: "inactive",
    });
    await montar();

    expect(await screen.findByText("Inativo")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ativo" }));

    expect(userService.setUserStatus).toHaveBeenCalledWith("u1", "inactive");
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Ativo" })).not.toBeInTheDocument(),
    );
  });

  it("conta anonimizada não alterna, e diz isso sem depender da cor", async () => {
    // A pílula de anonimizado pinta igual à de inativo de propósito: quem
    // carrega a diferença é a palavra. O que a distingue como CONTROLE é estar
    // desabilitada — e é isso que este caso prende.
    const user = userEvent.setup();
    await montar();

    const pilula = await screen.findByRole("button", { name: "Anonimizado" });
    expect(pilula).toBeDisabled();
    await user.click(pilula);
    expect(userService.setUserStatus).not.toHaveBeenCalled();
  });

  it("cada linha tem os seus controles, e eles dizem de quem são", async () => {
    // Eram N botões por página com o mesmo nome acessível: dez cadastros
    // davam dez controles chamados "Editar" e dez chamados "Excluir".
    await montar();
    expect(
      await screen.findByRole("button", { name: "Editar Ana Souza" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Excluir Bruno Lima" }),
    ).toBeInTheDocument();
    expect(screen.queryAllByRole("button", { name: "Editar" })).toHaveLength(0);
    expect(screen.queryAllByRole("button", { name: "Excluir" })).toHaveLength(0);
  });

  it("a busca tem nome acessível, e é feita no servidor", async () => {
    // O campo só tinha `placeholder`, que NÃO é nome acessível: quem navega
    // por leitor de tela chegava num campo de texto sem nome no meio da barra.
    // E a busca é do SERVIDOR — filtrar no cliente mostraria só a página atual.
    const user = userEvent.setup();
    await montar();

    await user.type(screen.getByRole("textbox", { name: "Buscar usuários" }), "ana");

    await waitFor(() =>
      expect(userService.getUsers).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: "ana" }),
      ),
    );
  });

  it("os dois vazios dizem coisas diferentes, e só um convida a criar", async () => {
    // Com filtro, o cadastro provavelmente existe e está escondido: oferecer
    // "criar" ali empurra para o duplicado.
    const user = userEvent.setup();
    comUsuarios([], 0);
    await montar();

    expect(await screen.findByText("Nenhum usuário cadastrado.")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Criar o primeiro usuário" }),
    ).toBeInTheDocument();

    await user.type(screen.getByRole("textbox", { name: "Buscar usuários" }), "zzz");

    expect(
      await screen.findByText("Nenhum usuário encontrado para esses filtros."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Criar o primeiro usuário" }),
    ).not.toBeInTheDocument();
  });

  it("o contador do cabeçalho concorda com o número", async () => {
    comUsuarios([ANA], 1);
    const { unmount } = render(<UsersPage />);
    expect(await screen.findByText("1 usuário cadastrado")).toBeInTheDocument();
    unmount();

    comUsuarios([ANA, BRUNO, CARLA], 3);
    render(<UsersPage />);
    expect(await screen.findByText("3 usuários cadastrados")).toBeInTheDocument();
  });

  it("excluir avisa que não volta, nomeia quem some, e só some ao confirmar", async () => {
    const user = userEvent.setup();
    vi.mocked(userService.deleteUser).mockResolvedValue(undefined as never);
    await montar();

    await user.click(await screen.findByRole("button", { name: "Excluir Ana Souza" }));

    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByText("Ação irreversível")).toBeInTheDocument();
    // O e-mail é o que desambigua homônimos, e ele vem do cartão de
    // pré-visualização — o bloco que confirma QUEM vai ser apagado.
    expect(within(dialogo).getByText("ana@exemplo.com")).toBeInTheDocument();
    expect(userService.deleteUser).not.toHaveBeenCalled();

    await user.click(
      within(dialogo).getByRole("button", { name: "Excluir permanentemente" }),
    );

    await waitFor(() => expect(userService.deleteUser).toHaveBeenCalledWith("u1"));
    await waitFor(() =>
      expect(screen.queryByText("ana@exemplo.com")).not.toBeInTheDocument(),
    );
  });

  it("editar abre com o usuário já dentro", async () => {
    const user = userEvent.setup();
    await montar();

    await user.click(await screen.findByRole("button", { name: "Editar Bruno Lima" }));

    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByText("bruno@exemplo.com")).toBeInTheDocument();
    expect(within(dialogo).getByLabelText("Nome *")).toHaveValue("Bruno Lima");
  });

  it("o filtro de estado oferece só os dois valores que o servidor aceita", async () => {
    // "suspended" já morou no `userService` sem nunca ter existido no banco, e
    // a opção que ele gerava derrubava a lista com 422 — o FastAPI recusa na
    // validação do Query, antes do handler. Anonimizado é real, mas filtrar
    // por ele não é uso de tela.
    const user = userEvent.setup();
    await montar();

    await user.click(screen.getByRole("button", { name: "Status" }));

    const opcoes = (await screen.findAllByRole("option")).map((o) => o.textContent);
    expect(opcoes).toContain("Ativo");
    expect(opcoes).toContain("Inativo");
    expect(opcoes).not.toContain("Anonimizado");
  });
});
