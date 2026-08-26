import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { AxiosInstance, InternalAxiosRequestConfig } from "axios";

/**
 * Testes do interceptor de autenticação (`services/api.ts`).
 *
 * O módulo guarda estado (`isRefreshing`, `failedQueue`) e registra os
 * interceptors no import — por isso cada teste importa uma cópia fresca via
 * `vi.resetModules()`. As respostas HTTP são programadas no adapter do axios,
 * então as requisições percorrem o caminho real (request interceptor →
 * adapter → response interceptor) sem tocar a rede.
 */

type Responder = (config: InternalAxiosRequestConfig) => {
  status: number;
  data?: unknown;
};

// ── Ambiente por teste ────────────────────────────────────────

const locationMock = { href: "" };

async function freshApi() {
  vi.resetModules();
  const axiosModule = await import("axios");
  const axios = axiosModule.default;
  const { AxiosError } = axiosModule;
  const mod = await import("../../services/api");

  const queue: Responder[] = [];
  const adapter = vi.fn(async (config: InternalAxiosRequestConfig) => {
    const responder = queue.shift();
    if (!responder) throw new Error("adapter sem resposta programada");
    const { status, data = {} } = responder(config);
    const response = { data, status, statusText: "", headers: {}, config };
    if (status >= 400) {
      throw new AxiosError("request failed", "ERR_BAD_REQUEST", config, null, response);
    }
    return response;
  });
  (mod.api as AxiosInstance).defaults.adapter = adapter;

  /** Programa a resposta da próxima requisição que chegar ao adapter. */
  const respond = (status: number, data?: unknown) =>
    queue.push(() => ({ status, data }));

  return { axios, api: mod.api, tokenStorage: mod.tokenStorage, adapter, respond };
}

