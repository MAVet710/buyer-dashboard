import { expect, test } from "@playwright/test";

for (const width of [1280, 390]) {
  test(`readiness owner, explicit Work, and durable reporting at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    const item = { key: "inventory", label: "Starting inventory", route: "Data & Settings", status: "incomplete", evidence: "No canonical inventory transactions observed.", manual: false, manual_status: null, notes: "", owner_user_id: null, owner_name: null, work_item_id: null as string | null, target_date: null };
    const writes: { path: string; body: Record<string, unknown>; idempotency: string | undefined }[] = [];
    let subscriptions: Record<string, unknown>[] = [], deliveries: Record<string, unknown>[] = [];
    await page.route("**/api/v1/**", async route => {
      const request = route.request(), path = new URL(request.url()).pathname;
      const body = request.method() === "POST" ? request.postDataJSON() : {};
      if (request.method() === "POST") writes.push({ path, body, idempotency: request.headers()["x-idempotency-key"] });
      if (path.endsWith("/implementation-readiness/inventory/work")) { item.work_item_id = "work-one"; return route.fulfill({ json: { work_item_id: item.work_item_id } }); }
      if (path.endsWith("/implementation-readiness/inventory")) { Object.assign(item, body, { owner_name: "Facility Operator" }); return route.fulfill({ json: item }); }
      if (path.endsWith("/implementation-readiness")) return route.fulfill({ json: { can_manage: true, items: [item], owner_options: [{ id: "user-one", name: "Facility Operator" }] } });
      if (path.endsWith("/executive-reports/catalog")) return route.fulfill({ json: { items: [{ key: "production", label: "Production" }] } });
      if (path.endsWith("/report-subscriptions/history")) return route.fulfill({ json: { items: deliveries } });
      if (path.endsWith("/report-subscriptions/sub-one/active")) { subscriptions[0].active = body.active; return route.fulfill({ json: subscriptions[0] }); }
      if (path.endsWith("/report-subscriptions/sub-one/run")) {
        const delivery = { id: "delivery-one", report_type: "production", recipients: ["ops@example.com"], status: "deferred", detail: "Spacemail is unavailable or validation failed. No email was sent.", created_at: "2026-09-25T12:00:00Z" };
        deliveries = [delivery]; return route.fulfill({ json: delivery });
      }
      if (path.endsWith("/report-subscriptions")) {
        if (request.method() === "POST") subscriptions = [{ ...body, id: "sub-one", active: true, next_run: "2026-10-02T12:00:00Z", last_run: null }];
        return route.fulfill({ json: request.method() === "POST" ? subscriptions[0] : { items: subscriptions } });
      }
      return route.fulfill({ status: 404, json: { detail: "Unexpected fixture request" } });
    });
    await page.goto("/e2e/fixtures/integration-wizard.html");
    await expect(page.getByRole("heading", { name: "Starting inventory" })).toBeVisible();
    expect(writes).toEqual([]);
    await page.getByRole("combobox", { name: "Owner", exact: true }).selectOption("user-one");
    await page.getByLabel("Notes", { exact: true }).fill("Opening balances need review");
    await page.getByLabel("Target date").fill("2026-10-01");
    await page.getByRole("button", { name: "Save review" }).click();
    await expect(page.getByText("Review saved.")).toBeVisible();
    expect(writes[0].body).toMatchObject({ owner_user_id: "user-one", target_date: "2026-10-01" });
    expect(writes[0].body).not.toHaveProperty("owner");
    await page.reload();
    await expect(page.getByRole("combobox", { name: "Owner", exact: true })).toHaveValue("user-one");
    await page.getByRole("button", { name: "Create Doobie Work item" }).click();
    await expect(page.getByRole("status")).toContainText("/work?item=work-one");
    await page.getByRole("button", { name: "Readiness", exact: true }).click();
    await expect(page.getByRole("button", { name: "Open Doobie Work item" })).toBeVisible();
    await expect(page.getByText("incomplete", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Reports", exact: true }).click();
    await page.getByLabel("Recipients, separated by commas").fill("ops@example.com");
    await page.getByRole("button", { name: "Create subscription", exact: true }).click();
    await expect(page.getByRole("button", { name: "Pause", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Test delivery" }).click();
    await expect(page.getByRole("heading", { name: "production: deferred" })).toBeVisible();
    expect(writes.find(write => write.path.endsWith("/run"))).toMatchObject({ body: { test: true }, idempotency: expect.any(String) });
    await page.getByRole("button", { name: "Pause", exact: true }).click();
    await page.reload();
    await page.getByRole("button", { name: "Reports", exact: true }).click();
    await expect(page.getByRole("button", { name: "Resume", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "production: deferred" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(errors).toEqual([]);
    await page.screenshot({ path: `../tmp/adoption-${width}.png`, fullPage: true });
  });
}
