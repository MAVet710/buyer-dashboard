import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { describe, expect, it } from "vitest";

const html = readFileSync(new URL("../../index.html", import.meta.url), "utf8");
const bootstrap = html.match(/<script id="doobielogic-scanner-bootstrap">([\s\S]*?)<\/script>/)?.[1];
if (!bootstrap) throw new Error("Scanner bootstrap not found");

type Script = { src?: string; integrity?: string; crossOrigin?: string; referrerPolicy?: string; async?: boolean; onload?: () => void; onerror?: () => void };
function environment(hostname: string, pathname = "/") {
  const scripts: Script[] = [];
  const created: string[] = [];
  const window: { location: { hostname: string; pathname: string }; doobielogicScannerReady?: Promise<void>; Html5Qrcode?: unknown; BarcodeDetector?: unknown } = { location: { hostname, pathname } };
  const document = {
    head: { appendChild: (script: Script) => scripts.push(script) },
    body: { appendChild: () => undefined },
    getElementById: () => null,
    createElement: (tag: string) => {
      created.push(tag);
      if (tag === "canvas") return { getContext: () => ({}) };
      if (tag === "div") return { setAttribute: () => undefined, style: {} };
      return {};
    },
  };
  runInNewContext(bootstrap!, { window, document });
  return { window, scripts, created };
}
async function flush() { for (let turn = 0; turn < 6; turn += 1) await Promise.resolve(); }

describe("scanner dependency isolation", () => {
  it.each(["doobielogic.io", "www.doobielogic.io", "DOOBIELOGIC.IO."])("does not load scanner scripts or create a canvas on %s", async (host) => {
    const env = environment(host);
    await env.window.doobielogicScannerReady;
    expect(env.scripts).toHaveLength(0);
    expect(env.created).toHaveLength(0);
    expect(env.window.BarcodeDetector).toBeUndefined();
  });
  it.each(["ops.doobielogic.io", "localhost"])("preserves script order, security attributes and bootstrap-before-ready on %s", async (host) => {
    const env = environment(host);
    expect(env.scripts).toHaveLength(1);
    expect(env.scripts[0]).toMatchObject({ src: "https://cdnjs.cloudflare.com/ajax/libs/html5-qrcode/2.3.8/html5-qrcode.min.js", crossOrigin: "anonymous", referrerPolicy: "no-referrer", async: false });
    expect(env.scripts[0].integrity).toBe("sha512-r6rDA7W6ZeQhvl8S7yRVQUKVHdexq+GAlNkNNqVC7YyIV+NwqCTJe2hDWCiffTyRNOeGEzRRJ9ifvRm/HCzGYg==");
    env.window.Html5Qrcode = class {};
    env.scripts[0].onload?.();
    await flush();
    expect(env.scripts).toHaveLength(2);
    expect(env.scripts[1]).toMatchObject({ src: "https://cdnjs.cloudflare.com/ajax/libs/qrcode-generator/1.4.4/qrcode.min.js", crossOrigin: "anonymous", referrerPolicy: "no-referrer", async: false });
    expect(env.created).not.toContain("canvas");
    expect(env.window.BarcodeDetector).toBeUndefined();
    env.scripts[1].onload?.();
    await env.window.doobielogicScannerReady;
    expect(env.created).toContain("canvas");
    expect(env.window.BarcodeDetector).toBeTypeOf("function");
  });
  it("settles after CDN errors so operators can still open the app", async () => {
    const env = environment("ops.doobielogic.io");
    env.scripts[0].onerror?.();
    await flush();
    env.scripts[1].onerror?.();
    await expect(env.window.doobielogicScannerReady).resolves.toBeUndefined();
  });
  it("keeps the mount behind scanner readiness and retains the module entry", () => {
    const main = readFileSync(new URL("../main.tsx", import.meta.url), "utf8");
    expect(main.indexOf("await window.doobielogicScannerReady")).toBeLessThan(main.indexOf("createRoot(document"));
    expect(main).toContain('const App = lazy(');
    expect(main).toContain('<PublicStorefrontAgeGate><StorefrontPage slug={storefrontSlug} /></PublicStorefrontAgeGate>');
    expect(main).toContain('<BrowserRouter>');
    expect(main).toContain('<OfflineStatusBar />');
    expect(main).toContain('void registerDoobieLogicServiceWorker();');
    expect(main).toContain('client.setQueryDefaults(["account-context"]');
    expect(main).toContain('client.setQueryDefaults(["access-options"]');
    expect(html).toContain('<script type="module" src="/src/main.tsx"></script>');
    expect(html).not.toMatch(/<script src="https:\/\/cdnjs/);
  });
  it.each(["/store/sample-store", "/portal/test-token"])("preserves scanner availability on existing public %s flows", async (pathname) => {
    const env = environment("doobielogic.io", pathname);
    expect(env.scripts).toHaveLength(1);
    env.scripts[0].onerror?.();
    await flush();
    expect(env.scripts).toHaveLength(2);
    env.scripts[1].onerror?.();
    await env.window.doobielogicScannerReady;
  });
  it("retains the installed-app manifest and icon declarations", () => {
    expect(html).toContain('<link rel="manifest" href="/manifest.webmanifest" />');
    expect(html).toContain('<link rel="apple-touch-icon" href="/doobielogic-logo.webp" />');
  });
});
