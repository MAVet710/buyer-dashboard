# Web cutover gates

The React application at `https://ops.doobielogic.io` must not replace the
Streamlit application until every required gate below passes against the same
production-shaped database and facility permissions.

## Platform

- [ ] Supabase JWT authentication, sign-out, session refresh, and account recovery
- [ ] Organization, facility, license, role, and feature authorization
- [ ] Supabase Data API is disabled; browser data access is Supabase Auth plus FastAPI only
- [ ] Production database is at Alembic `0037_function_acl_hardening`
- [ ] `PUBLIC`, `anon`, and `authenticated` have no direct operational table/sequence/function privileges that bypass FastAPI
- [ ] Stable API errors, audit metadata, request IDs, logging, and health checks
- [ ] Durable uploads, exports, background jobs, retry behavior, and observability
- [ ] Responsive desktop, tablet, phone, scanning, and accessibility checks

## Home and shared navigation

- [ ] Operations Home, Inbox, universal search, Product 360, and Package 360
- [ ] Role/license-aware navigation and active facility switching
- [ ] Cross-workspace links preserve organization and facility context

## Retail Ops

- [ ] Durable products and packages, sales history, velocity, DOH, margin, and aging
- [ ] Purchasing, PO builder, approvals, inbound queue, receiving, and receive history
- [ ] Holds, testing, labels, adjustments, transfers, audits, and reconciliation
- [ ] Trends, slow movers, delivery impact, reports, compliance, and exports

## Production Ops

- [ ] Materials/packages, plants where licensed, rooms, testing, QA, and holds
- [ ] Receiving, receive history, reservations, WIP, transformations, and lineage
- [ ] Production planning/execution, BOMs, yields, waste, true COGS, and Package Studio
- [ ] Extraction, white label/repack, audits, reports, traceability, and exports

## Commercial and data operations

- [ ] Partners, orders, allocation, pick/pack, manifests, fulfillment, invoices, and A/R
- [ ] Data Hub imports, mappings, integration settings, legal acceptance, and admin tools
- [ ] Doobie read/explain/recommend/draft/preview/approve flows preserve safety boundaries

## Release

- [ ] Encrypted production backup and isolated restore verification pass immediately before database changes
- [ ] Database migrations pass on a production-shaped clone with rollback evidence
- [ ] Legacy Supabase Auth migration dry-run passes before any Auth user is created
- [ ] Imported legacy accounts pass username/password sign-in, refresh, sign-out, recovery and facility-switch checks
- [ ] API unit/integration tests and React component/browser tests pass
- [ ] Streamlit-to-React parity scripts pass for representative facility datasets
- [ ] Security, tenant-isolation, mobile, performance, backup, and recovery checks pass
- [ ] Zero-traffic Cloud Run candidate and Cloudflare preview pass production-shaped verification
- [ ] Pilot facility acceptance and documented rollback plan are complete
