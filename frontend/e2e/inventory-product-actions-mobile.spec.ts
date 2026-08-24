import { expect, test, type Page } from "@playwright/test";

const accountContext = {
  user: { display_name: "Mobile Operator", email: "mobile@doobielogic.io", role: "dev", must_change_password: false },
  organization: { id: "org-mobile", name: "Mobile Cannabis", slug: "mobile-cannabis" },
  facility_id: "facility-mobile",
  capabilities: { retail: true, production: true, cultivation: false, commercial: true },
  facilities: [{ id: "facility-mobile", name: "Mobile Facility", code: "MOBILE", license_type: "Retail", capabilities: { retail: true, production: true, cultivation: false, commercial: true } }],
};

const accessOptions = {
  organizations: [{ id: "org-mobile", name: "Mobile Cannabis", slug: "mobile-cannabis", facilities: accountContext.facilities }],
  organization_id: "org-mobile",
  facility_id: "facility-mobile",
};

const retailInventory = {
  operation: "retail",
  grain: "packages",
  items: [
    { id: "lot-copper-a", package_id: "1A4-MOBILE-0001", lot_code: "COPPER-A", product_id: "prod-copper", sku: "FLOW-001", product_name: "Copper Kush Whole Flower 3.5g", material_type: "Flower", location: "Vault A", status: "Available", source_name: "Mobile Gardens", available: 8, reserved: 0, usable: 8, unit: "unit", received_at: "2026-08-01T12:00:00Z", expiration_at: "2026-10-01T12:00:00Z", attention: "", sold_30d: 20, daily_velocity: 0.67, days_on_hand: 12, unit_cost: 11, retail_price: 30, margin_pct: 63.3, age_days: 23, days_to_expiry: 38 },
    { id: "lot-copper-b", package_id: "1A4-MOBILE-0002", lot_code: "COPPER-B", product_id: "prod-copper", sku: "FLOW-001", product_name: "Copper Kush Whole Flower 3.5g", material_type: "Flower", location: "Vault B", status: "Available", source_name: "Mobile Gardens", available: 10, reserved: 0, usable: 10, unit: "unit", received_at: "2026-08-03T12:00:00Z", expiration_at: "2026-10-03T12:00:00Z", attention: "", sold_30d: 20, daily_velocity: 0.67, days_on_hand: 15, unit_cost: 11, retail_price: 30, margin_pct: 63.3, age_days: 21, days_to_expiry: 40 },
    { id: "lot-night", package_id: "1A4-MOBILE-0003", lot_code: "NIGHT-A", product_id: "prod-night", sku: "PRE-001", product_name: "Night Shift Pre-Roll 1g", material_type: "Pre-Roll", location: "Vault A", status: "Available", source_name: "Mobile Gardens", available: 24, reserved: 0, usable: 24, unit: "unit", received_at: "2026-08-04T12:00:00Z", expiration_at: "2026-11-01T12:00:00Z", attention: "", sold_30d: 10, daily_velocity: 0.33, days_on_hand: 72, unit_cost: 2.5, retail_price: 8, margin_pct: 68.8, age_days: 20, days_to_expiry: 69 },
  ],
  facets: { statuses: ["Available"], material_types: ["Flower", "Pre-Roll"], locations: ["Vault A", "Vault B"], sources: ["Mobile Gardens"] },
  summary: { package_count: 3, available_quantity: 42, reserved_quantity: 0, hold_count: 0, low_balance_count: 0 },
};

const packageStudioWorkspace = {
  lots: [
    { lot_id: "lot-copper-a", lot_code: "COPPER-A", compliance_package_id: "1A4-MOBILE-0001", product_id: "prod-copper", product_name: "Copper Kush Whole Flower 3.5g", sku: "FLOW-001", balance: 8, unit: "unit", location_code: "Vault A" },
    { lot_id: "lot-copper-b", lot_code: "COPPER-B", compliance_package_id: "1A4-MOBILE-0002", product_id: "prod-copper", product_name: "Copper Kush Whole Flower 3.5g", sku: "FLOW-001", balance: 10, unit: "unit", location_code: "Vault B" },
  ],
  products: [{ product_id: "prod-copper", name: "Copper Kush Whole Flower 3.5g", sku: "FLOW-001", item_type: "Flower", base_unit: "unit" }],
  runs: [],
  can_commit: true,
};

