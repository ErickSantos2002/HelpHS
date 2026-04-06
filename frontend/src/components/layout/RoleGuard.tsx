import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";
import type { UserRole } from "../../types/auth";

interface RoleGuardProps {
  roles: UserRole[];
}

/**
 * Restricts child routes to specific roles.
 * Redirects to /403 if the current user's role is not in the allowed list.
 */
export function RoleGuard({ roles }: RoleGuardProps) {
  const { user } = useAuth();

  if (!user || !roles.includes(user.role)) {
    return <Navigate to="/403" replace />;
  }

  return <Outlet />;
}
