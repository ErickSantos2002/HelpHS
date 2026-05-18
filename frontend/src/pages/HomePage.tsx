import { lazy, Suspense } from "react";
import { Spinner } from "../components/ui";
import { useAuth } from "../contexts/AuthContext";

const AdminDashboard = lazy(() => import("./dashboard/AdminDashboard"));
const TechnicianDashboard = lazy(
  () => import("./dashboard/TechnicianDashboard"),
);
const ClientDashboard = lazy(() => import("./dashboard/ClientDashboard"));

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
      {user?.role === "client" && <ClientDashboard />}
    </Suspense>
  );
}
