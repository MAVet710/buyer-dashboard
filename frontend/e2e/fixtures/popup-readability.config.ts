import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// Isolated synthetic fixture: no environment files or production API proxy.
export default defineConfig({ plugins: [react()], envDir: "/__popup_fixture_no_env__", optimizeDeps: { noDiscovery: true, include: [] }, build: { outDir: "tmp/popup-readability/site", rollupOptions: { input: "e2e/fixtures/popup-readability.html" } }, preview: { host: "127.0.0.1", port: 4197, strictPort: true, proxy: {} }, server: { host: "127.0.0.1", port: 4197, strictPort: true, proxy: {} } });
