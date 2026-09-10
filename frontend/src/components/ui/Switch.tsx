import type { InputHTMLAttributes, ReactNode } from "react";
import { useId } from "react";
import { cn } from "../../lib/utils";

/**
 * Interruptor de duas posições, de `DS/components/forms/Switch.jsx`.
 *
 * **Efeito imediato, sem botão de salvar** — é o que separa um `Switch` de uma
 * caixa de seleção. Por isso ele só existe aqui porque existe um controle assim
 * hoje: o alternador de tema no menu do usuário.
 *
 * ── O que a extração conserta, além de token ───────────────────────────
 *
 * O alternador era um `<button>` com um trilho desenhado dentro. Três coisas
 * saíam erradas, e só uma era de cor:
 *
 * 1. **Não tinha estado.** `role="switch"` e `aria-checked` não existiam em
 *    lugar nenhum do `src/` — quem usa leitor de tela ouvia "Modo escuro,
 *    botão", sem saber se estava ligado. Aqui o estado vem de graça: é um
 *    `<input type="checkbox" role="switch">` de verdade, com teclado e anúncio.
 * 2. **O desligado era invisível.** Trilho em `slate-300` sobre painel branco:
 *    **1,48:1**, contra o piso de **3:1** que a WCAG 1.4.11 pede para
 *    componente de interface. No escuro, `slate-600` sobre o painel: 2,11:1.
 * 3. **Cor cravada**, no caminho legado do desvio D5.
 *
 * ── Dois desvios do pacote, os dois medidos ────────────────────────────
 *
 * O `Switch.jsx` de referência também reprova, e vale registrar por quê:
 *
 * - **A bolinha.** O pacote a pinta com `--color-white` cravado. Sobre o
 *   `--action` do tema escuro isso dá **2,69:1** — o mesmo número que a emenda
 *   **E1** corrigiu no botão primário, e que o link de pular carregava até
 *   ontem. Aqui ela usa `--text-on-primary`, o token que a E1 criou: 5,29:1 no
 *   claro e 5,11:1 no escuro.
 * - **O limite do desligado.** O pacote o delimitava com `--border-color`, que
 *   dá 1,23:1 — e nenhum dos três tokens de borda alcançava 3:1 contra
 *   `--surface`. Isso virou a emenda **E7**: nasceu o `--border-control`
 *   (slate-500 no claro, slate-400 no escuro), que mede **4,76 · 4,55 · 4,34**
 *   e **6,23 · 6,78 · 5,29** contra as três superfícies. O trilho desligado usa
 *   ele, e o pacote também — o desvio durou um commit.
 *
 * A E7 levou a bolinha do `Switch.jsx` do pacote a `--text-on-primary` junto,
 * então este arquivo e a referência voltaram a dizer a mesma coisa.
 */
export interface SwitchProps
  extends Omit<
    InputHTMLAttributes<HTMLInputElement>,
    "onChange" | "type" | "size" | "checked"
  > {
  checked: boolean;
  /** Recebe o valor novo, não o evento — como o `.d.ts` do pacote define. */
  onChange: (checked: boolean) => void;
  /**
   * Conteúdo à direita do interruptor, e o nome acessível do controle.
   *
   * O `.d.ts` do pacote declara `string`; aqui é `ReactNode`, que é
   * superconjunto e não quebra nenhum uso. O motivo é concreto: o alternador de
   * tema tem um ícone junto do rótulo, e passá-lo pelo `label` mantém a **linha
   * inteira clicável** — que é como ela funcionava quando era um `<button>`.
   * Com o ícone fora, clicar nele deixaria de alternar.
   */
  label?: ReactNode;
  disabled?: boolean;
  size?: "sm" | "md";
}

/** Trilho e bolinha, nos dois tamanhos do pacote (44×24 e 48×28). */
const MEDIDAS = {
  sm: { trilho: "w-11 h-6", bolinha: "w-4 h-4", desloca: "translate-x-5" },
  md: { trilho: "w-12 h-7", bolinha: "w-5 h-5", desloca: "translate-x-5" },
} as const;

export function Switch({
  checked,
  onChange,
  label,
  disabled = false,
  size = "md",
  className,
  id,
  ...props
}: SwitchProps) {
  const gerado = useId();
  const inputId = id ?? gerado;
  const m = MEDIDAS[size];

  return (
    <label
      htmlFor={inputId}
      className={cn(
        "inline-flex items-center gap-3 text-sm text-conteudo",
        disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer",
        className,
      )}
    >
      <span className={cn("relative shrink-0", m.trilho)}>
        <input
          id={inputId}
          type="checkbox"
          role="switch"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
          className="peer absolute h-px w-px opacity-0"
          {...props}
        />

        {/* O trilho. Ligado: preenchido com --action, que já se distingue do
            painel. Desligado: superfície elevada com contorno em --text-muted,
            porque é o contorno que dá o limite perceptível — o preenchimento
            sozinho fica em 1,10:1. */}
        <span
          aria-hidden="true"
          className={cn(
            "block h-full w-full rounded-full border transition-colors",
            "peer-focus-visible:ring-2 peer-focus-visible:ring-action peer-focus-visible:ring-offset-2",
            checked
              ? "bg-action border-action"
              : "bg-surface-elevated border-borda-control",
          )}
        />

        {/* A bolinha. --text-on-primary e não branco cravado: no escuro o
            --action inverte para o degrau claro da rampa, e o branco cai a
            2,69:1. É a lição da emenda E1. */}
        <span
          aria-hidden="true"
          className={cn(
            "absolute top-1/2 left-1 -translate-y-1/2 rounded-full bg-on-primary shadow-sm transition-transform",
            m.bolinha,
            checked && m.desloca,
          )}
        />
      </span>

      {label ? <span>{label}</span> : null}
    </label>
  );
}
