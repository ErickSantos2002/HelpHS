import { Toaster } from "sonner";
import { useTheme } from "../../contexts/ThemeContext";
import { Icon } from "./Icon";

/**
 * A configuração do `sonner`, do §7.1/§15 do prompt mestre.
 *
 * **O sonner fica.** Ele não é candidato a primitivo: notificação empilhada tem
 * fila, prioridade, pausa no hover, empilhamento e remoção animada — nada disso
 * é desenho, e reescrever seria trocar uma biblioteca resolvida por um bug
 * futuro. O que se adota são os **tokens**, na configuração.
 *
 * Mora num arquivo próprio, e não dentro do `AppLayout`, por dois motivos: é um
 * componente da Fase 10 como o `Alert` e o `Modal`, e montar o `AppLayout` num
 * teste arrastaria roteador e sessão para prender uma configuração.
 *
 * **Os 30 chamadores de `toast()` não mudam.**
 *
 * ── Três coisas que a configuração conserta ───────────────────────────
 *
 * 1. **`theme` estava cravado em `"dark"`.** No tema claro o toast continuava
 *    escuro — a única peça da interface que não acompanhava o resto. E `"system"`
 *    também não serve: o app tem escolha própria, guardada no armazenamento
 *    local, e `"system"` ignoraria a escolha da pessoa para seguir o sistema
 *    operacional. Quem sabe o tema é o contexto do app.
 *
 * 2. **`richColors` saiu.** Ele pinta o fundo inteiro do toast com a cor do
 *    tipo, usando a paleta **própria da biblioteca** — fora do sistema de
 *    tokens e sem contraste medido. É o mesmo vício que o `SlaChip` tinha com a
 *    paleta crua do Tailwind.
 *
 * 3. **A cor do tipo foi para o ícone**, que é onde ela informa sem virar
 *    decoração. O fundo é `--toast-bg` nos quatro tipos.
 *
 * ── Por que estes tokens, e não os óbvios ─────────────────────────────
 *
 * Medido contra `--toast-bg` nos dois temas, com o piso de **3:1** da WCAG
 * 1.4.11 — ícone é gráfico, não texto:
 *
 * | Token | claro | escuro | |
 * |---|---:|---:|---|
 * | `--on-tint-success` | 7,68 | 7,72 | ✅ |
 * | `--on-tint-danger` | 6,47 | 7,82 | ✅ |
 * | `--on-tint-warning` | 7,09 | 8,89 | ✅ |
 * | `--action` | 5,29 | 5,52 | ✅ |
 * | `--color-warning-500` | **2,15** | 6,91 | ❌ |
 * | `--color-success-500` | **2,54** | 5,85 | ❌ |
 * | `--action-success` | 5,48 | **2,71** | ❌ |
 *
 * As cores cheias da rampa — o palpite óbvio para "a cor do tipo" — reprovam no
 * tema claro. E o `--action-success` reprova no escuro pela mesma razão que o
 * `Input` não usa `--action-danger`: **o bloco `.dark` não os redefine**.
 *
 * O `info` usa `--action` de propósito: é a mesma cor do que é clicável no resto
 * do sistema, e informação é o tipo que mais convida à ação.
 */
export function AppToaster() {
  const { theme } = useTheme();

  return (
    <Toaster
      theme={theme}
      position="top-right"
      offset={80}
      closeButton
      icons={{
        success: (
          <Icon name="check" size={18} style={{ color: "var(--on-tint-success)" }} />
        ),
        error: (
          <Icon name="error" size={18} style={{ color: "var(--on-tint-danger)" }} />
        ),
        warning: (
          <Icon name="warning" size={18} style={{ color: "var(--on-tint-warning)" }} />
        ),
        info: <Icon name="info" size={18} style={{ color: "var(--action)" }} />,
      }}
      toastOptions={{
        duration: 4000,
        style: {
          background: "var(--toast-bg)",
          color: "var(--toast-color)",
          border: "1px solid var(--toast-border)",
          boxShadow: "var(--shadow-lg)",
          borderRadius: "var(--radius-lg)",
        },
      }}
    />
  );
}
