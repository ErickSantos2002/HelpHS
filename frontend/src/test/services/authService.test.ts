import { describe, it, expect, vi, beforeEach } from "vitest";
import { loginApi, getMeApi, logoutApi } from "../../services/authService";
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
