import { expect, test } from "@playwright/test";

// Serve the real marketing hostname from the local preview only. No live APIs,
// operator sessions, form submissions, external analytics or production writes.
test.use({ serviceWorkers: "block" });
test.beforeEach(async ({ context, page, baseURL }) => {
  const origin = new URL(baseURL || "http://127.0.0.1:4173");
  if (!["127.0.0.1", "localhost", "[::1]"].includes(origin.hostname)) {
    throw new Error("Marketing browser tests require a loopback preview server.");
  }
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (
      url.hostname !== "doobielogic.io" ||
      request.method() !== "GET" ||
      url.pathname.startsWith("/api/")
    ) {
      await route.abort();
      return;
    }
    const response = await route.fetch({
      url: origin.origin + url.pathname + url.search,
    });
    await route.fulfill({ response });
  });
  await page.goto("http://doobielogic.io/", { waitUntil: "networkidle" });
});

for (const width of [390, 430, 768, 1024, 1440]) {
  test(`product inspection is keyboard-accessible and contained at ${width}px`, async ({ page, context }) => {
    await page.setViewportSize({ width, height: 900 });
    const previousOverflow = await page.evaluate(() => document.documentElement.style.overflow);
    await expect(page.locator(".mh-product-caption")).toBeVisible();
    await expect(page.locator(".mh-product-showcase img")).toHaveCount(1);

    for (const name of ["Buyer workspace", "Inventory workspace"]) {
      await page.getByRole("button", { name, exact: true }).click();
      const trigger = page.getByRole("link", { name: `Open full-size ${name} screenshot`, exact: true });
      await trigger.focus();
      await page.keyboard.press("Enter");
      const dialog = page.getByRole("dialog", { name, exact: true });
      await expect(dialog).toBeVisible();
      await expect(dialog).toContainText("not a live workspace.");
      await expect(dialog.getByRole("button", { name: "Close product preview" })).toBeFocused();
      await expect.poll(() => page.evaluate(() => document.documentElement.style.overflow)).toBe("hidden");

      // Native modal containment must hold across a complete keyboard cycle.
      for (let index = 0; index < 8; index += 1) {
        await page.keyboard.press("Tab");
        await expect.poll(() => dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
      }

      await dialog.getByRole("button", { name: "Zoom to full detail" }).click();
      await expect(dialog.getByRole("button", { name: "Fit to window" })).toHaveAttribute("aria-pressed", "true");
      const stage = dialog.getByRole("region");
      await expect.poll(() => stage.evaluate((node) => node.scrollWidth > node.clientWidth)).toBe(true);
      await stage.focus();
      await page.keyboard.press("ArrowRight");
      await expect.poll(() => stage.evaluate((node) => node.scrollLeft)).toBeGreaterThan(0);
      await dialog.getByRole("button", { name: "Fit to window" }).click();
      await expect(dialog.getByRole("button", { name: "Zoom to full detail" })).toHaveAttribute("aria-pressed", "false");
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);

      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(trigger).toBeFocused();
      await expect.poll(() => page.evaluate(() => document.documentElement.style.overflow)).toBe(previousOverflow);
      await expect(page.locator(".mh-product-showcase img")).toHaveCount(1);
      expect(context.pages()).toHaveLength(1);
    }

    const captionLink = page.getByRole("link", { name: "View full size", exact: true });
    await captionLink.focus();
    await page.keyboard.press("Enter");
    await page.getByRole("button", { name: "Close product preview" }).click();
    await expect(captionLink).toBeFocused();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });
}

test("operation selectors retain existing router history metadata", async ({ page }) => {
  const originalState = await page.evaluate(() => {
    const state = { ...window.history.state, homepageTest: "preserve-existing-state" };
    window.history.replaceState(state, "", window.location.href);
    return state;
  });
  for (const id of ["cultivation", "production", "retail", "vertical"]) {
    await page.locator(`#solution-${id}`).click();
    await expect(page.locator(`#solution-${id}`)).toHaveAttribute("aria-pressed", "true");
    await expect.poll(() => page.evaluate(() => window.history.state)).toEqual(originalState);
    await expect(page).toHaveURL(new RegExp(`#solution-${id}$`));
  }
});

test("operation deep links track browser back and forward", async ({ page }) => {
  await page.locator('.mh-proof-strip a[href="#solution-cultivation"]').click();
  await expect(page.locator("#solution-cultivation")).toHaveAttribute("aria-pressed", "true");
  await page.locator('.mh-proof-strip a[href="#solution-retail"]').click();
  await expect(page.locator("#solution-retail")).toHaveAttribute("aria-pressed", "true");
  await page.goBack();
  await expect(page.locator("#solution-cultivation")).toHaveAttribute("aria-pressed", "true");
  await page.goForward();
  await expect(page.locator("#solution-retail")).toHaveAttribute("aria-pressed", "true");
});

test("backdrop dismisses the viewer without leaving page scrolling locked", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const previousOverflow = await page.evaluate(() => document.documentElement.style.overflow);
  await page.getByRole("link", { name: "View full size", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.mouse.click(1, 1);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => document.documentElement.style.overflow)).toBe(previousOverflow);
});

test("a failed full-size image leaves an accessible way to close the viewer", async ({ page }) => {
  await page.route("**/marketing/buyer-workspace.webp", (route) => route.abort());
  await page.getByRole("link", { name: "View full size", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("status")).toContainText("This screenshot could not load.");
  await expect(dialog.getByRole("button", { name: "Zoom to full detail" })).toBeDisabled();
  await dialog.getByRole("button", { name: "Close product preview" }).click();
  await expect(dialog).toHaveCount(0);
});

test("browsers without native modal support keep the original image link", async ({ page, context }) => {
  await page.evaluate(() => {
    Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
      configurable: true,
      value: undefined,
    });
  });
  const popupPromise = context.waitForEvent("page");
  await page.getByRole("link", { name: "View full size", exact: true }).click();
  const popup = await popupPromise;
  await expect(popup).toHaveURL(/\/marketing\/buyer-workspace\.webp$/);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await popup.close();
});
