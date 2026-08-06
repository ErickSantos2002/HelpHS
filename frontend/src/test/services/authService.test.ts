import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  loginApi,
  getMeApi,
  logoutApi,
  verifyEmailApi,
  resendVerificationApi,
  forgotPasswordApi,
  resetPasswordApi,
} from "../../services/authService";
import { api } from "../../services/api";

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

const mockPost = vi.mocked(api.post);
const mockGet = vi.mocked(api.get);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("loginApi", () => {
  it("posts to /auth/login and returns token response", async () => {
    const tokens = {
      access_token: "access123",
      refresh_token: "refresh456",
      token_type: "bearer",
    };
    mockPost.mockResolvedValue({ data: tokens });

    const result = await loginApi({
      email: "admin@test.com",
      password: "pass",
    });

    expect(mockPost).toHaveBeenCalledWith("/auth/login", {
      email: "admin@test.com",
      password: "pass",
    });
    expect(result).toEqual(tokens);
  });
});

describe("getMeApi", () => {
  it("gets /users/me and returns user data", async () => {
    const user = {
      id: "u1",
      name: "Admin",
      email: "admin@test.com",
      role: "admin",
    };
    mockGet.mockResolvedValue({ data: user });

    const result = await getMeApi();

    expect(mockGet).toHaveBeenCalledWith("/users/me");
    expect(result).toEqual(user);
  });
});

describe("logoutApi", () => {
  it("posts to /auth/logout", async () => {
    mockPost.mockResolvedValue({});

    await logoutApi();

    expect(mockPost).toHaveBeenCalledWith("/auth/logout");
  });

  it("silently ignores errors on logout", async () => {
    mockPost.mockRejectedValue(new Error("network error"));

    await expect(logoutApi()).resolves.toBeUndefined();
  });
});

// ── Confirmação de e-mail e recuperação de senha ──────────────

describe("verifyEmailApi", () => {
  it("envia o token para /auth/verify-email", async () => {
    mockPost.mockResolvedValue({ data: { message: "E-mail confirmado." } });

    const msg = await verifyEmailApi("tok123");

    expect(mockPost).toHaveBeenCalledWith("/auth/verify-email", { token: "tok123" });
    expect(msg).toBe("E-mail confirmado.");
  });
});

describe("resendVerificationApi", () => {
  it("envia o e-mail para /auth/resend-verification", async () => {
    mockPost.mockResolvedValue({ data: { message: "ok" } });

    await resendVerificationApi("cliente@test.com");

    expect(mockPost).toHaveBeenCalledWith("/auth/resend-verification", {
      email: "cliente@test.com",
    });
  });
});

describe("forgotPasswordApi", () => {
  it("envia o e-mail para /auth/forgot-password", async () => {
    mockPost.mockResolvedValue({ data: { message: "instruções enviadas" } });

    const msg = await forgotPasswordApi("cliente@test.com");

    expect(mockPost).toHaveBeenCalledWith("/auth/forgot-password", {
      email: "cliente@test.com",
    });
    expect(msg).toBe("instruções enviadas");
  });
});

describe("resetPasswordApi", () => {
  it("envia token e nova senha para /auth/reset-password", async () => {
    mockPost.mockResolvedValue({ data: { message: "Senha alterada." } });

    await resetPasswordApi("tok123", "NovaSenha@1");

    expect(mockPost).toHaveBeenCalledWith("/auth/reset-password", {
      token: "tok123",
      password: "NovaSenha@1",
    });
  });
});
