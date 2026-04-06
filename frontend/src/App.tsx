import { lazy, Suspense } from "react";
import { Routes, Route } from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext";
import { AppLayout } from "./components/layout/AppLayout";
import { AuthGuard } from "./components/layout/AuthGuard";
import { RoleGuard } from "./components/layout/RoleGuard";
import { PublicOnlyRoute } from "./components/layout/PublicOnlyRoute";
import { Spinner } from "./components/ui";
import PlaceholderPage from "./pages/PlaceholderPage";

// Pages (lazy-loaded for code splitting)
const LoginPage = lazy(() => import("./pages/auth/LoginPage"));
const HomePage = lazy(() => import("./pages/HomePage"));
const ForbiddenPage = lazy(() => import("./pages/errors/ForbiddenPage"));
const NotFoundPage = lazy(() => import("./pages/errors/NotFoundPage"));

function Loading() {
  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <Spinner size="lg" />
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <Suspense fallback={<Loading />}>
        <Routes>
          {/* ── Public only ──────────────────────────────────── */}
          <Route element={<PublicOnlyRoute />}>
            <Route path="/login" element={<LoginPage />} />
          </Route>

          {/* ── Error pages ──────────────────────────────────── */}
          <Route path="/403" element={<ForbiddenPage />} />
          <Route path="*" element={<NotFoundPage />} />

          {/* ── Protected ────────────────────────────────────── */}
          <Route element={<AuthGuard />}>
            <Route element={<AppLayout />}>
              {/* All authenticated roles */}
              <Route path="/" element={<HomePage />} />
              <Route
                path="/tickets"
                element={
                  <PlaceholderPage
                    title="Tickets"
                    description="Listagem de tickets — Sprint 5"
                  />
                }
              />
              <Route
                path="/notifications"
                element={
                  <PlaceholderPage
                    title="Notificações"
                    description="Central de notificações — Sprint 5"
                  />
                }
              />
              <Route
                path="/profile"
                element={
                  <PlaceholderPage
                    title="Meu perfil"
                    description="Edição de perfil — Sprint 5"
                  />
                }
              />

              {/* Admin + Technician */}
              <Route element={<RoleGuard roles={["admin", "technician"]} />}>
                <Route
                  path="/reports"
                  element={
                    <PlaceholderPage
                      title="Relatórios"
                      description="Relatórios e métricas — Sprint 7"
                    />
                  }
                />
              </Route>

              {/* Admin only */}
              <Route element={<RoleGuard roles={["admin"]} />}>
                <Route
                  path="/users"
                  element={
                    <PlaceholderPage
                      title="Usuários"
                      description="Gestão de usuários — Sprint 5"
                    />
                  }
                />
                <Route
                  path="/products"
                  element={
                    <PlaceholderPage
                      title="Produtos e Equipamentos"
                      description="Gestão de produtos — Sprint 5"
                    />
                  }
                />
                <Route
                  path="/audit-logs"
                  element={
                    <PlaceholderPage
                      title="Audit Logs"
                      description="Registros de auditoria — Sprint 7"
                    />
                  }
                />
              </Route>
            </Route>
          </Route>
        </Routes>
      </Suspense>
    </AuthProvider>
  );
}

export default App;
