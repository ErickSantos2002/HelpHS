import { useNavigate } from "react-router-dom";
import { Button } from "../../components/ui";

export default function NotFoundPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="text-center space-y-4">
        <p className="text-6xl font-bold text-slate-600">404</p>
        <h1 className="text-xl font-semibold text-slate-100">
          Página não encontrada
        </h1>
        <p className="text-slate-400 max-w-xs">
          O endereço que você acessou não existe ou foi removido.
        </p>
        <Button variant="secondary" onClick={() => navigate("/")}>
          Ir para o início
        </Button>
      </div>
    </div>
  );
}
