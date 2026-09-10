import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({ getSession: vi.fn(), refreshSession: vi.fn() }));
vi.mock("./supabase", () => ({ supabase: { auth } }));
const session = { access_token: "test-token", user: { app_metadata: { organization_id: "test-org", facility_id: "test-facility" } } };

beforeEach(() => {
  vi.resetModules(); vi.clearAllMocks();
  vi.stubGlobal("localStorage", { getItem: () => null });
  vi.stubGlobal("sessionStorage", { getItem: () => null });
  auth.getSession.mockResolvedValue({ data: { session } });
});
afterEach(() => vi.unstubAllGlobals());

describe("API session recovery", () => {
  it("aborts before fetch when session lookup is stalled", async () => {
    let finish: (value: unknown) => void = () => {};
    auth.getSession.mockReturnValue(new Promise(resolve => { finish = resolve; }));
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    const { apiGet } = await import("./api");
    const controller = new AbortController();
    const request = apiGet("/api/v1/account/context", controller.signal);
    await Promise.resolve();
    controller.abort();
    await expect(request).rejects.toMatchObject({ name: "AbortError" });
    finish({ data: { session } }); await Promise.resolve(); await Promise.resolve();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("shares one refresh between concurrent 401 responses", async () => {
    let finish: (value: unknown) => void = () => {};
    auth.refreshSession.mockReturnValue(new Promise(resolve => { finish = resolve; }));
    let requests = 0;
    vi.stubGlobal("fetch", vi.fn(async () => ++requests <= 2
      ? new Response("{}", { status: 401 })
      : new Response('{"ok":true}', { status: 200 })));
    const { apiGet } = await import("./api");
    const first = apiGet("/one"); const second = apiGet("/two");
    await vi.waitFor(() => expect(auth.refreshSession).toHaveBeenCalledTimes(1));
    finish({ data: { session }, error: null });
    await expect(Promise.all([first, second])).resolves.toEqual([{ ok: true }, { ok: true }]);
    expect(auth.refreshSession).toHaveBeenCalledTimes(1);
  });

  it("does not refresh a healthy session when the server is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response('{"detail":"Starting"}', { status: 503 })));
    const { apiGet } = await import("./api");
    await expect(apiGet("/api/v1/account/context")).rejects.toMatchObject({ status: 503 });
    expect(auth.refreshSession).not.toHaveBeenCalled();
  });
});
