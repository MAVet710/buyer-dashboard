import { expect, test } from "@playwright/test";

const packageTag = "1A4000000000000000008123";

const account = {
  user: { display_name: "Label QA", email: "qa@example.test", role: "qa", must_change_password: false },
  organization: { id: "org-integrity", name: "Integrity Cannabis", slug: "integrity-cannabis" },
  facility_id: "facility-integrity",
  capabilities: { retail: true, production: true, cultivation: true, commercial: true },
  facilities: [{
    id: "facility-integrity",
    name: "Integrity Manufacturing",
    code: "INT-MFG",
    license_type: "Manufacturing",
    capabilities: { retail: true, production: true, cultivation: true, commercial: true },
  }],
};

const accessOptions = {
  organizations: [{ id: account.organization.id, name: account.organization.name, slug: account.organization.slug, facilities: account.facilities }],
  organization_id: account.organization.id,
  facility_id: account.facility_id,
};

const template = {
  id: "template-integrity",
  name: "Verified Testing Label",
  version: 1,
  jurisdiction: "Massachusetts",
  license_scope: "Manufacturing",
  status: "active",
  layout: {
    fields: [
      "product_name", "brand", "strain", "product_type", "package_size", "net_contents",
      "license_number", "facility_name", "package_id", "batch_number", "serial_number",
      "potency", "total_thc", "total_cbd", "total_cannabinoids", "total_terpenes",
      "lab_testing_state", "laboratory", "lab_license_number", "test_date", "coa_reference",
      "harvest_date", "package_date", "expiration_date", "cultivated_by", "cultivator_license",
      "packaged_by", "packager_license", "sold_by", "seller_license",
    ],
  },
  rules: [],
};

const summary = {
  lot_id: "lot-integrity",
  product_id: "product-integrity",
  package_id: packageTag,
  lot_code: "IK-FG-001",
  product_name: "Integrity Kush Flower",
  sku: "IK-FLR-35",
  location: "FINISHED-GOODS",
  status: "available",
  on_hand: 24,
  inventory_unit: "unit",
};

