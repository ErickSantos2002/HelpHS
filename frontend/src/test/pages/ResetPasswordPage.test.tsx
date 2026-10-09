import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/authService", () => ({
  resetPasswordApi: vi.fn(),
}));

import ResetPasswordPage from "../../pages/auth/ResetPasswordPage";
import { resetPasswordApi } from "../../services/authService";

const mockReset = vi.mocked(resetPasswordApi);

function renderiza() {
  render(
    <MemoryRouter initialEntries={["/redefinir-senha?token=tok-123"]}>
      <Routes>
        <Route path="/redefinir-senha" element={<ResetPasswordPage />} />
        <Route path="/login" element={<p>Tela de acesso</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

/**
 * Os rótulos dos botões contêm o nome do campo ("Mostrar nova senha"), então
 * o campo é sempre buscado pelo rótulo exato e pelo seletor `input` — nunca
 * por texto parcial, que pegaria o botão junto.
 */
function campos() {
  return {
    senha: screen.getByLabelText("Nova senha", { exact: true, selector: "input" }),
    confirmacao: screen.getByLabelText("Confirmar nova senha", {
      exact: true,
      selector: "input",
    }),
  };
}

describe("ResetPasswordPage — mostrar/ocultar senha", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("os dois campos começam ocultos", () => {
    renderiza();
    const { senha, confirmacao } = campos();
    expect(senha).toHaveAttribute("type", "password");
    expect(confirmacao).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Mostrar nova senha" })).toHaveAttribute(
      "type",
      "button",
    );
    expect(
      screen.getByRole("button", { name: "Mostrar confirmação da senha" }),
    ).toHaveAttribute("type", "button");
  });

  it("cada controle alterna só o seu campo, o rótulo acompanha e o valor fica", async () => {
    renderiza();
    const { senha, confirmacao } = campos();
    await userEvent.type(senha, "SenhaNova1");
    await userEvent.type(confirmacao, "SenhaNova1");

    await userEvent.click(screen.getByRole("button", { name: "Mostrar nova senha" }));
    expect(senha).toHaveAttribute("type", "text");
    expect(confirmacao).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Ocultar nova senha" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Mostrar confirmação da senha" }),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Mostrar confirmação da senha" }));
    expect(confirmacao).toHaveAttribute("type", "text");
    expect(senha).toHaveAttribute("type", "text");

    await userEvent.click(screen.getByRole("button", { name: "Ocultar nova senha" }));
    expect(senha).toHaveAttribute("type", "password");
    expect(confirmacao).toHaveAttribute("type", "text");

    await userEvent.click(screen.getByRole("button", { name: "Ocultar confirmação da senha" }));
    expect(confirmacao).toHaveAttribute("type", "password");

    expect(senha).toHaveValue("SenhaNova1");
    expect(confirmacao).toHaveValue("SenhaNova1");
    expect(mockReset).not.toHaveBeenCalled();
  });

  it("Enter e Espaço no controle alternam sem enviar o formulário", async () => {
    renderiza();
    const { senha, confirmacao } = campos();
    await userEvent.type(senha, "SenhaNova1");
    await userEvent.type(confirmacao, "SenhaNova1");

    const botaoSenha = screen.getByRole("button", { name: "Mostrar nova senha" });
    botaoSenha.focus();
    await userEvent.keyboard("{Enter}");
    expect(senha).toHaveAttribute("type", "text");
    await userEvent.keyboard(" ");
    expect(senha).toHaveAttribute("type", "password");

    const botaoConfirmacao = screen.getByRole("button", {
      name: "Mostrar confirmação da senha",
    });
    botaoConfirmacao.focus();
    await userEvent.keyboard(" ");
    expect(confirmacao).toHaveAttribute("type", "text");
    await userEvent.keyboard("{Enter}");
    expect(confirmacao).toHaveAttribute("type", "password");

    expect(mockReset).not.toHaveBeenCalled();
    expect(screen.queryByText("Tela de acesso")).not.toBeInTheDocument();
  });

  it("os controles entram na ordem de tabulação logo depois do seu campo", async () => {
    renderiza();
    const { senha, confirmacao } = campos();
    // autoFocus continua no primeiro campo.
    expect(senha).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole("button", { name: "Mostrar nova senha" })).toHaveFocus();
    await userEvent.tab();
    expect(confirmacao).toHaveFocus();
    await userEvent.tab();
    expect(
      screen.getByRole("button", { name: "Mostrar confirmação da senha" }),
    ).toHaveFocus();
  });
});

describe("ResetPasswordPage — envio", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("continua validando antes de chamar a API", async () => {
    renderiza();
    const { senha, confirmacao } = campos();
    await userEvent.type(senha, "SenhaNova1");
    await userEvent.type(confirmacao, "SenhaOutra1");
    await userEvent.click(screen.getByRole("button", { name: "Salvar nova senha" }));

    expect(await screen.findByText("As senhas não coincidem.")).toBeInTheDocument();
    expect(mockReset).not.toHaveBeenCalled();
  });

  it("envia token e senha e volta para o acesso, também com a senha visível", async () => {
    mockReset.mockResolvedValue("ok");
    renderiza();
    const { senha, confirmacao } = campos();
    await userEvent.type(senha, "SenhaNova1");
    await userEvent.type(confirmacao, "SenhaNova1");
    await userEvent.click(screen.getByRole("button", { name: "Mostrar nova senha" }));
    await userEvent.click(screen.getByRole("button", { name: "Salvar nova senha" }));

    expect(await screen.findByText("Tela de acesso")).toBeInTheDocument();
    expect(mockReset).toHaveBeenCalledTimes(1);
    expect(mockReset).toHaveBeenCalledWith("tok-123", "SenhaNova1");
  });
});
