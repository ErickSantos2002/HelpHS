import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  loginApi,
  getMeApi,
  logoutApi,
  verifyEmailApi,
  resendVerificationApi,
  forgotPasswordApi,
  resetPasswordApi,
  isMfaChallenge,
  verifyMfaApi,
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

// ── Segundo fator ─────────────────────────────────────────────

/**
 * O desafio chega como 403 — mesmo status de "confirme seu e-mail" e de "conta
 * inativa". Distinguir pelo corpo, e não pelo status, é o que permite que a
 * tela de login continue tratando os outros dois casos como sempre tratou.
 */
describe("loginApi — desafio de segundo fator", () => {
  function erro403(data: unknown) {
    return { response: { status: 403, data } };
  }

  it("converte o desafio em valor de retorno em vez de erro", async () => {
    mockPost.mockRejectedValue(
      erro403({ detail: "Informe o código.", mfa_required: true, mfa_token: "abc", expires_in: 300 }),
    );

    const resultado = await loginApi({ email: "a@b.com", password: "x" });

    expect(isMfaChallenge(resultado)).toBe(true);
    expect(resultado).toMatchObject({ mfa_token: "abc" });
  });

  it("não confunde token com sessão", async () => {
    mockPost.mockResolvedValue({
      data: { access_token: "a", refresh_token: "r", token_type: "bearer" },
    });

    expect(isMfaChallenge(await loginApi({ email: "a@b.com", password: "x" }))).toBe(false);
  });

  it("deixa passar o 403 de e-mail não confirmado", async () => {
    // Sem `mfa_required` no corpo, o 403 continua sendo erro — senão a tela de
    // login perderia a mensagem que manda reenviar a confirmação.
    mockPost.mockRejectedValue(erro403({ detail: "Confirme seu e-mail para ativar a conta." }));

    await expect(loginApi({ email: "a@b.com", password: "x" })).rejects.toBeTruthy();
  });

  it("deixa passar um 403 que diz precisar de MFA mas não manda o token", async () => {
    // Corpo pela metade é resposta quebrada, não desafio: tratar como desafio
    // levaria a tela a um passo que não tem como ser concluído.
    mockPost.mockRejectedValue(erro403({ mfa_required: true }));

    await expect(loginApi({ email: "a@b.com", password: "x" })).rejects.toBeTruthy();
  });

  it("deixa passar 401 de senha errada", async () => {
    mockPost.mockRejectedValue({ response: { status: 401, data: { detail: "E-mail ou senha incorretos." } } });

    await expect(loginApi({ email: "a@b.com", password: "x" })).rejects.toBeTruthy();
  });
});

describe("verifyMfaApi", () => {
  it("troca desafio e código pelos tokens", async () => {
    mockPost.mockResolvedValue({
      data: { access_token: "novo", refresh_token: "r", token_type: "bearer" },
    });

    const tokens = await verifyMfaApi("desafio-1", "123456");

    expect(mockPost).toHaveBeenCalledWith("/auth/mfa/verify", {
      mfa_token: "desafio-1",
      code: "123456",
    });
    expect(tokens.access_token).toBe("novo");
  });
});
