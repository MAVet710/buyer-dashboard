import { expect, test } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:4191", channel: process.platform === "win32" ? "chrome" : undefined, video: "off" });
const fixture = "/e2e/fixtures/cultivation-radio.html";
for (const width of [390, 1280]) {
  test(`select supported sensor and see actual saved room evidence ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    page.on("pageerror", () => errors.push("page_runtime_error"));
    await page.goto(fixture);
    const find = page.getByRole("button", { name: "Find sensors", exact: true });
    await expect(find).toBeDisabled();
    await page.getByLabel("I am authorized to identify sensors at this facility.").check();
    await find.click();
    await page.getByRole("button", { name: "Select Synthetic canopy sensor", exact: true }).click();
    await expect(page.getByRole("button", { name: "Select Encrypted fixture", exact: true })).toHaveCount(0);
    await expect(page.getByText("Encrypted sensor. A supported pairing method is required.", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Connect sensor", exact: true })).toBeDisabled();
    await page.getByRole("combobox", { name: "Room", exact: true }).selectOption({ label: "Synthetic room A" });
    await page.getByLabel("This is my facility's sensor and I authorize read-only collection.").check();
    const linkedResponse = page.waitForResponse(r => r.url().endsWith("/cultivation-radio/connections") && r.request().method() === "POST");
    await page.getByRole("button", { name: "Connect sensor", exact: true }).click();
    const response = await linkedResponse;
    expect(response.status()).toBe(200);
    const linked = await response.json();
    expect(linked.status).toBe("awaiting_reading");
    await expect(page.getByText("Receiving readings", { exact: true })).toBeVisible({ timeout: 30000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);
    await page.screenshot({ path: info.outputPath(`radio-linked-${width}.png`) });
    await page.getByRole("link", { name: "Open Room 360", exact: true }).click();
    await page.getByRole("button", { name: "Environment", exact: true }).click();
    const readings = page.getByRole("region", { name: "Latest sensor readings", exact: true });
    await expect(readings.getByText("25 C", { exact: true })).toBeVisible();
    await expect(readings.getByText("50.55 %", { exact: true })).toBeVisible();
    await page.screenshot({ path: info.outputPath(`radio-room-${width}.png`) });
    await page.goto(fixture);
    await page.getByText("Disconnect sensor", { exact: true }).click();
    await page.getByRole("button", { name: "Confirm disconnect Synthetic canopy sensor", exact: true }).click();
    await expect(page.getByText("Disconnected", { exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });
}
