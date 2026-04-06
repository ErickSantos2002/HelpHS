import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Avatar } from "../ui";
import { cn } from "../../lib/utils";
import { useAuth } from "../../contexts/AuthContext";

const roleLabel: Record<string, string> = {
  admin: "Administrador",
  technician: "Técnico",
  client: "Cliente",
};

interface TopbarProps {
  onMenuClick: () => void;
}

export function Topbar({ onMenuClick }: TopbarProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-border bg-background-surface px-4 md:px-6">
      {/* Left: hamburger (mobile) */}
      <button
        className="rounded-lg p-2 text-slate-400 hover:bg-background-elevated hover:text-slate-100 transition-colors md:hidden"
        onClick={onMenuClick}
        aria-label="Abrir menu"
      >
        <svg
          className="w-5 h-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M4 6h16M4 12h16M4 18h16"
          />
        </svg>
      </button>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Right: notifications + user menu */}
      <div className="flex items-center gap-2">
        {/* Notification bell */}
        <button
          className="relative rounded-lg p-2 text-slate-400 hover:bg-background-elevated hover:text-slate-100 transition-colors"
          aria-label="Notificações"
          onClick={() => navigate("/notifications")}
        >
          <svg
            className="w-5 h-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
            />
          </svg>
          {/* Badge dot — will be dynamic with real notifications */}
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-danger" />
        </button>

        {/* User dropdown */}
        <div className="relative" ref={dropdownRef}>
          <button
            className={cn(
              "flex items-center gap-2.5 rounded-lg px-2 py-1.5 transition-colors",
              "hover:bg-background-elevated",
              dropdownOpen && "bg-background-elevated",
            )}
            onClick={() => setDropdownOpen((v) => !v)}
          >
            <Avatar name={user?.name ?? "?"} size="sm" />
            <div className="hidden md:block text-left">
              <p className="text-sm font-medium text-slate-100 leading-tight">
                {user?.name}
              </p>
              <p className="text-xs text-slate-500 leading-tight">
                {roleLabel[user?.role ?? "client"]}
              </p>
            </div>
            <svg
              className="w-4 h-4 text-slate-500 hidden md:block"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M19 9l-7 7-7-7"
              />
            </svg>
          </button>

          {/* Dropdown menu */}
          {dropdownOpen && (
            <div className="absolute right-0 top-full mt-1 w-48 rounded-xl border border-border bg-background-surface shadow-xl z-50 py-1">
              <div className="px-3 py-2 border-b border-border">
                <p className="text-sm font-medium text-slate-100 truncate">
                  {user?.name}
                </p>
                <p className="text-xs text-slate-500 truncate">{user?.email}</p>
              </div>
              <button
                className="flex w-full items-center gap-2 px-3 py-2 text-sm text-slate-300 hover:bg-background-elevated hover:text-slate-100 transition-colors"
                onClick={() => {
                  setDropdownOpen(false);
                  navigate("/profile");
                }}
              >
                <svg
                  className="w-4 h-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
                  />
                </svg>
                Meu perfil
              </button>
              <button
                className="flex w-full items-center gap-2 px-3 py-2 text-sm text-danger hover:bg-background-elevated transition-colors"
                onClick={handleLogout}
              >
                <svg
                  className="w-4 h-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
                  />
                </svg>
                Sair
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
