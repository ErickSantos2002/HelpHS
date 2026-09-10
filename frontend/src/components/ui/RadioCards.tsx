import { useId } from "react";
import { cn } from "../../lib/utils";
import { Icon, type IconName } from "./Icon";

/**
 * Escolha única apresentada como cartões ou fichas.
 *
 * ── O que ele substitui ───────────────────────────────────────────────
 *
 * O `TicketFormPage` tinha o mesmo padrão duas vezes — a grade de categorias e
 * a fileira de prioridades —, e as duas eram **pilhas de `<button>`**. Quem
 * enxerga vê oito cartões e um deles aceso; quem usa leitor de tela ouvia oito
 * botões chamados "Hardware", "Software", "Rede"…, sem "escolhido", sem "1 de
 * 8" e sem nenhuma relação com a palavra "Categoria" escrita acima.
 *
 * ── Por que rádio de verdade, e não `role="radio"` à mão ──────────────
 *
 * Escrever `role="radiogroup"` com `aria-checked` e `tabindex` móvel é
 * reimplementar, em JavaScript, quatro comportamentos que o navegador já tem:
 * seta anda entre as opções, o grupo inteiro é **uma** parada de tabulação,
 * `Espaço` escolhe, e o nome do grupo sai do `legend`. Cada um deles é uma
 * chance de errar — e a `Tabs` do pacote precisou de emenda (E12) exatamente
 * nesse terreno.
 *
 * Então o rádio é real e fica escondido só visualmente (`sr-only`), com o
 * cartão desenhado no `<label>` irmão. Foco e escolha continuam sendo do
 * navegador; o CSS só reage a eles por `peer-checked` e `peer-focus-visible`.
 *
 * ── A cor não fica sozinha ────────────────────────────────────────────
 *
 * O escolhido muda **borda, fundo e texto** ao mesmo tempo, não só a cor
 * (WCAG 1.4.1). E o par fundo/texto é sempre `tint-*` com `on-tint-*`, que é o
 * par medido do pacote — nunca uma tinta com texto do degrau 500.
 */

/** As mesmas tonalidades fechadas do `KpiCard`. */
export type RadioTone = "primary" | "info" | "success" | "warning" | "danger" | "muted";

/**
 * O estado escolhido, por tonalidade — **escrito por extenso**.
 *
 * Nada aqui pode ser montado por concatenação. O Tailwind gera utilitário
 * varrendo o texto dos arquivos: `"peer-checked:" + tom` some da varredura, a
 * regra não nasce, e o cartão escolhido fica **igual ao não escolhido** — sem
 * erro de compilação e sem aviso. É o mesmo modo de falhar que o canário da
 * galeria existe para pegar.
 *
 * O ponto entra por variante descendente (`[&_[data-ponto]]`) porque
 * `peer-checked` só enxerga IRMÃO, e o ponto mora dentro do rótulo. Ele usa a
 * cor cheia da variante, não a do texto — decisão do módulo de prioridade.
 */
const ESCOLHIDO: Record<RadioTone, string> = {
  primary:
    "peer-checked:border-primary peer-checked:bg-tint-primary peer-checked:text-on-tint-primary peer-checked:[&_[data-ponto]]:bg-primary",
  info: "peer-checked:border-info peer-checked:bg-tint-info peer-checked:text-on-tint-info peer-checked:[&_[data-ponto]]:bg-info",
  success:
    "peer-checked:border-success peer-checked:bg-tint-success peer-checked:text-on-tint-success peer-checked:[&_[data-ponto]]:bg-success",
  warning:
    "peer-checked:border-warning peer-checked:bg-tint-warning peer-checked:text-on-tint-warning peer-checked:[&_[data-ponto]]:bg-warning",
  danger:
    "peer-checked:border-danger peer-checked:bg-tint-danger peer-checked:text-on-tint-danger peer-checked:[&_[data-ponto]]:bg-danger",
  muted:
    "peer-checked:border-borda peer-checked:bg-tint-neutral peer-checked:text-on-tint-neutral peer-checked:[&_[data-ponto]]:bg-borda-control",
};

