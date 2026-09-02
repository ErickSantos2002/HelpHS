/**
 * Galeria da casca — ARTEFATO DE DESENVOLVIMENTO. NÃO VAI PARA PRODUÇÃO.
 *
 * Existe para uma coisa só: dar ao Checkpoint 1 o screenshot que a seção 26 do
 * prompt mestre exige — sidebar expandida, recolhida e gaveta mobile, mais a
 * topbar, nos dois temas — sem depender de backend, de sessão e de dado real.
 *
 * Três garantias, nesta ordem:
 *
 * 1. **Só em desenvolvimento.** A rota é registrada no `App.tsx` dentro de um
 *    `import.meta.env.DEV`. Em `npm run build` o Rollup elimina o ramo inteiro
 *    (a constante é substituída por `false` e o código morto some), então este
 *    arquivo não entra no bundle publicado. Conferido no relatório do
 *    Checkpoint 1 procurando "galeria" nos assets gerados.
 * 2. **Dado falso, cravado aqui.** O usuário abaixo é inventado. A galeria
 *    monta `Sidebar` e `Topbar` — os componentes reais, não cópias — sobre um
 *    `AuthContext.Provider` local. Nada de `AuthProvider`, nada de token, nada
 *    de `/auth/me`.
 * 3. **Sai na Fase 20.** Junto com este arquivo saem o bloco `DEV` do
 *    `App.tsx` e o `export` do `AuthContext`.
 *
 * A única chamada de rede que a `Topbar` faz por conta própria é o contador de
 * não lidas (`getNotifications`), e ela já engole o erro — sem backend o
 * contador fica em zero. O script de captura
 * (`scripts/capturar-casca.mjs`) intercepta toda requisição de qualquer jeito,
 * inclusive essa, e falha se alguma escapar.
 *
 * Estado vem por query string, para o script poder pedir um estado por vez:
 *
 *   /galeria-ds?estado=expandida    sidebar 256px
 *   /galeria-ds?estado=recolhida    sidebar 72px
 *   /galeria-ds?estado=gaveta       drawer aberto (use viewport estreita)
 */
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AuthContext } from "../contexts/AuthContext";
import { Sidebar } from "../components/layout/Sidebar";
import { Topbar } from "../components/layout/Topbar";
import type { AuthUser } from "../types/auth";

/** Pessoa que não existe. Nome curto de propósito: nome longo esconderia o
 *  truncamento do título da topbar, que é justamente o que se quer olhar. */
const USUARIO_FALSO: AuthUser = {
  id: "00000000-0000-4000-8000-000000000000",
  name: "Ana Ferreira",
  email: "ana.ferreira@exemplo.invalid",
  role: "admin",
  avatar_url: null,
  onboarding_completed: true,
};

type Estado = "expandida" | "recolhida" | "gaveta";

function eEstado(v: string | null): v is Estado {
  return v === "expandida" || v === "recolhida" || v === "gaveta";
}

export default function GaleriaCasca() {
  const [params] = useSearchParams();
  const bruto = params.get("estado");
  const estado: Estado = eEstado(bruto) ? bruto : "expandida";

  // A gaveta é estado da própria galeria para o screenshot poder pegá-la
  // aberta; nos outros dois modos ela fica fechada, como no app.
  const [gavetaAberta, setGavetaAberta] = useState(estado === "gaveta");

  const auth = useMemo(
    () => ({
      user: USUARIO_FALSO,
      token: "token-de-galeria-nao-serve-para-nada",
      isAuthenticated: true,
      isLoading: false,
      login: async () => ({ mfaRequired: false }) as const,
      verifyMfa: async () => {},
      logout: async () => {},
      markOnboardingComplete: () => {},
      updateAvatarUrl: () => {},
    }),
    [],
  );

  return (
    <AuthContext.Provider value={auth}>
      <div
        className="flex h-screen overflow-hidden bg-background"
        data-galeria={estado}
      >
        <Sidebar
          collapsed={estado === "recolhida"}
          mobileOpen={gavetaAberta}
          onMobileClose={() => setGavetaAberta(false)}
        />

        <div className="flex flex-1 flex-col overflow-hidden min-w-0">
          <Topbar
            onMobileMenuClick={() => setGavetaAberta(true)}
            onToggleCollapsed={() => {}}
            sidebarCollapsed={estado === "recolhida"}
            pageTitle="Chamados"
          />

          <main
            id="main-content"
            className="flex-1 overflow-y-auto p-4 md:p-6"
          >
            {/* Conteúdo mínimo: o objeto do screenshot é a casca, não a
                página. O cartão existe só para provar superfície, borda e
                raio contra o fundo — se ele sumir no tema claro, é bug de
                token, não de conteúdo. */}
            <div className="rounded-xl border border-border bg-background-surface p-5">
              <h2 className="text-sm font-semibold text-conteudo-heading">
                Galeria da casca — {estado}
              </h2>
              <p className="mt-1 text-sm text-conteudo-muted">
                Dado falso. Rota de desenvolvimento; sai na Fase 20.
              </p>
            </div>
          </main>
        </div>
      </div>
    </AuthContext.Provider>
  );
}
