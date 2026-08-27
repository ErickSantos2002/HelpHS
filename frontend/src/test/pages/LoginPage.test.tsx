import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

import LoginPage from "../../pages/auth/LoginPage";
import { useAuth } from "../../contexts/AuthContext";

const mockUseAuth = vi.mocked(useAuth);

/**
 * O rate limit do login (429) travou produção em 26/08 e o usuário só via
 * "Erro ao conectar com o servidor" — mensagem de rede para um bloqueio
 * proposital. Estes testes prendem a distinção: 429 mostra o motivo real
 * (o backend manda `detail` em português), erro de servidor segue genérico.
 */
describe("LoginPage — erro de login", () => {
  function preparaLogin(rejeicao: unknown) {
    mockUseAuth.mockReturnValue({
      login: vi.fn().mockRejectedValue(rejeicao),
      verifyMfa: vi.fn(),
    } as unknown as ReturnType<typeof useAuth>);
  }

  async function submete() {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    await userEvent.type(screen.getByLabelText("E-mail"), "alguem@exemplo.com");
    await userEvent.type(screen.getByLabelText("Senha"), "SenhaQualquer1");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
  }

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("mostra o motivo do bloqueio quando o login devolve 429", async () => {
    preparaLogin({
      response: {
        status: 429,
        data: { detail: "Muitas tentativas. Aguarde alguns minutos e tente novamente." },
      },
    });
    await submete();
    expect(
      await screen.findByText("Muitas tentativas. Aguarde alguns minutos e tente novamente."),
    ).toBeInTheDocument();
  });

  it("mantém a mensagem genérica para erro de servidor (500)", async () => {
    preparaLogin({ response: { status: 500, data: {} } });
    await submete();
    expect(
      await screen.findByText("Erro ao conectar com o servidor. Tente novamente."),
    ).toBeInTheDocument();
  });
});

/**
 * Sem o olho, um caractere trocado só aparece como "senha incorreta" — a
 * pessoa não tem como ver o que digitou. O teste prende o que importa: o
 * campo troca de máscara, guarda o que foi digitado e volta a esconder.
 */
describe("LoginPage — revelar a senha", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({
      login: vi.fn(),
      verifyMfa: vi.fn(),
    } as unknown as ReturnType<typeof useAuth>);
  });

  it("alterna entre esconder e mostrar a senha digitada", async () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    const senha = screen.getByLabelText("Senha");
    await userEvent.type(senha, "SenhaQualquer1");
    expect(senha).toHaveAttribute("type", "password");

    await userEvent.click(screen.getByRole("button", { name: "Mostrar senha" }));
    expect(senha).toHaveAttribute("type", "text");
    expect(senha).toHaveValue("SenhaQualquer1");

    await userEvent.click(screen.getByRole("button", { name: "Ocultar senha" }));
    expect(senha).toHaveAttribute("type", "password");
  });
});