beforeEach(() => {
  localStorage.clear();
  locationMock.href = "";
  Object.defineProperty(window, "location", {
    value: locationMock,
    writable: true,
    configurable: true,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ── Request interceptor ───────────────────────────────────────

describe("request interceptor", () => {
  it("anexa o Bearer token quando há sessão", async () => {
    const { api, tokenStorage, respond, adapter } = await freshApi();
    tokenStorage.set("tok-acesso", "tok-refresh");
    respond(200, { ok: true });

    await api.get("/tickets");

    const config = adapter.mock.calls[0][0];
    expect(config.headers.Authorization).toBe("Bearer tok-acesso");
  });

  it("não anexa Authorization sem token no storage", async () => {
    const { api, respond, adapter } = await freshApi();
    respond(200, { ok: true });

    await api.get("/kb/articles");

    const config = adapter.mock.calls[0][0];
    expect(config.headers.Authorization).toBeUndefined();
  });
});

// ── Caminhos que NÃO disparam refresh ─────────────────────────

describe("response interceptor — erros que passam reto", () => {
  it("propaga status que não é 401 sem tentar refresh", async () => {
    const { axios, api, respond } = await freshApi();
    const postSpy = vi.spyOn(axios, "post");
    respond(403);

    await expect(api.get("/equipments/xyz")).rejects.toMatchObject({
      response: { status: 403 },
    });
    expect(postSpy).not.toHaveBeenCalled();
  });

  it("propaga 401 do próprio /auth/refresh sem reentrar (senão vira loop)", async () => {
    const { axios, api, tokenStorage, respond } = await freshApi();
    tokenStorage.set("expirado", "refresh-1");
    const postSpy = vi.spyOn(axios, "post");
    respond(401);

    await expect(api.post("/auth/refresh", {})).rejects.toMatchObject({
      response: { status: 401 },
    });
    expect(postSpy).not.toHaveBeenCalled();
  });
});

// ── Fluxo de refresh ──────────────────────────────────────────

describe("response interceptor — refresh e retry", () => {
  it("num 401 renova o token e reexecuta a requisição original", async () => {
    const { axios, api, tokenStorage, respond, adapter } = await freshApi();
    tokenStorage.set("expirado", "refresh-1");
    const postSpy = vi.spyOn(axios, "post").mockResolvedValue({
      data: { access_token: "novo-acesso", token_type: "bearer", expires_in: 28800 },
    });
    respond(401); // primeira tentativa
    respond(200, { id: "t1" }); // retry pós-refresh

    const { data } = await api.get("/tickets/t1");

    expect(data).toEqual({ id: "t1" });
    expect(postSpy).toHaveBeenCalledTimes(1);
    expect(postSpy.mock.calls[0][1]).toEqual({ refresh_token: "refresh-1" });
    // O retry sai com o token novo e o storage é atualizado
    const retryConfig = adapter.mock.calls[1][0];
    expect(retryConfig.headers.Authorization).toBe("Bearer novo-acesso");
    expect(tokenStorage.getAccess()).toBe("novo-acesso");
    expect(tokenStorage.getRefresh()).toBe("refresh-1");
  });

  it("preserva o refresh token, que a resposta do backend não repete", async () => {
    // `/auth/refresh` devolve AccessTokenResponse — access_token, token_type e
    // expires_in, sem refresh_token (backend/app/schemas/auth.py). Gravar um
    // `data.refresh_token` que não existe escreve a string "undefined" no
    // localStorage: ela é truthy, passa pela guarda, e é o refresh seguinte que
    // morre — 401 e sessão perdida sem sintoma no momento do erro.
    const { axios, api, tokenStorage, respond } = await freshApi();
    tokenStorage.set("expirado", "refresh-1");
    vi.spyOn(axios, "post").mockResolvedValue({
      data: { access_token: "novo-acesso", token_type: "bearer", expires_in: 28800 },
    });
    respond(401);
    respond(200, { id: "t1" });

    await api.get("/tickets/t1");

    expect(tokenStorage.getAccess()).toBe("novo-acesso");
    expect(tokenStorage.getRefresh()).toBe("refresh-1");
  });

  it("sem refresh token, limpa a sessão e manda para /login", async () => {
    const { axios, api, tokenStorage, respond } = await freshApi();
    tokenStorage.set("expirado", "refresh-1");
    localStorage.removeItem("helphs_refresh_token");
    const postSpy = vi.spyOn(axios, "post");
    respond(401);

    await expect(api.get("/tickets")).rejects.toBeTruthy();

    expect(postSpy).not.toHaveBeenCalled();
    expect(tokenStorage.getAccess()).toBeNull();
    expect(locationMock.href).toBe("/login");
  });

  it("quando o refresh falha, limpa a sessão e manda para /login", async () => {
    const { axios, api, tokenStorage, respond } = await freshApi();
    tokenStorage.set("expirado", "refresh-invalido");
    vi.spyOn(axios, "post").mockRejectedValue(new Error("refresh recusado"));
    respond(401);

    await expect(api.get("/tickets")).rejects.toThrow("refresh recusado");

    expect(tokenStorage.getAccess()).toBeNull();
    expect(tokenStorage.getRefresh()).toBeNull();
    expect(locationMock.href).toBe("/login");
  });

  it("um 401 no retry propaga em vez de tentar refresh de novo", async () => {
    // `_retry` marca a requisição já reexecutada: se o token novo também for
    // recusado, o erro sobe — sem a marca, seria refresh em loop.
    const { axios, api, tokenStorage, respond } = await freshApi();
    tokenStorage.set("expirado", "refresh-1");
    const postSpy = vi.spyOn(axios, "post").mockResolvedValue({
      data: { access_token: "novo-acesso", token_type: "bearer", expires_in: 28800 },
    });
    respond(401); // primeira tentativa
    respond(401); // o retry também falha

    await expect(api.get("/tickets")).rejects.toMatchObject({
      response: { status: 401 },
    });
    expect(postSpy).toHaveBeenCalledTimes(1);
  });
});

// ── Concorrência ──────────────────────────────────────────────

describe("response interceptor — fila durante o refresh", () => {
  it("dois 401 simultâneos disparam UM refresh; a segunda espera e reusa o token", async () => {
    const { axios, api, tokenStorage, respond, adapter } = await freshApi();
    tokenStorage.set("expirado", "refresh-1");

    // Refresh controlado à mão, para manter a janela de concorrência aberta
    type RespostaRefresh = {
      data: { access_token: string; token_type: string; expires_in: number };
    };
    let liberaRefresh!: (v: RespostaRefresh) => void;
    const refreshPendente = new Promise<RespostaRefresh>((resolve) => {
      liberaRefresh = resolve;
    });
    const postSpy = vi.spyOn(axios, "post").mockReturnValue(refreshPendente as never);

    respond(401); // primeira requisição
    const p1 = api.get("/tickets");
    await vi.waitFor(() => expect(postSpy).toHaveBeenCalledTimes(1));

    respond(401); // segunda requisição, com o refresh ainda em voo
    const p2 = api.get("/notifications");
    await vi.waitFor(() => expect(adapter).toHaveBeenCalledTimes(2));

    respond(200, { id: "t1" }); // retry da primeira
    respond(200, { id: "n1" }); // retry da segunda
    liberaRefresh({
      data: { access_token: "novo-acesso", token_type: "bearer", expires_in: 28800 },
    });

    const [r1, r2] = await Promise.all([p1, p2]);

    expect(postSpy).toHaveBeenCalledTimes(1);
    expect(r1.data).toEqual({ id: "t1" });
    expect(r2.data).toEqual({ id: "n1" });
    // Os dois retries saíram com o token renovado
    expect(adapter.mock.calls[2][0].headers.Authorization).toBe("Bearer novo-acesso");
    expect(adapter.mock.calls[3][0].headers.Authorization).toBe("Bearer novo-acesso");
  });

  it("quando o refresh falha, as requisições da fila falham juntas", async () => {
    const { axios, api, tokenStorage, respond, adapter } = await freshApi();
    tokenStorage.set("expirado", "refresh-1");

    let rejeitaRefresh!: (err: Error) => void;
    const refreshPendente = new Promise((_, reject) => {
      rejeitaRefresh = reject;
    });
    const postSpy = vi.spyOn(axios, "post").mockReturnValue(refreshPendente as never);

    respond(401);
    const p1 = api.get("/tickets");
    await vi.waitFor(() => expect(postSpy).toHaveBeenCalledTimes(1));

    respond(401);
    const p2 = api.get("/notifications");
    await vi.waitFor(() => expect(adapter).toHaveBeenCalledTimes(2));

    rejeitaRefresh(new Error("refresh recusado"));

    await expect(p1).rejects.toThrow("refresh recusado");
    await expect(p2).rejects.toThrow("refresh recusado");
    expect(locationMock.href).toBe("/login");
  });
});

// ── tokenStorage ──────────────────────────────────────────────

describe("tokenStorage", () => {
  it("grava, lê e limpa o par de tokens", async () => {
    const { tokenStorage } = await freshApi();

    tokenStorage.set("a1", "r1");
    expect(tokenStorage.getAccess()).toBe("a1");
    expect(tokenStorage.getRefresh()).toBe("r1");

    tokenStorage.clear();
    expect(tokenStorage.getAccess()).toBeNull();
    expect(tokenStorage.getRefresh()).toBeNull();
  });
});
