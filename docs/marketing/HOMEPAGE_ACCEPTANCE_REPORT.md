# DoobieLogic homepage rebuild — acceptance report

Date: 2026-09-11. Baseline commit: `1de2d511b8dd9df1b41336e51a507211bd95950f`.

**Initial local acceptance record.** See RELEASE_EXECUTION.md for the subsequent user-authorized integration and deployment. At this initial review the changes were not deployed. The public homepage has been rebuilt around operation type, real product evidence and truthful beta positioning. The operator application's business logic, auth rules, database and AI authority were not changed. Unrelated pre-existing AI runtime edits remain untouched.

## Before vs after

| Before | After |
|---|---|
| Long feature-list headline | Short outcome headline with explicit cannabis ERP category and beta status |
| Buying/extraction/module-first structure | Cultivation, Production / Manufacturing, Retail Operations and Vertically Integrated pathways |
| Constructed dashboard labeled live with illustrative sync/compliance scores | Real Buyer and Inventory UI captures with synthetic demo data, clearly labeled beta; full-size inspection links |
| Desktop navigation disappeared at narrow widths | Keyboard-accessible mobile menu, visible focus, Escape focus restoration and anchored solution selection |
| Broad integration/audit language | Explicit Metrc validation status, bounded controls and operation-specific fit review |
| Limited evaluation content | Lifecycle story, read-only AI explanation, integration readiness, onboarding process, seven FAQs and deeper real navigation |
| Shared operator scripts blocked marketing startup | Operator modules load separately; marketing skips scanner dependencies; responsive image preload, smaller icon and actual nginx gzip |
| No formal claim/evidence inventory | Proof ledger, claim audit, competitive research, buyer review, source-backed screenshots and approval-gated customer-proof components |

Existing charcoal/copper identity, logo, serif wordmark, operator voice, application login and beta conversion flow are retained. The warm lifecycle section adds visual contrast without replacing the brand with generic enterprise styling.

## Positioning

- **H1:** Your operation. One clear picture.
- **Subheadline:** Cannabis ERP in beta for cultivation, production, retail and vertically integrated teams. Bring the work into view, from the grow room to the next buying decision.
- **Primary CTA:** Apply for beta.
- **Secondary CTA:** See the workspace.
- **Access qualification:** For licensed operations. Access follows beta fit review.

Three hero directions were considered in `HOMEPAGE_REBUILD_CONTROL.md`; the selected outcome-led direction gives the product and operation pathways room. No measured efficiency gain or general-availability promise is implied.

## Final section order

1. Public navigation with beta and login actions.
2. Outcome-led hero and beta qualification.
3. Real product showcase: Buyer / Inventory, synthetic data, full-size links.
4. Four-operation navigation band.
5. Fragmented tools / shared operational context.
6. Operation-specific solution selectors and detail.
7. Vertical lifecycle evaluation map.
8. Facility context, role access, supported action records and compliance scope.
9. Doobie Agent as beta intelligence within the operational platform.
10. Integration readiness: Metrc validation, beta data flows, existing-stack review.
11. Three-step beta evaluation and onboarding.
12. FAQs and existing beta-program/data-use resources.
13. Existing contact channels.
14. Final beta invitation.
15. Expanded footer with working destinations.

No placeholder testimonials or customer-logo bands render. Reusable evidence-gated components and styles are ready for approved content. No fabricated legal or educational destinations were created.

## Competitive gap addressed

| Benchmark | Principle applied | Honest remaining gap |
|---|---|---|
| Canix | Outcome-led hero, direct operator segmentation, evidence beside the product | No approved customer result or commercial-scale metric |
| Distru | Concrete operational paths and workflow language | Current genuine screenshots are retail; more production evidence would help |
| Flourish | Connected lifecycle, integration evaluation and resource navigation | Complete public guides and mature integration ecosystem are not established |
| 365 Cannabis | ERP category, executive context and adoption discussion | No inferred enterprise rollout, platform partnership or certification |
| Cova | Specific retail story, clear human contact and onboarding steps | No uptime, support SLA or POS-replacement claims |
| LeafLink / Apex | Different routes for different operators; commercial handoffs remain visible | No marketplace reach or wholesale transaction-volume claims |
| BLAZE / Trym | Workflow specificity, operational personality and clear next steps | No unsupported sensor, hardware or implementation-speed claims |

