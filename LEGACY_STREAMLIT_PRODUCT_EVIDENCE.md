# Legacy Streamlit Product Evidence

This file is part of the exact-parity acceptance contract for the Streamlit -> React/FastAPI migration.

## Product identity / branding clarification

`Buyer Dash` was the working/development name of this same application. The intended production product name is **DoobieLogic**. Buyer Dash and DoobieLogic are not separate products and the migration must not split them into separate concepts.

Exact parity therefore means: restore the application that existed as Streamlit Buyer Dash on the faster React/FastAPI/Supabase/Cloud Run architecture, while using **DoobieLogic** as the production brand on `doobielogic.io`.

The product-name substitution `Buyer Dash` -> `DoobieLogic` is an explicitly approved branding change. It does not authorize any UI, workflow, calculation, navigation, permission, report, data-source, or feature redesign. Job-function names such as Buyer Operations, Buyer Intelligence, Buyer Brief, purchasing, inventory, production, compliance, and other operational terminology remain product behavior and must be preserved unless separately approved.

## Why this exists

The migration exists to improve runtime performance, reliability, persistence and hosting. It is **not** a product redesign. A React page, API endpoint, or equivalent capability does not satisfy parity when the operator-facing workflow, composition, controls, evidence, reports, or navigation from the working Streamlit Buyer Dash has been removed, fragmented, hidden, or materially changed.

The old `MIGRATION_PARITY_TRACKER.md` must not be used by itself to declare migration completion.

## Binding evidence hierarchy

1. Operator-used Streamlit recordings and screenshots supplied during migration review.
2. The last working Streamlit implementation that produced those operator workflows.
3. Current Streamlit source (`app.py`, `ui_premium.py`, `ui_polish.py`, `views/*`, `modules/*/ui.py`, navigation modules).
4. React/FastAPI implementation.

When an older operator recording proves a useful workflow existed and later Streamlit refactoring removed or split it, that workflow is still considered required unless the product owner explicitly approved its removal.

A checked item in `STREAMLIT_EXACT_PARITY_AUDIT.md` is reopened if operator evidence demonstrates missing composition or behavior.

## Acceptance rule

A capability is migrated only when a user can perform the same job from the same logical product area with the same required controls, calculations, evidence, outputs and permissions. The following do **not** count as parity by themselves:

- the API supports the action;
- a React component with the same name exists;
- the capability was moved to another page;
- several old sections were split into separate tools;
- a new workflow reaches roughly the same outcome;
- Doobie can answer a question that deterministic UI previously exposed;
- a backend service or test exists without the original operator surface.

New DoobieLogic capabilities are additive. They may not replace surviving Streamlit functionality.

## Buyer / Purchasing command-center evidence

Review artifact: `ScreenRecording_04-16-2026 22-23-38_1.mp4`, supplied by the product owner on 2026-08-23. The recording shows the Buyer/Purchasing experience as one connected buyer workflow.

The restored DoobieLogic Buyer/Purchasing surface must include and visually/behaviorally verify all of the following together, not merely scattered across unrelated pages:

- [x] Sales Trend visualization in the buyer workflow.
- [x] Revenue by Category visualization in the buyer workflow.
- [x] Top Slow Movers embedded in the buyer workflow.
- [x] Inventory Health score/gauge and supporting inventory condition evidence.
- [x] Doobie Buyer Brief in the same buyer decision flow, preserving deterministic evidence first.
- [x] Inventory Summary with Units Sold and Reorder ASAP evidence.
- [x] Category DOS at a glance.
- [x] Full Forecast Table.
- [x] Forecast Excel export.
- [x] Category expanders in buyer ordering (Flower, Pre-Rolls, Vapes, etc.).
- [x] Nested SKU-level reorder drilldowns with strain/type/size and reorder quantity.
- [x] SKU sales and batch/lot evidence inside reorder drilldowns.
- [x] Full Buyer Filters & Settings surface: search, velocity window, Top N, sort, category/subcategory, vendor/brand, expiration window, on-hand filter, minimum DOH and maximum DOH.
- [x] Inventory-condition KPI block including overstock, expiring inventory, dollar exposure and reorder/out-of-stock conditions.
- [x] Full SKU inventory table and Show all columns behavior.
- [x] Doobie Inventory Check against the current filtered buyer view.
- [x] Continuous workflow composition matching the operator recording rather than requiring page-hopping for core buyer decisions.
- [x] Existing newer replenishment-policy/vendor-policy and durable PO functionality remains available as additive functionality.

Verification evidence: `frontend/src/pages/BuyerOperationsPage.tsx`, `frontend/src/components/BuyerLegacyOverview.tsx`, Buyer parity API tests, and the real-browser responsive matrix in `frontend/e2e/parity-browser.spec.ts`. The browser gate exercises the connected Buyer command center at 390, 430, 768, 1024 and 1440 px and uploads full-page screenshot evidence.

## App-wide recovery rule

The same standard applies to every product area: shell/navigation, Home, Retail Inventory, receiving, audits, purchasing, POs, budgets, trends, delivery analytics, reports, compliance, mapper, Production/Cultivation Inventory, Co-Man, Extraction, White Label/Repack, Package Studio, Commercial Orders/Finance, Admin, users, passwords, roles, organizations, facilities, sandbox, integrations, Doobie, exports and responsive behavior.

No workspace is considered complete until it has been compared against source and available operator evidence at 390, 430, 768, 1024 and 1440 px where applicable.

## Release rule

PR #276 stays draft and must not be treated as production acceptance until:

- every open exact-parity item is resolved or explicitly waived by the product owner;
- legacy evidence items above are verified;
- user/password/role/org/facility/license/sandbox behavior is verified;
- CI is green;
- responsive visual acceptance is complete;
- production deployment/readiness gates pass.
