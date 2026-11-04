import axios, { AxiosError, AxiosHeaders } from "axios";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * O download dos relatórios (F1-C-01a), pelo cliente HTTP DE VERDADE.
 *
 * O defeito era de transporte — host errado e token ausente —, e um `api`
 * simulado não o veria: o caso passaria com a URL relativa de antes. Aqui só o
 * adaptador é trocado, o último elo antes da rede. Interceptores, base da URL,
 * `Authorization`, renovação do 401 e o aviso do 428 são os de produção, e o
 * adaptador recebe o pedido exatamente como ele sairia.
 */

const BASE = "https://api.exemplo.test/api/v1";

type Svc = typeof import("../../services/reportService");
type Api = typeof import("../../services/api");
type Aceite = typeof import("../../services/aceitePolitica");
type ApiError = typeof import("../../lib/apiError");

let svc: Svc;
let apiMod: Api;
let aceite: Aceite;
let apiError: ApiError;

/** O que o adaptador responde, na ordem dos pedidos. */
type Resposta =
  | { status: number; corpo: BlobPart; tipo: string }
  | { rede: true };

let respostas: Resposta[];
let pedidos: InternalAxiosRequestConfig[];

const adaptador: AxiosAdapter = async (config) => {
  pedidos.push(config);
  const r = respostas.shift();
  if (!r) throw new Error("pedido sem resposta preparada");
  if ("rede" in r) {
    throw new AxiosError("Network Error", AxiosError.ERR_NETWORK, config, {});
  }
  const resposta: AxiosResponse = {
    data: new Blob([r.corpo], { type: r.tipo }),
    status: r.status,
    statusText: "",
    headers: new AxiosHeaders({ "content-type": r.tipo }),
    config,
    request: {},
  };
  if (r.status >= 200 && r.status < 300) return resposta;
  throw new AxiosError(
    `Request failed with status code ${r.status}`,
    AxiosError.ERR_BAD_RESPONSE,
    config,
    {},
    resposta,
  );
};

const CSV = "Relatório HelpHS — 2026-08-01 a 2026-08-31\r\nFiltros: Todos\r\n";
const PDF = "%PDF-1.4\n%fake\n";
const INDEX_HTML = '<!doctype html>\n<html lang="pt-BR" data-app="helphs"></html>';

const json = (corpo: unknown) => JSON.stringify(corpo);

/** O que o navegador recebeu: URL temporária, nome e conteúdo. */
let criadas: Blob[];
let revogadas: string[];
let cliques: { href: string; download: string }[];

beforeEach(async () => {
  vi.stubEnv("VITE_API_URL", BASE);
  vi.resetModules();
  apiMod = await import("../../services/api");
  svc = await import("../../services/reportService");
  aceite = await import("../../services/aceitePolitica");
  apiError = await import("../../lib/apiError");

  apiMod.api.defaults.adapter = adaptador;
  apiMod.tokenStorage.set("token-de-acesso", "token-de-refresh");

  respostas = [];
  pedidos = [];
  criadas = [];
  revogadas = [];
  cliques = [];
  let n = 0;
  vi.spyOn(URL, "createObjectURL").mockImplementation((b) => {
    criadas.push(b as Blob);
    return `blob:teste/${++n}`;
  });
  vi.spyOn(URL, "revokeObjectURL").mockImplementation((u) => {
    revogadas.push(u);
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    cliques.push({ href: this.getAttribute("href") ?? "", download: this.download });
  });
});

afterEach(async () => {
  // A revogação sai no tique seguinte: sem esperar aqui, ela cai no espião do
  // PRÓXIMO caso e a contagem dele mente.
  await new Promise((r) => setTimeout(r, 0));
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  localStorage.clear();
});

const AGOSTO = { start_date: "2026-08-01", end_date: "2026-08-31" };

