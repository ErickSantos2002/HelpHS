import fs from "node:fs";
import path from "node:path";

import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getUsers,
  createUser,
  updateUser,
  setUserStatus,
  anonymizeUser,
  deleteUser,
  removeAvatar,
  removeUserAvatar,
  getExibicaoDaFoto,
  setExibicaoDaFoto,
  updateLGPDConsent,
  getTechnicians,
  USER_STATUSES,
} from "../../services/userService";
import { api } from "../../services/api";

vi.mock("../../services/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockGet = vi.mocked(api.get);
const mockPost = vi.mocked(api.post);
const mockPatch = vi.mocked(api.patch);
const mockDelete = vi.mocked(api.delete);
const mockPut = vi.mocked(api.put);

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
    mockPatch.mockResolvedValue({ data: { ...user, status: "inactive" } });

    await setUserStatus("u1", "inactive");

    expect(mockPatch).toHaveBeenCalledWith("/users/u1/status", {
      status: "inactive",
    });
  });
});

describe("USER_STATUSES", () => {
  // O caso que existia aqui afirmava que setUserStatus("u1", "suspended")
  // funcionava. Passava verde contra um servidor que nao existe: "suspended"
  // nunca esteve no enum do banco, e o filtro que oferecia a opcao devolvia
  // 422 -- a lista de usuarios simplesmente nao carregava.
  //
  // O teste que entra no lugar nao repete a lista a mao: uma lista copiada
  // volta a divergir do mesmo jeito. Ele le o enum do backend e compara.
  it("e exatamente o enum UserStatus do backend", () => {
    // O vitest roda com o cwd em `frontend/` (e o CI tambem, via
    // working-directory), entao o backend fica um nivel acima.
    const caminho = path.resolve(
      process.cwd(),
      "../backend/app/models/models.py",
    );
    expect(fs.existsSync(caminho), `nao encontrei ${caminho}`).toBe(true);
    const models = fs.readFileSync(caminho, "utf-8");

    const linhas = models.split(/\r?\n/);
    const inicio = linhas.findIndex((l) => l.startsWith("class UserStatus("));
    expect(
      inicio,
      "nao achei o enum UserStatus em backend/app/models/models.py",
    ).toBeGreaterThan(-1);

    const doBackend: string[] = [];
    for (const linha of linhas.slice(inicio + 1)) {
      const membro = linha.match(/^\s+\w+ = "([^"]+)"/);
      if (membro) doBackend.push(membro[1]);
      else if (linha.trim() !== "") break;
    }
    expect(doBackend.length).toBeGreaterThan(0);

    expect([...USER_STATUSES].sort()).toEqual([...doBackend].sort());
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

describe("removeAvatar", () => {
  it("chama DELETE /users/me/avatar sem mandar chave nenhuma", async () => {
    mockDelete.mockResolvedValue({});

    await removeAvatar();

    expect(mockDelete).toHaveBeenCalledWith("/users/me/avatar");
    expect(mockDelete.mock.calls[0]).toHaveLength(1);
  });

  it("deixa o erro subir para a tela mostrar", async () => {
    mockDelete.mockRejectedValue(new Error("rede"));

    await expect(removeAvatar()).rejects.toThrow("rede");
  });
});

describe("removeUserAvatar", () => {
  it("chama POST /users/:id/avatar/remove com a justificativa e a versão, sem chave", async () => {
    mockPost.mockResolvedValue({ data: { ...user, avatar_url: null } });

    const resposta = await removeUserAvatar(
      "u1",
      "Foto imprópria",
      "2026-10-15T10:00:00.123456Z",
    );

    expect(mockPost).toHaveBeenCalledWith("/users/u1/avatar/remove", {
      justification: "Foto imprópria",
      expected_updated_at: "2026-10-15T10:00:00.123456Z",
    });
    expect(Object.keys(mockPost.mock.calls[0][1] as object).sort()).toEqual([
      "expected_updated_at",
      "justification",
    ]);
    expect(resposta.avatar_url).toBeNull();
  });

  it("deixa o erro subir para o diálogo mostrar", async () => {
    mockPost.mockRejectedValue(new Error("rede"));

    await expect(
      removeUserAvatar("u1", "Foto imprópria", "2026-10-15T10:00:00Z"),
    ).rejects.toThrow("rede");
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
  it("calls GET /users/technicians", async () => {
    mockGet.mockResolvedValue({
      data: { items: [user], total: 1, limit: 100, offset: 0 },
    });

    const result = await getTechnicians();

    expect(mockGet).toHaveBeenCalledWith("/users/technicians");
    expect(result).toHaveLength(1);
  });
});

describe("foto para outras pessoas", () => {
  const ESTADO = {
    autorizada: true,
    disponivel: true,
    aviso: { versao: "TESTE-AVISO-01", rotulo: "TESTE", explicacao: ["TESTE"] },
  };

  it("lê a própria escolha em GET /users/me/avatar/exibicao", async () => {
    mockGet.mockResolvedValue({ data: ESTADO });

    await expect(getExibicaoDaFoto()).resolves.toEqual(ESTADO);
    expect(mockGet).toHaveBeenCalledWith("/users/me/avatar/exibicao");
  });

  it("o PUT leva só a escolha e a versão mostrada — nada que escolha conta", async () => {
    mockPut.mockResolvedValue({ data: ESTADO });

    await expect(setExibicaoDaFoto(true, "TESTE-AVISO-01")).resolves.toEqual(ESTADO);

    expect(mockPut).toHaveBeenCalledTimes(1);
    const [url, corpo] = mockPut.mock.calls[0];
    expect(url).toBe("/users/me/avatar/exibicao");
    expect(corpo).toEqual({ autorizada: true, versao_aviso: "TESTE-AVISO-01" });
  });

  it("revogar sem texto manda versão nula", async () => {
    mockPut.mockResolvedValue({ data: { ...ESTADO, autorizada: false } });

    await setExibicaoDaFoto(false, null);

    expect(mockPut.mock.calls[0][1]).toEqual({ autorizada: false, versao_aviso: null });
  });

  it("deixa o erro subir: a tela não pode presumir sucesso", async () => {
    mockPut.mockRejectedValue(new Error("409"));

    await expect(setExibicaoDaFoto(true, "TESTE-AVISO-01")).rejects.toThrow("409");
  });
});
