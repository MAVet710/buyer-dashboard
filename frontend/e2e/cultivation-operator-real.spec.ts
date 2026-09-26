import { test, expect, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
const evidence = process.env.CI_REAL_EVIDENCE!;
if (!evidence) throw new Error("Use scripts/acceptance/cultivation_operator_browser.py");
const scope = JSON.parse(fs.readFileSync(path.join(evidence, "scope.json"), "utf8"));
const origin = "http://127.0.0.1:4193";
const fixture = origin + "/e2e/fixtures/cultivation-operator.html";
const base = "/api/v1/cultivation-intelligence";
const headers = { "X-Organization-Id": scope.organization_id, "X-Facility-Id": scope.facility_id, "X-User-Id": "web-local-developer", "X-User-Role": "admin", "Content-Type": "application/json" };
let network: { method: string; path: string; status: number }[];
let errors: string[];
let forbidden: string[];
let secretCleared: boolean;
test.beforeEach(async ({ page, context }) => {
  network = []; errors = []; forbidden = []; secretCleared = true;
  await context.route("**/*", route => {
    const url = new URL(route.request().url());
    if (!["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)) { forbidden.push(url.origin); return route.abort(); }
    return route.continue();
  });
  page.on("pageerror", error => errors.push(error.message));
  page.on("response", response => { const url = new URL(response.url()); if (url.pathname.startsWith("/api/")) network.push({ method: response.request().method(), path: url.pathname, status: response.status() }); });
  await page.addInitScript(({ organization_id, facility_id }) => {
    localStorage.setItem("buyer-dash-organization", organization_id); localStorage.setItem("buyer-dash-facility", facility_id);
  }, scope);
});
test.afterEach(async ({ page }, info) => {
  const name = info.title.replace(/[^a-z0-9]+/gi, "-");
  const overflow = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }));
  // Tokens never enter page state, request recording, screenshots or receipts.
  await page.screenshot({ path: path.join(evidence, `${name}.png`), fullPage: true });
  const checks = { overflow, errors, forbidden, secret_cleared: secretCleared, http: network };
  fs.writeFileSync(path.join(evidence, `case-${name}.json`), JSON.stringify({ name: info.title, status: info.status, checks }, null, 2));
  expect(errors).toEqual([]); expect(forbidden).toEqual([]); expect(secretCleared).toBe(true);
  expect(network.filter(row => row.status >= 500)).toEqual([]);
  expect(overflow.scroll).toBeLessThanOrEqual(overflow.width + 1);
});
async function api(suffix: string, body?: unknown, suppliedHeaders = headers) {
  const response = await fetch(origin + base + suffix, { method: body === undefined ? "GET" : "POST", headers: suppliedHeaders, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  network.push({ method: body === undefined ? "GET" : "POST", path: base + suffix, status: response.status });
  expect(response.status, `Real API ${suffix}`).toBe(200);
  return response.json();
}
async function push(value: number, name: string) {
  const connections = await api("/connections");
  const connection = connections.connections.find((row: { id: string }) => row.id === scope.connection);
  // Explicit real administrator provisioning. Native Node fetch keeps the token out of browser/tool traces.
  const issued = await fetch(origin + base + `/connections/${scope.connection}/ingress-grants`, { method: "POST", headers, body: JSON.stringify({ version: connection.version, label: "Synthetic ephemeral sender", expires_at: new Date(Date.now() + 3600000).toISOString() }) });
  expect(issued.status).toBe(200);
  let credential = await issued.json(); let token = credential.token; const grant = credential.grant;
  credential = null; secretCleared = false;
  try {
    const response = await fetch(origin + `/api/v1/external/v1/cultivation-telemetry/${scope.connection}/batches`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ schema_version: 1, batch_id: name, readings: [{ event_id: name, source_device_id: "synthetic-device", source_channel: "temp", source_metric: "vendor_temp", value, unit: "F", observed_at: new Date(Date.now() - 1000).toISOString() }] }) });
    expect(response.status).toBe(200); const result = await response.json(); expect(result.committed).toBe(true); expect(result.accepted).toBe(1);
    network.push({ method: "POST", path: "/api/v1/external/v1/cultivation-telemetry/:connection/batches", status: response.status });
  } finally {
    token = ""; secretCleared = token.length === 0;
    await api(`/connections/${scope.connection}/ingress-grants/${grant.id}/revoke`, { version: grant.version });
  }
}
async function room(page: Page) {
  await page.goto(fixture + `?room=${scope.room}`);
  const dialog = page.getByRole("dialog", { name: "Room 360", exact: true });
  await dialog.getByRole("button", { name: "Environment", exact: true }).click(); return dialog;
}
for (const width of [390, 1280]) {
  test(`real guided CSV mapping persistence and actual push refresh ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(fixture + "?view=connections");
    await page.getByRole("combobox", { name: "Cultivation connection", exact: true }).selectOption(scope.connection);
    const content = `event_id,source_device_id,source_channel,source_metric,value,unit,observed_at\nfile-${width},synthetic-device,temp,vendor_temp,077.00,F,${new Date(Date.now() - 1000).toISOString()}\n`;
    await page.getByLabel("Choose evidence file").setInputFiles({ name: "normalized.csv", mimeType: "text/csv", buffer: Buffer.from(content) });
    await page.getByRole("button", { name: "Use source channels for mapping" }).click();
    await page.getByRole("region", { name: "Review channel mappings" }).getByLabel("Normalized measurement").selectOption("temperature");
    await page.getByRole("button", { name: "Preview import", exact: true }).click();
    const preview = page.getByRole("region", { name: "Server normalized preview", exact: true });
    await expect(preview).toContainText("077.00 F"); await expect(preview).toContainText("25 C");
    await expect(preview).toContainText("Synthetic room A"); await expect(preview).toContainText("Synthetic exact cycle");
    await expect(preview).toContainText("No zone assigned");
    await page.screenshot({ path: path.join(evidence, `guided-normalized-preview-${width}.png`), fullPage: true });
    await page.getByRole("button", { name: "Commit reviewed import", exact: true }).click();
    await expect(page.getByRole("status").filter({ hasText: "Import committed" })).toContainText("Accepted 1");
    const stored = await api(`/connections/${scope.connection}/evidence`);
    const imported = stored.items.find((item: { raw?: { event_id: string } }) => item.raw?.event_id === `file-${width}`);
    expect(imported.raw.value).toBe("077.00"); expect(imported.canonical.value).toBe(25);
    // Unmount clears file review state; no stale commit survives selecting a connection again.
    await page.getByRole("combobox", { name: "Cultivation connection", exact: true }).selectOption("");
    await page.getByRole("combobox", { name: "Cultivation connection", exact: true }).selectOption(scope.connection);
    await expect(page.getByLabel("Measurement content")).toHaveValue("");
    await expect(page.getByRole("button", { name: "Commit reviewed import" })).toBeDisabled();
    const dialog = await room(page); const latest = dialog.getByRole("region", { name: "Latest sensor readings", exact: true });
    await expect(latest).toContainText("25 C");
    const originalUrl = page.url(); await push(78.8, `push-${width}`);
    await expect(latest).toContainText("26 C", { timeout: 40000 }); expect(page.url()).toBe(originalUrl);
    await expect(latest).toContainText("duration-qualified alarm");
  });
  test(`real historical reviewed Work reuse exact return and read-only denial ${width}`, async ({ page, context }) => {
    await page.setViewportSize({ width, height: 900 });
    const readings = [0, 300].map(seconds => ({ event_id: `history-${seconds}`, source_device_id: "synthetic-device", source_channel: "temp", source_metric: "vendor_temp", value: 77, unit: "F", observed_at: new Date(Date.parse(scope.start) + seconds * 1000).toISOString() }));
    const body = { format: "json", content: JSON.stringify(readings), mappings: [{ source_channel: "temp", source_metric: "vendor_temp", metric: "temperature", unit: "F" }] };
    const preview = await api(`/connections/${scope.connection}/imports/preview`, body);
    await api(`/connections/${scope.connection}/imports`, { ...body, digest: preview.digest });
    await api(`/connections/${scope.connection}/rollup`, { start: scope.start, end: scope.end });
    const list = await api(`/rooms/${scope.room}/deviations?${new URLSearchParams({ start: scope.start, end: scope.end })}`);
    expect(list.truncated).toBe(false); expect(list.items.length).toBeGreaterThan(0);
    const item = list.items[0];
    await page.goto(origin + item.return_route);
    const dialog = page.getByRole("dialog", { name: "Room 360", exact: true });
    await expect(dialog.getByRole("button", { name: "Environment", exact: true })).toHaveAttribute("aria-pressed", "true");
    const card = dialog.getByRole("article", { name: `Deviation ${item.exception_id}`, exact: true });
    await expect(card).toBeFocused();
    expect(list.can_create_work, "The real bridge must expose effective Work creation eligibility for this authorized operator").toBe(true);
    if (!item.work_item_id) {
      await card.getByRole("button", { name: "Review Work action", exact: true }).click();
      await card.getByRole("button", { name: "Create Doobie Work", exact: true }).click();
    }
    const open = card.getByRole("link", { name: "Open Work", exact: true }); await expect(open).toBeVisible();
    const href = await open.getAttribute("href"); const workId = new URL(href!, origin).searchParams.get("item");
    const repeated = await api(`/rooms/${scope.room}/deviations/${item.exception_id}/work`, { start: scope.start, end: scope.end });
    expect(repeated.existing).toBe(true); expect(repeated.work_item_id).toBe(workId);
    await open.click(); await expect(page.getByRole("region", { name: "Work details" })).toBeVisible();
    await page.getByRole("button", { name: "Open linked workspace", exact: true }).click();
    await expect(page.getByRole("article", { name: `Deviation ${item.exception_id}`, exact: true })).toBeFocused();
    expect(new URL(page.url()).searchParams.get("start")).toBe(new URL(item.return_route, origin).searchParams.get("start"));
    const work = await fetch(origin + `/api/v1/work/${workId}`, { headers }).then(result => result.json());
    const complete = await fetch(origin + `/api/v1/work/${workId}/complete`, { method: "POST", headers, body: JSON.stringify({ version: work.version }) }); expect(complete.status).toBe(200);
    const completedReuse = await api(`/rooms/${scope.room}/deviations/${item.exception_id}/work`, { start: scope.start, end: scope.end }); expect(completedReuse.work_item_id).toBe(workId);
    await context.route("**/api/**", route => route.fallback({ headers: { ...route.request().headers(), "x-user-id": "browser-readonly", "x-user-role": "read_only" } }));
    await page.reload(); await expect(page.getByRole("link", { name: "Open Work", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Create Doobie Work", exact: true })).toHaveCount(0);
    const denied = await fetch(origin + base + `/rooms/${scope.room}/deviations/${item.exception_id}/work`, { method: "POST", headers: { ...headers, "X-User-Id": "browser-readonly", "X-User-Role": "read_only" }, body: JSON.stringify({ start: scope.start, end: scope.end }) }); expect(denied.status).toBe(403);
    network.push({ method: "POST", path: "/rooms/:room/deviations/:exception/work", status: denied.status });
  });
}
