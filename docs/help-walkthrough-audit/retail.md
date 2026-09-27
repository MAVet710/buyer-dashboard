# Retail Help walkthrough source audit

Status: DOCUMENTATION_UPDATED. Source review only. No browser testing, screenshots, provider calls, database work, installs, deployments or git mutations were performed.

Output: `frontend/src/lib/help/retail.ts`, exporting `retailWalkthroughs: HelpWalkthroughRegistry` with the existing `./types` contract.

Coverage: 16 guides, 100 steps and 150 field descriptions. All six existing Buying guides and all eight existing retail Inventory guides are retained. Two additional retail workflows are documented for lead integration.

| Help route | Application route | Active source |
| --- | --- | --- |
| `/help/buying` | `/buying` | BuyerCommandCenterPage, BuyerOperationsPage, BuyerCurrentInventory |
| `/help/buying/recommendations` | `/buying/recommendations` | BuyingRecommendationsPage, MarketPulse |
| `/help/buying/purchase-orders` | `/buying/purchase-orders` | PurchaseOrdersWorkspacePage, purchaseOrderContinuity |
| `/help/buying/budget` | `/buying/budget` | BuyingBudgetPage |
| `/help/buying/delivery-performance` | `/buying/delivery-performance` | DeliveryImpactPage |
| `/help/buying/planning-settings` | `/buying/planning-settings` | PurchasingPage |
| `/help/inventory` | `/inventory` | InventoryPage, useInventory, InventoryOperationalActions |
| `/help/inventory/receiving` | `/inventory`, Receive inventory | ReceiveInventory, ReceiveHistory |
| `/help/inventory/transfers` | `/inventory/transfers` | InventoryTransfersPage, InventoryTransferManager |
| `/help/inventory/product-360` | `/inventory/products` | RetailProduct360Page, Product360Drawer |
| `/help/inventory/package-360` | `/inventory/packages` | Package360Page, Package360Window |
| `/help/inventory/audits` | `/inventory/audits` | FocusedInventoryAudits, InventoryAudits, CameraScanner |
| `/help/inventory/slow-movers` | `/inventory/slow-movers` | SlowMoversPage |
| `/help/inventory/catalog-admin` | `/inventory/catalog` | ProductMasterPage |
| `/help/inventory/audits/import-inventory` (new) | `/inventory/audits`, Load or refresh Dutchie retail inventory | InventoryAudits |
| `/help/inventory/reconciliation` (new) | `/inventory`, Receive inventory, Reconcile with Metrc | InventoryReconciliationControl |

## Source verification

Active routing and navigation were checked in `frontend/src/App.tsx`, `frontend/src/lib/workspaceRoutes.ts` and `frontend/src/components/AppShell.tsx`. Each guide lists its repository-relative UI and validation evidence in `sourceFiles`; every listed path was checked for existence.

Server sources reviewed include:

- Buying: `backend/app/routers/purchasing.py`, `backend/app/services/purchase_order_continuity.py`, `modules/commercial/repository.py`, `modules/retail_planning/service.py`, `backend/app/routers/buyer_parity.py`, `backend/app/routers/buyer_parity_actions.py`, `backend/app/routers/buyer_legacy_overview.py`, `backend/app/routers/buying_budget_parity.py`, `services/web_buying_budget_parity.py`.
- Stock and receiving: `backend/app/routers/inventory.py`, `backend/app/schemas/inventory.py`, `backend/app/routers/receiving_preflight.py`, `backend/app/services/receiving_preflight.py`, `backend/app/services/inventory_receiving.py`, `backend/app/routers/inventory_reconciliation.py`, `backend/app/services/inventory_reconciliation.py`.
- Transfers: `backend/app/routers/inventory_transfers.py`, `backend/app/schemas/inventory_transfers.py`, `modules/inventory_transfers/service.py`.
- Audits: `backend/app/routers/audits.py`, `backend/app/services/audits.py`, `backend/app/routers/offline_inventory.py`, `backend/app/services/offline_audit_counts.py`, `modules/inventory_audit/repository.py`, `modules/inventory_audit/workflow.py`.
- Product/package/catalog and slow stock: `backend/app/routers/product_360.py`, `backend/app/routers/package_360.py`, `backend/app/routers/product_master.py`, `backend/app/routers/metrc_package_actions.py`, `backend/app/routers/slow_movers_parity.py`, `services/web_slow_movers_parity.py`.

## Differences from the old help

