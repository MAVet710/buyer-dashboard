import { expect, test, type Page } from "@playwright/test";
import type { Connection, IngressGrant, IngressGrantCreated, IngressGrants, PushHealth, Workspace } from "../src/components/cultivationIntelligenceTypes";

const base = "/api/v1/cultivation-intelligence";
const connection: Connection = { id: "fixture-push", provider: "json", label: "Fixture producer", mode: "push", status: "configured", version: 7, revoked_at: null, live_supported: false };
const grant: IngressGrant = { id: "fixture-grant", connection_id: connection.id, service_account_id: "fixture-account", label: "Fixture collector", version: 4, created_at: "2026-09-26T12:00:00Z", expires_at: "2027-09-26T12:00:00Z", revoked_at: null, status: "active" };
const token = "synthetic-one-time-fixture-not-a-credential";
type Options = { readOnly?: boolean; empty?: boolean; error?: number; revokeConflict?: boolean; issueError?: number; health?: Partial<PushHealth>; delayIssue?: () => Promise<void> };
async function fixture(page: Page, options: Options = {}) {
  const writes: { path: string; body: unknown; facility?: string }[] = [];
  let grants: IngressGrants = { grants: options.empty ? [] : [grant], truncated: false };
  const workspace: Workspace = { rooms: [], cycles: [], recipes: [], connections: [connection], truncated: false, can_manage: !options.readOnly, can_manage_connections: !options.readOnly, decision_support_only: true };
  const health: PushHealth = { ingress: { grant_state: "active", grants_truncated: false, transport_state: "receiving", last_push_received_at: new Date().toISOString(), last_push_batch_id: "fixture-batch" }, freshness: { basis: "connection_scope_not_room_condition", last_import_at: null, last_received_at: new Date().toISOString(), last_valid_observed_at: "2020-01-01T00:00:00Z", observation_status: "stale", sensor_freshness_status: "unknown", last_provider_contact_at: null, live_connected: false }, connection: { ...connection, stale_after_seconds: 120 }, edge: { last_push_received_at: new Date().toISOString(), last_valid_observed_at: "2020-01-01T00:00:00Z", counts: { pending: 3 }, limits: { rows: 100000 }, capacity: { state: "full", limiting_resource: "rows" } }, live_contract_status: "blocked", ...options.health };
  await page.route("**/api/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() !== "GET") writes.push({ path, body: request.postDataJSON(), facility: request.headers()["x-facility-id"] });
    if (path === `${base}/workspace`) return route.fulfill({ json: workspace });
    if (path === `${base}/connections`) return route.fulfill({ json: request.method() === "POST" ? connection : { connections: [connection], truncated: false } });
    if (path === `${base}/connections/${connection.id}/health`) return route.fulfill({ json: health });
    if (path === `${base}/connections/${connection.id}/devices`) return route.fulfill({ json: { devices: [{ id: "device1", source_device_id: "probe", display_name: "Fixture probe", version: 1 }], truncated: false } });
    if (path === `${base}/devices/device1/mapping`) return route.fulfill({ json: { mappings: [{ id: "map1", room_id: "room1", zone_id: null, effective_at: "2026-09-26T00:00:00Z" }], truncated: false } });
    if (path === `${base}/devices/device1/sensors`) return route.fulfill({ json: { sensors: [], truncated: false } });
    if (path === `${base}/metrics`) return route.fulfill({ json: { metrics: [] } });
    if (path === `${base}/connections/${connection.id}/ingress-grants` && request.method() === "GET") return options.error ? route.fulfill({ status: options.error, json: { detail: "Fixture diagnostics unavailable" } }) : route.fulfill({ json: grants });
    if (path === `${base}/connections/${connection.id}/ingress-grants` && request.method() === "POST") {
      if (options.delayIssue) await options.delayIssue();
      if (options.issueError) return route.fulfill({ status: options.issueError, json: { detail: "Fixture issuance unavailable" } });
      grants = { grants: [grant], truncated: false };
      const result: IngressGrantCreated = { grant, connection_version: 8, token };
      return route.fulfill({ json: result });
    }
    if (path === `${base}/connections/${connection.id}/ingress-grants/${grant.id}/revoke`) {
      if (options.revokeConflict) return route.fulfill({ status: 409, json: { detail: "Grant version conflict" } });
      const revoked = { ...grant, revoked_at: "2026-09-26T13:00:00Z", status: "revoked", version: 5 };
      grants = { grants: [revoked], truncated: false };
      return route.fulfill({ json: revoked });
    }
    return route.fulfill({ status: 404, json: { detail: "Unexpected fixture request" } });
  });
  await page.goto("/e2e/fixtures/cultivation-push.html");
  await page.getByRole("combobox", { name: "Cultivation connection", exact: true }).selectOption(connection.id);
  await expect(page.getByRole("heading", { name: "Normalized push setup" })).toBeVisible();
  return writes;
}
async function issue(page: Page) {
  await page.getByRole("button", { name: "Create ingress grant", exact: true }).click();
  await page.getByLabel("Producer label").fill("Fixture collector");
  await page.getByLabel("Expires at (ISO with timezone)").fill("2099-01-01T00:00:00Z");
  await page.getByRole("button", { name: "Issue one-time credential" }).click();
}

