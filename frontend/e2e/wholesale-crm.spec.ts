import { expect, test, type Page } from "@playwright/test";

test.use({ channel: "chrome" });
const origin = process.env.CRM_BROWSER_BASE_URL || "http://127.0.0.1:4178";
async function fixture(page: Page, pipeline = false) {
  const writes: { path: string; payload: Record<string, unknown> }[] = [];
  const customer = { id: "customer", name: "Retail Account", contact_name: "Buyer", contact_email: "buyer@example.test", contact_phone: "555-0100", payment_terms: "Net 30", license_or_registration: "TEST" };
  let relationship: Record<string, unknown> = { id: "account", partner_id: "customer", owner: "Rep", status: "active", next_action: "Call buyer", next_action_date: "2026-10-01" };
  const quotes: Record<string, unknown>[] = [];
  const opportunities: Record<string, unknown>[] = [{ id: "opportunity", partner_id: "customer", customer_name: "Retail Account", title: "Restock", stage: "qualified", estimated_value: 200, expected_close_date: null, owner: "Rep", source: "Referral", next_action: "Send quote", next_action_date: null }];
  await page.route("**/api/v1/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    let body: unknown = {};
    if (request.method() === "POST") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      writes.push({ path, payload });
      if (path.endsWith("/account")) relationship = { ...relationship, ...payload };
      if (path.endsWith("/opportunities/opportunity")) opportunities[0] = { ...opportunities[0], ...payload };
      if (path.endsWith("/quotes")) quotes.push({ id: "quote", title: payload.title, status: "draft", commercial_order_id: null, lines_json: JSON.stringify([{ product_id: "product", description: "Flower", quantity: 4, unit: "unit", unit_price: 12 }]) });
      if (path.endsWith("/convert")) { quotes[0].commercial_order_id = "canonical-order"; quotes[0].status = "converted"; body = { id: "canonical-order" }; }
    } else if (path.endsWith("/customers")) body = { items: [{ ...customer, relationship }], has_more: false };
    else if (path.endsWith("/pipeline")) body = { items: opportunities, has_more: false };
    else if (path.endsWith("/products")) body = [{ id: "product", name: "Flower", sku: "SKU", base_unit: "unit", retail_price: 20 }];
    else if (path.endsWith("/customers/customer")) body = { customer, relationship, sales_value: 200, open_balance: 80, pricing: [], opportunities, quotes, timeline: [{ id: "call", kind: "activities", at: "2026-09-25T12:00:00Z", text: "Discussed reorder", status: "call", actor: "Rep" }] };
    await route.fulfill({ json: body });
  });
  await page.goto(origin + "/e2e/fixtures/wholesale-crm.html" + (pipeline ? "?pipeline" : ""));
  return writes;
}

test("account edits, quotes and activities preserve CRM payloads and canonical order handoff", async ({ page }) => {
  const writes = await fixture(page);
  await page.getByRole("button", { name: "Retail Account" }).click();
  await expect(page.getByText("CUSTOMER 360", { exact: true })).toBeVisible();
  await page.getByLabel("Assigned rep").fill("New rep");
  await page.getByRole("button", { name: "Save account" }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].payload).toEqual({ owner: "New rep", status: "active", next_action: "Call buyer", next_action_date: "2026-10-01" });
  await page.getByLabel("Quote title").fill("Opening quote");
  await page.getByLabel("Add product").selectOption("product");
  await page.getByLabel("Quantity", { exact: true }).fill("4");
  await page.getByRole("button", { name: "Save quote", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Opening quote" })).toBeVisible();
  expect(writes[1].payload).toEqual({ title: "Opening quote", opportunity_id: null, lines: [{ product_id: "product", quantity: 4, unit_price: null }] });
  await page.getByRole("button", { name: "Convert to draft sales order" }).click();
  await expect(page.getByRole("status")).toContainText("canonical-order");
  await expect(page.getByRole("button", { name: "Convert to draft sales order" })).toHaveCount(0);
  await page.getByLabel("Notes", { exact: true }).fill("Spoke to buyer");
  await page.getByRole("button", { name: "Record activity" }).click();
  await expect.poll(() => writes.length).toBe(4);
  expect(writes[3].payload).toEqual({ kind: "note", body: "Spoke to buyer", reference: "" });
  await expect(page.getByText("activities: Discussed reorder")).toBeVisible();
});

test("mobile pipeline opens a customer and persists opportunity stage and next action", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const writes = await fixture(page, true);
  await page.getByRole("button", { name: "Retail Account" }).click();
  await page.getByRole("button", { name: "Restock", exact: true }).click();
  await page.getByRole("combobox", { name: "Stage", exact: true }).selectOption("negotiating");
  const form = page.locator("form").filter({ has: page.getByRole("heading", { name: "Edit opportunity" }) });
  await form.getByLabel("Next action", { exact: true }).fill("Review terms");
  await form.getByRole("button", { name: "Save opportunity" }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].payload.stage).toBe("negotiating");
  expect(writes[0].payload.next_action).toBe("Review terms");
  expect(writes[0].payload).not.toHaveProperty("id");
  await expect(page.getByRole("cell", { name: "negotiating", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
