import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/groupService", () => ({
  getCompany: vi.fn(),
  listCompanyNotes: vi.fn(),
  updateCompany: vi.fn(),
  deleteCompany: vi.fn(),
  assignClient: vi.fn(),
  unassignClient: vi.fn(),
  updateClientNotes: vi.fn(),
  listUnassignedClients: vi.fn(),
  createCompanyNote: vi.fn(),
  deleteCompanyNote: vi.fn(),
  // A página inteira, que os casos da Fase 16 montam. Um nome que falta aqui
  // só estoura quando a tela CHAMA a função — por isso a lista antiga passava
  // sem eles, e por isso ela precisa crescer junto com o que se monta.
  listGroups: vi.fn(),
  getGroup: vi.fn(),
  createGroup: vi.fn(),
  updateGroup: vi.fn(),
  deleteGroup: vi.fn(),
  createCompany: vi.fn(),
  getCompanySuggestions: vi.fn(),
  createCompanyFromSuggestion: vi.fn(),
  listGroupNotes: vi.fn(),
  createGroupNote: vi.fn(),
  deleteGroupNote: vi.fn(),
}));

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import GroupsPage, { CompanyDetailModal } from "../../pages/groups/GroupsPage";
import {
  deleteCompany,
  deleteCompanyNote,
  deleteGroup,
  deleteGroupNote,
  getCompany,
  unassignClient,
  getGroup,
  listCompanyNotes,
  listGroupNotes,
  listGroups,
} from "../../services/groupService";
import type {
  ClientInCompany,
  CompanyNote,
  CompanyResponse,
  GroupDetail,
  GroupNote,
  GroupResponse,
} from "../../services/groupService";

/**
 * O aviso do ESLint pedia `load` nas deps do efeito deste modal. Atender ao
 * pedido do jeito ingênuo — só acrescentar `load` — dá laço infinito, porque
 * `load` era redefinido a cada render e chama `setState`.
 *
 * A correção foi `useCallback(load, [groupId, company.id])` com
 * `useEffect(() => load(), [load])`. Estes testes prendem as duas metades
 * dessa correção:
 *
 *   1. o efeito NÃO dispara em re-render sem mudança — se disparasse, seria o
 *      laço que a correção ingênua causaria;
 *   2. o efeito dispara quando `groupId` muda — que é a dependência que estava
 *      FALTANDO antes e a razão de a correção não ser só cosmética.
 *
 * O teste 2 é o que importa: tirar `groupId` das deps do useCallback deixa o
 * teste 1 verde e derruba só ele.
 */

const EMPRESA: CompanyResponse = {
  id: "empresa-1",
  group_id: "grupo-A",
  name: "Transportes Alfa",
  cnpj: "12.345.678/0001-90",
  phone: null,
  address: null,
  city: null,
  state: null,
  notes: null,
  client_count: 0,
  note_count: 0,
  created_at: "2026-09-01T12:00:00Z",
  updated_at: "2026-09-01T12:00:00Z",
};

const DETALHE = { ...EMPRESA, clients: [] };

