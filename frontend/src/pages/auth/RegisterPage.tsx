import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Alert, Button, Input } from "../../components/ui";
import { api } from "../../services/api";
import logoFull from "../../assets/Logo HelpHS.png";

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

const STEPS = [
  { num: 1, label: "Dados pessoais" },
  { num: 2, label: "Acesso" },
  { num: 3, label: "Confirmação" },
];

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
    if (!/[A-Z]/.test(password)) return "A senha deve conter ao menos uma letra maiúscula.";
    if (!/[0-9]/.test(password)) return "A senha deve conter ao menos um número.";
    if (password !== confirm) return "As senhas não coincidem.";
    if (!lgpd) return "Você deve aceitar os termos de uso para criar uma conta.";
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
      navigate("/login", { state: { registered: true }, replace: true });
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
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
    <div className="min-h-screen flex">
      {/* ── Left panel 60% — branding ───────────────────────── */}
      <div className="hidden lg:flex lg:w-3/5 relative flex-col justify-between overflow-hidden bg-[#080F1A] px-14 py-12">
        {/* Decorative blobs */}
        <div className="pointer-events-none absolute -top-32 -right-32 w-[500px] h-[500px] rounded-full blur-[120px]" style={{ backgroundColor: "rgba(14,165,233,0.18)" }} />
        <div className="pointer-events-none absolute -bottom-40 -left-20 w-[400px] h-[400px] rounded-full blur-[100px]" style={{ backgroundColor: "rgba(14,165,233,0.09)" }} />

        {/* Logo */}
        <div className="relative z-10">
          <img src={logoFull} alt="HelpHS" className="h-10 w-auto object-contain" />
        </div>

        {/* Main copy */}
        <div className="relative z-10 space-y-10">
          <div className="space-y-4">
            <div className="inline-flex items-center gap-2 rounded-full px-3 py-1" style={{ border: "1px solid rgba(14,165,233,0.3)", backgroundColor: "rgba(14,165,233,0.1)" }}>
              <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
              <span className="text-xs font-medium text-primary">Crie sua conta gratuitamente</span>
            </div>
            <h1 className="text-4xl font-bold text-white leading-tight">
              Comece a usar<br />
              em minutos
            </h1>
            <p className="text-base text-slate-400 leading-relaxed max-w-md">
              Junte-se à plataforma que simplifica o suporte em Saúde e Segurança do Trabalho para equipes de todos os tamanhos.
            </p>
          </div>

          {/* How it works */}
          <div className="space-y-3">
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-600">Como funciona</p>
            <div className="space-y-4">
              {STEPS.map((step, i) => (
                <div key={step.num} className="flex items-center gap-4">
                  <div className="relative shrink-0 flex items-center justify-center w-8 h-8 rounded-full" style={{ backgroundColor: "rgba(14,165,233,0.12)", border: "1px solid rgba(14,165,233,0.3)" }}>
                    <span className="text-xs font-bold text-primary">{step.num}</span>
                    {i < STEPS.length - 1 && (
                      <div className="absolute top-full left-1/2 -translate-x-1/2 w-px h-4 bg-primary/20 mt-0.5" />
                    )}
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-white">{step.label}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Trust signals */}
          <div className="flex flex-wrap gap-4">
            {[
              {
                label: "Dados protegidos por LGPD",
                icon: (
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                ),
              },
              {
                label: "Setup em menos de 2 min",
                icon: (
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                ),
              },
              {
                label: "Ambiente seguro e criptografado",
                icon: (
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                  </svg>
                ),
              },
            ].map((t) => (
              <div key={t.label} className="flex items-center gap-2">
                <span className="text-primary">{t.icon}</span>
                <span className="text-xs text-slate-500">{t.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="relative z-10">
          <p className="text-xs text-slate-600">
            © {new Date().getFullYear()} HelpHS — Health &amp; Safety Tech. Todos os direitos reservados.
          </p>
        </div>
      </div>

      {/* ── Right panel 40% — form ──────────────────────────── */}
      <div className="flex flex-1 lg:w-2/5 flex-col items-center justify-center bg-background px-6 py-12 overflow-y-auto">
        <div className="w-full max-w-sm space-y-7">
          {/* Mobile logo */}
          <div className="flex lg:hidden items-center justify-center gap-2.5">
            <img src={logoFull} alt="HelpHS" className="h-8 w-auto object-contain" />
          </div>

          {/* Heading */}
          <div className="space-y-1">
            <h2 className="text-2xl font-bold text-slate-100">Criar conta</h2>
            <p className="text-sm text-slate-500">Preencha os dados abaixo para se registrar</p>
          </div>

          {/* Error alert */}
          {error && (
            <Alert variant="danger" onDismiss={() => setError(null)}>
              {error}
            </Alert>
          )}

          {/* Form */}
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
              placeholder="Mín. 8 caracteres, 1 maiúscula, 1 número"
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

            {/* LGPD */}
            <label className="flex items-start gap-3 cursor-pointer">
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

          {/* Footer */}
          <p className="text-center text-sm text-slate-500">
            Já tem uma conta?{" "}
            <Link to="/login" className="text-primary hover:text-primary-400 transition-colors font-medium">
              Entrar
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
