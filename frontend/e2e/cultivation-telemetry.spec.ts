import { expect, test } from "@playwright/test";

test.use({ channel: process.env.TELEMETRY_BROWSER_CHANNEL || undefined });
const origin = process.env.TELEMETRY_BROWSER_BASE_URL || "http://127.0.0.1:4175";
const exceptionId = "cultivation-telemetry:v1:fixture";

for (const width of [390, 1280]) {
  for (const role of ["operator", "viewer"]) {
    test(`${role} telemetry workflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const writes: string[] = [];
      let workItemId: string | null = null;
      await page.route("**/api/v1/**", async route => {
        const path = new URL(route.request().url()).pathname;
        if (route.request().method() !== "GET") writes.push(path);
        if (path.endsWith("/account/context")) return route.fulfill({ json: { user: { role } } });
        if (path.endsWith("/plants/rooms")) return route.fulfill({ json: { items: [{ id: "r1", room_code: "Flower", display_name: "Flower", active: true }] } });
        if (path.endsWith("/telemetry/rooms/r1") && route.request().method() === "GET") {
          const exception = { metric: "temperature", source: "manual", device_id: "probe", value: 30, unit: "C", quality: "valid",
            observed_at: "2026-09-25T18:00:00Z", states: ["out_of_range"], target: { minimum: 20, maximum: 25, stale_minutes: 60 },
            trend_24h: { kind: "continuous", count: 2, min: 24, max: 30, average: 27 }, exception_id: exceptionId, work_item_id: workItemId };
          return route.fulfill({ json: {
            as_of: "2026-09-25T18:05:00Z", truncated: false, exceptions: [exception], readings: [
              exception,
              { metric: "irrigation_event", source: "manual", device_id: "", value: 1, unit: "count", quality: "valid", observed_at: "2026-09-25T18:00:00Z", states: ["current"], target: null, trend_24h: { kind: "event_count", count: 3, total: 3 } },
              { metric: "irrigation_volume", source: "manual", device_id: "", value: 2, unit: "L", quality: "valid", observed_at: "2026-09-25T18:00:00Z", states: ["current"], target: null, trend_24h: { kind: "volume_total", count: 2, total: 4.5 } },
            ],
          } });
        }
        if (path.includes("/exceptions/") && path.endsWith("/work") && route.request().method() === "POST") {
          workItemId = "work-fixture";
          return route.fulfill({ json: { work_item_id: workItemId, existing: false } });
        }
        return route.fulfill({ status: 404, json: { detail: "Unexpected fixture request" } });
      });

      await page.goto(origin + `/e2e/fixtures/cultivation-telemetry.html?room=r1&telemetry=${encodeURIComponent(exceptionId)}`);
      await expect(page.getByText("3 recorded events", { exact: true })).toBeVisible();
      await expect(page.getByText("Total 4.5 L", { exact: false })).toBeVisible();
      await expect(page.getByText("Focused exception", { exact: true })).toBeVisible();
      await expect(page.getByRole("table")).toContainText("avg 27 C");

      const entry = page.locator("summary", { hasText: "Record an observation or configure targets" });
      if (role === "operator") {
        await expect(entry).toBeVisible();
        await page.getByRole("button", { name: "Create Doobie Work" }).click();
        const open = page.getByRole("link", { name: "Open Work" });
        await expect(open).toBeVisible();
        await expect(open).toHaveAttribute("href", "/work?item=work-fixture");
        expect(writes).toEqual([`/api/v1/inventory/production/plants/telemetry/rooms/r1/exceptions/${encodeURIComponent(exceptionId)}/work`]);
      } else {
        await expect(entry).toHaveCount(0);
        await expect(page.getByRole("button", { name: "Create Doobie Work" })).toHaveCount(0);
        await expect(page.getByText("Review required", { exact: true })).toBeVisible();
        expect(writes).toEqual([]);
      }
      const documentBounds = await page.evaluate(() => ({ width: window.innerWidth, scrollWidth: document.documentElement.scrollWidth }));
      expect(documentBounds.scrollWidth).toBeLessThanOrEqual(documentBounds.width + 1);
      const tableBounds = await page.locator(".inventory-panel").first().evaluate(el => {
        const wrapper = el.querySelector(".table-wrap") as HTMLElement | null;
        return { panel: el.clientWidth, wrapper: wrapper?.clientWidth ?? 0, tableScroll: wrapper?.scrollWidth ?? 0 };
      });
      expect(tableBounds.wrapper).toBeLessThanOrEqual(tableBounds.panel);
      expect(tableBounds.tableScroll).toBeGreaterThanOrEqual(tableBounds.wrapper);
    });
  }
}