const source = {
  ...summary,
  label: {
    product_name: "Integrity Kush Flower",
    brand: "Integrity Reserve",
    strain: "Integrity Kush",
    product_type: "Flower",
    package_size: "3.5 g",
    net_contents: "NET WT. .12345 OZ",
    package_composition: "",
    license_number: "MP281234",
    facility_name: "Integrity Manufacturing",
    manufacturer: "Integrity Manufacturing",
    package_id: packageTag,
    batch_number: "IK-2026-08",
    serial_number: "INT-001",
    potency: "THCA 30.1% · Total THC 26.84% · TAC 31.2% · Total terpenes 2.75%",
    total_thc: "26.84%",
    total_cbd: "0.12%",
    total_cannabinoids: "31.2%",
    total_terpenes: "2.75%",
    lab_testing_state: "Passed",
    laboratory: "Integrity Cannabis Lab",
    lab_license_number: "IL281234",
    test_date: "2026-08-30",
    coa_reference: "COA-INTEGRITY-1",
    ingredients: "Cannabis flower",
    allergens: "None declared",
    harvest_date: "2026-06-08",
    manufacture_date: "",
    package_date: "2026-08-31",
    expiration_date: "2027-08-30",
    cultivated_by: "Integrity Cultivation",
    cultivator_license: "MC281111",
    cultivator_contact: "New Bedford, MA",
    packaged_by: "Integrity Manufacturing",
    packager_license: "MP281234",
    packager_contact: "New Bedford, MA",
    sold_by: "Integrity Retail",
    seller_license: "MR281222",
    seller_contact: "New Bedford, MA",
    warning_text: "",
    universal_symbol: "",
    qr_value: packageTag,
  },
  coa: {
    available: true,
    lookup_key: packageTag,
    fallback_allowed: false,
    needs_confirmation: false,
    document_id: "coa-integrity",
    source: "coa_library",
    status: "parsed",
    verification_state: "matched",
    filename: "integrity-kush-coa.pdf",
    file_url: "/api/v1/label-printing/coas/coa-integrity/file",
    lab_name: "Integrity Cannabis Lab",
    lab_license_number: "IL281234",
    lab_id: "COA-INTEGRITY-1",
    metrc_source_id: packageTag,
    metrc_lab_id: "1A4000000000000000008998",
    date_tested: "2026-08-30",
    overall_status: "pass",
    total_thc: 26.84,
    total_cbd: 0.12,
    total_cannabinoids: 31.2,
    total_terpenes: 2.75,
    results: [
      { analysis: "cannabinoids", key: "thca", name: "THCA", value: 30.1, value_text: "30.1", units: "%", mg_g: null, limit: null, lod: null, loq: null, status: "" },
      { analysis: "terpenes", key: "beta_myrcene", name: "Beta-Myrcene", value: 0.9, value_text: "0.9", units: "%", mg_g: null, limit: null, lod: null, loq: null, status: "" },
    ],
  },
  qr: { value: packageTag, svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>' },
  barcode: { value: packageTag, format: "Code128", svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10"><rect width="20" height="10"/></svg>' },
  raw_text: "Integrity Kush Flower",
  source_summary: {
    facility: "Integrity Manufacturing",
    license_number: "MP281234",
    license_type: "Manufacturing",
    qa_source: "coa:coa_library",
    coa_source: "coa_library",
    coa_verification: "matched",
  },
};

test("selected inventory and COA facts arrive unchanged in pre-release review and LabelGuard", async ({ page }) => {
  let reviewPayload: Record<string, unknown> | null = null;

  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    let body: unknown = {};

    if (path === "/api/v1/account/context") body = account;
    else if (path === "/api/v1/account/access-options") body = accessOptions;
    else if (path === "/api/v1/control-tower/label-templates") body = [template];
    else if (path === "/api/v1/label-printing/inventory-sources" && url.searchParams.get("summary") === "true") body = [summary];
    else if (path === "/api/v1/label-printing/inventory-sources/lot-integrity") body = source;
    else if (path === "/api/v1/control-tower/label-reviews" && request.method() === "POST") {
      reviewPayload = request.postDataJSON() as Record<string, unknown>;
      body = { id: "review-integrity", status: "pass", reviewed_at: "2026-09-03T10:00:00Z", findings: [], disclaimer: "Reviewed" };
    } else if (path === "/api/v1/search") body = { results: [] };

    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });

  await page.addInitScript(() => {
    localStorage.setItem("buyer-dash-organization", "org-integrity");
    localStorage.setItem("buyer-dash-facility", "facility-integrity");
    localStorage.setItem("buyer-dash-operation", "Production Ops");
    localStorage.setItem("buyer-dash-data-mode", "Uploads");
    sessionStorage.setItem("buyer-dash-pending-page", "Label Studio");
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByLabel("Inventory batch").selectOption("lot-integrity");

  const coaPanel = page.locator("section.inventory-panel").filter({ hasText: "Test results for this material" });
  await expect(coaPanel.getByText("2026-08-30", { exact: true })).toBeVisible();

  const review = page.locator("section.inventory-panel").filter({ hasText: "Testing-label pre-release review" });
  const expectedFields: Array<[string, string]> = [
    ["Product identity", "Integrity Kush Flower"],
    ["Brand", "Integrity Reserve"],
    ["Strain", "Integrity Kush"],
    ["Product type / category", "Flower"],
    ["Package size", "3.5 g"],
    ["Net contents", "NET WT. .12345 OZ"],
    ["Active facility license", "MP281234"],
    ["Active facility", "Integrity Manufacturing"],
    ["Package / traceability ID", packageTag],
    ["Batch / lot number", "IK-2026-08"],
    ["Label serial number", "INT-001"],
    ["Potency statement", "THCA 30.1% · Total THC 26.84% · TAC 31.2% · Total terpenes 2.75%"],
    ["Total THC", "26.84%"],
    ["Total CBD", "0.12%"],
    ["Total cannabinoids / TAC", "31.2%"],
    ["Total terpenes", "2.75%"],
    ["Lab testing state", "Passed"],
    ["Testing laboratory", "Integrity Cannabis Lab"],
    ["Laboratory license", "IL281234"],
    ["Test date", "2026-08-30"],
    ["COA reference", "COA-INTEGRITY-1"],
    ["Harvest date", "2026-06-08"],
    ["Package date", "2026-08-31"],
    ["Expiration / best-by", "2027-08-30"],
    ["Cultivated by", "Integrity Cultivation"],
    ["Cultivator license", "MC281111"],
    ["Packaged by", "Integrity Manufacturing"],
    ["Packager license", "MP281234"],
    ["Sold by", "Integrity Retail"],
    ["Seller license(s)", "MR281222"],
  ];

  for (const [label, value] of expectedFields) {
    await expect(review.getByLabel(label)).toHaveValue(value);
  }

  await expect(review.getByLabel("Package / traceability ID")).toHaveJSProperty("readOnly", true);
  await expect(page.getByAltText(`QR code for METRC package ${packageTag}`)).toBeVisible();
  await expect(page.getByAltText(`Code 128 barcode for METRC package ${packageTag}`)).toBeVisible();

  await page.getByRole("button", { name: "Run LabelGuard" }).click();
  await expect(page.getByRole("heading", { name: "PASS" })).toBeVisible();

  expect(reviewPayload).not.toBeNull();
  expect(reviewPayload?.product_id).toBe("product-integrity");
  expect(reviewPayload?.package_id).toBe(packageTag);
  const submitted = reviewPayload?.label as Record<string, string>;
  for (const [field, expected] of [
    ["product_name", "Integrity Kush Flower"],
    ["package_id", packageTag],
    ["batch_number", "IK-2026-08"],
    ["test_date", "2026-08-30"],
    ["expiration_date", "2027-08-30"],
    ["laboratory", "Integrity Cannabis Lab"],
    ["lab_license_number", "IL281234"],
    ["coa_reference", "COA-INTEGRITY-1"],
    ["total_thc", "26.84%"],
    ["total_terpenes", "2.75%"],
  ] as Array<[string, string]>) {
    expect(submitted[field]).toBe(expected);
  }
});
