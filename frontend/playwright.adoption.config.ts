import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

export default defineConfig(base, {
  testMatch: ["integration-wizard.spec.ts", "onboarding-reporting.spec.ts"],
  outputDir: "../tmp/browser-adoption",
  use: { ...base.use, channel: "msedge", baseURL: "http://127.0.0.1:4186" },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4186 --strictPort",
    url: "http://127.0.0.1:4186/e2e/fixtures/integration-wizard.html",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
