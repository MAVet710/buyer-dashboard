import { expect, test, type Page } from "@playwright/test";
const origin = process.env.CI_OPERATOR_ORIGIN || "http://127.0.0.1:4196";
const fixture = "/e2e/fixtures/cultivation-intelligence.html";
const base = "/api/v1/cultivation-intelligence";
const room = { id: "r2", room_code: "R2", display_name: "Exact room two", phase: "vegetative", active: true, plant_capacity: 50 };
const cycle = { id: "c2", cycle_code: "C2", display_name: "Exact cycle two", genetics_label: "Fixture genetics", recipe_id: "recipe1", harvest_id: null, nursery_group_id: null, started_on: null, estimated_harvest_date: null, status: "active", version: 2 };
const recipe = { id: "recipe1", name: "Facility standard", description: "Fixture only", version: 1, status: "approved", approved_at: "2026-09-26T00:00:00Z", approved_by: "fixture-reviewer", stages: [{ id: "stage1", stage_key: "facility-stage", display_name: "Facility stage", sequence: 0, targets: [] }] };
const connection = { id: "conn1", provider: "growlink", label: "Fixture export", mode: "file", status: "configured", version: 1, revoked_at: null, live_supported: false };
async function mock(page: Page, manage = true) {
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  let created = false, revoked = false;
  const recipes = [recipe];
  // Fail closed for every API request, including unexpected legacy routes.
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const post = route.request().method() === "POST";
    if (post) writes.push({ path, body: route.request().postDataJSON() });
    if (path === "/api/v1/cultivation-radio/status" && !post) return route.fulfill({ json: { enabled: false, host_matches: false, can_manage: manage, receivers: [], runtime_error: null, limitations: [] } });
    if (path === `${base}/workspace`) return route.fulfill({ json: { rooms: [room], cycles: created ? [cycle, { ...cycle, id: "created", display_name: "Saved cycle" }] : [cycle], connections: [connection], recipes, truncated: false, can_manage: manage, can_manage_connections: manage, decision_support_only: true } });
    if (path === `${base}/rooms/r2`) return route.fulfill({ json: { room, plants: [], cycles: [cycle], environment: { readings: [] }, edge_summary: null, events: [], work: [], costs: { total: null, allocation_status: "unknown" }, truncated: false, can_manage: manage } });
    if (path === `${base}/cycles` && post) { created = true; return route.fulfill({ json: { ...cycle, id: "created", display_name: "Saved cycle" } }); }
    if ([`${base}/cycles/c2`, `${base}/cycles/created`].includes(path)) return route.fulfill({ json: { cycle: path.endsWith("created") ? { ...cycle, id: "created", display_name: "Saved cycle" } : cycle, members: [], occupancy: [], harvest: null, economics: { allocated_cost: null, allocation_status: "unknown", provenance: [] }, events: [], lineage: [], truncated: false, can_manage: manage } });
    if (path === `${base}/cycles/c2/occupancy`) return route.fulfill({ status: 409, json: { detail: "Cycle version conflict" } });
    if (path === `${base}/metrics`) return route.fulfill({ json: { metrics: [{ metric: "future_metric", unit: "custom", kind: "continuous", aliases: [] }] } });
    if (path === `${base}/recipes` && post) { recipes.push({ ...recipe, id: "draft2", version: 2, status: "draft" }); return route.fulfill({ json: recipes[1] }); }
    if (path === `${base}/connections`) return route.fulfill({ json: { connections: [{ ...connection, status: revoked ? "revoked" : "configured", revoked_at: revoked ? "2026-09-26T00:00:00Z" : null }], truncated: false } });
    if (path.endsWith("/revoke")) { revoked = true; return route.fulfill({ json: { ...connection, status: "revoked", version: 2 } }); }
    if (path.endsWith("/health")) return route.fulfill({ json: { connection, edge: null, live_contract_status: "blocked" } });
    if (path.endsWith("/devices")) return route.fulfill({ json: { devices: [{ id: "device1", display_name: "Fixture device", version: 1, mappings: [], sensors: [] }], truncated: false } });
    if (path.endsWith("/zones")) return route.fulfill({ json: { zones: [{ id: "z2", room_id: "r2", zone_code: "Z2", display_name: "Exact zone", active: true }], truncated: false } });
    if (path.endsWith("/mapping") && !post) return route.fulfill({ json: { mappings: [], truncated: false } });
    if (path.endsWith("/sensors") && !post) return route.fulfill({ json: { sensors: [], truncated: false } });
    if (path.endsWith("/mapping")) return route.fulfill({ status: 409, json: { detail: "Device version conflict" } });
    if (path.endsWith("/imports/preview")) return route.fulfill({ json: { digest: "fixture-digest", rows: 1, unknown_channels: [{ source_channel: "unmapped" }], conflicts: [], can_commit: true } });
    if (path.endsWith("/imports")) return route.fulfill({ json: { accepted: 0, duplicates: 1, conflicts: 0, queued_for_mapping: 1 } });
    return route.fulfill({ status: 404, json: { detail: "Requested fixture record unavailable" } });
  });
  // Browser cannot call any remote provider or identity service during fixtures.
  await page.route(/^https:\/\//, route => route.abort());
  return writes;
}
for (const width of [390, 1280]) {
  test(`fixture exact room and cycle, tabs and no overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 }); await mock(page);
    await page.goto(origin + fixture + "?room=r2&cycle=c2");
    const roomDialog = page.getByRole("dialog", { name: "Room 360", exact: true });
    const cycleDialog = page.getByRole("dialog", { name: "Crop Cycle 360", exact: true });
    await expect(cycleDialog).toContainText("Exact cycle two"); await cycleDialog.getByRole("button", { name: "Close window" }).click();
    await expect(roomDialog).toContainText("Exact room two"); await roomDialog.getByRole("button", { name: "Environment", exact: true }).click();
    await expect(roomDialog).toContainText("history remain unknown"); await page.keyboard.press("Tab");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.reload(); await expect(page.getByRole("dialog", { name: "Room 360", exact: true })).toContainText("Exact room two");
  });
  test(`fixture save and reopen cycle at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 }); const writes = await mock(page); await page.goto(origin + fixture);
    await page.getByRole("button", { name: "Create Cycle", exact: true }).click();
    await page.getByLabel("Cycle code").fill("FIXTURE"); await page.getByLabel("Cycle name").fill("Saved cycle"); await page.getByRole("button", { name: "Save cycle", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Crop Cycle 360", exact: true })).toContainText("Saved cycle");
    expect(writes[0].body).toMatchObject({ cycle_code: "FIXTURE", recipe_id: null }); await page.reload();
    await expect(page.getByRole("dialog", { name: "Crop Cycle 360", exact: true })).toContainText("Saved cycle");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  });
}
test("fixture unknown requested records never fall back", async ({ page }) => { await mock(page); await page.goto(origin + fixture + "?room=absent"); const dialog = page.getByRole("dialog"); await expect(dialog).toContainText("unavailable"); await expect(dialog).not.toContainText("Exact room two"); await expect(dialog.getByRole("button", { name: "Retry" })).toBeVisible(); });
test("fixture effective deny hides mutation controls", async ({ page }) => { await mock(page, false); await page.goto(origin + fixture); await expect(page.getByText("Cultivation command panel")).toBeVisible(); await expect(page.getByRole("button", { name: "Create Cycle" })).toHaveCount(0); await expect(page.getByRole("button", { name: "Recipes", exact: true })).toHaveCount(0); });
test("fixture cycle version conflict retains exact input", async ({ page }) => { const writes = await mock(page); await page.goto(origin + fixture + "?cycle=c2"); await page.getByRole("button", { name: "Manage", exact: true }).click(); await page.getByRole("combobox", { name: "Room", exact: true }).selectOption("r2"); await page.getByLabel("Entered at").fill("2026-09-26T12:00"); await page.getByRole("button", { name: "Save cycle action" }).click(); await expect(page.getByRole("alert")).toContainText("version conflict"); await expect(page.getByLabel("Entered at")).toHaveValue("2026-09-26T12:00"); expect(writes[0].body).toMatchObject({ version: 2, room_id: "r2", zone_id: null }); });
test("fixture approved recipes require a new version with arbitrary stages", async ({ page }) => { await mock(page); await page.goto(origin + fixture); await page.getByRole("button", { name: "Recipes", exact: true }).click(); await expect(page.getByRole("button", { name: "Approve version 1" })).toHaveCount(0); await page.getByRole("button", { name: "New version from this recipe" }).click(); await page.getByLabel("Stage name").fill("Facility custom stage"); await page.getByRole("button", { name: "Add target", exact: true }).click(); await page.getByRole("combobox", { name: "Measurement", exact: true }).selectOption("future_metric"); await page.getByRole("button", { name: "Save draft version" }).click(); await expect(page.getByRole("alert")).toContainText("at least one valid bound"); await page.getByLabel("Minimum").fill("0"); await page.getByRole("button", { name: "Save draft version" }).click(); await expect(page.getByRole("button", { name: "Approve version 2" })).toBeVisible(); });
test("fixture preview digest, duplicates, mapping conflict and revoke", async ({ page }) => {
  const writes = await mock(page); await page.goto(origin + fixture + "?view=connections"); await page.getByRole("combobox", { name: "File connection", exact: true }).selectOption("conn1");
  await expect(page.getByRole("button", { name: "Commit reviewed import" })).toBeDisabled();
  await page.getByLabel("Measurement content").fill('[{"event_id":"fixture","source_device_id":"d1","source_channel":"temp","source_metric":"temperature","value":77,"unit":"F","observed_at":"2026-09-26T12:00:00Z"}]'); await page.getByRole("button", { name: "Preview import" }).click(); await expect(page.getByRole("button", { name: "Commit reviewed import" })).toBeEnabled();
  await page.getByLabel("Measurement content").fill('[{"event_id":"changed","source_device_id":"d1","source_channel":"temp","source_metric":"temperature","value":77,"unit":"F","observed_at":"2026-09-26T12:00:00Z"}]'); await expect(page.getByRole("button", { name: "Commit reviewed import" })).toBeDisabled(); await page.getByRole("button", { name: "Preview import" }).click(); await page.getByRole("button", { name: "Commit reviewed import" }).click();
  await expect(page.getByRole("status")).toContainText("duplicates 1"); expect(writes.find(item => item.path.endsWith("/imports"))?.body).toMatchObject({ digest: "fixture-digest", content: '[{"event_id":"changed","source_device_id":"d1","source_channel":"temp","source_metric":"temperature","value":77,"unit":"F","observed_at":"2026-09-26T12:00:00Z"}]', mappings: [] });
  await page.getByText("Fixture device", { exact: true }).click(); await page.getByLabel("Mapped room").selectOption("r2"); await page.getByLabel("Effective at").fill("2026-09-26T12:00"); await page.getByRole("button", { name: "Save mapping revision" }).click(); await expect(page.getByRole("alert").filter({ hasText: "Device version conflict" })).toContainText("Your input is retained"); await expect(page.getByLabel("Effective at")).toHaveValue("2026-09-26T12:00");
  await page.getByRole("button", { name: "Revoke connection and preserve evidence" }).click(); await expect(page.getByText("Revoked. Existing evidence is preserved; ingestion is disabled.")).toBeVisible(); await expect(page.getByRole("button", { name: "Preview import" })).toHaveCount(0);
});
for (const width of [390, 1280]) {
  test(`fixture explicit CSV file preview and connection layout at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 }); const writes = await mock(page);
    await page.goto(origin + fixture + "?view=connections");
    await page.getByRole("combobox", { name: "File connection", exact: true }).selectOption("conn1");
    await page.getByRole("combobox", { name: "File format", exact: true }).selectOption("csv");
    const content = "event_id,source_device_id,source_channel,source_metric,value,unit,observed_at\nfixture,d1,c1,temperature,20,C,2026-09-26T12:00:00Z";
    await page.getByLabel("Choose evidence file").setInputFiles({ name: "fixture.csv", mimeType: "text/csv", buffer: Buffer.from(content) });
    await expect(page.getByLabel("Measurement content")).toHaveValue(content);
    expect(writes).toHaveLength(0);
    await page.getByRole("button", { name: "Preview import" }).click();
    await expect(page.getByRole("button", { name: "Commit reviewed import" })).toBeEnabled();
    expect(writes[0].body).toEqual({ format: "csv", content, mappings: [] });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.getByRole("button", { name: "Preview import" }).focus(); await page.keyboard.press("Tab");
    await expect(page.getByRole("region", { name: "Normalized sample readings", exact: true })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Commit reviewed import" })).toBeFocused();
  });
}
test("fixture denied connection management never offers import or revoke", async ({ page }) => {
  await mock(page, false); await page.goto(origin + fixture + "?view=connections");
  await page.getByRole("combobox", { name: "File connection", exact: true }).selectOption("conn1");
  await expect(page.getByText("Administrator capability:")).toContainText("Read only");
  for (const name of ["Preview import", "Revoke connection and preserve evidence", "Create file configuration"]) await expect(page.getByRole("button", { name, exact: true })).toHaveCount(0);
});

for (const width of [390, 1280]) {
  test(`real contract zone, transition, membership and dated aggregates at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 }); await mock(page);
    let version = 2, closed = false;
    const writes: { path: string; body: Record<string, unknown> }[] = [];
    const zones: { id: string; room_id: string; zone_code: string; display_name: string; active: boolean }[] = [];
    const summary = { status: "PARTIAL", start: 1790294400, end: 1790380800, truncated: true, streams: [{ metric: "future_metric", kind: "continuous", unit: "custom", snapshot: { sensor_id: "sensor-real", recipe_revision: 1, threshold_seconds: 120 }, coverage_seconds: 180, unknown_seconds: 86220, above_seconds: 180, below_seconds: 0, attribution_intervals: [[1790294400, 1790294580]], deviations: [{ start: 1790294400, end: 1790294580, direction: "above", seconds: 180 }] }] };
    await page.route(`**${base}/**`, async route => {
      const url = new URL(route.request().url()), path = url.pathname, post = route.request().method() === "POST";
      if (post) writes.push({ path, body: route.request().postDataJSON() });
      if (path === `${base}/rooms/r2/zones`) {
        if (post) { zones.push({ id: "zone-created", room_id: "r2", zone_code: "N", display_name: "North", active: true }); return route.fulfill({ json: zones[0] }); }
        return route.fulfill({ json: { zones, truncated: false } });
      }
      if (path === `${base}/rooms/r2`) return route.fulfill({ json: { room, zones, approved_targets: [{ metric: "future_metric", minimum: null, maximum: 1, unit: "custom", recipe_version: 1 }], plants: [{ id: "plant-canonical", plant_tag: "TAG-1", phase: "vegetative" }], cycles: [cycle], environment: { readings: [] }, edge_summary: summary, events: [], work: [], costs: { total: null, recorded_total: 12, recorded_entry_count: 1, allocation_status: "unknown" }, can_manage: true, can_manage_connections: true, truncated: false } });
      if (path === `${base}/cycles/c2`) return route.fulfill({ json: { cycle: { ...cycle, version }, approved_recipe: recipe, members: [], occupancy: closed ? [] : [{ id: "occ-real", room_id: "r2", stage_id: "stage1", entered_at: "2026-09-26T00:00:00Z", exited_at: null }], harvest: null, economics: { allocated_cost: null, allocation_status: "unknown", provenance: [] }, events: [], lineage: [], edge_summary: { rooms: [{ room_id: "r2", summary }], truncated: false }, can_manage: true, truncated: false } });
      if (path.endsWith("/close")) { closed = true; version++; return route.fulfill({ json: { id: "occ-real", version } }); }
      if (path.endsWith("/occupancy") || path.endsWith("/members")) { version++; return route.fulfill({ json: { id: "next-real", version } }); }
      return route.fallback();
    });
    await page.goto(origin + fixture + "?room=r2");
    await page.getByRole("button", { name: "Operations", exact: true }).click();
    await expect(page.getByText(/Recorded costs:/)).toContainText("12");
    await page.getByLabel("Zone code").fill("N"); await page.getByLabel("Zone name").fill("North"); await page.getByRole("button", { name: "Create zone", exact: true }).click(); await expect(page.getByRole("button", { name: "Create another zone" })).toBeVisible();
    await page.goto(origin + fixture + "?cycle=c2"); await page.getByRole("button", { name: "Manage", exact: true }).click();
    const boundary = "2026-09-27T00:00:00Z";
    await page.getByLabel("Transition boundary").fill(boundary); await page.getByRole("button", { name: "Close this occupancy" }).click();
    await expect(page.getByLabel("Entered at")).toHaveValue(boundary);
    const refresh = page.getByRole("button", { name: "Use current version 3 and keep input" });
    await expect(refresh.or(page.getByText("Editing cycle version 3.", { exact: false }))).toBeVisible();
    if (await refresh.count()) await refresh.click();
    await expect(page.getByText("Editing cycle version 3.", { exact: false })).toBeVisible();
    await page.getByRole("combobox", { name: "Room", exact: true }).selectOption("r2"); await page.getByLabel("Zone (optional)").selectOption("zone-created"); await page.getByLabel("Approved recipe stage").selectOption("stage1"); await page.getByRole("button", { name: "Save cycle action" }).click();
    await expect.poll(() => writes.filter(write => write.path.endsWith("/occupancy")).length).toBe(1);
    expect(writes.find(write => write.path.endsWith("/close"))?.body).toEqual({ version: 2, exited_at: boundary });
    expect(writes.find(write => write.path.endsWith("/occupancy"))?.body).toEqual({ version: 3, room_id: "r2", zone_id: "zone-created", stage_id: "stage1", entered_at: boundary, exited_at: null });
    await page.getByLabel("Cycle action").selectOption("members"); await page.getByLabel("Plant choice room").selectOption("r2"); await page.getByLabel("Canonical plant IDs").selectOption("plant-canonical"); await page.getByLabel("Effective at").fill(boundary); await page.getByRole("button", { name: "Save cycle action" }).click();
    await expect.poll(() => writes.filter(write => write.path.endsWith("/members")).length).toBe(1); expect(writes.find(write => write.path.endsWith("/members"))?.body.plant_ids).toEqual(["plant-canonical"]);
    await page.getByRole("button", { name: "Environment", exact: true }).click(); await page.getByText("future_metric", { exact: false }).click(); await expect(page.getByText(/Cumulative out-of-target seconds/)).toBeVisible(); await expect(page.getByText(/Continuous threshold:/)).toContainText("120 seconds");
    await page.getByText("Historical aggregate window", { exact: true }).click(); await page.getByLabel("Start (UTC hour)").fill("2026-09-25T00:00:00Z"); await page.getByLabel("End (UTC hour)").fill("2026-09-26T00:00:00Z");
    const read = page.waitForRequest(request => request.url().includes("/cycles/c2?start=")); await page.getByRole("button", { name: "Read dated aggregates" }).click(); expect(new URL((await read).url()).searchParams.get("end")).toBe("2026-09-26T00:00:00Z");
    await expect(page.getByText(/Summary is incomplete/)).toBeVisible(); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  });
}

