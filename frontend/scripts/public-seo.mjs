// Emit crawler-readable public metadata from the same contract used by React.
// No application/tenant routes are generated and no extra browser JS is added.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import ts from 'typescript';
const root = new URL('../', import.meta.url);
const dataModule = code => 'data:text/javascript;base64,' + Buffer.from(code).toString('base64');
const compile = async path => ts.transpileModule(await readFile(new URL(path, root), 'utf8'), {compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const metadata = dataModule(await compile('src/lib/advisorySeo.ts'));
const content = dataModule(await compile('src/components/marketing/content.ts'));
const seoModule = (await compile('src/lib/seo.ts')).replace('"./advisorySeo"', JSON.stringify(metadata)).replace('"../components/marketing/content"', JSON.stringify(content));
const {seoPage,marketingStructuredData} = await import(dataModule(seoModule));
const {advisoryRoutes} = await import(metadata);
const dist = resolve(process.argv[2] || new URL('../dist', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'));
const original = await readFile(resolve(dist,'index.html'),'utf8');
const escape = value => value.replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;').replaceAll('>','&gt;');
for (const path of Object.keys(advisoryRoutes).filter(path => path.startsWith('/consulting') || path.startsWith('/resources') || path.startsWith('/tools/'))) {
  const page = seoPage(true,path);
  let html = original.replace(/<title>[\s\S]*?<\/title>/i, `<title>${escape(page.title)}</title>`)
    .replace(/<meta\s+(?:name="(?:description|robots|googlebot|twitter:[^"]+)"|property="og:[^"]+")[^>]*>/gi,'')
    .replace(/<link\s+rel="canonical"[^>]*>/gi,'');
  const tags = [
    `<meta name="description" content="${escape(page.description)}">`,
    `<meta name="robots" content="${escape(page.robots)}">`,
    `<link rel="canonical" href="${page.canonical}">`,
    ...Object.entries({'og:type':page.kind==='article'?'article':'website','og:title':page.title,'og:description':page.description,'og:url':page.canonical,'og:site_name':'DoobieLogic','og:image':'https://doobielogic.io/doobielogic-logo.webp'}).map(([name,value])=>`<meta property="${name}" content="${escape(value)}">`),
    `<meta name="twitter:card" content="summary">`,
    `<script id="doobielogic-software-schema" type="application/ld+json">${JSON.stringify(marketingStructuredData(path)).replaceAll('<','\\u003c')}</script>`,
  ];
  html=html.replace('</head>',tags.join('\n')+'\n</head>');
  const target=resolve(dist,path.slice(1),'index.html');
  await mkdir(dirname(target),{recursive:true});await writeFile(target,html);
}
console.log('Public advisory route metadata emitted.');
