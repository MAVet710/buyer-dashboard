# DoobieLogic Performance Contract

Last reviewed: 2026-09-02

DoobieLogic is an operator-facing system used repeatedly throughout a workday. Performance is part of usability and reliability, not a cosmetic enhancement.

The product rule is: **complex underneath, simple and fast on top.**

This contract applies to the React/FastAPI production application and to shared backend services used by compatibility surfaces.

## User-facing targets

These are engineering targets for normal authenticated operations on a healthy production deployment with realistic facility data. External provider calls and explicitly long-running work are handled separately below.

- A common workspace should present useful operational content in about **1–2 seconds**.
- A workspace taking more than **3 seconds** to become useful requires performance review before release.
- A normal deterministic action should usually acknowledge or complete in **under 1 second** when it does not depend on an external provider or heavy file processing.
- Opening a 360/detail view must not require loading unrelated facility-wide history first.
- Navigation must remain responsive while secondary detail is progressively loaded.

These targets are not permission to bypass validation, traceability verification, audit history, tenant isolation, or other safety controls.

## Read-model rules

1. **No per-row HTTP fan-out.** A screen that needs information for a list of records uses one bounded summary/read-model endpoint or a small fixed number of requests. It must not request one detail endpoint per row.
2. **No per-row SQL fan-out.** Balances, reservations, QA state, counts, costs, and other list-level facts are aggregated or batch-loaded. Avoid N+1 database patterns.
3. **Summary first, detail on demand.** List endpoints return only fields required to render/search the list. COAs, analyte results, genealogy, event history, generated barcodes/QRs, and other expensive detail load when the operator opens or selects the record.
4. **Bound large collections.** Use server-side filters, pagination, bounded windows, or purpose-built snapshots instead of returning unlimited facility history.
5. **Reuse canonical data.** Performance work must not create a second inventory, production, compliance, customer, or financial source of truth.
6. **Preserve tenant scope.** Every optimized query remains organization/facility/license scoped exactly like the authoritative workflow it accelerates.

## External systems and heavy work

- Normal workspace rendering must not silently depend on Metrc, BioTrack, AI providers, payment providers, or other external services unless the workspace is specifically a live-provider view.
- External reads should be explicit, cached where safe, bounded, and visibly identified.
- External writes continue to use preflight/confirmation/execution/readback/reconciliation contracts; latency is never a reason to weaken them.
- COA parsing, bulk imports, large report generation, reconciliation sweeps, and similar heavy jobs should be explicit and resumable or backgrounded when they cannot reliably meet interactive targets.
- Loading indicators may communicate real work, but must not be used to hide avoidable query or request fan-out.

## Frontend rules

- Route-level code splitting and React Query caching are retained.
- Query invalidation should target the changed domain/query when practical; avoid global refetch storms.
- Expensive components and provider checks load only when their view is opened or requested.
- Preserve the existing operator UI and workflow unless a UX change is separately approved. Performance refactors should normally be behavior-preserving.

## Backend rules

- Prefer set-based SQL, grouped aggregates, joins/subqueries, and bounded projections over repeated repository calls inside loops.
- A list/read-model service may aggregate canonical tables but may not mutate them.
- Do not increase database pool size, Cloud Run resources, or instance count as the first response to application-level N+1 behavior. Fix unnecessary work first, then scale infrastructure from measured demand.
- Add or change indexes only from demonstrated query needs; do not duplicate indexes already provided by constraints or model definitions.

## Observability

FastAPI responses expose request timing through `Server-Timing` and `X-Response-Time-Ms`. API requests at or above 1000 ms are logged as slow-request warnings so production traces can identify hot endpoints.

Performance investigations should record, where practical:

- endpoint duration
- request count needed to render the workspace
- SQL query count or dominant queries
- payload size
- records scanned/returned
- browser render/interaction delay
- whether an external provider is on the critical path

## Release expectations

Performance regressions are release regressions. New or materially changed operator workspaces should have regression coverage that prevents known N+1/fan-out patterns from returning.

At realistic data volume, acceptance should verify that:

- common list and planning surfaces remain bounded as record counts grow
- detail hydration does not block the initial list
- normal navigation does not trigger unnecessary external-provider calls
- existing UI, permissions, workflow safety, and source-of-truth behavior remain intact

If a workflow cannot meet this contract because the work is intrinsically long-running, document that exception and make progress/status/retry/resume behavior explicit rather than treating the delay as normal navigation latency.