test("facility reload clears prior evidence and exact deep links fail closed", async ({ page }) => {
  await mock(page); await page.goto(origin + fixture + "?room=r2"); await expect(page.getByRole("dialog")).toContainText("Exact room two");
  await page.route(`**${base}/**`, async route => {
    if (route.request().headers()["x-facility-id"] !== "changed-facility") return route.fallback();
    return new URL(route.request().url()).pathname.endsWith("/workspace") ? route.fulfill({ json: { rooms: [], cycles: [], recipes: [], connections: [], can_manage: false, can_manage_connections: false, truncated: false, decision_support_only: true } }) : route.fulfill({ status: 404, json: { detail: "No record in changed facility" } });
  });
  await page.evaluate(() => localStorage.setItem("buyer-dash-facility", "changed-facility")); await page.reload();
  await expect(page.getByRole("dialog")).toContainText("No record in changed facility"); await expect(page.getByRole("dialog")).not.toContainText("Exact room two"); await expect(page.getByRole("button", { name: "Create Cycle" })).toHaveCount(0);
});

test("loading is explicit until bounded workspace resolves", async ({ page }) => {
  await mock(page); let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route(`**${base}/workspace`, async route => { await gate; return route.fulfill({ json: { rooms: [], cycles: [], recipes: [], connections: [], can_manage: false, can_manage_connections: false, truncated: false } }); });
  await page.goto(origin + fixture); await expect(page.getByText("Loading evidence...")).toBeVisible(); release(); await expect(page.getByText(/No canonical rooms are configured/)).toBeVisible();
});

