import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

// Isolated worktree acceptance server; never use the production PC listener.
export default defineConfig(base, {
  testMatch: "doobie-work.spec.ts",
  use: { ...base.use, baseURL: "http://127.0.0.1:5179" },
});
