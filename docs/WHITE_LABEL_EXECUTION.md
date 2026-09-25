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

Apply migration `0080_white_label_execution` before enabling the new application
code. It adds one planning table, foreign keys, a unique execution link, scope
index and browser-role restrictions. It changes no existing business rows and
refuses a downgrade that would discard saved plans. Deployment and PostgreSQL
acceptance are reserved for the coordinating release worker; this implementation
worker is explicitly limited to a local commit.

Validation: 52 focused and related backend tests passed (White Label execution,
repack calculations, Package Studio, inventory commitments, physical production
start, Run 360 QA/mutation previews, and migration contracts/capacity). Frontend
lint, build and all 110 unit tests passed. Two mocked-API Chromium acceptance
tests passed at desktop 1440px and mobile 390px, covering save, unsaved-change
approval blocking, durable reload and execution handoff. PostgreSQL migration,
concurrent approval and authenticated production acceptance remain release gates.
