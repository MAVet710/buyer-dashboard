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
- [x] Target Days on Hand control (1-60, default 21).
- [x] Velocity Adjustment control (0.01-5.0, default 0.5).
- [x] Days in Sales Period slider (7-120, default 60).
- [x] Clickable Units Sold and Reorder ASAP KPI filters.
- [x] Current-filter indicator.
- [x] Visible Categories multiselect with Streamlit category ordering.
- [x] Show product-level rows checkbox (default off).
- [x] Tracked Categories / Forecast Rows / Reorder ASAP / Product Rows glass metrics.
- [x] Category DOS table.
- [x] Forecast Excel export and table use the current metric/category slice.
- [x] One category expander per category, in Streamlit ordering.
- [x] Category DOS inside each expander.
- [x] Nested Reorder ASAP SKU expanders.
- [x] SKU sales + Batch/Lot evidence inside nested expanders.
- [x] Product-level rows section only when enabled; 2,000-row warning behavior.
- [x] Product-level Excel export.
- [x] SKU Inventory Buyer View velocity window 28/56/84 (default 56).
- [x] All Inventory / Reorder / Overstock / Expiring tabs and exact thresholds/status labels.
- [x] Inventory cross-reference status caption.
- [x] Doobie Inventory Check on the current filtered slice.
- [x] Generate Doobie Buyer Brief action.

### Inventory Command Center
- [x] Product Master has separate Retail and Production operation-scoped surfaces and routes.
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
- [x] Start audit workflow matches Streamlit, including independent durable workspaces, scope, blind-count default, tolerance, selected inventory and immediate in-progress state.
- [x] Uploaded/current source selection matches Streamlit, including CSV/XLSX/XLS preview, explicit field mapping, durable import, active Buyer Ops inventory and uploaded-lot audit scoping.
- [x] Camera scanner behavior matches Streamlit mobile flow, with a persistent mounted camera stream plus Bluetooth/USB, typed-code and manual-item fallbacks.
- [x] Pause/resume/stop/reopen audit lifecycle matches Streamlit; pausing returns to the dashboard and stopped work remains reviewable and reopenable.
- [x] Partial and completed reports match, including unscanned rows, activity history, CSV and multi-sheet Excel exports.
- [x] Audit dialogs/drawers and discrepancy resolution match, including blind first pass, recount, reason/note capture, correction posting and full-screen mobile count entry.
- [x] Retail Scan Audit and the production Inventory Audit & Reconciliation embed are facility/capability scoped and use the same durable audit engine without cross-operation leakage.
- [x] Audit acceptance covers 390, 430, 768, 1024 and 1440 px with no viewport overflow, horizontally scrollable reports, full-screen mobile count entry and a right-side desktop drawer.

### Slow Movers
- [x] Velocity/DOH windows, all filters/defaults, Top N including All, five-KPI snapshot, decision table, full-detail expander, discount tiers and three-sheet dated Excel export match.
- [x] Slow Movers acceptance covers 390, 430, 768, 1024 and 1440 px with contained table scrolling and no hidden controls or export action.

### MA Flower Equivalency
- [x] All six product categories, category-specific blank/default text fields, decimal-safe calculations, exact validation, result cards, calculation breakdown, Dutchie entry value and copy action match.
- [x] MA Flower Equivalency acceptance covers 390, 430, 768, 1024 and 1440 px with stacked mobile result/entry cards and no viewport overflow.

### Buyer Intelligence
- [x] Optional market-reference expander, 14–120 day lookback, four exact KPIs, Top Categories, SKU Risk and What to Buy deterministic evidence tables match.
- [x] Doobie Buyer Brief action retains the exact source placement/label and selected-lookback evidence context without replacing deterministic tables.
- [x] Buyer Intelligence acceptance covers 390, 430, 768, 1024 and 1440 px with contained table scrolling and no hidden action.

### Delivery Impact
- [x] Multi-manifest upload, optional sales upload and facility-scoped Buyer Dashboard sales reuse match, including invalid-manifest exclusion without discarding valid files.
- [x] Before/after and same-weekday modes, exact defaults, combined/individual selection, KPI labels/math, top-lift rows, unmatched review and every uploaded-file debug expander/download match.
- [x] Daily/hourly chart overlays, delivery markers, prior-week series, point-value hover evidence and no-data behavior match in the responsive React SVG implementation.
- [x] Delivery Impact acceptance covers 390, 430, 768, 1024 and 1440 px with mobile navigation, contained table scrolling and no hidden controls or debug actions.

