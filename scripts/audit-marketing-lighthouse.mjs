// Audit a production build locally using the marketing hostname, never production.
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { gzipSync } from 'node:zlib';
const require = createRequire(path.join(process.env.QA_TOOLS, 'package.json'));
const { default: lighthouse } = await import(pathToFileURL(require.resolve('lighthouse')).href);
const { default: desktopConfig } = await import(pathToFileURL(require.resolve('lighthouse/core/config/desktop-config.js')).href);
const launcher = await import(pathToFileURL(require.resolve('chrome-launcher')).href);
const root = path.resolve('frontend/dist');
const output = path.resolve('artifacts/marketing-browser');
await fs.mkdir(output, { recursive: true });
const mime = { '.js':'text/javascript', '.css':'text/css', '.webp':'image/webp', '.png':'image/png', '.svg':'image/svg+xml', '.html':'text/html', '.xml':'application/xml' };
const nginx = await fs.readFile('frontend/nginx.conf', 'utf8');
const robots = nginx.match(/1 "(User-agent:[^\"]+)";/)?.[1].replaceAll('\\n','\n');
const server = http.createServer(async (request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
  if (pathname === '/robots.txt') { response.writeHead(200, { 'Content-Type':'text/plain' }); response.end(robots); return; }
  const target = path.resolve(root, '.' + pathname);
  if (target !== root && !target.startsWith(root + path.sep)) { response.writeHead(400); response.end(); return; }
  let file = target;
  try { if (!(await fs.stat(file)).isFile()) file = path.join(root, 'index.html'); } catch { file = path.join(root, 'index.html'); }
  const contentType = mime[path.extname(file)] || 'application/octet-stream';
  const bytes = await fs.readFile(file);
  const compress = /gzip\s+on;/.test(nginx) && /\bgzip\b/.test(request.headers['accept-encoding'] || '') && ['text/html','text/css','text/javascript','application/javascript','application/json','application/xml','image/svg+xml'].includes(contentType);
  response.writeHead(200, { 'Content-Type':contentType, 'Cache-Control':pathname.startsWith('/assets/') ? 'public, max-age=31536000' : 'no-cache', 'X-Content-Type-Options':'nosniff', 'Referrer-Policy':'same-origin', 'Permissions-Policy':'camera=(self), microphone=(), geolocation=()', ...(compress ? {'Content-Encoding':'gzip','Vary':'Accept-Encoding'} : {}) });
  response.end(compress ? gzipSync(bytes, {level:6}) : bytes);
});
await new Promise(resolve => server.listen(4185, '127.0.0.1', resolve));
const chrome = await launcher.launch({ chromePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', chromeFlags:['--headless=new', '--no-sandbox', '--host-resolver-rules=MAP doobielogic.io 127.0.0.1', '--no-proxy-server'] });
try {
  for (const mode of ['mobile', 'desktop']) {
    const result = await lighthouse('http://doobielogic.io:4185/', { port:chrome.port, output:['json','html'], logLevel:'error', onlyCategories:['performance','accessibility','best-practices','seo'] }, mode === 'desktop' ? desktopConfig : undefined);
    await fs.writeFile(path.join(output, `lighthouse-${mode}.json`), result.report[0]);
    await fs.writeFile(path.join(output, `lighthouse-${mode}.html`), result.report[1]);
    console.log(mode, JSON.stringify({ scores:Object.fromEntries(Object.entries(result.lhr.categories).map(([name, value]) => [name, Math.round(value.score*100)])), metrics:Object.fromEntries(['first-contentful-paint','largest-contentful-paint','total-blocking-time','cumulative-layout-shift','speed-index'].map(key=>[key,result.lhr.audits[key].displayValue])), failed:Object.entries(result.lhr.audits).filter(([,audit])=>audit.score !== null && audit.score < 1).map(([id,audit])=>({id,score:audit.score,title:audit.title,displayValue:audit.displayValue})) }));
  }
} finally { try { await chrome.kill(); } catch (error) { console.warn('Chrome cleanup warning:', error.message); } server.close(); }
