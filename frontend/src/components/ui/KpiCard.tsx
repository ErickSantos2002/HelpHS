import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

/**
 * Cartão de indicador dos painéis.
 *
 * ── Por que ele existe ────────────────────────────────────────────────
 *
 * Existia em **três cópias divergentes**, uma por painel, e as três tinham a
 * mesma causa-raiz: uma prop de **classe crua**. O `ClientDashboard` chamava-a
 * `color`, os outros dois `valueCls`, e os dois últimos ainda traziam `accent` e
 * `iconBg` — três strings livres por cartão.
 *
 * Uma prop de classe aberta não é atalho: é a porta pela qual a cor entra sem
 * revisão. Por ela chegaram `text-sky-600`, `text-violet-600`,
 * `text-indigo-600`, `bg-amber-500/10` — paleta crua do Tailwind, fora do
 * sistema de tokens, com contraste nunca medido. E foi ela que deixou as três
 * cópias divergirem sem que nada reclamasse.
 *
 * Aqui o tom é uma **união fechada**. Não há como passar uma classe.
 *
 * ── O que cada tom pinta ──────────────────────────────────────────────
 *
 * O filete à esquerda, o fundo do ícone e o número. Os três saem dos pares
 * `tint`/`on-tint`, que a **E2** e a **E8** mediram contra as três superfícies
 * nos dois temas.
 *
 * O número colorido foi **medido antes de ficar**: `--on-tint-*` sobre
 * superfície nua dá entre 5,29:1 e 9,58:1 — o par foi medido sobre a tinta, e
 * sobre a superfície ele passa com folga. É o que permite manter o sinal que os
 * painéis já davam (número vermelho quando há violação) sem cor fora do sistema.
 *
 * `neutral` deixa o número em `--text-heading`, que é onde ele já estava.
 *
 * ── Três tons que sumiram, e o que se perdeu ──────────────────────────
 *
 * `sky`, `violet` e `indigo` não têm token e não viraram um. Colapsaram em
 * `info` e `primary`. **O que se perde é variedade decorativa, não informação**:
 * o que o cartão mede está escrito no rótulo, e nunca dependeu da matiz.
 */

export type KpiTone =
  | "neutral"
  | "primary"
  | "info"
  | "success"
  | "warning"
  | "danger";

const filete: Record<KpiTone, string> = {
  neutral: "border-l-borda-strong",
  primary: "border-l-primary",
  info: "border-l-info",
  success: "border-l-success",
  warning: "border-l-warning",
  danger: "border-l-danger",
};

const fundoIcone: Record<KpiTone, string> = {
  neutral: "bg-surface-elevated text-conteudo-muted",
  primary: "bg-tint-primary text-on-tint-primary",
  info: "bg-tint-info text-on-tint-info",
  success: "bg-tint-success text-on-tint-success",
  warning: "bg-tint-warning text-on-tint-warning",
  danger: "bg-tint-danger text-on-tint-danger",
};

const numero: Record<KpiTone, string> = {
  neutral: "text-conteudo-heading",
  primary: "text-on-tint-primary",
  info: "text-on-tint-info",
  success: "text-on-tint-success",
  warning: "text-on-tint-warning",
  danger: "text-on-tint-danger",
};

export interface KpiCardProps {
  label: string;
  value: number | string;
  /** Segunda linha, menor: o que o número está contando. */
  sub?: string;
  /** Ícone de 20px. O tom já pinta o fundo e a cor dele. */
  icon?: ReactNode;
  tone?: KpiTone;
  className?: string;
}

export function KpiCard({
  label,
  value,
  sub,
  icon,
  tone = "neutral",
  className,
}: KpiCardProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl border border-l-4 border-borda bg-surface p-5",
        filete[tone],
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wider text-conteudo-muted">
            {label}
          </p>
          <p className={cn("mt-2 text-3xl font-bold tabular-nums", numero[tone])}>
            {value}
          </p>
          {sub && <p className="mt-1.5 text-xs text-conteudo-muted">{sub}</p>}
        </div>
        {icon && (
          <span
            aria-hidden="true"
            className={cn(
              "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl",
              fundoIcone[tone],
            )}
          >
            {icon}
          </span>
        )}
      </div>
    </div>
  );
}
