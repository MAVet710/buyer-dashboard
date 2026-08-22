# Migration Parity Tracker

Source of truth: `app.py` and the Streamlit workspaces it routes to  
Target: React + FastAPI DoobieLogic operations app

This checklist is the product-parity contract for retiring Streamlit from the production traffic path. A checked item means the operator capability is present in React/FastAPI or has an intentional, documented equivalent that preserves the same outcome without preserving Streamlit-specific implementation details.

## Global platform behavior
- [x] Auth flow (admin, user, trial)
- [x] Theme toggle
- [x] Upload logging / admin upload viewer
- [x] Daily upload persistence
- [x] AI provider debug/admin tools where still relevant
- [x] Doobie-only routing replacing legacy AI paths

Acceptance notes:
- Supabase Auth preserves legacy username/password sign-in, password-change lifecycle, organization/facility authorization and DEV access. The 24-hour trial key validates through the platform Doobie integration and issues a signed, sandbox-scoped token.
- Trial users receive operational demo navigation in `dev-sandbox` but not Users & Access, platform integrations, organization administration or privileged Doobie approvals.
- Theme preference persists in the React shell.
- Data Hub files are durable, tenant/facility scoped, fingerprinted, versioned and restored from SQL rather than browser/session memory. Import history records the file, status, quality, row count, publisher and activation time. Operational roles can publish required daily sources; archive is restricted to DEV/admin/supervisor.
- External provider credentials and connection tests live in the role-gated Integrations workspace. The production API no longer imports Streamlit for auth, trial, Doobie or provider configuration.
- User-facing AI workflows route through Doobie contracts. Deterministic evidence remains first-class underneath Doobie rather than being replaced by generic model output.

## Buyer Operations workspace
- [x] Inventory Dashboard full parity
- [x] Target DOH settings
- [x] Velocity adjustment
- [x] Sales period controls
- [x] Category DOS quick table
- [x] Forecast table
- [x] Product-level rows toggle / equivalent React tab
- [x] SKU Inventory Buyer View tabs
- [x] Export Forecast Table (Excel)
- [x] AI Inventory Check replaced by Doobie

Acceptance notes:
- The React/FastAPI buyer model preserves the Streamlit category, package-size, strain/product classification, synthetic 28g flower and 500mg edible calculations, DOH/reorder thresholds, SKU velocity windows, expiry/overstock statuses and Excel outputs.
- Reorder ASAP rows include the original weighted SKU sales drill-down and batch/lot on-hand breakdown.
- Doobie Inventory Check receives only the current Buyer filter slice and current model controls.

## Trends workspace
- [x] Category mix
- [x] Package size mix
- [x] Top movers by SKU
- [x] Best sellers by category
- [x] Fast movers + low stock

## Delivery Impact workspace
- [x] Manifest upload
- [x] Sales upload
- [x] Before/after analysis
- [x] Same weekday WoW analysis
- [x] KPI summary table
- [x] Charting (responsive React SVG equivalent replacing Streamlit/Plotly rendering)
- [x] Top delivered items by lift
- [x] Unmatched item review
- [x] PDF debug text dump

Acceptance note: the charting implementation intentionally changes from Streamlit/Plotly to responsive React SVG while preserving the daily and same-weekday comparison series and point-level values. Plotly is not retained as a runtime dependency solely for implementation parity.

Acceptance notes:
- Delivery Impact now restores Streamlit's multiple-manifest workflow, cached facility sales reuse or direct sales upload, exact comparison defaults, invalid-file exclusion, combined/individual manifest analysis, dynamic same-weekday KPI columns, exact four-metric summary, lift tables, unmatched review and all-file debug downloads.
- Combined analysis applies the union of delivered product matches to every active manifest exactly as Streamlit does; individual selection recomputes from that manifest's own delivered-item evidence.
- The responsive chart retains daily/hourly overlays, separate sales/order scaling, current/prior-week series, delivery markers and point-value hover evidence.
- Browser acceptance passed at 390px, 430px, 768px, 1024px and 1440px with mobile navigation, contained table scrolling and no hidden controls.

## Slow Movers workspace
- [x] Full filter bar
- [x] Velocity window selector
- [x] DOH threshold controls
- [x] Top N selector
- [x] Search / category / brand filters
- [x] KPI strip
- [x] Decision-first table
- [x] Discount tier summary
- [x] Excel export

Acceptance notes:
- The web workflow now follows the canonical `app.py` version rather than the older separate view: 28/56/84-day velocity choices, 60-day default threshold, All default Top N, single category/vendor selectors, exact sort/toggles, five KPI snapshot, full-detail expander and the three-sheet dated workbook.
- Buyer Intelligence restores the optional live-reference expander, exact lookback control, revenue evidence, Top Categories, SKU Risk, What to Buy and the original Buyer Brief placement.
- Trends is again one continuous workflow with exact settings, tables and per-category expanders; the React-only five-tab layout was removed.
- Slow Movers, Buyer Intelligence and Trends were visually accepted at 390px, 430px, 768px, 1024px and 1440px with contained table scrolling and no hidden actions.

