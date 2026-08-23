# DoobieLogic Streamlit Restoration Execution Control

This document is the operating control for PR #276. It exists to prevent the migration oversight from recurring.

## Product rule

Buyer Dash was the working/development name of DoobieLogic. The migration replaces the Streamlit runtime with React/FastAPI/Supabase/Cloud Run. It does not redesign the product. Streamlit source and operator-used recordings/screenshots remain the required product behavior unless the product owner explicitly approves a change.

## Evidence rule

A phase can move to `verified` only when all four evidence types exist where applicable:

1. **Source evidence** — Streamlit control/label/order/logic compared directly with React/FastAPI implementation.
2. **Behavior evidence** — automated tests cover the same calculations, permissions, persistence, actions, exports, and failure states.
3. **Responsive evidence** — 390 / 430 / 768 / 1024 / 1440 px acceptance for interactive surfaces.
4. **Operator evidence** — supplied recordings/screenshots have been reconciled and any recovered workflow composition is preserved.

A page name, route, API endpoint, or similar-looking component is not sufficient evidence.

## Phase gates

### Phase 1 — Global shell and navigation
Status: source/behavior verified · final side-by-side visual acceptance pending

Verified:
- DoobieLogic production branding without breaking legacy browser/session keys.
- Home / Inventory / Purchasing / Orders / Production / Reports / Compliance / Data & Settings shell.
- Correct secondary tools per operation and role.
- Organization / facility / operation context continuity.
- Retail vs Production capability routing and cross-facility handoff.
- Uploads / Dutchie Live selector changes the data behavior rather than only the label.
- Global search and shared Product 360 on every workspace.
- Shared right-side desktop / full-screen mobile work-window CSS contract.
- Mobile navigation and classic-navigation compatibility.

Remaining gate:
- Pixel/interaction comparison against Streamlit at the required responsive widths.

### Phase 2 — Buyer / Purchasing command center
Status: source/behavior restored · operator-recording visual acceptance pending

Verified:
- Operator-recorded continuous purchasing workflow is restored in one logical buyer surface.
- Sales Trend, Revenue by Category, Top Slow Movers, Inventory Health, exposure metrics.
- Inventory Summary, Category DOS, Forecast Table/export, category/SKU reorder drilldowns.
- Full Buyer Filters & Settings and Show All columns.
- Doobie Buyer Brief and Inventory Check use the current filtered slice.
- Newer replenishment/vendor policy and durable PO tools remain additive.
- Active Buyer controls flow into the retained Buyer executive report builder.

Remaining gate:
- Side-by-side comparison against the supplied 2026-04-16 operator recording.

### Phase 3 — Inventory command center and receiving
Status: source/behavior verified · final visual acceptance pending

Verified:
- Product 360 actions, audit focus, PO staging, Package Studio prefill, labels, adjustment, selected export.
- Product 360 and Inventory multi-select audit focus now preserve Retail vs Production operation and exact selected lot/product scope end to end.
- Retail inbound queue -> Receive Details -> Review -> Post Inventory -> Labels flow.
- Production bulk-material receiving is a separate production/cultivation workflow and never routes through Retail receiving.
- Receive history is operation, organization and facility scoped.
- Existing durable audit lifecycle remains unchanged.

Remaining gate:
- Side-by-side command-center/receiving interaction acceptance.

### Phase 4 — Compliance, mapper, admin, integrations
Status: source/behavior verified · final visual acceptance pending

Verified:
- Compliance Q&A source/template/upload/query/citation/state/scope/review parity.
- Product Name Mapper upload/review/create-new/memory/library/export parity.
- User/password/role/org/facility access parity, including intentional zero-facility accounts.
- Admin upload viewer and non-secret diagnostics parity.
- DEV AI controls vs non-DEV METRC-only integration behavior.

Remaining gate:
- Final rendered comparison of these administrative/compliance surfaces.

### Phase 5 — Production / cultivation inventory
Status: source/behavior verified · final visual acceptance pending

Verified:
- Manufacturing/cultivation inventory grains remain distinct from retail.
- Production projections do not borrow Retail sales velocity/DOH semantics.
- Bulk cannabis/material receiving is separate and facility/license scoped.
- Cultivation plant inventory, Plant 360 and lifecycle events.
- Adjustments, package lineage, hold/quarantine semantics and receiving history.
- Retail/Production audit focus no longer leaks across operations.

Remaining gate:
- Final rendered Production Inventory and receiving comparison.

### Phase 6 — Reports and shared data-source behavior
Status: source/behavior verified for currently exposed reports · final visual acceptance pending

Verified:
- Buyer executive report uses the retained Streamlit builder, current facility data and active Buyer controls.
- Production/Co-Man, Extraction and White Label reports retain the original builders.
- Retail / Production / Company executive pack controls and dated filenames match current Streamlit.
- Current Streamlit does not route a standalone Retail Labor or Competitor Intelligence report workspace; those byte payloads are conditional session-state additions to the executive pack only, so React does not invent unsupported standalone pages.
- Active data-source state is consistent across Buyer surfaces.
- Uploads / Dutchie Live semantics are explicit and Dutchie Live never silently falls back to uploaded data while the live client remains unimplemented.

