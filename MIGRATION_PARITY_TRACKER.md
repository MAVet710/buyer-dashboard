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
- [x] Inventory Dashboard full calculation parity
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
- [x] Chart data parity
- [x] Top delivered items by lift
- [x] Unmatched item review
- [x] PDF debug text dump

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

## PO Builder workspace
- [x] Reorder cross-reference from Inventory Dashboard
- [x] Add all reorder ASAP lines
- [x] Manual PO entry form
- [x] Inventory cross-check in line items
- [x] Totals and taxes
- [x] PDF generation
- [x] Smart PO merged without removing original capabilities

## Compliance workspace
- [x] Compliance source upload
- [x] Template download
- [x] Grounded Q&A
- [x] Admin compliance QA tools

## Buyer Intelligence workspace
- [x] KPI summary
- [x] Category and SKU risk tables
- [x] AI Buyer Brief replaced by Doobie while preserving section outputs

## Extraction Command Center workspace
- [x] Executive Overview
- [x] Run Analytics
- [x] Toll Processing
- [x] Compliance / METRC
- [x] Data Input
- [x] AI Ops Brief replaced by Doobie
- [x] Manual run entry preserved
- [x] Manual toll job entry preserved

## Exact Streamlit UI and interaction parity

These gates are intentionally stricter than backend/calculation parity. They cover the operator experience the Streamlit application actually shipped. A React page with similar data is not sufficient if controls, workflows, dialogs/popovers, visual hierarchy, or workspace boundaries changed.

### Global shell and visual system
- [ ] Restore the Streamlit glass/translucent visual system across cards, metrics, tables, forms, sidebars and top bars
- [ ] Restore the Streamlit fixed background/overlay depth, orange accent hierarchy, shadows, borders and hover/focus treatments
- [ ] Restore all Streamlit popovers/expanders/dialog-like interactions as working React overlays/drawers/popovers rather than inline replacements
- [ ] Match Streamlit role-aware navigation/workspace grouping and preserve every distinct workspace instead of collapsing routes
- [ ] Match Streamlit responsive/mobile behavior and preserve usable overlays on phone/tablet

### Retail / Buyer Operations exact experience
- [ ] Inventory Dashboard control placement, KPI hierarchy, category DOS, forecast, product/SKU tabs and drill-down presentation match Streamlit
- [ ] Buyer Inventory Check opens and displays as an in-context pop-out/overlay with the filtered evidence slice
- [ ] Trends chart/table presentation and controls match Streamlit
- [ ] Slow Movers filter/KPI/decision/discount presentation matches Streamlit
- [ ] Delivery Impact uploads, KPI layout, charts, unmatched review and debug/download controls match Streamlit
- [ ] Buyer Intelligence/Recommendations presentation and Doobie brief interaction match Streamlit
- [ ] PO Builder layout and purchasing workflow match the original Streamlit builder, including reorder cross-reference, manual lines, inventory review, metadata, totals, clear/reset and PDF actions
- [ ] Purchasing Budget layout, scenario controls and category current-vs-target presentation match Streamlit
- [ ] MA Flower Equivalency interaction and results presentation match Streamlit
- [ ] Product Name Mapper upload/review/confirmation/export workflow matches Streamlit
- [ ] Compliance Q&A source/status/query/citation presentation matches Streamlit

### Production exact experience
- [ ] Co-Man Production workspace preserves every Streamlit tab, KPI, data-entry, run/order, capacity and report interaction
- [ ] Extraction Command Center preserves all Streamlit tabs, KPI hierarchy, run analytics, toll processing, compliance/METRC, data input and Doobie Ops Brief interactions
- [ ] White Label / Repack is restored as its own five-step scenario workspace and is not aliased to Package Studio
- [ ] Package Studio remains available separately for inventory transformations
- [ ] Production inventory/receiving/plant workflows preserve the Streamlit facility/license-aware behavior and interaction model

### Commercial, Data, Admin and reporting exact experience
- [ ] Orders & Fulfillment preserves the complete Streamlit commercial workspace behavior and presentation
- [ ] Data Hub preserves upload, active-source, history, mapping/quality and operational restore interactions with Streamlit-equivalent hierarchy
- [ ] Admin Tools preserves user/org/facility management and admin QA/integration interactions with Streamlit-equivalent presentation
- [ ] AI/METRC Integrations preserves role-gated connection status, testing and configuration interactions
- [ ] Executive Report Packs popover is restored with Retail Ops and Production Ops pack downloads and available individual reports
- [ ] Role Home/help/command-center interactions and quick navigation match Streamlit

## Parity result

Backend/calculation parity is substantially implemented, but **exact Streamlit UI, interaction and workspace parity is reopened and currently incomplete**. Production web deployment must remain blocked by `scripts/verify_streamlit_parity.py` until every unchecked item above is implemented and verified against the Streamlit source of truth.
