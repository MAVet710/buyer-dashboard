# Host-local cultivation maintenance integration contract

Status: CODE_READY candidate; primary owns integration and PC/public release acceptance.
No startup hook, launcher edit, scheduled task, service, package installation, new
central migration, receiver, or grant mechanism is installed by this change.

## Explicit integration

The preferred host API is now
`start_host_maintenance(engine, config_path=None)` in
`backend.app.services.cultivation_maintenance_runtime`. An explicit path wins;
otherwise it reads only `CULTIVATION_MAINTENANCE_CONFIG`. An absent/empty setting
returns `None` without database or filesystem IO and without creating a thread.
This is a trusted launcher/lifespan API, never a browser/request parameter.

One-time host installation must provision a protected local JSON file and bind
the exact organization, facility and canonical edge database. Example (synthetic
IDs and paths; installer must replace them once):

```json
{
  "enabled": true,
  "organization_id": "approved-host-organization",
  "facility_id": "approved-host-facility",
  "database_path": "C:\\DoobieLogicData\\cultivation\\edge.sqlite",
  "dynamic_connections": true,
  "archive_directory": null,
  "retention_days": null,
  "interval_seconds": 30,
  "edge_options": {}
}
```

`archive_directory` and `retention_days` are optional and default to `None`.
Omission never enables retention. Only explicit approved positive days enable it.
Static selection instead uses `"dynamic_connections": false` (or omits that key)
and `"connection_ids": ["approved-connection-id"]`. Dynamic selection cannot
be combined with a nonempty static list. The only disabled-file form is
`{"enabled": false}`.

The file contract is closed: unknown/duplicate keys, wrong types, malformed JSON,
files over 64KiB, relative/UNC/device/alternate-stream/traversal paths, symlinks,
reparse points and multiply linked files are rejected. It reads one regular file,
checks opened file identity, and does not expand variables or read included files.
No credentials belong in this file. Host ACL protection is mandatory: these checks
are not a substitute for preventing hostile concurrent directory replacement.
All configuration failures expose only `invalid_host_config`.

```python
from backend.app.services.cultivation_maintenance_runtime import (
    start_host_maintenance, stop_maintenance, maintenance_status,
)

runtime = start_host_maintenance(engine)  # before uvicorn.run, even with lifespan off
try:
    run_existing_server()  # existing trusted launcher owns this call
finally:
    stopped = stop_maintenance(timeout=5)
    # Primary must handle False as still stopping, before disposing the engine.
```

For an enabled FastAPI lifespan, call the same start helper before `yield` and
the stop helper in `finally`. Do not install both lifecycle owners. This change
does not edit either launcher or lifespan. Repeated starts with the same engine
object and parsed configuration reuse the live handle; mismatched starts fail.
Configuration is immutable until shutdown/restart. A timed-out stop keeps the
singleton reserved, including against a replacement using a changed config.
Unexpected daemon exceptions terminate with sanitized `failed` status.

`maintenance_status()` or `runtime.snapshot()` returns only state, fixed error
code and available counters (`examined`, `resolved`, `rebuilt`, `acknowledged`,
`purged`, `connections`, `excess`, `retry_after_seconds`). It omits IDs, paths,
timestamps, SQL, exceptions and secrets. This change adds no HTTP endpoint.

## Dynamic scheduling within the explicit host binding

Dynamic mode performs one scoped central SELECT per eligible tick, with grant
EXISTS predicates and LIMIT 101. PostgreSQL timeout SETs / SQLite busy-timeout
PRAGMA are separate setup statements, not per-row queries. Discovery includes
configured file connections and configured JSON push connections having a current
grant and active matching service account permitting `cultivation:ingest`, only
in the explicit active organization/facility with cultivation enabled. It never
selects token hashes. The existing `_resolver` still revalidates current admission
and materializes context for exactly one scheduled connection each tick.

At 101 returned rows, no connection work is attempted: `connection_capacity`,
`excess: 1` (a lower-bound overflow indicator) and 300-second backoff report the
need for explicit host capacity management. It never silently maintains only the
first 100. Discovery failure retains the last successful known connection set
for counts but does not resolve using cached permissions. Evidence is untouched.
Backoff is exponential to 300 seconds; successful discovery replaces that set.
Empty discovery idles. Revocation/inactive scope removes eligibility without
deleting evidence. Per-connection maintenance failure retains existing backoff.

A new saved UI connection (and UI-issued grant for push) is discovered on the next
eligible cycle without another host-file edit; bounded round-robin work can take
further ticks to reach it. The host installer remains required once. Dynamic mode
is not authorization for another facility or arbitrary developer PC. No new raw
receiver, central ledger, per-packet write, provider call or migration is added.
Malformed service-account JSON is excluded by SQLite discovery; PostgreSQL JSONB
cast failure fails the entire discovery closed with sanitized backoff. PostgreSQL
execution still requires primary's isolated acceptance gate.

