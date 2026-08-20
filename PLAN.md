# Objective
Build Buyer Dash into a cannabis operating system that can replace Dutchie and Distru as daily systems of record, not merely analyze or integrate with them.

## Product mandate
Buyer Dash must own the operator-facing workflow for retail, inventory, purchasing, traceability, production, wholesale, finance, reporting, customer commerce, and intelligence. Competitor integrations may exist as migration bridges, but the product architecture must not require Dutchie or Distru.

See `docs/COMPETITIVE_REPLACEMENT_ROADMAP.md` for the replacement bar, workstreams, sequencing, and exit criteria.

## Active milestones
1. Operations Inbox and Product 360 decision layer
2. Retail inventory / purchasing system-of-record parity
3. Traceability transaction and reconciliation layer
4. Register / POS and transaction ledger
5. Customer, promotions, loyalty, and commerce surfaces
6. Payment-provider abstraction and reconciliation
7. Package Studio Phase 2 / production ERP / true COGS
8. Wholesale fulfillment, invoicing, A/R, and finance
9. Approval-gated Doobie action framework
10. Enterprise multi-facility, API, SSO, migration, and cutover tooling

## Non-negotiable architecture rules
- One source of truth per operational domain.
- Append-only/auditable transaction history for material state changes.
- AI may analyze, recommend, draft, and explain; deterministic services validate and execute approved actions.
- Traceability and payment failures must be visible, recoverable, and reconcilable.
- Mobile floor workflows must be first-class.
- Long-running workflows must save, stop, and resume.
- Do not claim competitor replacement until the documented replacement exit criteria are met.
