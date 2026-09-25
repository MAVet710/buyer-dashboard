# Wholesale CRM implementation handoff

Status: CODE_READY. Local implementation only; no push, merge, PR, migration against production, or deployment was authorized for this worker.

## Scope

Wholesale Ops now has Customers and Pipeline entry points with Customer 360. Existing Orders, Fulfillment, Accounting, Inventory, and Storefront tabs remain intact. TradePartner remains customer identity. Assigned rep/owner is a durable free-text rep identifier, with no authentication or permission effect. Relationship status does not override canonical partner eligibility or order gates.

The relationship layer stores facility-specific ownership, account status and next actions, six-stage opportunities, immutable recorded activities, and quote snapshots. Activities include call, email, meeting, note, and task reference. Email activity records history only and sends nothing. Opportunity stages can be corrected or reopened explicitly and are audited.

Quotes use active organization products and existing customer pricing semantics: fixed customer price, otherwise customer percentage discount on the product retail price, otherwise the product retail price. An explicit quoted price overrides the suggestion. Quotes preserve accepted line prices. Conversion locks the quote and uses CommercialRepository.create_order inside the same transaction, creating one canonical draft sales order with a shared audit correlation ID. It neither reserves nor fulfills stock. Repeated conversion returns the same order. Changed product/partner eligibility blocks conversion through existing canonical validation.

## Storage and API

`0080_wholesale_crm` follows `0079_security_observation`. It adds commercial_customer_relationships, commercial_opportunities, commercial_activities, and commercial_quotes with foreign keys, state/value constraints, scope indexes, and PostgreSQL browser-role denial/RLS protection consistent with the preceding migration. No existing records are rewritten. Downgrade refuses to discard CRM evidence.

Endpoints live under `/api/v1/commercial/crm`. Reads retain commercial facility capability enforcement. Writes additionally require dev, admin, supervisor, or buyer. Mutation contracts reject extra scope fields, invalid stages, negative/nonfinite values, empty text and oversized payloads. General audit evidence remains in coman_audit_events.

Customers and pipeline use 50-record pagination. Customer 360 provides latest-50 collections and a merged latest-50 timeline, including audited changes, canonical orders, shipments, invoices, payments, and partner-linked storefront requests. Sales value and open invoice balance are full-account facility aggregates. Storefront requests without a canonical partner link are not heuristically attributed. Detail loading uses a fixed number of queries rather than per-record hydration. Customer 360 intentionally displays only the latest 50 quotes and opportunities per customer; deeper history navigation is a future extension.

## Verification and integration follow-ups

- Backend: 31 focused commercial, CRM, and migration-contract tests passed. New coverage checks tenant/facility isolation, owner/next-action persistence, opportunity stages, pricing, transactional rollback, idempotent canonical conversion, HTTP permissions, timeline aggregation, bounded queries, pagination, and evidence-preserving migration rollback.
- Frontend: lint and production build passed; 107 unit tests passed.
- Chrome: desktop account/quote/activity flow and mobile pipeline/stage editing passed, including payload assertions and a 390px horizontal-overflow check. APIs are mocked for browser tests; backend behavior is tested independently against isolated SQLite.
- The optional legacy `test_commercial_readiness.py` could not collect because this local Python runtime lacks Streamlit. It is separate from the 31 passing tests.
- Integration coordinator must exercise the migration and concurrent quote conversion on isolated PostgreSQL, then run authenticated acceptance and PC release gates if authorized. This worker did not access production data or deploy.
