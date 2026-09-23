# Consulting implementation report

Prepared 2026-09-19 from the active integration source and recorded validation evidence. This is the requested 17-item implementation handoff. Final deployment verification and Git identity are recorded by the release lead; this report does not invent them.

## 1. Existing design system discovered

The audit found a charcoal canvas (`#0c0e0f`), warm off-white text (`#f2eee8`), copper emphasis (`#f69a5b`) and a warm stone relief section. Green is contextual, not the primary public accent. The current homepage, rather than an older beta design from another branch, was the baseline. Typography uses the existing Inter/system stack. The audit gate was accepted before implementation. [DESIGN_SYSTEM_AUDIT.md](DESIGN_SYSTEM_AUDIT.md) retains its historical pre-implementation status.

No new brand palette or font family was introduced. Header, footer, buttons and cards extend the existing public design. The homepage receives an additive consulting section rather than a rebrand.

## 2. Components reused

Reused `MarketingBrand`, `MarketingNav`, existing homepage typography, CTA styles, integration-card grid, content widths, section spacing, public contact details and footer content. The shared footer retains software/operator destinations while adding consulting/resources and optional measurement consent. Mobile menu Escape/focus behavior, skip links and sticky-header anchor spacing remain consistent. Existing software homepage and beta positioning remain separate from advisory services.

## 3. New components added and why

`MarketingPage` and `ConsultationCTA` provide a consistent shell and contextual next step. `ConsultingPages` renders the hub, seven service/diagnostic pages, resource library and three articles from typed content. `ConsultingLeadForm` owns validation, intake, retry and confirmed success. `AdvisoryTools` provides the assessment and local CSV workflow. `AnalyticsConsent` gives the optional event collection an explicit control.

Service data lives in `consultingServices.ts`; article data in `consultingContent.ts`; deterministic scoring/parser functions in `advisoryTools.ts`; lightweight route metadata in `advisorySeo.ts`. This separation prevents article bodies loading on the homepage and keeps templates independent of content.

## 4. Routes created

| Purpose | Route |
| --- | --- |
| Consulting hub | `/consulting` |
| Inventory & Profit Audit | `/consulting/inventory-profit-audit` |
| Fractional Purchasing | `/consulting/fractional-purchasing` |
| Compliance & Operational Audit | `/consulting/compliance-operational-audit` |
| SOP & Workflow Development | `/consulting/sop-workflow-development` |
| Metrc & Technology Advisory | `/consulting/metrc-technology` |
| Production & Extraction Operations | `/consulting/production-extraction` |
| Operational Diagnostic | `/consulting/operational-diagnostic` |
| Resource library | `/resources` |
| Days-on-hand guide | `/resources/days-on-hand-for-cannabis-inventory` |
| Reconciliation guide | `/resources/inventory-reconciliation-checklist` |
| Metrc API guide | `/resources/metrc-api-readiness-checklist` |
| Operations assessment | `/tools/operations-score` |
| Inventory tool | `/tools/inventory-health-check` |

Existing `/` and `/beta` are preserved. No `/platform` route was invented; software references use the existing homepage section.

## 5. Backend changes

Added the advisory router, service layer and strict schemas. Public endpoints handle leads, score evaluation, consented events and booking configuration. DEV-only endpoints support lead listing/detail, status updates and metrics. `scripts/advisory_admin.py` provides an authenticated administrative CLI; no new visual CRM or automatic email campaign is claimed.

The backend recomputes assessment scores from validated answers, requires the configured active owner organization and commits a normal lead before confirming success. Database failures return a recoverable failure. Booking configuration exposes only an approved valid HTTPS URL; no slot is fabricated when configuration is absent.

## 6. Database changes

Migration `0078_advisory_leads` adds `advisory_leads` and `advisory_daily_events`. Leads contain bounded contact/operation fields, consent version, source tool, server-computed score summary, referral metadata, status and version. A per-owner submission-ID uniqueness constraint supports replay. Status/location checks and owner/status/time indexes support validation and bounded queries.

Daily analytics uses an owner/day/event/placement/item aggregate key and atomic count increments. General audit history records lead creation and status transitions without duplicating contact details in audit metadata. Existing operational ledgers are not replaced.

## 7. Lead architecture