for (const width of [390, 1280]) {
  test(`one-time credential, clipboard denial and close at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() => Object.defineProperty(navigator, "clipboard", { value: { writeText: async () => { throw new DOMException("Denied", "NotAllowedError"); } } }));
    const writes = await fixture(page, { empty: true });
    await expect(page.getByText(/No ingress grants/)).toBeVisible();
    await issue(page);
    await expect(page.getByRole("textbox", { name: "One-time credential", exact: true })).toHaveValue(token);
    expect(writes[0].body).toEqual({ version: 7, label: "Fixture collector", expires_at: "2099-01-01T00:00:00Z" });
    await page.getByRole("button", { name: "Copy credential", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("Clipboard access was denied");
    await page.getByText("Integration instructions", { exact: true }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.getByRole("button", { name: "Inspect fixture cache" }).click();
    await expect(page.getByLabel("Fixture cache")).not.toContainText(token);
    expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toContain(token);
    await page.getByRole("button", { name: "Close credential setup" }).click();
    await expect(page.getByRole("textbox", { name: "One-time credential", exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "Create ingress grant", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "One-time credential", exact: true })).toHaveCount(0);
    expect(writes).toHaveLength(1);
  });
}

test("scope switch clears credential, selection and prior scoped cache", async ({ page }) => {
  await fixture(page); await issue(page);
  await expect(page.getByRole("textbox", { name: "One-time credential", exact: true })).toHaveValue(token);
  await page.getByRole("button", { name: "Switch fixture facility" }).click();
  await expect(page.getByRole("combobox", { name: "Cultivation connection", exact: true })).toHaveValue("");
  await expect(page.getByRole("textbox", { name: "One-time credential", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Inspect fixture cache" }).click();
  await expect(page.getByLabel("Fixture cache")).not.toContainText("fixture-a");
  await expect(page.getByLabel("Fixture cache")).not.toContainText(token);
});

test("credential copy reports success without caching the token", async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(navigator, "clipboard", { value: { writeText: async () => undefined } }));
  await fixture(page); await issue(page);
  await expect(page.getByRole("textbox", { name: "One-time credential", exact: true })).toHaveValue(token);
  await page.getByRole("button", { name: "Copy credential", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Credential copied.");
  await page.getByRole("button", { name: "Inspect fixture cache" }).click();
  await expect(page.getByLabel("Fixture cache")).not.toContainText(token);
});

test("a delayed grant response cannot repopulate the next facility", async ({ page }) => {
  let release!: () => void;
  const wait = new Promise<void>(resolve => { release = resolve; });
  await fixture(page, { delayIssue: () => wait }); await issue(page);
  await page.getByRole("button", { name: "Switch fixture facility" }).click();
  release();
  await page.getByRole("combobox", { name: "Cultivation connection", exact: true }).selectOption(connection.id);
  await expect(page.getByRole("textbox", { name: "One-time credential", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Create ingress grant", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "One-time credential", exact: true })).toHaveCount(0);
});

test("closed setup ignores a delayed issuance response", async ({ page }) => {
  let release!: () => void;
  const wait = new Promise<void>(resolve => { release = resolve; });
  await fixture(page, { delayIssue: () => wait }); await issue(page);
  await page.getByRole("button", { name: "Close credential setup" }).click();
  release();
  await expect(page.getByRole("textbox", { name: "One-time credential", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Create ingress grant", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "One-time credential", exact: true })).toHaveCount(0);
});

for (const conflict of [false, true]) test(`grant revoke requires confirmation and sends version, conflict=${conflict}`, async ({ page }) => {
  const writes = await fixture(page, { revokeConflict: conflict });
  await page.getByRole("button", { name: "Revoke Fixture collector", exact: true }).click();
  expect(writes).toHaveLength(0);
  await page.getByRole("button", { name: "Confirm grant revocation" }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].body).toEqual({ version: 4 });
  if (conflict) await expect(page.getByRole("alert")).toContainText("Grant version conflict");
  else await expect(page.getByText(/Fixture collector: revoked/)).toBeVisible();
});

test("read-only users inspect health and missing zones without mutation controls", async ({ page }) => {
  const writes = await fixture(page, { readOnly: true });
  await expect(page.getByText(/Readings are stale/)).toBeVisible();
  await expect(page.getByText(/Mapping backlog/)).toBeVisible();
  await page.getByText("Fixture probe", { exact: true }).click();
  await expect(page.getByText(/Zone: No zone assigned/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Room 360" })).toHaveAttribute("href", "/cultivation?room=room1");
  await expect(page.getByRole("button", { name: "Create ingress grant", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Revoke / })).toHaveCount(0);
  await expect(page.getByText("Register device", { exact: true })).toHaveCount(0);
  expect(writes).toHaveLength(0);
});

test("push creation only offers normalized JSON and preserves file choices", async ({ page }) => {
  const writes = await fixture(page);
  await expect(page.getByLabel("Import provider")).toContainText("Generic CSV");
  await page.getByLabel("Collection mode").selectOption("push");
  await expect(page.getByLabel("Import provider")).not.toContainText("Generic CSV");
  await page.getByLabel("Connection label").fill("Fixture producer");
  await page.getByRole("button", { name: "Create push connection" }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].body).toEqual({ provider: "json", label: "Fixture producer", mode: "push", expected_interval_seconds: null, stale_after_seconds: null });
});

for (const status of [409, 429, 503]) test(`issuance failure ${status} never shows a credential or retries automatically`, async ({ page }) => {
  const writes = await fixture(page, { issueError: status }); await issue(page);
  await expect(page.getByRole("status")).toContainText("Credential creation was not confirmed");
  await expect(page.getByRole("textbox", { name: "One-time credential", exact: true })).toHaveCount(0);
  expect(writes).toHaveLength(1);
});

test("grant diagnostics failure is explicit", async ({ page }) => {
  await fixture(page, { error: 503, health: { edge: null } });
  await expect(page.getByRole("alert")).toContainText("Fixture diagnostics unavailable");
  await expect(page.getByText("Status unavailable", { exact: true })).toBeVisible();
});

test("receiving, backlog and storage full remain independent", async ({ page }) => {
  const now = new Date().toISOString();
  await fixture(page, { health: { ingress: { grant_state: "active", grants_truncated: false, transport_state: "receiving", last_push_received_at: now, last_push_batch_id: "fixture-batch" }, freshness: { basis: "connection_scope_not_room_condition", last_import_at: null, last_received_at: now, last_valid_observed_at: now, observation_status: "recent", sensor_freshness_status: "unknown", last_provider_contact_at: null, live_connected: false } } });
  await expect(page.getByText("Receiving readings", { exact: true })).toBeVisible();
  await expect(page.getByText(/Mapping backlog/)).toBeVisible();
  await expect(page.getByText("Storage limit reached", { exact: true })).toBeVisible();
});

test("a historical import does not become a push receipt", async ({ page }) => {
  await fixture(page, { health: { ingress: { grant_state: "unprovisioned", grants_truncated: false, transport_state: "awaiting", last_push_received_at: null, last_push_batch_id: null } } });
  await expect(page.getByText("Awaiting first reading", { exact: true })).toBeVisible();
  await expect(page.getByText("Receiving readings", { exact: true })).toHaveCount(0);
});


test("current connection refreshes new evidence without navigation", async ({ page }) => {
  await page.clock.install();
  await fixture(page);
  await expect(page.getByText("Readings are stale", { exact: true })).toBeVisible();
  let polls = 0;
  await page.route("**/api/v1/cultivation-intelligence/connections/fixture-push/health", async route => {
    polls++;
    const now = new Date().toISOString();
    const fresh: PushHealth = {
      connection: { ...connection, stale_after_seconds: 120 },
      ingress: { grant_state: "active", grants_truncated: false, transport_state: "receiving", last_push_received_at: now, last_push_batch_id: "new-batch" },
      freshness: { basis: "connection_scope_not_room_condition", last_import_at: null, last_received_at: now, last_valid_observed_at: now, observation_status: "recent", sensor_freshness_status: "unknown", last_provider_contact_at: null, live_connected: false },
      edge: { counts: { pending: 0 } }, live_contract_status: "normalized_push",
    };
    await route.fulfill({ json: fresh });
  });
  await page.clock.fastForward(30_100);
  await expect(page.getByText("Receiving readings", { exact: true })).toBeVisible();
  await expect(page.getByText("Readings are stale", { exact: true })).toHaveCount(0);
  expect(polls).toBe(1);
});
