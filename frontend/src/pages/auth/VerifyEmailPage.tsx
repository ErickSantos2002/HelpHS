import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Alert, Button, Input, Spinner } from "../../components/ui";
import { resendVerificationApi, verifyEmailApi } from "../../services/authService";
import { getApiError } from "../../lib/apiError";
import { AuthShell } from "./AuthShell";

type Situacao = "verificando" | "confirmado" | "falhou";

export default function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";

  const [situacao, setSituacao] = useState<Situacao>(token ? "verificando" : "falhou");
  const [mensagem, setMensagem] = useState("");
  const [email, setEmail] = useState("");
  const [reenviando, setReenviando] = useState(false);
  const [reenviado, setReenviado] = useState(false);
  // O React roda o efeito duas vezes em desenvolvimento; sem isto, o link
  // seria consumido em duplicidade
  const jaTentou = useRef(false);

  useEffect(() => {
    if (!token || jaTentou.current) return;
    jaTentou.current = true;

    verifyEmailApi(token)
      .then((msg) => {
        setMensagem(msg);
        setSituacao("confirmado");
      })
      .catch((err) => {
        setMensagem(getApiError(err, "Não foi possível confirmar o e-mail."));
        setSituacao("falhou");
      });
  }, [token]);

  async function handleReenviar(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setReenviando(true);
    try {
      await resendVerificationApi(email.trim());
      setReenviado(true);
    } finally {
      setReenviando(false);
    }
  }

  if (situacao === "verificando") {
    return (
      <AuthShell title="Confirmando seu e-mail" subtitle="Só um instante…">
        <div className="flex justify-center py-6">
          <Spinner size="lg" />
        </div>
      </AuthShell>
    );
  }

  if (situacao === "confirmado") {
    return (
      <AuthShell title="Tudo certo!" subtitle="Sua conta está ativa.">
        <Alert variant="success">{mensagem}</Alert>
        <Link to="/login">
          <Button variant="primary" size="lg" className="w-full">
            Entrar agora
          </Button>
        </Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Não foi possível confirmar"
      footer={
        <Link to="/login" className="text-primary hover:text-primary/80 transition-colors">
          Voltar para o acesso
        </Link>
      }
    >
      <Alert variant="danger">
        {mensagem || "Este endereço não traz um link de confirmação válido."}
      </Alert>

      {reenviado ? (
        <Alert variant="success">
          Se este e-mail estiver cadastrado e ainda não confirmado, o link chegará em instantes.
        </Alert>
      ) : (
        <form onSubmit={handleReenviar} className="space-y-3">
          <p className="text-sm text-slate-400">
            O link vale por tempo limitado. Informe seu e-mail para receber um novo:
          </p>
          <Input
            label="E-mail do cadastro"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="seu@email.com"
            required
          />
          <Button type="submit" variant="primary" loading={reenviando} className="w-full">
            Reenviar confirmação
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
