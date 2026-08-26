import React, { useState } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { Alert, Button, Input } from "../../components/ui";
import { useAuth } from "../../contexts/AuthContext";
import { resendVerificationApi } from "../../services/authService";
import { getApiError } from "../../lib/apiError";
import logoFull from "../../assets/Logo HelpHS.png";

const FEATURES = [
  {
    title: "Abertura rápida de chamados",
    desc: "Registre incidentes em segundos e acompanhe cada etapa em tempo real.",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z" />
      </svg>
    ),
  },
  {
    title: "SLA automático e inteligente",
    desc: "Prazos, prioridades e escalações gerenciados sem esforço manual.",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    title: "Base de conhecimento integrada",
    desc: "Acesso rápido a soluções, procedimentos e documentações internas.",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
      </svg>
    ),
  },
  {
    title: "Relatórios e dashboards",
    desc: "Métricas em tempo real para decisões mais rápidas e eficientes.",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
  },
];

export default function LoginPage() {
  const { login, verifyMfa } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [precisaConfirmar, setPrecisaConfirmar] = useState(false);
  const [reenviando, setReenviando] = useState(false);
  const [reenviado, setReenviado] = useState(false);

  // Segundo fator: enquanto houver desafio, a tela mostra o campo de código no
  // lugar das credenciais. A senha sai do estado assim que o desafio nasce —
  // ela já cumpriu o papel e não precisa continuar em memória.
  const [desafio, setDesafio] = useState<string | null>(null);
  const [codigo, setCodigo] = useState("");

  const justRegistered =
    (location.state as { registered?: boolean })?.registered === true;
  const passwordReset =
    (location.state as { passwordReset?: boolean })?.passwordReset === true;
  const from = (location.state as { from?: string })?.from ?? "/";

  async function handleReenviarConfirmacao() {
    setReenviando(true);
    try {
      await resendVerificationApi(email);
      setReenviado(true);
    } finally {
      setReenviando(false);
    }
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!email || !password) return;
    setLoading(true);
    setError(null);
    try {
      const resultado = await login(email, password);
      if (resultado.mfaRequired) {
        setDesafio(resultado.mfaToken);
        setPassword("");
        return;
      }
      navigate(from, { replace: true });
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) {
        // Conta existe e a senha está certa — falta confirmar o e-mail ou a
        // conta está inativa. A mensagem do servidor diz qual é o caso.
        const motivo = getApiError(err, "Não foi possível entrar.");
        setError(motivo);
        setPrecisaConfirmar(motivo.toLowerCase().includes("confirme seu e-mail"));
      } else if (status === 401 || status === 422) {
        setError("E-mail ou senha incorretos.");
      } else {
        setError("Erro ao conectar com o servidor. Tente novamente.");
      }
    } finally {
      setLoading(false);
    }
  }

  /** Volta ao passo da senha, descartando o desafio. */
  function recomecar(motivo: string | null) {
    setDesafio(null);
    setCodigo("");
    setError(motivo);
  }

  async function handleVerificar(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!desafio || !codigo) return;
    setLoading(true);
    setError(null);
    try {
      await verifyMfa(desafio, codigo);
      navigate(from, { replace: true });
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      const detalhe = getApiError(err, "Não foi possível verificar o código.");

      if (status === 429) {
        // O desafio foi queimado por excesso de erros: insistir aqui não leva
        // a lugar nenhum, então a tela volta sozinha para o começo.
        recomecar("Muitas tentativas. Entre novamente.");
      } else if (status === 401 && detalhe.toLowerCase().includes("expirou")) {
        recomecar(detalhe);
      } else if (status === 401) {
        setError(detalhe);
        setCodigo("");
      } else {
        setError("Erro ao conectar com o servidor. Tente novamente.");
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
          <img src={logoFull} alt="HelpHS" className="h-14 w-auto object-contain animate-logo-pulse" />
        </div>

        {/* Main copy */}
        <div className="relative z-10 space-y-10">
          <div className="space-y-4">
            <div className="inline-flex items-center gap-2 rounded-full px-3 py-1" style={{ border: "1px solid rgba(14,165,233,0.3)", backgroundColor: "rgba(14,165,233,0.1)" }}>
              <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
              <span className="text-xs font-medium text-primary">Help Desk — Saúde &amp; Segurança</span>
            </div>
            <h1 className="text-4xl font-bold text-white leading-tight">
              Suporte inteligente<br />
              para sua equipe
            </h1>
            <p className="text-base text-slate-400 leading-relaxed max-w-md">
              Plataforma completa para gerenciar chamados, SLA e comunicação interna com foco em Saúde e Segurança do Trabalho.
            </p>
          </div>

          {/* Features */}
          <div className="grid grid-cols-1 gap-5">
            {FEATURES.map((f) => (
              <div key={f.title} className="flex items-start gap-4">
                <div className="shrink-0 flex items-center justify-center w-9 h-9 rounded-lg text-[#0ea5e9]" style={{ backgroundColor: "rgba(14,165,233,0.12)" }}>
                  {f.icon}
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">{f.title}</p>
                  <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{f.desc}</p>
                </div>
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
      <div className="flex flex-1 lg:w-2/5 flex-col items-center justify-center bg-[#0D1623] px-6 py-12">
        <div className="w-full max-w-sm space-y-8">
          {/* Mobile logo */}
          <div className="flex lg:hidden items-center justify-center">
            <img src={logoFull} alt="HelpHS" className="h-12 w-auto object-contain animate-logo-pulse" />
          </div>

          {/* Heading */}
          <div className="space-y-1 text-center lg:text-left">
            <h2 className="text-2xl font-bold text-slate-100">
              {desafio ? "Verificação em duas etapas" : "Bem-vindo de volta"}
            </h2>
            <p className="text-sm text-slate-500">
              {desafio
                ? "Digite o código de 6 dígitos do seu aplicativo autenticador"
                : "Entre com suas credenciais para continuar"}
            </p>
          </div>

          {/* Alerts */}
          {justRegistered && (
            <Alert variant="success">
              Conta criada com sucesso! Faça login para continuar.
            </Alert>
          )}
          {passwordReset && (
            <Alert variant="success">
              Senha alterada com sucesso. Entre com a nova senha.
            </Alert>
          )}
          {error && (
            <Alert variant="danger" onDismiss={() => { setError(null); setPrecisaConfirmar(false); }}>
              {error}
            </Alert>
          )}
          {precisaConfirmar && !reenviado && (
            <button
              onClick={handleReenviarConfirmacao}
              disabled={reenviando}
              className="w-full rounded-lg border border-primary/30 bg-primary/10 px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-primary/20 disabled:opacity-50 cursor-pointer"
            >
              {reenviando ? "Enviando…" : "Reenviar e-mail de confirmação"}
            </button>
          )}
          {reenviado && (
            <Alert variant="success">
              Se este e-mail estiver cadastrado e ainda não confirmado, o link chegará em instantes.
            </Alert>
          )}

          {/* Form — código do segundo fator */}
          {desafio ? (
            <form onSubmit={handleVerificar} className="space-y-5">
              <Input
                label="Código de verificação"
                type="text"
                inputMode="numeric"
                placeholder="000000"
                value={codigo}
                onChange={(e) => setCodigo(e.target.value)}
                // `one-time-code` faz o iOS e o Android oferecerem o código
                // direto do teclado, sem a pessoa alternar de aplicativo
                autoComplete="one-time-code"
                maxLength={7}
                autoFocus
                required
              />
              <Button
                type="submit"
                variant="primary"
                size="lg"
                loading={loading}
                className="w-full"
              >
                Verificar
              </Button>
              <button
                type="button"
                onClick={() => recomecar(null)}
                className="w-full text-center text-xs font-medium text-slate-500 transition-colors hover:text-slate-300 cursor-pointer"
              >
                Entrar com outra conta
              </button>
            </form>
          ) : (
          /* Form — credenciais */
          <form onSubmit={handleSubmit} className="space-y-5">
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
            <div className="space-y-1.5">
              <Input
                label="Senha"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
              <div className="flex justify-end">
                <Link
                  to="/esqueci-senha"
                  className="text-xs font-medium text-primary hover:text-primary/80 transition-colors"
                >
                  Esqueci minha senha
                </Link>
              </div>
            </div>

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
          )}

          {/* Footer links */}
          <div className="space-y-3 text-center">
            {!desafio && (
              <p className="text-sm text-slate-500">
                Não tem uma conta?{" "}
                <Link to="/register" className="text-primary hover:text-primary-400 transition-colors font-medium">
                  Registre-se
                </Link>
              </p>
            )}
            <p className="text-xs text-slate-600">
              {desafio
                ? "Perdeu o acesso ao aplicativo? Contate o administrador."
                : "Problemas para acessar? Contate o administrador."}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
