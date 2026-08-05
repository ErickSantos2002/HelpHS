import { useEffect, useRef } from "react";
import { cn } from "../../lib/utils";
import type { QuickReply } from "../../services/quickReplyService";

interface QuickReplyPickerProps {
  replies: QuickReply[];
  activeIndex: number;
  onSelect: (reply: QuickReply) => void;
  onHover: (index: number) => void;
}

/**
 * Menu que aparece acima do campo de mensagem quando o técnico digita "/".
 * A navegação por teclado é controlada pelo ChatPanel, que é quem recebe as
 * teclas enquanto o foco continua no textarea.
 */
export function QuickReplyPicker({
  replies,
  activeIndex,
  onSelect,
  onHover,
}: QuickReplyPickerProps) {
  const listRef = useRef<HTMLDivElement>(null);

  // Mantém o item ativo visível ao navegar com as setas
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  if (replies.length === 0) return null;

  return (
    <div
      ref={listRef}
      role="listbox"
      aria-label="Respostas rápidas"
      className="absolute bottom-full left-0 right-0 z-30 mb-2 max-h-64 overflow-y-auto rounded-xl border border-border bg-background-surface shadow-xl"
    >
      <p className="sticky top-0 bg-background-surface px-3 py-2 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
        Respostas rápidas
      </p>

      {replies.map((reply, index) => (
        <button
          key={reply.id}
          type="button"
          role="option"
          aria-selected={index === activeIndex}
          data-index={index}
          onMouseEnter={() => onHover(index)}
          onClick={() => onSelect(reply)}
          className={cn(
            "block w-full px-3 py-2 text-left transition-colors cursor-pointer",
            index === activeIndex
              ? "bg-primary/10"
              : "hover:bg-background-elevated",
          )}
        >
          <span className="flex items-baseline gap-2">
            <span className="text-sm font-semibold text-slate-100">/{reply.shortcut}</span>
            <span className="truncate text-xs text-slate-500">{reply.title}</span>
          </span>
          <span className="mt-0.5 block truncate text-xs text-slate-400">{reply.content}</span>
        </button>
      ))}

      <p className="sticky bottom-0 border-t border-border/50 bg-background-surface px-3 py-1.5 text-[10px] text-slate-600">
        ↑ ↓ para navegar · Enter para inserir · Esc para fechar
      </p>
    </div>
  );
}
