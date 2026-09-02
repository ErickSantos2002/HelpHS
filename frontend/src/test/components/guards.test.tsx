import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { AuthGuard } from "../../components/layout/AuthGuard";
import { RoleGuard } from "../../components/layout/RoleGuard";
import { OnboardingGuard } from "../../components/layout/OnboardingGuard";
import { OnboardingOnlyRoute } from "../../components/layout/OnboardingOnlyRoute";
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

// ── Destino do redirect pós-login ─────────────────────────────

/**
 * Evidência das entradas GHSA-wrjc-x8rr-h8h6 e GHSA-2j2x-hqr9-3h42 do
 * `.github/dependencias-conhecidas.toml` — os dois open redirects do
 * react-router que ALCANÇAM um SPA clássico. O sink existe aqui:
 * `AuthGuard` grava `location.pathname` em `state.from`, e o login faz
 * `navigate(from)`. Um `from` começando com `//` vira URL
 * protocolo-relativa e leva o usuário para outro domínio.
 *
 * O que fecha hoje é o casamento de rota: caminho hostil não casa com
 * rota nenhuma sob o guard e cai no `path="*"`, que não grava `from`.
 * Isso depende da tabela de rotas — daí o teste. Se alguém puser uma
 * rota curinga sob o AuthGuard, é aqui que quebra.
 *
 * Limite honesto: o `MemoryRouter` não passa pela normalização de URL do
 * navegador. A barra invertida é testada crua e na forma que o navegador
 * entregaria (já convertida para `//`).
 */
describe("AuthGuard: destino do retorno pós-login", () => {
  function destinoDeRetorno(rotaInicial: string) {
    mockUseAuth.mockReturnValue(autenticado(null));
    let capturado: string | undefined;

    function EspiaLogin() {
      capturado = (useLocation().state as { from?: string })?.from;
      return <div>tela de login</div>;
    }

    render(
      <MemoryRouter initialEntries={[rotaInicial]}>
        <Routes>
          <Route path="/login" element={<EspiaLogin />} />
          <Route path="*" element={<div>não encontrado</div>} />
          <Route element={<AuthGuard />}>
            <Route path="/tickets" element={<div>lista</div>} />
            <Route path="/tickets/:id" element={<div>detalhe</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    // O `?? "/"` é o mesmo default de LoginPage.tsx:86 — o teste afirma
    // sobre o valor que o `navigate()` receberia de fato.
    return capturado ?? "/";
  }

  it("captura o caminho interno quando a rota é legítima", () => {
    // Controle positivo: sem ele, os casos abaixo passariam mesmo se o
    // helper nunca capturasse nada.
    expect(destinoDeRetorno("/tickets/abc")).toBe("/tickets/abc");
  });

  // Só formas que chegam ao router começando de fato com `//` ou `/\` — as
  // que a mutação (mover o curinga para dentro do guard) derruba. Caminho
  // com `..` ficou de fora de propósito: ele passa nesta asserção por
  // começar com `/t`, e afirmar segurança ali seria afirmar o que este
  // teste não prova.
  it.each(["//evil.com", "//evil.com/tickets", "/\\evil.com", "///evil.com"])(
    "não devolve %s como destino — seria redirect externo",
    (hostil) => {
      // Um só `/`, e o próximo caractere não pode ser `/` nem `\`.
      expect(destinoDeRetorno(hostil)).toMatch(/^\/(?![/\\])/);
    },
  );
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

// ── OnboardingOnlyRoute ───────────────────────────────────────
//
// O par que faltava do OnboardingGuard. Um empurra para /onboarding quem
// ainda deve preencher; o outro tira de lá quem não tem o que preencher.
// Sem ele, /onboarding ficava sob o AuthGuard e fora do OnboardingGuard —
// qualquer autenticado abria a tela digitando a URL, inclusive o staff, que
// não tem onboarding nenhum. A porta que importava já foi fechada no backend
// (b1ab978); aqui é higiene de rota.

function renderOnboardingOnly() {
  return render(
    <MemoryRouter initialEntries={["/onboarding"]}>
      <Routes>
        <Route element={<OnboardingOnlyRoute />}>
          <Route path="/onboarding" element={<div>completar cadastro</div>} />
        </Route>
        <Route path="/" element={<div>painel</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("OnboardingOnlyRoute", () => {
  it("cliente com onboarding pendente vê a tela", () => {
    mockUseAuth.mockReturnValue(
      autenticado(usuario({ role: "client", onboarding_completed: false })),
    );

    renderOnboardingOnly();

    expect(screen.getByText("completar cadastro")).toBeInTheDocument();
  });

  it("cliente que já completou é mandado para a home", () => {
    // Refazer o onboarding sobrescreveria dados de cadastro já revisados.
    mockUseAuth.mockReturnValue(
      autenticado(usuario({ role: "client", onboarding_completed: true })),
    );

    renderOnboardingOnly();

    expect(screen.getByText("painel")).toBeInTheDocument();
  });

  it("staff não tem onboarding — vai para a home mesmo com a flag falsa", () => {
    mockUseAuth.mockReturnValue(
      autenticado(usuario({ role: "technician", onboarding_completed: false })),
    );

    renderOnboardingOnly();

    expect(screen.getByText("painel")).toBeInTheDocument();
  });

  it("admin também", () => {
    mockUseAuth.mockReturnValue(
      autenticado(usuario({ role: "admin", onboarding_completed: false })),
    );

    renderOnboardingOnly();

    expect(screen.getByText("painel")).toBeInTheDocument();
  });

  it("sem usuário, não mostra a tela (fail closed)", () => {
    // O AuthGuard já teria barrado antes; se um dia deixar de barrar, esta
    // rota não pode ser a brecha.
    mockUseAuth.mockReturnValue(autenticado(null));

    renderOnboardingOnly();

    expect(screen.queryByText("completar cadastro")).not.toBeInTheDocument();
  });
});
