import { lazy, Suspense } from "react";
import { Routes, Route } from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext";
import { ThemeProvider } from "./contexts/ThemeContext";
import { AppLayout } from "./components/layout/AppLayout";
import { AuthGuard } from "./components/layout/AuthGuard";
import { RoleGuard } from "./components/layout/RoleGuard";
import { PublicOnlyRoute } from "./components/layout/PublicOnlyRoute";
import { OnboardingGuard } from "./components/layout/OnboardingGuard";
import { OnboardingOnlyRoute } from "./components/layout/OnboardingOnlyRoute";
import { Spinner } from "./components/ui";

// Pages (lazy-loaded for code splitting)
const LoginPage = lazy(() => import("./pages/auth/LoginPage"));
const RegisterPage = lazy(() => import("./pages/auth/RegisterPage"));
const VerifyEmailPage = lazy(() => import("./pages/auth/VerifyEmailPage"));
const PoliticaPrivacidadePage = lazy(
  () => import("./pages/legal/PoliticaPrivacidadePage"),
);
const ForgotPasswordPage = lazy(() => import("./pages/auth/ForgotPasswordPage"));
const ResetPasswordPage = lazy(() => import("./pages/auth/ResetPasswordPage"));
const OnboardingPage = lazy(() => import("./pages/onboarding/OnboardingPage"));
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
const KBListPage = lazy(() => import("./pages/kb/KBListPage"));
const KBArticlePage = lazy(() => import("./pages/kb/KBArticlePage"));
const KBFormPage = lazy(() => import("./pages/kb/KBFormPage"));
const ReportsPage = lazy(() => import("./pages/reports/ReportsPage"));
const GroupsPage = lazy(() => import("./pages/groups/GroupsPage"));
const CalendarPage = lazy(() => import("./pages/calendar/CalendarPage"));
const ProfilePage = lazy(() => import("./pages/profile/ProfilePage"));
const EquipmentPage = lazy(() => import("./pages/equipment/EquipmentPage"));
const AuditLogsPage = lazy(() => import("./pages/audit/AuditLogsPage"));
const SettingsPage = lazy(() => import("./pages/settings/SettingsPage"));
const QuickRepliesPage = lazy(() => import("./pages/settings/QuickRepliesPage"));
const ForbiddenPage = lazy(() => import("./pages/errors/ForbiddenPage"));
const NotFoundPage = lazy(() => import("./pages/errors/NotFoundPage"));

/* Galeria da casca — SO EM DESENVOLVIMENTO (src/dev/GaleriaCasca.tsx).
 * O ternario e o guarda: no build `import.meta.env.DEV` vira `false`, o ramo
 * com o import dinamico fica inalcancavel e o Rollup nao emite o chunk. Por
 * isso o `lazy()` mora dentro da condicao, e nao fora dela — se ficasse fora,
 * o chunk seria gerado mesmo sem rota que o use. Sai na Fase 20. */
const GaleriaCasca = import.meta.env.DEV
  ? lazy(() => import("./dev/GaleriaCasca"))
  : null;

/* Galeria dos primitivos — mesma regra, mesmo guarda, mesma saida na Fase 20. */
const GaleriaPrimitivos = import.meta.env.DEV
  ? lazy(() => import("./dev/GaleriaPrimitivos"))
  : null;

function Loading() {
  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <Spinner size="lg" />
    </div>
  );
}

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
      <Suspense fallback={<Loading />}>
        <Routes>
          {/* ── Public only ──────────────────────────────────── */}
          <Route element={<PublicOnlyRoute />}>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/esqueci-senha" element={<ForgotPasswordPage />} />
            <Route path="/redefinir-senha" element={<ResetPasswordPage />} />
          </Route>

          {/* Confirmação de e-mail — acessível mesmo com sessão aberta, já que
              o link pode ser clicado em outro navegador */}
          <Route path="/confirmar-email" element={<VerifyEmailPage />} />

          {/* Política de privacidade — pública e fora do PublicOnlyRoute: é
              lida por quem está se cadastrando (sem sessão) e por quem já usa
              o sistema (com sessão). */}
          <Route path="/privacidade" element={<PoliticaPrivacidadePage />} />

          {/* Galeria da casca — nao existe no bundle de producao. */}
          {GaleriaCasca && (
            <Route path="/galeria-ds" element={<GaleriaCasca />} />
          )}
          {GaleriaPrimitivos && (
            <Route path="/galeria-primitivos" element={<GaleriaPrimitivos />} />
          )}

          {/* ── Error pages ──────────────────────────────────── */}
          <Route path="/403" element={<ForbiddenPage />} />
          <Route path="*" element={<NotFoundPage />} />

          {/* ── Protected ────────────────────────────────────── */}
          <Route element={<AuthGuard />}>
            {/* Onboarding — outside AppLayout, no nav. O OnboardingOnlyRoute
                é o par do OnboardingGuard: um empurra para cá quem ainda deve
                preencher, o outro tira daqui quem não tem o que preencher. */}
            <Route element={<OnboardingOnlyRoute />}>
              <Route path="/onboarding" element={<OnboardingPage />} />
            </Route>

            <Route element={<OnboardingGuard />}>
              <Route element={<AppLayout />}>
                {/* All authenticated roles */}
                <Route path="/" element={<HomePage />} />
                <Route path="/tickets" element={<TicketListPage />} />
                <Route path="/tickets/new" element={<TicketFormPage />} />
                <Route path="/tickets/:id/edit" element={<TicketFormPage />} />
                <Route path="/tickets/:id" element={<TicketDetailPage />} />
                <Route path="/notifications" element={<NotificationsPage />} />
                <Route path="/kb" element={<KBListPage />} />
                <Route path="/kb/new" element={<KBFormPage />} />
                <Route path="/kb/:id/edit" element={<KBFormPage />} />
                <Route path="/kb/:id" element={<KBArticlePage />} />
                <Route path="/profile" element={<ProfilePage />} />
                <Route path="/equipment" element={<EquipmentPage />} />

                {/* Admin + Technician */}
                <Route element={<RoleGuard roles={["admin", "technician"]} />}>
                  <Route path="/reports" element={<ReportsPage />} />
                  <Route path="/agenda" element={<CalendarPage />} />
                </Route>

                {/* Admin + Technician */}
                <Route element={<RoleGuard roles={["admin", "technician"]} />}>
                  <Route path="/users" element={<UsersPage />} />
                  <Route path="/products" element={<ProductsPage />} />
                  <Route path="/etiquetas" element={<SettingsPage />} />
                  <Route path="/respostas-rapidas" element={<QuickRepliesPage />} />
                  <Route path="/grupos" element={<GroupsPage />} />
                </Route>

                {/* Admin only */}
                <Route element={<RoleGuard roles={["admin"]} />}>
                  <Route path="/sla-config" element={<SlaConfigPage />} />
                  <Route path="/audit-logs" element={<AuditLogsPage />} />
                </Route>
              </Route>
            </Route>
          </Route>
        </Routes>
      </Suspense>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
