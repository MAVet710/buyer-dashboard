import { expect, test, type Page } from "@playwright/test";

async function install(page: Page, empty = false) {
  let unavailable = false;
  let available = 85;
  const paths: string[] = [];
  await page.addInitScript(() => {
    localStorage.setItem("buyer-dash-organization", "stock-org");
    if (!localStorage.getItem("buyer-dash-facility")) localStorage.setItem("buyer-dash-facility", "stock-facility");
    localStorage.setItem("buyer-dash-operation", "Retail Ops");
    localStorage.setItem("buyer-dash-data-mode", "Uploads");
  });
  await page.route("**/api/v1/**", async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    paths.push(path);
    const facility = request.headers()["x-facility-id"] || "stock-facility";
    const context = { user: { id: "buyer", display_name: "Buyer", email: "qa@example.test", role: "buyer" }, organization: { id: "stock-org", name: "Stock QA", slug: "stock-org" }, facility_id: facility, capabilities: { retail: true, production: false, cultivation: false, commercial: true }, facilities: [{ id: facility, name: "Stock facility", code: "STOCK", capabilities: { retail: true, production: false, cultivation: false, commercial: true } }] };
    let body: unknown = {};
    if (path === "/api/v1/account/context") body = context;
    else if (path === "/api/v1/account/access-options") body = { organizations: [{ ...context.organization, facilities: context.facilities }], organization_id: "stock-org", facility_id: facility };
    else if (path === "/api/v1/buyer-parity/uploaded-source-evidence") body = { state: "missing", items: [], message: "No published sources" };
    else if (path === "/api/v1/search") body = { results: [] };
    else if (path === "/api/v1/buyer-parity/current-inventory") {
      if (unavailable) { await route.fulfill({ status: 503, json: { detail: "Current inventory could not be read." } }); return; }
      const isEmpty = empty || facility === "empty-facility";
      const filteredOut = Boolean(url.searchParams.get("search"));
      const hasRows = !isEmpty && !filteredOut;
      body = {
        evidence: { state: isEmpty ? "empty" : "available", row_count: isEmpty ? 0 : 2, observed_at: "2026-09-23T12:00:00Z", provider_freshness: "Not verified" },
        items: hasRows ? [
          { id: "lot-g", product_id: "product-g", sku: "GRAMS", product_name: "Current source flower", package_id: "CURRENT-TAG-G", lot_code: "LOT-G", unit: "g", on_hand: 100, available, reserved: 15, status: "Available", location: "Vault", attention: "" },
          { id: "lot-u", product_id: "product-u", sku: "UNITS", product_name: "Held retail units", package_id: "CURRENT-TAG-U", lot_code: "LOT-U", unit: "unit", on_hand: 8, available: 0, reserved: 0, status: "Hold", location: "Hold room", attention: "Hold" },
        ] : [], total: hasRows ? 2 : 0, offset: 0, limit: 50, has_more: false,
        facets: { statuses: ["Available", "Hold"], units: ["g", "unit"] },
        summary: { package_count: hasRows ? 2 : 0, product_count: hasRows ? 2 : 0, held_packages: hasRows ? 1 : 0, totals_by_unit: hasRows ? [{ unit: "g", on_hand: 100, available, reserved: 15 }, { unit: "unit", on_hand: 8, available: 0, reserved: 0 }] : [] },
        sales_sources: { state: "missing", items: [], message: "No uploaded sales are published." },
      };
    } else if (path === "/api/v1/buyer-parity/dashboard" || path === "/api/v1/buyer-parity/legacy-overview") {
      await route.fulfill({ status: 422, json: { detail: "Historical forecast needs published sales." } }); return;
    }
    await route.fulfill({ status: 200, json: body });
  });
  return { paths, fail: () => { unavailable = true; }, recover: () => { unavailable = false; available = 75; } };
}

for (const width of [390, 1440]) test(`current Buyer inventory works without uploaded sources at ${width}px`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width, height: 1000 });
  const state = await install(page);
  await page.goto("/buying?buyerView=act");
  await page.getByText("Current inventory", { exact: true }).click();
  await expect(page.getByRole("tab", { name: "Act", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("table", { name: "Current buyer packages" })).toBeVisible();
  await expect(page.getByText("No active sales upload is published.", { exact: false })).toBeVisible();

  expect(state.paths).not.toContain("/api/v1/buyer-parity/legacy-overview");
  const totals = page.getByRole("table", { name: "Current stock totals by unit" });
  await expect(totals.getByRole("row")).toHaveCount(3);
  await expect(totals.getByRole("row").nth(1)).toContainText("85");
  await expect(page.getByRole("link", { name: "CURRENT-TAG-G" })).toHaveAttribute("href", "/inventory/packages/lot-g");
  await expect(page.getByRole("link", { name: "Current source flower" })).toHaveAttribute("href", "/inventory/products/product-g");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath(`buyer-current-${width}.png`), fullPage: true, animations: "disabled" });
});

