# Cultivation environmental telemetry

This foundation records environmental evidence against canonical cultivation rooms.
It is decision support only: no equipment, irrigation, inventory, or Metrc mutations
are performed. TrolMaster, Growlink and Argus adapters are not implemented.

## API contract

All paths below are relative to `/api/v1/inventory/production/plants/telemetry`.
Existing authenticated organization/facility context and cultivation capability
checks apply. Writes use the existing cultivation write roles. A room must belong
to both the active organization and facility. Browser Supabase table access is revoked.

- `POST /rooms/{room_id}/observations`: `{ "observations": [...] }`, 1 to 500 rows,
  committed atomically with one canonical audit event for newly inserted evidence.
- `GET /rooms/{room_id}`: latest evidence per metric/source/device, typed 24-hour
  valid-reading summaries, targets, and environmental exceptions.
- `POST /rooms/{room_id}/target`: metric, optional minimum/maximum in canonical
  units, and `stale_minutes` (1 to 10080). Changes are audited.

Example observation:

```json
{
  "source": "manual",
  "event_id": "stable-upstream-event-identifier",
  "device_id": "optional-probe-identifier",
  "metric": "temperature",
  "value": 77,
  "unit": "F",
  "quality": "valid",
  "observed_at": "2026-09-25T12:00:00-04:00"
}
```

Supported canonical metrics/units are `temperature`/`C`, `relative_humidity`/`%`,
`vpd`/`kPa`, `co2`/`ppm`, `substrate_ec`/`mS/cm`, `substrate_vwc`/`%`,
`irrigation_volume`/`L`, and `irrigation_event`/`count`. Explicit conversions accept
`F`, `uS/cm`, and `mL` for their respective metrics. VWC means volumetric water
content; arbitrary uncalibrated moisture scales cannot be imported as percentages.
Irrigation volume is the volume of a discrete event, not a cumulative meter value.
An irrigation event records exactly one occurrence. Shared event IDs may identify
different metrics from the same event. Use stable source and device identifiers.

Quality is `valid`, `suspect`, or `invalid`. All values must be finite and within
the transport bound of +/- 1e12 before conversion. Percentages must be 0 to 100;
non-temperature values are nonnegative. Timestamps require timezone offsets and
cannot be in the future. Invalid-quality numeric evidence is retained but excluded
from trend aggregates. Missing/non-numeric readings should not be fabricated as zero.

The unique identity is organization/facility/room/source/event_id/metric/device_id.
Exact normalized retries return duplicate counts. Reusing an identity with different
evidence returns HTTP 409 and rolls back the whole batch. Adapters must preserve IDs
on retries, including retries after timeouts. Observations are append-only through
the API; corrections require a new event identity. Manual entry is available in the
Cultivation room environment panel. CSV upload is deferred; a future importer should
map rows into this same validated batch contract, not write directly to tables.

## Read model and boundaries

Each sensor stream is evaluated independently, so a fresh probe cannot conceal
another probe's stale state. Continuous measurements default to stale after 60
minutes; irrigation events/volumes have no default stale expectation. Configuring
a metric target marks it as expected, generates missing exceptions when absent,
and sets its stale window. Unconfigured missing metrics are displayed without
generating an exception. No agronomic ranges are assumed. Stale and out-of-range
states can coexist. Suspect/invalid readings are flagged and cannot appear healthy.
Quality takes precedence over range evaluation: invalid/suspect evidence never gains
an out-of-range or current classification from target bounds; stale remains an
independent state. Range bounds apply to individual observations, including discrete
irrigation volumes, not the rolling total. Bounds are inclusive; stale begins strictly
after the configured window.

The 24-hour window is `(as_of - 24h, as_of]`. Continuous trends have
`kind: continuous` with count/min/max/average. Irrigation trends have
`kind: event_count` or `volume_total` with count/total only. Volume totals are liters
from valid discrete volume observations; event totals count valid event observations.
They are per source/device, not a sum across potentially overlapping sensors.
Invalid/suspect observations are excluded. No valid evidence yields a null trend,
not a fabricated zero. Unconfigured irrigation's `current` state means recorded,
not proof of freshness or ongoing delivery; the UI labels it "Recorded".

The selected-room read uses four queries regardless of sensor count, SQL aggregates,
and a maximum of 200 latest sensor streams with an explicit truncation flag.
It hydrates no history bodies and makes no external provider calls. Exceptions are
computed at read time, including when ingestion stops; no background scheduler is
needed. Exceptions appear in Cultivation. Facility-wide Home inbox integration,
device registration/retirement, history exports, CSV UI, and vendor adapters are
follow-ups, not claimed integrations. A retired stream remains visible as stale
until a future explicit retirement workflow exists.

## Final-rebase integration contract

