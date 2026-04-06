import { lazy, Suspense } from "react";
import { Spinner } from "../components/ui";
import { useAuth } from "../contexts/AuthContext";

const AdminDashboard = lazy(() => import("./dashboard/AdminDashboard"));
const TechnicianDashboard = lazy(
  () => import("./dashboard/TechnicianDashboard"),
);

function Loading() {
  return (
    <div className="flex h-48 items-center justify-center">
      <Spinner size="lg" />
    </div>
  );
}

export default function HomePage() {
  const { user } = useAuth();

  return (
    <Suspense fallback={<Loading />}>
      {user?.role === "admin" && <AdminDashboard />}
      {user?.role === "technician" && <TechnicianDashboard />}
      {user?.role === "client" && (
        <div className="space-y-2">
          <h1 className="text-2xl font-bold text-slate-100">Meus Tickets</h1>
          <p className="text-slate-400">
            Dashboard do cliente — disponível no T34.
          </p>
        </div>
      )}
    </Suspense>
  );
}
