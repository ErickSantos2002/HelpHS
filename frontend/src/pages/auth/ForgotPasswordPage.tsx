import { useState } from "react";
import { Link } from "react-router-dom";
import { Alert, Button, Input } from "../../components/ui";
import { forgotPasswordApi } from "../../services/authService";
import { getApiError } from "../../lib/apiError";
import { AuthShell } from "./AuthShell";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [enviado, setEnviado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setLoading(true);
    setErro(null);
    try {
      await forgotPasswordApi(email.trim());
      setEnviado(true);
    } catch (err) {
      setErro(getApiError(err, "Não foi possível enviar o e-mail. Tente novamente."));
    } finally {
      setLoading(false);
    }
  }

  if (enviado) {
    return (
      <AuthShell
        title="Confira seu e-mail"
        subtitle="Se este e-mail estiver cadastrado, as instruções chegarão em instantes."
        footer={
          <Link to="/login" className="text-primary hover:text-primary/80 transition-colors">
            Voltar para o acesso
          </Link>
        }
      >
        <Alert variant="success">
          Enviamos as instruções para <span className="font-semibold">{email}</span>. O link vale
          por 1 hora e só pode ser usado uma vez.
        </Alert>
        <p className="text-center text-xs text-slate-500">
          Não recebeu? Confira a caixa de spam ou{" "}
          <button
            onClick={() => setEnviado(false)}
            className="text-primary hover:text-primary/80 transition-colors cursor-pointer"
          >
            tente com outro e-mail
          </button>
          .
        </p>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Esqueci minha senha"
      subtitle="Informe seu e-mail e enviaremos um link para criar uma nova senha."
      footer={
        <Link to="/login" className="text-primary hover:text-primary/80 transition-colors">
          Voltar para o acesso
        </Link>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {erro && (
          <Alert variant="danger" onDismiss={() => setErro(null)}>
            {erro}
          </Alert>
        )}

        <Input
          label="E-mail"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="seu@email.com"
          autoFocus
          required
        />

        <Button type="submit" variant="primary" size="lg" loading={loading} className="w-full">
          Enviar link de recuperação
        </Button>
      </form>
    </AuthShell>
  );
}
