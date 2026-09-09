import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import type { ReactNode } from "react";
import { cn } from "../../lib/utils";
import { Icon } from "./Icon";

type ModalSize = "sm" | "md" | "lg" | "xl" | "2xl";

const sizeClasses: Record<ModalSize, string> = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-lg",
  xl: "max-w-2xl",
  "2xl": "max-w-3xl",
};

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  size?: ModalSize;
  children: ReactNode;
  className?: string;
}

export function Modal({
  open,
  onClose,
  title,
  size = "md",
  children,
  className,
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  // Quem tinha o foco quando o modal abriu. Sem guardar, fechar deixa o
  // foco no `body`: quem navega por teclado volta ao topo da pagina e
  // precisa percorrer tudo de novo ate onde estava.
  const focoAnterior = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  // Close on Escape + focus trap — only re-runs when `open` changes,
  // so typing inside modal inputs never re-triggers the focus logic.
  useEffect(() => {
    if (!open) return;

    focoAnterior.current = document.activeElement as HTMLElement | null;

    // Move focus into the modal only when it first opens
    const firstFocusable =
      panelRef.current?.querySelector<HTMLElement>(FOCUSABLE);
    firstFocusable?.focus();

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab") return;

      const focusable = Array.from(
        panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [],
      );
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      // A devolucao vai na limpeza, e nao num `onClose`: o modal tambem
      // fecha por Escape, por clique no fundo e por desmontagem da tela.
      focoAnterior.current?.focus();
    };
  }, [open]);

  // Prevent body scroll
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center p-3 sm:p-4"
      aria-modal="true"
      role="dialog"
      aria-labelledby={title ? titleId : undefined}
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div
        ref={panelRef}
        className={cn(
          "relative z-10 w-full flex flex-col rounded-xl border border-borda bg-surface shadow-xl",
          "animate-in fade-in zoom-in-95 duration-150",
          "max-h-[92vh]",
          sizeClasses[size],
          className,
        )}
      >
        {title && (
          <div className="flex items-center justify-between border-b border-borda px-4 py-3 sm:px-6 sm:py-4 shrink-0">
            <h2 id={titleId} className="text-base font-semibold text-conteudo-heading">
              {title}
            </h2>
            <button
              // Hoje isto NAO muda comportamento: o modal vai para um portal em
              // `document.body`, entao o botao nunca e descendente do `<form>`
              // no DOM e nao teria como submeter. Fica porque a garantia e do
              // portal, nao do botao — se o portal sair um dia, o padrao do HTML
              // dentro de `<form>` volta a ser `submit`.
              type="button"
              onClick={onClose}
              className={cn(
                "rounded-lg p-1 text-conteudo-muted transition-colors",
                "hover:bg-surface-elevated hover:text-conteudo-heading",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action",
              )}
              aria-label="Fechar"
            >
              <Icon name="close" size={20} strokeWidth={2} />
            </button>
          </div>
        )}
        <div className="px-4 pt-4 sm:px-6 overflow-y-auto flex-1 min-h-0">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

export interface ModalFooterProps {
  children: ReactNode;
  className?: string;
}

export function ModalFooter({ children, className }: ModalFooterProps) {
  return (
    <div
      className={cn(
        "flex items-center justify-end gap-3 border-t border-borda px-4 sm:px-6 py-4 -mx-4 sm:-mx-6 mt-4",
        className,
      )}
    >
      {children}
    </div>
  );
}
