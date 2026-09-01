import { expect, test } from "@playwright/test";

const account = {
  user: { display_name: "Label Operator", email: "label@example.com", role: "dev", must_change_password: false },
  organization: { id: "org-label", name: "Label Cannabis", slug: "label-cannabis" },
  facility_id: "facility-label",
  capabilities: { retail: true, production: true, cultivation: true, commercial: true },
  facilities: [{ id: "facility-label", name: "Label Manufacturing", code: "LABEL-MFG", license_type: "Manufacturing", capabilities: { retail: true, production: true, cultivation: true, commercial: true } }],
};

const accessOptions = {
  organizations: [{ id: "org-label", name: "Label Cannabis", slug: "label-cannabis", facilities: account.facilities }],
  organization_id: "org-label",
  facility_id: "facility-label",
};

const template = {
  id: "template-ma",
  name: "MA Manufacturing Label",
  version: 3,
  jurisdiction: "Massachusetts",
  license_scope: "Manufacturing",
  status: "active",
  layout: { fields: ["product_name", "net_contents", "license_number", "package_id", "batch_number", "warning_text"] },
  rules: [],
};

const currentTag = "1A4000000000000000001111";
const splitChildTag = "1A4000000000000000003333";
const qrSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="white"/><rect x="1" y="1" width="3" height="3" fill="black"/><rect x="6" y="1" width="3" height="3" fill="black"/><rect x="1" y="6" width="3" height="3" fill="black"/></svg>';

const matchedCoa = {
  available: true,
  lookup_key: currentTag,
  fallback_allowed: false,
  needs_confirmation: false,
  document_id: "coa-1",
  source: "coa_library",
  status: "parsed",
  verification_state: "tag_extracted",
  filename: "CK-0901-A-COA.pdf",
  file_url: "/api/v1/label-printing/coas/coa-1/file",
  lab_name: "Example Cannabis Lab",
  lab_license_number: "IL281000",
  lab_id: "COA-0901-A",
  metrc_source_id: currentTag,
  metrc_lab_id: "1A4000000000000000009999",
  date_tested: "2026-08-30",
  overall_status: "pass",
  total_thc: 28.4,
  total_cbd: 0,
  total_cannabinoids: 31.9,
  total_terpenes: 2.4,
  results: [
    { analysis: "cannabinoids", key: "thca", name: "THCA", value: 31.2, value_text: "31.2", units: "%", mg_g: null, limit: null, lod: null, loq: null, status: "" },
    { analysis: "cannabinoids", key: "delta_9_thc", name: "Delta-9 THC", value: 1.03, value_text: "1.03", units: "%", mg_g: null, limit: null, lod: null, loq: null, status: "" },
    { analysis: "terpenes", key: "beta_myrcene", name: "Beta-Myrcene", value: 0.68, value_text: "0.68", units: "%", mg_g: null, limit: null, lod: null, loq: null, status: "" },
  ],
};

const completeSource = {
  lot_id: "lot-complete",
  product_id: "product-complete",
  package_id: currentTag,
  lot_code: "CK-0901-A",
  product_name: "Copper Kush Flower",
  sku: "CK-FLR-35",
  location: "FINISHED-GOODS",
  status: "available",
  on_hand: 48,
  inventory_unit: "unit",
  label: {
    product_name: "Copper Kush Flower",
    brand: "Cowboy Kush",
    strain: "Copper Kush",
    product_type: "Flower",
    package_size: "3.5 g",
    net_contents: "NET WT. .12345 OZ",
    license_number: "MP281999",
    facility_name: "Label Manufacturing",
    package_id: currentTag,
    batch_number: "CK-0901-A",
    potency: "THCA 31.2% · Total THC 28.4% · TAC 31.9% · Total terpenes 2.4%",
    total_thc: "28.4%",
    total_cbd: "0%",
    total_cannabinoids: "31.9%",
    total_terpenes: "2.4%",
    lab_testing_state: "Passed",
    laboratory: "Example Cannabis Lab",
    test_date: "2026-08-30",
    coa_reference: "COA-0901-A",
    coa_url: "/api/v1/label-printing/coas/coa-1/file",
    ingredients: "Cannabis flower",
    allergens: "None declared",
    manufacture_date: "",
    package_date: "2026-09-01",
    expiration_date: "2027-08-30",
    warning_text: "Approved warning language",
  },
  coa: matchedCoa,
  qr: { value: currentTag, svg: qrSvg },
  raw_text: `Copper Kush Flower\n3.5 g\nNET WT. .12345 OZ\nMP281999\n${currentTag}\nCK-0901-A\nApproved warning language`,
  source_summary: { facility: "Label Manufacturing", license_number: "MP281999", license_type: "Manufacturing", qa_source: "coa:coa_library", coa_source: "coa_library", coa_verification: "tag_extracted" },
};

const inheritedSource = {
  ...completeSource,
  lot_id: "lot-inherited",
  product_id: "product-inherited",
  package_id: splitChildTag,
  lot_code: "CK-0901-SPLIT",
  on_hand: 12,
  label: {
    ...completeSource.label,
    package_id: splitChildTag,
    batch_number: "CK-0901-SPLIT",
  },
  coa: { ...matchedCoa, lookup_key: splitChildTag, metrc_source_id: currentTag },
  qr: { value: splitChildTag, svg: qrSvg },
  raw_text: `Copper Kush Flower\n3.5 g\nNET WT. .12345 OZ\nMP281999\n${splitChildTag}\nCK-0901-SPLIT\nApproved warning language`,
  source_summary: { ...completeSource.source_summary, qa_source: "inherited:pack_down" },
};

