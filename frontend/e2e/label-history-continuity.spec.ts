import { expect, test, type Page } from "@playwright/test";
import type { LabelRun } from "../src/components/InventoryDrivenLabelWorkflow";

const tag = "1A4000000000000000007999";
const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32"/></svg>';
const account = {
  user: { id: "qa-user", display_name: "QA Operator", email: "qa@example.test", role: "operator" },
  organization: { id: "qa-org", name: "QA only", slug: "qa-only" }, facility_id: "qa-facility",
  capabilities: { retail: true, production: true, cultivation: false, commercial: true },
  facilities: [{ id: "qa-facility", name: "QA facility", code: "QA", capabilities: { retail: true, production: true, cultivation: false, commercial: true } }],
};
function savedRun(status = "printed"): LabelRun {
  const source = {
    lot_id: "source-lot", package_id: "1A4000000000000000007001", lot_code: "BATCH-SAVED", product_id: "source-product", product_name: "Saved source", inventory_unit: "g",
    label: { strain: "Saved strain", batch_number: "BATCH-SAVED", harvest_date: "2026-08-01", test_date: "2026-08-30", cultivated_by: "QA grower" },
    coa: { available: true, needs_confirmation: false, document_id: "coa-saved", filename: "qa.pdf", lab_name: "QA Lab", lab_license_number: "TEST", date_tested: "2026-08-30", overall_status: "pass", total_thc: 20, total_cbd: 0, total_cannabinoids: 21, total_terpenes: 1, results: [] },
    source_summary: {},
  };
  return {
    id: "saved-run", product_id: "finished-product", quantity: 24, expected_material_quantity: 0, expected_material_unit: "g", status, metrc_package_tag: tag, created_by: "original-operator", printed_by: "original-operator", created_at: "2026-09-01T12:00:00Z", printed_at: "2026-09-01T12:01:00Z",
    snapshot: { source, sources: [source], product: { name: "Saved product", sku: "SAVED-1" }, label: { product_name: "Saved product", net_contents: "3.5 g" }, quantity: 24, expected_material_quantity: 0, expected_material_unit: "g", print_layout: { layout: "compact_single", width_in: 3.5, height_in: 2.1, source_count: 1 } },
    traceability: { value: tag, qr: { value: tag, svg }, barcode: { value: tag, svg } },
    events: [{ id: "print-original", event_type: "printed", from_status: "tagged", to_status: "printed", actor: "original-operator", occurred_at: "2026-09-01T12:01:00Z", details: { copies: 24 } }],
  };
}
async function setup(page: Page, status = "printed", role = "operator") {
  let stored = savedRun(status);
  const writes: Array<{ path: string; body: Record<string, unknown> }> = [];
  const liveSourceReads: string[] = [];
  await page.addInitScript(() => {
    localStorage.setItem("buyer-dash-organization", "qa-org");
    localStorage.setItem("buyer-dash-facility", "qa-facility");
    localStorage.setItem("buyer-dash-operation", "Retail Ops");
    localStorage.setItem("buyer-dash-data-mode", "Uploads");
    (window as unknown as { printCalls: number }).printCalls = 0;
    window.print = () => { (window as unknown as { printCalls: number }).printCalls += 1; };
  });
  await page.route("**/api/v1/**", async route => {
    const request = route.request(); const url = new URL(request.url()); const path = url.pathname;
    let body: unknown = {};
    if (request.method() === "POST") writes.push({ path, body: request.postDataJSON() });
    if (path === "/api/v1/account/context") body = { ...account, user: { ...account.user, role } };
    else if (path === "/api/v1/account/access-options") body = { organizations: [{ ...account.organization, facilities: account.facilities }], organization_id: "qa-org", facility_id: "qa-facility" };
    else if (path === "/api/v1/search") body = { results: [] };
    else if (path === "/api/v1/label-printing/history") body = { items: [{ id: stored.id, product_name: "Saved product", sku: "SAVED-1", package_tag: tag, source_packages: ["BATCH-SAVED"], quantity: 24, status: stored.status, created_by: stored.created_by, created_at: stored.created_at, printed_at: stored.printed_at, print_requests: stored.events.length, last_print_request_at: stored.printed_at, width_in: 3.5, height_in: 2.1, design_revision: 0, sandbox_test_pass: false }], total: 1, offset: 0, limit: 50, has_more: false };
    else if (path === "/api/v1/label-printing/production-runs/saved-run") body = stored;
    else if (path === "/api/v1/label-printing/production-runs/saved-run/print") {
      const payload = request.postDataJSON() as { copies: number; reason: string };
      stored = { ...stored, events: [...stored.events, { id: `reprint-${stored.events.length}`, event_type: "reprinted", from_status: stored.status, to_status: stored.status, actor: "qa-user", occurred_at: "2026-09-23T12:00:00Z", details: payload }] }; body = stored;
    } else if (path.includes("/label-printing/inventory-sources") || path.includes("/product-master")) {
      liveSourceReads.push(path); await route.fulfill({ status: 503, json: { detail: "Current inventory intentionally unavailable" } }); return;
    } else if (path.includes("/label-printing/production-runs/")) {
      await route.fulfill({ status: 404, json: { detail: "Label production run was not found in this facility." } }); return;
    }
    await route.fulfill({ status: 200, json: body });
  });
  await page.goto("/compliance/labels?labelMode=history", { waitUntil: "domcontentloaded" });
  return { writes, liveSourceReads, stored: () => stored };
}

