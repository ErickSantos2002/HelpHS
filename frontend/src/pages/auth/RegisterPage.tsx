import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Alert, Button, Input } from "../../components/ui";
import api from "../../services/api";

interface RegisterPayload {
  name: string;
  email: string;
  password: string;
  phone: string | null;
  department: string | null;
  lgpd_consent: boolean;
}

async function registerUser(payload: RegisterPayload) {
  const { data } = await api.post("/auth/register", payload);
  return data;
}

export default function RegisterPage() {
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [phone, setPhone] = useState("");
  const [department, setDepartment] = useState("");
  const [lgpd, setLgpd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function validate(): string | null {
    if (!name.trim()) return "Nome é obrigatório.";
    if (!email.trim()) return "E-mail é obrigatório.";
    if (password.length < 8) return "A senha deve ter no mínimo 8 caracteres.";
    if (!/[A-Z]/.test(password))
      return "A senha deve conter ao menos uma letra maiúscula.";
    if (!/[0-9]/.test(password))
      return "A senha deve conter ao menos um número.";
    if (password !== confirm) return "As senhas não coincidem.";
    if (!lgpd)
      return "Você deve aceitar os termos de uso e a política de privacidade para criar uma conta.";
    return null;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await registerUser({
        name: name.trim(),
        email: email.trim(),
        password,
        phone: phone.trim() || null,
        department: department.trim() || null,
        lgpd_consent: true,
      });
      navigate("/login", {
        state: { registered: true },
        replace: true,
      });
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response
        ?.status;
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;

      if (status === 409) {
        setError("Este e-mail já está cadastrado. Tente fazer login.");
      } else if (detail) {
        setError(detail);
      } else {
        setError("Erro ao criar conta. Tente novamente.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4 py-8">
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
            <h1 className="text-lg font-semibold text-slate-100">
              Criar conta
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">
              Preencha os dados abaixo para se registrar
            </p>
          </div>

          {error && (
            <Alert variant="danger" onDismiss={() => setError(null)}>
              {error}
            </Alert>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              label="Nome completo"
              type="text"
              placeholder="Seu nome"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
              autoFocus
              required
            />
            <Input
              label="E-mail"
              type="email"
              placeholder="email@empresa.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
            />
            <Input
              label="Senha"
              type="password"
              placeholder="Mín. 8 caracteres, 1 maiúscula e 1 número"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              required
            />
            <Input
              label="Confirmar senha"
              type="password"
              placeholder="••••••••"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              required
            />

            {/* Optional fields */}
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Telefone"
                type="tel"
                placeholder="(11) 99999-9999"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                autoComplete="tel"
              />
              <Input
                label="Departamento"
                type="text"
                placeholder="Ex: TI, RH"
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
              />
            </div>

            {/* LGPD consent */}
            <label className="flex items-start gap-3 cursor-pointer group">
              <input
                type="checkbox"
                checked={lgpd}
                onChange={(e) => setLgpd(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-border bg-background-elevated accent-primary cursor-pointer"
              />
              <span className="text-xs text-slate-400 leading-relaxed">
                Li e aceito os{" "}
                <span className="text-primary">termos de uso</span> e a{" "}
                <span className="text-primary">política de privacidade</span>,
                incluindo o tratamento dos meus dados conforme a LGPD.
              </span>
            </label>

            <Button
              type="submit"
              variant="primary"
              size="lg"
              loading={loading}
              className="w-full"
            >
              Criar conta
            </Button>
          </form>

          <p className="text-center text-sm text-slate-500">
            Já tem uma conta?{" "}
            <Link
              to="/login"
              className="text-primary hover:text-primary/80 transition-colors font-medium"
            >
              Entrar
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