describe("CompanyDetailModal — recarga do efeito", () => {
  beforeEach(() => {
    vi.mocked(getCompany).mockResolvedValue(DETALHE);
    vi.mocked(listCompanyNotes).mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("carrega uma vez só, por mais que o pai re-renderize", async () => {
    const { rerender } = render(
      <CompanyDetailModal
        groupId="grupo-A"
        company={EMPRESA}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );

    await waitFor(() => expect(getCompany).toHaveBeenCalledTimes(1));

    // Cinco re-renders com as MESMAS props, e callbacks inline novos a cada vez
    // — que é como o pai realmente renderiza este modal.
    for (let i = 0; i < 5; i++) {
      rerender(
        <CompanyDetailModal
          groupId="grupo-A"
          company={EMPRESA}
          onClose={() => {}}
          onUpdated={() => {}}
        />,
      );
    }

    expect(getCompany).toHaveBeenCalledTimes(1);
  });

  it("recarrega quando o grupo muda, mesmo com a mesma empresa", async () => {
    // Esta é a dependência que faltava. Antes da correção o efeito olhava só
    // `company.id`: com `groupId` novo e a mesma empresa, o modal seguiria
    // mostrando o que carregou pelo grupo anterior.
    const { rerender } = render(
      <CompanyDetailModal
        groupId="grupo-A"
        company={EMPRESA}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );

    await waitFor(() => expect(getCompany).toHaveBeenCalledTimes(1));
    expect(getCompany).toHaveBeenLastCalledWith("grupo-A", "empresa-1");

    rerender(
      <CompanyDetailModal
        groupId="grupo-B"
        company={EMPRESA}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );

    await waitFor(() => expect(getCompany).toHaveBeenCalledTimes(2));
    expect(getCompany).toHaveBeenLastCalledWith("grupo-B", "empresa-1");
  });

  it("recarrega quando a empresa muda", async () => {
    const { rerender } = render(
      <CompanyDetailModal
        groupId="grupo-A"
        company={EMPRESA}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );

    await waitFor(() => expect(getCompany).toHaveBeenCalledTimes(1));

    rerender(
      <CompanyDetailModal
        groupId="grupo-A"
        company={{ ...EMPRESA, id: "empresa-2" }}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );

    await waitFor(() => expect(getCompany).toHaveBeenCalledTimes(2));
    expect(getCompany).toHaveBeenLastCalledWith("grupo-A", "empresa-2");
  });
});

/**
 * Os casos abaixo entraram com a migração da Fase 16, e todos medem o que a
 * tela PROMETE — o rótulo que a pessoa lê, o nome acessível do controle, o
 * estado vazio —, nunca a classe que pinta.
 *
 * A distinção não é preciosismo: o jsdom não aplica CSS nenhum, então um caso
 * escrito sobre classe passaria com o elemento invisível e reprovaria com ele
 * visível. Cada um destes foi validado por mutação no próprio arquivo da tela.
 */

const NOTA_EMPRESA: CompanyNote = {
  id: "nota-1",
  company_id: "empresa-1",
  author_id: "user-1",
  author_name: "Ana Souza",
  content: "Contrato renovado em janeiro.",
  created_at: "2026-09-02T10:00:00Z",
};

describe("CompanyDetailModal — a aba de notas", () => {
  beforeEach(() => {
    vi.mocked(getCompany).mockResolvedValue(DETALHE);
    vi.mocked(listCompanyNotes).mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("mostra o estado vazio quando a empresa não tem nota", async () => {
    render(
      <CompanyDetailModal
        groupId="grupo-A"
        company={EMPRESA}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /Notas \(0\)/ }));

    expect(screen.getByText("Nenhuma nota ainda.")).toBeInTheDocument();
  });

  it("dá nome acessível ao botão de deletar de cada nota", async () => {
    // O botão é só o ícone, e o `Icon` do pacote é `aria-hidden`. Sem
    // `aria-label` quem usa leitor de tela ouve "botão" e mais nada — foi o
    // mesmo defeito achado no `TicketListPage`.
    vi.mocked(listCompanyNotes).mockResolvedValue([NOTA_EMPRESA]);

    render(
      <CompanyDetailModal
        groupId="grupo-A"
        company={EMPRESA}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /Notas \(1\)/ }));

    expect(
      screen.getByRole("button", { name: "Deletar nota" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Contrato renovado em janeiro.")).toBeInTheDocument();
  });

  /**
   * Os quatro `confirm()` nativos desta tela saíram pela D9.3, e este é o
   * primeiro deles. O que ele perguntava era "Deletar esta nota?" — a mesma
   * frase para todas as notas da aba —, sem dizer de quem era a nota, de que
   * empresa, nem que não volta.
   *
   * O caso mede a FRASE, não a casca: `getByText` cai no parágrafo do diálogo,
   * e `toHaveTextContent` cobra que o nome esteja NAQUELE parágrafo. Contar
   * ocorrências na tela não serviria — o autor da nota já está escrito na
   * lista atrás do diálogo.
   */
  it("o diálogo se anuncia nomeando o que será excluído", async () => {
    // O título do `Modal` é o NOME ACESSÍVEL do diálogo: o componente põe
    // `role="dialog"` com `aria-labelledby` apontando para o `<h2>` do título.
    // É a primeira coisa que o leitor de tela anuncia — e um título "Excluir"
    // seco deixaria quem não vê a tela sem saber o quê. O corpo também nomeia,
    // mas o corpo vem DEPOIS do nome, e só se a pessoa continuar.
    vi.mocked(listCompanyNotes).mockResolvedValue([NOTA_EMPRESA]);

    render(
      <CompanyDetailModal
        groupId="grupo-A"
        company={EMPRESA}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /Notas \(1\)/ }));
    fireEvent.click(screen.getByRole("button", { name: "Deletar nota" }));

    // O modal da empresa também é um `dialog`, e continua aberto atrás. É
    // por isso que o caso pesca pelo NOME, e não por `getByRole("dialog")`
    // solto: o nome é o que distingue os dois para quem só ouve.
    expect(
      await screen.findByRole("dialog", { name: "Excluir nota da empresa" }),
    ).toBeInTheDocument();
  });

  it("deletar nota abre diálogo que nomeia a nota e a empresa", async () => {
    vi.mocked(listCompanyNotes).mockResolvedValue([NOTA_EMPRESA]);

    render(
      <CompanyDetailModal
        groupId="grupo-A"
        company={EMPRESA}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /Notas \(1\)/ }));
    fireEvent.click(screen.getByRole("button", { name: "Deletar nota" }));

    const frase = await screen.findByText(/não pode ser desfeita/);
    expect(frase).toHaveTextContent("Ana Souza");
    expect(frase).toHaveTextContent("Transportes Alfa");
    expect(deleteCompanyNote).not.toHaveBeenCalled();
  });

  it("cancelar fecha o diálogo e a nota da empresa continua lá", async () => {
    vi.mocked(listCompanyNotes).mockResolvedValue([NOTA_EMPRESA]);

    render(
      <CompanyDetailModal
        groupId="grupo-A"
        company={EMPRESA}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /Notas \(1\)/ }));
    fireEvent.click(screen.getByRole("button", { name: "Deletar nota" }));
    await screen.findByText(/não pode ser desfeita/);
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    await waitFor(() =>
      expect(screen.queryByText(/não pode ser desfeita/)).not.toBeInTheDocument(),
    );
    expect(deleteCompanyNote).not.toHaveBeenCalled();
    expect(screen.getByText("Contrato renovado em janeiro.")).toBeInTheDocument();
  });

  it("só o «Excluir» do diálogo apaga a nota da empresa", async () => {
    vi.mocked(listCompanyNotes).mockResolvedValue([NOTA_EMPRESA]);
    vi.mocked(deleteCompanyNote).mockResolvedValue(undefined);

    render(
      <CompanyDetailModal
        groupId="grupo-A"
        company={EMPRESA}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /Notas \(1\)/ }));
    fireEvent.click(screen.getByRole("button", { name: "Deletar nota" }));
    await screen.findByText(/não pode ser desfeita/);
    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));

    await waitFor(() =>
      expect(deleteCompanyNote).toHaveBeenCalledWith(
        "grupo-A",
        "empresa-1",
        "nota-1",
      ),
    );
  });
});

