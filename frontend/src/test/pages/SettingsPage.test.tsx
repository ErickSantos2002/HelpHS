import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

// `vi.hoisted` porque o objeto é lido de dentro da fábrica do `vi.mock`, que
// sobe acima dos imports. Um `const` normal aqui embaixo ainda não existiria.
const sessao = vi.hoisted(() => ({
  user: { id: "u1", role: "admin", name: "Ana Souza" } as {
    id: string;
    role: string;
    name: string;
  },
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: sessao.user }),
}));
vi.mock("../../services/tagService", () => ({
  createTag: vi.fn(),
  deleteTag: vi.fn(),
  getTags: vi.fn(),
  updateTag: vi.fn(),
}));

import SettingsPage from "../../pages/settings/SettingsPage";
import * as tagService from "../../services/tagService";
import type { Tag } from "../../services/tagService";

/**
 * O que esta tela tinha, e que estes casos prendem.
 *
 * **Vinte e cinco classes de paleta crua em 449 linhas** — `slate` na escada de
 * texto inteira e `red` nos quatro degraus do aviso de exclusão, um banner
 * desenhado à mão que só tinha tom no tema escuro. **Quatro `<svg>` soltos**,
 * os quatro do mesmo desenho que o pacote já traz. E **um `text-white`** que
 * não estava sobre `bg-primary`: estava sobre uma cor que o USUÁRIO escolhe, e
 * sobre o amarelo da paleta padrão isso é claro sobre claro.
 *
 * Os dezesseis hexadecimais ficaram, e de propósito: são a paleta oferecida ao
 * usuário, dado do produto, não decisão de tema. Ver o comentário no `.tsx`.
 *
 * Nada disso é observável em happy-dom, que não aplica CSS nenhum. Por isso
 * nenhum caso aqui olha classe — trocar `sr-only` por `hidden` não esconde
 * coisa alguma de um `getByText`, e um caso que afirmasse a classe passaria com
 * o elemento invisível de verdade.
 *
 * O que os casos prendem é o que a migração podia ter quebrado sem ninguém
 * ver: a escolha de cor dizendo-se escolhida na árvore (antes ela existia só no
 * desenho do "certo"), o nome acessível dos dois botões de ícone e do campo de
 * cor personalizada, o aviso de exclusão que virou `Alert`, quem pode criar e
 * quem não pode, e os dois caminhos que a lista tem além do sucesso — o vazio e
 * o erro de carregamento.
 */

const URGENTE: Tag = {
  id: "t1",
  name: "Urgente",
  color: "#ef4444",
  created_by: "u1",
  created_at: "2026-09-01T12:00:00Z",
};

const BUG: Tag = {
  id: "t2",
  name: "Bug",
  color: "#6366f1",
  created_by: "u1",
  created_at: "2026-09-01T12:00:00Z",
};

/**
 * A cor do "certo" desenhado sobre a amostra escolhida.
 *
 * Ela é estilo EM LINHA, não classe: o happy-dom não aplica CSS nenhum, mas
 * aplica `style`. É o valor que a pessoa vê, e é ele que o caso mede.
 */
function corDoCerto(amostra: HTMLElement): string {
  const desenho = amostra.querySelector("svg");
  if (!desenho) throw new Error("a amostra escolhida não desenha o certo");
  return desenho.style.color;
}

async function montar(etiquetas: Tag[] = [URGENTE, BUG]) {
  vi.mocked(tagService.getTags).mockResolvedValue(etiquetas);

  render(<SettingsPage />);

  // O título é síncrono; o que precisa esperar é o `Spinner` sair, e quem
  // prova isso é o conteúdo da lista.
  await waitFor(() =>
    expect(screen.queryByRole("status")).not.toBeInTheDocument(),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  sessao.user = { id: "u1", role: "admin", name: "Ana Souza" };
});