test("failed refresh removes stale stock and retry reads new committed quantities", async ({ page }) => {
  const state = await install(page);
  await page.goto("/buying?buyerView=act");
  await page.getByText("Current inventory", { exact: true }).click();
  await expect(page.getByRole("table", { name: "Current buyer packages" })).toBeVisible();
  state.fail();
  await page.getByRole("button", { name: "Refresh current stock" }).click();
  await expect(page.getByRole("alert")).toContainText("does not mean zero stock");
  await expect(page.getByRole("table", { name: "Current buyer packages" })).toHaveCount(0);
  state.recover();
  await page.getByRole("button", { name: "Refresh current stock" }).click();
  await expect(page.getByRole("table", { name: "Current stock totals by unit" }).getByRole("row").nth(1)).toContainText("75");
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("empty facility and empty filter have different messages; old facility rows do not survive reload", async ({ page }) => {
  await install(page);
  await page.goto("/buying?buyerView=act");
  await page.getByText("Current inventory", { exact: true }).click();
  await expect(page.getByRole("table", { name: "Current buyer packages" })).toBeVisible();
  await page.getByLabel("Search current stock", { exact: true }).fill("does not match");
  await page.getByRole("button", { name: "Search current stock", exact: true }).click();
  await expect(page.getByText("No current packages match these filters.", { exact: true })).toBeVisible();
  await page.evaluate(() => localStorage.setItem("buyer-dash-facility", "empty-facility"));
  await page.reload();
  await page.getByText("Current inventory", { exact: true }).click();
  await expect(page.getByText("this facility has no retail package records.", { exact: false })).toBeVisible();
  await expect(page.getByRole("link", { name: "CURRENT-TAG-G" })).toHaveCount(0);
});

test("historical analysis is explicit, reloadable and cannot replace unavailable current stock", async ({ page }) => {
  const state = await install(page);
  await page.goto("/buying?buyerView=act");
  await page.getByText("Current inventory", { exact: true }).click();
  await page.getByRole("tab", { name: "Analyze", exact: true }).click();
  await expect(page).toHaveURL(/buyerView=analyze/);
  await expect(page.getByText("Historical uploaded-snapshot analysis", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("tab", { name: "Analyze", exact: true })).toHaveAttribute("aria-selected", "true");
  expect(state.paths).toContain("/api/v1/buyer-parity/dashboard");
  await page.getByRole("tab", { name: "Act", exact: true }).click();
  await page.getByText("Current inventory", { exact: true }).click();
  await expect(page.getByRole("table", { name: "Current buyer packages" })).toBeVisible();
});

for (const width of [390, 1440]) test(`four-view decision flow is compact and preserves actions at ${width}px`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width, height: 900 });
  const state = await install(page);
  const sku = (name: string, days: number, expiry: number) => ({ sku: name, product_name: name, category: "Flower", brand_vendor: "Test brand", onhandunits: 10, days_of_supply: days, days_to_expire: expiry, dollars_on_hand: 100 });
  const rows = [sku("Urgent flower", 2, 20), sku("Excess flower", 100, 100)];
  const writes: Record<string, unknown>[] = [];
  await page.route("**/api/v1/buyer-parity/dashboard?**", route => route.fulfill({ json: {
    summary: { units_sold: 50, reorder_asap: 1, tracked_products: 2, categories: 1 },
    sources: { inventory: { filename: "inventory.xlsx", rows: 2 }, sales: { filename: "sales.xlsx", rows: 50 } },
    forecast: [{ subcategory: "Flower", top_products: "Urgent flower", reorderpriority: "1 \u2013 Reorder ASAP", reorderqty: 12, onhandunits: 10, avgunitsperday: 5, product_count: 1 }],
    category_dos: [], product_rows: [], product_rows_total: 0, sku_views: { all: rows, reorder: [rows[0]], expiring: [rows[0]], overstock: [rows[1]] },
  } }));
  for (const action of ["inventory-check", "buyer-brief"]) await page.route(`**/api/v1/buyer-parity/${action}`, route => {
    writes.push(route.request().postDataJSON());
    return route.fulfill({ json: { answer: `${action} completed`, confidence: "review" } });
  });
  await page.goto("/buying?unrelated=keep");
  await expect(page.getByRole("tab", { name: "Today", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("1 held packages need review.", { exact: false })).toBeVisible();
  await expect(page.getByRole("table", { name: "Current buyer packages" })).toHaveCount(0);
  expect(state.paths).not.toContain("/api/v1/buyer-parity/dashboard");
  expect(state.paths).not.toContain("/api/v1/buyer-parity/legacy-overview");
  expect(await page.locator("#buyer-panel").evaluate(element => element.scrollHeight)).toBeLessThan(1250);
  await page.screenshot({ path: testInfo.outputPath(`buyer-today-${width}.png`), fullPage: true });
  await page.getByRole("tab", { name: "Today", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Decide", exact: true })).toBeFocused();
  await expect(page).toHaveURL(/unrelated=keep.*buyerView=decide/);
  await expect(page.getByRole("heading", { name: "Decide what needs action" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Forecast Table" })).toHaveCount(0);
  await expect(page.getByText("Urgent flower", { exact: true })).toHaveCount(2);
  await page.getByText("Forecast controls and buyer filters", { exact: true }).click();
  await page.getByLabel("Target Days on Hand", { exact: true }).fill("30");
  await page.getByLabel("Search (SKU / Product / Brand)", { exact: false }).fill("Urgent");
  await page.getByRole("button", { name: "Act on these decisions" }).click();
  await expect(page.getByRole("heading", { name: "Purchasing actions" })).toBeVisible();
  await page.getByRole("button", { name: "Run Doobie Inventory Check" }).click();
  await expect(page.getByText("inventory-check completed", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Generate Doobie Buyer Brief" }).click();
  await expect(page.getByText("buyer-brief completed", { exact: true })).toBeVisible();
  expect(writes).toHaveLength(2);
  expect(writes[0]).toMatchObject({ target_doh: 30, search: "Urgent", on_hand_only: true });
  await page.getByRole("tab", { name: "Analyze", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Forecast Table" })).toBeVisible();
  await expect(page.getByLabel("Target Days on Hand", { exact: true })).toHaveValue("30");
  await expect(page.getByRole("button", { name: "Export SKU inventory (Excel)" })).toBeVisible();
  await page.getByRole("tab", { name: "Act", exact: true }).click();
  await expect(page.getByText("buyer-brief completed", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.getByRole("button", { name: "Open Purchase Orders" }).click();
  await expect(page).toHaveURL(/purchase-orders/);
});
