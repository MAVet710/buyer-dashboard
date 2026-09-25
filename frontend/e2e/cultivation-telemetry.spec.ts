import { expect, test } from "@playwright/test";

test.use({ channel: process.env.TELEMETRY_BROWSER_CHANNEL || undefined });
const origin = process.env.TELEMETRY_BROWSER_BASE_URL || "http://127.0.0.1:4175";
for (const role of ["operator", "viewer"]) {
  test(`${role} sees irrigation totals and only authorized entry controls`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const writes: string[] = [];
    await page.route("**/api/v1/**", async route => {
      const path = new URL(route.request().url()).pathname;
      if (route.request().method() !== "GET") writes.push(path);
      if (path.endsWith("/account/context")) return route.fulfill({ json: { user: { role } } });
      if (path.endsWith("/plants/rooms")) return route.fulfill({ json: { items: [{ id: "r1", room_code: "Flower", display_name: "Flower", active: true }] } });
      if (path.endsWith("/telemetry/rooms/r1")) return route.fulfill({ json: {
        as_of: "2026-09-25T12:00:00Z", truncated: false, exceptions: [], readings: [
          { metric: "irrigation_event", source: "manual", device_id: "", value: 1, unit: "count", quality: "valid", observed_at: "2026-09-25T11:00:00Z", states: ["current"], target: null, trend_24h: { kind: "event_count", count: 3, total: 3 } },
          { metric: "irrigation_volume", source: "manual", device_id: "", value: 2, unit: "L", quality: "valid", observed_at: "2026-09-25T11:00:00Z", states: ["current"], target: null, trend_24h: { kind: "volume_total", count: 2, total: 4.5 } },
        ],
      } });
      return route.fulfill({ status: 404, json: { detail: "Unexpected fixture request" } });
    });
    await page.goto(origin + "/e2e/fixtures/cultivation-telemetry.html");
    await expect(page.getByText("3 recorded events", { exact: true })).toBeVisible();
    await expect(page.getByText("Total 4.5 L", { exact: false })).toBeVisible();
    await expect(page.getByRole("table")).not.toContainText("avg");
    const entry = page.locator("summary", { hasText: "Record an observation or configure targets" });
    if (role === "operator") await expect(entry).toBeVisible();
    else await expect(entry).toHaveCount(0);
    expect(writes).toEqual([]);
  });
}
