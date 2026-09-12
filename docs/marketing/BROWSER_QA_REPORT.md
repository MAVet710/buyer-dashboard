# Homepage browser and visual QA

Review date: 2026-09-11 (local timezone). All tests used local code and synthetic data. No production form submissions, operator actions, or customer data were used.

## Results

| Check | Result |
| --- | --- |
| Chrome at 320 / 375 / 390 / 430 / 768 / 1024 / 1440 | Pass: no document overflow, JavaScript page errors, broken anchors, or broken image loads |
| Edge at the same seven widths | Pass: same results |
| Axe WCAG 2/2.1 A and AA | Zero automated violations at all 14 browser/viewport combinations |
| Heading and metadata checks | Exactly one H1, canonical `https://doobielogic.io/`, indexable marketing metadata, valid JSON-LD |
| Keyboard mobile menu | Enter opens, Tab reaches links, Escape closes and restores menu-button focus |
| Solution navigation | All four proof-strip anchors activate matching panels; all four selectors work with Enter |
| Product showcase | Keyboard selection changes image and pressed state; full-size links remain available |
| FAQ | All seven native disclosures open and close with keyboard |
| Beta conversion | `/beta#apply` resolves; required fields and submit work with a locally intercepted accepted response |
| Login | Existing `https://ops.doobielogic.io/` destination preserved; production login was not requested |
| Reduced motion | Responsive tests ran with `prefers-reduced-motion: reduce`; content and controls remain available |
| Firefox | Not tested: downloaded Playwright Firefox cannot launch on this Windows host because its side-by-side configuration is incorrect |

Axe's final manual-review item is `color-contrast`; its earlier `aria-prohibited-attr` ambiguity was removed by giving the labelled selector containers explicit group semantics. All 14 final runs confirm that fix. Zero automated violations is not a claim of complete WCAG conformance. Keyboard behavior and viewport screenshots were independently inspected. Firefox failure is a host runtime limitation, not an observed website failure.

## Lighthouse

Production build, local HTTP server, Chrome headless. The browser mapped the marketing hostname to 127.0.0.1. The local server mirrors repository nginx robots output, asset caching, content headers, and the actual added gzip configuration. It compresses only requests accepting gzip; this is not a test-only performance setting.

| Mode | Performance | Accessibility | Best Practices | SEO | FCP | LCP | TBT | CLS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Mobile | 99 | 100 | 78 | 100 | 1.4 s | 2.0 s | 0 ms | 0 |
| Desktop | 100 | 100 | 78 | 100 | 0.3 s | 0.4 s | 0 ms | 0 |

Best Practices lost points solely because this test serves HTTP and has no HTTP-to-HTTPS redirect. These are honest local-environment results; production TLS and redirect behavior were not certified by this run. The requested Performance, Accessibility, and SEO targets were met. Best Practices >=95 still requires verification against the actual HTTPS deployment.

The initial uncompressed local production run measured mobile 78. Adding real nginx gzip, a responsive hero preload, and a small favicon raised it to 99. CSS and JS still contain some unused shared code; the final measured unused transfer estimates were about 22–24 KiB CSS and 37 KiB JS. No operator bundle was fetched by the final public homepage network trace. Initial homepage transfer in the mobile trace is about 159 KiB including the favicon request.

An earlier provisional desktop measurement accidentally used the mobile configuration; it was discarded and replaced with Lighthouse's explicit desktop configuration. A Chrome temporary-profile cleanup warning on Windows did not invalidate completed reports.

## Visual inspection

Inspected the real Chrome viewport captures at 320, 390, 768 and 1440, plus full-page captures. A final scoped override removes inherited operator-main padding from the public homepage. The complete 14-viewport browser/axe matrix and both Lighthouse modes were refreshed after this layout correction. The 1440 layout has a clear headline/CTA and a large genuine workspace below it. The 390 layout keeps the primary button full-width and visible before the product proof. At 320 the final headline fits two lines, both preview selectors remain on one line, the menu stays accessible, and controls fit. Tablet spacing keeps the workspace visible without squeezing navigation. The product image is necessarily small on a phone, but its caption and full-size link make the underlying evidence available. This is not a claim that every table cell is readable at phone thumbnail size.

The amber/dark brand, roomy hierarchy, warm lifecycle section, explicit beta status, and genuine interface imagery are retained throughout. Contact links precede the final CTA/footer, avoiding a second competing page ending. No fabricated customer proof is shown.

## Operator boundary regression caught and fixed

The first recapture after introducing lazy wrappers around App/AuthGate failed: an outer suspense retry consumed the existing pending-page selection and rendered Home with incomplete home fixtures. The orchestrator fixed startup by resolving the operator modules before mounting React, without changing operator workflows or App.initialPage.

After that fix, both actual Buyer Dashboard and Inventory captured with zero page errors. Their full-size screenshot SHA256 hashes are byte-identical to the original captures:

- Buyer: `1C3297CF3A56ABD1531B6403DEE5FC7EC50784F6C2D993C750E2F956871680C9`
- Inventory: `24EB6AAE59145965E474F570717618EA2FC6101211FEB7C3D891063045382912`

This checks the synthetic buyer/inventory rendering paths. It does not replace all application regression coverage.

## Commands and evidence

`pnpm build` ran successfully in `frontend`. Tool packages were installed into a temporary QA directory rather than application dependencies. The scripts below use explicit package locations from `PLAYWRIGHT_MODULE`, `SHARP_MODULE`, `AXE_SCRIPT`, and `QA_TOOLS` environment variables.

- `node scripts/audit-marketing-browser.mjs`: responsive/axe/metadata/screenshots. `artifacts/marketing-browser/results.json`; `chrome-*-viewport.png`, `msedge-*-viewport.png`, corresponding full-page images; `firefox-unavailable.txt`.
- `node scripts/audit-marketing-interactions.mjs`: keyboard/anchors/product/FAQ/intercepted form. `artifacts/marketing-browser/interactions.json`.
- `node scripts/audit-marketing-lighthouse.mjs`: production Lighthouse. `artifacts/marketing-browser/lighthouse-mobile.html`, `lighthouse-desktop.html`, and JSON results.
- `node scripts/capture-marketing-product.mjs`: real operator UI with existing synthetic API fixtures; public screenshots and responsive variants.
- `node scripts/capture-marketing-before.mjs`: original homepage from read-only git HEAD source overrides. `artifacts/marketing-browser/before-desktop.png`.

Raw screenshots and reports are local review artifacts. The public assets are limited to the separately reviewed marketing images.
