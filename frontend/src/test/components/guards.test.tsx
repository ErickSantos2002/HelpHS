import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { AuthGuard } from "../../components/layout/AuthGuard";
import { RoleGuard } from "../../components/layout/RoleGuard";
import { OnboardingGuard } from "../../components/layout/OnboardingGuard";
import type { AuthUser } from "../../types/auth";

/**
 * Testes dos guards de rota (`components/layout/`).
 *
 * Eles não são a fronteira de segurança — quem decide é o backend — mas são a
 * fronteira de regressão do front: um guard errado esconde tela de quem pode
 * ver ou mostra tela vazia a quem não pode. O contexto é mockado porque o que
 * está sob teste é a decisão de rota, não a restauração de sessão.
 */

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from "../../contexts/AuthContext";

const mockUseAuth = vi.mocked(useAuth);

function usuario(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: "u1",
    name: "Usuário",
    email: "u@test.com",
    role: "client",
    avatar_url: null,
    onboarding_completed: true,
    ...overrides,
  };
}

type Auth = ReturnType<typeof useAuth>;

function autenticado(user: AuthUser | null, isLoading = false): Auth {
  return { user, isAuthenticated: !!user, isLoading } as Auth;
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ── AuthGuard ─────────────────────────────────────────────────

function renderAuthGuard(rotaInicial = "/tickets") {
  return render(
    <MemoryRouter initialEntries={[rotaInicial]}>
      <Routes>
        <Route element={<AuthGuard />}>
          <Route path="/tickets" element={<div>lista de chamados</div>} />
        </Route>
        <Route path="/login" element={<div>tela de login</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AuthGuard", () => {
  it("renderiza a rota filha quando autenticado", () => {
    mockUseAuth.mockReturnValue(autenticado(usuario()));

    renderAuthGuard();

    expect(screen.getByText("lista de chamados")).toBeInTheDocument();
  });

  it("mostra o spinner enquanto a sessão é restaurada — sem redirecionar", () => {
    // Redirecionar durante o isLoading derrubaria para /login todo F5 de
    // usuário logado, antes de o token do storage ser validado.
    mockUseAuth.mockReturnValue(autenticado(null, true));

    renderAuthGuard();

    expect(screen.queryByText("tela de login")).not.toBeInTheDocument();
    expect(screen.queryByText("lista de chamados")).not.toBeInTheDocument();
  });

  it("sem sessão, redireciona para /login", () => {
    mockUseAuth.mockReturnValue(autenticado(null));

    renderAuthGuard();

    expect(screen.getByText("tela de login")).toBeInTheDocument();
  });

  it("guarda a rota de origem no state para o retorno pós-login", () => {
    // É o que faz o login devolver o usuário à página que ele tentou abrir.
    mockUseAuth.mockReturnValue(autenticado(null));
    let stateRecebido: unknown;

    function EspiaLogin() {
      stateRecebido = useLocation().state;
      return <div>tela de login</div>;
    }

    render(
      <MemoryRouter initialEntries={["/tickets/abc"]}>
        <Routes>
          <Route element={<AuthGuard />}>
            <Route path="/tickets/:id" element={<div>detalhe</div>} />
          </Route>
          <Route path="/login" element={<EspiaLogin />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("tela de login")).toBeInTheDocument();
    expect(stateRecebido).toEqual({ from: "/tickets/abc" });
  });
});

// ── RoleGuard ─────────────────────────────────────────────────

function renderRoleGuard(roles: AuthUser["role"][]) {
  return render(
    <MemoryRouter initialEntries={["/admin/users"]}>
      <Routes>
        <Route element={<RoleGuard roles={roles} />}>
          <Route path="/admin/users" element={<div>gestão de usuários</div>} />
        </Route>
        <Route path="/403" element={<div>acesso negado</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RoleGuard", () => {
  it("renderiza a rota filha quando o perfil está na lista", () => {
    mockUseAuth.mockReturnValue(autenticado(usuario({ role: "admin" })));

    renderRoleGuard(["admin", "technician"]);

    expect(screen.getByText("gestão de usuários")).toBeInTheDocument();
  });

  it("perfil fora da lista vai para /403", () => {
    mockUseAuth.mockReturnValue(autenticado(usuario({ role: "client" })));

    renderRoleGuard(["admin", "technician"]);

    expect(screen.getByText("acesso negado")).toBeInTheDocument();
  });

  it("sem usuário também vai para /403 (fail closed)", () => {
    mockUseAuth.mockReturnValue(autenticado(null));

    renderRoleGuard(["admin"]);

    expect(screen.getByText("acesso negado")).toBeInTheDocument();
  });
});

// ── OnboardingGuard ───────────────────────────────────────────

function renderOnboardingGuard() {
  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <Routes>
        <Route element={<OnboardingGuard />}>
          <Route path="/dashboard" element={<div>painel</div>} />
        </Route>
        <Route path="/onboarding" element={<div>completar cadastro</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("OnboardingGuard", () => {
  it("cliente sem onboarding vai para /onboarding", () => {
    mockUseAuth.mockReturnValue(
      autenticado(usuario({ role: "client", onboarding_completed: false })),
    );

    renderOnboardingGuard();

    expect(screen.getByText("completar cadastro")).toBeInTheDocument();
  });

  it("cliente com onboarding completo passa", () => {
    mockUseAuth.mockReturnValue(
      autenticado(usuario({ role: "client", onboarding_completed: true })),
    );

    renderOnboardingGuard();

    expect(screen.getByText("painel")).toBeInTheDocument();
  });

  it("staff passa mesmo sem onboarding — a exigência é só do cliente", () => {
    mockUseAuth.mockReturnValue(
      autenticado(usuario({ role: "technician", onboarding_completed: false })),
    );

    renderOnboardingGuard();

    expect(screen.getByText("painel")).toBeInTheDocument();
  });
});
