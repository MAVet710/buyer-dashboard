import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// Isolated fixture execution: no environment files, provider config or API proxy.
export default defineConfig({ plugins: [react()], envDir: "/__cultivation_fixture_no_env__", define: {
  "import.meta.env.VITE_API_URL": JSON.stringify(""), "import.meta.env.VITE_SUPABASE_URL": JSON.stringify(""),
  "import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY": JSON.stringify(""), "import.meta.env.VITE_SUPABASE_ANON_KEY": JSON.stringify(""),
}, build: { rollupOptions: { input: { app: "index.html", fixture: "e2e/fixtures/cultivation-intelligence.html", telemetry: "e2e/fixtures/cultivation-telemetry.html", crm: "e2e/fixtures/wholesale-crm.html", wizard: "e2e/fixtures/integration-wizard.html" } } }, optimizeDeps: { noDiscovery: true, include: [] }, server: { host: "127.0.0.1", port: 4196, strictPort: true, proxy: {} }, preview: { host: "127.0.0.1", port: 4196, strictPort: true, proxy: {} } });