async function installApiMocks(page: Page) {
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (path === "/api/v1/account/context") body = accountContext;
    else if (path === "/api/v1/account/access-options") body = accessOptions;
    else if (path === "/api/v1/inventory/retail/packages") body = retailInventory;
    else if (path === "/api/v1/package-studio/workspace") body = packageStudioWorkspace;
    else if (path === "/api/v1/inventory/retail/adjustment-reasons") body = { reasons: [{ name: "Physical count correction", requires_note: false }], metrc_ready: false, can_bypass: false, license_number: "" };
    else if (path === "/api/v1/search") body = { results: [] };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
}

async function assertNoOverflow(page: Page) {
  const { width, scrollWidth } = await page.evaluate(() => ({ width: window.innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  expect(scrollWidth).toBeLessThanOrEqual(width + 1);
}

for (const width of [390, 430]) {
  test(`product-level package actions are usable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await installApiMocks(page);
    await page.addInitScript(() => {
      localStorage.setItem("buyer-dash-theme", "dark");
      localStorage.setItem("buyer-dash-organization", "org-mobile");
      localStorage.setItem("buyer-dash-facility", "facility-mobile");
      localStorage.setItem("buyer-dash-operation", "Retail Ops");
      localStorage.setItem("buyer-dash-data-mode", "Uploads");
      sessionStorage.setItem("buyer-dash-pending-page", "Inventory");
    });
    await page.goto("/", { waitUntil: "networkidle" });

    await expect(page.getByRole("heading", { name: "Inventory" })).toBeVisible();
    await page.getByRole("checkbox", { name: "Select Copper Kush Whole Flower 3.5g" }).check();

    const work = page.getByRole("button", { name: "Work on package" });
    const labels = page.getByRole("button", { name: "Print labels" });
    const adjust = page.getByRole("button", { name: "Adjust", exact: true });
    await expect(work).toBeEnabled();
    await expect(labels).toBeEnabled();
    await expect(adjust).toBeEnabled();

    await work.click();
    const workChooser = page.getByRole("dialog", { name: "Choose package to work on" });
    await expect(workChooser).toBeVisible();
    await workChooser.getByRole("button", { name: /1A4-MOBILE-0001/ }).click();
    const studio = page.getByRole("dialog", { name: "Package Studio" });
    await expect(studio).toBeVisible();
    await expect(studio.getByText("Copper Kush Whole Flower 3.5g · 1A4-MOBILE-0001", { exact: true })).toBeVisible();
    await assertNoOverflow(page);
    await studio.getByRole("button", { name: "Close" }).click();

    await labels.click();
    const labelDialog = page.getByRole("dialog", { name: "Print inventory labels" });
    await expect(labelDialog).toBeVisible();
    await expect(labelDialog.getByText("1A4-MOBILE-0001", { exact: true })).toBeVisible();
    await expect(labelDialog.getByText("1A4-MOBILE-0002", { exact: true })).toBeVisible();
    await assertNoOverflow(page);
    await labelDialog.getByRole("button", { name: "Close" }).click();

    await adjust.click();
    const adjustChooser = page.getByRole("dialog", { name: "Choose package to adjust" });
    await expect(adjustChooser).toBeVisible();
    await adjustChooser.getByRole("button", { name: /1A4-MOBILE-0002/ }).click();
    const adjustDialog = page.getByRole("dialog", { name: "Adjust inventory" });
    await expect(adjustDialog).toBeVisible();
    await expect(adjustDialog.getByLabel("Package *")).toHaveValue("lot-copper-b");
    await assertNoOverflow(page);
  });
}
