import { useEffect, useState } from "react";
import { Link, Outlet, useNavigate } from "react-router-dom";
import { Alert, Button, Spinner } from "../ui";
import { useAuth } from "../../contexts/AuthContext";
import { getLgpdConsentStatus, updateLGPDConsent } from "../../services/userService";
import logoFull from "../../assets/Logo HelpHS.png";

/**
 * Cobra do cliente o aceite da revisão vigente da Política de Privacidade.
 *
 * A seção 15 da política promete pedir novo aceite "no primeiro acesso
 * posterior" a uma revisão relevante. Quem decide se a pessoa precisa aceitar
 * é o backend (`precisa_reaceitar`), que só cobra com `LGPD_EXIGE_REACEITE`
 * ligado — este guard só obedece.
 *
 * Decisões de 24/09/2026: só clientes (a equipe passa direto, sem nem
 * consultar); dá para recusar, e recusar é sair; a consulta acontece quando o
 * sistema abre, então ninguém é interrompido no meio de um chamado.
 *
 * Falhou a consulta, deixa passar. O front pode subir antes do backend que tem
 * a rota, e travar todo cliente por um 404 seria pior que o risco — o
 * interruptor mora no backend, e ele continua desligado até alguém ligá-lo.
 */
export function ReaceiteGuard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const ehCliente = user?.role === "client";

  const [situacao, setSituacao] = useState<"verificando" | "liberado" | "cobrar">(
    ehCliente ? "verificando" : "liberado",
  );
  const [revisao, setRevisao] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    if (!ehCliente) return;
    let vivo = true;
    getLgpdConsentStatus()
      .then((s) => {
        if (!vivo) return;
        setRevisao(s.revisao_politica_vigente);
        setSituacao(s.precisa_reaceitar ? "cobrar" : "liberado");
      })
      .catch(() => {
        if (vivo) setSituacao("liberado");
      });
    return () => {
      vivo = false;
    };
  }, [ehCliente, user?.id]);

  async function aceitar() {
    setEnviando(true);
    setErro(false);
    try {
      await updateLGPDConsent(true);
      setSituacao("liberado");
    } catch {
      setErro(true);
    } finally {
      setEnviando(false);
    }
  }

  async function recusar() {
    setEnviando(true);
    try {
      await logout();
    } finally {
      navigate("/login", { replace: true });
    }
  }

  if (situacao === "verificando") {
    return (
      <div className="flex h-screen items-center justify-center bg-surface-base">
        <Spinner size="lg" />
      </div>
    );
  }

  if (situacao === "liberado") return <Outlet />;

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-base px-4 py-10">
      <div className="w-full max-w-lg space-y-6 rounded-xl border border-borda bg-surface p-6 sm:p-8">
        <img src={logoFull} alt="HelpHS" className="h-7 w-auto object-contain" />

        <div className="space-y-3">
          <h1 className="text-xl font-semibold text-conteudo-heading">
            Atualizamos nossa Política de Privacidade
          </h1>
          <p className="text-sm leading-relaxed text-conteudo-muted">
            Para continuar usando o HelpHS, leia e aceite a{" "}
            {revisao ? `revisão ${revisao} da ` : ""}
            <Link
              to="/privacidade"
              target="_blank"
              rel="noopener noreferrer"
              className="text-conteudo-link hover:underline"
            >
              Política de Privacidade
            </Link>
            . Ela descreve quais dados tratamos, com quem os compartilhamos e
            como exercer os seus direitos.
          </p>
          <p className="text-sm leading-relaxed text-conteudo-muted">
            Se você recusar, sairá do sistema. Poderá aceitar no próximo acesso
            ou falar com o nosso Encarregado de dados pelos canais indicados na
            política.
          </p>
        </div>

        {erro && (
          <Alert variant="danger">
            Não foi possível registrar o seu aceite. Tente novamente.
          </Alert>
        )}

        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={recusar} disabled={enviando}>
            Recusar e sair
          </Button>
          <Button variant="primary" onClick={aceitar} loading={enviando}>
            Aceitar e continuar
          </Button>
        </div>
      </div>
    </div>
  );
}