describe("baixarRelatorio — o pedido que sai", () => {
  it.each(["csv", "pdf"] as const)(
    "%s vai ao host da API configurada, e não ao domínio do front",
    async (formato) => {
      respostas.push(
        formato === "csv"
          ? { status: 200, corpo: CSV, tipo: "text/csv; charset=utf-8" }
          : { status: 200, corpo: PDF, tipo: "application/pdf" },
      );

      await svc.baixarRelatorio(formato, AGOSTO);

      const url = new URL(apiMod.api.getUri(pedidos[0]));
      expect(url.origin).toBe("https://api.exemplo.test");
      expect(url.pathname).toBe(`/api/v1/dashboard/reports/export/${formato}`);
      expect(pedidos[0].responseType).toBe("blob");
    },
  );

  it("leva o Bearer pelo cabeçalho, e o token não aparece na URL", async () => {
    respostas.push({ status: 200, corpo: CSV, tipo: "text/csv" });

    await svc.baixarRelatorio("csv", AGOSTO);

    expect(pedidos[0].headers.Authorization).toBe("Bearer token-de-acesso");
    expect(apiMod.api.getUri(pedidos[0])).not.toContain("token");
  });

  it("manda as datas escolhidas, a categoria e a prioridade, e nenhum period", async () => {
    respostas.push({ status: 200, corpo: CSV, tipo: "text/csv" });

    await svc.baixarRelatorio("csv", {
      ...AGOSTO,
      category: "hardware",
      priority: "high",
    });

    const params = new URL(apiMod.api.getUri(pedidos[0])).searchParams;
    expect(params.get("start_date")).toBe("2026-08-01");
    expect(params.get("end_date")).toBe("2026-08-31");
    expect(params.get("category")).toBe("hardware");
    expect(params.get("priority")).toBe("high");
    expect(params.has("period")).toBe(false);
  });
});

describe("baixarRelatorio — o arquivo entregue", () => {
  it("o CSV chega inteiro, com o cabeçalho do relatório e o tipo text/csv", async () => {
    respostas.push({ status: 200, corpo: CSV, tipo: "text/csv; charset=utf-8" });

    await svc.baixarRelatorio("csv", AGOSTO);

    expect(criadas).toHaveLength(1);
    expect(criadas[0].type).toBe("text/csv");
    expect(await criadas[0].text()).toBe(CSV);
    expect((await criadas[0].text()).startsWith("Relatório HelpHS")).toBe(true);
  });

  it("o PDF chega começando por %PDF, com o tipo application/pdf", async () => {
    respostas.push({ status: 200, corpo: PDF, tipo: "application/pdf" });

    await svc.baixarRelatorio("pdf", AGOSTO);

    expect(criadas).toHaveLength(1);
    expect(criadas[0].type).toBe("application/pdf");
    expect((await criadas[0].text()).slice(0, 4)).toBe("%PDF");
  });

  it("o nome do arquivo diz o intervalo, os filtros e a extensão certa", async () => {
    respostas.push(
      { status: 200, corpo: CSV, tipo: "text/csv" },
      { status: 200, corpo: PDF, tipo: "application/pdf" },
    );

    await svc.baixarRelatorio("csv", AGOSTO);
    await svc.baixarRelatorio("pdf", { ...AGOSTO, category: "network", priority: "low" });

    expect(cliques.map((c) => c.download)).toEqual([
      "relatorio_helphs_2026-08-01_a_2026-08-31.csv",
      "relatorio_helphs_2026-08-01_a_2026-08-31_network_low.pdf",
    ]);
  });

  it("clica no link da URL temporária e a revoga depois", async () => {
    respostas.push({ status: 200, corpo: CSV, tipo: "text/csv" });

    await svc.baixarRelatorio("csv", AGOSTO);

    expect(cliques).toEqual([
      { href: "blob:teste/1", download: expect.stringMatching(/\.csv$/) },
    ]);
    await vi.waitFor(() => expect(revogadas).toEqual(["blob:teste/1"]));
    // O link auxiliar não fica na página.
    expect(document.querySelector('a[href^="blob:"]')).toBeNull();
  });

  it("revoga a URL temporária mesmo quando o clique falha", async () => {
    respostas.push({ status: 200, corpo: CSV, tipo: "text/csv" });
    vi.mocked(HTMLAnchorElement.prototype.click).mockImplementation(() => {
      throw new Error("navegador recusou");
    });

    await expect(svc.baixarRelatorio("csv", AGOSTO)).rejects.toThrow("navegador recusou");

    await vi.waitFor(() => expect(revogadas).toEqual(["blob:teste/1"]));
    expect(document.querySelector('a[href^="blob:"]')).toBeNull();
  });
});

