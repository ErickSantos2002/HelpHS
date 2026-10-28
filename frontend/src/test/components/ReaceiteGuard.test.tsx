import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthUser } from "../../types/auth";

/**
 * A tela de re-aceite da Política de Privacidade.
 *
 * Quem decide SE a pessoa precisa aceitar é o backend (que só liga com
 * `LGPD_EXIGE_REACEITE`) — o guard só obedece, com duas regras:
 *
 * - Política (`politica_pendente`): cliente, técnico e admin (Decisão 2, de
 *   27/10/2026). O backend também bloqueia: 428 nas rotas, 4428 no chat.
 * - Termos (`termos_pendentes`): só clientes, só a tela — a regra de
 *   24/09/2026, preservada.
 *
 * Dá para recusar, e recusar é sair. Falhar a consulta NÃO libera.
 */

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));
vi.mock("../../services/userService", () => ({
  getLgpdConsentStatus: vi.fn(),
  updateLGPDConsent: vi.fn(),
}));

import { useAuth } from "../../contexts/AuthContext";
import { getLgpdConsentStatus, updateLGPDConsent } from "../../services/userService";
import { ReaceiteGuard } from "../../components/layout/ReaceiteGuard";
import { avisaAceitePoliticaPendente } from "../../services/aceitePolitica";

const mockUseAuth = vi.mocked(useAuth);
const mockStatus = vi.mocked(getLgpdConsentStatus);
const mockAceite = vi.mocked(updateLGPDConsent);
const logout = vi.fn();

function comoUsuario(role: AuthUser["role"]) {
  mockUseAuth.mockReturnValue({
    user: {
      id: "u1",
      name: "Fulana",
      email: "f@test.com",
      role,
      avatar_url: null,
      onboarding_completed: true,
    },
    logout,
  } as unknown as ReturnType<typeof useAuth>);
}

function situacao(
  politica: boolean,
  { termos = false }: { termos?: boolean } = {},
) {
  return {
    revisao_politica_vigente: "01",
    revisao_termos_vigente: null,
    revisao_politica_aceita: politica ? "00" : "01",
    revisao_termos_aceita: null,
    politica_pendente: politica,
    termos_pendentes: termos,
    precisa_reaceitar: politica || termos,
  };
}

