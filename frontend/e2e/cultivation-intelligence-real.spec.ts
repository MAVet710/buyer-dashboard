import { test, expect, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const evidence = process.env.CI_REAL_EVIDENCE!;
if (!evidence) throw new Error("Run with scripts/acceptance/cultivation_intelligence_browser.py");
const scope = JSON.parse(fs.readFileSync(path.join(evidence, "scope.json"), "utf8"));
const origin = "http://127.0.0.1:4198";
const fixture = origin + "/e2e/fixtures/cultivation-intelligence.html";
const base = "/api/v1/cultivation-intelligence";
const headers = { "X-Organization-Id": scope.organization_id, "X-Facility-Id": scope.facility_id,
  "X-User-Id": "web-local-developer", "X-User-Role": "admin" };
let network: { method: string; path: string; status: number }[];
let forbidden: string[], errors: string[], requests: string[];

test.beforeEach(async ({ page, context }) => {
  network = []; forbidden = []; errors = []; requests = [];
  // Pass actual loopback traffic through unchanged. No response fulfillment.
  await context.route("**/*", route => {
    const url = new URL(route.request().url());
    if (!["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)) {
      forbidden.push(url.origin); return route.abort("blockedbyclient");
    }
    return route.continue();
  });
  page.on("request", request => { requests.push(new URL(request.url()).origin); });
  page.on("pageerror", error => errors.push(error.message));
  page.on("response", response => {
    const url = new URL(response.url());
    if (url.pathname.startsWith("/api/")) network.push({ method: response.request().method(), path: url.pathname + url.search, status: response.status() });
  });
  await page.addInitScript(({ organization_id, facility_id }) => {
    localStorage.setItem("buyer-dash-organization", organization_id);
    localStorage.setItem("buyer-dash-facility", facility_id);
  }, scope);
});

test.afterEach(async ({ page }, info) => {
  const name = info.title.replace(/[^a-z0-9]+/gi, "-");
  const overflow = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }));
  const windowStyles = await page.getByRole("dialog").evaluateAll(nodes => nodes.map(node => ({
    title: node.getAttribute("aria-label"), background: getComputedStyle(node).backgroundColor,
    surface_variable: getComputedStyle(node).getPropertyValue("--surface"),
  })));
  await page.screenshot({ path: path.join(evidence, `${name}.png`), fullPage: true });
  const unexpected = network.filter(row => row.status !== 200 &&
    !(row.status === 404 && row.path.endsWith("/rooms/nonexistent-synthetic-room")) &&
    !(row.status === 403 && row.method === "POST" && row.path === base + "/cycles"));
  const checks = { forbidden, page_errors: errors, overflow, window_styles: windowStyles, unexpected_http: unexpected,
    server_5xx: network.filter(row => row.status >= 500), origins: [...new Set(requests)] };
  const violations = forbidden.length + errors.length + unexpected.length + Number(overflow.scroll > overflow.width + 1);
  fs.writeFileSync(path.join(evidence, `case-${name}.json`), JSON.stringify({ name: info.title,
    status: info.status === "passed" && !violations ? "passed" : "failed", viewport: page.viewportSize(), scope,
    actual_http: network, checks, failures: info.errors.map(error => error.message) }, null, 2));
  expect(forbidden, "Non-loopback requests").toEqual([]);
  expect(errors, "Browser page errors").toEqual([]);
  expect(checks.server_5xx, "Real API server errors").toEqual([]);
  expect(unexpected, "Unexpected real HTTP status").toEqual([]);
  expect(overflow.scroll, "Horizontal overflow").toBeLessThanOrEqual(overflow.width + 1);
});

async function get(page: Page, suffix: string) {
  const response = await page.request.get(origin + base + suffix, { headers });
  network.push({ method: "GET", path: base + suffix, status: response.status() });
  expect(response.status(), await response.text()).toBe(200);
  return response.json();
}

