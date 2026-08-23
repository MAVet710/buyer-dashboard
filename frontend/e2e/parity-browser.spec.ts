import { expect, test, type Page, type TestInfo } from "@playwright/test";

const WIDTHS = [390, 430, 768, 1024, 1440] as const;
const HEIGHT = 900;

const accountContext = {
  user: { display_name: "Parity Operator", email: "parity@doobielogic.io", role: "dev", must_change_password: false },
  organization: { id: "org-parity", name: "Parity Cannabis", slug: "parity-cannabis" },
  facility_id: "facility-parity",
  capabilities: { retail: true, production: true, cultivation: true, commercial: true },
  facilities: [
    { id: "facility-parity", name: "Parity Integrated Facility", code: "PARITY-01", license_type: "Integrated", capabilities: { retail: true, production: true, cultivation: true, commercial: true } },
  ],
};

const accessOptions = {
  organizations: [{ id: "org-parity", name: "Parity Cannabis", slug: "parity-cannabis", facilities: accountContext.facilities }],
  organization_id: "org-parity",
  facility_id: "facility-parity",
};

const forecastRows = [
  { top_products: "Copper Kush 3.5g", mastercategory: "Flower", subcategory: "Flower", strain_type: "Hybrid", packagesize: "3.5g", onhandunits: 18, unitssold: 84, avgunitsperday: 2.8, daysonhand: 6.4, reorderqty: 41, reorderpriority: "1 – Reorder ASAP", product_count: 2 },
  { top_products: "Night Shift 1g", mastercategory: "Pre-Rolls", subcategory: "Pre-Rolls", strain_type: "Indica", packagesize: "1g", onhandunits: 96, unitssold: 72, avgunitsperday: 2.4, daysonhand: 40, reorderqty: 0, reorderpriority: "3 – Healthy", product_count: 1 },
];

const skuRows = [
  { sku: "FLOW-001", product_name: "Copper Kush Whole Flower 3.5g", brand_vendor: "Parity Gardens", category: "Flower", onhandunits: 18, avg_weekly_sales: 19.6, days_of_supply: 6.4, weeks_of_supply: 0.9, dollars_on_hand: 198, retail_dollars_on_hand: 540, expiration_date: "2026-09-18", days_to_expire: 26, status: "Reorder" },
  { sku: "PRE-001", product_name: "Night Shift Pre-Roll 1g", brand_vendor: "Parity Gardens", category: "Pre-Rolls", onhandunits: 96, avg_weekly_sales: 16.8, days_of_supply: 40, weeks_of_supply: 5.7, dollars_on_hand: 240, retail_dollars_on_hand: 768, expiration_date: "2026-11-30", days_to_expire: 99, status: "Healthy" },
  { sku: "VAPE-001", product_name: "Signal Fire Vape 1g", brand_vendor: "Doobie Labs", category: "Vapes", onhandunits: 140, avg_weekly_sales: 4, days_of_supply: 245, weeks_of_supply: 35, dollars_on_hand: 1260, retail_dollars_on_hand: 4200, expiration_date: "2027-02-01", days_to_expire: 162, status: "Overstock" },
];

const buyerDashboard = {
  controls: { target_doh: 21, velocity_adjustment: 0.5, sales_days: 60, sku_window: 56 },
  summary: { units_sold: 156, reorder_asap: 1, tracked_products: 3, categories: 2 },
  sources: { inventory: { filename: "parity_inventory.xlsx", rows: 3 }, sales: { filename: "parity_sales.xlsx", rows: 156 } },
  category_dos: [],
  forecast: forecastRows,
  product_rows: [
    { product_name: "Copper Kush Whole Flower 3.5g", subcategory: "Flower", strain_type: "Hybrid", packagesize: "3.5g", onhandunits: 18, unitssold: 84, avgunitsperday: 2.8, daysonhand: 6.4 },
    { product_name: "Night Shift Pre-Roll 1g", subcategory: "Pre-Rolls", strain_type: "Indica", packagesize: "1g", onhandunits: 96, unitssold: 72, avgunitsperday: 2.4, daysonhand: 40 },
  ],
  product_rows_total: 2,
  sku_views: { all: skuRows, reorder: [skuRows[0]], overstock: [skuRows[2]], expiring: [skuRows[0]] },
};

