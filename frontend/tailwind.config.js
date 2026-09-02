/**
 * Tema apontando para os tokens do Design System da Health & Safety.
 * Base: DS/guidelines/adocao.md, Passo 2 — com uma diferença deliberada.
 *
 * O bloco do `adocao.md` declara as cores como `var(--token)` puro. No
 * Tailwind v3 isso faz o utilitário com opacidade **deixar de ser gerado**:
 * `bg-action` sai, `bg-action/10` não sai — sem erro, sem aviso. Aqui isso
 * apagaria 398 usos (`bg-primary/10`, `border-border/40`, `text-primary/80`…).
 *
 * `color-mix` resolve os dois lados: lê o token do design system direto, sem
 * duplicar valor nenhum, e ainda aceita o modificador de opacidade. Decisão
 * D1 em COMPARTILHADO/DECISOES.md. Exige Chrome 111+, Safari 16.2+, Firefox 113+.
 */
const tk = (token) =>
  `color-mix(in srgb, var(${token}) calc(<alpha-value> * 100%), transparent)`;

/** Rampa completa a partir do prefixo do token (`--color-danger-` → 50…700). */
const rampa = (prefixo, degraus) =>
  Object.fromEntries(degraus.map((d) => [d, tk(`${prefixo}${d}`)]));

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: tk("--color-primary-500"),
          ...rampa("--color-primary-", [50, 100, 200, 300, 400, 500, 600, 700, 800, 900]),
        },

        // O degrau interativo, separado do degrau de marca: botão primário,
        // item ativo, foco e link saem daqui — nunca de primary-500.
        action: {
          DEFAULT: tk("--action"),
          hover: tk("--action-hover"),
          tint: tk("--action-tint"),
        },
        surface: {
          DEFAULT: tk("--surface"),
          base: tk("--bg-base"),
          elevated: tk("--surface-elevated"),
        },
        borda: {
          DEFAULT: tk("--border-color"),
          muted: tk("--border-muted"),
          strong: tk("--border-strong"),
        },
        conteudo: {
          DEFAULT: tk("--text-body"),
          heading: tk("--text-heading"),
          muted: tk("--text-muted"),
          faint: tk("--text-faint"),
        },

        // As rampas semânticas continuam completas porque as páginas usam os
        // degraus (text-success-700, dark:text-danger-400, bg-warning-500/10).
        // O `adocao.md` declara só o 500; aqui é mesclagem, não substituição
        // (seção 5.3 do prompt mestre).
        success: { DEFAULT: tk("--color-success-500"), ...rampa("--color-success-", [50, 100, 400, 500, 600, 700]) },
        danger:  { DEFAULT: tk("--color-danger-500"),  ...rampa("--color-danger-",  [50, 100, 400, 500, 600, 700]) },
        warning: { DEFAULT: tk("--color-warning-500"), ...rampa("--color-warning-", [50, 100, 400, 500, 600, 700]) },
        info:    { DEFAULT: tk("--color-info-500"),    ...rampa("--color-info-",    [50, 100, 400, 500, 600, 700]) },

        // ── Alias de compatibilidade (decisão D2) ──────────────
        // `background-*` e `border-*` são os nomes antigos do HelpHS, com ~700
        // usos. Apontam para os mesmos tokens que `surface-*` e `borda-*`, e
        // saem na Fase 20, quando a última tela tiver migrado.
        background: {
          DEFAULT: tk("--bg-base"),
          surface: tk("--surface"),
          elevated: tk("--surface-elevated"),
        },
        border: {
          DEFAULT: tk("--border-color"),
          muted: tk("--border-muted"),
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
      borderRadius: {
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
        "2xl": "var(--radius-2xl)",
      },
      keyframes: {
        // Herdado. O `tokens/motion.css` registra este keyframe como vindo
        // daqui, inclusive o drop-shadow em rgb(14 165 233) — o azul antigo.
        // O prompt mestre manda manter como está e anotar (seção 4.2).
        "logo-pulse": {
          "0%, 100%": { transform: "scale(1)", filter: "drop-shadow(0 0 0px rgba(14,165,233,0))" },
          "50%": { transform: "scale(1.06)", filter: "drop-shadow(0 0 10px rgba(14,165,233,0.55))" },
        },
      },
      animation: {
        "logo-pulse": "logo-pulse 3s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
