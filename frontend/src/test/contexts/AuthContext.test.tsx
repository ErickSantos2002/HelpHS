import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AuthProvider, useAuth } from "../../contexts/AuthContext";

// Mock the api module (tokenStorage)
vi.mock("../../services/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  tokenStorage: {
    getAccess: vi.fn(),
    getRefresh: vi.fn(),
    set: vi.fn(),
    clear: vi.fn(),
  },
}));

// Mock authService functions
vi.mock("../../services/authService", () => ({
  loginApi: vi.fn(),
  getMeApi: vi.fn(),
  logoutApi: vi.fn(),
  verifyMfaApi: vi.fn(),
  // Predicado puro, sem I/O: vale a implementação real, senão cada teste teria
  // de lembrar de devolver `false` e o esquecimento viraria erro obscuro.
  isMfaChallenge: (r: unknown) => (r as { mfa_required?: boolean })?.mfa_required === true,
}));

import { useState } from "react";
import { tokenStorage } from "../../services/api";
import { loginApi, getMeApi, logoutApi, verifyMfaApi } from "../../services/authService";

const mockTokenStorage = vi.mocked(tokenStorage);
const mockLoginApi = vi.mocked(loginApi);
const mockGetMeApi = vi.mocked(getMeApi);
const mockLogoutApi = vi.mocked(logoutApi);
const mockVerifyMfaApi = vi.mocked(verifyMfaApi);

/** Consumidor que expõe o resultado do login e o segundo passo. */
function MfaConsumer() {
  const { login, verifyMfa } = useAuth();
  const [resultado, setResultado] = useState("");
  return (
    <div>
      <span data-testid="resultado">{resultado}</span>
      <button
        onClick={async () => {
          const r = await login("suelen@test.com", "pass");
          setResultado(r.mfaRequired ? `desafio:${r.mfaToken}` : "sessao");
        }}
      >
        Login
      </button>
      <button onClick={() => verifyMfa("desafio-1", "123456")}>Verificar</button>
    </div>
  );
}

// Helper: renders a component that consumes useAuth
function TestConsumer() {
  const { user, isAuthenticated, isLoading, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="loading">{isLoading ? "loading" : "ready"}</span>
      <span data-testid="auth">{isAuthenticated ? "yes" : "no"}</span>
      <span data-testid="name">{user?.name ?? "none"}</span>
      <button onClick={() => login("admin@test.com", "pass")}>Login</button>
      <button onClick={() => logout()}>Logout</button>
    </div>
  );
}

