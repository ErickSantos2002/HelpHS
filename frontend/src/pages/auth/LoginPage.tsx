import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Alert, Button, Input } from "../../components/ui";
import { useAuth } from "../../contexts/AuthContext";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Redirect to the page the user was trying to access, or /
  const from = (location.state as { from?: string })?.from ?? "/";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!email || !password) return;

    setLoading(true);
    setError(null);

    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response
        ?.status;
      if (status === 401 || status === 422) {
        setError("E-mail ou senha incorretos.");
      } else {
        setError("Erro ao conectar com o servidor. Tente novamente.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-8">
        {/* Logo */}
        <div className="text-center space-y-2">
          <div className="flex items-center justify-center gap-2.5">
            <span className="w-3 h-3 rounded-full bg-primary" />
            <span className="text-2xl font-bold text-slate-100 tracking-tight">
              Help<span className="text-primary">HS</span>
            </span>
          </div>
          <p className="text-sm text-slate-500">
            Help Desk — Saúde &amp; Segurança do Trabalho
          </p>
        </div>

        {/* Card */}
        <div className="rounded-xl border border-border bg-background-surface p-6 space-y-5 shadow-xl">
          <div>
            <h1 className="text-lg font-semibold text-slate-100">Entrar</h1>
            <p className="text-sm text-slate-500 mt-0.5">
              Acesse sua conta para continuar
            </p>
          </div>

          {error && (
            <Alert variant="danger" onDismiss={() => setError(null)}>
              {error}
            </Alert>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              label="E-mail"
              type="email"
              placeholder="email@empresa.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              autoFocus
              required
            />
            <Input
              label="Senha"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
            <Button
              type="submit"
              variant="primary"
              size="lg"
              loading={loading}
              className="w-full"
            >
              Entrar
            </Button>
          </form>
        </div>

        <p className="text-center text-xs text-slate-600">
          Problemas para acessar? Contate o administrador do sistema.
        </p>
      </div>
    </div>
  );
}