`COMPETITIVE_HOMEPAGE_RESEARCH.md` includes primary-source links for all nine benchmarks and actual visual inspection of six core competitors plus the live DoobieLogic baseline. This report does not claim visual superiority, conversion uplift or exact imitation. The local baseline source and live website differed slightly; both are distinguished in the research.

## Claim audit

**VERIFIED:** actual beta application route/process; configured contact/login destinations; sanitized screenshot provenance; bounded facility/role/action-record architecture; read-only AI runtime distinction.

**SUPPORTED_BUT_BETA:** operational workspaces and their described features, multi-facility evaluation, production/retail/cultivation workflows, operational AI and data imports/exports. Beta status is explicit.

**Validation:** Metrc is described as in validation. No production-ready, two-way, certified or all-state integration is claimed.

**Removed / excluded:** simulated live sync indicators, compliance score/pass status, blanket full traceability/audit-readiness claims, invented customer evidence, savings, scale, supported-state totals, founder biography and unavailable integrations. Cultivation copy was narrowed to plant/room/phase context, estimated harvest dates and plant history.

See `MARKETING_PROOF_LEDGER.md` and `HOMEPAGE_CLAIM_AUDIT.md` for classifications, dates, public-use eligibility and evidence. Existing beta-page marketing beyond the successful-submit analytics hook was outside this homepage rewrite.

## Performance

Production bundle served locally with repository nginx compression, robots and caching behavior reproduced; Chrome resolved the marketing hostname to localhost. This is **local measurement**, not a live deployment audit.

| Lighthouse mode | Performance | Accessibility | Best Practices | SEO | FCP | LCP | TBT | CLS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Mobile | 99 | 100 | 78 | 100 | 1.4 s | 2.0 s | 0 ms | 0 |
| Desktop | 100 | 100 | 78 | 100 | 0.3 s | 0.4 s | 0 ms | 0 |

Performance, Accessibility and SEO targets were met. **Best Practices >=95 is not signed off:** the local HTTP test lacks HTTPS and its redirect. Those are the measured deductions; production TLS/redirect verification remains necessary. Nginx configuration was reviewed and its relevant serving behavior mirrored, but native nginx runtime validation was unavailable in this Windows environment.

Final main bundle: approximately 254.79 KB / 79.98 KB gzip. Shared CSS: 140.49 KB / 27.81 KB gzip. No operator bundle was fetched by the public homepage trace. Two responsive product-image families use 480 / 960 / 1440 widths; the navbar icon is about 5 KB. Shared unused CSS remains intentionally retained to preserve the operator and beta cascade.

## Accessibility, mobile and browser results

Chrome and Edge passed at **320, 375, 390, 430, 768, 1024 and 1440 px**: no document overflow, broken anchors, broken image loads or JavaScript page errors; one H1 and valid metadata/schema. Axe reported **zero automated WCAG A/AA violations in all 14 runs**. Native disclosures, semantic control groups, focus outlines and reduced-motion handling are implemented. Gradient/image contrast retains a manual-review flag; automated scores are not complete WCAG certification.

Keyboard tests covered menu open/Tab/Escape/focus restoration, all solution selectors and deep links, product switching, all seven FAQs, beta navigation and required form controls. Beta submission used a fully intercepted synthetic response; no production application or email was sent. Login destination is preserved without attempting production login.

Firefox was installed for testing but could not launch because the Windows side-by-side runtime was unavailable. It is recorded as **not tested**, not passed. The 320/390/768/1440 viewport images and full-page layouts were visually inspected. The final public main padding override isolates the homepage from an operator stylesheet's global `!important` padding.

## Operator boundary verification

A regression check caught Suspense retry consuming the existing pending-page selection. The fix resolves App/AuthGate imports before mounting the operator tree; their behavior and source remain unchanged. Post-fix Buyer and Inventory synthetic captures have identical SHA256 hashes to the original captures, with zero page errors. Scanner tests verify sequential dependency setup, errors settling, no marketing initialization and setup before operator mount. This is targeted regression evidence, not a complete operational acceptance suite.

