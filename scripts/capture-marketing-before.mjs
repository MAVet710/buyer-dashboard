import { execFileSync } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const { chromium } = await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href);
const { default: ts } = await import(pathToFileURL(path.resolve('frontend/node_modules/typescript/lib/typescript.js')).href);
const originals = Object.fromEntries(['frontend/src/pages/MarketingHome.tsx', 'frontend/src/marketing-home.css', 'frontend/src/lib/seo.ts'].map(file => [file.replace('frontend', ''), execFileSync('git', ['show', 'HEAD:' + file], { encoding: 'utf8' })]));
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.on('pageerror', error => console.log('PAGE ERROR', error.message));
page.on('console', message => { if (message.type() === 'error') console.log(message.text()); });
await page.route('**/*', async route => {
  const url = new URL(route.request().url());
  if (url.hostname !== 'doobielogic.io') {
    if (url.pathname.endsWith('/IMG_7158.PNG')) return route.fulfill({ body: await fs.readFile('IMG_7158.PNG'), contentType: 'image/png' });
    return route.abort();
  }
  if (url.pathname in originals) {
    let code = originals[url.pathname];
    if (url.pathname.endsWith('.css')) code = `const style = document.createElement('style');style.textContent=${JSON.stringify(code)};document.head.append(style);`;
    else code = ts.transpile(code, { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }).replace(/import \{([^}]+)\} from "react\/jsx-runtime";/, (_, names) => `import runtime from "/node_modules/.vite/deps/react_jsx-runtime.js"; const {${names.replaceAll(' as ', ': ')}} = runtime;`).replaceAll('"lucide-react"', '"/node_modules/.vite/deps/lucide-react.js"');
    return route.fulfill({ body: code, contentType: 'application/javascript' });
  }
  const response = await route.fetch({ url: 'http://127.0.0.1:4182' + url.pathname + url.search });
  await route.fulfill({ response });
});
await page.goto('http://doobielogic.io/', { waitUntil: 'networkidle' });
await page.locator('h1').waitFor();
await fs.mkdir('artifacts/marketing-browser', { recursive: true });
await page.screenshot({ path: 'artifacts/marketing-browser/before-desktop.png', fullPage: true });
console.log(await page.locator('h1').innerText());
await browser.close();
