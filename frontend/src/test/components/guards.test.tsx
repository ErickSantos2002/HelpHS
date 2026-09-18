import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
import LoginPage from "../../pages/auth/LoginPage";

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
 * O `AuthGuard` grava `location.pathname` em `state.from`, e o login faz
 * `navigate(from)`. Um `from` começando com `//` vira URL
 * protocolo-relativa e leva o usuário para outro domínio.
 *
 * Estes testes nasceram dos dois open redirects do react-router
 * (GHSA-wrjc-x8rr-h8h6 e GHSA-2j2x-hqr9-3h42), fechados na subida para
 * 7.18.3. Continuam aqui porque a biblioteca era a segunda barreira, não
 * a primeira: o que impede um caminho hostil de virar `from` é a tabela
 * de rotas do App, e essa é nossa. Um curinga sob o AuthGuard reabre o
 * buraco mesmo com o react-router corrigido.
 *
 * Limite honesto: o `MemoryRouter` não navega de verdade. Ele prova o que
 * chega a `state.from`; não prova o que o navegador faria com um `from`
 * ruim. Essa outra metade é da biblioteca, e a evidência dela é a versão
 * instalada mais o `npm audit` limpo para o pacote.
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

  // Formas que CHEGAM ao router já começando por `//`. São estas que a
  // mutação derruba: movendo o curinga para dentro do AuthGuard, todas
  // falham. Caminho com `..` ficou de fora de propósito — passaria a
  // asserção por começar com `/t`, e afirmar segurança ali seria afirmar
  // o que este teste não prova.
  it.each(["//evil.com", "//evil.com/tickets", "///evil.com", "/\\evil.com"])(
    "não devolve %s como destino — seria redirect externo",
    (hostil) => {
      // Um só `/`, e o próximo caractere não pode ser `/` nem `\`.
      expect(destinoDeRetorno(hostil)).toMatch(/^\/(?![/\\])/);
    },
  );

  // Estas nem chegam ao casamento de rota, então passam sem depender da
  // tabela — e por isso SOBREVIVEM à mutação acima. Medido, não suposto:
  //   "\\evil.com"       não casa com rota nenhuma, nem com o curinga
  //   "/%2F%2Fevil.com"  segue percent-encoded — uma barra só
  //   "/%5Cevil.com"     idem
  // Ficam como registro do que já não é ameaça. Se alguma delas voltar a
  // chegar como `//`, quem acusa é o grupo de cima.
  it.each(["\\\\evil.com", "/%2F%2Fevil.com", "/%5Cevil.com"])(
    "%s não chega ao guard como caminho protocolo-relativo",
    (forma) => {
      expect(destinoDeRetorno(forma)).toMatch(/^\/(?![/\\])/);
    },
  );
});

// ── A tabela de rotas de verdade ──────────────────────────────

/**
 * Os testes acima usam um harness que IMITA o App. Estes leem o
 * `App.tsx` de verdade, porque a proteção mora ali: o curinga precisa
 * ficar fora do bloco protegido, e nenhuma rota sob o `AuthGuard` pode
 * casar com caminho iniciado por `//`.
 *
 * O bloco do `AuthGuard` é o último filho de `<Routes>`, então "daqui
 * até o fim" é o bloco protegido. Se alguém puser rota pública depois
 * dele, este teste passa a cobrar demais — erro para o lado seguro, e
 * que obriga a olhar.
 */