## Existing direct controller API

`modules.cultivation.local_maintenance.MaintenanceController(engine, config)`
provides `tick(stop_event=None)` and `run(stop_event)`. The runtime helper is
`backend.app.services.cultivation_maintenance_runtime.start_maintenance(engine, config)`;
`stop_maintenance(timeout=5)` requests shutdown. Imports perform no maintenance.
The default `MaintenanceConfig()` is disabled: no central query, file, or thread.

Primary must supply the existing SQLAlchemy engine and a frozen host configuration:

```python
from modules.cultivation.local_maintenance import MaintenanceConfig
from backend.app.services.cultivation_maintenance_runtime import start_maintenance, stop_maintenance

config = MaintenanceConfig(
    enabled=True,
    organization_id=host_organization_id,
    facility_id=host_facility_id,
    connection_ids=(explicit_host_approved_connection_id,),
    database_path=canonical_absolute_edge_path,
    interval_seconds=30,
    archive_directory=None,
    retention_days=None,
    edge_options=(),  # Supply exact canonical receiver/collector quota settings if customized.
)
runtime = start_maintenance(engine, config)
# On shutdown: check the boolean result; False means stopping is still in progress.
stopped = stop_maintenance(timeout=5)
```

These values must come from protected server/launcher configuration, never a
request, browser, machine sender, tenant enumeration, or human impersonation.
For the direct/static API the tuple allowlist is fixed for a running instance,
limited to 100 connections, and required for both file and push modes. Dynamic
mode follows the explicit host binding described above. Enable only an explicitly approved own
DEV/QA connection during release acceptance. The raw database is the SAME canonical
EdgeStore used by that facility's collector/receiver. Provision its parent and any
archive directory locally with protected ACLs. No directory discovery or creation
of a raw store elsewhere, remote raw transfer, or subscription is involved.

Production currently runs uvicorn with lifespan off. Primary must explicitly call
the start/stop helpers from the versioned launcher, OR integrate into the existing
lifespan and enable that lifecycle without unrelated behavior changes. Merely
importing the module or adding a lifespan function that never runs is insufficient.
Use one configured process on the facility host; the singleton is per process,
not a cross-process leadership or new worker system. Concurrent external collectors
remain governed by EdgeStore SQLite transactions and their own existing locks.

The runtime returns the same handle for repeated identical starts and refuses a
different configuration while its daemon thread is alive. Its stop wait is at most
five seconds and interrupts the idle/backoff wait immediately. Stop checks occur
between central resolution and local opening, between rollups, and before archive
and retention. An in-flight canonical operation finishes or rolls back. A `False`
stop result must not be reported as stopped or used to launch a replacement thread.
The engine MUST have bounded pool checkout, connection establishment and driver/socket
timeouts supplied by primary; this module cannot impose a socket deadline on an
already supplied engine. PostgreSQL statements have a five-second timeout and
three-second lock timeout; SQLite busy timeout is at most five seconds. A sequence
of in-flight queries, disk IO or archive fsync can outlast a join timeout. A stuck OS
or disk has no hard completion guarantee. Verify actual shutdown in the launcher.

## Admission and bounded work

Every tick selects one allowlisted connection round-robin and freshly validates
active organization, active matching facility with cultivation capability, and a
configured, unrevoked connection. Push additionally needs at least one unrevoked,
unexpired grant with a scoped active service account explicitly permitting
`cultivation:ingest`; no client token is needed or read. Missing, malformed,
over-capacity (>200 live grants), expired, revoked or wildcard-only authorization
stops maintenance. File mode is authorized only by the explicit host allowlist plus
current scope validation. There is no synthetic AppUser/admin, positive auth cache,
central write, Work creation, equipment operation, or provider mutation.

The exact existing `context_resolution.build_resolver` performs eight bounded set
queries and materializes historical mappings before any local SQLite transaction.
Central outage leaves offline acquired rows pending. Once backoff expires and
central context returns, the next tick automatically retries. Authorization is an
admission snapshot: a bounded tick authorized before revocation may finish; later
ticks stop. Central and local transactions are not an atomic distributed transaction.

