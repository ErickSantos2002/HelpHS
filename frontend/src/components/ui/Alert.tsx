import type { ReactNode } from "react";
import { cn } from "../../lib/utils";
import { Icon } from "./Icon";
import type { IconName } from "./Icon";

type AlertVariant = "info" | "success" | "warning" | "danger";

/**
 * Aviso em bloco, de `DS/components/feedback/Alert.jsx`.
 *
 * ── O que a Fase 10 encontrou aqui ────────────────────────────────────
 *
 * 1. **`success` era pintado com `primary`.** Não é ajuste de tom: é a variante
 *    dizendo a cor errada. Um aviso de sucesso saía no degrau de marca, o mesmo
 *    de um botão primário, e ficava indistinguível de "aqui há uma ação".
 *
 * 2. **As quatro tintas vinham de opacidade**, `bg-info/10`, com o texto num
 *    degrau cravado da rampa (`text-info-400`). É o que a regra (b) do **D8-a**
 *    proíbe: tinta é token medido, não cor com alfa. Hoje são os pares
 *    `tint`/`on-tint` da E2 e da E8, os mesmos do `Badge`.
 *
 * 3. **`text-current/80` no corpo.** Herdava a cor da variante e a rebaixava a
 *    80% — cortando um quinto do contraste de um par que fora medido a 100%.
 *    Saiu: o corpo é o texto principal do aviso, não uma nota de rodapé.
 *
 * ── Os papéis passam a depender da variante ───────────────────────────
 *
 * As quatro variantes declaravam `role="alert"`, que é uma região viva
 * **assertiva**: ela interrompe o que o leitor de tela estiver dizendo. Para um
 * erro isso é o certo. Para um "salvo com sucesso" é atropelar a leitura da
 * pessoa com uma informação que podia esperar.
 *
 * Agora `danger` e `warning` seguem em `alert`, e `info` e `success` usam
 * `status` — que é a mesma região viva em modo **polido**, anunciada na próxima
 * pausa. É o item fixo da §29: o que a interface mostra tem de ser o que a
 * árvore de acessibilidade diz, por estado.
 *
 * **O `Alert.jsx` do pacote também usa `role="alert"` nas quatro**, e isso está
 * registrado como candidata a emenda — a correção pertence à origem, mas
 * emenda não se escreve sem autorização.
 */

const variantClasses: Record<AlertVariant, string> = {
  info: "bg-tint-info text-on-tint-info border-info/30",
  success: "bg-tint-success text-on-tint-success border-success/30",
  warning: "bg-tint-warning text-on-tint-warning border-warning/30",
  danger: "bg-tint-danger text-on-tint-danger border-danger/30",
};

const iconNames: Record<AlertVariant, IconName> = {
  info: "info",
  success: "check",
  warning: "warning",
  danger: "error",
};

/**
 * `alert` interrompe; `status` espera a próxima pausa. Erro e aviso valem a
 * interrupção — confirmação e informação não.
 */
const papeis: Record<AlertVariant, "alert" | "status"> = {
  info: "status",
  success: "status",
  warning: "alert",
  danger: "alert",
};

export interface AlertProps {
  variant?: AlertVariant;
  title?: string;
  children: ReactNode;
  className?: string;
  onDismiss?: () => void;
}

export function Alert({
  variant = "info",
  title,
  children,
  className,
  onDismiss,
}: AlertProps) {
  return (
    <div
      role={papeis[variant]}
      className={cn(
        "flex gap-3 rounded-lg border p-4 text-sm",
        variantClasses[variant],
        className,
      )}
    >
      <Icon name={iconNames[variant]} size={20} strokeWidth={2} className="shrink-0" />
      <div className="min-w-0 flex-1">
        {title && <p className="mb-0.5 font-medium">{title}</p>}
        <div>{children}</div>
      </div>
      {onDismiss && (
        <button
          // `type="button"` porque o aviso vive dentro de formulário: sem ele o
          // padrão do HTML é `submit`, e fechar o aviso enviaria o formulário.
          type="button"
          onClick={onDismiss}
          className={cn(
            "shrink-0 rounded p-0.5 transition-colors",
            // Véu neutro que inverte com o tema — `--text-body` é escuro no
            // claro e claro no escuro. Não é tinta semântica, é realce de
            // superfície, e por isso a opacidade aqui é legítima.
            "hover:bg-conteudo/10",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action",
          )}
          aria-label="Fechar"
        >
          <Icon name="close" size={16} strokeWidth={2} />
        </button>
      )}
    </div>
  );
}
