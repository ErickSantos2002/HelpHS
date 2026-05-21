import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Toaster } from "sonner";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppLayout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarMobileOpen, setSidebarMobileOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50 dark:bg-background">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-white"
      >
        Pular para o conteúdo principal
      </a>

      <Sidebar
        collapsed={sidebarCollapsed}
        mobileOpen={sidebarMobileOpen}
        onMobileClose={() => setSidebarMobileOpen(false)}
      />

      <div className="flex flex-1 flex-col overflow-hidden min-w-0">
        <Topbar
          onMobileMenuClick={() => setSidebarMobileOpen(true)}
          onToggleCollapsed={() => setSidebarCollapsed((v) => !v)}
          sidebarCollapsed={sidebarCollapsed}
        />
        <main id="main-content" className="flex-1 overflow-y-auto p-4 md:p-6">
          <Outlet />
        </main>
      </div>

      <Toaster
        theme="dark"
        position="top-right"
        richColors
        closeButton
        toastOptions={{ duration: 4000 }}
      />
    </div>
  );
}
