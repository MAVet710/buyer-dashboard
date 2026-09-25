import { expect, test, type Page } from "@playwright/test";

async function install(page: Page, role = "operator") {
  const writes: Array<Record<string, unknown>> = [];
  let work = { id: "work-1", title: "Inspect vault count", description: "Compare the signed count sheet.", status: "open", priority: "high", assignee_id: "worker-1", due_at: "2025-09-25T12:00:00Z", version: 1, blocked_reason: "", notes: "", evidence: "", workspace: "Inventory", route: "/inventory", entity_type: "inventory_lot", entity_id: "lot-1", created_by: "worker-1", completed_by: null as string | null, completed_at: null as string | null };
  await page.addInitScript(() => {
    localStorage.setItem("buyer-dash-organization", "work-org");
    localStorage.setItem("buyer-dash-facility", "work-facility");
    localStorage.setItem("buyer-dash-operation", "Retail Ops");
  });
  await page.route("**/api/v1/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    const capabilities = { retail: true, production: true, cultivation: true, commercial: true };
    const account = { user: { id: "worker-1", display_name: "Worker", role, must_change_password: false }, organization: { id: "work-org", name: "Work QA" }, facility_id: "work-facility", capabilities, facilities: [{ id: "work-facility", name: "QA facility", capabilities }] };
    let body: unknown = {};
    if (request.method() !== "GET") {
      const payload = request.postDataJSON(); writes.push(payload);
      if (path === "/api/v1/work/work-1" && request.method() === "PATCH") {
        work = { ...work, ...payload, version: work.version + 1,
          completed_by: payload.status === "completed" ? "worker-1" : null,
          completed_at: payload.status === "completed" ? "2026-09-25T12:00:00Z" : null };
        body = work;
      } else if (path === "/api/v1/work/templates/generate") body = { generated: 0, may_have_more: false };
      else if (path === "/api/v1/work") body = { ...work, ...payload, id: "created" };
      else { await route.fulfill({ status: 403, json: { detail: "Unexpected fixture write" } }); return; }
    } else if (path === "/api/v1/account/context") body = account;
    else if (path === "/api/v1/account/access-options") body = { organizations: [{ ...account.organization, facilities: account.facilities }], organization_id: "work-org", facility_id: "work-facility" };
    else if (path === "/api/v1/work") body = { items: [work], has_more: false };
    else if (path === "/api/v1/work/work-1") body = work;
    else if (path === "/api/v1/work/assignees") body = { items: [{ id: "worker-1", name: "Worker" }, { id: "worker-2", name: "QA Partner" }], has_more: false };
    else if (path === "/api/v1/work/templates") body = { items: [], has_more: false };
    else if (path === "/api/v1/home/inbox") body = { items: [], summary: { critical: 0, high: 0, total: 0 } };
    await route.fulfill({ status: 200, json: body });
  });
  return writes;
}

test("operator assigns, blocks with evidence, completes and reopens", async ({ page }) => {
  const writes = await install(page);
  await page.goto("/work?item=work-1");
  const detail = page.getByRole("region", { name: "Work details" });
  await expect(detail.getByRole("heading", { name: "Inspect vault count" })).toBeVisible();
  await detail.getByLabel("Assignee").selectOption("worker-2");
  await detail.getByRole("combobox", { name: "Status", exact: true }).selectOption("blocked");
  await detail.getByLabel("Blocked reason").fill("Waiting for signed count");
  await detail.getByLabel("Evidence / references").fill("Count sheet 42");
  await detail.getByRole("button", { name: "Save changes" }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toMatchObject({ version: 1, assignee_id: "worker-2", status: "blocked", evidence: "Count sheet 42" });
  await expect(detail.getByRole("button", { name: "Save changes" })).toBeEnabled();
  await detail.getByRole("combobox", { name: "Status", exact: true }).selectOption("completed");
  await detail.getByRole("button", { name: "Save changes" }).click();
  await expect(detail.getByText(/Completed by worker-1/)).toBeVisible();
  await detail.getByRole("combobox", { name: "Status", exact: true }).selectOption("open");
  await detail.getByRole("button", { name: "Save changes" }).click();
  await expect(detail.getByText(/Completed by worker-1/)).toHaveCount(0);
});

test("mobile queue is usable and title opens linked workspace", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await install(page);
  await page.goto("/work");
  await expect(page.getByRole("heading", { name: "Work Queue", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Inspect work / update" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole("button", { name: "Inspect vault count" }).click();
  await expect(page).toHaveURL(/\/inventory$/);
});

test("read-only role can inspect without mutation controls", async ({ page }) => {
  const writes = await install(page, "read_only");
  await page.goto("/work?item=work-1");
  await expect(page.getByRole("region", { name: "Work details" }).getByRole("combobox", { name: "Status", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Create work", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Generate due work" })).toHaveCount(0);
  expect(writes).toHaveLength(0);
});

test("Home inbox opens the exact work item and survives reload", async ({ page }) => {
  const writes = await install(page);
  await page.route("**/api/v1/home/inbox", route => route.fulfill({ json: {
    items: [{ id: "work:work-1", severity: "high", area: "Work", title: "Inspect vault count",
      detail: "Assigned work needs attention.", workspace: "Work Queue", route: "/work?item=work-1",
      entity_id: "work-1", action_label: "Inspect work", evidence: [] }],
    summary: { critical: 0, high: 1, total: 1 },
  } }));
  await page.goto("/home");
  await page.getByRole("button", { name: "Inspect work", exact: true }).click();
  await expect(page).toHaveURL(/\/work\?item=work-1$/);
  const detail = page.getByRole("region", { name: "Work details" });
  await expect(detail.getByRole("heading", { name: "Inspect vault count" })).toBeVisible();
  await page.reload();
  await expect(detail.getByRole("heading", { name: "Inspect vault count" })).toBeVisible();
  expect(writes).toHaveLength(0);
});
