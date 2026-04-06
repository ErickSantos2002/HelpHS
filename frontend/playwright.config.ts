import { defineConfig, devices } from "@playwright/test";

/**
 * E2E test configuration for HelpHS.
 *
 * Requires the dev server (npm run dev) and backend (port 8001) to be running.
 * Override credentials via env vars:
 *   ADMIN_EMAIL / ADMIN_PASSWORD
 *   TECH_EMAIL  / TECH_PASSWORD
 *   CLIENT_EMAIL / CLIENT_PASSWORD
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // run sequentially to avoid race conditions on shared DB
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["html", { open: "never" }], ["list"]],

  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "off",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  // Start the dev server automatically when running tests
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
