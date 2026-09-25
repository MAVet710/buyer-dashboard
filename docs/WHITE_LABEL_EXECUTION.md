# White Label / Repack execution handoff

The planner saves organization/facility-scoped documents in `white_label_plans`.
It preserves form inputs, package allocations, source/COA references and
server-calculated expected outputs and economics. These are estimates, not
inventory balances, verified label values, or posted accounting costs.

Save and approval require an existing weight-based lot with available/released
status, passed canonical QA evidence with a COA reference, matching ledger units,
and sufficient shared availability after production and wholesale commitments.
Browser COA text cannot override canonical evidence. Draft edits use a revision
check. Approved plans are immutable; duplicate a plan to revise its estimates.

Approval locks the plan and atomically creates exactly one canonical
`coman_production_orders` draft with the source and expected allocations. It
records correlated canonical audit events and does not reserve or deduct stock.
Retries return the linked order. The operator reviews actual output SKU mapping,
materials, quantities, costs and QA through existing execution workflows.

Production Run 360 displays the saved handoff. Package Studio opens the exact
source and includes the production order link in its existing preview/commit
flow. Its commit revalidates White Label scope, source identity, QA and current
availability. It never silently replaces an unavailable source. Output products
require explicit selection. Existing Package Studio inventory and lineage
records remain authoritative. Label Studio resolves resulting packages and
verified COA evidence through its existing workflow. No provider write is sent
by plan save, approval or handoff.

The document stores draft, approved or cancelled status. The API projects
executing/completed/cancelled from durable canonical execution: in-progress or
held production orders, or a committed linked Package Studio transformation,
mean executing; a completed production order means completed. Final QA and
production closure remain in Production Run 360. Cancel a draft in the planner;
cancel an approved execution through the existing production workflow.

Reads use bounded, paged plan summaries and searchable lot summaries. The
selected plan loads its details on demand. Session storage is no longer the
plan source of truth; the existing PDF export remains available.

Apply migration `0082_white_label_execution` after `0081_wholesale_crm`
(which follows `0080_doobie_work`) before enabling the new application code.
It adds one planning table, foreign keys, a unique execution link, scope index
and browser-role restrictions. It changes no existing business rows. Downgrade
refuses to discard saved plans; PostgreSQL locks the table before checking for
evidence, with a five-second lock timeout. Empty-table rollback leaves CRM and
Doobie Work intact.

The generalized `white_label.manage_plans` permission gates save, approval and
cancellation. Defaults preserve dev/admin/buyer/planner/supervisor behavior;
explicit denies apply and explicit allows cannot bypass existing role or
facility-capability checks. Read access keeps the existing facility gates.
Approval retries use the same status projection as list/detail, including
committed Package Studio runs, and return the existing production order.

Doobie Work retains its explicit operator-created work and linked route/entity
fields. This integration does not create tasks automatically or add a separate
White Label task ledger.

Integration validation (September 25, 2026): 191 backend tests passed across
White Label, repack, Package Studio, inventory commitments, production start,
Run 360 QA/mutation previews, generalized permissions, migration contracts and
rollback, Wholesale CRM, Doobie Work, and structured COA/label lineage. All 127
frontend unit tests, lint and production build passed. Two mocked-API Chromium
acceptance tests passed at desktop 1440px and mobile 390px, covering save,
unsaved-change approval blocking, durable reload, execution handoff and
executing/completed/cancelled display with execution and label links.

Status: CODE_READY, local integration only. Rebased from the completed White
Label commit onto CRM candidate `42a2fe3691e188443e2620aeb11aa75e51256c49`
without Git conflicts. No push, PR, merge or deployment was performed.
PostgreSQL live migration/RLS and concurrent approval acceptance, plus an
unmocked authenticated browser workflow, remain future release verification;
SQLite and SQL-contract tests do not claim those checks passed.