const buyerLegacyOverview = {
  sales_trend: [
    { date: "2026-08-17", revenue: 5200, units: 118 },
    { date: "2026-08-18", revenue: 6100, units: 131 },
    { date: "2026-08-19", revenue: 5700, units: 126 },
    { date: "2026-08-20", revenue: 6900, units: 148 },
    { date: "2026-08-21", revenue: 7350, units: 159 },
  ],
  revenue_by_category: [
    { category: "Flower", revenue: 12800, units: 244 },
    { category: "Pre-Rolls", revenue: 8700, units: 318 },
    { category: "Vapes", revenue: 7200, units: 121 },
  ],
  top_slow_movers: [skuRows[2]],
  inventory_health: { score: 76, reorder_skus: 1, at_risk_skus: 1, slow_movers: 1, overstock_skus: 1 },
  inventory_condition: { reorder_count: 1, overstock_count: 1, expiring_count: 1, no_stock_count: 0, overstock_cost_exposure: 1260, expiring_cost_exposure: 198, on_hand_cost: 1698, units_on_hand: 254, units_sold: 156 },
};

const retailInventory = {
  operation: "retail",
  grain: "packages",
  items: [
    { id: "lot-ret-1", package_id: "1A4-RETAIL-0001", lot_code: "RET-LOT-01", product_id: "prod-flower", sku: "FLOW-001", product_name: "Copper Kush Whole Flower 3.5g", material_type: "Flower", location: "Vault A", status: "Available", source_name: "Parity Gardens", available: 18, reserved: 0, usable: 18, unit: "unit", received_at: "2026-08-01T12:00:00Z", expiration_at: "2026-09-18T12:00:00Z", attention: "Reorder now", sold_30d: 84, daily_velocity: 2.8, days_on_hand: 6.4, unit_cost: 11, retail_price: 30, margin_pct: 63.3, age_days: 22, days_to_expiry: 26 },
    { id: "lot-ret-2", package_id: "1A4-RETAIL-0002", lot_code: "RET-LOT-02", product_id: "prod-preroll", sku: "PRE-001", product_name: "Night Shift Pre-Roll 1g", material_type: "Pre-Roll", location: "Vault A", status: "Available", source_name: "Parity Gardens", available: 96, reserved: 4, usable: 92, unit: "unit", received_at: "2026-08-05T12:00:00Z", expiration_at: "2026-11-30T12:00:00Z", attention: "", sold_30d: 72, daily_velocity: 2.4, days_on_hand: 40, unit_cost: 2.5, retail_price: 8, margin_pct: 68.8, age_days: 18, days_to_expiry: 99 },
  ],
  facets: { statuses: ["Available", "Hold"], material_types: ["Flower", "Pre-Roll"], locations: ["Vault A"], sources: ["Parity Gardens"] },
  summary: { package_count: 2, available_quantity: 114, reserved_quantity: 4, hold_count: 0, low_balance_count: 1 },
};

