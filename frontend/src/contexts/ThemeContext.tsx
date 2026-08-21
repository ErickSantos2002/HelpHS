import { createContext, useContext, useEffect, useState } from "react";

type Theme = "dark" | "light";

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

const CHAVE = "helphs-theme";

/**
 * A preferência do sistema operacional, quando dá para perguntar.
 *
 * Sem `matchMedia` — navegador antigo, ou renderização fora do browser — não
 * há o que perguntar, e o escuro é o visual de casa do HelpHS.
 *
 * O script anti-flash do `index.html` repete esta mesma regra à mão, porque
 * roda antes do bundle. Mudou aqui, muda lá.
 */
function preferenciaDoSistema(): Theme {
  if (typeof window.matchMedia !== "function") return "dark";
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

/** Só conta como escolha o que o próprio usuário gravou alternando o tema. */
function escolhaSalva(): Theme | null {
  const salvo = localStorage.getItem(CHAVE);
  return salvo === "light" || salvo === "dark" ? salvo : null;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // Quem já escolheu manda, contra o sistema inclusive: o SO é o palpite
  // inicial, não uma ordem.
  const [theme, setTheme] = useState<Theme>(() => escolhaSalva() ?? preferenciaDoSistema());

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  function toggleTheme() {
    const proximo: Theme = theme === "dark" ? "light" : "dark";
    // A gravação mora aqui, e não num efeito de montagem, de propósito: gravar
    // ao montar congelaria o valor do SO daquele dia, e quem trocasse o tema
    // do sistema depois nunca mais veria a mudança refletida — "seguir o
    // sistema" valeria por uma visita só.
    localStorage.setItem(CHAVE, proximo);
    setTheme(proximo);
  }

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