### PO Builder
- [x] Reorder cross-reference appears in the same location/order.
- [x] Add All Reorder ASAP Lines matches exactly, including source behavior that does not deduplicate additions and stores bulk-added line totals as zero.
- [x] Manual line form fields/defaults match.
- [x] Current PO item presentation matches the Streamlit read-only dataframe; React-only per-line editing/removal controls were removed.
- [x] Inventory cross-check reasons/thresholds match, including exact product/optional-size matching and the `>=15 on hand` review threshold.
- [x] Store/vendor/order metadata fields and defaults match.
- [x] Tax/discount/shipping/subtotal/total math and presentation match.
- [x] Clear-all behavior matches.
- [x] Original canvas PDF output and `PO_{po_number}_{YYYYMMDD}.pdf` filename match.
- [x] Smart/Doobie PO remains additive and does not replace or precede the original PO workflow.
- [x] PO acceptance covers 390, 430, 768, 1024 and 1440 px with no viewport overflow and horizontally scrollable tables.

### Purchasing Budget
- [x] Sales window, DOS, COGS, safety, growth, exclusions and on-order inputs match, including current proposed-PO carryover.
- [x] Metrics, the exact nine-column category table, both category charts and Conservative/Balanced/Aggressive scenarios match.
- [x] Purchasing Budget acceptance covers 390, 430, 768, 1024 and 1440 px with no viewport overflow and horizontally scrollable tables.

### Trends
- [x] Trend/comparison/run-rate controls, Category Mix, Package Size Mix, Top Movers, per-category Best Seller expanders and Fast Movers + Low Stock sections match in one continuous workflow.
- [x] Streamlit currently presents dataframe sections rather than chart tabs; React-only tabs/summary charts were removed and table behavior matches.
- [x] Trends acceptance covers 390, 430, 768, 1024 and 1440 px with contained table scrolling and every continuous section reachable.

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
- [x] The seven Co-Man tabs and exact source order match: Dashboard, New Job, Schedule, Resources, Inventory & BOM, Customers and Performance.
- [x] Dashboard setup-readiness, status/customer filters, KPI cards, durable job queue, status actions and job duplication match.
- [x] New Job optimizer inputs/defaults, editable product mix, material/labor/machine/economic calculations, recommendation table, order prefill and committed-order form match.
- [x] Schedule crew/capacity planning, single-machine context, downstream hand-labor context and end-to-end completion/shortage calculations match.
- [x] Resources machine benchmark library/source links, machine models, machines, rates and hand-labor configuration match.
- [x] Inventory & BOM products, lots, movements, reservations, ledger views and BOM editing match and use the existing durable Co-Man repository.
- [x] Customers and Performance actual-entry, KPI, chart and plan-vs-actual behavior match.
- [x] Production Control/Production 360 remains a separate right-side work window with BOM reservation, stage actuals, output creation, quarantine posting, QA disposition and COGS actions.
- [x] Co-Man and Production Control writes are tenant/facility scoped and covered by durable API and facility-isolation tests.
- [x] Co-Man desktop/mobile rendering and drawer geometry were verified at 390px, 430px, 768px, 1024px and 1440px.

### Extraction Command Center
- [x] Executive Overview metrics, deterministic alerts and output-by-method view match the six-area parity workspace and use current durable run evidence.
- [x] Run Analytics retains the exact source-order table fields and collapsed `Add Run Record` expander, labels, choices, defaults, numeric steps, calculations and blank-batch behavior while persisting entries durably.
- [x] Toll Processing retains the exact source-order job table and collapsed `Add Toll Processing Job` expander without React-only fields; dates, choices, defaults and SLA wording match.
- [x] Compliance/METRC required-field guidance plus facility-scoped output, QA and traceability evidence match.
- [x] Data Input retains the CSV-only uploader, success/error wording and full-column preview; manual run entry remains in the Run Analytics expander exactly as Streamlit exposes it.
- [x] Doobie Ops Brief uses current filtered durable run evidence, preserves the exact action label and does not replace deterministic extraction calculations.
- [x] Durable Extraction Operations run board, search/status/method/closed filters and KPI labels match `modules/extraction/ui.py`.
- [x] New Extraction Run opens in the Streamlit right-side work-window pattern with the exact durable run controls and defaults.
- [x] Run 360 opens in the right-side work-window pattern with the exact seven tabs: Overview, Inputs, Process, Outputs + QA, COGS, Traceability and History.
- [x] Run 360 source reservation/consumption/release, stage events, output creation, QA/COA/release, cost events, package-creation queue and history actions use the existing tenant/facility-scoped durable extraction services.
- [x] Streamlit exposes no separate toll customer/job detail dialog; toll-job context remains within the Toll Processing table and the attached Run 360 context.
- [x] Extraction desktop/mobile rendering and Run 360/New Run drawer geometry were verified at 390px, 430px, 768px, 1024px and 1440px.

