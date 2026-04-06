/**
 * Auth context stub — T30 will implement the full JWT flow.
 * For now provides a mock user so the layout renders correctly.
 */
import { createContext, useContext, useState, ReactNode } from "react";
import type { AuthUser } from "../types/auth";

interface AuthContextValue {
  user: AuthUser | null;
  token: string | null;
  login: (token: string, user: AuthUser) => void;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// Temporary mock user — replaced by real JWT data in T30
const MOCK_USER: AuthUser = {
  id: "00000000-0000-0000-0000-000000000001",
  name: "Erick Santos",
  email: "erick@helphs.com",
  role: "admin",
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(MOCK_USER);
  const [token, setToken] = useState<string | null>("mock-token");

  function login(newToken: string, newUser: AuthUser) {
    setToken(newToken);
    setUser(newUser);
  }

  function logout() {
    setToken(null);
    setUser(null);
  }

  return (
    <AuthContext.Provider
      value={{ user, token, login, logout, isAuthenticated: !!user }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
