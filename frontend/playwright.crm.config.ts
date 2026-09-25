import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

// Own the isolated fixture server so acceptance never depends on production listeners.
export default defineConfig(base, {
  testMatch: "wholesale-crm.spec.ts",
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4178 --strictPort",
    url: "http://127.0.0.1:4178/e2e/fixtures/wholesale-crm.html",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
