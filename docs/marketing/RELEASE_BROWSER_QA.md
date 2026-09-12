# Release browser QA

Release worktree: `.codex-worktrees/marketing-homepage-release`. Tested locally at `http://127.0.0.1:4192` with the current upstream router, storefront age gate, scanner initialization, and marketing integration. No production application requests or public form submissions were made.

## Passed checks

- Chrome and Edge at 320, 375, 390, 430, 768, 1024 and 1440px: 14/14 passed; no JavaScript page errors, document overflow, broken anchor targets, or broken images. Exactly one H1 and correct marketing canonical.
- Axe WCAG 2/2.1 A/AA: zero automated violations in all 14 runs. Color contrast remains an automated manual-review item; this is not a certification of full WCAG conformance.
- Keyboard menu opens with Enter, Tab reaches links, Escape closes and restores focus. All four operation selectors and proof-strip links activate matching panels. Product image switch works. All seven FAQs open and close with keyboard.
- Beta anchor and required form controls work. The beta submission test used a locally intercepted synthetic accepted response; no application was sent externally.
- Login href remains the existing operator app URL.
- Current repository `parity-browser.spec.ts`: 5/5 tests passed at 390, 430, 768, 1024 and 1440px in 27 seconds, using installed @playwright/test and the Chrome channel. The test mocks backend responses; it does not exercise production state.
- Read-only route isolation smoke: marketing root, beta, `/store/qa-demo`, `qa-demo.doobielogic.io`, `/portal/qa-token`, and `ops.doobielogic.io` all render their proper surfaces with zero page errors and zero write requests.
- Both storefront routes show the age gate before the catalog, and issue zero catalog requests before synthetic age confirmation. After confirmation the synthetic storefront catalog renders. No order was created.
- The private portal renders the synthetic retail partner. Operator startup redirects to `/buying` and renders Buyer Dashboard. No marketing homepage leaks into either surface.
- Homepage/beta retain indexable robots metadata; storefront, private portal and operator pages retain noindex metadata.
- Fresh real Chrome screenshots at 320px and 1440px were visually inspected. Headline, primary CTA, menu, preview controls and content fit without clipping. The final public main-padding isolation is retained.

Firefox was downloaded previously but cannot launch on this Windows host because of an incorrect/missing side-by-side runtime configuration. Firefox is untested, not passed. Public live TLS, hosted redirect behavior and deployed performance are outside these local checks.

## Commands

From the release worktree root, with bundled package locations supplied through PLAYWRIGHT_MODULE and AXE_SCRIPT and LOCAL_ORIGIN set to http://127.0.0.1:4192:

- `node scripts/audit-marketing-browser.mjs` — passed Chrome/Edge matrix; recorded Firefox runtime limitation.
- `node scripts/audit-marketing-interactions.mjs` — passed all interactions with locally intercepted beta submission.
- `node frontend/node_modules/@playwright/test/cli.js test --config artifacts/release-qa/playwright.config.mjs parity-browser.spec.ts` — 5 passed.
- `node artifacts/release-qa/route-smoke.mjs` — 6 route modes passed, all APIs mocked and write requests blocked.

## Evidence

- `artifacts/marketing-browser/results.json`
- `artifacts/marketing-browser/interactions.json`
- `artifacts/marketing-browser/chrome-320-viewport.png`
- `artifacts/marketing-browser/chrome-1440-viewport.png`
- Chrome/Edge screenshots for all requested widths in the same directory
- `artifacts/release-qa/route-smoke.json` and six route screenshots
- `artifacts/release-qa/parity/` test evidence

The existing BROWSER_QA_REPORT.md describes the earlier implementation audit and Lighthouse measurements. Those numbers should not be relabeled as measurements of this rebased release until rerun on its production build. This report records the release-specific checks above.