The funnel connects homepage services, resources and tools to a free 20-minute consultation request. Services explain review areas, deliverables and scope. Inventory & Profit Audit and Operational Diagnostic start at $500; final scope/fee is agreed before work. Fractional Purchasing is monthly; other engagements are scoped.

Pipeline stages are `NEW`, `CONTACTED`, `QUALIFIED`, `CONSULTATION_BOOKED`, `PROPOSAL_SENT`, `CLIENT` and `CLOSED_LOST`. Updates use optimistic concurrency. Metrics expose current states and cumulative distinct-lead stages from audit history.

An inquiry is not a booked appointment or paid engagement. Success requires accepted receipt plus a reference. Identical retries retain their submission ID; edited payloads receive a new ID. Failures preserve inputs. The assessment is shared only with lead consent; CSV content never accompanies an inquiry. A configured calendar is optional because the request-and-follow-up path remains available.

## 8. Analytics implementation

The first-party adapter sends exactly the 12 requested event types, allowlisted placement, fixed content slug and `consent: true` to `/api/v1/advisory/events`. It omits browser credentials/referrer headers. Event bodies contain no form content or user identifier. Collection defaults off, requires opt-in, honors DNT/GPC and supports withdrawal. Legacy marketing event hooks are preserved, while this adapter only sends advisory event types.

Lead consent separately covers storing inquiry details, applicable assessment answers and referral information for follow-up. Attribution retains known public landing paths, referrer origin and bounded campaign labels up to 100 characters. It drops arbitrary URL queries, fragments and credential-like values. Session persistence begins only after analytics opt-in. **First touch is not preserved across full-page homepage → resource → service → form navigation without opt-in.** Aggregate counts are not person-level funnel tracking.

## 9. SEO implementation

Existing homepage software metadata, SoftwareApplication and visible FAQ schema remain intact, as does beta positioning. Added routes have explicit titles/descriptions, exact canonicals and appropriate Service/Article metadata. Sitemap entries cover the implemented route definitions. Private workspace/storefront paths and unknown pages remain excluded from indexing. No ratings, credentials, endorsements or fixed checkout offers were invented.

SEO metadata imports no long-form article content. Runtime metadata is not evidence that every non-JavaScript preview crawler renders the SPA. Production crawling/preview verification belongs to release follow-up.

## 10. Resources created

Three substantial guides include review dates, scope boundaries and primary-source links:

- **Days on hand:** quantity-based calculation, worked example, worksheet and zero-sales/stockout/promotion limitations. Distinguishes stock cover from accounting days in inventory. Sources include official Shopify inventory documentation; no universal stock target.
- **Inventory reconciliation:** scope/cut-off, identification, count, investigation, approval, verification and exception-log template. Sources include Microsoft Learn and GS1. No legal count frequency, reporting deadline, tolerance or permitted adjustment is prescribed.
- **Metrc API readiness:** deployment context, access, mappings, synthetic test data, failure cases and readback evidence, grounded in official Metrc documentation. California/Montana references are explicitly illustrative, not nationwide contracts. State/license and medical/adult-use scope require separate current-source review.

Copy uses no fabricated client history, years, testimonials or results. Operational compliance advice is bounded as nonlegal; no Metrc endorsement/certification is implied.

## 11. Security changes

Strict server schemas reject unknown fields, enforce bounded values, require literal boolean consent and validate exact service/tool/question keys. Inventory tool data is rejected by intake. Public handling checks allowed origins, bounds request bodies before parsing, applies a honeypot and limits abuse-control memory. Proxy client-IP trust is explicit. Rate limiting is **single-process**, not a distributed WAF guarantee.

Admin access uses the existing server-established DEV role and configured owner scope. SQLAlchemy handles queries; version checks protect competing status edits. Rendered content uses React text handling rather than raw HTML insertion. CSV parsing is local and bounded to 2 MB/5,000 rows/64 columns; formula-like text is inert. No provider-changing operational action is introduced by this feature.

## 12. Tests performed

The lead reports **92 frontend tests passing and lint passing** in the latest combined run, superseding the prior 91-test count. The lead also reports **51 backend tests passing** including beta delivery. The isolated release checkout rerun of advisory and migration suites passed **50 tests**, with two upstream dependency deprecation warnings. These are separate suites; this author did not independently rerun the entire combined set. The author's latest focused SEO/analytics run passed 18 tests, and the service-data split production build passed.

