# DoobieLogic Performance Acceptance — 2026-09-02

This acceptance closes the platform-wide performance hardening pass governed by `docs/PERFORMANCE_CONTRACT.md`. The objective is to preserve the current operator UX/UI while proving that common read paths remain bounded as facility history grows.

## Automated realistic-volume gate

`tests/test_realistic_volume_performance.py` seeds data before measurement and then exercises the same production read functions used by the React/FastAPI application.

### Production Ops workspace

Synthetic busy-facility profile:

- 60 products
- 80 customers
- 500 production orders
- 1,000 inventory lots/packages
- 5,000 append-only inventory ledger transactions
- 500 active material reservations
- 300 completed-run actuals
- 60 future crew-capacity records
- 8 configured production machines

Routine Production Ops is now a bounded, summary-first workspace while preserving the existing seven tabs, controls, labels, write actions, and report/export behavior.

Acceptance requirements:

- the common Dashboard returns the latest **200 production orders** and does not hydrate inventory lots, ledger history, reservations, or production actuals
- Inventory & BOM loads on demand and returns at most **250 lots**, **250 ledger transactions**, and **250 material reservations**
- Performance loads on demand and returns at most **200 completed-run actuals**
- large customer/product/resource collections are bounded when their view is opened
- every loaded collection exposes `returned`, `total`, `limit`, `loaded`, and `truncated` metadata
- a truncated working view is disclosed to the operator; records are not silently hidden or deleted
- visible inventory-lot balances are calculated with a set-based CTE/read rather than one SQL query per lot
- the SQL acceptance listener counts both ordinary `SELECT` statements and CTE/`WITH ... SELECT` reads
- the initial/common workspace stays below the 3-second performance-review threshold on the CI runner and does not grow with unrelated historical collections
- section-specific views keep a fixed bounded query/request count as history grows
- the existing Production Ops PDF/report path remains unchanged and continues to use the complete report dataset rather than the routine UI windows

The setup/seed phase is deliberately excluded from timing. This is a regression gate for application read behavior, not a database benchmark.

### Enterprise Control secondary summaries

Synthetic multi-facility history profile:

- 3 active facilities
- 3,315 traceability transactions
- 450 label-review records

Acceptance requirements:

- exactly 4 SQL reads for traceability, SOP-deviation, label-review, and A/R summaries regardless of facility count
- under 3 seconds for the measured read/projection on the CI runner
- preserve the legacy latest-1,000 traceability summary window per facility
- preserve the legacy latest-100 label-review window per facility

The fixture intentionally places rejected traceability records and additional label failures outside those windows so the test proves historical records cannot leak back into current risk scoring.

## Performance work covered by this pass

The completed hardening work now includes:

- Production Planning bounded snapshot instead of workspace + per-run HTTP fan-out
- Label Studio summary-first/detail-on-demand loading and selected-package barcode/QR generation
- Product Master and retail-planning batching
- Production Calendar bounded read model
- Run 360 lightweight product selection
- Production Ops bounded section read models with lazy tab hydration and explicit truncation metadata
- Co-Man inventory balance batching/set-based visible-lot balances without long-lived stale inventory caches
- API response compression for larger JSON payloads
- Commercial/Wholesale order-line batching without expanding order-ID bind lists
- Enterprise Control grouped inventory/order/production summaries
- Enterprise Control grouped traceability/compliance/finance summaries with preserved legacy windows
- request timing headers and slow-request logging
- engineering requirements that prohibit per-row HTTP and SQL fan-out

## UX/UI preservation

The performance refactor does not redesign Production Ops. The original React page is retained as the operator surface, including:

- Dashboard
- New Job
- Schedule
- Resources
- Inventory & BOM
- Customers
- Performance
- Production Control drawer

A thin wrapper only hydrates the selected section into the existing React Query cache. Existing mutations still invalidate the canonical query and the active section is automatically rehydrated after the mutation refresh. The only intentional visible addition is a concise notice when a routine window is truncated so operators know exactly how many records are displayed.

All pre-existing write routes, validation, tenant/facility scoping, audit behavior, and the Production Ops report/export endpoint remain on the original implementation.

## Release bar

This performance pass is complete only when the final acceptance head passes the normal repository gates as one combined revision: backend tests, frontend tests/build, responsive browser parity, operator browser testing against real FastAPI, production migrations/startup, container vulnerability scans, secret-history scan, and the isolated Release Candidate Preview smoke test.

Release-candidate container images are published under commit-identified immutable tags. If a preview run is interrupted after publishing a tag, certification must use a fresh acceptance revision rather than attempting to overwrite the existing registry tag on a rerun.

The acceptance tests do not replace production telemetry. `Server-Timing`, `X-Response-Time-Ms`, and slow-request warnings remain the source for identifying environment-specific or future workload regressions after release.
