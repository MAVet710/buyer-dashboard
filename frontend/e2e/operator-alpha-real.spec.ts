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
});