const CLIENTE: ClientInCompany = {
  id: "cli-1",
  name: "Carla Dias",
  email: "carla@transportesalfa.com",
  phone: null,
  client_notes: null,
};

/**
 * A desvinculacao era o ULTIMO `confirm()` nativo de `src/pages/**`, e a D9.3
 * mandou converte-lo com uma diferenca deliberada: o botao de acao e `primary`,
 * nao `danger` — desvincular nao destroi a conta, tira o vinculo.
 *
 * Os casos abaixo NAO afirmam a cor: o jsdom nao aplica CSS, e um caso sobre
 * classe passaria com o botao invisivel. O que eles prendem e o que a pessoa
 * alcanca — o nome do dialogo, o nome dos dois botoes, e o que a frase promete
 * que acontece com a conta.
 */
describe("CompanyDetailModal — desvincular cliente", () => {
  beforeEach(() => {
    vi.mocked(getCompany).mockResolvedValue({
      ...DETALHE,
      clients: [CLIENTE],
      client_count: 1,
    });
    vi.mocked(listCompanyNotes).mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  function montar() {
    render(
      <CompanyDetailModal
        groupId="grupo-A"
        company={EMPRESA}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );
  }

  it("o dialogo se anuncia nomeando o cliente e a empresa", async () => {
    montar();

    fireEvent.click(
      await screen.findByRole("button", { name: "Desvincular Carla Dias" }),
    );

    // O modal da empresa tambem e um `dialog` e continua aberto atras: pescar
    // pelo NOME e o que distingue os dois para quem so ouve.
    const dialogo = await screen.findByRole("dialog", {
      name: "Desvincular cliente",
    });
    expect(dialogo).toHaveTextContent("Carla Dias");
    expect(dialogo).toHaveTextContent("Transportes Alfa");
    expect(unassignClient).not.toHaveBeenCalled();
  });

  it("a frase promete que a conta CONTINUA cadastrada", async () => {
    // Este e o caso que a decisao pediu de verdade: desvincular nao destroi, e
    // o texto tem de dizer isso. Se a frase virar a de uma exclusao, reprova.
    montar();

    fireEvent.click(
      await screen.findByRole("button", { name: "Desvincular Carla Dias" }),
    );

    const dialogo = await screen.findByRole("dialog", {
      name: "Desvincular cliente",
    });
    expect(dialogo).toHaveTextContent(/continua cadastrada/);
    expect(dialogo).not.toHaveTextContent(/não pode ser desfeita/);
  });

  it("os dois botoes se chamam Cancelar e Desvincular, e nao Excluir", async () => {
    montar();

    fireEvent.click(
      await screen.findByRole("button", { name: "Desvincular Carla Dias" }),
    );
    const dialogo = await screen.findByRole("dialog", {
      name: "Desvincular cliente",
    });

    expect(
      within(dialogo).getByRole("button", { name: "Cancelar" }),
    ).toBeInTheDocument();
    expect(
      within(dialogo).getByRole("button", { name: "Desvincular" }),
    ).toBeInTheDocument();
    expect(
      within(dialogo).queryByRole("button", { name: "Excluir" }),
    ).not.toBeInTheDocument();
  });

  it("cancelar fecha o dialogo e o cliente continua vinculado", async () => {
    montar();

    fireEvent.click(
      await screen.findByRole("button", { name: "Desvincular Carla Dias" }),
    );
    const dialogo = await screen.findByRole("dialog", {
      name: "Desvincular cliente",
    });
    fireEvent.click(within(dialogo).getByRole("button", { name: "Cancelar" }));

    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Desvincular cliente" }),
      ).not.toBeInTheDocument(),
    );
    expect(unassignClient).not.toHaveBeenCalled();
    expect(screen.getByText("Carla Dias")).toBeInTheDocument();
  });

  it("so o «Desvincular» do dialogo chama o servico", async () => {
    vi.mocked(unassignClient).mockResolvedValue(undefined);
    montar();

    fireEvent.click(
      await screen.findByRole("button", { name: "Desvincular Carla Dias" }),
    );
    const dialogo = await screen.findByRole("dialog", {
      name: "Desvincular cliente",
    });
    fireEvent.click(
      within(dialogo).getByRole("button", { name: "Desvincular" }),
    );

    await waitFor(() =>
      expect(unassignClient).toHaveBeenCalledWith("grupo-A", "empresa-1", "cli-1"),
    );
  });
});

