import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AxiosInstance, InternalAxiosRequestConfig } from "axios";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * O caminho inteiro de um login errado: tela → AuthContext → authService →
 * interceptor do axios → resposta. Os testes do `LoginPage.test.tsx` simulam o
 * `useAuth` e por isso nunca passavam pelo interceptor — e era nele que a
 * senha errada virava recarregamento da página (auditoria F1-B-01). Aqui só a
 * rede é falsa: o adapter do axios responde por rota.
 */

type Resposta = { status: number; data?: unknown };
type Rota = (config: InternalAxiosRequestConfig) => Resposta;

const locationMock = { href: "" };

async function montaTela(rotas: Record<string, Rota[]>) {
  vi.resetModules();
  const { AxiosError } = await import("axios");
  const { api } = await import("../../services/api");
  const { AuthProvider } = await import("../../contexts/AuthContext");
  const { default: LoginPage } = await import("../../pages/auth/LoginPage");

  const chamadas: string[] = [];
  const adapter = vi.fn(async (config: InternalAxiosRequestConfig) => {
    const url = config.url ?? "";
    chamadas.push(url);
    const fila = rotas[url];
    const responde = fila?.shift();
    if (!responde) throw new Error(`sem resposta programada para ${url}`);
    const { status, data = {} } = responde(config);
    const response = { data, status, statusText: "", headers: {}, config };
    if (status >= 400) {
      throw new AxiosError("request failed", "ERR_BAD_REQUEST", config, null, response);
    }
    return response;
  });
  (api as AxiosInstance).defaults.adapter = adapter;

  render(
    <AuthProvider>
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<p>painel aberto</p>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
  return { chamadas };
}

const responde =
  (status: number, data?: unknown): Rota =>
  () => ({ status, data });

const TOKENS = { access_token: "acesso", refresh_token: "refresh", token_type: "bearer" };
const EU = {
  id: "u1",
  name: "Ana",
  email: "ana@exemplo.com",
  role: "technician",
  avatar_url: null,
  onboarding_completed: true,
};

async function digitaEEntra(senha: string) {
  await userEvent.type(screen.getByLabelText("E-mail"), "ana@exemplo.com");
  await userEvent.type(screen.getByLabelText("Senha"), senha);
  await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
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

describe("LoginPage — senha errada passando pelo interceptor real", () => {
  it("mostra o erro, mantém o e-mail e não recarrega a página", async () => {
    await montaTela({
      "/auth/login": [responde(401, { detail: "E-mail ou senha incorretos." })],
    });

    await digitaEEntra("SenhaErrada1");

    expect(await screen.findByText("E-mail ou senha incorretos.")).toBeInTheDocument();
    expect(screen.getByLabelText("E-mail")).toHaveValue("ana@exemplo.com");
    expect(locationMock.href).toBe("");
  });

  it("com uma sessão antiga no navegador, o erro também fica na tela", async () => {
    // Uma sessão vencida no storage fazia o interceptor renovar e reenviar a
    // senha errada. Sem access token a tela não tenta restaurar a sessão: só
    // o refresh antigo fica lá, que é o caso do navegador que já foi usado.
    localStorage.setItem("helphs_refresh_token", "refresh-antigo");
    const { chamadas } = await montaTela({
      "/auth/login": [responde(401, { detail: "E-mail ou senha incorretos." })],
    });

    await digitaEEntra("SenhaErrada1");

    expect(await screen.findByText("E-mail ou senha incorretos.")).toBeInTheDocument();
    expect(chamadas).toEqual(["/auth/login"]);
    expect(localStorage.getItem("helphs_refresh_token")).toBe("refresh-antigo");
    expect(locationMock.href).toBe("");
  });

  it("deixa tentar de novo: a segunda tentativa, certa, entra", async () => {
    await montaTela({
      "/auth/login": [
        responde(401, { detail: "E-mail ou senha incorretos." }),
        responde(200, TOKENS),
      ],
      "/users/me": [responde(200, EU)],
    });

    await digitaEEntra("SenhaErrada1");
    await screen.findByText("E-mail ou senha incorretos.");
    await userEvent.clear(screen.getByLabelText("Senha"));
    await userEvent.type(screen.getByLabelText("Senha"), "SenhaCerta1");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByText("painel aberto")).toBeInTheDocument();
    expect(localStorage.getItem("helphs_access_token")).toBe("acesso");
    expect(locationMock.href).toBe("");
  });
});

describe("LoginPage — código do segundo fator errado", () => {
  const DESAFIO = {
    detail: "Informe o código do aplicativo autenticador.",
    mfa_required: true,
    mfa_token: "desafio-1",
    expires_in: 300,
  };

  it("continua no passo do código, com a mensagem, sem recarregar", async () => {
    await montaTela({
      "/auth/login": [responde(403, DESAFIO)],
      "/auth/mfa/verify": [
        responde(401, { detail: "Código inválido. Confira o aplicativo e tente de novo." }),
      ],
    });

    await digitaEEntra("SenhaCerta1");
    const campo = await screen.findByLabelText("Código de verificação");
    await userEvent.type(campo, "000000");
    await userEvent.click(screen.getByRole("button", { name: "Verificar" }));

    expect(
      await screen.findByText("Código inválido. Confira o aplicativo e tente de novo."),
    ).toBeInTheDocument();
    // Ainda no passo do código: o campo segue na tela, vazio para a nova tentativa
    expect(screen.getByLabelText("Código de verificação")).toHaveValue("");
    expect(locationMock.href).toBe("");
  });

  it("o código certo na segunda tentativa entra", async () => {
    await montaTela({
      "/auth/login": [responde(403, DESAFIO)],
      "/auth/mfa/verify": [
        responde(401, { detail: "Código inválido. Confira o aplicativo e tente de novo." }),
        responde(200, TOKENS),
      ],
      "/users/me": [responde(200, EU)],
    });

    await digitaEEntra("SenhaCerta1");
    await userEvent.type(await screen.findByLabelText("Código de verificação"), "000000");
    await userEvent.click(screen.getByRole("button", { name: "Verificar" }));
    await screen.findByText("Código inválido. Confira o aplicativo e tente de novo.");
    await userEvent.type(screen.getByLabelText("Código de verificação"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Verificar" }));

    expect(await screen.findByText("painel aberto")).toBeInTheDocument();
    expect(locationMock.href).toBe("");
  });
});
