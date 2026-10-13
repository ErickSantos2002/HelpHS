import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

// `vi.hoisted` porque o objeto é lido de dentro da fábrica do `vi.mock`, que
// sobe acima dos imports. Um `const` normal aqui embaixo ainda não existiria.
const sessao = vi.hoisted(() => ({
  user: { id: "u1abc2de3", role: "admin", name: "Ana Souza" } as {
    id: string;
    role: string;
    name: string;
  },
  // Espião estável: um `vi.fn()` criado dentro do `useAuth` seria outro a
  // cada render, e não daria para conferir que o contexto foi atualizado.
  updateAvatarUrl: vi.fn(),
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: sessao.user, updateAvatarUrl: sessao.updateAvatarUrl }),
}));
vi.mock("../../services/userService", () => ({
  changePassword: vi.fn(),
  completeOnboarding: vi.fn(),
  getMe: vi.fn(),
  removeAvatar: vi.fn(),
  updateMe: vi.fn(),
  uploadAvatar: vi.fn(),
}));
vi.mock("../../services/authService", () => ({
  activateMfaApi: vi.fn(),
  disableMfaApi: vi.fn(),
  getMfaStatusApi: vi.fn(),
  setupMfaApi: vi.fn(),
}));
vi.mock("../../services/equipmentService", () => ({
  lookupCnpj: vi.fn(),
  lookupCep: vi.fn(),
}));

import ProfilePage from "../../pages/profile/ProfilePage";
import * as userService from "../../services/userService";
import * as authService from "../../services/authService";
import type { UserSummary } from "../../services/userService";

/**
 * O que esta tela tinha, e que estes casos prendem.
 *
 * **Dois mapas locais indexados pela mesma chave** — `ROLE_LABEL` e
 * `ROLE_BADGE` —, o segundo pintando o papel `client` com nove classes de
 * paleta crua. **Um `INPUT_CLS` de uma linha só** repetido em **dez** campos,
 * e nenhum desses dez `<label>` tinha `htmlFor`: visualmente o rótulo ficava
 * ao lado, e para um leitor de tela **não existia relação nenhuma** entre ele
 * e o `<input>`. **Três `<svg>` soltos** e **quatro `bg-primary` com
 * `text-white`**, que é 3,83:1 nos dois temas.
 *
 * Nada disso é observável em happy-dom, que não aplica CSS. Por isso nenhum
 * caso aqui olha classe — olham o que a pessoa alcança: o rótulo que liga ao
 * campo, o nome acessível do botão de ícone, o que a árvore de
 * acessibilidade anuncia e o que ela deliberadamente não anuncia, e o que a
 * tela promete NÃO fazer (não mandar senha curta para a rede, não ligar o
 * segundo fator antes do código conferir).
 */

const PERFIL: UserSummary = {
  id: "u1abc2de3-0000-0000-0000-000000000000",
  name: "Ana Souza",
  email: "ana@exemplo.com",
  role: "admin",
  status: "active",
  phone: "(81) 99999-0000",
  department: "TI",
  avatar_url: null,
  last_login: "2026-09-01T12:00:00Z",
  lgpd_consent: true,
  lgpd_consent_at: "2026-01-10T12:00:00Z",
  company_name: null,
  cnpj: null,
  company_cep: null,
  company_address: null,
  company_city: null,
  company_state: null,
  api4com_extension: null,
  onboarding_completed: true,
  created_at: "2026-01-10T12:00:00Z",
  updated_at: "2026-01-10T12:00:00Z",
};

const MFA_DESLIGADO = { enabled: false, pending: false, available: true };

async function montar(perfil: Partial<UserSummary> = {}, mfa = MFA_DESLIGADO) {
  vi.mocked(userService.getMe).mockResolvedValue({ ...PERFIL, ...perfil });
  vi.mocked(authService.getMfaStatusApi).mockResolvedValue(mfa);

  render(<ProfilePage />);
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "Meu perfil" }),
    ).toBeInTheDocument(),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  sessao.user = { id: "u1abc2de3", role: "admin", name: "Ana Souza" };
});

