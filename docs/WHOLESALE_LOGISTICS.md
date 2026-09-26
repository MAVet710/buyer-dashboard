# Wholesale dispatch and logistics

Status: CODE_READY for local integration. No push, PR, merge, deployment or production migration is authorized in this task.

The two logistics commits (originally `5415c34a` and `92c39346561879f26d78ffb0ba9adf6ba2ab68d5`) were rebased onto the exact adoption candidate `5ad6c59a6d451234fa1f712e5233d542450b21a6`. Work, CRM, White Label, Readiness/Reporting and Integration Wizard remain present. The integration preserves both CRM and dispatch permissions and both Pipeline and Logistics navigation.

Wholesale Ops > Logistics tracks physical dispatch against existing CommercialShipment records. Canonical order and customer references come from the shipment/order chain; manifest references are read directly.

- All five run snapshots are optional: `driver_name`, `driver_license_number`, `vehicle_license_plate_number`, `vehicle_make`, `vehicle_model`. Omitted, null and blank values are supported. These fields do not form a driver master or rewrite provider proposals.
- Runs retain service date, notes, optimistic version and status derived from stops. Up to 100 ordered stops retain address/contact snapshots, planned windows and coordinates. A shipment belongs to at most one stop. Planning locks when loading begins.
- Deterministic planning keeps the first stop fixed and uses straight-line nearest neighbors with stable ID ties. Missing coordinates leave order unchanged. There is no map provider, traffic model or road optimization.
- Driver transitions are planned -> loaded -> en_route -> arrived -> delivered / partial / rejected; partial/rejected can progress to returned. En-route requires an existing governed manifested/shipped shipment and manifest reference.
- Delivered/partial require recipient evidence and an aware delivery timestamp. Exceptions require reconciliation notes. Status retries cannot overwrite POD; returned remainders preserve original partial evidence.
- Dispatch never changes CommercialOrder fulfillment, fulfilled quantities, inventory, invoice state or canonical shipment delivered_at. Returns, credits and inventory reconciliation remain canonical domain workflows.

## Explicit Work reconciliation

`POST /api/v1/wholesale-logistics/runs/{run_id}/stops/{stop_id}/create-reconciliation-work` accepts `{ "version": <observed run version> }`. The action requires the commercial facility capability, wholesale view/mutation permission and Work's existing writer role plus `work.create` permission. Permission overrides remain facility scoped; an allow override does not bypass the Work role gate. The generalized permission registry retains prior default role behavior. Canonical Work creation, template creation and recurrence generation all respect `work.create` denial.

The service locks the scoped run and stop, rejects removed/non-exception stops and stale first creation, then creates Work, records its audit, stores the nullable `work_item_id` pointer and records the dispatch audit in one transaction. Both audits share the dispatch correlation ID. An exception with an existing scoped pointer returns that ID without creating or mutating Work, including retry after a lost successful response. Deleting Work through a separately governed process sets the pointer to NULL; there is no logistics Work deletion API.

Work receives workspace `Wholesale`, entity type `wholesale_dispatch_stop`, entity ID equal to the stop ID, and `/wholesale?tab=fulfillment&dispatch=<run_id>&stop=<stop_id>`. This route selects Logistics and loads the exact run independently of today's board page, highlighting and scrolling to the exact stop. The UI provides **Create reconciliation work** or **Open Work**. Status changes never automatically create Work. Assignee, due date, priority and task status remain exclusively in Work; completing Work cannot change dispatch or fulfillment.

## Migration and performance

Single head `0084_wholesale_logistics` follows `0083_onboarding_reporting`, preserving the 0080 Work -> 0081 CRM -> 0082 White Label -> 0083 adoption chain. The migration adds dispatch tables and `work_item_id REFERENCES doobie_work_items(id) ON DELETE SET NULL`.

PostgreSQL tables enable RLS, revoke public/browser-role access, and grant CRUD conditionally to the existing server runtime identity. Downgrade retains a five-second lock timeout, locks both dispatch tables ACCESS EXCLUSIVE, and refuses to drop either if either has records. No operational evidence is removed.

Board pages contain at most 100 runs, candidate pages 200 shipments and run details 100 stops. Reads use 2, 1 and 2 SQL queries respectively, independent of rows within those bounds. Work handoff uses bounded point lookups and does not hydrate unrelated Work queues or provider data.

## Validation and remaining release gates

Validation includes SQLite schema/model parity and SET NULL execution, PostgreSQL DDL/ACL/lock contracts, migration chain, transactional rollback, repeat handoff, exact return route, permission denial, stale/removed/non-exception rejection, fulfillment/invoice isolation, immutable POD, and bounded queries. Browser acceptance uses synthetic API fixtures at 390px and 1280px and covers Work creation, opening Work, returning to the exact stop, reload and mobile overflow.

Live PostgreSQL upgrade, lock-contention/runtime-role verification, and authenticated PC/public acceptance remain release gates. Local SQL/mock tests do not establish those live results. Deployment is explicitly excluded by this task.

Final local results (2026-09-25): 230 combined logistics/Work/permission/CRM/White Label/adoption/commercial/migration/Integration Wizard tests passed, plus 11 wholesale order-to-cash/accounting/operations tests (241 total). All 140 frontend tests passed; lint and production build passed. Both synthetic browser checks passed at 390px and 1280px. Repository quality gate passed across 413 source files. Alembic reports only `0084_wholesale_logistics`. The backend emitted one existing Starlette/httpx deprecation warning. Rebased commits are `86ea3cf0` (implementation) and `9ccfd5e1` (unchanged hardening patch); subsequent integration adds the Work handoff and migration renumbering.
