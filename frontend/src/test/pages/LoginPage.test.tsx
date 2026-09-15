import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

/**
 * O bloqueio por tentativas dura 15 minutos e o backend informa o tempo exato
 * no Retry-After. O relógio conta ao vivo até o desbloqueio — sem ele, a
 * pessoa insiste no escuro (foi o incidente de 26/08 e a reclamação de 15/09).
 */
describe("LoginPage — contagem regressiva do bloqueio", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  async function submeteBloqueado(retryAfter: string) {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({
      login: vi.fn().mockRejectedValue({
        response: { status: 429, headers: { "retry-after": retryAfter }, data: {} },
      }),
      verifyMfa: vi.fn(),
    } as unknown as ReturnType<typeof useAuth>);
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    // fireEvent, não userEvent: o userEvent espera em timers e trava sob o
    // relógio falso (happy-dom). O preenchimento é síncrono de propósito.
    fireEvent.change(screen.getByLabelText("E-mail"), {
      target: { value: "alguem@exemplo.com" },
    });
    fireEvent.change(screen.getByLabelText("Senha"), {
      target: { value: "SenhaQualquer1" },
    });
    // O relógio falso liga ANTES do click, para o setInterval do bloqueio já
    // nascer nele — só timers e Date; mockar mais que isso trava o ambiente.
    vi.useFakeTimers({
      toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date"],
    });
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));
    // A rejeição do login assenta por microtask (não faked) — o act vazio basta.
    await act(async () => {});
  }

  it("mostra o relógio com o tempo do Retry-After e trava o Entrar", async () => {
    await submeteBloqueado("90");
    expect(screen.getByText(/tentar novamente em/)).toBeInTheDocument();
    expect(screen.getByText("1:30")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Entrar" })).toBeDisabled();
  });

  it("o relógio anda um segundo por vez", async () => {
    await submeteBloqueado("90");
    screen.getByText("1:30");
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByText("1:29")).toBeInTheDocument();
  });

  it("ao zerar, o aviso some e o Entrar volta a funcionar", async () => {
    await submeteBloqueado("2");
    screen.getByText(/tentar novamente em/);
    await act(async () => {
      vi.advanceTimersByTime(2500);
    });
    expect(screen.queryByText(/tentar novamente em/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Entrar" })).toBeEnabled();
  });
});
