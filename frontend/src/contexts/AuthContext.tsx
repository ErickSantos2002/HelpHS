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
import {
  getMeApi,
  isMfaChallenge,
  loginApi,
  logoutApi,
  verifyMfaApi,
} from "../services/authService";
import type { TokenResponse } from "../services/authService";

/**
 * O que o `login` devolve.
 *
 * Nunca é `void`: quem chama precisa saber se a sessão existe ou se falta o
 * segundo fator, e um retorno que não diz isso empurraria a decisão para um
 * `isAuthenticated` que ainda não mudou.
 */
export type ResultadoLogin =
  | { mfaRequired: false }
  | { mfaRequired: true; mfaToken: string };

interface AuthContextValue {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<ResultadoLogin>;
  /** Segundo passo do login: troca o desafio por sessão. */
  verifyMfa: (mfaToken: string, code: string) => Promise<void>;
  logout: () => Promise<void>;
  markOnboardingComplete: () => void;
  updateAvatarUrl: (url: string | null) => void;
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
        setUser({
          id: me.id,
          name: me.name,
          email: me.email,
          role: me.role,
          avatar_url: me.avatar_url ?? null,
          onboarding_completed: me.onboarding_completed,
        });
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

  /**
   * Guarda os tokens e carrega o usuário.
   *
   * Os dois caminhos do login — com e sem segundo fator — passam por aqui. Duas
   * cópias divergiriam na primeira mudança, e a que divergisse seria a menos
   * usada.
   */
  const estabelecerSessao = useCallback(async (tokens: TokenResponse) => {
    tokenStorage.set(tokens.access_token, tokens.refresh_token);
    setToken(tokens.access_token);

    const me = await getMeApi();
    setUser({
      id: me.id,
      name: me.name,
      email: me.email,
      role: me.role,
      avatar_url: me.avatar_url ?? null,
      onboarding_completed: me.onboarding_completed,
    });
  }, []);

  const login = useCallback(
    async (email: string, password: string): Promise<ResultadoLogin> => {
      const resultado = await loginApi({ email, password });

      if (isMfaChallenge(resultado)) {
        // Nada é gravado aqui: sem o código não há sessão, e guardar qualquer
        // coisa agora deixaria estado pela metade se a pessoa fechasse a aba.
        return { mfaRequired: true, mfaToken: resultado.mfa_token };
      }

      await estabelecerSessao(resultado);
      return { mfaRequired: false };
    },
    [estabelecerSessao],
  );

  const verifyMfa = useCallback(
    async (mfaToken: string, code: string) => {
      await estabelecerSessao(await verifyMfaApi(mfaToken, code));
    },
    [estabelecerSessao],
  );

  const logout = useCallback(async () => {
    await logoutApi();
    tokenStorage.clear();
    setToken(null);
    setUser(null);
  }, []);

  const markOnboardingComplete = useCallback(() => {
    setUser((prev) => (prev ? { ...prev, onboarding_completed: true } : prev));
  }, []);

  const updateAvatarUrl = useCallback((url: string | null) => {
    setUser((prev) => (prev ? { ...prev, avatar_url: url } : prev));
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user,
        isLoading,
        login,
        verifyMfa,
        logout,
        markOnboardingComplete,
        updateAvatarUrl,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
