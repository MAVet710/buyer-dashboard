import { test } from "node:test";
import assert from "node:assert/strict";
import worker from "./worker.mjs";

test("all public hosts route to fixed origins, retaining path and query", async () => {
  for (const host of ["doobielogic.io", "ops.doobielogic.io", "cowboykush.doobielogic.io", "api.doobielogic.io"]) {
    const original = globalThis.fetch;
    try {
      globalThis.fetch = async (request, init) => {
        const url = new URL(request.url);
        assert.equal(url.hostname, host.startsWith("api.") ? "doobielogic-api-rc.onrender.com" : "doobielogic-web-prod.onrender.com");
        assert.equal(url.pathname + url.search, "/some/path?value=1");
        assert.equal(request.headers.get("X-Forwarded-Host"), host);
        assert.equal(init.redirect, "manual");
        return new Response("ok");
      };
      assert.equal(await (await worker.fetch(new Request(`https://${host}/some/path?value=1`))).text(), "ok");
    } finally { globalThis.fetch = original; }
  }
});

test("POST body, authorization, CORS and status survive proxying without caching", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async request => {
      assert.equal(request.method, "POST");
      assert.equal(await request.text(), '{"example":true}');
      assert.equal(request.headers.get("Authorization"), "Bearer test-only");
      assert.equal(request.headers.get("Origin"), "https://ops.doobielogic.io");
      assert.equal(request.headers.get("Forwarded"), null);
      return new Response("denied", { status: 401, headers: { "Access-Control-Allow-Origin": "https://ops.doobielogic.io" } });
    };
    const response = await worker.fetch(new Request("https://api.doobielogic.io/api/v1/example", {
      method: "POST", body: '{"example":true}', headers: { Authorization: "Bearer test-only", Origin: "https://ops.doobielogic.io", Forwarded: "host=untrusted.invalid" },
    }));
    assert.equal(response.status, 401);
    assert.equal(response.headers.get("Cache-Control"), "no-store");
    assert.equal(response.headers.get("Access-Control-Allow-Origin"), "https://ops.doobielogic.io");
  } finally { globalThis.fetch = original; }
});

test("unknown hosts fail closed and HTTP redirects retain method-safe status", async () => {
  assert.equal((await worker.fetch(new Request("https://unknown.invalid/"))).status, 404);
  const response = await worker.fetch(new Request("http://ops.doobielogic.io/path?q=1"));
  assert.equal(response.status, 308);
  assert.equal(response.headers.get("Location"), "https://ops.doobielogic.io/path?q=1");
});

test("origin redirects retain the public host and network failure is explicit", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(null, { status: 307, headers: { Location: "https://doobielogic-api-rc.onrender.com/api/v1/example/" } });
    const response = await worker.fetch(new Request("https://api.doobielogic.io/api/v1/example"));
    assert.equal(response.headers.get("Location"), "https://api.doobielogic.io/api/v1/example/");
    globalThis.fetch = async () => { throw new Error("upstream unavailable"); };
    assert.equal((await worker.fetch(new Request("https://api.doobielogic.io/"))).status, 502);
  } finally { globalThis.fetch = original; }
});
