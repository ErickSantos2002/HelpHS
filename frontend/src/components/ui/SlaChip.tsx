import { useEffect, useState } from "react";
import { cn } from "../../lib/utils";

export interface SlaChipProps {
  label: string;
  /** Prazo. Sem ele o chip não existe. */
  dueAt: string | null;
  /** Flag de violação que o backend gravou — decide a COR. */
  breached: boolean;
  /**
   * Quando a resposta foi dada. Preenchido, o relógio para: o chip diz
   * "Respondido" e não conta mais nada, porque o prazo de resposta já foi
   * atendido (ou perdido — aí `breached` segue pintando de vermelho).
   */
  respondedAt?: string | null;
}

const Clock = (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

function restante(dueAt: string): string {
  const diff = new Date(dueAt).getTime() - Date.now();
  if (diff <= 0) return "Vencido";
  const h = Math.floor(diff / 3_600_000);
  const m = Math.floor((diff % 3_600_000) / 60_000);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

/**
 * Chip de prazo de SLA.
 *
 * Três dados, três responsabilidades: `dueAt` dá a contagem, `breached` dá a
 * cor, `respondedAt` desliga o relógio. Misturar os dois últimos é a
 * tentação a evitar — "se não violou, não escreva Vencido" — porque
 * `breached` só é recalculado em caminhos de ESCRITA do backend, nunca na
 * leitura. Um chamado que venceu há duas horas e ninguém tocou chega com
 * `breached = false`, e é exatamente para ele que a contagem ao vivo existe.
 * Quem pode calar o "Vencido" é só a resposta já ter sido dada.
 *
 * O caso que motivou `respondedAt`: chamado respondido no prazo e reaberto
 * dias depois. O prazo de resposta é o do primeiro ciclo, muito no passado,
 * e sem saber da resposta o chip dizia "Vencido" em âmbar — cor certa, letra
 * errada. Dar ao ciclo novo um prazo próprio é outra conversa (campo por
 * ciclo); este chip só diz a verdade sobre o que o backend manda hoje.
 */
export function SlaChip({ label, dueAt, breached, respondedAt }: SlaChipProps) {
  const respondido = Boolean(respondedAt);
  const [display, setDisplay] = useState(() => (dueAt && !respondido ? restante(dueAt) : ""));

  useEffect(() => {
    if (!dueAt || respondido) return;
    const update = () => setDisplay(restante(dueAt));
    update();
    const t = setInterval(update, 60_000);
    return () => clearInterval(t);
  }, [dueAt, respondido]);

  if (!dueAt) return null;

  const tom = breached
    ? "bg-red-500/15 text-red-700 dark:text-red-400 ring-red-500/25"
    : respondido
      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 ring-emerald-500/25"
      : "bg-amber-500/15 text-amber-700 dark:text-amber-400 ring-amber-500/25";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-semibold ring-1 ring-inset",
        tom,
      )}
    >
      {Clock}
      {label ? `${label}: ` : ""}
      <span>{respondido ? "Respondido" : display}</span>
    </span>
  );
}