test("metadata, mapping versions, quarantine reasons, rollup and retention protection", async ({ page }) => {
  await mock(page); let deviceVersion = 1, connectionVersion = 1;
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  await page.route(`**${base}/**`, async route => {
    const path = new URL(route.request().url()).pathname, post = route.request().method() === "POST";
    if (post) writes.push({ path, body: route.request().postDataJSON() });
    if (path === `${base}/connections`) return route.fulfill({ json: { connections: [{ ...connection, version: connectionVersion }], truncated: false } });
    if (path.endsWith("/health")) return route.fulfill({ json: { connection: { ...connection, last_import_at: "2026-09-26T12:00:00Z" }, edge: { last_received_at: "2026-09-26T11:00:00Z", last_valid_observed_at: "2026-09-24T00:00:00Z", counts: { ready: 1, quarantined: 2 } }, live_contract_status: "blocked" } });
    if (path.endsWith("/devices")) return route.fulfill({ json: { devices: [{ id: "device1", source_device_id: "source-real", display_name: "Fixture device", version: deviceVersion }], truncated: false } });
    if (path.endsWith("/mapping") || path.endsWith("/sensors")) {
      if (post) { deviceVersion++; connectionVersion++; return route.fulfill({ json: { id: "device1", version: deviceVersion, connection_version: connectionVersion } }); }
      return route.fulfill({ json: path.endsWith("/mapping") ? { mappings: [{ id: "mapping-real", room_id: "r2", zone_id: "z2", effective_at: "2026-09-26T00:00:00Z" }], truncated: false } : { sensors: [{ id: "sensor1", source_channel: "ch1", source_metric: "source_temperature", source_unit: "C", metric: "temperature", unit: "C" }], truncated: false } });
    }
    if (path.endsWith("/imports")) return route.fulfill({ json: { accepted: 0, duplicates: 0, conflicts: 1, queued_for_mapping: 1, quarantined: 2, dispositions: [{ status: "quarantined", reason: "invalid_quality" }] } });
    if (path.endsWith("/maintenance")) return route.fulfill({ json: { retention_blocker: "durable_aggregate_receiver_not_configured", configuration: { bucket_seconds: 3600, max_window_seconds: 2678400 } } });
    if (path.endsWith("/rollup")) return route.fulfill({ json: { rebuilt: 1, unchanged: 0, blocked: 2, truncated: true, cloud_publication: false } });
    return route.fallback();
  });
  await page.goto(origin + fixture + "?view=connections"); await page.getByRole("combobox", { name: "File connection", exact: true }).selectOption("conn1");
  await expect(page.getByText(/Last import \(count-only audit\)/)).toContainText("2026-09-24T00:00:00Z");
  await page.getByLabel("Measurement content").fill("[]"); await page.getByRole("button", { name: "Preview import" }).click(); await expect(page.getByRole("button", { name: "Commit reviewed import" })).toBeEnabled();
  await page.getByText("Fixture device", { exact: true }).click(); await expect(page.getByText(/ch1: source_temperature/)).toBeVisible();
  await page.getByLabel("Mapped room").selectOption("r2"); await page.getByLabel("Zone (optional)").selectOption("z2"); await page.getByLabel("Effective at").fill("2026-09-27T00:00"); await page.getByRole("button", { name: "Save mapping revision" }).click();
  await expect(page.getByRole("button", { name: "Commit reviewed import" })).toBeDisabled();
  await page.getByLabel("Source channel", { exact: true }).fill("ch2"); await page.getByLabel("Source metric", { exact: true }).fill("custom"); await page.getByLabel("Source unit", { exact: true }).fill("custom"); await page.getByLabel("Normalized measurement").selectOption("future_metric"); await page.getByRole("button", { name: "Save channel mapping" }).click();
  await expect.poll(() => writes.some(write => write.path.endsWith("/sensors"))).toBe(true); expect(writes.find(write => write.path.endsWith("/sensors"))?.body.version).toBe(2);
  await expect(page.getByText(/Provider: growlink/)).toContainText("Version 3");
  await page.getByLabel("Measurement content").fill("[]"); await page.getByRole("button", { name: "Preview import" }).click(); await page.getByRole("button", { name: "Commit reviewed import" }).click(); await expect(page.getByText(/quarantined 2/)).toBeVisible(); await expect(page.getByText("quarantined: invalid_quality")).toBeVisible();
  await page.getByText("Local aggregate maintenance", { exact: true }).click(); await expect(page.getByText(/Retention protection:/)).toContainText("durable_aggregate_receiver_not_configured");
  await page.getByText("Historical aggregate window", { exact: true }).click(); await page.getByLabel("Start (UTC hour)").fill("2026-09-25T00:00:00Z"); await page.getByLabel("End (UTC hour)").fill("2026-09-26T00:00:00Z"); await page.getByRole("button", { name: "Read dated aggregates" }).click(); await page.getByRole("button", { name: "Build selected local aggregates" }).click(); await expect(page.getByText(/Rebuilt: 1/)).toContainText("Yes, incomplete");
  expect(writes.some(write => write.path.endsWith("/retention"))).toBe(false);
});

