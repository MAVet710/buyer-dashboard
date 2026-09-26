import { defineConfig } from "vite";
import type { Plugin as EsbuildPlugin } from "esbuild";
import react from "@vitejs/plugin-react";
import { createRequire } from "node:module";
import { readFile } from "node:fs/promises";
import path from "node:path";

// esbuild's native resolver probes denied ancestors of this Windows worktree.
// Resolve installed dependencies with Node, then read only those resolved files.
const localDependencies: EsbuildPlugin = {
  name: "acceptance-local-dependencies",
  setup(build) {
    build.onResolve({ filter: /.*/ }, (args) => {
      if (!args.path.startsWith(".") && !path.isAbsolute(args.path)) return;
      const require = createRequire(args.importer || path.join(process.cwd(), "package.json"));
      return { path: require.resolve(args.path) };
    });
    build.onLoad({ filter: /\.[cm]?js$/ }, async (args) => ({
      contents: await readFile(args.path, "utf8"), loader: "js", resolveDir: path.dirname(args.path),
    }));
  },
};

export default defineConfig({
  plugins: [react(), { name: "operator-fixture-routes", configureServer(server) {
    server.middlewares.use((req, _res, next) => {
      if (/^\/(cultivation|work)(\?|$)/.test(req.url || "")) req.url = "/e2e/fixtures/cultivation-operator.html" + (req.url!.includes("?") ? req.url!.slice(req.url!.indexOf("?")) : "");
      next();
    });
  } }], envDir: false,
  cacheDir: path.join(process.env.CI_REAL_EVIDENCE || process.env.TEMP || ".", "vite-cache"),
  define: Object.fromEntries([
    "VITE_API_URL", "VITE_SUPABASE_URL", "VITE_SUPABASE_PUBLISHABLE_KEY", "VITE_SUPABASE_ANON_KEY",
  ].map(key => [`import.meta.env.${key}`, JSON.stringify("")])),
  esbuild: { tsconfigRaw: {} },
  optimizeDeps: { noDiscovery: true, include: ["react", "react-dom/client", "@supabase/supabase-js", "@tanstack/react-query", "lucide-react", "react-router-dom"], esbuildOptions: { tsconfigRaw: {}, plugins: [localDependencies] } },
  server: { host: "127.0.0.1", port: 4193, strictPort: true, hmr: false,
    proxy: { "/api": { target: "http://127.0.0.1:8018" } } },
});