## Tests and exact commands

| Command (from repository root unless specified) | Result |
|---|---|
| `cd frontend` then `pnpm lint` | PASS: zero errors; four pre-existing hook warnings in AdminToolsPage, ExtractionPage and IntegrationsPage |
| `cd frontend` then `pnpm test` | PASS: 38 tests across eight files |
| `cd frontend` then `pnpm build` | PASS: TypeScript and Vite production build |
| `node scripts/audit-marketing-browser.mjs` | PASS: 14 Chrome/Edge viewport runs; Firefox runtime unavailable |
| `node scripts/audit-marketing-interactions.mjs` | PASS: keyboard, navigation, product, FAQ and intercepted beta conversion |
| `node scripts/audit-marketing-lighthouse.mjs` | COMPLETED: actual scores above; HTTP environment limitation retained |
| `node scripts/capture-marketing-product.mjs` | PASS: actual synthetic operator captures; unchanged final hashes |
| `node scripts/capture-marketing-before.mjs` | PASS: baseline capture from read-only git source overrides |

QA scripts use explicit `PLAYWRIGHT_MODULE`, `SHARP_MODULE`, `AXE_SCRIPT` and `QA_TOOLS` environment paths to bundled/temporary tool installations. They add no application dependency. Reproduction and evidence details are in `BROWSER_QA_REPORT.md` and `PRODUCT_EVIDENCE.md`.

## Files changed

Application / public serving:

- `frontend/src/pages/MarketingHome.tsx`
- `frontend/src/marketing-home.css`
- `frontend/src/main.tsx` — loading/marketing contact placement only; operator modules resolve before initial mount
- `frontend/src/pages/BetaPartnerPage.tsx` — successful-submit analytics event only
- `frontend/src/lib/seo.ts`
- `frontend/src/lib/marketingAnalytics.ts`
- `frontend/index.html`
- `frontend/nginx.conf`
- `frontend/public/sitemap.xml`

Marketing components/data and tests:

- `frontend/src/components/marketing/MarketingNav.tsx`
- `frontend/src/components/marketing/ProductShowcase.tsx`
- `frontend/src/components/marketing/Solutions.tsx`
- `frontend/src/components/marketing/content.ts`
- `frontend/src/components/marketing/CustomerProof.tsx`
- `frontend/src/components/marketing/customerProofData.ts`
- `frontend/src/components/marketing/CustomerProof.test.tsx`
- `frontend/src/lib/marketingAnalytics.test.ts`
- `frontend/src/lib/seo.test.ts`
- `frontend/src/lib/scannerBootstrap.test.ts`

Assets: `frontend/public/marketing/brand.webp`, `apple-touch180.png`, `doobielogic-brand.png`, and Buyer/Inventory screenshot families (`*-workspace.webp`, `*-workspace-480.webp`, `*-workspace-960.webp`).

QA tooling: `scripts/capture-marketing-product.mjs`, `capture-marketing-before.mjs`, `audit-marketing-browser.mjs`, `audit-marketing-interactions.mjs`, `audit-marketing-lighthouse.mjs`.

Documentation: all ten reports in `docs/marketing/`: this report, rebuild control, competitive research, proof ledger, claim audit, product evidence, SEO/analytics/proof implementation, buyer review, browser QA and content roadmap. Review artifacts are under `artifacts/marketing-browser/`; pre-existing unrelated artifacts were preserved.

## Remaining marketing assets / follow-up evidence

- Approved customer logos, attributed testimonials and measured case studies.
- Additional cultivation, manufacturing/extraction and vertical-workflow captures with sanitized data.
- Professional product walkthrough video.
- Approved founder/origin copy; photography only if that section is pursued.
- Reviewed public privacy, terms and security/assurance pages, plus substantive educational/product-update content.
- Documented live integration acceptance, supported-market evidence or partnerships before stronger claims are added.
- Production HTTPS Lighthouse/redirect verification and Firefox verification on a working host.

No paid analytics service is installed. The adapter is swappable and a no-op without an explicit provider plus consent; it honors DNT/GPC and excludes form values and identifiers. No conversion lift is claimed. No commit, deployment or production configuration mutation was performed.