const productionInventory = {
  operation: "production",
  grain: "packages",
  items: [
    { id: "lot-prod-1", package_id: "1A4-PROD-0001", lot_code: "HARV-0821-A", product_id: "prod-bulk-flower", sku: "BULK-FLOW-001", product_name: "Copper Kush Bulk Flower", material_type: "Bulk Flower", location: "Dry Room 2", status: "Available", source_name: "Cultivation", available: 8240.5, reserved: 1200, usable: 7040.5, unit: "g", received_at: "2026-08-21T15:00:00Z", expiration_at: null, attention: "Production ready", sold_30d: 0, daily_velocity: 0, days_on_hand: null, unit_cost: 1.35, retail_price: 0, margin_pct: null, age_days: 2, days_to_expiry: null },
    { id: "lot-prod-2", package_id: "1A4-PROD-0002", lot_code: "TRIM-0819-B", product_id: "prod-trim", sku: "TRIM-001", product_name: "Mixed Trim Extraction Input", material_type: "Biomass / Trim", location: "Extraction Staging", status: "Hold", source_name: "Cultivation", available: 4120, reserved: 0, usable: 0, unit: "g", received_at: "2026-08-19T15:00:00Z", expiration_at: null, attention: "Hold", sold_30d: 0, daily_velocity: 0, days_on_hand: null, unit_cost: 0.55, retail_price: 0, margin_pct: null, age_days: 4, days_to_expiry: null },
  ],
  facets: { statuses: ["Available", "Hold"], material_types: ["Bulk Flower", "Biomass / Trim"], locations: ["Dry Room 2", "Extraction Staging"], sources: ["Cultivation"] },
  summary: { package_count: 2, available_quantity: 12360.5, reserved_quantity: 1200, hold_count: 1, low_balance_count: 0 },
};

const packageStudioWorkspace = {
  lots: [{ lot_id: "lot-ret-1", lot_code: "RET-LOT-01", compliance_package_id: "1A4-RETAIL-0001", product_id: "prod-flower", product_name: "Copper Kush Whole Flower 3.5g", sku: "FLOW-001", balance: 18, unit: "unit", location_code: "Vault A" }],
  products: [
    { product_id: "prod-flower", name: "Copper Kush Whole Flower 3.5g", sku: "FLOW-001", item_type: "Flower", base_unit: "unit" },
    { product_id: "prod-preroll", name: "Copper Kush Pre-Roll 1g", sku: "PRE-COPPER-001", item_type: "Pre-Roll", base_unit: "unit" },
  ],
  runs: [{ id: "run-1", run_number: "PS-2026-0001", action_type: "breakdown", status: "committed", source_quantity: 5, source_unit: "unit", loss_quantity: 0, external_sync_status: "Not requested", created_by: "Parity Operator", committed_at: "2026-08-22T12:00:00Z" }],
  can_commit: true,
};

async function installApiMocks(page: Page) {
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let body: unknown = {};
    if (path === "/api/v1/account/context") body = accountContext;
    else if (path === "/api/v1/account/access-options") body = accessOptions;
    else if (path === "/api/v1/buyer-parity/dashboard") body = buyerDashboard;
    else if (path === "/api/v1/buyer-parity/legacy-overview") body = buyerLegacyOverview;
    else if (path === "/api/v1/inventory/retail/packages") body = retailInventory;
    else if (path === "/api/v1/inventory/production/packages") body = productionInventory;
    else if (path === "/api/v1/package-studio/workspace") body = packageStudioWorkspace;
    else if (path === "/api/v1/package-studio/preview") body = { action_type: "breakdown", total_input: 1, total_output_source_equivalent: 1, loss_quantity: 0, source_unit: "unit", balanced: true, difference: 0, output_count: 2 };
    else if (path === "/api/v1/search") body = { results: [] };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
}

async function setPage(page: Page, pageName: string, operation: "Retail Ops" | "Production Ops") {
  await page.evaluate(({ pageName, operation }) => {
    localStorage.setItem("buyer-dash-theme", "dark");
    localStorage.setItem("buyer-dash-organization", "org-parity");
    localStorage.setItem("buyer-dash-facility", "facility-parity");
    localStorage.setItem("buyer-dash-operation", operation);
    localStorage.setItem("buyer-dash-data-mode", "Uploads");
    sessionStorage.setItem("buyer-dash-pending-page", pageName);
  }, { pageName, operation });
  await page.reload({ waitUntil: "networkidle" });
}

async function assertNoDocumentOverflow(page: Page) {
  const result = await page.evaluate(() => {
    const root = document.documentElement;
    return { innerWidth: window.innerWidth, scrollWidth: root.scrollWidth };
  });
  expect(result.scrollWidth, `document overflowed: ${result.scrollWidth}px > ${result.innerWidth}px`).toBeLessThanOrEqual(result.innerWidth + 1);
}

