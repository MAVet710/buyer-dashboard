// Capture the real operator UI with the repository's synthetic browser fixtures.
// Requires a local Vite server and PLAYWRIGHT_MODULE / SHARP_MODULE paths.
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import { pathToFileURL } from 'node:url';
const repo = process.cwd();
const { chromium } = await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href);
const { default: sharp } = await import(pathToFileURL(process.env.SHARP_MODULE).href);
const { default: ts } = await import(pathToFileURL(path.join(repo, 'frontend/node_modules/typescript/lib/typescript.js')).href);
const source = await fs.readFile(path.join(repo, 'frontend/e2e/parity-browser.spec.ts'), 'utf8');
const fixtures = source.slice(source.indexOf('const accountContext'), source.indexOf('async function setPage'));
const js = ts.transpile(fixtures, { target: ts.ScriptTarget.ES2022 });
const context = { URL, JSON };
vm.createContext(context);
vm.runInContext(js + ';globalThis.install = installApiMocks;', context);
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
await page.route('**/*', async route => {
  const url = new URL(route.request().url());
  if (url.hostname === '127.0.0.1') return route.continue();
  if (url.pathname.endsWith('/IMG_7158.PNG')) return route.fulfill({ body: await fs.readFile(path.join(repo, 'IMG_7158.PNG')), contentType: 'image/png' });
  return route.abort();
});
await context.install(page);
await page.addInitScript(() => {
  localStorage.setItem('buyer-dash-theme', 'dark');
  localStorage.setItem('buyer-dash-organization', 'org-parity');
  localStorage.setItem('buyer-dash-facility', 'facility-parity');
  localStorage.setItem('buyer-dash-data-mode', 'Uploads');
  localStorage.setItem('buyer-dash-operation', 'Retail Ops');
  if (!sessionStorage.getItem('buyer-dash-pending-page')) sessionStorage.setItem('buyer-dash-pending-page', 'Buyer Operations');
});
await page.goto(process.env.CAPTURE_URL || 'http://127.0.0.1:4182/', { waitUntil: 'networkidle' });
try { await page.getByRole('heading', { name: 'Buyer Dashboard', exact: true }).waitFor(); }
catch (error) { console.log('Capture startup errors:', errors, await page.locator('body').innerText()); await browser.close(); throw error; }
for (const [name, pageName] of [['buyer-workspace', 'Buyer Operations'], ['inventory-workspace', 'Inventory']]) {
  if (pageName === 'Inventory') {
    await page.evaluate(() => sessionStorage.setItem('buyer-dash-pending-page', 'Inventory'));
    await page.reload({ waitUntil: 'networkidle' });
    await page.getByRole('heading', { name: 'Inventory', exact: true }).waitFor();
  }
  const bytes = await page.screenshot({ animations: 'disabled' });
  await sharp(bytes).webp({ quality: 88 }).toFile(path.join(repo, 'frontend/public/marketing', name + '.webp'));
  for (const width of [480, 960]) await sharp(bytes).resize(width).webp({ quality: 85 }).toFile(path.join(repo, 'frontend/public/marketing', `${name}-${width}.webp`));
  console.log(name, await page.locator('body').innerText());
}
console.log('Page errors:', errors);
await browser.close();
