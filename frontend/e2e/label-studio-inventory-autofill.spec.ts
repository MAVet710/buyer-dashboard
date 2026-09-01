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

const completeSource = {
  lot_id: "lot-complete",
  product_id: "product-complete",
  package_id: "1A4000000000000000001111",
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
    net_contents: "3.5 g",
    license_number: "MP281999",
    facility_name: "Label Manufacturing",
    package_id: "1A4000000000000000001111",
    batch_number: "CK-0901-A",
    potency: "THCA 31.2% · Total THC 28.4%",
    lab_testing_state: "Passed",
    laboratory: "Example Cannabis Lab",
    test_date: "2026-08-30",
    coa_reference: "COA-0901-A",
    coa_url: "https://example.invalid/coa/0901-a",
    ingredients: "Cannabis flower",
    allergens: "None declared",
    manufacture_date: "",
    package_date: "2026-09-01",
    expiration_date: "2027-03-01",
    warning_text: "Approved warning language",
  },
  raw_text: "Copper Kush Flower\n3.5 g\nMP281999\n1A4000000000000000001111\nCK-0901-A\nApproved warning language",
  source_summary: { facility: "Label Manufacturing", license_number: "MP281999", license_type: "Manufacturing", qa_source: "verified" },
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
    net_contents: "",
    package_id: "",
    batch_number: "BULK-0901-B",
  },
};

test("selecting an inventory batch builds, reviews, and gates the label", async ({ page }) => {
  let reviewPayload: Record<string, unknown> | null = null;
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let body: unknown = {};
    if (path === "/api/v1/account/context") body = account;
    else if (path === "/api/v1/account/access-options") body = accessOptions;
    else if (path === "/api/v1/control-tower/label-templates") body = [template];
    else if (path === "/api/v1/label-printing/inventory-sources") body = [completeSource, incompleteSource];
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

  await expect(page.getByText("19 label fields populated from inventory.")).toBeVisible();
  await expect(page.getByText("All fields required by the current rule set are populated.")).toBeVisible();
  const reviewSection = page.locator("section.inventory-panel").filter({ hasText: "Pre-release review" });
  await expect(reviewSection.getByLabel("Product identity")).toHaveValue("Copper Kush Flower");
  await expect(reviewSection.getByLabel("Net contents")).toHaveValue("3.5 g");
  await expect(reviewSection.getByLabel("Package / traceability ID")).toHaveValue("1A4000000000000000001111");
  await expect(page.getByText("THCA 31.2% · Total THC 28.4%")).toBeVisible();

  await page.getByRole("button", { name: "Run LabelGuard" }).click();
  await expect(page.getByRole("heading", { name: "PASS" })).toBeVisible();
  expect(reviewPayload).not.toBeNull();
  expect(reviewPayload?.product_id).toBe("product-complete");
  expect(reviewPayload?.package_id).toBe("1A4000000000000000001111");
  expect((reviewPayload?.label as Record<string, string>).batch_number).toBe("CK-0901-A");
  await expect(page.getByRole("button", { name: "Print reviewed preview" })).toBeEnabled();

  await batchSelect.selectOption("lot-incomplete");
  const missingBanner = page.getByText(/Required information still missing:/);
  await expect(missingBanner).toContainText("Net contents");
  await expect(missingBanner).toContainText("Package / traceability ID");
  await expect(page.getByRole("button", { name: "Run LabelGuard" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Print reviewed preview" })).toBeDisabled();
});
