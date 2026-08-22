# Streamlit Exact-Parity Acceptance Audit

**Source of truth:** the current Streamlit `app.py`, `ui_premium.py`, `ui_polish.py`, `modules/navigation/*`, `views/*`, and `modules/*/ui.py` implementations on `main`.

This is stricter than the old migration tracker. A React page does **not** pass merely because an equivalent API or a page with the same name exists.

A surface passes only when all of the following match the current Streamlit app:

- navigation location and operation/license visibility
- page title, section order, labels, controls, defaults and ranges
- glass/surface styling, spacing, responsive behavior and status treatments
- buttons, tabs, expanders, drawers/dialogs/pop-outs and their open/close behavior
- tables, visible columns, filters, search, sorting and row actions
- uploads, live-data mode, persistence and source status
- calculations, thresholds and deterministic business rules
- reports/downloads/export filenames and formats
- Doobie actions and evidence boundaries
- role, organization, facility, sandbox and license restrictions
- empty/error/loading states

No item may be checked because of an intentional redesign. The requirement is **no redesign**.

## Global shell

- [ ] Premium Streamlit visual system is pixel/behavior equivalent (copper palette, glass surfaces, shadows, radii, typography, dark/light theme).
- [ ] Flat sidebar matches: Home / Inventory / Purchasing / Orders / Production / Reports / Compliance / Data & Settings.
- [ ] Secondary tool selector matches the active category and operation.
- [ ] Persistent organization/facility/operation context bar matches Streamlit.
- [ ] Retail Ops / Production Ops availability matches roles and facility capabilities.
- [ ] Retail data-source selector matches `Uploads` / `Dutchie Live` and actually changes the source used by Buyer workflows.
- [ ] Global search appears on every workspace.
- [ ] Product 360 opens as the same right-side drawer and exposes the same evidence/actions.
- [ ] All dialogs/pop-outs use the same right-side drawer behavior on desktop and full-screen behavior on mobile.
- [ ] Mobile navigation matches the Streamlit category/tool selectors.
- [ ] Classic-navigation compatibility option is preserved if still enabled in Streamlit.

## Home

- [ ] Role-aware Operations Home content matches `modules/navigation/role_home.py`.
- [ ] Home search/inbox/cards expose the same routes and status evidence.

## Retail / Buyer Operations

### Inventory Dashboard / Purchasing Overview
- [ ] Target Days on Hand control (1-60, default 21).
- [ ] Velocity Adjustment control (0.01-5.0, default 0.5).
- [ ] Days in Sales Period slider (7-120, default 60).
- [ ] Clickable Units Sold and Reorder ASAP KPI filters.
- [ ] Current-filter indicator.
- [ ] Visible Categories multiselect with Streamlit category ordering.
- [ ] Show product-level rows checkbox (default off).
- [ ] Tracked Categories / Forecast Rows / Reorder ASAP / Product Rows glass metrics.
- [ ] Category DOS table.
- [ ] Forecast Excel export and table.
- [ ] One category expander per category, in Streamlit ordering.
- [ ] Category DOS inside each expander.
- [ ] Nested Reorder ASAP SKU expanders.
- [ ] SKU sales + Batch/Lot evidence inside nested expanders.
- [ ] Product-level rows section only when enabled; 2,000-row warning behavior.
- [ ] Product-level Excel export.
- [ ] SKU Inventory Buyer View velocity window 28/56/84 (default 56).
- [ ] All Inventory / Reorder / Overstock / Expiring tabs and exact thresholds/status labels.
- [ ] Inventory cross-reference status caption.
- [ ] Doobie Inventory Check on the current filtered slice.
- [ ] Generate Doobie Buyer Brief action.

### Inventory Command Center
- [x] Retail Products / Packages grains and Production Packages / cultivation Plants grains are distinct.
- [x] Retail built-in views match: All Inventory, Low Stock, Under 14 DOH, Slow Movers, Expiring 90 Days, Bulk Packages, Quarantine / Hold.
- [x] Production built-in views match: All Material, Bulk Flower, Biomass / Trim, Extraction Input, WIP, Finished Bulk, Production Ready, Low Balance, Quarantine / Hold.
- [x] Search plus status, vendor/source, room and category/material filters use the facility-scoped durable ledger.
- [x] Saved views and clear/reset controls match the Streamlit command center.
- [x] Show All / Show Defaults / Compact display-column controls match.
- [x] Multi-row selection surface restores the Streamlit action labels and row/available totals.
- [ ] Product 360, audit focus, Add to PO staging, Package Studio prefill, labels, adjustment and selected export have been source/visual verified end-to-end.
- [ ] Retail receive drawer matches the full inbound queue → Receive Details Streamlit workflow.
- [ ] Production receive drawer matches the bulk material Streamlit workflow.
- [ ] Receive history matches Streamlit source semantics for both operations.