describe("baixarRelatorio — o que não é relatório não vira arquivo", () => {
  it("o index.html da SPA, com 200, é recusado e nada é baixado", async () => {
    respostas.push({ status: 200, corpo: INDEX_HTML, tipo: "text/html" });

    await expect(svc.baixarRelatorio("csv", AGOSTO)).rejects.toBeInstanceOf(
      svc.ArquivoDeRelatorioInvalido,
    );
    expect(criadas).toHaveLength(0);
    expect(cliques).toHaveLength(0);
  });

  it("HTML rotulado como text/csv também é recusado", async () => {
    respostas.push({ status: 200, corpo: INDEX_HTML, tipo: "text/csv" });

    await expect(svc.baixarRelatorio("csv", AGOSTO)).rejects.toBeInstanceOf(
      svc.ArquivoDeRelatorioInvalido,
    );
    expect(cliques).toHaveLength(0);
  });

  it("PDF sem a assinatura %PDF é recusado", async () => {
    respostas.push({ status: 200, corpo: "não sou pdf", tipo: "application/pdf" });

    await expect(svc.baixarRelatorio("pdf", AGOSTO)).rejects.toBeInstanceOf(
      svc.ArquivoDeRelatorioInvalido,
    );
    expect(cliques).toHaveLength(0);
  });

  it("CSV pedido e PDF recebido é recusado", async () => {
    respostas.push({ status: 200, corpo: PDF, tipo: "application/pdf" });

    await expect(svc.baixarRelatorio("csv", AGOSTO)).rejects.toBeInstanceOf(
      svc.ArquivoDeRelatorioInvalido,
    );
  });

  it("corpo vazio é recusado", async () => {
    respostas.push({ status: 200, corpo: "", tipo: "text/csv" });

    await expect(svc.baixarRelatorio("csv", AGOSTO)).rejects.toBeInstanceOf(
      svc.ArquivoDeRelatorioInvalido,
    );
  });
});

