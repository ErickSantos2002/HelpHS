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
const TicketListPage = lazy(() => import("./pages/tickets/TicketListPage"));
const UsersPage = lazy(() => import("./pages/users/UsersPage"));
const TicketFormPage = lazy(() => import("./pages/tickets/TicketFormPage"));
const TicketDetailPage = lazy(() => import("./pages/tickets/TicketDetailPage"));
const ProductsPage = lazy(() => import("./pages/products/ProductsPage"));
const SlaConfigPage = lazy(() => import("./pages/sla/SlaConfigPage"));
const NotificationsPage = lazy(
  () => import("./pages/notifications/NotificationsPage"),
);
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
              <Route path="/tickets" element={<TicketListPage />} />
              <Route path="/tickets/new" element={<TicketFormPage />} />
              <Route path="/tickets/:id/edit" element={<TicketFormPage />} />
              <Route path="/tickets/:id" element={<TicketDetailPage />} />
              <Route path="/notifications" element={<NotificationsPage />} />
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
                <Route path="/users" element={<UsersPage />} />
                <Route path="/products" element={<ProductsPage />} />
                <Route path="/sla-config" element={<SlaConfigPage />} />
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