## Inventory Audits workspace
- [x] Durable independent audit sessions
- [x] Uploaded Dutchie inventory and active Buyer Ops source selection
- [x] Explicit source-column mapping and facility-scoped durable import
- [x] Camera, Bluetooth/USB, typed-code and manual-item scanning
- [x] Blind first count and tolerance-based recount
- [x] Pause, resume, stop, reopen and complete lifecycle
- [x] Partial and completed report review
- [x] CSV and multi-sheet Excel exports
- [x] Retail and Production operation/facility isolation
- [x] Desktop right-side count drawer and full-screen mobile count workflow

Acceptance notes:
- Streamlit navigation to Inventory Counts is preserved as the standalone Retail Scan Audit workspace; Commercial embeds the same durable engine as Inventory Audit & Reconciliation for Production Ops.
- Audit history, counts, scan evidence, events, discrepancy reasons and optional ledger corrections persist in SQL and remain resumable across sessions.

## PO Builder workspace
- [x] Reorder cross-reference from Inventory Dashboard
- [x] Add all reorder ASAP lines
- [x] Manual PO entry form
- [x] Inventory cross-check in line items
- [x] Totals and taxes
- [x] PDF generation
- [x] Smart PO merged without removing original capabilities

Acceptance notes:
- The original manual PO workflow remains intact in exact source order: reorder cross-reference, store/vendor/order metadata, manual line entry, read-only current-item review table, tax, discount, shipping and the legacy canvas PDF output.
- Inventory review uses exact product name plus optional size matching and the Streamlit `>=15 on hand` threshold; bulk reorder additions intentionally retain the source workflow's zero stored line total until prices are filled.
- Smart buying evidence is available alongside the manual workflow and can be added to the PO without replacing manual lines. The full Doobie Buyer Brief remains available as the interpretation layer over the same Buyer evidence.
- Purchasing Budget retains the exact inputs/defaults, formulas, nine-column category table, two category charts, three scenarios and proposed-PO budget carryover.
- PO Builder and Purchasing Budget were visually accepted at 390px, 430px, 768px, 1024px and 1440px with contained horizontal table scrolling and no hidden actions.

## Compliance workspace
- [x] Compliance source upload
- [x] Template download
- [x] Grounded Q&A
- [x] Admin compliance QA tools

Acceptance notes:
- Q&A only answers from the active reviewed facility source and returns citations/source metadata.
- Reviewed-source publication is restricted to DEV, admin, QA and supervisor roles; other users retain read/query/template access.
- Traceability Operations preserves the facility-scoped queue, provider filtering, sanitized evidence, lifecycle history and role-gated reconciliation controls in the exact right-side desktop/full-screen mobile work window.

## Data Hub workspace
- [x] Ten-source operational readiness table
- [x] Retail source inspect, mapping, preview and durable publish/replace
- [x] Production extraction CSV/XLS/XLSX inspect, mapping, preview and durable append
- [x] Revision history and role-gated archive
- [x] Tenant/facility isolation and responsive acceptance

Acceptance notes:
- Retail uploads retain reviewed source mappings and normalize canonical headers before durable publication.
- Production partner imports prefer known extraction-field aliases, calculate missing yield/efficiency values, append to the existing extraction model and skip exact run-date/batch/method duplicates.

## Buyer Intelligence workspace
- [x] KPI summary
- [x] Category and SKU risk tables
- [x] AI Buyer Brief replaced by Doobie while preserving section outputs

Acceptance note: deterministic Buy First, SKU stockout risk, overstock/slow watch and category risk sections remain visible independently of the generated Doobie Buyer Brief.

## Extraction Command Center workspace
- [x] Executive Overview
- [x] Run Analytics
- [x] Toll Processing
- [x] Compliance / METRC
- [x] Data Input
- [x] AI Ops Brief replaced by Doobie
- [x] Manual run entry preserved
- [x] Manual toll job entry preserved

Acceptance notes:
- The grounded Doobie extraction brief consumes current run evidence and preserves explicit measurement-availability boundaries rather than inventing unsupported process metrics.
- Run creation, workflow/stage events, loss recording, outputs, QA, mass balance, COGS, toll jobs and traceability remain available in React/FastAPI.

## Parity result

The Streamlit product-parity contract is complete for the React/FastAPI application. This does **not** by itself authorize public DNS/traffic cutover. Production-clone validation, provider deployment gates, pilot acceptance, backup/restore and rollback rehearsal in `docs/WEB_CUTOVER_GATES.md` and `docs/PRODUCTION_DEPLOYMENT.md` remain mandatory before Streamlit is retired from public production traffic.
