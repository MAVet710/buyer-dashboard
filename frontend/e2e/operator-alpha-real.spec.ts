import { expect, test, type Locator, type Page } from "@playwright/test";
import { canonicalWorkspaceRoutes } from "../src/lib/workspaceRoutes";

const organizationId = process.env.ALPHA_ORGANIZATION_ID ?? "";
const facilityId = process.env.ALPHA_FACILITY_ID ?? "";

const uniqueRoutes = Array.from(
  new Map(canonicalWorkspaceRoutes().map(row => [row.path, row])).values(),
).filter(row => row.path !== "/");

function operationFor(path: string): "Retail Ops" | "Production Ops" {
  if (path.startsWith("/production")) return "Production Ops";
  return "Retail Ops";
}

async function prepare(page: Page, path: string) {
  await page.addInitScript(
    ({ org, facility, operation }) => {
      localStorage.setItem("buyer-dash-theme", "dark");
      localStorage.setItem("buyer-dash-organization", org);
      localStorage.setItem("buyer-dash-facility", facility);
      localStorage.setItem("buyer-dash-operation", operation);
      localStorage.setItem("buyer-dash-data-mode", "Uploads");
    },
    { org: organizationId, facility: facilityId, operation: operationFor(path) },
  );
}

async function clickViewTabs(root: Page | Locator, page: Page) {
  const tabs = root.locator(".view-tabs button:visible");
  const count = await tabs.count();
  for (let index = 0; index < count; index += 1) {
    const current = root.locator(".view-tabs button:visible");
    if (index >= await current.count()) break;
    const button = current.nth(index);
    if (await button.isDisabled()) continue;
    await button.click();
    await page.waitForTimeout(120);
  }
}

test.describe("strict real-stack operator alpha", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
  });

  for (const route of uniqueRoutes) {
    test(`${route.page} boots against real FastAPI and its visible view tabs do not crash`, async ({ page }) => {
      expect(organizationId, "ALPHA_ORGANIZATION_ID must be seeded by CI").not.toBe("");
      expect(facilityId, "ALPHA_FACILITY_ID must be seeded by CI").not.toBe("");
      await prepare(page, route.path);

      const pageErrors: string[] = [];
      const serverErrors: string[] = [];
      page.on("pageerror", error => pageErrors.push(error.message));
      page.on("response", response => {
        const url = response.url();
        if (!url.includes("/api/v1/")) return;
        if ([500, 501, 502].includes(response.status())) {
          serverErrors.push(`${response.status()} ${url}`);
        }
      });

      await page.goto(route.path, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(350);
      await expect(page.getByText("Workspace unavailable", { exact: true })).toHaveCount(0);
      await expect(page.locator("body")).not.toHaveText(/^\s*$/);

      await clickViewTabs(page, page);

      if (route.page === "Extraction") {
        const advanced = page.getByRole("button", { name: "Advanced Run 360" });
        if (await advanced.isVisible()) {
          await advanced.click();
          const dialog = page.getByRole("dialog", { name: "Advanced Extraction Run 360" });
          await expect(dialog).toBeVisible();
          await clickViewTabs(dialog, page);
          await dialog.getByRole("button", { name: "Close" }).click();
        }
      }

      expect(pageErrors, `uncaught browser errors on ${route.page}: ${pageErrors.join(" | ")}`).toEqual([]);
      expect(serverErrors, `real API 5xx responses on ${route.page}: ${serverErrors.join(" | ")}`).toEqual([]);
    });
  }

  test("Retail Ops can receive a package through the actual Inventory work window", async ({ page }) => {
    expect(organizationId).not.toBe("");
    expect(facilityId).not.toBe("");
    await prepare(page, "/inventory");
    await page.goto("/inventory", { waitUntil: "domcontentloaded" });

    await expect(page.getByRole("heading", { name: "Inventory" })).toBeVisible();
    await page.getByRole("button", { name: "Receive inventory", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: "Receive inventory" })).toBeVisible();

    const manualFallback = dialog.locator("summary").filter({ hasText: "Manual receipt (additive fallback)" });
    await manualFallback.click();
    await dialog.getByRole("button", { name: "Open manual receipt" }).click();
    await expect(dialog.getByRole("heading", { name: "Manual receipt" })).toBeVisible();

    const product = dialog.getByLabel("Product");
    await expect(product.locator("option")).not.toHaveCount(1);
    await product.selectOption({ index: 1 });
    await dialog.getByLabel("Package ID").fill("1A4-OA-BROWSER-RETAIL-0001");
    await dialog.getByLabel("Internal lot").fill("OA-BROWSER-RETAIL-LOT-0001");
    await dialog.getByLabel("Quantity").fill("3");
    await dialog.getByLabel("Location").fill("RETAIL-VAULT-BROWSER");
    await dialog.getByLabel("Source / supplier").fill("Browser Acceptance Vendor");
    await dialog.getByLabel("Manifest / transfer").fill("OA-BROWSER-MANIFEST-0001");
    await dialog.getByLabel("COA reference").fill("OA-BROWSER-COA-0001");
    await dialog.getByLabel("Notes").fill("Real browser operator acceptance receipt");

    await dialog.getByRole("button", { name: "Receive inventory", exact: true }).click();
    await expect(dialog.getByText("Inventory receipt posted.", { exact: true })).toBeVisible();
    await expect(dialog.getByText(/1 package\(s\) were added/)).toBeVisible();
    await dialog.getByRole("button", { name: "Done" }).click();

    await page.getByRole("button", { name: "Packages", exact: true }).click();
    const search = page.getByPlaceholder(/Product, SKU, package, strain, vendor/i);
    await search.fill("1A4-OA-BROWSER-RETAIL-0001");
    await expect(page.getByText("1A4-OA-BROWSER-RETAIL-0001", { exact: true })).toBeVisible();
  });

  test("Extraction can plan, reserve, preflight, and start a run through the actual floor UI", async ({ page }) => {
    expect(organizationId).not.toBe("");
    expect(facilityId).not.toBe("");
    await prepare(page, "/production/extraction");
    await page.goto("/production/extraction", { waitUntil: "domcontentloaded" });

    await expect(page.getByRole("heading", { name: "Extraction" })).toBeVisible();
    await page.getByRole("button", { name: "New run" }).click();
    await expect(page.getByRole("heading", { name: "Reserve source material" })).toBeVisible();

    await expect(page.getByLabel("Process / target").locator("option")).not.toHaveCount(0);
    await expect(page.getByLabel("Source material").locator("option")).not.toHaveCount(0);
    await page.getByLabel("Amount to reserve").fill("1");
    await page.getByLabel("Run ID").fill("OA-BROWSER-EXTRACTION-0001");
    const plan = page.getByRole("button", { name: "Plan run & reserve" });
    await expect(plan).toBeEnabled();
    await plan.click();

    await expect(page.getByRole("heading", { name: "OA-BROWSER-EXTRACTION-0001" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Ready to start this run?" })).toBeVisible();
    await page.getByLabel("Source package/material verified").check();
    await page.getByLabel("Required equipment/work area ready").check();
    await page.getByLabel("Required SOP/batch documentation ready").check();

    const start = page.getByRole("button", { name: "Start run & consume reserved material" });
    await expect(start).toBeEnabled();
    await start.click();
    await expect(page.getByRole("heading", { name: "Ready to start this run?" })).toHaveCount(0);
    await expect(page.locator(".metric").filter({ hasText: "Consumed input" })).toContainText("1 g");
    await expect(page.getByText("Current process step", { exact: true })).toBeVisible();
  });
});
