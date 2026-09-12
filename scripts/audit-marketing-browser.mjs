// Browser checks against a local homepage build, preserving the public hostname.
// PLAYWRIGHT_MODULE: absolute Playwright entry file. LOCAL_ORIGIN: local Vite URL.
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const { chromium, firefox } = await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href);
const local = process.env.LOCAL_ORIGIN || 'http://127.0.0.1:4182';
const output = path.resolve('artifacts/marketing-browser');
await fs.mkdir(output, { recursive: true });
const results = [];
for (const channel of ['chrome', 'msedge', 'firefox']) {
  let browser;
  try { browser = channel === 'firefox' ? await firefox.launch({headless:true}) : await chromium.launch({ channel, headless: true }); }
  catch (error) { await fs.writeFile(path.join(output, `${channel}-unavailable.txt`), error.message); console.warn(channel, error.message); continue; }
  for (const width of [320, 375, 390, 430, 768, 1024, 1440]) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce' });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('http://doobielogic.io/**', async route => {
      const original = new URL(route.request().url());
      const response = await route.fetch({ url: local + original.pathname + original.search });
      await route.fulfill({ response });
    });
    await page.goto('http://doobielogic.io/', { waitUntil: 'networkidle' });
    await page.evaluate(async () => {
      for (let y = 0; y < document.documentElement.scrollHeight; y += 700) {
        window.scrollTo(0, y);
        await new Promise(resolve => setTimeout(resolve, 30));
      }
      window.scrollTo(0, 0);
    });
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: path.join(output, `${channel}-${width}-viewport.png`), fullPage: false, animations: 'disabled' });
    const result = await page.evaluate(() => ({
      title: document.title,
      h1: [...document.querySelectorAll('h1')].map(node => node.textContent),
      headings: [...document.querySelectorAll('h2,h3')].map(node => [node.tagName, node.textContent]),
      overflow: document.documentElement.scrollWidth > innerWidth + 1,
      brokenAnchors: [...document.querySelectorAll('a[href^="#"]')].filter(node => node.hash.length > 1 && !document.getElementById(decodeURIComponent(node.hash.slice(1)))).map(node => node.getAttribute('href')),
      images: [...document.images].map(node => ({ src: node.getAttribute('src'), alt: node.alt, loaded: node.complete && node.naturalWidth > 0 })),
      canonical: document.querySelector('link[rel="canonical"]')?.getAttribute('href'),
      robots: document.querySelector('meta[name="robots"]')?.getAttribute('content'),
      schema: [...document.querySelectorAll('script[type="application/ld+json"]')].map(node => { try { return JSON.parse(node.textContent); } catch { return 'INVALID JSON'; } }),
    }));
    await page.keyboard.press('Tab');
    result.firstKeyboardTarget = await page.evaluate(() => ({ tag: document.activeElement?.tagName, text: document.activeElement?.textContent, href: document.activeElement?.getAttribute('href') }));
    if (process.env.AXE_SCRIPT) {
      await page.addScriptTag({ path: process.env.AXE_SCRIPT });
      result.accessibility = await page.evaluate(async () => {
        const result = await window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] } });
        return { violations: result.violations.map(({ id, impact, description, nodes }) => ({ id, impact, description, nodes: nodes.map(({ html, failureSummary }) => ({ html, failureSummary })) })), incomplete: result.incomplete.map(({ id }) => id), passes: result.passes.length };
      });
    }
    await page.screenshot({ path: path.join(output, `${channel}-${width}.png`), fullPage: true, animations: 'disabled' });
    results.push({ channel, width, errors, ...result });
    await page.close();
  }
  await browser.close();
  await fs.writeFile(path.join(output, 'results.json'), JSON.stringify(results, null, 2));
}
await fs.writeFile(path.join(output, 'results.json'), JSON.stringify(results, null, 2));
console.log(JSON.stringify(results.map(({ channel, width, errors, overflow, h1, brokenAnchors, images, canonical }) => ({ channel, width, errors, overflow, h1Count: h1.length, brokenAnchors, brokenImages: images.filter(image => !image.loaded), canonical })), null, 2));
if (results.some(result => result.errors.length || result.overflow || result.h1.length !== 1 || result.brokenAnchors.length)) process.exitCode = 1;