Each tick retries at most `min(100, max_batch, max_query_rows)` pending records using
EdgeStore's persisted composite cursor, then attempts at most two separate one-hour
rollups. One cursor visits oldest dirty buckets and another discovers observed time
windows chronologically, including boundary halos. Both wrap and persist in the
small `local_cultivation_maintenance` table in the SAME SQLite database. A derived
`local_cultivation_dirty` index supports dirty-bucket seeks. Evidence discovery uses
indexed `observed` seeks with LIMIT 1, skips dense hours, and loads no raw payload.
It may revisit unchanged hours on a new pass; it never loads or groups all raw history.
Supported maintenance bucket size is 3600 seconds, with max gap at most 3600 seconds.
All other canonical query/stream/batch/row/byte/disk bounds remain in force.

Cursors advance before a bucket attempt so an oversized or purged dirty bucket
cannot permanently starve new history. A crash can defer that attempt until the
next wrap; it cannot lose the raw row or acknowledge the bucket. Both selected
buckets are attempted even when the first exceeds rollup capacity. Each rollup is
the canonical atomic calculation: no truncated/partial aggregate is published.
Oldest-first traversal is fair over successive passes, not a backlog SLA.

Only after successful revalidation and bounded rollup work may optional local
`archive_aggregates` run (at most two revisions, within existing byte/batch bounds).
It uses existing verified immutable archive and exact revision acknowledgement.
Only an explicit positive `retention_days` enables existing protected retention
(at most 100 examined rows). Default `None` never purges. Retention uses both receipt
and observation cutoff and preserves dirty, unacknowledged, pending, quarantined,
disputed and unknown-gap evidence exactly as EdgeStore requires. Tombstones and
original finalized input files are not deleted. Archive does not imply raw purge.

Capacity/locking failures enter bounded runtime backoff (30-second minimum interval,
exponential to 300 seconds), leave evidence intact and do not acknowledge failed
work. Runtime backoff resets on restart; SQLite pending/retention/bucket cursors
survive. Quotas can prevent progress and require explicit host capacity management;
this is not an indefinite-storage guarantee. No automatic quota increase or cleanup.

## Status and acceptance

`tick()` and `controller.status` contain only fixed state/error codes, local counters
and timestamps: examined/resolved/rebuilt/acknowledged/purged, attempted/completed
times and retry delay. `completed` means that bounded iteration completed; it does
not mean backlog empty, sensor healthy, equipment live, or release verified. Exceptions
never expose their strings, SQL, credentials, raw readings or paths. Partially
completed work can remain committed; a later failure reports stopped/backoff, not
false success. This module installs no status endpoint or frontend component.

Tests use the trusted Python, APP_ENV=test, DATABASE_URL=sqlite://,
COMAN_DATABASE_URL=sqlite://, AI_ALLOW_CLOUD_FALLBACK=false, `--noconftest`, and isolated
temporary SQLite. Positive paths use actual foundation fixtures, FileCollector,
historical resolver, EdgeStore and archive. Cases cover offline/recovery, replay,
scope/capability/revocation failure before writes, live grant expiry and revocation,
fixed query count/100-row retry bound, old/new bucket and connection fairness,
unacknowledged/unknown/disputed retention protection, full/locked store, atomic
rollup-limit refusal, subprocess cursor reopen, and disabled/singleton runtime.

Prior controller validation on September 26, 2026: **148 passed** in 13.27 seconds
(32 new maintenance cases plus ingress, edge-store and aggregate-archive suites).
Two pre-existing Starlette/httpx/anyio deprecation warnings; no package changes.
Command arguments: `-I -B -m pytest --noconftest -p no:cacheprovider
tests/test_cultivation_local_maintenance.py tests/test_cultivation_ingress.py
tests/test_cultivation_edge_store.py tests/test_cultivation_aggregate_archive.py
--basetemp=.tmp/local-maintenance-c -q`. Only isolated local SQLite was used.

Host-bootstrap validation on September 26, 2026: **185 passed** in 16.90 seconds,
including **37 new runtime cases** and all 148 existing cases above. The same two
dependency deprecation warnings remain. Trusted Python was invoked with `-I -B`,
`APP_ENV=test`, `DATABASE_URL=sqlite://`, `COMAN_DATABASE_URL=sqlite://`,
`AI_ALLOW_CLOUD_FALLBACK=false`, `--noconftest -p no:cacheprovider`; test selection
adds `tests/test_cultivation_maintenance_runtime.py` to the four suites above.
Temporary databases were confined to the authorized evidence directory's `rt3`
subdirectory; sanitized command output is `rt3.log` in that evidence directory.
No long soak, PostgreSQL connection, production access or deployment was performed.

Remaining primary gates: integrate explicit startup/shutdown; confirm matching
canonical paths and quotas, host binding/allowlist, protected directories and engine
timeouts; run final-candidate regression gates; then perform authorized PC deployment,
exact release-identity verification and affected authenticated public acceptance.
No production or public-workflow verification has been performed here.
