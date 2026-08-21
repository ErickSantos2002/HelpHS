import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";

/**
 * O par do OnboardingGuard: só deixa em /onboarding quem ainda tem onboarding
 * a fazer — cliente com `onboarding_completed` falso.
 *
 * Um guard empurra para a tela quem deve preenchê-la; este tira de lá todo o
 * resto. Sem ele, /onboarding ficava sob o AuthGuard e fora do
 * OnboardingGuard, então qualquer autenticado abria a tela digitando a URL:
 * staff, que não tem onboarding nenhum, e o cliente que já completou, para
 * quem refazer significaria sobrescrever dados de cadastro já revisados.
 *
 * Sem usuário ninguém passa (fail closed). Na prática o AuthGuard já barrou
 * antes; a regra vale para o dia em que a ordem dos guards mudar.
 */
export function OnboardingOnlyRoute() {
  const { user } = useAuth();

  if (user?.role === "client" && !user.onboarding_completed) {
    return <Outlet />;
  }

  return <Navigate to="/" replace />;
}