[FRONTEND_BRAND_QA.md](FRONTEND_BRAND_QA.md) records 15 routes × six widths (320/390/768/1024/1440/1920), totaling 90 combinations. It includes automated accessibility, runtime/overflow checks, selected screenshots and keyboard/mobile interaction checks. Browser interaction evidence covers score calculation, submission retry, referral handling and valid/invalid CSV mapping.

## 13. Results

The final 90-combination pass records zero horizontal/header overflow, duplicate IDs, runtime errors or axe WCAG 2 A/AA and 2.1 AA violations. Computed homepage/consulting comparison at 390px confirms matching font/color, H1 size, copper button treatment and header background. Mobile menu focus return and consultation anchor positioning were checked. This is not an exhaustive accessibility certification or a Safari/Firefox claim.

The 25-question assessment validates all questions, at least 15 applicable answers and 0–4 values; it labels results self-reported, not a compliance certification. Inventory signals explicitly depend on available input columns, with limitations for absent data. Review found retry-after-edit and selected-service analytics issues; both are corrected in current source. Production release 20260919T233225Z-advisory is live on the existing PC-hosted Caddy/Cloudflare path. All 16 public routes returned 200 with expected headings/canonicals and no runtime errors; the existing ops sign-in page still loads. No authentication workflow or inventory API was replaced.

## 14. Performance findings

[PERFORMANCE.md](PERFORMANCE.md) and raw observations document three fresh-context local Chrome runs per route. The first advisory bundle unnecessarily loaded all article text on the homepage; splitting service data removed that dependency.

Measured homepage JS increased 446,507 → 466,070 bytes; CSS 168,635 → 171,883 bytes. Combined uncompressed JS/CSS increased 3.71%, with an estimated gzip increase of 8,710 bytes. Median local FCP was 56 ms before/after; LCP 444/436 ms. These are local intercepted asset bodies and unthrottled lab timings, not production transfer sizes or field Core Web Vitals. They do not establish absence of a production regression. Consulting/resources still share a bounded lazy article chunk.

## 15. Remaining integrations

A real approved HTTPS booking URL is optional setup for direct calendar scheduling; manual request-and-follow-up works without it. Owner configuration, migration 0078, runtime grants, RLS and loopback-only trusted-proxy configuration were applied and verified. A real browser lead returned 202, identical retry returned the same reference, unauthenticated administration returned 401, and the synthetic record was removed. Multiple workers/instances need shared or edge abuse controls if a global limit is required. Staff must monitor leads and follow up; no automatic email delivery was promised.

Respect the disclosed first-touch limitation without opt-in. Verify actual production compression, caching and mobile/network performance after release. Preserve current-source review for any future jurisdiction-specific compliance content.

## 16. Git commits

Implementation commit: `6c9c3537a84763f849e4c409402b1adb19af1527` on `codex/advisory-growth-system`. Pull request: https://github.com/MAVet710/buyer-dashboard/pull/574 (open; not merged). A subsequent documentation-only commit records the final live verification. The isolated release checkout excludes unrelated active backend edits. Publication uses the existing PC-hosted integration build; it does not depend on merging the PR.

## 17. Final URLs

The intended public base is **https://doobielogic.io**. The final route URLs are that origin plus the exact paths in item 4; the consulting entry is **https://doobielogic.io/consulting**, resources **https://doobielogic.io/resources**, and tools **https://doobielogic.io/tools/operations-score** and **https://doobielogic.io/tools/inventory-health-check**.

These routes are published and verified. The immutable build is `.local/public-releases/20260919T233225Z-advisory/dist`; sibling rollback directories retain prior Caddy and host configuration. The last four representative public responses were also inspected as raw HTML: route-specific titles, descriptions, canonical URLs, Open Graph and BreadcrumbList metadata are present before JavaScript runs. `frontend/scripts/public-seo.mjs` derives static HTML metadata from the shared SEO source during the production build. Caddy tries `{path}/index.html` before SPA fallback. Homepage screenshot preloading now applies only to the homepage, avoiding unnecessary tool/resource downloads. Existing operator access remains on its configured host and is not replaced by consulting.
