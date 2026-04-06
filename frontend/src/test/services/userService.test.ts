import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getUsers,
  createUser,
  updateUser,
  setUserStatus,
  anonymizeUser,
  deleteUser,
  updateLGPDConsent,
  getTechnicians,
} from "../../services/userService";
import { api } from "../../services/api";

vi.mock("../../services/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockGet = vi.mocked(api.get);
const mockPost = vi.mocked(api.post);
const mockPatch = vi.mocked(api.patch);
const mockDelete = vi.mocked(api.delete);

const user = {
  id: "u1",
  name: "João Silva",
  email: "joao@test.com",
  role: "client",
  status: "active",
  phone: null,
  department: null,
  avatar_url: null,
  last_login: null,
  lgpd_consent: true,
  lgpd_consent_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getUsers", () => {
  it("calls GET /users with no filters", async () => {
    mockGet.mockResolvedValue({
      data: { items: [user], total: 1, limit: 20, offset: 0 },
    });

    const result = await getUsers();

    expect(mockGet).toHaveBeenCalledWith("/users?");
    expect(result.items).toHaveLength(1);
  });

  it("appends role, status and search filters", async () => {
    mockGet.mockResolvedValue({
      data: { items: [], total: 0, limit: 20, offset: 0 },
    });

    await getUsers({ role: "technician", status: "active", search: "ana" });

    const url = mockGet.mock.calls[0][0] as string;
    expect(url).toContain("role=technician");
    expect(url).toContain("status=active");
    expect(url).toContain("search=ana");
  });
});

describe("createUser", () => {
  it("posts to /users and returns the created user", async () => {
    mockPost.mockResolvedValue({ data: user });

    const result = await createUser({
      name: "João Silva",
      email: "joao@test.com",
      password: "Senha@123",
      role: "client",
      lgpd_consent: true,
    });

    expect(mockPost).toHaveBeenCalledWith(
      "/users",
      expect.objectContaining({
        name: "João Silva",
        role: "client",
      }),
    );
    expect(result.id).toBe("u1");
  });
});

describe("updateUser", () => {
  it("patches /users/:id with the payload", async () => {
    mockPatch.mockResolvedValue({ data: { ...user, name: "João Atualizado" } });

    const result = await updateUser("u1", { name: "João Atualizado" });

    expect(mockPatch).toHaveBeenCalledWith("/users/u1", {
      name: "João Atualizado",
    });
    expect(result.name).toBe("João Atualizado");
  });
});

describe("setUserStatus", () => {
  it("patches /users/:id/status", async () => {
    mockPatch.mockResolvedValue({ data: { ...user, status: "suspended" } });

    await setUserStatus("u1", "suspended");

    expect(mockPatch).toHaveBeenCalledWith("/users/u1/status", {
      status: "suspended",
    });
  });
});

describe("anonymizeUser", () => {
  it("posts to /users/:id/anonymize", async () => {
    mockPost.mockResolvedValue({ data: user });

    await anonymizeUser("u1");

    expect(mockPost).toHaveBeenCalledWith("/users/u1/anonymize");
  });
});

describe("deleteUser", () => {
  it("calls DELETE /users/:id", async () => {
    mockDelete.mockResolvedValue({});

    await deleteUser("u1");

    expect(mockDelete).toHaveBeenCalledWith("/users/u1");
  });
});

describe("updateLGPDConsent", () => {
  it("patches /users/me/lgpd-consent", async () => {
    mockPatch.mockResolvedValue({ data: { ...user, lgpd_consent: false } });

    await updateLGPDConsent(false);

    expect(mockPatch).toHaveBeenCalledWith("/users/me/lgpd-consent", {
      lgpd_consent: false,
    });
  });
});

describe("getTechnicians", () => {
  it("calls GET /users with role=technician, status=active, limit=100", async () => {
    mockGet.mockResolvedValue({
      data: { items: [user], total: 1, limit: 100, offset: 0 },
    });

    const result = await getTechnicians();

    expect(mockGet).toHaveBeenCalledWith(
      "/users?role=technician&status=active&limit=100",
    );
    expect(result).toHaveLength(1);
  });
});
