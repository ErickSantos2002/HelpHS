import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";

/**
 * Redirects clients that haven't completed onboarding to /onboarding.
 * Admin and technician users pass through unconditionally.
 */
export function OnboardingGuard() {
  const { user } = useAuth();

  if (user?.role === "client" && !user.onboarding_completed) {
    return <Navigate to="/onboarding" replace />;
  }

  return <Outlet />;
}
