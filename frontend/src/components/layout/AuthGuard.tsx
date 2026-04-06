import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Spinner } from "../ui";
import { useAuth } from "../../contexts/AuthContext";

/**
 * Protects all child routes: redirects to /login if not authenticated.
 * While the session is being restored (isLoading), shows a full-screen spinner.
 */
export function AuthGuard() {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  return <Outlet />;
}