test("optional threshold has explicit seconds conversion without universal defaults", async ({ page }) => {
  const writes = await mock(page); await page.goto(origin + fixture); await page.getByRole("button", { name: "Recipes", exact: true }).click(); await page.getByRole("button", { name: "New version from this recipe" }).click(); await page.getByRole("button", { name: "Add target", exact: true }).click();
  await expect(page.getByText("Not configured", { exact: true })).toBeVisible(); await page.getByRole("combobox", { name: "Measurement", exact: true }).selectOption("future_metric"); await page.getByLabel("Minimum").fill("0"); await page.getByLabel("Continuous deviation threshold (seconds, optional)").fill("120"); await expect(page.getByText("2 minutes; 60 seconds = 1 minute")).toBeVisible(); await page.getByRole("button", { name: "Save draft version" }).click();
  await expect.poll(() => writes.length).toBe(1); expect(writes[0].body.stages).toEqual([{ stage_key: "facility-stage", display_name: "Facility stage", sequence: 0, targets: [{ metric: "future_metric", minimum: 0, maximum: null, unit: "custom", threshold_seconds: 120 }] }]);
});

test("canonical Plant360 links remain cohort references, not individual exposure", async ({ page }) => {
  await mock(page);
  await page.route(`**${base}/plants/plant1/exposure`, route => route.fulfill({ json: { plant_id: "plant1", exposure_status: "unknown", reason: "Individual movement is unproven.", intervals: [], memberships: [{ id: "member1", cycle_id: "c2", added_at: "2026-09-25T00:00:00Z", removed_at: null, cycle_url: "/cultivation?cycle=c2" }], cohort_occupancy: [{ id: "occ1", cycle_id: "c2", room_id: "r2", zone_id: "z2", entered_at: "2026-09-25T00:00:00Z", exited_at: null, evidence_basis: "cycle_occupancy_not_individual_movement" }], relationships: { mother_plant_id: "mother1", mother_plant_tag: "MOTHER", group_ids: ["group1"], harvest_ids: ["harvest1"] }, truncated: true } }));
  await page.goto(origin + fixture + "?view=plant&plant=plant1");
  await expect(page.getByText(/No proven exposure intervals/)).toBeVisible(); await expect(page.getByText(/Cycle occupancy does not prove/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Crop Cycle" }).first()).toHaveAttribute("href", "/cultivation?cycle=c2"); await expect(page.getByRole("link", { name: "Open Room 360" })).toHaveAttribute("href", "/cultivation?room=r2"); await expect(page.getByRole("link", { name: "Open canonical mother" })).toHaveAttribute("href", "/cultivation?plant=mother1"); await expect(page.getByText(/Relationship references are incomplete/)).toBeVisible();
});

test("remaining file setup actions use explicit versioned mutations", async ({ page }) => {
  await mock(page); let version = 1;
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  await page.route(`**${base}/**`, async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON(); writes.push({ path, body });
      if (path === `${base}/connections`) return route.fulfill({ json: { ...connection, version } });
      if (path.endsWith("/devices")) { version++; return route.fulfill({ json: { id: "registered", version: 1, connection_version: version } }); }
      if (path.endsWith("/drain")) return route.fulfill({ json: { processed: 2, pending: 1, conflicts: 0, raw_stays_local: true, cloud_publication: false } });
    }
    if (path === `${base}/connections`) return route.fulfill({ json: { connections: [{ ...connection, version }], truncated: false } });
    return route.fallback();
  });
  await page.goto(origin + fixture + "?view=connections"); await page.getByLabel("Connection label").fill("Fixture export"); await page.getByRole("button", { name: "Create file configuration" }).click(); await expect(page.getByRole("combobox", { name: "File connection", exact: true })).toHaveValue("conn1");
  await page.locator("summary").filter({ hasText: /^Register device$/ }).click(); await page.getByLabel("Source device ID").fill("source2"); await page.getByLabel("Device name").fill("New source"); await page.getByRole("button", { name: "Register device", exact: true }).click(); await expect(page.getByText(/Provider: growlink/)).toContainText("Version 2");
  await page.getByText("Process queued mapping evidence", { exact: true }).click(); await page.getByRole("button", { name: "Process up to 100 queued rows" }).click(); await expect(page.getByText(/Processed 2; pending 1/)).toBeVisible();
  expect(writes[0].body).toEqual({ provider: "json", label: "Fixture export", mode: "file" }); expect(writes.find(write => write.path.endsWith("/devices"))?.body).toEqual({ version: 1, source_device_id: "source2", display_name: "New source" }); expect(writes.find(write => write.path.endsWith("/drain"))?.body).toEqual({ limit: 100 });
});

