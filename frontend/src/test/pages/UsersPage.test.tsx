import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

// O papel de QUEM edita decide se o campo de ramal aparece, e ele e lido a
// cada render dentro do `useAuth` — por isso a variavel troca por teste, e nao
// a fabrica do mock (que o vitest ica uma vez so).
let papelDeQuemEdita = "admin";
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "eu", role: papelDeQuemEdita, name: "Quem Edita" } }),
}));
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
import { campoDeMenu, escolherNoMenu, opcoesDoMenu } from "../helpers/menu";

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

/**
 * Por que "Administrador" e "Inativo" já precisaram de um filtro na busca.
 *
 * Pela D9.2 os dois filtros da barra eram o campo nativo do navegador, e o
 * nativo desenha TODAS as opções na árvore o tempo todo. As duas palavras
 * ficavam em dois lugares — o selo da linha e a opção do filtro —, então os
 * casos que falam da LINHA passavam `{ ignore: "script, style, option" }` para
 * tirar a opção da busca. Não `getAllByText(...)[0]`: esse continuaria passando
 * com o selo apagado, que é o que eles existem para reprovar.
 *
 * O `SelectMenu` desfez o empate: o painel mora num portal e só existe com o
 * menu ABERTO, então numa página em repouso a palavra do selo é a única
 * ocorrência. O guardião saiu, e não por limpeza: as linhas do painel são
 * `role="option"` sem serem elemento `option`, logo um seletor de tag não as
 * alcança — ele não guardava mais nada. O que ele protegia segue protegido, e
 * de mais perto: agora uma segunda ocorrência REPROVA o caso em vez de ser
 * ignorada em silêncio.
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
  api4com_extension: null,
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
  beforeEach(() => {
    papelDeQuemEdita = "admin";
  });

  it("o papel de cada usuário está escrito, e não só pintado", async () => {
    // O selo saiu de um mapa local de classes cruas para o `Badge` do pacote.
    // O que não pode ter mudado é o que sobra para quem não enxerga a cor: a
    // PALAVRA — e que ela seja a palavra do rótulo, e não o valor do backend.
    await montar();
    expect(await screen.findByText("Administrador")).toBeInTheDocument();
    expect(screen.getByText("Técnico")).toBeInTheDocument();
    expect(screen.getByText("Cliente")).toBeInTheDocument();
    // O valor cru do backend não aparece em lugar nenhum — nem na linha, nem
    // dentro do filtro, onde ele é o `value` e nunca o texto.
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

  it("cada filtro tem nome próprio, e não se anuncia pelo valor escolhido", async () => {
    // O defeito que a D9.2 fecha. O `FilterSelect` não repassava `label`: com
    // um valor escolhido, os dois filtros desta barra viravam "Técnico" e
    // "Ativo" para quem usa leitor de tela, sem dizer de que filtro eram — e
    // "Ativo" é também a palavra do selo de cada linha.
    await montar();

    expect(screen.getByRole("combobox", { name: "Perfil" })).toBeInTheDocument();
    expect(
      screen.getByRole("combobox", { name: "Status da conta" }),
    ).toBeInTheDocument();
  });

  it("escolher o perfil no filtro pede ao serviço aquele papel", async () => {
    await montar();

    // O auxiliar escolhe pelo RÓTULO — o `selectOptions` escolhia pelo valor.
    // O que o caso prende continua sendo o VALOR que chega ao serviço: a
    // travessia "Técnico" → `technician` é justamente o que pode quebrar.
    escolherNoMenu(screen.getByRole("combobox", { name: "Perfil" }), "Técnico");

    await waitFor(() =>
      expect(userService.getUsers).toHaveBeenLastCalledWith(
        expect.objectContaining({ role: "technician" }),
      ),
    );
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
    // Pela D9.3 o aviso deixou de ser bloco com casca e virou prosa. O caso
    // mede a FRASE — e mede as duas coisas NO MESMO parágrafo, porque é ali
    // que o nome tem de estar: o cartão de pré-visualização também escreve
    // "Ana Souza", e um caso que só contasse ocorrências na tela continuaria
    // passando com a frase sem nome nenhum.
    const frase = within(dialogo).getByText(/não pode ser desfeita/);
    expect(frase).toHaveTextContent("Ana Souza");
    // O e-mail é o que desambigua homônimos, e ele vem do cartão de
    // pré-visualização — o bloco que confirma QUEM vai ser apagado.
    expect(within(dialogo).getByText("ana@exemplo.com")).toBeInTheDocument();
    expect(userService.deleteUser).not.toHaveBeenCalled();

    await user.click(within(dialogo).getByRole("button", { name: "Excluir" }));

    await waitFor(() => expect(userService.deleteUser).toHaveBeenCalledWith("u1"));
    await waitFor(() =>
      expect(screen.queryByText("ana@exemplo.com")).not.toBeInTheDocument(),
    );
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
      await screen.findByRole("button", { name: "Excluir Ana Souza" }),
    );

    expect(
      await screen.findByRole("dialog", { name: "Excluir usuário" }),
    ).toBeInTheDocument();
  });

  it("cancelar fecha o diálogo e não exclui ninguém", async () => {
    // A outra metade da D9.3: o diálogo é a única barreira entre o clique e a
    // exclusão. Se "Cancelar" chamasse o serviço — ou se o diálogo continuasse
    // aberto —, a barreira não existe.
    const user = userEvent.setup();
    await montar();

    await user.click(
      await screen.findByRole("button", { name: "Excluir Ana Souza" }),
    );
    const dialogo = await screen.findByRole("dialog");
    await user.click(within(dialogo).getByRole("button", { name: "Cancelar" }));

    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(userService.deleteUser).not.toHaveBeenCalled();
    expect(screen.getByText("ana@exemplo.com")).toBeInTheDocument();
  });

  it("editar abre com o usuário já dentro", async () => {
    const user = userEvent.setup();
    await montar();

    await user.click(await screen.findByRole("button", { name: "Editar Bruno Lima" }));

    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByText("bruno@exemplo.com")).toBeInTheDocument();
    expect(within(dialogo).getByLabelText("Nome *")).toHaveValue("Bruno Lima");
    // O perfil também vem preenchido. A leitura é por TEXTO porque é o texto
    // que o gatilho mostra: `toHaveValue("technician")` num botão falharia
    // sempre, já que o jest-dom lê `button.value` e ali é `""` (medido).
    expect(within(dialogo).getByRole("combobox", { name: "Perfil *" })).toHaveTextContent(
      "Técnico",
    );
  });

  it("o perfil escolhido no formulário manda na validação do telefone e chega ao serviço", async () => {
    // O campo de perfil deixou de ser nativo e passou a falar com o
    // react-hook-form por um `Controller`. Se o valor não chegasse lá, o
    // `superRefine` julgaria o papel ERRADO: admin barrado por falta de
    // telefone, ou cliente sem telefone passando. As duas metades ficam no
    // MESMO formulário, com o telefone vazio o tempo todo — o que muda entre
    // uma e outra é só o perfil.
    const user = userEvent.setup();
    vi.mocked(userService.createUser).mockResolvedValue({
      ...ANA,
      id: "u9",
      name: "Dora Melo",
      email: "dora@exemplo.com",
    });
    await montar();

    await user.click(screen.getByRole("button", { name: "Novo usuário" }));
    const dialogo = await screen.findByRole("dialog", { name: "Novo usuário" });
    await user.type(within(dialogo).getByLabelText("Nome *"), "Dora Melo");
    await user.type(
      within(dialogo).getByLabelText("E-mail *"),
      "dora@exemplo.com",
    );
    await user.type(within(dialogo).getByLabelText("Senha *"), "Senha1234");

    // O formulário nasce em "Cliente", e cliente sem telefone é recusado.
    const perfil = within(dialogo).getByRole("combobox", { name: "Perfil *" });
    expect(perfil).toHaveTextContent("Cliente");
    await user.click(
      within(dialogo).getByRole("button", { name: "Criar usuário" }),
    );
    expect(
      await within(dialogo).findByText("Telefone é obrigatório para cliente."),
    ).toBeInTheDocument();
    expect(userService.createUser).not.toHaveBeenCalled();

    // Trocar para "Administrador" muda o que o mesmo formulário exige.
    escolherNoMenu(perfil, "Administrador");
    await waitFor(() => expect(perfil).toHaveTextContent("Administrador"));

    await user.click(
      within(dialogo).getByRole("button", { name: "Criar usuário" }),
    );

    // E o valor que chega ao serviço é o do backend, não o rótulo da tela.
    await waitFor(() =>
      expect(userService.createUser).toHaveBeenCalledWith(
        expect.objectContaining({ role: "admin" }),
      ),
    );
  });


  // ── Ramal API4COM ───────────────────────────────────────────
  //
  // O campo decide COM QUAL IDENTIDADE uma ligação sai. Quem o controla
  // controla de quem a chamada parece ter vindo — por isso a tela só o mostra
  // a admin, e por isso "não aparece" é caso de teste tanto quanto "aparece".
  // A autoridade continua sendo o backend; aqui se prende a superfície.

  it("admin vê o ramal ao editar um técnico, e ao editar outro admin", async () => {
    const user = userEvent.setup();
    comUsuarios([ANA, BRUNO]);
    await montar();

    await user.click(await screen.findByRole("button", { name: "Editar Bruno Lima" }));
    expect(
      within(await screen.findByRole("dialog")).getByLabelText("Ramal API4COM"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await user.click(await screen.findByRole("button", { name: "Editar Ana Souza" }));
    expect(
      within(await screen.findByRole("dialog")).getByLabelText("Ramal API4COM"),
    ).toBeInTheDocument();
  });

  it("editar um cliente não oferece ramal — cliente não origina ligação", async () => {
    const user = userEvent.setup();
    await montar();

    await user.click(await screen.findByRole("button", { name: "Editar Carla Dias" }));

    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).queryByLabelText("Ramal API4COM")).not.toBeInTheDocument();
  });

  it("técnico não recebe o controle de ramal, nem para si", async () => {
    papelDeQuemEdita = "technician";
    const user = userEvent.setup();
    await montar();

    await user.click(await screen.findByRole("button", { name: "Editar Bruno Lima" }));

    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).queryByLabelText("Ramal API4COM")).not.toBeInTheDocument();
    // E o campo não pode viajar escondido no corpo: o backend devolveria 403
    // num salvamento que só mexeu no nome.
    await user.click(within(dialogo).getByRole("button", { name: "Salvar alterações" }));
    await waitFor(() => expect(userService.updateUser).toHaveBeenCalled());
    expect(vi.mocked(userService.updateUser).mock.calls[0][1]).not.toHaveProperty(
      "api4com_extension",
    );
  });

  it("admin define o ramal de quem não tinha", async () => {
    const user = userEvent.setup();
    vi.mocked(userService.updateUser).mockResolvedValue({ ...BRUNO, api4com_extension: "1018" });
    await montar();

    await user.click(await screen.findByRole("button", { name: "Editar Bruno Lima" }));
    const dialogo = await screen.findByRole("dialog");
    const campo = within(dialogo).getByLabelText("Ramal API4COM");
    expect(campo).toHaveValue("");

    await user.type(campo, "1018");
    await user.click(within(dialogo).getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() =>
      expect(userService.updateUser).toHaveBeenCalledWith(
        "u2",
        expect.objectContaining({ api4com_extension: "1018" }),
      ),
    );
  });

  it("admin troca um ramal por outro", async () => {
    const user = userEvent.setup();
    comUsuarios([{ ...BRUNO, api4com_extension: "1018" }]);
    vi.mocked(userService.updateUser).mockResolvedValue({ ...BRUNO, api4com_extension: "1019" });
    await montar();

    await user.click(await screen.findByRole("button", { name: "Editar Bruno Lima" }));
    const dialogo = await screen.findByRole("dialog");
    const campo = within(dialogo).getByLabelText("Ramal API4COM");
    expect(campo).toHaveValue("1018");

    await user.clear(campo);
    await user.type(campo, "1019");
    await user.click(within(dialogo).getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() =>
      expect(userService.updateUser).toHaveBeenCalledWith(
        "u2",
        expect.objectContaining({ api4com_extension: "1019" }),
      ),
    );
  });

  it("esvaziar o campo REMOVE o vínculo, e manda null — não string vazia", async () => {
    // A distinção é do backend: a string vazia seria um VALOR, e o índice
    // único a trataria como tal — o segundo usuário esvaziado colidiria com o
    // primeiro. Quem remove manda null.
    const user = userEvent.setup();
    comUsuarios([{ ...BRUNO, api4com_extension: "1018" }]);
    vi.mocked(userService.updateUser).mockResolvedValue({ ...BRUNO, api4com_extension: null });
    await montar();

    await user.click(await screen.findByRole("button", { name: "Editar Bruno Lima" }));
    const dialogo = await screen.findByRole("dialog");
    await user.clear(within(dialogo).getByLabelText("Ramal API4COM"));
    await user.click(within(dialogo).getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() =>
      expect(userService.updateUser).toHaveBeenCalledWith(
        "u2",
        expect.objectContaining({ api4com_extension: null }),
      ),
    );
  });

  it("o ramal viaja como texto, e zero à esquerda sobrevive", async () => {
    // Converter para número faria 0700 virar 700, e a ligação sairia de outro
    // lugar. O fornecedor declara o ramal como identificador textual.
    const user = userEvent.setup();
    vi.mocked(userService.updateUser).mockResolvedValue({ ...BRUNO, api4com_extension: "0700" });
    await montar();

    await user.click(await screen.findByRole("button", { name: "Editar Bruno Lima" }));
    const dialogo = await screen.findByRole("dialog");
    await user.type(within(dialogo).getByLabelText("Ramal API4COM"), "0700");
    await user.click(within(dialogo).getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() => expect(userService.updateUser).toHaveBeenCalled());
    const enviado = vi.mocked(userService.updateUser).mock.calls[0][1].api4com_extension;
    expect(enviado).toBe("0700");
    expect(typeof enviado).toBe("string");
  });

  it("ramal já usado por outra pessoa é dito com as palavras do servidor", async () => {
    const user = userEvent.setup();
    vi.mocked(userService.updateUser).mockRejectedValue({
      response: { status: 409, data: { detail: "Este ramal já está vinculado a outro usuário." } },
    });
    await montar();

    await user.click(await screen.findByRole("button", { name: "Editar Bruno Lima" }));
    const dialogo = await screen.findByRole("dialog");
    await user.type(within(dialogo).getByLabelText("Ramal API4COM"), "1018");
    await user.click(within(dialogo).getByRole("button", { name: "Salvar alterações" }));

    expect(
      await within(dialogo).findByText("Este ramal já está vinculado a outro usuário."),
    ).toBeInTheDocument();
  });

  it("rebaixar a cliente fecha o campo do ramal", async () => {
    // O backend recusa com 422 quem vira cliente ainda tendo ramal — de
    // propósito. Mandar null junto apagaria o vínculo em silêncio, e quem
    // rebaixasse por engano perderia o dado sem ver.
    const user = userEvent.setup();
    comUsuarios([{ ...BRUNO, api4com_extension: "1018", phone: "+5581999999999" }]);
    await montar();

    await user.click(await screen.findByRole("button", { name: "Editar Bruno Lima" }));
    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByLabelText("Ramal API4COM")).toBeInTheDocument();

    escolherNoMenu(campoDeMenu("Perfil *"), "Cliente");

    await waitFor(() =>
      expect(within(dialogo).queryByLabelText("Ramal API4COM")).not.toBeInTheDocument(),
    );
  });

  it("promover a técnico já abre o campo na mesma edição", async () => {
    const user = userEvent.setup();
    comUsuarios([{ ...CARLA, status: "active", phone: "+5581999999999" }]);
    await montar();

    await user.click(await screen.findByRole("button", { name: "Editar Carla Dias" }));
    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).queryByLabelText("Ramal API4COM")).not.toBeInTheDocument();

    escolherNoMenu(campoDeMenu("Perfil *"), "Técnico");

    expect(await within(dialogo).findByLabelText("Ramal API4COM")).toBeInTheDocument();
  });

  it("o filtro de estado oferece só os dois valores que o servidor aceita", async () => {
    // "suspended" já morou no `userService` sem nunca ter existido no banco, e
    // a opção que ele gerava derrubava a lista com 422 — o FastAPI recusa na
    // validação do Query, antes do handler. Anonimizado é real, mas filtrar
    // por ele não é uso de tela.
    await montar();

    // A lista agora vive num portal e só existe com o menu ABERTO — por isso a
    // leitura é `opcoesDoMenu`, que abre antes de ler. A conta é a mesma de
    // antes, e é ela que prende a lista curta: exatamente três linhas, na
    // ordem, com "Anonimizado" de fora.
    const filtro = screen.getByRole("combobox", { name: "Status da conta" });
    expect(opcoesDoMenu(filtro)).toEqual(["Status", "Ativo", "Inativo"]);
  });
});
