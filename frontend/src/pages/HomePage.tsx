import { lazy, Suspense, useState } from "react";
import {
  Spinner,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "../components/ui";
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

function AdminHome() {
  const [tab, setTab] = useState("admin");

  return (
    <Tabs value={tab} onChange={setTab} className="space-y-4">
      <TabsList>
        <TabsTrigger value="admin">Dashboard Admin</TabsTrigger>
        <TabsTrigger value="technician">Dashboard Técnico</TabsTrigger>
      </TabsList>

      <Suspense fallback={<Loading />}>
        <TabsContent value="admin">
          <AdminDashboard />
        </TabsContent>
        <TabsContent value="technician">
          <TechnicianDashboard />
        </TabsContent>
      </Suspense>
    </Tabs>
  );
}

export default function HomePage() {
  const { user } = useAuth();

  return (
    <Suspense fallback={<Loading />}>
      {user?.role === "admin" && <AdminHome />}
      {user?.role === "technician" && <TechnicianDashboard />}
      {user?.role === "client" && <ClientDashboard />}
    </Suspense>
  );
}
