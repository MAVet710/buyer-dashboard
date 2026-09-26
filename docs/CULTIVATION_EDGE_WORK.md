# Reviewed historical edge deviations and canonical Work

Status: implementation handoff; primary owns integration and release.

Mount `backend.app.routers.cultivation_edge_work.router` with the existing
`/api/v1` prefix. No startup worker, migration, task-link table or automatic Work
creation is added. The service uses the existing host-configured
`CULTIVATION_EDGE_PATH` and gateway limit configuration.

## HTTP contract

`GET /api/v1/cultivation-intelligence/rooms/{room_id}/deviations?start=<UTC>&end=<UTC>`
returns `{items, window:{start,end}, truncated}`. Every item contains
`exception_id, metric, unit, connection_id, sensor_id, cycle_id, recipe_revision,
direction, started_at, ended_at, duration_seconds, threshold_seconds,
work_item_id, return_route`.

`POST /api/v1/cultivation-intelligence/rooms/{room_id}/deviations/{exception_id}/work`
accepts only `{start,end}` and returns `{work_item_id, existing, return_route}`.
Both inputs reject extra fields, naive/non-UTC timestamps, reversed windows,
unaligned bucket boundaries and windows beyond the gateway's configured limits.
404 means the room is outside active scope or absent; 403 means authorization
failed; 409 requires refreshing evidence; 422 means invalid input.

The exact route is `/cultivation?room=<room>&edge_exception=<id>&start=<UTC>&end=<UTC>`.
Values are percent-encoded; UTC timestamps are normalized with `+00:00`.
The frontend owner must explicitly offer review/create, refresh on 409, use the
returned canonical Work ID and restore the room, historical window and selected
exception from this route. Do not treat the latest/current reading as a
duration-qualified deviation, automatically create Work, or claim that the
return-route focus UI is delivered by this router.

## Evidence and consistency

Only bounded, persisted rollups are read. The bridge never calculates from raw
samples or accepts browser evidence, targets, values or mapping snapshots.
At most 200 streams and 200 exceptions are eligible. Dirty/truncated queries
return no eligible items; dirty detection conservatively covers the facility's
selected window. Missing rollups, approved recipe context, positive duration
policy, targets or continuous attribution cannot qualify an interval.
Partial windows may contain a provably covered historical deviation; gaps
cannot be stitched across to satisfy a duration threshold.

Scoped central context is fetched in fixed batched queries. Approved historical
recipe, stage, cycle, mapping, source, sensor, target and unit must agree with
the persisted snapshot. Each exception hashes that full scoped context,
same-direction interval and its contributing bucket revisions. A changed
revision requires fresh review even if the resulting duration is unchanged.
Historical windows remain actionable while their persisted evidence is clean
and still proves the exact selection. Relevant bucket revisions make unchanged
interval identities independent of a wider selected window.

The bridge reads EdgeStore's existing `buckets` metadata through its local
SQLite connection for dirty flags and revisions. This private schema adapter
is an integration seam: preserve or replace it with an equivalent bounded
public metadata API if EdgeStore changes. Summary revisions are checked before
and after reading, then again immediately before canonical creation/reuse.

Local evidence and the central database do **not** share a transaction. Work
retains immutable `evidence_as_of`, revision fingerprint, contributing bucket
revisions and approved snapshot; `local_cloud_atomic` is explicitly false.
A collector can change evidence after the last check. The stored evidence is
an as-of decision record, not a promise that local acquisition was locked.
Evidence JSON is limited to 16,000 UTF-8 bytes.

## Authorization and canonical writes

Room and facility scope are checked before local filesystem access. POST uses
`IntelligenceService.authorize(write=True, session=...)`, including cultivation
capability, write role, cultivation permission, active actor, SQLite
`BEGIN IMMEDIATE` and PostgreSQL facility lock. It additionally checks
`work.create` before either creation or reuse, then locks the canonical room.

GET performs one bounded batched canonical Work lookup. POST serializes the
lookup and creation on the central facility/room lock. All statuses, including
completed Work, reuse the existing ID for that exception. There is no telemetry
task-link table. `WorkService.create` receives the same session as the cultivation
audit; failure of either central audit rolls back Work and both audits together.
No inventory, external traceability, equipment or notification mutation occurs.

## Verification scope

`tests/test_cultivation_edge_work.py` uses real file-backed SQLite EdgeStore and
central SQLite, historical approved recipe/mapping/cycle fixtures, real resolver,
HTTP boundary and WorkService. It covers scope, roles, capability, permissions,
unknown IDs, completed reuse, concurrent clicks, duration/gaps, missing context,
dirty and rebuilt evidence, strict windows, route round trip, read-only summary,
bounded batched lookup and central rollback on audit failure.

Primary retains router mounting, frontend historical-focus acceptance,
PostgreSQL release gates and all PC/public deployment verification.

Verified September 26, 2026 with the assigned trusted Python and explicit test
SQLite/cloud-fallback-disabled environment:

- `pytest tests/test_cultivation_edge_work.py tests/test_doobie_work.py tests/test_cultivation_telemetry.py -k work -q`: 71 passed, 65 deselected.
- Final bridge rerun after batching revision fingerprint work: 26 passed.
- An earlier broader telemetry run had 135 passes and one unrelated failure:
  `test_final_migration_chain_is_single_0086_head` expects 0086 while the receiver
  worker's reserved migration advances head to 0087. That unowned assertion is
  left for primary integration.

Temporary databases stayed in owner-specific `work-bridge-*` directories under
the assigned release-evidence root. No PostgreSQL/live database, provider,
browser, commit, deployment or production acceptance was performed.


## Primary integration validation

The response now includes effective `can_create_work`, requiring an active canonical user, cultivation writer eligibility, cultivation intelligence permission and Work creation permission. Listing does not acquire a write reservation. Deviation evidence is opened using the explicit read-only EdgeStore mode; missing or incompatible storage is unavailable, never initialized by this read. Legacy calculation buckets are withheld without altering any scope. Current POST authorization, exact evidence revision checks, canonical Work lifecycle and completed-item reuse remain enforced.

The actual React/FastAPI guided flow passed at 390px and 1280px after correcting overlapping mobile action links. It covers normalized file preview, persisted evidence, actual authenticated machine push, automatic room refresh, reviewed Work creation/reuse and exact return to the source exception. This is isolated local acceptance, not production delivery.
