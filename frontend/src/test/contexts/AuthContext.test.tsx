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
}));

import { tokenStorage } from "../../services/api";
import { loginApi, getMeApi, logoutApi } from "../../services/authService";

const mockTokenStorage = vi.mocked(tokenStorage);
const mockLoginApi = vi.mocked(loginApi);
const mockGetMeApi = vi.mocked(getMeApi);
const mockLogoutApi = vi.mocked(logoutApi);

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
