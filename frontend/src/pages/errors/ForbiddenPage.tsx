import { useNavigate } from "react-router-dom";
import { Button } from "../../components/ui";

export default function ForbiddenPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="text-center space-y-4">
        <p className="text-6xl font-bold text-danger">403</p>
        <h1 className="text-xl font-semibold text-slate-100">Acesso negado</h1>
        <p className="text-slate-400 max-w-xs">
          Você não tem permissão para acessar esta página.
        </p>
        <Button variant="secondary" onClick={() => navigate(-1)}>
          Voltar
        </Button>
      </div>
    </div>
  );
}
