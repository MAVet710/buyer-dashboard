import { expect, test, type Page } from "@playwright/test";
test.use({ channel: process.env.WIZARD_BROWSER_CHANNEL || undefined });
const origin = process.env.WIZARD_BROWSER_BASE_URL || "http://127.0.0.1:4186";
async function fixture(page: Page) {
  let step = "facility", skipped = false, failed = false, saved = false;
  const writes: string[] = [];
  const connection = () => ({ configured: saved, status: failed ? "failed" : "configured", secret_hint: "", configuration: { state: "MA", license_number: "TEST-LICENSE" }, last_validated_at: null, last_error: "" });
  const mode = { selected_mode: "metrc_sandbox", effective_mode: "metrc_sandbox", explicit: true, source: "facility", metrc_sandbox_mapping_available: true, production_writes_enabled: false, choices: [], message: "Sandbox only. Production writes remain disabled." };
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() === "POST") writes.push(path);
    if (path.endsWith("/integration-wizard/progress")) { step = route.request().postDataJSON().step; return route.fulfill({ json: { step } }); }
    if (path.endsWith("/integration-wizard/providers/quickbooks")) { skipped = route.request().postDataJSON().skipped; return route.fulfill({ json: { skipped } }); }
    if (path.endsWith("/integrations/metrc/test")) { failed = true; return route.fulfill({ json: { ...connection(), result: { ok: false, message: "Synthetic provider denial" } } }); }
    if (path.endsWith("/integrations/metrc") && route.request().method() === "POST") { saved = true; return route.fulfill({ json: connection() }); }
    if (path.endsWith("/integration-wizard")) return route.fulfill({ json: {
      facility: { id: "one", name: "Test Facility", license_number: "TEST-LICENSE", license_type: "Processor", capabilities: ["production", "commercial"] }, mode, step, can_manage: true,
      items: ["metrc", "quickbooks"].map(key => ({ key, label: key === "metrc" ? "Metrc" : "QuickBooks", required: key === "metrc", status: key === "quickbooks" && skipped ? "optional_skipped" : failed && key === "metrc" ? "blocked" : "needs_validation", evidence: failed && key === "metrc" ? "The last provider validation failed." : "No successful validation recorded.", last_validated_at: null, environment: "sandbox", test_path: `/api/v1/${key === "metrc" ? "integrations" : "native-integrations"}/${key}/test`, settings_path: `/settings/integrations?provider=${key}`, mapping_route: "Integrations", managed_entities: [], manual_mapping_required: [] })),
    } });
    if (path.endsWith("/implementation-readiness")) return route.fulfill({ json: { items: [], can_manage: true } });
    if (path.endsWith("/alpha-operating-mode")) return route.fulfill({ json: mode });
    if (path.endsWith("/native-integrations")) return route.fulfill({ json: { metrc: connection(), biotrack: connection(), quickbooks: connection(), activation_rules: {} } });
    if (path.endsWith("/integrations")) return route.fulfill({ json: { metrc: connection(), doobie: null, ai_runtime: null, spacemail: null } });
    return route.fulfill({ status: 404, json: { detail: "Unexpected fixture request" } });
  });
  await page.goto(origin + "/e2e/fixtures/integration-wizard.html");
  await page.getByRole("button", { name: "Start or resume Integration Wizard" }).click();
  return writes;
}
for (const width of [1280, 390]) {
  test(`guided save, resume, optional skip and failure at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const writes = await fixture(page);
    await expect(page.getByRole("heading", { name: "Confirm facility", exact: true })).toBeVisible();
    expect(writes).toEqual([]);
    await page.getByRole("button", { name: "Confirm context and continue" }).click();
    await page.getByRole("button", { name: "Skip optional QuickBooks" }).click();
    await expect(page.getByText("Optional skipped", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Skip optional Metrc" })).toHaveCount(0);
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await page.getByRole("button", { name: "Open advanced settings for Metrc" }).click();
    await page.getByLabel("METRC User API Key").fill("synthetic-key-never-returned");
    const card = page.locator("#integration-metrc");
    await card.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByLabel("METRC User API Key")).toHaveValue("");
    await page.getByRole("button", { name: "Resume Integration Wizard" }).click();
    await expect(page.getByRole("heading", { name: "Connect", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await page.getByRole("button", { name: "Test / Validate Metrc" }).click();
    await expect(page.getByRole("alert")).toContainText("Provider validation failed");
    await expect(page.getByText("Blocked", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "7. Readiness summary" }).click();
    await expect(page.getByText("1 required provider(s) remain incomplete.", { exact: false })).toBeVisible();
    await page.reload();
    await page.getByRole("button", { name: "Start or resume Integration Wizard" }).click();
    await expect(page.getByRole("heading", { name: "Readiness summary", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(await page.content()).not.toContain("synthetic-key-never-returned");
    expect(writes.filter(path => path.endsWith("/test"))).toEqual(["/api/v1/integrations/metrc/test"]);
    await page.screenshot({ path: `../tmp/wizard-${width}.png`, fullPage: true });
  });
}
