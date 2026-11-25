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
    // A API responde o mesmo 200 para conta ativa, inativa, inexistente e para
    // o e-mail que não é o do cadastro — de propósito, para não revelar quem
    // tem conta. A tela, então, não sabe se algo foi enviado, e não pode dizer
    // que foi: o "Enviamos as instruções" que estava aqui fazia o pedido que
    // não gerou e-mail nenhum parecer falha de entrega (RS-03). Por isso o
    // aviso é `info` e condicional, sem repetir o endereço e sem prazo — o
    // prazo real do link é configuração do servidor e vai escrito no e-mail.
    return (
      <AuthShell
        title="Confira seu e-mail"
        footer={
          <Link to="/login" className="text-primary hover:text-primary/80 transition-colors">
            Voltar para o acesso
          </Link>
        }
      >
        <Alert variant="info">
          Se houver uma conta ativa associada ao e-mail informado, você receberá instruções para
          redefinir sua senha.
        </Alert>
        {/* Cor fixa, não `text-slate-*`: a AuthShell é escura nos dois temas e
            essas classes trocam de cor no tema claro (index.css). O
            `text-slate-500` dava 3,8:1 aqui; este passa de 4,5:1 nos dois. */}
        <p className="text-center text-xs text-[#94a3b8]">
          Não recebeu? Verifique a pasta de spam e confirme que informou o e-mail utilizado no
          cadastro. Se precisar, entre em contato com o suporte.
        </p>
        <p className="text-center text-xs">
          <button
            type="button"
            onClick={() => setEnviado(false)}
            className="inline-flex min-h-11 items-center rounded-lg px-3 text-primary hover:text-primary/80 transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            Tentar com outro e-mail
          </button>
        </p>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Esqueci minha senha"
      subtitle="Informe o e-mail associado à sua conta para solicitar a redefinição de senha."
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
          Solicitar redefinição
        </Button>
      </form>
    </AuthShell>
  );
}