- Buying Recommendations opens Buyer Intelligence. It has a lookback slider, evidence tables and Generate Buyer Brief, but no sorting/filter suite, quantity editor or recommendation-to-PO conversion. Actual conversion occurs through Planning Settings → Build PO, Inventory → Add to PO, or Product 360 → Add / update in PO.
- `/buying` now uses Today, Decide, Act and Analyze. Today/current stock uses saved package stock while uploaded forecasting, budget and slow-stock evidence remain separate sources.
- Purchase Orders uses the saved commercial workspace, not the legacy PDF builder. The draft has Vendor, PO number, Order date, Requested delivery, Notes, product selection, positive quantities, product units, quoted prices and an explicit review checkbox. Save creates a draft; Approve & confirm records committed inbound. Close order only closes detail. There is no saved-order edit, requested-date edit, cancellation or receiving-link control in this workspace.
- Buying Budget is an interactive scenario estimate, not an automatically reconciled budget/PO ledger. On-order cost is entered manually and can initialize from legacy browser-session state.
- Delivery Performance is file-based Delivery Impact Analysis with automatic recalculation, selected sales reuse/upload, manifest matching and comparison controls. No received-date override is visible in the active workspace.
- Inbound receiving requires exact product mapping and two provider reads. Provider quantity, unit and lab state are read-only. The entire remaining package set is reviewed and posted atomically; the form is not a partial-receipt quantity editor.
- The retail receipt UI supplies no commercial order or line IDs, although the receipt service supports and validates explicit PO links. The help does not promise automatic PO fulfillment updates.
- Transfers are cross-facility local ledger movements requiring prior state-system confirmation. Move handles room changes. The receive form takes the full shipped line and has no quantity editor.
- The active Product 360 drawer has Overview, Inventory, Sales, Purchasing, Packages, Compliance and Audits. It does not expose the Product Master tab from the separate older Product360Workspace component.
- Audit first-count completion, required recounts, explicit review, correction-posting choice, pause/resume, stop/reopen, offline replay and separate completion permission are now documented. Completion corrections target current live balances, not merely the snapshot variance.
- Catalog Administration creates products and saves classification, packaging, aliases, mappings and values separately. The visible existing-product detail is not a general SKU/name identity editor.
- Slow Movers displays suggestions and exports a report. It does not apply discounts, transfers or purchasing pauses.

## UI limitations and issues for lead review

1. Manual receipt uses the shared success screen that claims matching provider readback, despite using the direct manual receipt endpoint. It also builds completion labels from `reviewedReceipts`, which are derived from inbound mapped rows rather than the manual receipt. The guide explicitly directs verification through Receive history and does not claim manual provider verification.
2. Inbound completion labels are limited to the first 24 reviewed packages. The guide directs remaining labels through Inventory selection.
3. The audit snapshot import is materially more powerful than its intake wording suggests: it updates product name/base unit/cost/retail price, sets imported lot status to available, and posts balance corrections. Missing cost mappings can become zero. The added guide warns before import; held inventory and source mappings need careful review.
4. Audit creation selects all eligible lots by default and can reset selection when package/source data changes. Scope text is only descriptive. Review the actual Inventory to count list immediately before starting.
5. The physical-count number input has `step="1"` even though backend quantities allow nonnegative floats. A blind first-count dialog hides the expected-quantity metric that otherwise includes the unit. Fractional weight counting and unit visibility merit UI review; no unsupported decimal-entry workaround is prescribed.
6. Offline captures are locally queued, with separate replay status. The completion panel is driven by server pending/recount counts and does not directly disable itself based on `offlineEntries`. The guide requires resolving local captures before completion.
7. Planning Settings exposes a direct Approve & confirm card action without the saved-order workspace's browser confirmation. The help warns before this commitment and recommends reviewing the saved PO first.
8. A Product 360 or Inventory staged quantity can start at 1 even without positive need. Carried selections are deduplicated rather than summed. The help requires quantity review.
9. Read-only reconciliation can render a clean package message alongside a truncated-read warning because summary status and truncation are separate. The help explicitly says an incomplete read is not a complete reconciliation.
10. Direct Package 360 and embedded Package360Window differ. The embedded window adds synchronized regulatory detail, lab results, material lineage and recall views; the direct page mounts MetrcPackageControls. Package regulatory writes are restricted by production capability and verified MA sandbox gates in the server. This retail guide teaches source-trail inspection, not those controlled production-provider mutations; lead should coordinate any detailed controlled-action article with the compliance/production owner.
11. Direct audit routing relies on FocusedInventoryAudits' stored operation/focus context. The retail guide tells the operator to confirm Retail Scan Audit and the facility. Browser captures should verify navigation after a production audit session.

## Validation and remaining integration

- Isolated strict TypeScript check passed for `retail.ts` and its imported types using the existing TypeScript installation with `noEmit`.
- An in-memory registry check passed: all 14 existing retail/Buying help paths present, 16 entries total, 100 unique kebab-case step IDs, 150 field descriptions, nonempty required sections, at least two troubleshooting cases per guide, all source paths present, and no em dashes.
- No full application test suite or browser acceptance was run. No generated screenshots or placeholder image assets were added.
- The lead owns registry integration, the two new paths' navigation/search/SEO entries, screenshot capture and final application gates. Useful capture targets are the saved PO draft/review and confirmed detail, receiving mappings/preflight/result, audit source mapping/count/recount/completion controls, and actual transfer dispatch/receipt forms.
