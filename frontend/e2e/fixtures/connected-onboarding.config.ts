import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react(), { name: "radio-test-route", configureServer(server) {
    server.middlewares.use((request, _response, next) => {
      if (request.url?.startsWith("/cultivation?")) request.url = "/e2e/fixtures/cultivation-radio.html" + request.url.slice(request.url.indexOf("?"));
      next();
    });
  } }], envDir: false,
  define: Object.fromEntries(["VITE_API_URL", "VITE_SUPABASE_URL", "VITE_SUPABASE_PUBLISHABLE_KEY", "VITE_SUPABASE_ANON_KEY"].map(key => [`import.meta.env.${key}`, JSON.stringify("")])),
  server: { host: "127.0.0.1", port: 4194, strictPort: true, hmr: false,
    proxy: { "/api": "http://127.0.0.1:8021", "/fixture": "http://127.0.0.1:8021" } },
});
