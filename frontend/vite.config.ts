import { configDefaults, defineConfig } from "vitest/config";
import { loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Para onde o dev server encaminha /api. Sem VITE_DEV_API_TARGET, é o
  // backend local na 8001. Definindo a variável (ex.: a API de produção), o
  // front local passa a falar com ela SEM CORS: o navegador só enxerga
  // localhost:5173 (mesma origem) e quem sai para a internet é o Vite, do lado
  // servidor — e servidor não faz preflight. É o que permite desenvolver o
  // front sem subir backend nenhum aqui.
  const env = loadEnv(mode, ".", "");
  const apiTarget = env.VITE_DEV_API_TARGET || "http://localhost:8001";
  const wsTarget = apiTarget.replace(/^http/, "ws");

  return {
    plugins: [react()],
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            // Core React runtime — cached across all page loads
            "vendor-react": ["react", "react-dom", "react-router-dom"],
            // Form / validation libs
            "vendor-forms": ["react-hook-form", "@hookform/resolvers", "zod"],
          },
        },
      },
    },
    server: {
      port: 5173,
      proxy: {
        // WebSocket must be matched before the generic /api rule
        "/api/v1/ws": {
          target: wsTarget,
          ws: true,
          changeOrigin: true,
        },
        "/api": {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: "happy-dom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      exclude: [...configDefaults.exclude, "e2e/**"],
      coverage: {
        provider: "v8",
        reporter: ["text", "lcov"],
        include: [
          "src/components/ui/**/*.tsx",
          // Os guards de rota decidem quem vê o quê — sem eles no include, o
          // relatório dizia 50% sem saber que essa camada existia.
          "src/components/layout/**/*.tsx",
          "src/lib/**/*.ts",
          "src/services/**/*.ts",
          "src/contexts/**/*.tsx",
        ],
      },
    },
  };
});
