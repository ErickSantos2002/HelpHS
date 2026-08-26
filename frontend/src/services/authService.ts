import { api } from "./api";
import type { AuthUser } from "../types/auth";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface MeResponse {
  id: string;
  name: string;
  email: string;
  role: AuthUser["role"];
  avatar_url?: string | null;
  onboarding_completed: boolean;
}

/**
 * Desafio de segundo fator: a senha valeu, mas ainda não há sessão.
 *
 * Chega como 403, e não como 200 com campos vazios, para que nenhum caminho do
 * código consiga confundir "falta o código" com "entrou".
 */
export interface MfaChallenge {
  mfa_required: true;
  mfa_token: string;
  expires_in: number;
}

export type LoginResult = TokenResponse | MfaChallenge;

export function isMfaChallenge(resultado: LoginResult): resultado is MfaChallenge {
  return (resultado as MfaChallenge).mfa_required === true;
}

/**
 * Entra com e-mail e senha.
 *
 * O desafio de segundo fator é o único 403 que vira valor de retorno em vez de
 * erro; todos os outros continuam sendo lançados, porque a tela de login já
 * distingue "confirme seu e-mail" de "conta inativa" pela mensagem. A conversão
 * mora aqui, num ponto só, para que nenhuma tela precise saber que o desafio
 * chega com status de erro.
 */
export async function loginApi(body: LoginRequest): Promise<LoginResult> {
  try {
    const { data } = await api.post<TokenResponse>("/auth/login", body);
    return data;
  } catch (err) {
    const resposta = (err as { response?: { status?: number; data?: unknown } })?.response;
    const corpo = resposta?.data as Partial<MfaChallenge> | undefined;
    if (resposta?.status === 403 && corpo?.mfa_required === true && corpo.mfa_token) {
      return corpo as MfaChallenge;
    }
    throw err;
  }
}

/** Troca o desafio pelo par de tokens, se o código conferir. */
export async function verifyMfaApi(mfaToken: string, code: string): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>("/auth/mfa/verify", {
    mfa_token: mfaToken,
    code,
  });
  return data;
}

export async function getMeApi(): Promise<MeResponse> {
  const { data } = await api.get<MeResponse>("/users/me");
  return data;
}

export async function logoutApi(): Promise<void> {
  await api.post("/auth/logout").catch(() => {
    // Best-effort: ignore errors on logout
  });
}

// ── Confirmação de e-mail e recuperação de senha ──────────────

interface MessageResponse {
  message: string;
}

/** Confirma o cadastro a partir do link recebido por e-mail. */
export async function verifyEmailApi(token: string): Promise<string> {
  const { data } = await api.post<MessageResponse>("/auth/verify-email", { token });
  return data.message;
}

/** Reenvia o link de confirmação. */
export async function resendVerificationApi(email: string): Promise<string> {
  const { data } = await api.post<MessageResponse>("/auth/resend-verification", { email });
  return data.message;
}

/**
 * Pede o link de redefinição de senha.
 *
 * A resposta é sempre a mesma, mesmo para e-mail que não existe — é assim de
 * propósito, para não revelar quem tem conta no sistema.
 */
export async function forgotPasswordApi(email: string): Promise<string> {
  const { data } = await api.post<MessageResponse>("/auth/forgot-password", { email });
  return data.message;
}

/** Grava a nova senha usando o link recebido por e-mail. */
export async function resetPasswordApi(token: string, password: string): Promise<string> {
  const { data } = await api.post<MessageResponse>("/auth/reset-password", { token, password });
  return data.message;
}

// ── Segundo fator (só staff) ──────────────────────────────────

export interface MfaStatus {
  enabled: boolean;
  /** Segredo cadastrado, aguardando o código que confirma o pareamento. */
  pending: boolean;
  /** Se o ambiente tem chave de cifra; sem ela não dá para cadastrar. */
  available: boolean;
}

export interface MfaSetup {
  /** Base32 agrupado de quatro em quatro, para quem digita à mão. */
  secret: string;
  otpauth_uri: string;
}

export async function getMfaStatusApi(): Promise<MfaStatus> {
  const { data } = await api.get<MfaStatus>("/auth/mfa");
  return data;
}

/**
 * Gera um segredo novo. **Não** liga o segundo fator — ligar só acontece no
 * `activateMfaApi`, depois de um código provar que o aplicativo pareou.
 */
export async function setupMfaApi(): Promise<MfaSetup> {
  const { data } = await api.post<MfaSetup>("/auth/mfa/setup");
  return data;
}

export async function activateMfaApi(code: string): Promise<void> {
  await api.post("/auth/mfa/activate", { code });
}

export async function disableMfaApi(password: string): Promise<void> {
  await api.delete("/auth/mfa", { data: { password } });
}