### Inventory Audits
- [ ] Start audit workflow matches Streamlit.
- [ ] Uploaded/current source selection matches Streamlit.
- [ ] Camera scanner behavior matches Streamlit mobile flow.
- [ ] Pause/resume/stop/reopen audit lifecycle matches Streamlit.
- [ ] Partial and completed reports match.
- [ ] Audit dialogs/drawers and discrepancy resolution match.

### Slow Movers
- [ ] Velocity/DOH windows, all filters, Top N, KPI strip, decision table, discount tiers and Excel export match.

### MA Flower Equivalency
- [ ] Inputs, defaults, calculation, warnings and presentation match.

### Buyer Intelligence
- [ ] Deterministic evidence tables match.
- [ ] Doobie Buyer Brief action matches Streamlit.

### Delivery Impact
- [ ] Manifest + sales upload workflow matches.
- [ ] Before/after, same-weekday, lift, unmatched review and debug output match.
- [ ] Chart presentation/interactions match Streamlit.

### PO Builder
- [ ] Reorder cross-reference appears in the same location/order.
- [ ] Add All Reorder ASAP Lines matches exactly.
- [ ] Manual line form fields/defaults match.
- [ ] Current PO item editing/removal matches.
- [ ] Inventory cross-check reasons/thresholds match.
- [ ] Store/vendor/order metadata fields and defaults match.
- [ ] Tax/discount/shipping/subtotal/total math and presentation match.
- [ ] Clear-all behavior matches.
- [ ] Original PDF output and filename match.
- [ ] Smart/Doobie PO remains additive and does not replace the original PO workflow.

### Purchasing Budget
- [ ] Sales window, DOS, COGS, safety, growth, exclusions and on-order inputs match.
- [ ] Metrics, category table and Conservative/Balanced/Aggressive scenarios match.

### Trends
- [ ] Category mix, package size mix, top movers, best sellers and fast-mover/low-stock sections match.
- [ ] Plot/chart behavior matches Streamlit.

### Compliance Q&A
- [ ] Source status/upload/template/query workflow matches.
- [ ] Required citation/state/scope/review fields match.

### Nomenclature Mapper
- [ ] Catalog/manifest upload, suggestions, confirmations, learned mappings and export match.

### Admin Tools / Integrations
- [ ] User/org/facility/password/role controls match Streamlit.
- [ ] Upload/admin viewer and diagnostics match.
- [ ] DEV AI controls and non-DEV METRC-only behavior match.

## Production Ops

### Production Inventory
- [ ] Production/cultivation inventory grains match Streamlit, distinct from retail inventory.
- [ ] Bulk cannabis/material receiving matches.
- [ ] Plant inventory/events match.
- [ ] Adjustments, lineage, holds and receiving history dialogs match.

### Co-Man Production
- [ ] All planning/execution/material/QA/cost tabs and actions match Streamlit.
- [ ] Production ERP dialogs match Streamlit.

### Extraction Command Center
- [ ] Executive Overview matches.
- [ ] Run Analytics matches.
- [ ] Toll Processing matches.
- [ ] Compliance/METRC matches.
- [ ] Data Input/manual run matches.
- [ ] Doobie Ops Brief matches.
- [ ] Run/customer/detail dialogs match Streamlit.

### White Label / Repack
- [ ] Repack workspace matches `modules/repack/ui.py`; Package Studio must not replace it.
- [ ] Package Studio remains available where Streamlit exposes it.
- [ ] Package Studio dialogs/actions match.

## Commercial Ops

- [ ] Orders & Fulfillment tabs, filters, order actions, allocation and dialogs match Streamlit.
- [ ] Commercial finance surfaces/dialogs match where exposed.

## Compliance / Traceability

- [ ] Traceability queue/submission/reconciliation behavior matches.
- [ ] Traceability dialogs and METRC actions match.

## Data & Settings

- [ ] Location settings match Streamlit.
- [ ] Imports & Data version history/publish/archive behavior matches.
- [ ] Data source state is reflected consistently across Buyer surfaces.

## Reports

- [ ] Every report exposed by Streamlit is present with the same data scope and output format.
- [ ] Buyer executive report matches.
- [ ] Production/Co-Man report matches.
- [ ] Extraction report matches.
- [ ] White Label report matches if exposed.
- [ ] Retail Ops report matches if exposed.
- [ ] Competitor report matches if exposed.

## Release gate

- [ ] Automated exact-parity test/audit passes.
- [ ] Frontend lint/test/build passes.
- [ ] Full backend suite passes.
- [ ] Production containers and security scans pass.
- [ ] Desktop acceptance completed against current Streamlit side-by-side.
- [ ] iPhone/mobile acceptance completed against current Streamlit side-by-side.
- [ ] Only after all above: deploy React/FastAPI candidate for user acceptance.