test("reopen a saved label, reload, and print only two original replacements", async ({ page }) => {
  const state = await setup(page);
  await page.getByRole("button", { name: `Open saved label ${tag}` }).click();
  await expect(page).toHaveURL(/labelRun=saved-run/);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Saved label & reprints" })).toBeVisible();
  await page.getByLabel("Replacement copies").fill("2");
  await page.getByLabel("First original label number").fill("5");
  await page.getByLabel("Reprint reason").fill("Two damaged labels");
  await page.getByRole("button", { name: "Reprint 2 replacements", exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as unknown as { printCalls: number }).printCalls)).toBe(1);
  await expect(page.locator(".production-label-copy")).toHaveCount(2);
  await expect(page.locator(".printed-unit-id").first()).toHaveText("#5 / 24");
  await expect(page.locator(".printed-unit-id").last()).toHaveText("#6 / 24");
  expect(state.liveSourceReads).toEqual([]);
  expect(state.writes).toHaveLength(1);
  expect(state.writes[0].path).toBe("/api/v1/label-printing/production-runs/saved-run/print");
  expect(state.writes[0].body.copies).toBe(2);
  expect(state.stored().quantity).toBe(24);
  expect(state.stored().metrc_package_tag).toBe(tag);
  await page.getByRole("button", { name: "Back to label history" }).click();
  await page.getByRole("button", { name: `Open saved label ${tag}` }).click();
  await expect(page.getByText(/Two damaged labels/)).toBeVisible();
});

test("archived labels remain viewable but cannot be reprinted", async ({ page }) => {
  const state = await setup(page, "archived");
  await page.getByRole("button", { name: `Open saved label ${tag}` }).click();
  await expect(page.getByRole("heading", { name: "Saved label & reprints" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Reprint \d/ })).toHaveCount(0);
  expect(state.writes).toEqual([]);
});

test("read-only users cannot request replacement prints", async ({ page }) => {
  const state = await setup(page, "printed", "read_only");
  await page.getByRole("button", { name: `Open saved label ${tag}` }).click();
  await expect(page.getByText("Your role can view saved labels but cannot create, print, or change label runs.")).toBeVisible();
  await expect(page.getByLabel("Replacement copies")).toHaveCount(0);
  expect(state.writes).toEqual([]);
});

test("a missing or inaccessible saved run never substitutes another label", async ({ page }) => {
  await setup(page);
  await page.goto("/compliance/labels?labelMode=history&labelRun=not-in-this-facility");
  await expect(page.getByText(/This saved label could not be opened/)).toBeVisible();
  await expect(page.locator(".production-label-print-batch")).toHaveCount(0);
});
