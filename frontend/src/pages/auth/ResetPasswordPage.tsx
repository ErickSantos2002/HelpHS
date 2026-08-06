import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Alert, Button, Input } from "../../components/ui";
import { resetPasswordApi } from "../../services/authService";
import { getApiError } from "../../lib/apiError";
import { AuthShell } from "./AuthShell";

function validar(senha: string, confirmacao: string): string | null {
  if (senha.length < 8) return "A senha deve ter no mínimo 8 caracteres.";
  if (!/[A-Z]/.test(senha)) return "A senha deve conter ao menos uma letra maiúscula.";
  if (!/\d/.test(senha)) return "A senha deve conter ao menos um número.";
  if (senha !== confirmacao) return "As senhas não coincidem.";
  return null;
}

export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") ?? "";

  const [senha, setSenha] = useState("");
  const [confirmacao, setConfirmacao] = useState("");
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const problema = validar(senha, confirmacao);
    if (problema) {
      setErro(problema);
      return;
    }

    setLoading(true);
    setErro(null);
    try {
      await resetPasswordApi(token, senha);
      navigate("/login", { state: { passwordReset: true }, replace: true });
    } catch (err) {
      setErro(getApiError(err, "Não foi possível alterar a senha. Tente novamente."));
    } finally {
      setLoading(false);
    }
  }

  if (!token) {
    return (
      <AuthShell
        title="Link inválido"
        footer={
          <Link to="/esqueci-senha" className="text-primary hover:text-primary/80 transition-colors">
            Pedir um novo link
          </Link>
        }
      >
        <Alert variant="danger">
          Este endereço não traz um link de redefinição válido. Peça um novo pela tela de acesso.
        </Alert>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Criar nova senha"
      subtitle="Escolha uma senha que você não use em outros sites."
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
          label="Nova senha"
          type="password"
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
          placeholder="Mín. 8 caracteres, 1 maiúscula, 1 número"
          autoFocus
          required
        />

        <Input
          label="Confirmar nova senha"
          type="password"
          value={confirmacao}
          onChange={(e) => setConfirmacao(e.target.value)}
          placeholder="Repita a senha"
          required
        />

        <Button type="submit" variant="primary" size="lg" loading={loading} className="w-full">
          Salvar nova senha
        </Button>
      </form>
    </AuthShell>
  );
}
