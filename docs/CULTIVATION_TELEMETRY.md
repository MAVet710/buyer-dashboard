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
- `GET /rooms/{room_id}`: latest evidence per metric/source/device, 24-hour valid
  reading count/min/max/average/total, targets, and environmental exceptions.
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

The selected-room read uses four queries regardless of sensor count, SQL aggregates,
and a maximum of 200 latest sensor streams with an explicit truncation flag.
It hydrates no history bodies and makes no external provider calls. Exceptions are
computed at read time, including when ingestion stops; no background scheduler is
needed. Exceptions appear in Cultivation. Facility-wide Home inbox integration,
device registration/retirement, history exports, CSV UI, and vendor adapters are
follow-ups, not claimed integrations. A retired stream remains visible as stale
until a future explicit retirement workflow exists.

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

Local validation: 33 focused telemetry tests, 25 broader cultivation/regulatory/
migration tests, all 109 frontend tests, frontend lint, and production frontend
build passed. Python emitted existing test-client deprecation warnings. Vite
required execution outside the Windows filesystem sandbox to resolve parent
directories; no security settings or hosting configuration were changed.
