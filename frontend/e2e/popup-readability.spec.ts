import { test, expect } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";

test.use({ channel: process.platform === "win32" ? "chrome" : undefined, baseURL: "http://127.0.0.1:4197", video: "off" });
const baseline = process.env.POPUP_BASELINE === "1";
const phase = baseline ? "before" : "after";
const evidence = "tmp/popup-readability";
mkdirSync(evidence, { recursive: true });

test("fixture imports the real app CSS in order", () => {
  const app = [...readFileSync("src/main.tsx", "utf8").matchAll(/import "\.\/([^"\n]+\.css)";/g)].map(match => match[1]);
  const fixture = [...readFileSync("e2e/fixtures/popup-readability-entry.tsx", "utf8").matchAll(/import "\.\.\/\.\.\/src\/([^"\n]+\.css)";/g)].map(match => match[1]);
  expect(fixture).toEqual(app);
});

for (const width of [390, 1280]) for (const theme of ["dark", "light"]) {
  test(`${phase} ${theme} ${width}: surfaces and window controls`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const unexpected: string[] = [];
    await page.route("**/*", route => {
      const url = new URL(route.request().url());
      if (url.origin !== "http://127.0.0.1:4197" || url.pathname.startsWith("/api")) { unexpected.push(url.origin + url.pathname); return route.abort(); }
      return route.continue();
    });
    async function open(path: string) {
      await page.goto(path);
      await page.evaluate(value => document.documentElement.dataset.theme = value, theme);
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    }
    const records: unknown[] = [];
    async function capture(name: string, selectors: string[]) {
      const values = await page.evaluate(selectors => {
        const rgba = (value: string) => { const n = value.match(/[\d.]+/g)?.map(Number) ?? []; return [n[0] ?? 0,n[1] ?? 0,n[2] ?? 0,n[3] ?? 1]; };
        const mix = (front: number[], back: number[]) => [...front.slice(0,3).map((v,i)=>v*front[3]+back[i]*(1-front[3])), front[3]+back[3]*(1-front[3])];
        const lum = (c: number[]) => c.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
        return selectors.map(selector => {
          const element = document.querySelector(selector)!;
          const style = getComputedStyle(element);
          let effective = [0,0,0,0], opacity = 1;
          let current: Element | null = element;
          while (current) {
            const css = getComputedStyle(current);
            let bg = rgba(css.backgroundColor);
            const gradient = css.backgroundImage.match(/rgba?\([^)]+\)/g);
            if (gradient?.length) bg = rgba(gradient[0]);
            effective = mix(effective, bg);
            opacity *= Number(css.opacity);
            current = current.parentElement;
          }
          const fg = rgba(style.color), renderedText = mix(fg,effective);
          const contrast = (Math.max(lum(renderedText),lum(effective))+.05)/(Math.min(lum(renderedText),lum(effective))+.05);
          return { selector, background:style.backgroundColor, image:style.backgroundImage, ownAlpha:rgba(style.backgroundColor)[3], effectiveAlpha:effective[3], textAlpha:fg[3], opacity, contrast, surface:style.getPropertyValue("--surface").trim(), popupSurface:style.getPropertyValue("--dl-popup-surface").trim() };
        });
      }, selectors);
      records.push({ name, values });
      await page.screenshot({ path:`${evidence}/${phase}-${theme}-${width}-${name}.png`, fullPage:true });
      if (!baseline) for (const value of values) {
        if ([".workspace-window", ".workspace-window-footer", ".workspace-window .view-tabs", ".global-search-results", ".multi-select-menu", ".commerce-launcher-window", ".modal-heading"].includes(value.selector)) expect(value.ownAlpha, value.selector).toBe(1);
        expect(value.effectiveAlpha, value.selector).toBe(1);
        expect(value.opacity, value.selector).toBe(1);
        expect(value.textAlpha, value.selector).toBe(1);
        expect(value.contrast, value.selector).toBeGreaterThanOrEqual(4.5);
      }
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    }
    await open("/e2e/fixtures/popup-readability.html");
    await capture("workspace", [".workspace-window", ".workspace-window-heading h2", ".workspace-window-heading p", ".workspace-window-footer", ".workspace-window .view-tabs", ".workspace-window input", ".workspace-window th", ".workspace-window td", ".workspace-window .secondary", ".workspace-window-footer .secondary", ".workspace-window-close", ".workspace-window .view-tabs button:not(.active)"]);
    if (width===1280) {
      const window = page.locator(".workspace-window");
      const before = await window.boundingBox();
      const header = await page.locator(".workspace-window-heading").boundingBox();
      await page.mouse.move(header!.x+20,header!.y+20); await page.mouse.down(); await page.mouse.move(header!.x-80,header!.y+70,{steps:5}); await page.mouse.up();
      expect((await window.boundingBox())!.x).toBeLessThan(before!.x);
      await page.getByRole("button",{name:"Maximize window"}).click(); await expect(window).toHaveClass(/maximized/);
      await page.getByRole("button",{name:"Restore window"}).click();
      await page.getByRole("button",{name:"Minimize window"}).click(); await expect(page.locator(".workspace-window-body")).toBeHidden();
      await page.getByRole("button",{name:"Restore window"}).click(); await expect(page.locator(".workspace-window-body")).toBeVisible();
    }
    await page.getByRole("button",{name:"Open nested window"}).click();
    await expect(page.getByRole("dialog",{name:"Nested window",exact:true})).toBeVisible();
    await capture("nested", ['[data-window-key="nested-readability"]', '[data-window-key="nested-readability"] p']);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog",{name:"Nested window",exact:true})).toHaveCount(0);
    await expect(page.getByRole("dialog",{name:"Doobie workspace",exact:true})).toBeVisible();
    await page.getByRole("button",{name:"Open detail",exact:true}).click();
    await capture("dialog",[".modal", ".modal-heading", ".modal-heading h2", ".modal-heading p", ".modal input", ".modal th", ".modal td", ".modal .secondary"]);
    await page.locator(".modal").evaluate(el=>el.scrollTop=200);
    await capture("dialog-scrolled",[".modal-heading h2", ".modal-heading p"]);
    await page.locator(".modal").getByRole("button",{name:"Close",exact:true}).click();
    await expect(page.locator(".modal")).toHaveCount(0);
    await page.getByRole("button",{name:"Open detail",exact:true}).click();
    // Existing components both listen for Escape. Preserve and record that
    // a dialog nested in a window closes both; this CSS task changes no handlers.
    await page.keyboard.press("Escape"); await expect(page.locator(".workspace-window")).toHaveCount(0);
    for (const mode of ["menus","commerce"]) {
      await open(`/e2e/fixtures/popup-readability.html?mode=${mode}`);
      await capture(mode,mode==="menus"?[".global-search-results", ".global-search-results small", ".multi-select-menu", ".multi-select-menu label", ".multi-select-control summary"]:[".commerce-launcher-window", ".commerce-launcher-window th", ".commerce-launcher-window td"]);
    }
    expect(unexpected).toEqual([]);
    writeFileSync(`${evidence}/${phase}-${theme}-${width}.json`,JSON.stringify(records,null,2));
  });
}

test("solid fallback survives missing popup and theme surface tokens", async ({ page }) => {
  test.skip(baseline, "The baseline has no fallback.");
  await page.goto("/e2e/fixtures/popup-readability.html");
  await page.evaluate(() => {
    document.documentElement.style.setProperty("--dl-popup-surface", "initial");
    document.documentElement.style.setProperty("--dl-surface-solid", "initial");
  });
  await expect(page.locator(".workspace-window")).toHaveCSS("background-color", "rgb(17, 20, 18)");
  await page.getByRole("button",{name:"Open detail",exact:true}).focus();
  await expect(page.getByRole("button",{name:"Open detail",exact:true})).toBeFocused();
});