const GRUPO_ALFA: GroupResponse = {
  id: "grupo-A",
  name: "Grupo Alfa",
  description: "Transportadoras do litoral",
  notes: null,
  company_count: 1,
  created_at: "2026-09-01T12:00:00Z",
  updated_at: "2026-09-01T12:00:00Z",
};

const GRUPO_BETA: GroupResponse = {
  ...GRUPO_ALFA,
  id: "grupo-B",
  name: "Grupo Beta",
  description: null,
  company_count: 0,
};

const DETALHE_ALFA: GroupDetail = { ...GRUPO_ALFA, companies: [EMPRESA] };

const NOTA_GRUPO: GroupNote = {
  id: "nota-G",
  group_id: "grupo-A",
  author_id: "user-2",
  author_name: "Beto Reis",
  content: "Reunião trimestral marcada.",
  created_at: "2026-09-03T10:00:00Z",
};

describe("GroupsPage — a lista de grupos", () => {
  beforeEach(() => {
    vi.mocked(listGroups).mockResolvedValue([GRUPO_ALFA, GRUPO_BETA]);
    vi.mocked(getGroup).mockResolvedValue(DETALHE_ALFA);
    vi.mocked(listGroupNotes).mockResolvedValue([]);
    vi.mocked(getCompany).mockResolvedValue(DETALHE);
    vi.mocked(listCompanyNotes).mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("lista os grupos e pede que se escolha um", async () => {
    render(<GroupsPage />);

    expect(await screen.findByText("Grupo Alfa")).toBeInTheDocument();
    expect(screen.getByText("Grupo Beta")).toBeInTheDocument();
    expect(screen.getByText("Selecione um grupo")).toBeInTheDocument();
  });

  it("dá nome acessível ao campo de busca de grupos", async () => {
    // O campo só tinha `placeholder`, e placeholder some ao digitar: quem
    // volta ao campo depois não tem como saber o que ele filtra.
    render(<GroupsPage />);
    await screen.findByText("Grupo Alfa");

    expect(
      screen.getByRole("textbox", { name: "Pesquisar grupos" }),
    ).toBeInTheDocument();
  });

  it("a busca esconde o grupo que não casa com o texto", async () => {
    render(<GroupsPage />);
    await screen.findByText("Grupo Alfa");

    fireEvent.change(screen.getByRole("textbox", { name: "Pesquisar grupos" }), {
      target: { value: "beta" },
    });

    expect(screen.queryByText("Grupo Alfa")).not.toBeInTheDocument();
    expect(screen.getByText("Grupo Beta")).toBeInTheDocument();
  });

  it("escolher um grupo traz as empresas dele", async () => {
    render(<GroupsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /Grupo Alfa/ }));

    expect(await screen.findByText("Transportes Alfa")).toBeInTheDocument();
    expect(getGroup).toHaveBeenCalledWith("grupo-A");
  });

  /**
   * Os outros três `confirm()` da tela, agora diálogos da frota (D9.3). Os
   * três perguntavam com o nome interpolado — "Deletar o grupo \"X\"?" —, mas
   * numa caixa que o tema não alcança, que não diz que não volta e que não
   * tem como ser lida por caso nenhum. O que mudou de verdade é a última
   * parte: o `confirm()` do jsdom devolve `undefined`, então o caminho de
   * exclusão desta tela NUNCA foi exercido por teste até aqui.
   */
  it("os diálogos de grupo e de empresa se anunciam nomeando o que some", async () => {
    // O título do `Modal` é o NOME ACESSÍVEL do diálogo: o componente põe
    // `role="dialog"` com `aria-labelledby` apontando para o `<h2>` do título.
    // É a primeira coisa que o leitor de tela anuncia — e um título "Excluir"
    // seco deixaria quem não vê a tela sem saber o quê. O corpo também nomeia,
    // mas o corpo vem DEPOIS do nome, e só se a pessoa continuar.
    render(<GroupsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /Grupo Alfa/ }));
    await screen.findByText("Transportes Alfa");

    fireEvent.click(
      screen.getByRole("button", { name: "Excluir grupo Grupo Alfa" }),
    );
    expect(
      await screen.findByRole("dialog", { name: "Excluir grupo" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Excluir empresa Transportes Alfa" }),
    );
    expect(
      await screen.findByRole("dialog", { name: "Excluir empresa" }),
    ).toBeInTheDocument();
  });

  it("o diálogo da nota do grupo se anuncia nomeando o que some", async () => {
    vi.mocked(listGroupNotes).mockResolvedValue([NOTA_GRUPO]);
    render(<GroupsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /Grupo Alfa/ }));
    const botoes = await screen.findAllByRole("button", {
      name: "Deletar nota",
    });
    fireEvent.click(botoes[0]);

    // Nome exato: «Excluir nota» NÃO casa com «Excluir nota da empresa»,
    // e é essa distinção que o caso prende.
    expect(
      await screen.findByRole("dialog", { name: "Excluir nota" }),
    ).toBeInTheDocument();
  });

  it("excluir grupo abre diálogo que nomeia o grupo, e só apaga ao confirmar", async () => {
    vi.mocked(deleteGroup).mockResolvedValue(undefined);
    render(<GroupsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /Grupo Alfa/ }));
    await screen.findByText("Transportes Alfa");
    fireEvent.click(
      screen.getByRole("button", { name: "Excluir grupo Grupo Alfa" }),
    );

    const frase = await screen.findByText(/não pode ser desfeita/);
    expect(frase).toHaveTextContent("Grupo Alfa");
    expect(deleteGroup).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    await waitFor(() =>
      expect(screen.queryByText(/não pode ser desfeita/)).not.toBeInTheDocument(),
    );
    expect(deleteGroup).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole("button", { name: "Excluir grupo Grupo Alfa" }),
    );
    await screen.findByText(/não pode ser desfeita/);
    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));

    await waitFor(() => expect(deleteGroup).toHaveBeenCalledWith("grupo-A"));
  });

  it("excluir empresa abre diálogo que nomeia a empresa, e só apaga ao confirmar", async () => {
    vi.mocked(deleteCompany).mockResolvedValue(undefined);
    render(<GroupsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /Grupo Alfa/ }));
    await screen.findByText("Transportes Alfa");
    fireEvent.click(
      screen.getByRole("button", { name: "Excluir empresa Transportes Alfa" }),
    );

    const frase = await screen.findByText(/não pode ser desfeita/);
    expect(frase).toHaveTextContent("Transportes Alfa");
    expect(deleteCompany).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    await waitFor(() =>
      expect(screen.queryByText(/não pode ser desfeita/)).not.toBeInTheDocument(),
    );
    expect(deleteCompany).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole("button", { name: "Excluir empresa Transportes Alfa" }),
    );
    await screen.findByText(/não pode ser desfeita/);
    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));

    await waitFor(() =>
      expect(deleteCompany).toHaveBeenCalledWith("grupo-A", "empresa-1"),
    );
  });

  it("deletar nota do grupo nomeia a nota, e só apaga ao confirmar", async () => {
    vi.mocked(listGroupNotes).mockResolvedValue([NOTA_GRUPO]);
    vi.mocked(deleteGroupNote).mockResolvedValue(undefined);
    render(<GroupsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /Grupo Alfa/ }));
    const botoes = await screen.findAllByRole("button", {
      name: "Deletar nota",
    });
    fireEvent.click(botoes[0]);

    const frase = await screen.findByText(/não pode ser desfeita/);
    expect(frase).toHaveTextContent("Beto Reis");
    expect(deleteGroupNote).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));
    await waitFor(() =>
      expect(deleteGroupNote).toHaveBeenCalledWith("grupo-A", "nota-G"),
    );
  });
});
