# Wholesale Accounting Architecture

Wholesale Accounting is a first-class surface inside **Wholesale Ops**. It is a read-oriented commercial control center built from DoobieLogic's existing durable records; it is not a second accounting ledger.

## Data pooled into Wholesale → Accounting

The accounting hub currently combines:

- **Accounts receivable** from canonical commercial invoices, including current and overdue aging buckets.
- **Invoice balances and status** from `CommercialInvoice`.
- **Recorded customer payments** from `CommercialPayment`.
- **Wholesale sales-order payment state and order value** from the canonical commercial order lifecycle.
- **QuickBooks identity and synchronization metadata** from `AccountingSyncLink` for customers, invoices, Items, vendors, and purchase orders.
- **QuickBooks purchasing reconciliation** comparing current local vendor/PO records with the last successfully synchronized deterministic payload.

The hub stays usable when QuickBooks is not configured. Local invoices, A/R, payments, and order payment state remain available; the QuickBooks section reports that the provider is not connected.

## Source-of-truth rules

DoobieLogic commercial records remain the operational source of truth for the Wholesale workspace. QuickBooks IDs and SyncTokens are external accounting identity/version metadata.

A local reconciliation result does **not** mean QuickBooks was freshly read. The UI must say when it is showing durable local synchronization metadata instead of a provider readback.

QuickBooks vendor and purchase-order writes remain explicitly governed. They require an authorized admin/dev role, a validated facility-scoped QuickBooks connection, and deterministic mapping prerequisites.

## Purchase-order boundary

A confirmed purchase order is a purchasing commitment, not automatically Accounts Payable.

DoobieLogic must not label an open PO as a payable liability unless an actual vendor bill or another authoritative liability record exists. Future accounting depth should therefore keep these concepts separate:

1. **Purchase commitment** — confirmed unfulfilled PO value.
2. **Vendor bill / A/P** — an actual liability supported by a bill or equivalent source record.
3. **Cash payment** — settlement against an authoritative bill/payment record.

This distinction is especially important when QuickBooks Bill/Payment synchronization is added later.

## Mutation boundaries

The Wholesale Accounting dashboard itself is read-only visibility. It does not silently:

- confirm purchase orders;
- create or alter vendor bills;
- post payments;
- change accounting mappings;
- mutate QuickBooks;
- represent stale local metadata as live provider state.

Operational accounting actions can be added as explicit governed workflows, with tenant/facility scope, role checks, idempotency, human confirmation where appropriate, and durable audit evidence.

## Next accounting depth

The next safe additions to this same Wholesale Accounting surface are:

- customer-level outstanding balance exposure and overdue concentration;
- confirmed open purchase commitments by vendor;
- invoices issued and cash collected over selected periods;
- vendor bills / A/P only after an authoritative bill lifecycle exists;
- QuickBooks payment/bill reconciliation only after local lifecycle semantics are explicit and testable;
- margin/COGS only from authoritative historical cost snapshots, never by silently substituting a current product cost for historical cost.
