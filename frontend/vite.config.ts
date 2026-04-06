import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react-swc";

// https://vite.dev/config/
export default defineConfig({
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
        target: "ws://localhost:8001",
        ws: true,
        changeOrigin: true,
      },
      "/api": {
        target: "http://localhost:8001",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    exclude: ["node_modules", "e2e/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: [
        "src/components/ui/**/*.tsx",
        "src/lib/**/*.ts",
        "src/services/**/*.ts",
        "src/contexts/**/*.tsx",
      ],
    },
  },
});
