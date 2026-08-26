/**
 * Axios instance with JWT interceptors.
 *
 * Request:  attaches Authorization: Bearer <access_token>
 * Response: on 401, tries to refresh the token once, then retries;
 *           if refresh fails, clears session and redirects to /login.
 */
import axios, { AxiosError } from "axios";
import type { InternalAxiosRequestConfig } from "axios";

const BASE_URL = import.meta.env.VITE_API_URL ?? "/api/v1";

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
});

// ── Token helpers ─────────────────────────────────────────────

const TOKEN_KEY = "helphs_access_token";
const REFRESH_KEY = "helphs_refresh_token";

export const tokenStorage = {
  getAccess: () => localStorage.getItem(TOKEN_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  set: (access: string, refresh: string) => {
    localStorage.setItem(TOKEN_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },
  /**
   * Só o access token. A renovação (`/auth/refresh`) não devolve refresh novo,
   * e passar `undefined` para `set` gravaria a string "undefined" no lugar do
   * refresh válido — daí os dois caminhos serem métodos separados.
   */
  setAccess: (access: string) => {
    localStorage.setItem(TOKEN_KEY, access);
  },
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

// ── Refresh queue ─────────────────────────────────────────────

type QueueItem = {
  resolve: (token: string) => void;
  reject: (err: unknown) => void;
};

let isRefreshing = false;
let failedQueue: QueueItem[] = [];

function processQueue(error: unknown, token: string | null) {
  failedQueue.forEach((item) => {
    if (error) item.reject(error);
    else item.resolve(token!);
  });
  failedQueue = [];
}

// ── Request interceptor ───────────────────────────────────────

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStorage.getAccess();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Response interceptor ──────────────────────────────────────

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    const is401 = error.response?.status === 401;
    const isRefreshEndpoint = original.url?.includes("/auth/refresh");
    const alreadyRetried = original._retry;

    if (!is401 || isRefreshEndpoint || alreadyRetried) {
      return Promise.reject(error);
    }

    if (isRefreshing) {
      // Queue this request until the ongoing refresh completes
      return new Promise<string>((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      }).then((newToken) => {
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      });
    }

    original._retry = true;
    isRefreshing = true;

    const refreshToken = tokenStorage.getRefresh();
    if (!refreshToken) {
      isRefreshing = false;
      tokenStorage.clear();
      window.location.href = "/login";
      return Promise.reject(error);
    }

    try {
      // Espelha `AccessTokenResponse` do backend (app/schemas/auth.py): a
      // renovação devolve só o access token. O refresh continua o mesmo, válido
      // até o próprio vencimento — reescrevê-lo aqui é o que destruía a sessão.
      const { data } = await axios.post<{
        access_token: string;
        token_type: string;
        expires_in: number;
      }>(`${BASE_URL}/auth/refresh`, { refresh_token: refreshToken });

      tokenStorage.setAccess(data.access_token);
      api.defaults.headers.common.Authorization = `Bearer ${data.access_token}`;

      processQueue(null, data.access_token);
      original.headers.Authorization = `Bearer ${data.access_token}`;
      return api(original);
    } catch (refreshError) {
      processQueue(refreshError, null);
      tokenStorage.clear();
      window.location.href = "/login";
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  },
);
