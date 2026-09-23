import { expect, test, type Page } from "@playwright/test";

type Options = { unavailable?: boolean; mismatched?: boolean; queueUnavailable?: boolean };
async function install(page: Page, options: Options = {}) {
  const paths: string[] = [];
  const writes: Array<{ path: string; body: unknown }> = [];
  let unavailable = options.unavailable ?? false;
  const notes: Record<string, string> = { first: "First run note", second: "Second run note", historical: "Archived run note" };
  const run = (id: string) => ({ id, batch_number: `BATCH-${id.toUpperCase()}`, method: "BHO", workflow_key: "bho_cured", current_stage_key: "intake", status: id === "historical" ? "complete" : "planned", release_status: "pending", product_family: "", strain: "QA fixture", toll_processing: false, compliance_provider: "metrc", license_number: "TEST", operator: "QA operator", notes: notes[id] || "", updated_at: "2026-09-23T12:00:00Z" });
  await page.addInitScript(() => {
    localStorage.setItem("buyer-dash-organization", "extraction-org");
    if (!localStorage.getItem("buyer-dash-facility")) localStorage.setItem("buyer-dash-facility", "extraction-facility");
    localStorage.setItem("buyer-dash-operation", "Production Ops");
    localStorage.setItem("buyer-dash-data-mode", "Uploads");
  });
  await page.route("**/api/v1/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    paths.push(path);
    const facility = request.headers()["x-facility-id"] || "extraction-facility";
    const capabilities = { retail: false, production: true, cultivation: false, commercial: false };
    const account = { user: { id: "extraction-user", display_name: "Operator", email: "operator@example.test", role: "operator", must_change_password: false }, organization: { id: "extraction-org", name: "QA extraction", slug: "extraction-org" }, facility_id: facility, capabilities, facilities: [{ id: facility, name: "QA facility", code: "TEST", capabilities }] };
    let body: unknown = {};
    if (request.method() !== "GET") {
      writes.push({ path, body: request.postDataJSON() });
      if (path === "/api/v1/extraction/runs/second/notes" && facility === "extraction-facility") {
        notes.second = String((request.postDataJSON() as { notes: string }).notes);
        await route.fulfill({ status: 200, json: run("second") }); return;
      }
      await route.fulfill({ status: 403, json: { detail: "Unexpected write blocked by this synthetic acceptance fixture." } }); return;
    }
    if (path === "/api/v1/account/context") body = account;
    else if (path === "/api/v1/account/access-options") body = { organizations: [{ ...account.organization, facilities: account.facilities }], organization_id: "extraction-org", facility_id: facility };
    else if (path === "/api/v1/search") body = { results: [] };
    else if (path === "/api/v1/extraction/runs") {
      if (options.queueUnavailable) { await route.fulfill({ status: 503, json: { detail: "Run list is temporarily unavailable." } }); return; }
      body = [run("first"), run("second")];
    } else if (path === "/api/v1/extraction-parity/overview") body = { runs: [], workflows: [], summary: {}, alerts: [], toll_jobs: [] };
    else if (path.startsWith("/api/v1/extraction/runs/")) {
      const id = decodeURIComponent(path.slice("/api/v1/extraction/runs/".length));
      if (unavailable || facility !== "extraction-facility" || !(id in notes)) {
        await route.fulfill({ status: facility !== "extraction-facility" ? 403 : 404, json: { detail: "Run unavailable in this facility." } }); return;
      }
      body = { run: run(options.mismatched ? "first" : id), workflow: { key: "bho_cured", label: "QA workflow", method: "BHO", stages: [{ key: "intake", label: "Intake", output_fields: [] }] }, inputs: [], outputs: [], events: [], qa_events: [], cost_events: [], traceability: [], mass_balance: { consumed_input: 0, recorded_output: 0, yield_pct: 0 }, cogs: { total: 0 }, toll_job: null };
    } else if (path.endsWith("/products") || path.endsWith("/lots") || path.endsWith("/workflows")) body = [];
    await route.fulfill({ status: 200, json: body });
  });
  return { paths, writes, recover: () => { unavailable = false; }, notes };
}

const deepLink = (id: string) => `/production/extraction?extractionView=runs&extractionRun=${encodeURIComponent(id)}&extractionPanel=run`;

for (const width of [390, 1440]) test(`floor to Advanced keeps the exact run through reload and return at ${width}px`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width, height: 1000 });
  const state = await install(page);
  await page.goto("/production/extraction?extractionView=runs");
  const floor = page.locator(".extraction-operator-workspace");
  await floor.getByRole("row").filter({ hasText: "BATCH-SECOND" }).click();
  await expect(floor.getByRole("heading", { name: "BATCH-SECOND", exact: true })).toBeVisible();
  await floor.getByRole("button", { name: "Advanced Run 360", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "BATCH-SECOND", exact: true })).toBeVisible();
  await expect(page).toHaveURL(/extractionRun=second.*extractionPanel=run/);
  await page.reload();
  const detail = page.getByRole("dialog", { name: "BATCH-SECOND", exact: true });
  await expect(detail).toBeVisible();
  for (const tab of ["Overview", "Inputs", "Process", "Outputs + QA", "COGS", "Traceability", "History"]) await expect(detail.getByRole("button", { name: tab, exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath(`extraction-exact-${width}.png`), fullPage: true, animations: "disabled" });
  await detail.getByRole("button", { name: "Close", exact: true }).click();
  await expect(page).toHaveURL(/extractionPanel=board/);
  await page.getByRole("button", { name: "Close window", exact: true }).click();
  await expect(page).not.toHaveURL(/extractionPanel=/);
  await expect(page).toHaveURL(/extractionRun=second/);
  await expect(floor.getByRole("heading", { name: "BATCH-SECOND", exact: true })).toBeVisible();
  expect(state.writes).toEqual([]);
});

