import { expect, test } from "@playwright/test";

const sourceTag = "1A4000000000000000007001";
const finishedTag = "1A4000000000000000007999";

const account = {
  user: { display_name: "Packaging Operator", email: "operator@example.test", role: "operator", must_change_password: false },
  organization: { id: "org-label-run", name: "Cowboy Kush", slug: "cowboy-kush" },
  facility_id: "facility-label-run",
  capabilities: { retail: true, production: true, cultivation: false, commercial: true },
  facilities: [{ id: "facility-label-run", name: "Cowboy Kush Manufacturing", code: "CK-MFG", license_type: "Manufacturing", capabilities: { retail: true, production: true, cultivation: false, commercial: true } }],
};
const accessOptions = { organizations: [{ id: account.organization.id, name: account.organization.name, slug: account.organization.slug, facilities: account.facilities }], organization_id: account.organization.id, facility_id: account.facility_id };
const summary = { lot_id: "lot-gmo", product_id: "bulk-gmo", package_id: sourceTag, lot_code: "GMO-BULK-01", product_name: "GMO Bulk Flower", sku: "GMO-BULK", location: "BULK", status: "available", on_hand: 4000, inventory_unit: "g" };
const source = {
  ...summary,
  label: { product_name: "GMO Bulk Flower", strain: "GMO", total_thc: "29.4%", total_cbd: "0.1%", total_terpenes: "3.2%", laboratory: "Test Lab", lab_license_number: "IL281234", test_date: "2026-08-30", coa_reference: "GMO-COA-1", batch_number: "GMO-H-01", package_id: sourceTag },
  coa: { available: true, needs_confirmation: false, document_id: "coa-gmo", filename: "gmo.pdf", lab_name: "Test Lab", lab_license_number: "IL281234", date_tested: "2026-08-30", overall_status: "pass", total_thc: 29.4, total_cbd: 0.1, total_cannabinoids: 31.1, total_terpenes: 3.2, results: [] },
  source_summary: { facility: "Cowboy Kush Manufacturing", license_number: "MP281234", license_type: "Manufacturing", qa_source: "coa", coa_source: "coa_library", coa_verification: "matched" },
};
const finishedProduct = { id: "product-gmo-28", sku: "GMO-PR-28", name: "GMO 28-Count Pre-Roll Multipack", item_type: "finished_good", base_unit: "unit", active: true, brand: "Cowboy Kush", category: "Pre-Rolls", product_format: "Pre-Rolls" };
const productDetail = { product: finishedProduct, profile: { brand: "Cowboy Kush", category: "Pre-Rolls", subcategory: "Multipack", strain: "GMO", manufacturer: "Cowboy Kush Manufacturing", product_format: "Pre-Rolls", production_enabled: true }, packaging: { net_content: 28, net_content_unit: "g", units_per_package: 28, sellable_unit: "each", case_pack: 0, warning_text: "Required package warning" } };

function run(status: "validated" | "tagged") {
  const tag = status === "tagged" ? finishedTag : "";
  return {
    id: "run-gmo-24", product_id: finishedProduct.id, quantity: 24, expected_material_quantity: 672, expected_material_unit: "g", status, metrc_package_tag: tag, created_by: "operator@example.test", printed_by: "", created_at: "2026-09-03T17:00:00Z", printed_at: null,
    snapshot: {
      source: { lot_id: summary.lot_id, package_id: sourceTag, lot_code: summary.lot_code, product_name: summary.product_name, coa: source.coa },
      product: { id: finishedProduct.id, name: finishedProduct.name, sku: finishedProduct.sku, packaging: productDetail.packaging },
      label: { product_name: finishedProduct.name, brand: "Cowboy Kush", strain: "GMO", product_type: "Pre-Rolls", package_size: "28 g", net_contents: "NET WT. .98767 OZ", package_composition: "28 x 1g Pre-Rolls", total_thc: "29.4%", total_cbd: "0.1%", total_terpenes: "3.2%", laboratory: "Test Lab", lab_license_number: "IL281234", test_date: "2026-08-30", coa_reference: "GMO-COA-1", batch_number: "GMO-H-01", warning_text: "Required package warning", package_id: tag },
      quantity: 24, expected_material_quantity: 672, expected_material_unit: "g",
    },
    traceability: { value: tag, qr: { value: tag, svg: tag ? '<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>' : "" }, barcode: { value: tag, format: "Code128", svg: tag ? '<svg xmlns="http://www.w3.org/2000/svg"><rect width="20" height="10"/></svg>' : "" } },
    events: [{ id: "event-create", event_type: "created", from_status: "", to_status: "draft", actor: "operator@example.test", details: {}, occurred_at: "2026-09-03T17:00:00Z" }, { id: "event-validate", event_type: "validated", from_status: "draft", to_status: "validated", actor: "operator@example.test", details: {}, occurred_at: "2026-09-03T17:00:01Z" }],
  };
}

