# Objective
Build Buyer Dash Backoffice into the cannabis operating system that can replace Dutchie Backoffice and Distru as the operator's daily system of record.

A future Buyer Dash POS will live at a separate URL/application and communicate with Backoffice through stable APIs/events. The current Backoffice program must not depend on Dutchie POS, Dutchie Backoffice, or Distru to operate.

## Product mandate
Buyer Dash Backoffice must own the operator-facing workflow and authoritative records for catalog, inventory, packages/lots, purchasing, receiving, transfers, traceability, production, wholesale, finance, reporting, customer/loyalty rules, and intelligence.

Competitor integrations may exist as migration bridges or optional interoperability, but the Backoffice architecture must not require Dutchie or Distru.

See `docs/COMPETITIVE_REPLACEMENT_ROADMAP.md` for the complete replacement bar and `docs/BACKOFFICE_SCOPE.md` for the current product boundary.

## Active Backoffice milestones
1. Operations Inbox and Product 360 decision layer
2. Retail inventory / purchasing system-of-record parity
3. Traceability transaction and reconciliation layer
4. Receiving, transfer, package, and source-of-truth continuity
5. Package Studio Phase 2 / production ERP / true COGS
6. Wholesale fulfillment, invoicing, A/R, CRM, and finance
7. Pricing, promotions, loyalty, and customer-domain rules exposed for future channels
8. Approval-gated Doobie action framework
9. Enterprise multi-facility, API, SSO, migration, and cutover tooling
10. Stable Backoffice API/event contracts for a future separate Buyer Dash POS

## Deferred separate application
Register/POS UI, till/shift UX, payment terminal UX, receipt UX, and consumer checkout surfaces are intentionally not part of the current Backoffice implementation phase. They will consume Backoffice services later rather than live inside the Backoffice URL.

## Non-negotiable architecture rules
- One source of truth per operational domain.
- Append-only/auditable transaction history for material state changes.
- AI may analyze, recommend, draft, and explain; deterministic services validate and execute approved actions.
- Traceability failures must be visible, recoverable, and reconcilable.
- Mobile Backoffice floor workflows must be first-class.
- Long-running workflows must save, stop, and resume.
- Backoffice APIs/events must be channel-neutral so a future POS, e-commerce app, kiosk, or mobile client can consume them without duplicating business logic.
- Do not claim competitor replacement until the documented replacement exit criteria are met.
