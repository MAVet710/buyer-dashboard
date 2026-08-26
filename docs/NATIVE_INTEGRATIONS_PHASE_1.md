# Native integrations phase 1

DoobieLogic treats Metrc, BioTrack, accounting systems, printers, and external equipment as credentialed providers. Internal queue state never implies that an external regulator or vendor accepted a transaction.

## Production rules

- Credentials are scoped to organization, facility/license, and provider.
- Provider secrets stay encrypted at rest and are never returned by read APIs.
- Reads and writes are idempotent where the provider permits it.
- Every outbound mutation records request, provider response, retry state, and reconciliation state.
- Provider failures surface as operational exceptions instead of silently falling back to uploaded data.
- Production activation requires real vendor credentials and any required certification/approval.
- Sandbox providers remain isolated from production provider records.

## Phase 1 targets

1. Metrc and BioTrack connection health, license/facility validation, read synchronization, queued mutation dispatch, retries, and reconciliation.
2. QuickBooks Online connection lifecycle and deterministic accounting export/sync contracts for customers, vendors, invoices, credits, payments, bills, purchase orders, and summarized COGS/valuation entries.
3. Label print jobs with versioned templates, printer profiles, immutable print history, and LabelGuard approval linkage.
4. Receiving/manifest reconciliation that ties purchase orders, inbound state transfers, package scans, discrepancies, COAs, and accepted inventory together.
5. External API and webhook operator documentation with scoped service-account permissions and signed-delivery semantics.

No connector is represented as live until its credentialed health check succeeds.