for (const width of [390, 1280]) {
  test(`real workspace and UI cycle creation ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(fixture);
    await expect(page.getByText(/Canonical plant count: 2/)).toBeVisible();
    await expect(page.getByText(/Current stage: Synthetic flower/)).toBeVisible();
    await expect(page.getByRole("link", { name: "Open Room 360", exact: true })).toHaveAttribute("href", `/cultivation?room=${scope.room}`);
    await page.getByRole("button", { name: "Create Cycle", exact: true }).click();
    await page.getByLabel("Cycle code").fill(`BROWSER-${width}`);
    await page.getByLabel("Cycle name").fill(`UI-created cycle ${width}`);
    const saved = page.waitForResponse(response => new URL(response.url()).pathname === base + "/cycles" && response.request().method() === "POST");
    await page.getByRole("button", { name: "Save cycle", exact: true }).click();
    const response = await saved; expect(response.status()).toBe(200);
    const cycle = await response.json();
    await expect(page.getByRole("dialog", { name: "Crop Cycle 360", exact: true })).toContainText(`UI-created cycle ${width}`);
    expect((await get(page, `/cycles/${cycle.id}`)).cycle.display_name).toBe(`UI-created cycle ${width}`);
    await page.reload();
    await expect(page.getByRole("dialog", { name: "Crop Cycle 360", exact: true })).toContainText(`UI-created cycle ${width}`);
  });

  test(`real clone approved recipe preserves standards ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(fixture);
    await page.getByRole("button", { name: "Recipes", exact: true }).click();
    const original = page.locator("section.ci-stage").filter({
      has: page.getByRole("heading", { name: /^Synthetic approved standard .* Version 1$/ }),
    });
    await expect(original).toHaveCount(1);
    await original.getByRole("button", { name: "New version from this recipe", exact: true }).click();
    const saved = page.waitForResponse(response => new URL(response.url()).pathname === base + "/recipes" && response.request().method() === "POST");
    await page.getByRole("button", { name: "Save draft version", exact: true }).click();
    const response = await saved;
    expect(response.status(), await response.text()).toBe(200);
    const recipe = await response.json();
    expect(recipe.version).toBeGreaterThan(1);
    expect(recipe.stages[0].targets[0]).toMatchObject({ metric: "temperature", maximum: 24, threshold_seconds: 120 });
    const approved = await page.request.post(origin + base + `/recipes/${recipe.id}/approve`, { headers, data: { version: recipe.version } });
    network.push({ method: "POST", path: base + `/recipes/${recipe.id}/approve`, status: approved.status() });
    expect(approved.status(), await approved.text()).toBe(200);
    const recipes = (await get(page, "/recipes")).recipes;
    const first = recipes.find((row: { name: string; version: number }) => row.name === "Synthetic approved standard" && row.version === 1);
    expect(first.status).toBe("approved");
    expect(first.stages[0].targets[0]).toMatchObject({ metric: "temperature", maximum: 24, threshold_seconds: 120 });
  });

  test(`real preview commit normalized local evidence and dispositions ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(fixture + "?view=connections");
    await page.getByRole("combobox", { name: "File connection", exact: true }).selectOption(scope.connection);
    const historical = new Date(Date.parse(scope.start) + 600000).toISOString();
    const row = { source_device_id: "synthetic-device", source_channel: "temp", source_metric: "vendor_temp", value: 77, unit: "F", observed_at: historical, quality: "valid" };
    const content = [
      { ...row, event_id: `history-${width}` },
      { ...row, event_id: `current-${width}`, observed_at: new Date(Date.now() - 3000).toISOString() },
      { ...row, event_id: `unknown-${width}`, source_device_id: "unregistered-device" },
      { ...row, source_device_id: "quarantine-device", event_id: `quarantine-${width}`, observed_at: new Date(Date.now() + 86400000).toISOString() },
    ];
    await page.getByLabel("Measurement content").fill(JSON.stringify(content));
    await page.getByLabel("Explicit import mappings (JSON)").fill(JSON.stringify([
      { source_channel: "temp", source_metric: "vendor_temp", metric: "temperature", unit: "F" },
    ]));
    const previewed = page.waitForResponse(response => response.url().endsWith("/imports/preview"));
    await page.getByRole("button", { name: "Preview import", exact: true }).click();
    const preview = await previewed; expect(preview.status()).toBe(200);
    expect((await preview.json()).unknown_channels.length).toBeGreaterThan(0);
    const committed = page.waitForResponse(response => response.url().endsWith("/imports") && response.request().method() === "POST");
    await page.getByRole("button", { name: "Commit reviewed import", exact: true }).click();
    const response = await committed; expect(response.status()).toBe(200);
    expect(await response.json()).toMatchObject({ accepted: 2, queued_for_mapping: 1, quarantined: 1 });
    await expect(page.getByRole("status").filter({ hasText: "Accepted" })).toContainText("Accepted 2; duplicates 0; conflicts 0; queued for mapping 1; quarantined 1");
    await expect(page.getByText("quarantined: future_observation", { exact: true })).toBeVisible();
    const local = await get(page, `/connections/${scope.connection}/evidence`);
    const raw = local.items.find((item: { raw?: { event_id?: string } }) => item.raw?.event_id === `history-${width}`);
    expect(raw.raw).toMatchObject({ value: 77, unit: "F" });
    expect(raw.canonical).toMatchObject({ value: 25, unit: "C" });
    expect(raw.snapshot).toMatchObject({ room_id: scope.room, cycle_id: scope.cycle });
    fs.writeFileSync(path.join(evidence, `edge-normalization-${width}.json`), JSON.stringify(raw, null, 2));
    await page.getByText("Local aggregate maintenance", { exact: true }).click();
    await page.getByText("Historical aggregate window", { exact: true }).click();
    await page.getByLabel("Start (UTC hour)").fill(scope.start);
    await page.getByLabel("End (UTC hour)").fill(scope.end);
    await page.getByRole("button", { name: "Read dated aggregates" }).click();
    const rolled = page.waitForResponse(response => response.url().endsWith("/rollup"));
    await page.getByRole("button", { name: "Build selected local aggregates" }).click();
    expect((await rolled).status()).toBe(200);
  });

  test(`real room cycle reload current conditions and partial coverage ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(fixture + `?room=${scope.room}&cycle=${scope.cycle}`);
    const cycle = page.getByRole("dialog", { name: "Crop Cycle 360", exact: true });
    await expect(cycle).toContainText("Synthetic exact cycle");
    await page.reload(); await expect(cycle).toContainText("Synthetic exact cycle");
    await cycle.getByRole("button", { name: "Environment", exact: true }).click();
    await cycle.getByText("Historical aggregate window", { exact: true }).click();
    await page.getByLabel("Start (UTC hour)").fill(scope.start); await page.getByLabel("End (UTC hour)").fill(scope.end);
    await page.getByRole("button", { name: "Read dated aggregates" }).click();
    await cycle.locator("summary").filter({ hasText: /^temperature/ }).click();
    await expect(cycle).toContainText("Sample mean: 25");
    await expect(cycle).toContainText(/Unknown seconds: [1-9]/);
    await page.screenshot({ path: path.join(evidence, `cycle-coverage-${width}.png`), fullPage: true });
    await cycle.getByRole("button", { name: "Close window" }).click();
    const room = page.getByRole("dialog", { name: "Room 360", exact: true });
    await expect(room).toContainText("Synthetic room A");
    await expect(room.getByRole("link", { name: "SYNTHETIC-1", exact: true })).toHaveAttribute("href", `/cultivation?plant=${scope.plants[0]}`);
    await room.getByRole("button", { name: "Environment", exact: true }).click();
    const detail = await get(page, `/rooms/${scope.room}`);
    fs.writeFileSync(path.join(evidence, `room-response-${width}.json`), JSON.stringify(detail, null, 2));
    // Promised current EdgeStore data is mandatory. Missing integration fails.
    expect(detail.edge_latest.readings.some((reading: { value: number | null; unit: string }) => reading.value === 25 && reading.unit === "C"), "Room response must include the imported current 25 C reading separately from manual observations").toBe(true);
    await expect(room.getByRole("region", { name: "Latest sensor readings", exact: true })).toContainText("25 C", { timeout: 5000 });
    await page.reload(); await expect(room).toContainText("Synthetic room A");
    await room.getByRole("button", { name: "Environment", exact: true }).click();
    await expect(room.getByRole("region", { name: "Latest sensor readings", exact: true })).toContainText("25 C", { timeout: 5000 });
  });

  test(`real exact plant links missing room and readonly headers ${width}`, async ({ page, context }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(fixture + `?view=plant&plant=${scope.plants[0]}`);
    await expect(page.getByRole("link", { name: "Open Crop Cycle" }).first()).toHaveAttribute("href", `/cultivation?cycle=${scope.cycle}`);
    await expect(page.getByRole("link", { name: "Open Room 360" }).first()).toHaveAttribute("href", `/cultivation?room=${scope.room}`);
    await expect(page.getByText(/No proven exposure intervals/)).toBeVisible();
    await page.goto(fixture + "?room=nonexistent-synthetic-room");
    await expect(page.getByRole("dialog")).toContainText(/not found|unavailable/i);
    await expect(page.getByRole("dialog")).not.toContainText("Synthetic room A");
    await context.route("**/api/**", route => route.fallback({ headers: { ...route.request().headers(), "x-user-id": "browser-readonly", "x-user-role": "read_only" } }));
    await page.goto(fixture); await expect(page.getByText(/Canonical plant count: 2/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Create Cycle", exact: true })).toHaveCount(0);
    const denied = await page.request.post(origin + base + "/cycles", { headers: { ...headers, "X-User-Id": "browser-readonly", "X-User-Role": "read_only" }, data: { cycle_code: "DENIED", display_name: "Denied" } });
    network.push({ method: "POST", path: base + "/cycles", status: denied.status() });
    expect(denied.status()).toBe(403);
  });
}
