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
      // fecha por Escape, pelos botoes da tela que o chamou e por
      // desmontagem da tela. (O clique no fundo ja NAO fecha — 15/09/2026.)
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
      {/* Segue a E24 do pacote (`design-system/EMENDAS.md`): o clique no
          fundo não fecha, e o X existe sempre. Este port mudou antes do pacote
          (`8fa38f9`, na `main` por `cc8f070`), e o pacote foi emendado depois, a
          pedido do operador. Não é a primeira vez que o HelpHS anda antes do
          pacote: na E12 foi este mesmo arquivo (`0bfaf01`), e na E11 foram os
          campos de formulário.
          Entre `8fa38f9` e a E24 isto foi um desvio declarado do `Modal.jsx`;
          desde a E24 não é mais.

          Fundo. Escurece e BLOQUEIA a tela de trás, mas não fecha mais.

          Tinha `onClick={onClose}`, e saiu a pedido do usuário (15/09/2026):
          um clique fora por engano descartava o que já estava digitado no
          formulário. Uma modal fecha pelo X, pelos botões dela e pelo Escape.

          O fundo continua existindo e cobrindo a tela inteira de propósito: é
          ele que impede o clique de chegar à página atrás. Tirar a div junto
          com o `onClick` trocaria "não fecha por engano" por "clica sem querer
          no que está atrás". */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

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
        {/* O cabeçalho — e o X dentro dele — é desenhado SEMPRE.

            Era `{title && ...}`: sem título, não havia X. Enquanto o fundo
            fechava, isso não prendia ninguém. Sem o fundo, prenderia quem só tem
            clique (o Escape seguiria valendo — e celular não tem Escape) — e não
            é hipótese: o detalhe da empresa usa `title={company.name}`, o nome
            vazio é alcançável, e carregando ou com erro de carga aquela modal
            não tem botão nenhum. Se só o X fecha por clique, toda modal precisa
            de um X, e a garantia mora aqui, não em cada tela que chama.

            Sem título, a barra perde a borda e o título, e fica só o X à
            direita — o conteúdo não ganha um traço solto em cima.

            E o X não pode ser EMPURRADO para fora. Item flex não encolhe abaixo
            da sua maior palavra: um título sem espaço (nome de empresa como
            "INDUSTRIAECOMERCIODEEQUIPAMENTOS…", que o backend aceita) estourava
            a linha e levava o X para além da borda do painel — no celular,
            para fora da tela. Enquanto o fundo fechava, sobrava saída. Agora o
            X é a única saída por clique, e celular não tem tecla Escape. Por
            isso o título tem `min-w-0 break-words` (pode encolher e quebra a
            palavra) e o botão tem `shrink-0` (nunca é espremido). Medido em
            navegador real, a 390px, com o controle negativo das classes
            antigas — ver o commit `8fa38f9`. Aquela medição usou fonte de
            fallback: o veredito (dentro / fora) vale para qualquer fonte; os
            pixels dela, não. */}
        <div
          className={cn(
            "flex items-center gap-3 shrink-0 px-4 py-3 sm:px-6 sm:py-4",
            title ? "justify-between border-b border-borda" : "justify-end",
          )}
        >
          {title && (
            <h2
              id={titleId}
              className="min-w-0 break-words text-base font-semibold text-conteudo-heading"
            >
              {title}
            </h2>
          )}
          <button
            // Hoje isto NAO muda comportamento: o modal vai para um portal em
            // `document.body`, entao o botao nunca e descendente do `<form>`
            // no DOM e nao teria como submeter. Fica porque a garantia e do
            // portal, nao do botao — se o portal sair um dia, o padrao do HTML
            // dentro de `<form>` volta a ser `submit`.
            type="button"
            onClick={onClose}
            className={cn(
              "shrink-0 rounded-lg p-1 text-conteudo-muted transition-colors",
              "hover:bg-surface-elevated hover:text-conteudo-heading",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action",
            )}
            aria-label="Fechar"
          >
            <Icon name="close" size={20} strokeWidth={2} />
          </button>
        </div>
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