export interface RadioOption {
  value: string;
  label: string;
  /** Desenho do cartão. Some da árvore de acessibilidade: o rótulo é o nome. */
  icon?: IconName;
  /** Cor do estado escolhido. Padrão `primary`. */
  tone?: RadioTone;
}

export interface RadioCardsProps {
  /** Agrupa os rádios no navegador. Precisa ser único na página. */
  name: string;
  /** Nome do grupo, e é o `legend` — não um parágrafo solto acima dele. */
  label: string;
  value: string;
  onChange: (valor: string) => void;
  options: RadioOption[];
  /** `grade` para cartão com ícone; `linha` para ficha com ponto. */
  layout?: "grade" | "linha";
  /** Marca o `*` e passa o `required` a cada rádio, que é o nativo. */
  required?: boolean;
  error?: string;
  hint?: string;
  className?: string;
}

export function RadioCards({
  name,
  label,
  value,
  onChange,
  options,
  layout = "grade",
  required,
  error,
  hint,
  className,
}: RadioCardsProps) {
  const base = useId();
  const idErro = base + "-erro";
  const idDica = base + "-dica";
  const descrito = error ? idErro : hint ? idDica : undefined;

  return (
    <fieldset
      className={cn("min-w-0 space-y-2 border-0 p-0", className)}
      aria-describedby={descrito}
    >
      <legend className="text-sm font-medium text-conteudo">
        {label}
        {required && (
          <span className="text-on-tint-danger" aria-hidden="true">
            {" *"}
          </span>
        )}
      </legend>

      <div
        className={cn(
          layout === "grade" ? "grid grid-cols-4 gap-2 sm:grid-cols-8" : "flex gap-2",
        )}
      >
        {options.map((opcao) => {
          const tom = opcao.tone ?? "primary";
          const id = base + "-" + opcao.value;
          return (
            <div key={opcao.value} className={layout === "linha" ? "flex-1" : undefined}>
              {/*
                O rádio é real e some só da vista. `peer` liga o cartão ao
                estado dele: nada aqui decide o que está escolhido, quem decide
                é o navegador.
              */}
              <input
                type="radio"
                id={id}
                name={name}
                value={opcao.value}
                checked={value === opcao.value}
                required={required}
                aria-invalid={error ? true : undefined}
                onChange={() => onChange(opcao.value)}
                className="peer sr-only"
              />
              <label
                htmlFor={id}
                className={cn(
                  "flex cursor-pointer items-center justify-center gap-1.5 rounded-lg border",
                  "transition-colors",
                  layout === "grade"
                    ? "h-full flex-col px-2 py-3 text-center"
                    : "px-3 py-2 text-xs font-semibold",
                  // O anel vem do foco do rádio escondido, não de um `outline`
                  // no cartão: assim ele acende na navegação por teclado e
                  // some no clique, que é o que `:focus-visible` promete.
                  "peer-focus-visible:outline peer-focus-visible:outline-2",
                  "peer-focus-visible:outline-offset-2 peer-focus-visible:outline-action",
                  "border-borda-control bg-surface-elevated text-conteudo-muted",
                  "hover:border-borda hover:text-conteudo",
                  ESCOLHIDO[tom],
                )}
              >
                {opcao.icon && <Icon name={opcao.icon} size={20} />}
                {layout === "linha" && (
                  <span
                    data-ponto=""
                    className="h-2 w-2 shrink-0 rounded-full bg-borda-control"
                  />
                )}
                <span
                  className={cn(
                    layout === "grade" && "text-[11px] font-semibold leading-tight",
                  )}
                >
                  {opcao.label}
                </span>
              </label>
            </div>
          );
        })}
      </div>

      {error && (
        <p id={idErro} className="text-xs text-on-tint-danger">
          {error}
        </p>
      )}
      {hint && !error && (
        <p id={idDica} className="text-xs text-conteudo-muted">
          {hint}
        </p>
      )}
    </fieldset>
  );
}
