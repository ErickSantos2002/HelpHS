import { useAuth } from "../contexts/AuthContext";

export default function HomePage() {
  const { user } = useAuth();

  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-bold text-slate-100">
        Olá, {user?.name?.split(" ")[0]} 👋
      </h1>
      <p className="text-slate-400">
        Bem-vindo ao HelpHS. Seu dashboard está sendo preparado.
      </p>
    </div>
  );
}