const incompleteSource = {
  ...completeSource,
  lot_id: "lot-incomplete",
  product_id: "product-incomplete",
  package_id: "",
  lot_code: "BULK-0901-B",
  product_name: "Bulk Copper Kush Flower",
  label: {
    ...completeSource.label,
    product_name: "Bulk Copper Kush Flower",
    package_size: "",
    net_contents: "",
    package_id: "",
    batch_number: "BULK-0901-B",
  },
  coa: { ...matchedCoa, available: false, lookup_key: "", fallback_allowed: false, document_id: "", source: "", status: "missing", verification_state: "missing", filename: "", file_url: "", results: [] },
  qr: { value: "", svg: "" },
};

test("selecting inventory builds a current-tag QR label and follows COA lineage", async ({ page }) => {
  let reviewPayload: Record<string, unknown> | null = null;
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let body: unknown = {};
    if (path === "/api/v1/account/context") body = account;
    else if (path === "/api/v1/account/access-options") body = accessOptions;
    else if (path === "/api/v1/control-tower/label-templates") body = [template];
    else if (path === "/api/v1/label-printing/inventory-sources") body = [completeSource, inheritedSource, incompleteSource];
    else if (path === "/api/v1/control-tower/label-reviews" && request.method() === "POST") {
      reviewPayload = request.postDataJSON() as Record<string, unknown>;
      body = { id: "review-1", status: "pass", reviewed_at: "2026-09-01T12:00:00Z", findings: [], disclaimer: "Reviewed" };
    } else if (path === "/api/v1/search") body = { results: [] };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });

  await page.addInitScript(() => {
    localStorage.setItem("buyer-dash-organization", "org-label");
    localStorage.setItem("buyer-dash-facility", "facility-label");
    localStorage.setItem("buyer-dash-operation", "Production Ops");
    localStorage.setItem("buyer-dash-data-mode", "Uploads");
    sessionStorage.setItem("buyer-dash-pending-page", "Label Studio");
  });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("heading", { name: "Label Studio + LabelGuard" })).toBeVisible();
  const batchSelect = page.getByLabel("Inventory batch");
  await batchSelect.selectOption("lot-complete");

  await expect(page.getByText(/label fields populated from inventory/)).toBeVisible();
  await expect(page.getByText("All fields required by the current rule set are populated.")).toBeVisible();
  await expect(page.getByText("COA matched to the current METRC package tag.")).toBeVisible();
  await expect(page.getByRole("cell", { name: "THCA" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "31.2 %" })).toBeVisible();
  await expect(page.getByText(/Fallback: upload the COA/)).toHaveCount(0);
  await expect(page.getByAltText(`QR code for METRC package ${currentTag}`)).toBeVisible();

  const reviewSection = page.locator("section.inventory-panel").filter({ hasText: "Pre-release review" });
  await expect(reviewSection.getByLabel("Product identity")).toHaveValue("Copper Kush Flower");
  await expect(reviewSection.getByLabel("Package size")).toHaveValue("3.5 g");
  await expect(reviewSection.getByLabel("Net contents")).toHaveValue("NET WT. .12345 OZ");
  await expect(reviewSection.getByLabel("Package / traceability ID")).toHaveValue(currentTag);
  await expect(reviewSection.getByLabel("Package / traceability ID")).toHaveJSProperty("readOnly", true);
  await expect(reviewSection.getByLabel("Expiration / best-by")).toHaveValue("2027-08-30");
  await expect(reviewSection.getByLabel("Potency statement")).toHaveValue("THCA 31.2% · Total THC 28.4% · TAC 31.9% · Total terpenes 2.4%");

  await page.getByRole("button", { name: "Run LabelGuard" }).click();
  await expect(page.getByRole("heading", { name: "PASS" })).toBeVisible();
  expect(reviewPayload).not.toBeNull();
  expect(reviewPayload?.product_id).toBe("product-complete");
  expect(reviewPayload?.package_id).toBe(currentTag);
  expect((reviewPayload?.label as Record<string, string>).package_id).toBe(currentTag);
  expect((reviewPayload?.label as Record<string, string>).batch_number).toBe("CK-0901-A");
  await expect(page.getByRole("button", { name: "Print reviewed label" })).toBeEnabled();

  await batchSelect.selectOption("lot-inherited");
  await expect(page.getByText("COA inherited through package lineage.")).toBeVisible();
  await expect(page.getByText(new RegExp(`Current package ${splitChildTag}`))).toBeVisible();
  await expect(page.getByAltText(`QR code for METRC package ${splitChildTag}`)).toBeVisible();
  await expect(reviewSection.getByLabel("Package / traceability ID")).toHaveValue(splitChildTag);
  await expect(page.getByRole("button", { name: "Print reviewed label" })).toBeDisabled();

  await batchSelect.selectOption("lot-incomplete");
  const missingBanner = page.getByText(/Required information still missing:/);
  await expect(missingBanner).toContainText("Net contents");
  await expect(missingBanner).toContainText("Package / traceability ID");
  await expect(page.getByText("No METRC package/tag is stored on this inventory lot.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Run LabelGuard" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Print reviewed label" })).toBeDisabled();
});