This old-base branch contains only wholesale permissions in
`backend/app/permissions.py`; it does not contain the generalized cultivation or
Doobie Work contracts. Do not graft wholesale permissions onto cultivation.
`backend/app/routers/cultivation_telemetry.py::authorize_telemetry` is the single
authorization hook for both observation and target writes. On final rebase, add the
generalized cultivation write permission there using the actual rebased registry
key and `require_permission`, keeping both `require_write` and cultivation capability
checks. No optional import, unknown-key fallback, or allow-on-error is acceptable.
Add facility-scoped deny/allow override tests for both routes; explicit allow must
not bypass the cultivation role/capability gates. Align the UI's entry affordance
with effective permissions; server enforcement remains authoritative.

Exceptions carry `exception_id = cultivation-telemetry:v1:<sha256>`. The hash covers
an unambiguous JSON array of organization, facility, room, metric, source, device,
sorted states, normalized UTC observation timestamp and upstream event ID. Poll time,
database-generated IDs and receipt order are excluded. Equal-time observations use
event ID descending as a deterministic tie-break. A missing configured metric has
null observation/event identity and remains stable between polls. A new observation
or state changes identity. Repeated missing episodes without new evidence reuse the
same identity deliberately; Work reopening should be an explicit operator action.

`TelemetryService.prepare_work_item(org, facility, room, exception_id, actor=...)`
is the non-mutating service seam. It re-derives the bounded room snapshot, resolves
only a current visible exception, rejects obsolete/cross-room selections, and returns
tenant scope, origin type/ID, room, actor, title and server-derived evidence/as-of.
It is not a public mutation endpoint and does not authorize or persist Work itself.
No task table, derived alert ledger, automatic ingest trigger, or inactive UI button
has been introduced.

After Doobie Work is present, wire an explicit "Create Work item" action on a selected
exception to a POST with only its exception ID and permitted Work operator inputs:

1. Derive tenant/facility/actor from authenticated context. Apply
   `authorize_telemetry(..., write=True)` plus the canonical Work create permission.
2. Call `prepare_work_item`; return 409 and require refresh if the exception changed
   or is not among the visible 200 streams. Never trust client evidence or tenant IDs.
3. Pass the returned origin/evidence into the existing canonical Work creation
   service. Atomically deduplicate `(organization, facility, origin_type, origin_id)`
   using Work's supported source-link/idempotency contract, including concurrent
   clicks and retries. Return the existing linked Work item for repeated requests.
   Keep the evidence snapshot and shared correlation ID in canonical Work/audit;
   preserve normal assignment/status/permission rules. Do not add a parallel table.
4. Add authenticated API/UI tests for explicit creation, double-click/concurrent
   retry deduplication, cross-tenant denial, stale selection, permission overrides,
   and proof that ingest/polling never creates Work. No action controls equipment.

The coordinator must reconcile/renumber `0080` only after Logistics/`0084` is ready,
then run migration-chain and PostgreSQL runtime/browser-role ACL acceptance. This
hardening intentionally leaves migration identity and DDL unchanged.

## Migration and validation

`0080_cultivation_telemetry` follows `0079_security_observation`. It adds two tables
and a composite room uniqueness constraint used by scoped foreign keys. It does not
rewrite operational records. PostgreSQL RLS is enabled and browser/public grants
revoked. The existing server runtime receives SELECT/INSERT for observations and
SELECT/INSERT/UPDATE for targets. It cannot update/delete observations via these
grants. Downgrade refuses to discard any observations or target configuration.

Focused tests cover API roles/capability, cross-scope reads and writes, foreign keys,
idempotency/conflicts, atomic audit rollback, units, stale/range boundaries, missing
and invalid evidence, constant query count, and migration preservation. Frontend
render tests exercise the evidence table. Isolated PostgreSQL migration/concurrency
acceptance and authenticated browser acceptance remain integration release gates.
This implementation task explicitly excludes deployment.

Hardening validation: 104 focused telemetry/cultivation/migration tests (64 telemetry,
40 broader checks) and all 110 frontend tests pass, as do frontend lint and production
build. Two isolated mobile-width Chromium tests pass for operator/viewer controls
and irrigation totals; these use mocked authenticated API responses, not production
credentials or public acceptance. Run with Vite on loopback port 4175 and
`npx playwright test e2e/cultivation-telemetry.spec.ts`. The PostgreSQL ACL
test captures generated migration statements; it is not a live PostgreSQL role test.
Python emits an existing test-client deprecation warning. Vite requires execution
outside the Windows filesystem sandbox to resolve parent directories. No security
settings or hosting configuration were changed. Release status is `CODE_READY` for
this local pre-rebase hardening; generalized permission and canonical Work integration,
final migration-chain acceptance, and PC/public acceptance remain final-release work.