describe("SettingsPage", () => {
  it("a lista traz o nome de cada etiqueta", async () => {
    await montar();
    expect(screen.getByText("Urgente")).toBeInTheDocument();
    expect(screen.getByText("Bug")).toBeInTheDocument();
  });

  it("cada botão de ícone diz DE QUAL etiqueta ele é", async () => {
    // Dez linhas na página davam dez botões chamados "Editar" — e o `title`
    // sozinho não desempata para quem navega pela lista de controles.
    await montar();
    expect(
      screen.getByRole("button", { name: "Editar Urgente" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Excluir Bug" }),
    ).toBeInTheDocument();
  });

  it("cliente não cria, não edita e não exclui", async () => {
    sessao.user = { id: "u9", role: "client", name: "Cliente" };
    await montar();

    expect(screen.getByText("Urgente")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Nova etiqueta/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Editar Urgente" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Excluir Urgente" }),
    ).not.toBeInTheDocument();
  });

  it("sem etiqueta nenhuma, a tela convida a criar a primeira", async () => {
    await montar([]);
    expect(
      screen.getByText(/Nenhuma etiqueta cadastrada/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Criar a primeira" }),
    ).toBeInTheDocument();
  });

  it("o convite do vazio não aparece para quem não pode criar", async () => {
    sessao.user = { id: "u9", role: "client", name: "Cliente" };
    await montar([]);

    expect(
      screen.getByText(/Nenhuma etiqueta cadastrada/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Criar a primeira" }),
    ).not.toBeInTheDocument();
  });

  it("quando a lista não carrega, a tela DIZ que não carregou", async () => {
    vi.mocked(tagService.getTags).mockRejectedValue(new Error("rede"));
    render(<SettingsPage />);

    expect(
      await screen.findByText("Não foi possível carregar as etiquetas."),
    ).toBeInTheDocument();
  });

  it("o campo de nome tem rótulo, e não só um placeholder", async () => {
    // O placeholder some exatamente quando a pessoa começa a digitar, e nunca
    // chega a quem não vê a tela.
    const user = userEvent.setup();
    await montar();

    await user.click(screen.getByRole("button", { name: /Nova etiqueta/ }));
    expect(
      await screen.findByLabelText("Nome da etiqueta"),
    ).toBeInTheDocument();
  });

  it("cada cor da paleta é um botão com o nome da cor", async () => {
    const user = userEvent.setup();
    await montar();

    await user.click(screen.getByRole("button", { name: /Nova etiqueta/ }));
    const dialogo = await screen.findByRole("dialog");

    expect(
      within(dialogo).getByRole("button", { name: "Índigo" }),
    ).toBeInTheDocument();
    expect(
      within(dialogo).getByRole("button", { name: "Amarelo" }),
    ).toBeInTheDocument();
  });

  it("a cor escolhida se declara na árvore, e não só no desenho do certo", async () => {
    // Antes o único sinal de "esta é a escolhida" era o `<svg>` do certo
    // desenhado por cima — e ele era `text-white` cravado, ilegível sobre o
    // amarelo. Quem não vê a tela ouvia dezesseis botões idênticos.
    const user = userEvent.setup();
    await montar();

    await user.click(screen.getByRole("button", { name: /Nova etiqueta/ }));
    const dialogo = await screen.findByRole("dialog");

    // O primeiro da paleta é o padrão de uma etiqueta nova.
    expect(
      within(dialogo).getByRole("button", { name: "Índigo", pressed: true }),
    ).toBeInTheDocument();
    expect(
      within(dialogo).getByRole("button", { name: "Amarelo", pressed: false }),
    ).toBeInTheDocument();

    await user.click(within(dialogo).getByRole("button", { name: "Amarelo" }));

    expect(
      within(dialogo).getByRole("button", { name: "Amarelo", pressed: true }),
    ).toBeInTheDocument();
    expect(
      within(dialogo).getByRole("button", { name: "Índigo", pressed: false }),
    ).toBeInTheDocument();
  });

  it("a cor personalizada é um campo com nome", async () => {
    // O rótulo visível era um desenho de `+`: o `<input type="color">` não
    // tinha nome nenhum na árvore de acessibilidade.
    const user = userEvent.setup();
    await montar();

    await user.click(screen.getByRole("button", { name: /Nova etiqueta/ }));
    const dialogo = await screen.findByRole("dialog");

    expect(
      within(dialogo).getByLabelText("Cor personalizada"),
    ).toBeInTheDocument();
  });

  it("o certo é claro sobre amostra escura e ESCURO sobre amostra clara", async () => {
    // O caso que faltava, e que deixou passar um mutante: trocar
    // `readableTextColor(c.hex)` de volta por branco fixo não reprovava em
    // nenhum dos outros doze casos.
    //
    // **Duas afirmações, e não uma.** Um caso que só olhasse o lado escuro
    // passaria com `text-white` de volta — e é justamente o defeito que a
    // migração tirou daqui.
    //
    // A escolha das duas cores não é livre: medida a luminância relativa
    // (WCAG) das dezesseis, **quinze caem do mesmo lado** e só o `#eab308`
    // ("Amarelo", 0,4975) cruza o limiar de 0,45. Ou seja, o branco fixo era
    // invisível em quinze amostras e ilegível numa — o pior modo de um defeito
    // de cor existir. Se um dia a paleta perder o Amarelo, este caso perde o
    // lado claro e passa a medir metade do que diz medir.
    const user = userEvent.setup();
    await montar();

    await user.click(screen.getByRole("button", { name: /Nova etiqueta/ }));
    const dialogo = await screen.findByRole("dialog");

    // Royal, `#1d4ed8`, luminância 0,107 — a amostra mais escura da paleta.
    await user.click(within(dialogo).getByRole("button", { name: "Royal" }));
    expect(
      corDoCerto(within(dialogo).getByRole("button", { name: "Royal" })),
    ).toBe("#ffffff");

    // Amarelo, `#eab308`, luminância 0,4975 — a única do outro lado.
    await user.click(within(dialogo).getByRole("button", { name: "Amarelo" }));
    expect(
      corDoCerto(within(dialogo).getByRole("button", { name: "Amarelo" })),
    ).toBe("#0f172a");
  });

  it("editar abre com o nome da etiqueta já preenchido", async () => {
    const user = userEvent.setup();
    await montar();

    await user.click(screen.getByRole("button", { name: "Editar Urgente" }));

    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByLabelText("Nome da etiqueta")).toHaveValue(
      "Urgente",
    );
  });

  it("excluir avisa que a ação é irreversível e nomeia a etiqueta", async () => {
    const user = userEvent.setup();
    await montar();

    await user.click(screen.getByRole("button", { name: "Excluir Urgente" }));

    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByText("Ação irreversível")).toBeInTheDocument();
    expect(
      within(dialogo).getByText(
        "Esta etiqueta será removida de todos os tickets que a utilizam.",
      ),
    ).toBeInTheDocument();
    expect(
      within(dialogo).getAllByText(/Urgente/).length,
    ).toBeGreaterThan(0);
    expect(
      within(dialogo).getByRole("button", { name: "Sim, excluir" }),
    ).toBeInTheDocument();
  });

  it("confirmar a exclusão chama o serviço e tira a etiqueta da lista", async () => {
    const user = userEvent.setup();
    await montar();
    vi.mocked(tagService.deleteTag).mockResolvedValue(undefined);

    await user.click(screen.getByRole("button", { name: "Excluir Urgente" }));
    const dialogo = await screen.findByRole("dialog");
    await user.click(
      within(dialogo).getByRole("button", { name: "Sim, excluir" }),
    );

    await waitFor(() =>
      expect(tagService.deleteTag).toHaveBeenCalledWith("t1"),
    );
    await waitFor(() =>
      expect(screen.queryByText("Urgente")).not.toBeInTheDocument(),
    );
  });
});
