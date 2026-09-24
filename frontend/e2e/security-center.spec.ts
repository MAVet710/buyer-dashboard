import { expect, test, type Page } from "@playwright/test";
test.use({ channel: process.env.SECURITY_BROWSER_CHANNEL || undefined });
const origin = process.env.SECURITY_BROWSER_BASE_URL || "http://127.0.0.1:4174";
async function fixture(page: Page, role = "dev") {
  let failed = false;
  const observed: string[] = [];
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/account/context") {
      await route.fulfill({ json: { user: { id: "test-user", role }, facility_id: "test-facility" } }); return;
    }
    observed.push(path);
    if (failed) { await route.fulfill({ status: 503, json: { detail: "Synthetic monitoring outage" } }); return; }
    await route.fulfill({ json: path.endsWith("/status") ? { state: "observing", notifications: "not_connected", last_success: 1790270000, dropped: 0, failures: 0 }
      : { total: 1, items: [{ id: "test-incident", title: "Repeated denied access", severity: "high", status: "open", occurrences: 10, evidence: { outcome: "all_observed_requests_denied" } }] } });
  });
  await page.goto(origin + "/e2e/fixtures/security-center.html");
  return { observed, fail: () => { failed = true; } };
}
test("DEV review loads on demand and explains disconnected alerts", async ({ page }) => {
  const state = await fixture(page);
  const summary = page.locator("summary", { hasText: "Security Center" });
  await expect(summary).toBeVisible(); expect(state.observed).toEqual([]);
  await summary.click();
  await expect(page.getByText("Repeated denied access", { exact: true })).toBeVisible();
  await expect(page.getByText("Email and external monitoring are not connected", { exact: false })).toBeVisible();
  expect(state.observed).toContain("/api/v1/security/status");
});
test("customer administrator cannot see or fetch platform incident panel", async ({ page }) => {
  const state = await fixture(page, "admin");
  await expect(page.locator("summary", { hasText: "Security Center" })).toHaveCount(0);
  expect(state.observed).toEqual([]);
});
test("failed refresh does not present stale observing state as current", async ({ page }) => {
  const state = await fixture(page);
  await page.locator("summary", { hasText: "Security Center" }).click();
  await expect(page.getByText("Observer: observing", { exact: false })).toBeVisible();
  state.fail(); await page.getByRole("button", { name: "Refresh security observations" }).click();
  await expect(page.getByRole("alert")).toContainText("Monitoring coverage is not verified");
  await expect(page.getByText("Observer: observing", { exact: false })).toHaveCount(0);
});
