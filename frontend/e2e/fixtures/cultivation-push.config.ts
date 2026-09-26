import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// No environment files, real auth configuration, API proxy or live backend.
export default defineConfig({ plugins: [react()], envDir: false, define: Object.fromEntries([
  "VITE_API_URL", "VITE_SUPABASE_URL", "VITE_SUPABASE_PUBLISHABLE_KEY", "VITE_SUPABASE_ANON_KEY",
].map(key => [`import.meta.env.${key}`, JSON.stringify("")])), server: { host: "127.0.0.1", port: 4195, strictPort: true, hmr: false, proxy: {} } });