test("operational events, exact harvest reference and draft approval", async ({ page }) => {
  await mock(page); const writes: { path: string; body: Record<string, unknown> }[] = [];
  await page.route(`**${base}/**`, async route => {
    if (route.request().method() !== "POST") return route.fallback();
    const path = new URL(route.request().url()).pathname; writes.push({ path, body: route.request().postDataJSON() });
    if (path.endsWith("/events")) return route.fulfill({ json: { id: "event1" } });
    if (path.endsWith("/harvest")) return route.fulfill({ json: { ...cycle, harvest_id: "harvest-real", version: 3 } });
    if (path.endsWith("/approve")) return route.fulfill({ json: { ...recipe, id: "draft2", status: "approved", version: 2 } });
    return route.fallback();
  });
  await page.goto(origin + fixture + "?cycle=c2"); await page.getByRole("button", { name: "Manage", exact: true }).click();
  await page.getByLabel("Event type").fill("inspection"); await page.getByLabel("Title", { exact: true }).fill("Reviewed source"); await page.getByRole("button", { name: "Save event" }).click(); await expect(page.getByRole("button", { name: "Record another event" })).toBeVisible();
  await page.getByLabel("Cycle action").selectOption("harvest"); await page.getByLabel("Existing canonical harvest ID").fill("harvest-real"); await page.getByRole("button", { name: "Save cycle action" }).click(); await expect.poll(() => writes.length).toBe(2); expect(writes[1].body).toEqual({ version: 2, harvest_id: "harvest-real" });
  await page.goto(origin + fixture); await page.getByRole("button", { name: "Recipes", exact: true }).click(); await page.getByRole("button", { name: "New version from this recipe" }).click(); await page.getByRole("button", { name: "Save draft version" }).click(); await page.getByRole("button", { name: "Approve version 2" }).click(); await expect.poll(() => writes.some(write => write.path.endsWith("/approve"))).toBe(true); expect(writes.find(write => write.path.endsWith("/approve"))?.body).toEqual({ version: 2 });
});

