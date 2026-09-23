import { expect, test, type Page } from "@playwright/test";

async function install(page: Page, missing = false) {
  const requested: string[] = [];
  const account = { user: { id: "production-operator", display_name: "Operator", email: "operator@example.test", role: "operator", must_change_password: false }, organization: { id: "run-org", name: "Production test", slug: "run-org" }, facility_id: "run-facility", capabilities: { retail: false, production: true, cultivation: false, commercial: false }, facilities: [{ id: "run-facility", name: "Production facility", code: "RUN", capabilities: { retail: false, production: true, cultivation: false, commercial: false } }] };
  await page.addInitScript(() => { localStorage.setItem("buyer-dash-organization", "run-org"); localStorage.setItem("buyer-dash-facility", "run-facility"); localStorage.setItem("buyer-dash-operation", "Production Ops"); });
  await page.route("**/api/v1/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    let body: unknown = {};
    if (request.method() !== "GET") { await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "This acceptance test must not write operational records." }) }); return; }
    if (path === "/api/v1/account/context") body = account;
    else if (path === "/api/v1/account/access-options") body = { organizations: [{ ...account.organization, facilities: account.facilities }], organization_id: "run-org", facility_id: "run-facility" };
    else if (path === "/api/v1/inventory/products") body = [];
    else if (path === "/api/v1/production/orders") body = [{ order_id: "different-run", Order: "OTHER-RUN", Product: "Not the requested run", Status: "planned", Planned: 1, Actual: 0, "Attainment %": 0, COGS: 0, "Cost / Unit": 0, Reservations: 0, QA: "pending", Attention: "" }];
    else if (path.startsWith("/api/v1/production/orders/")) {
      requested.push(path);
      if (missing || !path.endsWith("/requested-run")) { await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Production run was not found in this facility." }) }); return; }
      body = { order: { id: "requested-run", order_number: "EXACT-RUN-002", product_name: "Requested production product", sku: "EXACT", product_format: "finished_good", requested_units: 24, priority: "normal", status: "planned", notes: "", due_at: null }, bom: null, standard: null, variance: { expected_output: 24, actual_output: 0, output_variance: -24, output_variance_pct: -100, expected_loss_pct: 0, expected_labor_hours: 0, actual_labor_hours: 0, labor_variance_hours: 0, labor_variance_pct: null, expected_machine_hours: 0, actual_machine_hours: 0, machine_variance_hours: 0, machine_variance_pct: null, expected_cycle_hours: 0, actual_cycle_hours: null, cycle_variance_hours: null, cycle_variance_pct: null, qa_required: false, qa_ready: false, compliance_checkpoint: "", resource_category: "", standard_configured: false }, requirements: [], reservations: [], outputs: [], events: [], qa_events: [], cogs: { total: 0 }, planned_output: 24, actual_output: 0, attainment_pct: 0 };
    } else if (path === "/api/v1/search") body = { results: [] };
    else if (path.includes("/regulatory-detail/local/")) body = { provider: "metrc", entity_type: "production_order", entity_id: "requested-run", network_request_made: false, linked: false, entries: [] };
    else if (path.includes("/traceability-actions/entities/") && path.endsWith("/history")) body = { current_state: "unlinked", unresolved_exception_count: 0, last_successful_inbound: null, last_successful_outbound: null, events: [] };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  return requested;
}

test("an exact production-run link opens the requested record even outside the current queue", async ({ page }) => {
  const requests = await install(page);
  await page.goto("/production/runs/requested-run");
  await expect(page.getByRole("heading", { name: "Requested production product", exact: true })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Production run", exact: true })).toHaveValue("requested-run");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Requested production product", exact: true })).toBeVisible();
  expect(requests.length).toBeGreaterThanOrEqual(2);
  expect(requests.every(path => path.endsWith("/requested-run"))).toBe(true);
});

test("missing or unauthorized run does not fall back to the first queued order", async ({ page }) => {
  const requests = await install(page, true);
  await page.goto("/production/runs/requested-run");
  await expect(page.getByText("No other run was selected in its place.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Post run event", exact: true })).toHaveCount(0);
  expect(requests).toContain("/api/v1/production/orders/requested-run");
  expect(requests.some(path => path.endsWith("/different-run"))).toBe(false);
  await expect(page).toHaveURL(/\/production\/runs\/requested-run$/);
});
