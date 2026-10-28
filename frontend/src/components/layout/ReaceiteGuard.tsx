import { useEffect, useRef, useState } from "react";
import { Link, Outlet, useNavigate } from "react-router-dom";
import { Alert, Button, Spinner } from "../ui";
import { useAuth } from "../../contexts/AuthContext";
import { aoAceitePoliticaPendente } from "../../services/aceitePolitica";
import { getLgpdConsentStatus, updateLGPDConsent } from "../../services/userService";
import type { LgpdConsentStatus } from "../../services/userService";
import logoFull from "../../assets/Logo HelpHS.png";

/**
 * Cobra o aceite da revisão vigente da Política de Privacidade.
 *
 * Quem decide se a pessoa precisa aceitar é o backend
 * (`GET /users/me/lgpd-consent`), que só cobra com `LGPD_EXIGE_REACEITE`
 * ligado — este guard só obedece. Duas regras diferentes:
 *
 * - Política (`politica_pendente`): cliente, técnico e admin. É a Decisão 2,
 *   de 27/10/2026, e o backend também BLOQUEIA (428 nas rotas, 4428 no chat).
 * - Termos (`termos_pendentes`): só clientes, só esta tela, sem bloqueio no
 *   backend — a regra de 24/09/2026, preservada.
 *
 * A tela aparece ao abrir o sistema e também a qualquer momento em que um
 * pedido receba o 428 do aceite (ou o chat feche com 4428): o aviso chega por
 * `aoAceitePoliticaPendente`, e o guard consulta de novo. Dá para recusar, e
 * recusar é sair.
 *
 * Falhou a consulta, LIBERA, como antes da Decisão 2. Quem obriga o aceite da
 * Política é o backend: com ela pendente, o primeiro pedido protegido volta
 * com 428 e o aviso traz esta tela de volta. Bloquear aqui só criaria
 * indisponibilidade nova com `LGPD_EXIGE_REACEITE` desligado. A exceção é a
 * consulta disparada por esse aviso: o 428 já disse que a Política está
 * pendente, então, se ela falhar, a tela de aceite aparece mesmo assim — sem
 * isso o sistema voltaria, o 428 voltaria, e assim sem fim.
 *
 * Vem ANTES do onboarding (`App.tsx`): o onboarding chama rotas que o backend
 * bloqueia sem o aceite.
 */
export function ReaceiteGuard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const ehCliente = user?.role === "client";

  const [situacao, setSituacao] = useState<"verificando" | "liberado" | "cobrar">(
    "verificando",
  );
  const [revisao, setRevisao] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState(false);
  // Cada aviso de 428/4428 é uma consulta nova.
  const [consulta, setConsulta] = useState(0);
  // O backend avisou que a Política está pendente e nenhuma consulta o
  // desmentiu ainda: se a próxima falhar, cobra em vez de liberar.
  const pendentePeloAviso = useRef(false);

  useEffect(
    () =>
      aoAceitePoliticaPendente(() => {
        pendentePeloAviso.current = true;
        setConsulta((n) => n + 1);
      }),
    [],
  );

  // Pelo id e não pelo objeto: o AuthContext troca o objeto do usuário quando
  // o perfil muda, e reconsultar a cada troca desmontaria o sistema inteiro.
  const userId = user?.id;
  useEffect(() => {
    if (!userId) return;
    let vivo = true;
    setSituacao("verificando");
    getLgpdConsentStatus()
      .then((s) => {
        if (!vivo) return;
        pendentePeloAviso.current = false;
        setRevisao(s.revisao_politica_vigente);
        setSituacao(precisaDaTela(s, ehCliente) ? "cobrar" : "liberado");
      })
      .catch(() => {
        if (vivo) setSituacao(pendentePeloAviso.current ? "cobrar" : "liberado");
      });
    return () => {
      vivo = false;
    };
  }, [ehCliente, userId, consulta]);

  async function aceitar() {
    setEnviando(true);
    setErro(false);
    try {
      await updateLGPDConsent(true);
      pendentePeloAviso.current = false;
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

/**
 * Se a tela de aceite aparece. Sem `politica_pendente` na resposta, o backend
 * é anterior a esta mudança: vale a regra antiga (só clientes, pelo
 * `precisa_reaceitar`), que é o que esse backend sabe dizer.
 */
function precisaDaTela(s: LgpdConsentStatus, ehCliente: boolean): boolean {
  if (s.politica_pendente === undefined) return ehCliente && s.precisa_reaceitar;
  return s.politica_pendente || (ehCliente && s.termos_pendentes === true);
}