describe("App.tsx: a posição do curinga", () => {
  const MARCA_GUARD = "<Route element={<AuthGuard />}>";
  // O vitest roda com a raiz do front como cwd, aqui e no CI
  // (`working-directory: frontend`). Se isso mudar, o teste morre dizendo
  // por quê, em vez de ler string vazia e passar sem medir nada.
  const CAMINHO_APP = resolve(process.cwd(), "src/App.tsx");
  if (!existsSync(CAMINHO_APP)) {
    throw new Error(`Não achei o App.tsx em ${CAMINHO_APP} (cwd=${process.cwd()})`);
  }
  const FONTE = readFileSync(CAMINHO_APP, "utf8");

  it("declara o catch-all uma vez só, e antes do bloco protegido", () => {
    expect(FONTE.match(/path="\*"/g)).toHaveLength(1);
    expect(FONTE.indexOf('path="*"')).toBeLessThan(FONTE.indexOf(MARCA_GUARD));
  });

  it("nenhuma rota sob o AuthGuard casa com caminho iniciado por // ou \\", () => {
    const inicio = FONTE.indexOf(MARCA_GUARD);
    expect(inicio).toBeGreaterThan(-1);

    const protegidas = [...FONTE.slice(inicio).matchAll(/path="([^"]*)"/g)].map(
      (m) => m[1],
    );

    // Guarda contra o regex deixar de casar e o teste virar vácuo.
    expect(protegidas.length).toBeGreaterThan(10);
    for (const rota of protegidas) {
      expect(rota).toMatch(/^\/(?![/\\])/);
    }
  });
});

// ── Fluxo inteiro, com o LoginPage de verdade ─────────────────

/**
 * Os testes acima param no `state.from`. Este vai até o fim: rota
 * protegida sem sessão, tela de login real, submissão, e o
 * `navigate(from)` do `LoginPage`. É onde as duas metades se encontram.
 */
describe("Fluxo: rota protegida -> login -> volta para a rota", () => {
  function monta(rotaInicial: string, comSessao = false) {
    const trilha: string[] = [];
    const login = vi.fn(async () => {
      // Depois do login o contexto passa a devolver sessão, como na app.
      mockUseAuth.mockReturnValue({
        ...autenticado(usuario()),
        login,
        verifyMfa: vi.fn(),
      } as unknown as Auth);
      return { mfaRequired: false };
    });

    mockUseAuth.mockReturnValue({
      ...autenticado(comSessao ? usuario() : null),
      login,
      verifyMfa: vi.fn(),
    } as unknown as Auth);

    function Rastro() {
      const atual = useLocation().pathname;
      if (trilha[trilha.length - 1] !== atual) trilha.push(atual);
      return null;
    }

    render(
      <MemoryRouter initialEntries={[rotaInicial]}>
        <Rastro />
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<div>não encontrado</div>} />
          <Route element={<AuthGuard />}>
            <Route path="/" element={<div>início</div>} />
            <Route path="/tickets/:id" element={<div>detalhe do chamado</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    return trilha;
  }

  async function entra() {
    await userEvent.type(screen.getByLabelText("E-mail"), "alguem@exemplo.com");
    await userEvent.type(screen.getByLabelText("Senha"), "SenhaQualquer1");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
  }

  it("devolve o usuário à rota que ele tentou abrir", async () => {
    const trilha = monta("/tickets/abc");
    expect(screen.getByLabelText("E-mail")).toBeInTheDocument();

    await entra();

    expect(await screen.findByText("detalhe do chamado")).toBeInTheDocument();
    expect(trilha).toContain("/login");
    expect(trilha[trilha.length - 1]).toBe("/tickets/abc");
  });

  it("sem rota de origem, o login cai na raiz — nunca fora do domínio", async () => {
    const trilha = monta("/login");

    await entra();

    expect(await screen.findByText("início")).toBeInTheDocument();
    expect(trilha[trilha.length - 1]).toBe("/");
  });

  it("usuário já autenticado abre a rota sem passar pelo login", () => {
    const trilha = monta("/tickets/abc", true);

    expect(screen.getByText("detalhe do chamado")).toBeInTheDocument();
    expect(trilha).not.toContain("/login");
  });

  it("rota inexistente cai no NotFound, sem acionar o guard", () => {
    const trilha = monta("/rota-que-nao-existe");

    expect(screen.getByText("não encontrado")).toBeInTheDocument();
    expect(trilha).not.toContain("/login");
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
