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