describe("ProfilePage", () => {
  it("cada campo do formulário é alcançável pelo próprio rótulo", async () => {
    // Os dez `<label>` da versão anterior não tinham `htmlFor`: quem usa
    // leitor de tela ouvia "campo de edição, em branco" dez vezes seguidas.
    await montar();
    await userEvent.click(
      screen.getAllByRole("button", { name: "Editar" })[0],
    );

    expect(screen.getByLabelText("Nome completo")).toHaveValue("Ana Souza");
    expect(screen.getByLabelText("Telefone")).toHaveValue("(81) 99999-0000");
    expect(screen.getByLabelText("Departamento")).toHaveValue("TI");
  });

  it("o selo do papel diz o cargo por extenso", async () => {
    await montar();
    expect(screen.getByText("Administrador")).toBeInTheDocument();
  });

  it("o botão de trocar a foto tem nome, e não só um desenho", async () => {
    // O ícone é `aria-hidden`. Sem o rótulo o controle não tem nome nenhum.
    await montar();
    expect(
      screen.getByRole("button", { name: "Alterar foto" }),
    ).toBeInTheDocument();
  });

  it("o estado da conta é dito em texto, não só na cor do ponto", async () => {
    await montar();
    expect(screen.getByText("Ativo")).toBeInTheDocument();
  });

  it("a seção Empresa é só de cliente", async () => {
    await montar();
    expect(
      screen.queryByRole("heading", { name: "Empresa" }),
    ).not.toBeInTheDocument();
  });

  it("o cliente vê Empresa, e o aviso de cadastro incompleto não interrompe a leitura", async () => {
    // O aviso já está na tela quando ela termina de carregar — não responde a
    // ação nenhuma. Região viva anuncia MUDANÇA; anunciá-lo faria o leitor
    // ler a consequência antes da causa (emenda E12).
    sessao.user = { id: "c1", role: "client", name: "Cliente" };
    await montar({ role: "client", cnpj: null, company_cep: null });

    expect(
      screen.getByRole("heading", { name: "Empresa" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Complete o cadastro da sua empresa/)).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("o segundo fator só existe para o staff", async () => {
    // A ausência é medida pelo que a tela NÃO pergunta ao servidor: o cliente
    // nem chega a montar a seção, então o status do segundo fator não é
    // consultado. Um `queryBy` sozinho não distinguiria "não existe" de
    // "ainda não chegou".
    sessao.user = { id: "c1", role: "client", name: "Cliente" };
    await montar({ role: "client" });

    expect(authService.getMfaStatusApi).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("heading", { name: "Verificação em duas etapas" }),
    ).not.toBeInTheDocument();
  });

  it("cadastrar o segundo fator mostra a chave e NÃO liga nada antes do código", async () => {
    // A promessa está escrita na própria tela: "se o aplicativo não pareou,
    // nada muda e você não fica trancado fora".
    await montar();
    vi.mocked(authService.setupMfaApi).mockResolvedValue({
      secret: "ABCD EFGH IJKL MNOP",
      otpauth_uri: "otpauth://totp/HelpHS:ana",
    });

    // `findBy`: o status do segundo fator chega DEPOIS do perfil, então a
    // seção aparece num segundo quadro.
    await userEvent.click(await screen.findByRole("button", { name: "Ativar" }));

    expect(await screen.findByText("ABCD EFGH IJKL MNOP")).toBeInTheDocument();
    expect(screen.getByLabelText("Código do aplicativo")).toBeInTheDocument();
    expect(authService.activateMfaApi).not.toHaveBeenCalled();
  });

  it("desligar o segundo fator pede a senha por um campo com rótulo", async () => {
    // O campo dizia o que era só pelo `placeholder`, que some quando a pessoa
    // começa a digitar — e nunca chega a quem não vê a tela.
    await montar({}, { enabled: true, pending: false, available: true });

    await userEvent.click(await screen.findByRole("button", { name: "Desativar" }));
    expect(screen.getByLabelText("Sua senha atual")).toBeInTheDocument();
  });

  it("senha curta é recusada com o motivo, e não vai para a rede", async () => {
    await montar();
    await userEvent.click(
      screen.getByRole("button", { name: "Alterar senha" }),
    );

    await userEvent.type(screen.getByLabelText("Senha atual"), "SenhaAtual1");
    await userEvent.type(screen.getByLabelText("Nova senha"), "Ab1");
    await userEvent.type(screen.getByLabelText("Confirmar nova senha"), "Ab1");
    await userEvent.click(
      screen.getByRole("button", { name: "Alterar senha" }),
    );

    expect(
      await screen.findByText(/no mínimo 8 caracteres/),
    ).toBeInTheDocument();
    expect(userService.changePassword).not.toHaveBeenCalled();
  });

  it("a troca de senha bem-sucedida é ANUNCIADA, e não só pintada de verde", async () => {
    vi.mocked(userService.changePassword).mockResolvedValue(undefined as never);
    await montar();
    await userEvent.click(
      screen.getByRole("button", { name: "Alterar senha" }),
    );

    await userEvent.type(screen.getByLabelText("Senha atual"), "SenhaAtual1");
    await userEvent.type(screen.getByLabelText("Nova senha"), "NovaSenha1");
    await userEvent.type(
      screen.getByLabelText("Confirmar nova senha"),
      "NovaSenha1",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Alterar senha" }),
    );

    const aviso = await screen.findByRole("status");
    expect(aviso).toHaveTextContent("Senha alterada com sucesso!");
  });
});

// ── A própria foto: remover e cair nas iniciais ────────────────────────

const FOTO = "https://api.exemplo.com/api/v1/files/tok-da-foto";

function botaoRemover() {
  return screen.queryByRole("button", { name: "Remover foto" });
}

async function abrirConfirmacao() {
  await userEvent.click(botaoRemover()!);
  return screen.findByRole("dialog");
}

describe("ProfilePage — remover a própria foto", () => {
  it("o botão aparece quando há foto", async () => {
    await montar({ avatar_url: FOTO });
    expect(botaoRemover()).toBeInTheDocument();
  });

  it("o botão não aparece sem foto", async () => {
    await montar({ avatar_url: null });
    expect(botaoRemover()).not.toBeInTheDocument();
  });

  it("pede confirmação e não remove nada antes dela", async () => {
    await montar({ avatar_url: FOTO });

    const dialogo = await abrirConfirmacao();

    expect(dialogo).toHaveAccessibleName("Remover foto");
    expect(userService.removeAvatar).not.toHaveBeenCalled();
  });

  it("cancelar fecha o diálogo e a foto fica", async () => {
    await montar({ avatar_url: FOTO });
    await abrirConfirmacao();

    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(userService.removeAvatar).not.toHaveBeenCalled();
    expect(screen.getByAltText("Ana Souza")).toHaveAttribute("src", FOTO);
  });

  it("confirmar remove, volta às iniciais e atualiza a sessão", async () => {
    vi.mocked(userService.removeAvatar).mockResolvedValue();
    await montar({ avatar_url: FOTO });
    await abrirConfirmacao();

    await userEvent.click(screen.getByRole("button", { name: "Remover" }));

    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(userService.removeAvatar).toHaveBeenCalledTimes(1);
    expect(screen.queryByAltText("Ana Souza")).not.toBeInTheDocument();
    expect(screen.getByText("AS")).toBeInTheDocument();
    // O Topbar lê do contexto: sem isto ele seguiria mostrando a foto.
    expect(sessao.updateAvatarUrl).toHaveBeenCalledWith(null);
    expect(botaoRemover()).not.toBeInTheDocument();
  });

  it("o erro aparece no aviso da página e a foto fica", async () => {
    vi.mocked(userService.removeAvatar).mockRejectedValue({
      response: { data: { detail: "Volume indisponível." } },
    });
    await montar({ avatar_url: FOTO });
    await abrirConfirmacao();

    await userEvent.click(screen.getByRole("button", { name: "Remover" }));

    expect(await screen.findByText("Volume indisponível.")).toBeInTheDocument();
    expect(screen.getByAltText("Ana Souza")).toHaveAttribute("src", FOTO);
    expect(sessao.updateAvatarUrl).not.toHaveBeenCalled();
  });

  it("enquanto remove, um segundo clique não dispara outra remoção", async () => {
    let concluir: () => void = () => {};
    vi.mocked(userService.removeAvatar).mockReturnValue(
      new Promise<void>((resolve) => {
        concluir = resolve;
      }),
    );
    await montar({ avatar_url: FOTO });
    await abrirConfirmacao();
    const remover = screen.getByRole("button", { name: "Remover" });

    await userEvent.click(remover);
    // `fireEvent` despacha o clique mesmo em botão desabilitado — quem o
    // descarta é o React, porque o `loading` desabilitou o botão no primeiro.
    fireEvent.click(remover);
    fireEvent.click(remover);

    expect(userService.removeAvatar).toHaveBeenCalledTimes(1);
    expect(remover).toBeDisabled();
    expect(screen.getByRole("button", { name: "Alterar foto" })).toBeDisabled();

    concluir();
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });
});

describe("ProfilePage — a foto que não carrega", () => {
  it("cai nas iniciais quando a imagem falha", async () => {
    await montar({ avatar_url: FOTO });

    fireEvent.error(screen.getByAltText("Ana Souza"));

    expect(screen.queryByAltText("Ana Souza")).not.toBeInTheDocument();
    expect(screen.getByText("AS")).toBeInTheDocument();
    // A referência continua gravada: dá para remover mesmo sem ver a foto.
    expect(botaoRemover()).toBeInTheDocument();
  });

  it("uma foto nova depois da falha é tentada normalmente", async () => {
    const nova = { ...PERFIL, avatar_url: "https://api.exemplo.com/api/v1/files/tok-nova" };
    vi.mocked(userService.uploadAvatar).mockResolvedValue(nova);
    await montar({ avatar_url: FOTO });
    fireEvent.error(screen.getByAltText("Ana Souza"));

    const arquivo = new File(["x"], "eu.png", { type: "image/png" });
    const campo = document.querySelector<HTMLInputElement>('input[type="file"]')!;
    await userEvent.upload(campo, arquivo);

    expect(await screen.findByAltText("Ana Souza")).toHaveAttribute("src", nova.avatar_url);
  });

  it("editar o perfil não troca a foto pela chave crua da resposta", async () => {
    // O `PATCH /users/me` devolve `avatars/<id>.png`, que o serviço vira
    // `<API>/avatars/...` — rota que não existe. A foto da tela tem que ficar.
    vi.mocked(userService.updateMe).mockResolvedValue({
      ...PERFIL,
      name: "Ana Souza",
      avatar_url: "https://api.exemplo.com/api/v1/avatars/u1.png",
    });
    await montar({ avatar_url: FOTO });

    await userEvent.click(screen.getAllByRole("button", { name: "Editar" })[0]);
    await userEvent.click(screen.getByRole("button", { name: /salvar/i }));

    await waitFor(() => expect(userService.updateMe).toHaveBeenCalled());
    expect(await screen.findByAltText("Ana Souza")).toHaveAttribute("src", FOTO);
  });
});
