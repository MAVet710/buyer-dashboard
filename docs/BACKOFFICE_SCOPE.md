# Buyer Dash Backoffice Product Boundary

Last reviewed: 2026-08-20

## Current goal

Buyer Dash Backoffice is the system of record and operating environment for cannabis retail, production, wholesale, compliance, and finance workflows.

The current build phase is explicitly focused on replacing:

- Dutchie Backoffice
- Distru ERP

A future Buyer Dash POS will be a separate application/URL. It will consume Backoffice APIs/events and will not duplicate catalog, inventory, package, pricing, customer, loyalty, tax/compliance, or traceability business logic.

## Backoffice owns

- organization, facility, license, user, role, and permissions context
- product/catalog master and nomenclature
- package/lot master and source genealogy
- sellable, reserved, inbound, hold, quarantine, WIP, and finished inventory state
- inventory ledger, adjustments, labels, counts, audits, and reconciliations
- vendor master, cost history, purchasing budgets, purchase orders, approvals, and receiving
- manifests/transfers and internal movement
- traceability adapters, transaction queue, idempotency, retries, external responses, and reconciliation
- COAs/lab state and release readiness
- production planning, BOMs/recipes, reservations, actuals, package transformations, yield, waste, QA, labor/material COGS, and rework
- wholesale CRM, sales orders, allocation, pick/pack, shipping/manifest state, invoices, A/R, returns, and customer portals
- pricing rules, promotions, loyalty rules, customer identity/consent, and eligibility data that future sales channels can consume
- financial events, landed cost, COGS, revenue, discounts, tax, payments/settlements references, margin, and reporting
- Product 360, Package/Source 360, Operations Inbox, search, reporting, and Doobie intelligence/action drafts
- multi-facility administration, import/migration tooling, APIs, webhooks/events, and enterprise controls

## Separate future POS owns

The future POS application owns only the register-specific interaction layer:

- cashier/register UX
- cart UX
- scanning UX
- till/shift interaction
- tender/payment terminal interaction
- receipts
- customer-facing checkout interaction

The POS must call Backoffice for authoritative product, package, inventory, pricing, promotion, customer/loyalty, purchase-limit, tax/compliance, and traceability decisions, then post completed transaction events back to Backoffice.

## Architectural contract

1. Backoffice remains usable without a POS connected.
2. POS remains replaceable because business logic lives in Backoffice services, not the register UI.
3. Dutchie and Distru are never required dependencies.
4. External state systems such as Metrc/BioTrack remain regulated adapters, not Buyer Dash's primary operational database.
5. Payment processors remain provider adapters; Buyer Dash stores only the operational references needed for reconciliation.
6. Every material state change is durable, tenant-scoped, permissioned, and auditable.
7. AI never mutates source-of-truth state directly; approved actions pass through deterministic services.

## Current execution priority

1. Finish the deterministic Operations Inbox and Product 360 decision layer.
2. Make inventory/purchasing/receiving/transfer continuity complete enough to replace Dutchie Backoffice.
3. Complete provider-neutral traceability transactions and reconciliation.
4. Expand Package Studio and production accounting until it can replace Distru manufacturing/ERP workflows.
5. Complete wholesale/CRM/invoicing/A/R and true financial/COGS continuity.
6. Expose stable Backoffice APIs/events for future POS and commerce clients.
