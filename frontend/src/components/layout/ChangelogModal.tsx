import type { ReactNode } from "react";
import { cn } from "../../lib/utils";
import { Modal } from "../ui";
import { APP_VERSION, CHANGELOG, type EntryType } from "../../data/changelog";

const ENTRY_CONFIG: Record<EntryType, { label: string; className: string; icon: ReactNode }> = {
  novidade: {
    label: "Novidade",
    className: "bg-blue-500/15 text-blue-400 border border-blue-500/25",
    icon: (
      <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
      </svg>
    ),
  },
  corrigido: {
    label: "Corrigido",
    className: "bg-orange-500/15 text-orange-400 border border-orange-500/25",
    icon: (
      <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
      </svg>
    ),
  },
  melhoria: {
    label: "Melhoria",
    className: "bg-emerald-500/15 text-emerald-400 border border-emerald-500/25",
    icon: (
      <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
      </svg>
    ),
  },
};

interface ChangelogModalProps {
  open: boolean;
  onClose: () => void;
}

export function ChangelogModal({ open, onClose }: ChangelogModalProps) {
  return (
    <Modal open={open} onClose={onClose} title="O que há de novo?" size="2xl">
      <p className="-mt-1 mb-5 text-sm text-slate-500">Atualizações recentes do HelpHS</p>

      <div className="space-y-6">
        {CHANGELOG.map((v, idx) => {
          const isCurrent = v.version === APP_VERSION;
          return (
            <div key={v.version}>
              <div className="flex items-center gap-2 mb-3">
                <span className={cn(
                  "rounded-full px-2.5 py-0.5 text-xs font-bold",
                  isCurrent ? "bg-emerald-500 text-white" : "bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
                )}>
                  {v.version}
                </span>
                <span className="text-xs text-slate-500">{v.date}</span>
                {isCurrent && (
                  <span className="rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/25 px-2 py-0.5 text-[10px] font-semibold">
                    Versão atual
                  </span>
                )}
              </div>

              <div className="space-y-2">
                {v.entries.map((entry, i) => {
                  const cfg = ENTRY_CONFIG[entry.type];
                  return (
                    <div key={i} className="flex items-start gap-3 rounded-xl border border-border bg-background-elevated px-3.5 py-2.5">
                      <span className={cn(
                        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold shrink-0 mt-0.5",
                        cfg.className,
                      )}>
                        {cfg.icon}
                        {cfg.label}
                      </span>
                      <p className="text-sm text-slate-300 leading-relaxed">{entry.text}</p>
                    </div>
                  );
                })}
              </div>

              {idx < CHANGELOG.length - 1 && (
                <div className="mt-6 border-b border-border" />
              )}
            </div>
          );
        })}
      </div>

      <p className="mt-6 text-center text-xs text-slate-600">
        HelpHS — desenvolvido internamente pela equipe
      </p>
    </Modal>
  );
}
