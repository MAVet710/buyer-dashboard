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
Status: in progress

Required:
- DoobieLogic production branding without breaking legacy browser/session keys.
- Home / Inventory / Purchasing / Orders / Production / Reports / Compliance / Data & Settings shell.
- Correct secondary tools per operation and role.
- Organization / facility / operation context continuity.
- Retail vs Production capability routing and cross-facility handoff.
- Uploads / Dutchie Live selector changes the data behavior rather than only the label.
- Global search and Product 360 on every workspace.
- Right-side desktop / full-screen mobile work windows.
- Mobile navigation and classic-navigation compatibility.

### Phase 2 — Buyer / Purchasing command center
Status: in progress

Required:
- Restore the operator-recorded continuous purchasing workflow.
- Sales Trend, Revenue by Category, Top Slow Movers, Inventory Health, exposure metrics.
- Inventory Summary, Category DOS, Forecast Table/export, category/SKU reorder drilldowns.
- Full Buyer Filters & Settings and Show All columns.
- Doobie Buyer Brief and Inventory Check use the current filtered slice.
- Newer replenishment/vendor policy and durable PO tools remain additive.

### Phase 3 — Inventory command center and receiving
Status: in progress

Required:
- Product 360 actions, audit focus, PO staging, Package Studio prefill, labels, adjustment, selected export.
- Retail inbound queue -> Receive Details flow.
- Production bulk-material receiving flow.
- Receive history source semantics for both operations.
- Existing durable audit lifecycle remains unchanged.

### Phase 4 — Compliance, mapper, admin, integrations
Status: in progress

Required:
- Compliance Q&A source/template/upload/query/citation/state/scope/review parity.
- Product Name Mapper upload/review/create-new/memory/library/export parity.
- User/password/role/org/facility access parity.
- Admin upload viewer and diagnostics parity.
- DEV AI controls vs non-DEV METRC-only integration behavior.

### Phase 5 — Production / cultivation inventory
Status: in progress

Required:
- Manufacturing/cultivation inventory grains remain distinct from retail.
- Bulk cannabis/material receiving.
- Cultivation plant inventory and plant events.
- Adjustments, lineage, holds, receiving history.
- Facility/license isolation and no retail data leakage.

### Phase 6 — Reports and shared data-source behavior
Status: in progress

Required:
- Every Streamlit-exposed report is present with the same scope and output format.
- Buyer executive report and any exposed Retail/competitor reports.
- Production/Co-Man, Extraction, White Label reports retain original builders where applicable.
- Active data-source state is consistent across Buyer surfaces.
- Uploads / Dutchie Live semantics are explicit and never silently fall back to another source.

### Phase 7 — Full responsive and visual acceptance
Status: blocked by phases 1–6

Required:
- Side-by-side Streamlit comparison at 390 / 430 / 768 / 1024 / 1440 px.
- No hidden controls, accidental page fragmentation, overflow, or altered workflow order.
- White Label/Repack and Package Studio visual acceptance completed.
- Desktop drawers and mobile full-screen work windows verified.

### Phase 8 — Release and production cutover
Status: blocked by phases 1–7

Required:
- `STREAMLIT_EXACT_PARITY_AUDIT.md` has no unchecked items.
- `LEGACY_STREAMLIT_PRODUCT_EVIDENCE.md` has no unchecked binding items.
- Frontend lint/tests/build pass.
- Full backend suite passes.
- API/frontend containers build and security scans pass.
- User/password/role/org/facility/license/sandbox continuity verified.
- Production migration job succeeds.
- `/health` and `/health/ready` return 200 after deploy.
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