async function saveEvidence(page: Page, testInfo: TestInfo, label: string) {
  await page.screenshot({ path: testInfo.outputPath(`${label}.png`), fullPage: true, animations: "disabled" });
}

for (const width of WIDTHS) {
  test(`real-browser parity matrix at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: HEIGHT });
    await installApiMocks(page);
    const pageErrors: string[] = [];
    page.on("pageerror", error => pageErrors.push(error.message));

    await page.addInitScript(() => {
      localStorage.setItem("buyer-dash-theme", "dark");
      localStorage.setItem("buyer-dash-organization", "org-parity");
      localStorage.setItem("buyer-dash-facility", "facility-parity");
      localStorage.setItem("buyer-dash-data-mode", "Uploads");
      if (!localStorage.getItem("buyer-dash-operation")) localStorage.setItem("buyer-dash-operation", "Retail Ops");
      if (!sessionStorage.getItem("buyer-dash-pending-page")) sessionStorage.setItem("buyer-dash-pending-page", "Buyer Operations");
    });
    await page.goto("/", { waitUntil: "networkidle" });

    // Operator-recorded Buyer command center: keep the recovered evidence in one continuous surface.
    await expect(page.getByRole("heading", { name: "Buyer Dashboard" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Sales Trend" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Revenue by Category" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Top Slow Movers" })).toBeVisible();
    await expect(page.getByText("Inventory Health", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Forecast Table" })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Buyer Filters & Settings/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "Generate Doobie Buyer Brief" })).toBeVisible();
    await assertNoDocumentOverflow(page);
    await saveEvidence(page, testInfo, `buyer-${width}`);

    // White Label / Repack: exercise every Streamlit tab and ensure no viewport leakage.
    await setPage(page, "White Label / Repack", "Production Ops");
    await expect(page.getByRole("heading", { name: "White Label / Repack" })).toBeVisible();
    for (const tab of ["Step 1: Bulk Lot", "Step 2: Costs", "Step 3: Package Plan", "Step 4: Results", "Step 5: Compliance"]) {
      await page.getByRole("button", { name: tab }).click();
      await assertNoDocumentOverflow(page);
    }
    await page.getByRole("button", { name: "Step 1: Bulk Lot" }).click();
    await saveEvidence(page, testInfo, `white-label-${width}`);

    // Package Studio must be a Streamlit-style work window from Inventory.
    await setPage(page, "Inventory", "Retail Ops");
    await expect(page.getByRole("heading", { name: "Inventory" })).toBeVisible();
    await page.getByRole("button", { name: "Actions" }).click();
    await page.getByRole("button", { name: "Package Studio" }).click();
    const dialog = page.getByRole("dialog", { name: "Package Studio" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "Package transformation" })).toBeVisible();
    const box = await dialog.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      if (width <= 900) {
        expect(Math.abs(box.x)).toBeLessThanOrEqual(1);
        expect(Math.abs(box.width - width)).toBeLessThanOrEqual(2);
      } else {
        expect(box.width).toBeLessThanOrEqual(572);
        expect(Math.abs((box.x + box.width) - width)).toBeLessThanOrEqual(2);
      }
    }
    await assertNoDocumentOverflow(page);
    await saveEvidence(page, testInfo, `package-studio-drawer-${width}`);
    await dialog.getByRole("button", { name: "Close" }).click();

    // Production inventory is a separate bulk/cultivation surface, never retail DOS inventory in disguise.
    await setPage(page, "Production Inventory", "Production Ops");
    await expect(page.getByRole("heading", { name: "Inventory" })).toBeVisible();
    await expect(page.getByText("Bulk cannabis materials, lots, rooms, receiving, transformations, and audits.")).toBeVisible();
    await expect(page.getByText("Copper Kush Bulk Flower")).toBeVisible();
    await expect(page.getByText("Mixed Trim Extraction Input")).toBeVisible();
    await assertNoDocumentOverflow(page);
    await saveEvidence(page, testInfo, `production-inventory-${width}`);

    expect(pageErrors, `uncaught browser errors: ${pageErrors.join(" | ")}`).toEqual([]);
  });
}
