import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
const { chromium } = await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href);
const browser = await chromium.launch({ channel:'chrome', headless:true });
const page = await browser.newPage({ viewport:{width:390,height:844}, reducedMotion:'reduce' });
const results = [];
let submissions = 0;
await page.route('**/*', async route => {
  const url = new URL(route.request().url());
  if (url.hostname !== 'doobielogic.io') return route.abort();
  if (url.pathname === '/api/v1/beta/apply') { submissions++; return route.fulfill({ json:{accepted:true} }); }
  const response = await route.fetch({ url:(process.env.LOCAL_ORIGIN || 'http://127.0.0.1:4182') + url.pathname + url.search });
  await route.fulfill({response});
});
try {
  await page.goto('http://doobielogic.io/', {waitUntil:'networkidle'});
  const menu = page.getByRole('button',{name:'Menu',exact:true});
  await menu.focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.getByRole('button',{name:'Close',exact:true}).getAttribute('aria-expanded'),'true');
  await page.keyboard.press('Tab');
  assert.equal(await page.evaluate(()=>document.activeElement.textContent),'Platform');
  await page.keyboard.press('Escape');
  assert.equal(await menu.getAttribute('aria-expanded'),'false');
  assert.equal(await menu.evaluate(node=>node===document.activeElement),true);
  results.push('Mobile menu opens with Enter; Tab enters links; Escape closes and restores toggle focus.');
  for (const id of ['cultivation','production','retail','vertical']) {
    await page.locator(`.mh-proof-strip a[href="#solution-${id}"]`).click();
    await page.waitForFunction(id => document.getElementById('solution-'+id)?.getAttribute('aria-pressed') === 'true', id);
    assert.equal(await page.locator('#solution-'+id).getAttribute('aria-pressed'),'true');
  }
  results.push('All four proof-strip links select the matching operation panel.');
  for (const id of ['cultivation','production','retail','vertical']) {
    const button=page.locator('#solution-'+id);
    await button.focus(); await page.keyboard.press('Enter');
    assert.equal(await button.getAttribute('aria-pressed'),'true');
  }
  results.push('All four operation selectors work using keyboard Enter.');
  const inventory = page.getByRole('button',{name:'Inventory workspace',exact:true});
  await inventory.focus(); await page.keyboard.press('Enter');
  assert.equal(await inventory.getAttribute('aria-pressed'),'true');
  assert.ok((await page.locator('.mh-product-showcase img').getAttribute('src')).includes('inventory-workspace'));
  results.push('Product preview switches screenshot with keyboard.');
  const summaries = page.locator('details summary');
  for (let i=0;i<await summaries.count();i++) {
    const summary=summaries.nth(i); await summary.focus(); await page.keyboard.press('Enter');
    assert.equal(await summary.evaluate(node=>node.parentElement.open),true);
    await page.keyboard.press('Enter');
  }
  results.push(`${await summaries.count()} FAQ disclosures open and close with keyboard.`);
  const login=page.locator('nav a').filter({hasText:/Log in/});
  assert.equal(await login.getAttribute('href'),'https://ops.doobielogic.io/');
  results.push('Login links to the existing operator app; no production login request was made.');
  await page.goto('http://doobielogic.io/beta#apply',{waitUntil:'networkidle'});
  assert.equal(await page.locator('#apply').count(),1);
  await page.locator('input[name="name"]').fill('Synthetic QA Operator');
  await page.locator('input[name="email"]').fill('qa@example.invalid');
  await page.locator('input[name="company"]').fill('Synthetic QA Company');
  await page.locator('input[name="role"]').fill('Operations');
  await page.locator('select[name="operation"]').selectOption('Retail');
  await page.locator('select[name="facilities"]').selectOption('1');
  await page.locator('input[name="state"]').fill('MA');
  await page.locator('textarea[name="pain"]').fill('Synthetic local browser test of the beta application form.');
  await page.locator('input[name="consent"]').check();
  await page.getByRole('button',{name:'Submit Beta Application'}).click();
  await page.waitForTimeout(150);
  assert.equal(submissions,1);
  results.push('Beta anchor and required form controls work; submission intercepted locally with accepted response.');
  console.log(results.join('\n'));
  await fs.writeFile('artifacts/marketing-browser/interactions.json',JSON.stringify(results,null,2));
} finally { await browser.close(); }
