import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthUser } from "../../types/auth";

/**
 * A tela de re-aceite da Política de Privacidade.
 *
 * Decisões de 24/09/2026: só clientes passam por ela; dá para recusar, e
 * recusar é sair do sistema; ela aparece na próxima abertura do sistema, não
 * no meio do trabalho. Quem decide SE a pessoa precisa aceitar é o backend
 * (`precisa_reaceitar`, que só liga com `LGPD_EXIGE_REACEITE`) — o guard só
 * obedece.
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

function situacao(precisa: boolean) {
  return {
    revisao_politica_vigente: "01",
    revisao_termos_vigente: null,
    revisao_politica_aceita: precisa ? "00" : "01",
    revisao_termos_aceita: null,
    precisa_reaceitar: precisa,
  };
}

function monta() {
  return render(
    <MemoryRouter initialEntries={["/tickets"]}>
      <Routes>
        <Route element={<ReaceiteGuard />}>
          <Route path="/tickets" element={<div>lista de chamados</div>} />
        </Route>
        <Route path="/login" element={<div>tela de login</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  logout.mockResolvedValue(undefined);
});

describe("ReaceiteGuard — quem passa", () => {
  it.each(["admin", "technician"] as const)(
    "%s passa direto, sem consultar o aceite",
    (papel) => {
      comoUsuario(papel);
      monta();
      expect(screen.getByText("lista de chamados")).toBeInTheDocument();
      expect(mockStatus).not.toHaveBeenCalled();
    },
  );

  it("cliente com a revisão vigente segue para o sistema", async () => {
    comoUsuario("client");
    mockStatus.mockResolvedValue(situacao(false));
    monta();
    expect(await screen.findByText("lista de chamados")).toBeInTheDocument();
  });

  it("não mostra o sistema enquanto a consulta não volta", () => {
    // Mostrar a tela e trocá-la pelo aceite um instante depois seria deixar o
    // cliente clicar em algo que ele ainda não pode usar.
    comoUsuario("client");
    mockStatus.mockReturnValue(new Promise(() => {}));
    monta();
    expect(screen.queryByText("lista de chamados")).toBeNull();
  });

  it("se a consulta falhar, deixa passar", async () => {
    // O front pode subir antes do backend que tem a rota. Travar todo cliente
    // por um 404 seria pior que o risco: o interruptor mora no backend.
    comoUsuario("client");
    mockStatus.mockRejectedValue(new Error("404"));
    monta();
    expect(await screen.findByText("lista de chamados")).toBeInTheDocument();
  });
});

describe("ReaceiteGuard — a tela de aceite", () => {
  it("cobra o aceite do cliente com revisão antiga, no lugar do sistema", async () => {
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