describe("baixarRelatorio — os erros", () => {
  it("401: renova o token pelo fluxo de sempre e repete o download", async () => {
    respostas.push(
      { status: 401, corpo: json({ detail: "expirou" }), tipo: "application/json" },
      { status: 200, corpo: CSV, tipo: "text/csv" },
    );
    const refresh = vi.spyOn(axios, "post").mockResolvedValue({
      data: { access_token: "token-novo", token_type: "bearer", expires_in: 900 },
    });

    await svc.baixarRelatorio("csv", AGOSTO);

    expect(refresh).toHaveBeenCalledWith(`${BASE}/auth/refresh`, {
      refresh_token: "token-de-refresh",
    });
    expect(pedidos).toHaveLength(2);
    expect(pedidos[1].headers.Authorization).toBe("Bearer token-novo");
    expect(pedidos[1].responseType).toBe("blob");
    expect(cliques).toHaveLength(1);
  });

  it("401 sem renovação possível: limpa a sessão e não baixa nada", async () => {
    respostas.push({ status: 401, corpo: json({ detail: "expirou" }), tipo: "application/json" });
    vi.spyOn(axios, "post").mockRejectedValue(new Error("refresh recusado"));

    await expect(svc.baixarRelatorio("csv", AGOSTO)).rejects.toThrow("refresh recusado");

    expect(apiMod.tokenStorage.getAccess()).toBeNull();
    expect(cliques).toHaveLength(0);
  });

  it("428 do aceite: o corpo Blob é lido e o aviso da Política é disparado", async () => {
    respostas.push({
      status: 428,
      corpo: json({ detail: "Aceite pendente", code: "aceite_politica_pendente" }),
      tipo: "application/json",
    });
    const aviso = vi.fn();
    const para = aceite.aoAceitePoliticaPendente(aviso);

    const erro = await svc.baixarRelatorio("csv", AGOSTO).catch((e: unknown) => e);
    para();

    expect(aviso).toHaveBeenCalledTimes(1);
    expect(aceite.ehAceitePoliticaPendente(erro)).toBe(true);
    expect(cliques).toHaveLength(0);
  });

  it("outro 428, sem o código do aceite, não dispara o aviso", async () => {
    respostas.push({ status: 428, corpo: json({ detail: "outra coisa" }), tipo: "application/json" });
    const aviso = vi.fn();
    const para = aceite.aoAceitePoliticaPendente(aviso);

    await svc.baixarRelatorio("csv", AGOSTO).catch(() => undefined);
    para();

    expect(aviso).not.toHaveBeenCalled();
  });

  it.each([
    [403, { detail: "Access denied" }, "Você não tem permissão para realizar esta ação."],
    [
      422,
      { detail: [{ field: "end_date", message: "O fim vem antes do início." }] },
      "O fim vem antes do início.",
    ],
    [500, { detail: "Internal Server Error Traceback (most recent call last)" }, "Erro interno no servidor. Tente novamente em instantes."],
  ])("%i: o corpo Blob vira a mensagem de sempre do apiError", async (status, corpo, mensagem) => {
    respostas.push({ status, corpo: json(corpo), tipo: "application/json" });

    const erro = await svc.baixarRelatorio("csv", AGOSTO).catch((e: unknown) => e);

    expect(apiError.getApiError(erro)).toBe(mensagem);
    expect(cliques).toHaveLength(0);
  });

  it("erro com página HTML no corpo cai na mensagem do status, sem mostrar o HTML", async () => {
    respostas.push({ status: 502, corpo: "<html><body>Bad Gateway</body></html>", tipo: "text/html" });

    const erro = await svc.baixarRelatorio("csv", AGOSTO).catch((e: unknown) => e);

    const mensagem = apiError.getApiError(erro);
    expect(mensagem).toBe("O servidor está indisponível no momento. Tente novamente em instantes.");
    expect(mensagem).not.toContain("<");
  });

  it("falha de rede sai como a mensagem de conexão", async () => {
    respostas.push({ rede: true });

    const erro = await svc.baixarRelatorio("csv", AGOSTO).catch((e: unknown) => e);

    expect(apiError.getApiError(erro)).toBe(
      "Não foi possível falar com o servidor. Verifique sua conexão e tente de novo.",
    );
    expect(cliques).toHaveLength(0);
  });
});

describe("nomeDoArquivoDoRelatorio", () => {
  const HOJE = new Date("2026-11-04T15:00:00Z");

  it("com o period legado, usa a data de hoje e os dias", () => {
    expect(svc.nomeDoArquivoDoRelatorio("csv", { period: 30 }, HOJE)).toBe(
      "relatorio_helphs_2026-11-04_30d.csv",
    );
  });

  it("intervalo pela metade não entra no nome", () => {
    expect(
      svc.nomeDoArquivoDoRelatorio("pdf", { start_date: "2026-08-01" }, HOJE),
    ).toBe("relatorio_helphs_2026-11-04.pdf");
  });

  it("não deixa barra, ponto ou espaço do filtro chegar ao nome", () => {
    expect(
      svc.nomeDoArquivoDoRelatorio(
        "csv",
        { ...AGOSTO, category: "../a b", priority: "x/y" },
        HOJE,
      ),
    ).toBe("relatorio_helphs_2026-08-01_a_2026-08-31_ab_xy.csv");
  });
});