test("operator builds 24 retail labels under one finished METRC package tag", async ({ page }) => {
  let createPayload: Record<string, unknown> | null = null;
  let tagPayload: Record<string, unknown> | null = null;

  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    let body: unknown = {};
    if (path === "/api/v1/account/context") body = account;
    else if (path === "/api/v1/account/access-options") body = accessOptions;
    else if (path === "/api/v1/label-printing/inventory-sources" && url.searchParams.get("summary") === "true") body = [summary];
    else if (path === "/api/v1/label-printing/inventory-sources/lot-gmo") body = source;
    else if (path === "/api/v1/product-master" && url.searchParams.get("item_type") === "finished_good") body = [finishedProduct];
    else if (path === "/api/v1/product-master/product-gmo-28") body = productDetail;
    else if (path === "/api/v1/label-printing/production-runs" && request.method() === "POST") { createPayload = request.postDataJSON() as Record<string, unknown>; body = run("validated"); }
    else if (path === "/api/v1/label-printing/production-runs/run-gmo-24/tag" && request.method() === "POST") { tagPayload = request.postDataJSON() as Record<string, unknown>; body = run("tagged"); }
    else if (path === "/api/v1/control-tower/label-templates") body = [];
    else if (path === "/api/v1/search") body = { results: [] };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });

  await page.addInitScript(() => {
    localStorage.setItem("buyer-dash-organization", "org-label-run");
    localStorage.setItem("buyer-dash-facility", "facility-label-run");
    localStorage.setItem("buyer-dash-operation", "Production Ops");
    localStorage.setItem("buyer-dash-data-mode", "Uploads");
    sessionStorage.setItem("buyer-dash-pending-page", "Label Studio");
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByLabel("Source batch").selectOption("lot-gmo");
  await expect(page.getByText("✓ Verified source")).toBeVisible();
  await page.getByLabel("End product").selectOption("product-gmo-28");
  await page.getByLabel("Finished quantity").fill("24");
  await expect(page.getByText("24 finished packages = 672 g theoretical material before loss/waste")).toBeVisible();

  await page.getByRole("button", { name: "4. Build & validate label preview" }).click();
  await expect(page.getByText("GMO 28-Count Pre-Roll Multipack", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("28 x 1g Pre-Rolls", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("672 g", { exact: true }).first()).toBeVisible();
  expect(createPayload).toEqual({ source_lot_id: "lot-gmo", product_id: "product-gmo-28", quantity: 24 });

  await page.getByLabel("METRC finished package tag").fill(finishedTag);
  await page.getByRole("button", { name: "Assign tag" }).click();
  expect(tagPayload).toEqual({ metrc_package_tag: finishedTag });
  await expect(page.getByAltText(`QR code for finished METRC package ${finishedTag}`)).toBeVisible();
  await expect(page.getByAltText(`Code 128 barcode for finished METRC package ${finishedTag}`)).toBeVisible();
  await expect(page.getByRole("button", { name: "6. Finalize & print 24 labels" })).toBeVisible();
  await expect(page.getByText("Retail unit 1 of 24", { exact: true })).toBeVisible();
});
