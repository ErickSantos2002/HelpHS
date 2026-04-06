import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";

/**
 * Prevents authenticated users from accessing public-only routes (e.g. /login).
 * Redirects to / if already logged in.
 */
export function PublicOnlyRoute() {
  const { isAuthenticated, isLoading } = useAuth();

  // While loading, don't redirect — wait for session restore
  if (isLoading) return null;

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