test("effective deny also removes room and cycle mutation controls", async ({ page }) => {
  await mock(page, false); await page.goto(origin + fixture + "?cycle=c2"); await expect(page.getByRole("dialog")).toContainText("Exact cycle two"); await expect(page.getByRole("button", { name: "Manage", exact: true })).toHaveCount(0);
  await page.goto(origin + fixture + "?room=r2"); await page.getByRole("button", { name: "Operations", exact: true }).click(); await expect(page.getByRole("button", { name: "Create zone", exact: true })).toHaveCount(0); await expect(page.getByRole("button", { name: "Save event", exact: true })).toHaveCount(0);
});

for (const width of [390, 1280]) {
  test(`latest imported sensor evidence stays separate and scoped at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 }); await mock(page);
    const fresh = { connection_id: "conn1", source_device_id: "fresh-source", source_channel: "air", device_id: "d1", sensor_id: "s1", metric: "temperature", value: 25, unit: "C", original_value: 77, original_unit: "F", observed_at: "2026-09-26T12:01:00Z", received_at: "2026-09-26T12:01:02Z", data_age_seconds: 2, latency_seconds: 2, state: "ready", quality: "valid", reason: null, freshness: "fresh", status: "in_target", snapshot: { room_id: "r2", organization_id: "org", facility_id: "facility", connection_id: "conn1", device_id: "d1", sensor_id: "s1", mapping_revision: "mapping", metric: "temperature", recipe_revision: "approved", target_min: 20, target_max: 26, effective_from: "2026-09-26T00:00:00Z", effective_to: "2026-09-27T00:00:00Z" } };
    await page.route(`**${base}/rooms/r2`, route => route.request().headers()["x-facility-id"] === "changed-facility" ? route.fulfill({ status: 404, json: { detail: "No room in changed facility" } }) : route.fulfill({ json: { room, plants: [], cycles: [], environment: { readings: [] }, edge_summary: null, edge_latest: { as_of: "2026-09-26T12:01:02Z", status: "UNKNOWN", truncated: true, readings: [fresh, { ...fresh, source_device_id: "stale-source", sensor_id: "s2", value: 22, status: "stale", freshness: "stale", data_age_seconds: 301 }, { ...fresh, source_device_id: "invalid-source", sensor_id: "s3", value: 98765, original_value: 98766, state: "quarantined", status: "invalid" }, { ...fresh, metric: "future_metric", unit: "custom", sensor_id: "s4", status: "unconfigured", snapshot: { ...fresh.snapshot, recipe_revision: null, target_min: null, target_max: null } }, { ...fresh, sensor_id: "s5", value: 30, status: "above", snapshot: { ...fresh.snapshot, threshold_seconds: 120 } }, { ...fresh, sensor_id: "other-room", value: 999, snapshot: { ...fresh.snapshot, room_id: "other" } }] }, events: [], work: [], costs: { total: null, allocation_status: "unknown" }, truncated: false, can_manage: true } }));
    await page.goto(origin + fixture + "?room=r2"); await page.getByRole("button", { name: "Environment", exact: true }).click();
    const latest = page.getByRole("region", { name: "Latest sensor readings" });
    await expect(latest).toContainText("25 C"); await expect(latest).toContainText("Stale source. Current value unknown."); await expect(latest).not.toContainText("22 C"); await expect(latest).not.toContainText("98765"); await expect(latest).not.toContainText("98766"); await expect(latest).not.toContainText("999"); await expect(latest).toContainText("future metric"); await expect(latest).toContainText("Target unknown");
    await latest.getByText("Reading details", { exact: true }).first().click(); await expect(latest).toContainText("Original: 77 F"); await expect(latest).toContainText("not configured"); await expect(latest).toContainText("does not establish a duration-qualified alarm");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.evaluate(() => localStorage.setItem("buyer-dash-facility", "changed-facility")); await page.reload(); await expect(page.getByRole("dialog")).toContainText("No room in changed facility"); await expect(page.getByRole("dialog")).not.toContainText("25 C");
  });
}

test("archive reports exact acknowledgements and retention requires preview of the same cutoff", async ({ page }) => {
  await mock(page); const actions: { path: string; body: unknown }[] = []; let healthReads = 0, maintenanceReads = 0;
  await page.route(`**${base}/connections/conn1/**`, route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/health")) healthReads++;
    if (path.endsWith("/maintenance")) { maintenanceReads++; return route.fulfill({ json: { archive_configured: true, retention_blocker: "requires_clean_verified_archive_and_resolved_evidence", configuration: {} } }); }
    if (path.endsWith("/archive")) { actions.push({ path, body: route.request().postDataJSON() }); return route.fulfill({ json: { archived: 3, acknowledged: 2, stale: 1, truncated: true, raw_stays_local: true, cloud_publication: false } }); }
    if (path.endsWith("/retention")) { const body = route.request().postDataJSON(); actions.push({ path, body }); return route.fulfill({ json: body.execute ? { executed: true, purged: 2, protected: 4, truncated: true, blocker: "requires_clean_verified_archive_and_resolved_evidence", receiver_acknowledged: false } : { executed: false, purged: 0, eligible: null, preview_basis: "edge_prerequisites_checked_on_execution", blocker: "requires_clean_verified_archive_and_resolved_evidence", edge: {} } }); }
    return route.fallback();
  });
  await page.goto(origin + fixture + "?view=connections"); await page.getByRole("combobox", { name: "File connection", exact: true }).selectOption("conn1"); await page.getByText("Local aggregate maintenance", { exact: true }).click();
  await page.getByRole("button", { name: "Archive local summaries" }).click(); await expect(page.getByText(/Archived: 3/)).toContainText("Exact revisions acknowledged: 2. Stale revisions: 1");
  await expect.poll(() => maintenanceReads).toBeGreaterThan(1); await expect.poll(() => healthReads).toBeGreaterThan(1);
  await page.getByText("Raw reading retention", { exact: true }).click(); const cutoff = page.getByLabel("Raw readings before (UTC)");
  await cutoff.fill("2020-01-01T00:00:00"); await page.getByRole("button", { name: "Preview retention prerequisites" }).click(); await expect(page.getByRole("region", { name: "Local archive and retention" }).getByRole("alert")).toContainText("past UTC"); expect(actions).toHaveLength(1);
  await cutoff.fill("2020-01-01T00:00:00Z"); await page.getByRole("button", { name: "Preview retention prerequisites" }).click(); await expect(page.getByText(/Eligible count is unknown/)).toBeVisible(); const remove = page.getByRole("button", { name: "Remove eligible raw readings" }); await expect(remove).toBeDisabled();
  await page.getByRole("checkbox", { name: /only eligible already-archived/ }).check(); await cutoff.fill("2020-01-02T00:00:00Z"); await expect(remove).toHaveCount(0);
  await page.getByRole("button", { name: "Preview retention prerequisites" }).click(); await expect(remove).toBeDisabled(); await page.getByRole("checkbox", { name: /only eligible already-archived/ }).check(); await remove.click(); await expect(page.getByText(/Raw bodies removed: 2/)).toContainText("Protected: 4");
  expect(actions.map(action => action.body)).toEqual([{ limit: 100 }, { before: "2020-01-01T00:00:00Z", limit: 100, execute: false }, { before: "2020-01-02T00:00:00Z", limit: 100, execute: false }, { before: "2020-01-02T00:00:00Z", limit: 100, execute: true }]);
  await expect(remove).toHaveCount(0);
});

test("unconfigured archive never offers archive or executable retention", async ({ page }) => {
  const writes = await mock(page);
  await page.route(`**${base}/connections/conn1/maintenance`, route => route.fulfill({ json: { archive_configured: false, retention_blocker: "durable_aggregate_receiver_not_configured", configuration: {} } }));
  await page.route(`**${base}/connections/conn1/retention`, route => route.fulfill({ json: { executed: false, eligible: null, blocker: "durable_aggregate_receiver_not_configured" } }));
  await page.goto(origin + fixture + "?view=connections"); await page.getByRole("combobox", { name: "File connection", exact: true }).selectOption("conn1"); await page.getByText("Local aggregate maintenance", { exact: true }).click(); await expect(page.getByText("Local summary archive is not configured on this host.")).toBeVisible(); await expect(page.getByRole("button", { name: "Archive local summaries" })).toHaveCount(0);
  await page.getByText("Raw reading retention", { exact: true }).click(); await page.getByLabel("Raw readings before (UTC)").fill("2020-01-01T00:00:00Z"); await page.getByRole("button", { name: "Preview retention prerequisites" }).click(); await page.getByRole("checkbox", { name: /only eligible already-archived/ }).check(); await expect(page.getByRole("button", { name: "Remove eligible raw readings" })).toBeDisabled(); expect(writes).toHaveLength(0);
});

test("readonly denies all local maintenance controls and reads", async ({ page }) => {
  await mock(page, false); const requests: string[] = []; page.on("request", request => { if (/\/(maintenance|archive|retention|rollup)$/.test(new URL(request.url()).pathname)) requests.push(request.url()); });
  await page.goto(origin + fixture + "?view=connections"); await page.getByRole("combobox", { name: "File connection", exact: true }).selectOption("conn1"); await expect(page.getByText(/Read only. Administrator/)).toBeVisible(); await expect(page.getByText("Local aggregate maintenance", { exact: true })).toHaveCount(0); await expect(page.getByRole("button", { name: "Archive local summaries" })).toHaveCount(0); expect(requests).toEqual([]);
});
