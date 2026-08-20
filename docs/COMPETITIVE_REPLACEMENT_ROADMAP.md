# Buyer Dash Competitive Replacement Roadmap

Last reviewed: 2026-08-20

## Product mandate

Buyer Dash is not a reporting layer that depends on Dutchie or Distru as permanent systems of record.

The end state is a cannabis operating system that can replace both products for an operator:

- retail register and back office
- catalog, inventory, packages, purchasing, receiving, transfers, labels, audits, and reporting
- state traceability integration and reconciliation
- production planning, BOMs, package transformations, WIP, QA, yield, waste, and true COGS
- wholesale CRM, sales orders, fulfillment, pick/pack, manifests, invoicing, A/R, and customer portals
- e-commerce, customer identity, promotions, loyalty, delivery/kiosk/mobile ordering, and payment orchestration
- multi-company and multi-facility administration
- deterministic operational intelligence plus approval-gated AI assistance

Integrations with Dutchie or Distru may exist only as migration bridges or optional interoperability. New architecture must not require either competitor to operate Buyer Dash.

## Competitive baseline

Official product surfaces reviewed for this roadmap:

- Dutchie POS: https://dutchie.com/business/pos
- Dutchie E-Commerce: https://dutchie.com/business/ecommerce
- Dutchie Payments: https://dutchie.com/business/payments
- Distru cannabis ERP: https://www.distru.com/cannabis-erp

The replacement bar is the combined capability footprint, not one competitor in isolation.

## Product rules

1. **One operational graph.** Products, packages/lots, facilities, partners, orders, production runs, audits, compliance events, customers, and financial events must connect to one durable model.
2. **One source of truth per domain.** UI modules may project the same state differently but must not create competing inventory, sales, production, or customer ledgers.
3. **Enter data once.** Receiving, package operations, checkout, production, fulfillment, and traceability submissions should reuse the same underlying records.
4. **Every exception leads to an action.** Dashboards must route directly into the authoritative workflow.
5. **Every action is auditable.** Inventory, compliance, production, payment, discount, refund, and administrative state changes require actor/time/reason/history.
6. **Save, stop, resume.** Long workflows cannot trap an operator in a single session.
7. **Mobile is a first-class operating surface.** Counts, receiving, pick/pack, package work, floor inventory, and manager approvals must work well on phones/tablets.
8. **AI is not the ledger.** AI can analyze, explain, draft, and recommend. Deterministic code validates and executes approved operational actions.
9. **Traceability failures are visible.** Buyer Dash must never silently pretend a Metrc/BioTrack action succeeded.
10. **No fake parity.** A page name does not count as a capability until the workflow is durable, permissioned, tested, and recoverable.

## The shared operating graph

### Product

Connects catalog identity, brand, strain, category, tax/compliance attributes, packages, vendors, cost history, pricing, sales, purchasing, production recipes, customer demand, and audit history.

### Package / lot

Connects source material, child outputs, location, quantity, reservations, test/COA state, expiration, traceability identity, inventory transactions, production consumption, sales allocation, transfers, and audit history.

### Partner

Supports vendor, customer, or both. Connects licensing, terms, contacts, price lists, POs, sales orders, invoices, payments, fill rate, lead time, and performance history.

### Order

Purchase and sales orders share common durable lifecycle concepts while preserving domain-specific rules. Orders connect products, quantities, lots, pricing, allocations, receipts/shipments, manifests, invoices, and payments.

### Production run

Connects recipe/BOM, reservations, actual inputs, outputs, package lineage, labor, machine time, non-cannabis materials, yield, waste, rework, QA, and actual COGS.

### Compliance event

Append-only record of requested action, validation, external submission, response, retry/reconciliation state, external identifiers, actor, and linked operational object.

### Customer

Connects identity, consent, purchase history, loyalty, promotions, preferences, online/in-store orders, returns, and payment references without making sensitive payment credentials part of the general operational dataset.

### Financial event

Connects landed cost, COGS, revenue, discount, tax, payment, refund, invoice, settlement, and margin back to the operational event that caused it.

# Replacement workstreams

## 1. Operations Home and universal decision layer

Status: **In progress**

Required:

- deterministic Operations Inbox ranked by regulatory risk, urgency, and financial impact
- one-click route from exception to source workflow
- universal product/package/tool search
- Product 360 as the common product work window
- Package 360 / Source Trail for lot-level genealogy
- cross-workspace event timeline
- Doobie explanation layer that cites the deterministic evidence behind a recommendation

Current implementation already includes flat navigation, global search, Product 360, Package Studio, and the first deterministic Operations Inbox service.

Exit criteria:

- an operator can start the day from Home and reach every material exception without hunting through separate reports
- every inbox item is derived from source data and has an authoritative action route

## 2. Retail inventory and purchasing system of record

Status: **Strong foundation / parity work continuing**

Required:

- product and package views
- stock/hold/quarantine/testing/WIP/inbound/allocated states
- purchase planning and budget controls
- vendor price and lead-time history
- POs and approvals
- inbound queue and receiving against PO/manifest
- shortage/overage/damage reconciliation
- catalog mapping during receiving
- lab/COA ingestion
- labels and barcode/QR workflows
- adjustments with reason and external-sync state
- transfers and internal moves
- blind and non-blind audits
- resumable cycle counts and multi-audit lifecycle
- discrepancy investigation and approval
- inventory valuation and aging