### White Label / Repack
- [x] White Label / Repack remains its own workspace and is not routed to Package Studio.
- [x] Scenario Name, Save Scenario, Load Scenario, Duplicate Scenario, Clear Scenario and conditional Apply Loaded Scenario match source order and behavior.
- [x] The five tabs and their exact labels/order match `modules/repack/ui.py`.
- [x] Bulk Lot fields, defaults and Advanced Lot Details expander match.
- [x] Costs fields, defaults and Advanced Costs expander match.
- [x] Simple Mode, dynamic package-plan rows, packaging-cost details and allocation warnings match.
- [x] Gram conversion, landed cost, modeled loss, usable weight, unit rounding, leftovers, revenue, gross profit, gross margin, break-even and readiness calculations are source-matched and tested.
- [x] Results metrics/table, three charts and compliance checklist labels/status rules match.
- [x] Export Retail Ops Report uses the retained `reports/white_label_report.py` builder with the active scenario payload.
- [ ] White Label / Repack desktop and mobile rendering has been accepted side-by-side against Streamlit.
- [x] Package Studio remains separate and opens from Inventory in the Streamlit right-side work-window pattern with the selected source package prefilled.
- [x] New Run, Source Trail and Recent Runs tabs match source order and labels.
- [x] Breakdown, Pack Down, Build Run, Multi-Build, Sample Pull, Rework and Source Correction actions use the existing durable Package Studio service.
- [x] Source metrics, output-count defaults, loss/work note, per-output product/lot/METRC/quantity/unit/source-equivalent/purpose controls and mass-balance messages match.
- [x] Review confirmation, role-based commit restriction, exact commit labels and durable inventory/lineage writes match.
- [x] Source Trail parent/downstream tables and expanders use the tenant/facility-scoped durable lineage service.
- [x] Recent Runs columns and status/action presentation match the Streamlit dataframe.
- [ ] Package Studio desktop/mobile drawer rendering has been accepted side-by-side against Streamlit.

## Commercial Ops

- [x] Orders & Fulfillment preserves the Streamlit heading and exact six-tab order: Command Center, New Order, Allocate & Fulfill, Trade Partners, Inventory Audits, Inventory Ledger.
- [x] Command Center KPIs, order search, incoming/outgoing columns, exception logic, status labels, ordering, and empty states match Streamlit.
- [x] New Order, allocation/fulfillment, receiving-lot, partner, payment-status, and ledger/export controls use the existing durable tenant/facility-scoped repositories.
- [x] The shared Inventory Audits surface embedded in Commercial preserves the complete Streamlit scanner, resumable sessions, reports, and production source-selection workflow.
- [x] Wholesale + Finance remains an additive right-side work window with exact A/R metrics, order selector, shipment/manifest, invoice/payment, and customer-pricing pop-outs.
- [x] Commercial desktop/mobile acceptance covers 390, 430, 768, 1024, and 1440 px with no viewport overflow and full-screen mobile/right-side desktop finance behavior.

## Compliance / Traceability

- [x] Traceability queue views, provider filters, full evidence columns, status summaries and facility isolation match `modules/traceability/ui.py`.
- [x] Transaction detail opens in the Streamlit right-side work-window pattern with Overview, Attempts, Lifecycle and Payloads tabs, sanitized payloads and audit history.
- [x] Reconciliation reason/confirmation, role restrictions and Requeue / Mark verified / Cancel action lifecycle controls match and remain audit logged.
- [x] Traceability desktop/mobile rendering and drawer geometry were verified at 390px, 430px, 768px, 1024px and 1440px; the drawer is full-screen through 768px and 570px right-side at desktop widths.

## Data & Settings

- [ ] Location settings match Streamlit.
- [x] Imports & Data preserves the four source-order tabs, ten-source readiness table, reviewed retail inspect/map/preview/publish flow, durable version history and role-gated archive behavior.
- [x] Production Data Input preserves raw extraction intake while adding reviewed CSV/XLS/XLSX normalization, safe alias mapping, defaults, mapped preview, calculated yields, durable append and exact duplicate protection against the existing extraction model.
- [x] Data Hub publishing, history, archive and production import are tenant/facility scoped and covered by durable API tests; responsive rendering was verified at 390px, 430px, 768px, 1024px and 1440px without viewport overflow.
- [ ] Data source state is reflected consistently across Buyer surfaces.

## Reports

- [ ] Every report exposed by Streamlit is present with the same data scope and output format.
- [ ] Buyer executive report matches.
- [x] Production/Co-Man report uses the retained Streamlit `reports/coman_report.py` builder and current facility-scoped queue data.
- [x] Extraction report uses the retained Streamlit `reports/extraction_report.py` builder and current facility-scoped durable run evidence.
- [x] White Label report uses the same Streamlit report builder and active scenario scope.
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
