# Wholesale CRM integration handoff

Status: CODE_READY. Integrated locally onto `c6ff533e`; no push, merge, PR, production migration or deployment, as explicitly requested. Rebase completed without conflicts. Accepted continuity, Buyer UX, permissions/security and Doobie Work features remain in the ancestry.

## Contracts

- `0081_wholesale_crm` follows `0080_doobie_work` and is the single Alembic head. The CRM migration is unreleased: its prior `0080_wholesale_crm` name is replaced, not treated as a deployed upgrade path. Existing deployed databases are untouched. PostgreSQL RLS/browser-role denial and evidence-preserving downgrade remain intact.
- Account and opportunity `owner_user_id` are nullable foreign keys to canonical `app_users`. Assignment requires an active user in the same organization with an eligible facility role (buyer/supervisor/admin/dev), or organization admin/dev authority. A facility CRM permission denial also excludes the owner. Names are display-only, loaded in batches. Owners are searchable and paginated in pages of 50.
- `wholesale.manage_crm` belongs to the existing Wholesale permission group. Default writers remain dev/admin/supervisor/buyer; prior role gates remain mandatory and facility overrides are enforced. Read capability checks remain unchanged.
- `POST /commercial/crm/customers/{partner_id}/follow-ups` creates canonical Doobie Work through WorkService. Customer/opportunity scope is validated; Work assignment checks are retained. Work and its CRM `task_reference` activity commit or roll back together, with correlated audit evidence. The Work route opens the linked Customer 360/opportunity. CRM retains planning text/date only; lifecycle, completion, recurrence and evidence remain in Work. Manually recorded task references must identify Work in the current facility.
- Quote defaults use active facility storefront listings, including the existing quantity-break resolver, followed by shared customer-price rule semantics. Fixed customer pricing wins over storefront pricing; customer discounts apply to the wholesale base. An explicit quote unit price overrides defaults. Conflicting storefront prices or absent valid prices require explicit `unit_price`. Retail MSRP is never a quote fallback and is not returned by the CRM product selector.
- Conversion retains the quote row lock and shared transaction with canonical CommercialOrder creation and audits. Repeated conversion returns the same draft order. No parallel order or inventory reservation is created.
- Customers/pipeline retain 50-record pagination. Customer 360 retains bounded latest-50 collections and a merged latest-50 timeline with full-account scoped financial aggregates. Owner labels add at most one batch query, never per-row reads.

## Verification

- Focused backend: 139 tests across CRM, Work, commercial operations/performance, order-to-cash continuity, storefronts, wholesale/accounting, permissions and migration contracts.
- CRM coverage includes inactive/foreign/facility-ineligible/permission-denied owner rejection, canonical owner persistence, Work reference and rollback, customer/wholesale pricing precedence, retail fallback prohibition, conversion rollback/idempotency, scoped permissions, migration chain/head/FKs, pagination and bounded detail query counts.
- Frontend: lint and production build pass; 124 unit tests pass.
- Chrome (`npx playwright test --config playwright.crm.config.ts`, test-owned loopback server): three mocked-API acceptance checks pass: desktop account/quote/activity/Work follow-up, mobile pipeline editing and 390px overflow, and customer/opportunity return route.

## Remaining acceptance limits

The tests use isolated SQLite and mocked browser APIs. Live PostgreSQL migration/RLS execution and concurrent conversion under PostgreSQL locking remain unverified; Docker is installed but its daemon is unavailable. No authenticated production/public workflow was exercised because deployment is explicitly out of scope. No POS or Dutchie Live work was added.
