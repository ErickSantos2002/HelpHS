import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
} from "react";
import type { ReactNode } from "react";
import type { AuthUser } from "../types/auth";
import { tokenStorage } from "../services/api";
import { getMeApi, loginApi, logoutApi } from "../services/authService";

interface AuthContextValue {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Restore session from localStorage on mount
  useEffect(() => {
    async function restore() {
      const stored = tokenStorage.getAccess();
      if (!stored) {
        setIsLoading(false);
        return;
      }
      try {
        setToken(stored);
        const me = await getMeApi();
        setUser({ id: me.id, name: me.name, email: me.email, role: me.role });
      } catch {
        // Token invalid or expired beyond refresh — clear session
        tokenStorage.clear();
        setToken(null);
      } finally {
        setIsLoading(false);
      }
    }
    restore();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await loginApi({ email, password });
    tokenStorage.set(tokens.access_token, tokens.refresh_token);
    setToken(tokens.access_token);

    const me = await getMeApi();
    setUser({ id: me.id, name: me.name, email: me.email, role: me.role });
  }, []);

  const logout = useCallback(async () => {
    await logoutApi();
    tokenStorage.clear();
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
      }}
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