function renderWithProvider() {
  return render(
    <AuthProvider>
      <TestConsumer />
    </AuthProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("AuthProvider — session restore", () => {
  it("sets isLoading=false and user=null when no token in storage", async () => {
    mockTokenStorage.getAccess.mockReturnValue(null);

    renderWithProvider();

    await waitFor(() =>
      expect(screen.getByTestId("loading")).toHaveTextContent("ready"),
    );
    expect(screen.getByTestId("auth")).toHaveTextContent("no");
    expect(screen.getByTestId("name")).toHaveTextContent("none");
  });

  it("restores user from stored token on mount", async () => {
    mockTokenStorage.getAccess.mockReturnValue("stored-token");
    mockGetMeApi.mockResolvedValue({
      id: "u1",
      name: "Admin",
      email: "admin@test.com",
      role: "admin",
      onboarding_completed: true,
    });

    renderWithProvider();

    await waitFor(() =>
      expect(screen.getByTestId("loading")).toHaveTextContent("ready"),
    );
    expect(screen.getByTestId("auth")).toHaveTextContent("yes");
    expect(screen.getByTestId("name")).toHaveTextContent("Admin");
  });

  it("clears session when stored token is invalid", async () => {
    mockTokenStorage.getAccess.mockReturnValue("expired-token");
    mockGetMeApi.mockRejectedValue(new Error("401 Unauthorized"));

    renderWithProvider();

    await waitFor(() =>
      expect(screen.getByTestId("loading")).toHaveTextContent("ready"),
    );
    expect(mockTokenStorage.clear).toHaveBeenCalled();
    expect(screen.getByTestId("auth")).toHaveTextContent("no");
  });
});

describe("AuthProvider — login", () => {
  it("calls loginApi then getMeApi, sets user on success", async () => {
    mockTokenStorage.getAccess.mockReturnValue(null);
    mockLoginApi.mockResolvedValue({
      access_token: "new-access",
      refresh_token: "new-refresh",
      token_type: "bearer",
    });
    mockGetMeApi.mockResolvedValueOnce({
      id: "u1",
      name: "Admin",
      email: "admin@test.com",
      role: "admin",
      onboarding_completed: true,
    });

    renderWithProvider();
    await waitFor(() =>
      expect(screen.getByTestId("loading")).toHaveTextContent("ready"),
    );

    await userEvent.click(screen.getByRole("button", { name: "Login" }));

    expect(mockLoginApi).toHaveBeenCalledWith({
      email: "admin@test.com",
      password: "pass",
    });
    expect(mockTokenStorage.set).toHaveBeenCalledWith(
      "new-access",
      "new-refresh",
    );
    expect(screen.getByTestId("auth")).toHaveTextContent("yes");
    expect(screen.getByTestId("name")).toHaveTextContent("Admin");
  });
});

describe("AuthProvider — logout", () => {
  it("calls logoutApi, clears storage and resets user", async () => {
    mockTokenStorage.getAccess.mockReturnValue("token");
    mockGetMeApi.mockResolvedValue({
      id: "u1",
      name: "Admin",
      email: "admin@test.com",
      role: "admin",
      onboarding_completed: true,
    });
    mockLogoutApi.mockResolvedValue(undefined);

    renderWithProvider();
    await waitFor(() =>
      expect(screen.getByTestId("name")).toHaveTextContent("Admin"),
    );

    await userEvent.click(screen.getByRole("button", { name: "Logout" }));

    expect(mockLogoutApi).toHaveBeenCalled();
    expect(mockTokenStorage.clear).toHaveBeenCalled();
    expect(screen.getByTestId("auth")).toHaveTextContent("no");
    expect(screen.getByTestId("name")).toHaveTextContent("none");
  });
});

describe("useAuth", () => {
  it("throws when used outside AuthProvider", () => {
    // Suppress expected console.error from React
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => {});

    expect(() => render(<TestConsumer />)).toThrow(
      "useAuth must be used inside <AuthProvider>",
    );

    consoleError.mockRestore();
  });
});


// ── Segundo fator ─────────────────────────────────────────────

describe("AuthProvider — segundo fator", () => {
  function renderMfa() {
    return render(
      <AuthProvider>
        <MfaConsumer />
      </AuthProvider>,
    );
  }

  it("devolve o desafio e NAO grava sessao nenhuma", async () => {
    // A assercao que mais importa: senha certa sem codigo nao e sessao. Gravar
    // token aqui deixaria a pessoa "logada" sem ter passado pelo segundo fator.
    mockTokenStorage.getAccess.mockReturnValue(null);
    mockLoginApi.mockResolvedValue({
      mfa_required: true,
      mfa_token: "desafio-1",
      expires_in: 300,
    });

    renderMfa();
    await userEvent.click(screen.getByRole("button", { name: "Login" }));

    await waitFor(() =>
      expect(screen.getByTestId("resultado")).toHaveTextContent("desafio:desafio-1"),
    );
    expect(mockTokenStorage.set).not.toHaveBeenCalled();
    expect(mockGetMeApi).not.toHaveBeenCalled();
  });

  it("o segundo passo estabelece a sessao pelo mesmo caminho do login simples", async () => {
    mockTokenStorage.getAccess.mockReturnValue(null);
    mockVerifyMfaApi.mockResolvedValue({
      access_token: "pos-mfa",
      refresh_token: "refresh-pos-mfa",
      token_type: "bearer",
    });
    mockGetMeApi.mockResolvedValueOnce({
      id: "u9",
      name: "Suelen",
      email: "suelen@test.com",
      role: "technician",
      onboarding_completed: true,
    });

    renderMfa();
    await userEvent.click(screen.getByRole("button", { name: "Verificar" }));

    await waitFor(() =>
      expect(mockTokenStorage.set).toHaveBeenCalledWith("pos-mfa", "refresh-pos-mfa"),
    );
    expect(mockVerifyMfaApi).toHaveBeenCalledWith("desafio-1", "123456");
    expect(mockGetMeApi).toHaveBeenCalled();
  });
});

// ── Perfil em memoria, token exposto e caminhos de erro ────────
//
// Ramos que faltavam: os dois `?? null` do avatar, os dois
// `prev ? ... : prev` de markOnboardingComplete/updateAvatarUrl e o
// `setToken(null)` do catch da restauracao.

/** Consumidor do perfil: le avatar/onboarding/token e deixa muta-los. */
function PerfilConsumer() {
  const {
    user,
    token,
    isAuthenticated,
    isLoading,
    login,
    logout,
    markOnboardingComplete,
    updateAvatarUrl,
  } = useAuth();
  return (
    <div>
      <span data-testid="loading">{isLoading ? "loading" : "ready"}</span>
      <span data-testid="auth">{isAuthenticated ? "yes" : "no"}</span>
      <span data-testid="token">{token ?? "sem-token"}</span>
      <span data-testid="nome">{user ? user.name : "nenhum"}</span>
      {/* String() de proposito: distingue `null` normalizado de `undefined`. */}
      <span data-testid="avatar">{user ? String(user.avatar_url) : "nenhum"}</span>
      <span data-testid="onboarding">
        {user ? String(user.onboarding_completed) : "nenhum"}
      </span>
      <button onClick={() => markOnboardingComplete()}>Concluir</button>
      <button onClick={() => updateAvatarUrl("/media/novo.png")}>Trocar avatar</button>
      <button onClick={() => updateAvatarUrl(null)}>Remover avatar</button>
      <button onClick={() => login("admin@test.com", "pass")}>Entrar</button>
      <button onClick={() => logout()}>Sair</button>
    </div>
  );
}

function renderPerfil() {
  return render(
    <AuthProvider>
      <PerfilConsumer />
    </AuthProvider>,
  );
}

/** Consumidor que captura o erro em vez de deixar a promessa estourar. */
function ErroConsumer() {
  const { login, verifyMfa, isAuthenticated, token } = useAuth();
  const [erro, setErro] = useState("");
  return (
    <div>
      <span data-testid="erro">{erro || "sem-erro"}</span>
      <span data-testid="auth">{isAuthenticated ? "yes" : "no"}</span>
      <span data-testid="token">{token ?? "sem-token"}</span>
      <button
        onClick={async () => {
          try {
            await login("admin@test.com", "pass");
            setErro("passou");
          } catch (e) {
            setErro((e as Error).message);
          }
        }}
      >
        Login
      </button>
      <button
        onClick={async () => {
          try {
            await verifyMfa("desafio-1", "000000");
            setErro("passou");
          } catch (e) {
            setErro((e as Error).message);
          }
        }}
      >
        Verificar
      </button>
    </div>
  );
}

function renderErro() {
  return render(
    <AuthProvider>
      <ErroConsumer />
    </AuthProvider>,
  );
}

describe("AuthProvider — restauracao: avatar e token expostos", () => {
  it("preserva o avatar que o servidor manda ao restaurar a sessao", async () => {
    mockTokenStorage.getAccess.mockReturnValue("stored-token");
    mockGetMeApi.mockResolvedValue({
      id: "u1",
      name: "Admin",
      email: "admin@test.com",
      role: "admin",
      avatar_url: "/media/avatars/u1.png",
      onboarding_completed: true,
    });

    renderPerfil();

    await waitFor(() =>
      expect(screen.getByTestId("loading")).toHaveTextContent("ready"),
    );
    expect(screen.getByTestId("avatar")).toHaveTextContent("/media/avatars/u1.png");
  });

  it("normaliza avatar ausente para null, e nao para undefined", async () => {
    // O tipo AuthUser promete `string | null`. Sem o `?? null` o campo viraria
    // `undefined` e quem compara com null erraria em silencio.
    mockTokenStorage.getAccess.mockReturnValue("stored-token");
    mockGetMeApi.mockResolvedValue({
      id: "u1",
      name: "Admin",
      email: "admin@test.com",
      role: "admin",
      onboarding_completed: false,
    });

    renderPerfil();

    await waitFor(() =>
      expect(screen.getByTestId("loading")).toHaveTextContent("ready"),
    );
    expect(screen.getByTestId("avatar")).toHaveTextContent("null");
    expect(screen.getByTestId("onboarding")).toHaveTextContent("false");
  });

  it("expoe no contexto o token que veio do storage", async () => {
    mockTokenStorage.getAccess.mockReturnValue("stored-token");
    mockGetMeApi.mockResolvedValue({
      id: "u1",
      name: "Admin",
      email: "admin@test.com",
      role: "admin",
      onboarding_completed: true,
    });

    renderPerfil();

    await waitFor(() =>
      expect(screen.getByTestId("token")).toHaveTextContent("stored-token"),
    );
  });

  it("zera o token em memoria quando a restauracao falha", async () => {
    // O token chega a entrar no estado antes do getMe. Se o setToken(null) do
    // catch sumisse, o contexto seguiria entregando um token ja invalido.
    mockTokenStorage.getAccess.mockReturnValue("expired-token");
    mockGetMeApi.mockRejectedValue(new Error("401 Unauthorized"));

    renderPerfil();

    await waitFor(() =>
      expect(screen.getByTestId("loading")).toHaveTextContent("ready"),
    );
    expect(screen.getByTestId("token")).toHaveTextContent("sem-token");
    expect(screen.getByTestId("nome")).toHaveTextContent("nenhum");
  });
});

describe("AuthProvider — avatar no login", () => {
  it("preserva o avatar que o servidor manda ao estabelecer a sessao", async () => {
    mockTokenStorage.getAccess.mockReturnValue(null);
    mockLoginApi.mockResolvedValue({
      access_token: "new-access",
      refresh_token: "new-refresh",
      token_type: "bearer",
    });
    mockGetMeApi.mockResolvedValueOnce({
      id: "u1",
      name: "Admin",
      email: "admin@test.com",
      role: "admin",
      avatar_url: "/media/avatars/u1.png",
      onboarding_completed: true,
    });

    renderPerfil();
    await waitFor(() =>
      expect(screen.getByTestId("loading")).toHaveTextContent("ready"),
    );

    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    await waitFor(() =>
      expect(screen.getByTestId("avatar")).toHaveTextContent("/media/avatars/u1.png"),
    );
    expect(screen.getByTestId("token")).toHaveTextContent("new-access");
  });

  it("normaliza para null o avatar ausente na resposta do login", async () => {
    mockTokenStorage.getAccess.mockReturnValue(null);
    mockLoginApi.mockResolvedValue({
      access_token: "new-access",
      refresh_token: "new-refresh",
      token_type: "bearer",
    });
    mockGetMeApi.mockResolvedValueOnce({
      id: "u1",
      name: "Admin",
      email: "admin@test.com",
      role: "admin",
      onboarding_completed: true,
    });

    renderPerfil();
    await waitFor(() =>
      expect(screen.getByTestId("loading")).toHaveTextContent("ready"),
    );

    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    await waitFor(() => expect(screen.getByTestId("auth")).toHaveTextContent("yes"));
    expect(screen.getByTestId("avatar")).toHaveTextContent("null");
  });
});

describe("AuthProvider — markOnboardingComplete", () => {
  it("marca o onboarding do usuario atual sem tocar nos outros campos", async () => {
    mockTokenStorage.getAccess.mockReturnValue("stored-token");
    mockGetMeApi.mockResolvedValue({
      id: "u1",
      name: "Admin",
      email: "admin@test.com",
      role: "admin",
      avatar_url: "/media/avatars/u1.png",
      onboarding_completed: false,
    });

    renderPerfil();
    await waitFor(() =>
      expect(screen.getByTestId("onboarding")).toHaveTextContent("false"),
    );

    await userEvent.click(screen.getByRole("button", { name: "Concluir" }));

    expect(screen.getByTestId("onboarding")).toHaveTextContent("true");
    expect(screen.getByTestId("nome")).toHaveTextContent("Admin");
    expect(screen.getByTestId("avatar")).toHaveTextContent("/media/avatars/u1.png");
  });

  it("nao inventa usuario quando nao ha sessao", async () => {
    // Sem o guarda `prev ? ... : prev`, espalhar null criaria um objeto so com
    // onboarding_completed e o isAuthenticated (!!user) viraria true.
    mockTokenStorage.getAccess.mockReturnValue(null);

    renderPerfil();
    await waitFor(() =>
      expect(screen.getByTestId("loading")).toHaveTextContent("ready"),
    );

    await userEvent.click(screen.getByRole("button", { name: "Concluir" }));

    expect(screen.getByTestId("auth")).toHaveTextContent("no");
    expect(screen.getByTestId("nome")).toHaveTextContent("nenhum");
    expect(screen.getByTestId("onboarding")).toHaveTextContent("nenhum");
  });
});

describe("AuthProvider — updateAvatarUrl", () => {
  it("troca o avatar preservando o resto do usuario", async () => {
    mockTokenStorage.getAccess.mockReturnValue("stored-token");
    mockGetMeApi.mockResolvedValue({
      id: "u1",
      name: "Admin",
      email: "admin@test.com",
      role: "admin",
      avatar_url: "/media/avatars/antigo.png",
      onboarding_completed: true,
    });

    renderPerfil();
    await waitFor(() =>
      expect(screen.getByTestId("avatar")).toHaveTextContent("/media/avatars/antigo.png"),
    );

    await userEvent.click(screen.getByRole("button", { name: "Trocar avatar" }));

    expect(screen.getByTestId("avatar")).toHaveTextContent("/media/novo.png");
    expect(screen.getByTestId("nome")).toHaveTextContent("Admin");
    expect(screen.getByTestId("onboarding")).toHaveTextContent("true");
  });

  it("aceita null para remover o avatar sem derrubar a sessao", async () => {
    mockTokenStorage.getAccess.mockReturnValue("stored-token");
    mockGetMeApi.mockResolvedValue({
      id: "u1",
      name: "Admin",
      email: "admin@test.com",
      role: "admin",
      avatar_url: "/media/avatars/antigo.png",
      onboarding_completed: true,
    });

    renderPerfil();
    await waitFor(() =>
      expect(screen.getByTestId("avatar")).toHaveTextContent("/media/avatars/antigo.png"),
    );

    await userEvent.click(screen.getByRole("button", { name: "Remover avatar" }));

    expect(screen.getByTestId("avatar")).toHaveTextContent("null");
    expect(screen.getByTestId("auth")).toHaveTextContent("yes");
  });

  it("nao inventa usuario quando nao ha sessao", async () => {
    mockTokenStorage.getAccess.mockReturnValue(null);

    renderPerfil();
    await waitFor(() =>
      expect(screen.getByTestId("loading")).toHaveTextContent("ready"),
    );

    await userEvent.click(screen.getByRole("button", { name: "Trocar avatar" }));

    expect(screen.getByTestId("auth")).toHaveTextContent("no");
    expect(screen.getByTestId("avatar")).toHaveTextContent("nenhum");
  });
});

describe("AuthProvider — caminhos de erro do login", () => {
  it("propaga a falha de credencial e nao grava sessao nenhuma", async () => {
    mockTokenStorage.getAccess.mockReturnValue(null);
    mockLoginApi.mockRejectedValue(new Error("Credenciais invalidas"));

    renderErro();
    await userEvent.click(screen.getByRole("button", { name: "Login" }));

    await waitFor(() =>
      expect(screen.getByTestId("erro")).toHaveTextContent("Credenciais invalidas"),
    );
    expect(mockTokenStorage.set).not.toHaveBeenCalled();
    expect(mockGetMeApi).not.toHaveBeenCalled();
    expect(screen.getByTestId("auth")).toHaveTextContent("no");
  });

  it("com o /users/me falhando, deixa token gravado e sessao sem usuario", async () => {
    // Fixa o comportamento de HOJE, que nao e o desejavel: estabelecerSessao
    // grava os tokens ANTES do getMe e nao tem catch, entao a falha do
    // /users/me deixa token no storage sem usuario -- e ninguem limpa.
    mockTokenStorage.getAccess.mockReturnValue(null);
    mockLoginApi.mockResolvedValue({
      access_token: "meio-access",
      refresh_token: "meio-refresh",
      token_type: "bearer",
    });
    mockGetMeApi.mockRejectedValue(new Error("500 Internal Server Error"));

    renderErro();
    await userEvent.click(screen.getByRole("button", { name: "Login" }));

    await waitFor(() =>
      expect(screen.getByTestId("erro")).toHaveTextContent("500 Internal Server Error"),
    );
    expect(mockTokenStorage.set).toHaveBeenCalledWith("meio-access", "meio-refresh");
    expect(mockTokenStorage.clear).not.toHaveBeenCalled();
    expect(screen.getByTestId("auth")).toHaveTextContent("no");
    expect(screen.getByTestId("token")).toHaveTextContent("meio-access");
  });

  it("propaga o codigo de segundo fator errado sem gravar sessao", async () => {
    mockTokenStorage.getAccess.mockReturnValue(null);
    mockVerifyMfaApi.mockRejectedValue(new Error("Codigo invalido"));

    renderErro();
    await userEvent.click(screen.getByRole("button", { name: "Verificar" }));

    await waitFor(() =>
      expect(screen.getByTestId("erro")).toHaveTextContent("Codigo invalido"),
    );
    expect(mockTokenStorage.set).not.toHaveBeenCalled();
    expect(mockGetMeApi).not.toHaveBeenCalled();
    expect(screen.getByTestId("auth")).toHaveTextContent("no");
  });
});

describe("AuthProvider — logout limpa o token em memoria", () => {
  it("zera o token do contexto, e nao so o do storage", async () => {
    mockTokenStorage.getAccess.mockReturnValue("stored-token");
    mockGetMeApi.mockResolvedValue({
      id: "u1",
      name: "Admin",
      email: "admin@test.com",
      role: "admin",
      onboarding_completed: true,
    });
    mockLogoutApi.mockResolvedValue(undefined);

    renderPerfil();
    await waitFor(() =>
      expect(screen.getByTestId("token")).toHaveTextContent("stored-token"),
    );

    await userEvent.click(screen.getByRole("button", { name: "Sair" }));

    await waitFor(() =>
      expect(screen.getByTestId("token")).toHaveTextContent("sem-token"),
    );
    expect(screen.getByTestId("nome")).toHaveTextContent("nenhum");
    expect(screen.getByTestId("avatar")).toHaveTextContent("nenhum");
  });
});