Remaining gate:
- Final rendered reports/download acceptance.

### Phase 7 — Full responsive and visual acceptance
Status: real-browser responsive evidence verified · operator side-by-side visual acceptance pending

Verified on the current release-candidate branch:
- Real Chromium execution at 390 / 430 / 768 / 1024 / 1440 px.
- Buyer continuous command-center sections render through the actual React shell at every required width.
- White Label / Repack renders and all five workflow steps are exercised at every required width.
- Inventory -> Package Studio opens through the real application workflow.
- Package Studio is full-screen at mobile/tablet widths and a right-side work window on desktop widths.
- Production Inventory renders as a distinct bulk/cultivation surface at every required width.
- No document-level horizontal overflow or uncaught browser page errors were found in the matrix.
- GitHub Actions `React and FastAPI gates` run 357 passed and uploaded `browser-parity-evidence` artifact 9498594372 for head `cade4ac7820f874b1565c88c52213559f251fcce`.

Remaining gate:
- Side-by-side reconciliation against Streamlit/operator screenshots and the supplied 2026-04-16 Buyer recording. The recording could not be retrieved from the current file source during the automated acceptance pass, so operator evidence remains deliberately open.

### Phase 8 — Release and production cutover
Status: technical CI green · live Auth/schema continuity partially verified · blocked by licenses/METRC/operator acceptance and final deployed-candidate checks

Current technical evidence:
- `scripts/verify_streamlit_parity.py --mode contract` passes in CI.
- Frontend lint/tests/build pass.
- Full backend suite passes.
- API/frontend containers build, production migrations/startup checks pass, and security scans pass.
- Real Chromium responsive matrix passes at every required width.
- General CI and React/FastAPI CI both passed on the browser-evidence candidate.
- Live Supabase now reports Alembic `0037_function_acl_hardening`.
- Six active durable users map 6/6 to six Supabase Auth users by the same durable UUID.
- Login email, legacy username metadata, role, organization and facility metadata match the migration plan for all six users.
- Supabase Auth password hashes match the durable legacy bcrypt hashes for all six active users without exposing password material.
- The one durable `must_change_password` account still exists and maps to the expected Auth UUID.
- DEV Sandbox remains present.
- After 0037 there are zero direct `anon`/`authenticated` public table grants, zero browser sequence grants, and zero `PUBLIC`/browser-role execute grants on public functions.
- Detailed live verification is recorded in `docs/PHASE8_CONTINUITY_EVIDENCE_2026-08-23.md`.

Continuity blockers found:
- Active facility license continuity is not proven: both active non-sandbox facilities currently have blank durable facility license numbers.
- METRC credential/configuration continuity is not proven: `integration_configurations` currently contains no rows. A verified METRC traceability transaction is evidence of traceability behavior, not proof of a surviving live facility credential.
- Supabase Data API disablement has not yet been directly verified.
- Supabase Security Advisor reports leaked-password protection disabled; treat this as a public-launch hardening follow-up.

Still required before release:
- `STREAMLIT_EXACT_PARITY_AUDIT.md` has no unresolved applicable items.
- `LEGACY_STREAMLIT_PRODUCT_EVIDENCE.md` binding visual/operator items are accepted.
- Reconcile real facility license numbers/types against the pre-migration source of truth.
- Reconcile real METRC facility configuration/credentials against the pre-migration source of truth and validate without exposing secrets.
- Verify the unused Supabase Data API is disabled while Auth remains functional.
- Complete/record the encrypted backup and isolated restore drill if not already evidenced.
- Perform representative real-account sign-in, refresh, sign-out, password-change/recovery, role/facility switching, DEV cross-company access and `must_change_password` acceptance against the release candidate.
- Production migration/candidate deployment evidence is reconciled to the approved head and rollback plan.
- `/health` and `/health/ready` return 200 from the approved deployed candidate.
- Product owner completes final browser acceptance before PR #276 is treated as complete.

## Change-control rules

- PR #276 remains draft until Phase 8.
- No direct production deployment from this restoration branch.
- `MIGRATION_PARITY_TRACKER.md` is historical only and cannot release the app.
- `scripts/verify_streamlit_parity.py --mode contract` runs in normal CI.
- `scripts/verify_streamlit_parity.py --mode release` runs before production deployment and fails while any strict/binding checkbox remains open.
- A checked parity item is reopened when operator evidence proves the experience is incomplete.
- New functionality is additive. It cannot replace deterministic Streamlit behavior without explicit approval.
- Doobie may interpret evidence but may not become the source of truth for inventory, calculations, compliance, traceability, METRC, permissions, or audit records.