Exit criteria:

- a retail operator can run purchasing, receiving, package inventory, counts, adjustments, and transfers without Dutchie Backoffice

## 3. Traceability transaction and reconciliation layer

Status: **Read/adjustment foundations exist; full transaction layer required**

Required state machine:

`requested -> validated -> queued -> submitted -> accepted | rejected -> verified | reconciliation_required`

Required:

- Metrc/BioTrack adapter abstraction
- credentials scoped by user/license/facility
- packages/items/transfers/lab reads
- package creation and finishing
- package adjustment
- package merge/split where jurisdiction API supports it
- transfer/manifest actions
- sales reporting actions required by jurisdiction
- production/package transformation submissions
- retry queue with idempotency keys
- external response archive
- Buyer Dash vs external-state reconciliation screen
- explicit conflict resolution with actor/reason
- health and backlog monitoring

Exit criteria:

- normal inventory, package, production, receiving, transfer, and sales workflows do not require the operator to manually duplicate the same work in the state traceability portal

## 4. Register / POS

Status: **Major replacement gap**

This is mandatory to replace Dutchie rather than coexist with it.

Required register core:

- employee sign-in / till assignment
- shift and drawer lifecycle
- customer lookup and anonymous transaction support as permitted
- ID/age verification hooks
- medical/adult-use eligibility and purchase-limit engine
- live sellable inventory by package
- barcode scanning
- cart and line-item edits
- jurisdiction-aware taxes
- discounts, promotions, bundles, coupons, employee discounts, and manager overrides
- loyalty earn/redeem
- cash and external payment tender abstraction
- split tender where supported
- tips where supported
- receipt print/email/SMS abstraction
- return/refund/void lifecycle
- reason codes and manager approval
- offline-safe transaction queue design
- sales ledger posting
- package quantity decrement
- compliance reporting queue
- end-of-day reconciliation

Register UX target:

- common sale in a few taps
- no separate inventory reconciliation after checkout
- package, customer, loyalty, discount, payment, tax, and traceability state all flow from the same transaction

Exit criteria:

- a dispensary can complete a full day of compliant retail sales without Dutchie POS

## 5. Consumer commerce

Status: **Major replacement gap**

Required:

- live public menu from Buyer Dash catalog/sellable inventory
- pickup ordering
- delivery ordering and delivery zones
- customer accounts and social/email/SMS sign-in abstraction
- cart and checkout
- loyalty visibility/redemption
- promotions and personalized offers
- scheduled pickup
- order status notifications
- abandoned-cart and back-in-stock events
- kiosk mode
- mobile/PWA surface first; native app can follow
- SEO/indexable storefront architecture where desired
- analytics/event instrumentation

Exit criteria:

- online and in-store sales consume the same catalog, prices, promotions, inventory, customer identity, and order ledger

## 6. Loyalty, promotions, and customer CRM

Status: **Major replacement gap**

Required:

- customer profile and consent
- loyalty points ledger
- tiers
- earn/redeem rules
- promotions engine with eligibility/stacking rules
- segments
- visit, spend, basket, category, brand, and recency analytics
- customer notes with permissions
- campaign/export/webhook interfaces
- customer lifetime value and churn signals
- returns/refunds impact on loyalty ledger

Exit criteria:

- no external loyalty system is required for core earn/redeem and promotion behavior

## 7. Payments and cash management

Status: **Platform orchestration required; payment rails remain provider-backed**

Buyer Dash does not need to become a bank or payment network to replace Dutchie as the operator-facing application. It must own the payment workflow, ledger, reconciliation, and provider abstraction.

Required:

- tender abstraction
- cash drawers
- cash drops/payouts
- external ACH/pay-by-bank provider adapter
- compliant debit/other provider adapters where legally available
- terminal/device abstraction
- payment authorization/result references
- tips
- refunds
- settlement import
- transaction-to-settlement reconciliation
- failed payment/reversal handling
- payment-provider health
- no raw bank credentials or card data in general app storage

Exit criteria:

- the operator uses Buyer Dash for checkout and reconciliation while payment processing occurs through interchangeable approved providers

## 8. Production ERP / Package Studio Phase 2+

Status: **Strong foundation / Distru depth still to close**

Required:

- versioned BOMs/recipes
- cannabis and non-cannabis components
- multi-input / multi-output runs
- material reservations
- WIP
- planned vs actual consumption
- labor and machine actuals
- expected vs actual yield
- waste/loss/rework
- QA holds/releases
- samples
- Package Studio lineage
- production scheduling and capacity
- true run and unit COGS
- landed packaging/material costs
- traceability submissions

Exit criteria:

- cultivator/manufacturer can plan, execute, cost, trace, and release production without Distru

## 9. Warehouse, wholesale, and commercial ERP

Status: **Foundation exists**

Required:

- vendor/customer/both partner CRM
- customer-specific price lists
- credit limits and payment terms
- sales orders
- purchase orders
- lot allocation
- FEFO/FIFO policy support
- mobile pick/pack
- shipment staging
- internal transfers
- manifests
- delivery routes
- returns
- samples
- invoices
- payments
- A/R aging
- customer portal and wholesale ordering
- sales rep ownership/commissions where needed

Exit criteria:

- wholesale teams can sell, allocate, pick, manifest, ship, invoice, and reconcile without Distru

## 10. Financial intelligence

Status: **Partial**

Required:

- cost history
- landed cost
- inventory valuation
- actual production COGS
- retail and wholesale gross margin
- discount impact
- write-off/waste impact
- invoice and payment state
- A/R
- payment settlement reconciliation
- accounting export/API adapters
- facility/product/category/brand/package/run/customer/vendor profitability

Exit criteria:

- operational margin is explainable back to package/run/order/transaction source events without spreadsheet reconstruction

## 11. Doobie operating layer

Status: **Read-only specialist agent foundation exists**

Progression:

1. **Analyze** — bounded read-only tools.
2. **Explain** — cite the exact operational evidence.
3. **Recommend** — deterministic candidate actions with AI explanation.
4. **Draft** — build POs, count plans, transfers, production plans, customer follow-ups, or other drafts.
5. **Preview** — deterministic validation shows the exact change and compliance/financial impact.
6. **Approve** — authorized human confirms.
7. **Execute** — non-AI service code performs the operation and writes the audit trail.

No direct unconstrained model mutation of Buyer Dash, Metrc, payments, or customer data.

Exit criteria:

- common operating decisions can move from detection to approved action without manually rebuilding the same context in another screen or spreadsheet

## 12. Enterprise, platform, and migration

Required:

- multi-organization / multi-license / multi-facility hierarchy
- cross-facility inventory and centralized purchasing
- enterprise roles and custom permissions
- SSO
- API keys/service accounts
- webhooks
- public/private API boundaries
- audit/event export
- disaster recovery
- background job queue architecture
- device management for register/kiosk/label hardware
- observability and alerting
- migration importers for Dutchie and Distru exports
- optional transitional sync connectors during cutover

Exit criteria:

- a multi-site operator can migrate from competitor systems without losing source history and can operate Buyer Dash as the primary platform

# Current build sequence

## Phase A — Decision layer and product graph

- [x] Flat business navigation
- [x] Universal local search
- [x] Product 360 foundation
- [x] Package Studio / Source Trail foundation
- [x] Inventory v2 command center
- [x] Durable/resumable audit foundation
- [x] Labels and inventory adjustment workflow
- [ ] Operations Inbox UI and ranked exceptions
- [ ] Product 360 v2: supply, package, audit, compliance, margin, and recommendation context
- [ ] Package 360 / unified event timeline

## Phase B — Traceability and transaction reliability

- [ ] Compliance transaction event model
- [ ] queued/idempotent external actions
- [ ] reconciliation center
- [ ] package creation/finish/transfer workflows
- [ ] production and sales traceability actions

## Phase C — Retail replacement

- [ ] Register transaction ledger
- [ ] tax/purchase-limit engine
- [ ] cash drawer/tender lifecycle
- [ ] discount/promotion engine
- [ ] customer + loyalty ledger
- [ ] returns/refunds/voids
- [ ] online ordering
- [ ] kiosk/mobile ordering
- [ ] payment-provider abstraction and settlement reconciliation

## Phase D — Production ERP replacement

- [ ] Package Studio Phase 2 multi-input workflows
- [ ] durable recipe/BOM management UI
- [ ] reservations/WIP
- [ ] run actuals and yield
- [ ] non-cannabis material inventory
- [ ] true run-level COGS
- [ ] QA release workflow

## Phase E — Commercial and financial replacement

- [ ] price lists and terms
- [ ] mobile pick/pack
- [ ] shipment/manifest lifecycle
- [ ] invoicing and A/R
- [ ] customer/wholesale portal
- [ ] accounting adapters
- [ ] profitability drilldowns

## Phase F — Agentic operating system and enterprise

- [ ] recommendation evidence contracts
- [ ] draft/preview/approve/execute action framework
- [ ] multi-facility command center
- [ ] SSO/API/webhooks
- [ ] migration/cutover toolkit

# Definition of "replaces Dutchie and Distru"

Buyer Dash only claims replacement when a reference operator can perform all of the following without either competitor being required for daily operations:

1. open/close a retail day and ring compliant sales
2. maintain catalog, price, promotions, customers, loyalty, and sellable inventory
3. receive, count, adjust, transfer, trace, and label packages
4. purchase from vendors and manage inbound inventory
5. synchronize/reconcile required state traceability actions
6. run production from BOM through finished package with actual COGS
7. sell wholesale, allocate lots, pick/pack, manifest, ship, invoice, and collect
8. operate online ordering/customer surfaces
9. reconcile tenders, settlements, invoices, inventory value, and margin
10. manage multiple facilities/roles with complete audit history
11. use Doobie to identify, explain, draft, and safely accelerate operational decisions

Until all eleven are true, competitor parity remains a roadmap target rather than a marketing claim.