function monta(inicio = "/tickets") {
  return render(
    <MemoryRouter initialEntries={[inicio]}>
      <Routes>
        <Route element={<ReaceiteGuard />}>
          <Route path="/tickets" element={<div>lista de chamados</div>} />
          <Route path="/onboarding" element={<div>tela de onboarding</div>} />
        </Route>
        <Route path="/login" element={<div>tela de login</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

const TITULO = /atualizamos nossa política de privacidade/i;
const PAPEIS = ["client", "technician", "admin"] as const;

beforeEach(() => {
  vi.clearAllMocks();
  logout.mockResolvedValue(undefined);
});

describe("ReaceiteGuard — Política: todos os papéis", () => {
  it.each(PAPEIS)("%s com a Política pendente vê a tela, e não o sistema", async (papel) => {
    comoUsuario(papel);
    mockStatus.mockResolvedValue(situacao(true));
    monta();

    expect(await screen.findByRole("heading", { name: TITULO })).toBeInTheDocument();
    expect(screen.queryByText("lista de chamados")).toBeNull();
  });

  it.each(PAPEIS)("%s com a Política aceita segue para o sistema", async (papel) => {
    comoUsuario(papel);
    mockStatus.mockResolvedValue(situacao(false));
    monta();
    expect(await screen.findByText("lista de chamados")).toBeInTheDocument();
  });

  it("não mostra o sistema enquanto a consulta não volta", () => {
    // Mostrar a tela e trocá-la pelo aceite um instante depois seria deixar a
    // pessoa clicar em algo que ela ainda não pode usar.
    comoUsuario("technician");
    mockStatus.mockReturnValue(new Promise(() => {}));
    monta();
    expect(screen.queryByText("lista de chamados")).toBeNull();
  });
});

describe("ReaceiteGuard — Termos: comportamento antigo, só clientes", () => {
  it("cliente com só os Termos pendentes vê a tela", async () => {
    comoUsuario("client");
    mockStatus.mockResolvedValue(situacao(false, { termos: true }));
    monta();
    expect(await screen.findByRole("heading", { name: TITULO })).toBeInTheDocument();
  });

  it.each(["technician", "admin"] as const)(
    "%s não é cobrado pelos Termos, mesmo que a resposta diga",
    async (papel) => {
      comoUsuario(papel);
      mockStatus.mockResolvedValue(situacao(false, { termos: true }));
      monta();
      expect(await screen.findByText("lista de chamados")).toBeInTheDocument();
    },
  );

  it("backend anterior (sem politica_pendente): vale a regra antiga", async () => {
    const antigo = {
      revisao_politica_vigente: "01",
      revisao_termos_vigente: null,
      revisao_politica_aceita: null,
      revisao_termos_aceita: null,
      precisa_reaceitar: true,
    };
    comoUsuario("technician");
    mockStatus.mockResolvedValue(antigo);
    const { unmount } = monta();
    expect(await screen.findByText("lista de chamados")).toBeInTheDocument();
    unmount();

    comoUsuario("client");
    monta();
    expect(await screen.findByRole("heading", { name: TITULO })).toBeInTheDocument();
  });
});

describe("ReaceiteGuard — falha na consulta", () => {
  it("NÃO libera: mostra o erro e deixa tentar de novo", async () => {
    comoUsuario("client");
    mockStatus.mockRejectedValueOnce(new Error("rede caiu"));
    mockStatus.mockResolvedValueOnce(situacao(false));
    monta();

    expect(await screen.findByRole("alert")).toHaveTextContent(/não foi possível verificar/i);
    expect(screen.queryByText("lista de chamados")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: /tentar novamente/i }));
    expect(await screen.findByText("lista de chamados")).toBeInTheDocument();
    expect(mockStatus).toHaveBeenCalledTimes(2);
  });

  it("da tela de erro dá para sair", async () => {
    comoUsuario("admin");
    mockStatus.mockRejectedValue(new Error("timeout"));
    monta();

    await userEvent.click(await screen.findByRole("button", { name: /^sair$/i }));
    await waitFor(() => expect(logout).toHaveBeenCalled());
    expect(await screen.findByText("tela de login")).toBeInTheDocument();
  });
});

describe("ReaceiteGuard — o 428 de qualquer pedido", () => {
  it("o aviso de 428/4428 troca o sistema pela tela de aceite", async () => {
    comoUsuario("technician");
    mockStatus.mockResolvedValueOnce(situacao(false));
    mockStatus.mockResolvedValueOnce(situacao(true));
    monta();
    expect(await screen.findByText("lista de chamados")).toBeInTheDocument();

    act(() => avisaAceitePoliticaPendente());

    expect(await screen.findByRole("heading", { name: TITULO })).toBeInTheDocument();
    expect(screen.queryByText("lista de chamados")).toBeNull();
  });
});

describe("ReaceiteGuard — antes do onboarding", () => {
  it("o onboarding não aparece enquanto a Política está pendente", async () => {
    comoUsuario("client");
    mockStatus.mockResolvedValue(situacao(true));
    monta("/onboarding");

    expect(await screen.findByRole("heading", { name: TITULO })).toBeInTheDocument();
    expect(screen.queryByText("tela de onboarding")).toBeNull();
  });

  it("no App.tsx, a tela de aceite envolve o onboarding e o sistema", () => {
    const fonte = readFileSync(resolve(process.cwd(), "src/App.tsx"), "utf8");
    const posicao = (trecho: string) => {
      const i = fonte.indexOf(trecho);
      expect(i, `não achei ${trecho} no App.tsx`).toBeGreaterThan(-1);
      return i;
    };
    const auth = posicao("<AuthGuard />");
    const aceite = posicao("<ReaceiteGuard />");
    expect(fonte.indexOf("<ReaceiteGuard />", aceite + 1)).toBe(-1);
    expect(auth).toBeLessThan(aceite);
    expect(aceite).toBeLessThan(posicao("<OnboardingOnlyRoute />"));
    expect(aceite).toBeLessThan(posicao("<OnboardingGuard />"));
    expect(aceite).toBeLessThan(posicao("<AppLayout />"));
  });
});

describe("ReaceiteGuard — a tela de aceite", () => {
  it("cobra o aceite de quem tem revisão antiga, no lugar do sistema", async () => {
    comoUsuario("client");
    mockStatus.mockResolvedValue(situacao(true));
    monta();

    expect(
      await screen.findByRole("heading", { name: /atualizamos nossa política de privacidade/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText("lista de chamados")).toBeNull();
  });

  it("oferece o texto da política, em nova aba", async () => {
    comoUsuario("client");
    mockStatus.mockResolvedValue(situacao(true));
    monta();

    const link = await screen.findByRole("link", { name: /política de privacidade/i });
    expect(link.getAttribute("href")).toBe("/privacidade");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("aceitar grava o aceite e libera o sistema", async () => {
    comoUsuario("client");
    mockStatus.mockResolvedValue(situacao(true));
    mockAceite.mockResolvedValue({} as Awaited<ReturnType<typeof updateLGPDConsent>>);
    monta();

    await userEvent.click(await screen.findByRole("button", { name: /aceitar e continuar/i }));

    expect(mockAceite).toHaveBeenCalledWith(true);
    expect(await screen.findByText("lista de chamados")).toBeInTheDocument();
  });

  it("se o aceite não for gravado, a tela continua e avisa", async () => {
    comoUsuario("client");
    mockStatus.mockResolvedValue(situacao(true));
    mockAceite.mockRejectedValue(new Error("500"));
    monta();

    await userEvent.click(await screen.findByRole("button", { name: /aceitar e continuar/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/não foi possível registrar/i);
    expect(screen.queryByText("lista de chamados")).toBeNull();
  });

  it("recusar sai do sistema, sem gravar aceite", async () => {
    comoUsuario("client");
    mockStatus.mockResolvedValue(situacao(true));
    monta();

    await userEvent.click(await screen.findByRole("button", { name: /recusar e sair/i }));

    await waitFor(() => expect(logout).toHaveBeenCalled());
    expect(mockAceite).not.toHaveBeenCalled();
    expect(await screen.findByText("tela de login")).toBeInTheDocument();
  });
});