test("the two floor entry points and browser back/forward preserve run identity", async ({ page }) => {
  const state = await install(page);
  await page.goto("/production/extraction?extractionRun=second");
  await page.getByRole("button", { name: "Open Run 360", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "BATCH-SECOND", exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("dialog", { name: "Advanced Extraction Run 360", exact: true })).toHaveCount(0);
  await expect(page).toHaveURL(/extractionRun=second/);
  await page.goForward();
  await expect(page.getByRole("dialog", { name: "BATCH-SECOND", exact: true })).toBeVisible();
  expect(state.writes).toEqual([]);
});

test("a historical exact run loads even when absent from the run list", async ({ page }) => {
  const state = await install(page);
  await page.goto(deepLink("historical"));
  await expect(page.getByRole("dialog", { name: "BATCH-HISTORICAL", exact: true })).toBeVisible();
  expect(state.paths.filter(path => path.startsWith("/api/v1/extraction/runs/"))).toEqual(["/api/v1/extraction/runs/historical"]);
  expect(state.writes).toEqual([]);
});

test("exact detail remains available when the unrelated run list fails", async ({ page }) => {
  const state = await install(page, { queueUnavailable: true });
  await page.goto(deepLink("second"));
  await expect(page.getByRole("dialog", { name: "BATCH-SECOND", exact: true })).toBeVisible();
  expect(state.paths.some(path => path === "/api/v1/extraction/runs/first")).toBe(false);
});

test("missing detail fails visibly and retry opens the same run without fallback", async ({ page }) => {
  const state = await install(page, { unavailable: true });
  await page.goto(deepLink("second"));
  const unavailable = page.getByRole("dialog", { name: "Run unavailable", exact: true });
  await expect(unavailable.getByRole("alert")).toContainText("No other run was selected");
  await expect(unavailable.getByRole("button", { name: "Save notes", exact: true })).toHaveCount(0);
  expect(state.paths.some(path => path === "/api/v1/extraction/runs/first")).toBe(false);
  state.recover();
  await unavailable.getByRole("button", { name: "Retry requested run", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "BATCH-SECOND", exact: true })).toBeVisible();
  expect(state.writes).toEqual([]);
});

test("a response for a different record is never presented as the requested run", async ({ page }) => {
  const state = await install(page, { mismatched: true });
  await page.goto(deepLink("second"));
  await expect(page.getByRole("dialog", { name: "Run unavailable", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "BATCH-FIRST", exact: true })).toHaveCount(0);
  expect(state.writes).toEqual([]);
});

test("a facility switch cannot restore the previous facility's run detail", async ({ page }) => {
  const state = await install(page);
  await page.goto(deepLink("second"));
  await expect(page.getByRole("dialog", { name: "BATCH-SECOND", exact: true })).toBeVisible();
  await page.evaluate(() => localStorage.setItem("buyer-dash-facility", "other-facility"));
  await page.reload();
  await expect(page.getByRole("dialog", { name: "Run unavailable", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "BATCH-SECOND", exact: true })).toHaveCount(0);
  expect(state.writes).toEqual([]);
});

test("selecting another floor run resets its preflight confirmations", async ({ page }) => {
  const state = await install(page);
  await page.goto("/production/extraction?extractionView=runs&extractionRun=first");
  const floor = page.locator(".extraction-operator-workspace");
  for (const label of ["Source package/material verified", "Required equipment/work area ready", "Required SOP/batch documentation ready"]) await floor.getByRole("checkbox", { name: label, exact: true }).check();
  await floor.getByRole("row").filter({ hasText: "BATCH-SECOND" }).click();
  await expect(floor.getByRole("heading", { name: "BATCH-SECOND", exact: true })).toBeVisible();
  for (const label of ["Source package/material verified", "Required equipment/work area ready", "Required SOP/batch documentation ready"]) await expect(floor.getByRole("checkbox", { name: label, exact: true })).not.toBeChecked();
  await expect(floor.getByRole("button", { name: "Start run & consume reserved material", exact: true })).toBeDisabled();
  expect(state.writes).toEqual([]);
});

test("an Advanced note is saved only to the selected run and survives reopening", async ({ page }) => {
  const state = await install(page);
  await page.goto(deepLink("second"));
  let detail = page.getByRole("dialog", { name: "BATCH-SECOND", exact: true });
  await detail.getByText("Run notes", { exact: true }).click();
  // Match the existing editor's accessible role/name, not nested label text.
  await expect(detail.getByRole("textbox", { name: "Notes", exact: true })).toHaveValue("Second run note");
  await detail.getByRole("textbox", { name: "Notes", exact: true }).fill("QA continuity note");
  await detail.getByRole("button", { name: "Save notes", exact: true }).click();
  await expect.poll(() => state.notes.second).toBe("QA continuity note");
  await page.reload();
  detail = page.getByRole("dialog", { name: "BATCH-SECOND", exact: true });
  await detail.getByText("Run notes", { exact: true }).click();
  await expect(detail.getByRole("textbox", { name: "Notes", exact: true })).toHaveValue("QA continuity note");
  expect(state.notes.first).toBe("First run note");
  expect(state.writes).toEqual([{ path: "/api/v1/extraction/runs/second/notes", body: { notes: "QA continuity note" } }]);
});
