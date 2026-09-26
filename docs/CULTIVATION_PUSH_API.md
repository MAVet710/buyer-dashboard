# Cultivation normalized push API (schema 1)

Implementation contract for frontend and local edge integration. This is a
DoobieLogic normalized JSON transport, not native Growlink support or a release claim.

## Human provisioning

Existing prefix: `/api/v1/cultivation-intelligence` and existing human JWT/scope.
Create connections with `{provider:"json",label,mode:"push"}`; file mode remains
the default. Optional `expected_interval_seconds` and `stale_after_seconds` are
positive integers up to 2678400, or null; neither has an agronomic default.

* `GET /connections/{id}/ingress-grants`: `{grants:[{id,connection_id,service_account_id,label,version,created_at,expires_at,revoked_at,status}],truncated}`. No token/hash.
* `POST /connections/{id}/ingress-grants`: `{version:<connection version>,label:<1..120 chars>,expires_at:<future timezone-aware ISO timestamp>}`. Returns `{grant:<same public grant>,connection_version,token}`. Token is returned only by explicit creation. Creation requires current admin/dev plus effective cultivation manage-connections permission and a canonical active AppUser. Each creation generates a new service account/token; overlap allows rotation.
* `POST /connections/{id}/ingress-grants/{grant_id}/revoke`: `{version:<grant version>}`. Returns public grant. Requires the same permission; stale version is 409. Revocation preserves the grant and audit evidence.

## Machine intake

`POST /api/v1/external/v1/cultivation-telemetry/{connection_id}/batches`

Bearer `dla_...` service-account token; explicit `cultivation:ingest` scope (`*`
alone fails). Account, grant, organization, facility and connection must agree.
No human session fallback. Send only `Content-Type: application/json`, without
content encoding. Optional facility/org scope headers must match the binding.

```json
{"schema_version":1,"batch_id":"batch-001","readings":[{"event_id":"sample-001","source_device_id":"sensor-1","source_channel":"temperature","source_metric":"temperature","value":24.5,"unit":"C","observed_at":"2026-09-26T12:00:00Z","quality":"valid"}]}
```

All illustrated reading fields are required except quality (defaults to valid).
Identities are 1..120 ASCII letters/digits/`_.:@-`; batch_id is the same (max 120).
Only these fields are accepted. Measurement value is a scalar, not an object or
array. Strings are bounded. Original timestamp/unit/value representations survive
ingestion. Bad measurement, timestamp or quality is persisted as quarantine;
missing/unsafe source identity or structural errors persist nothing.
1..min(500, configured EdgeStore.max_batch) readings; 1 MiB streamed byte limit,
including chunked requests. No snapshots, scope, received_at, URLs or metadata.

200 response: `{schema_version:1,batch_id,committed:true,accepted,duplicates,conflicts,quarantined,pending,items:[{identity,status,reason}]}`.
Status is ready/pending/quarantined/disputed/duplicate. Identity is an opaque hash;
no raw values or token. Acknowledgement follows the same-host EdgeStore commit.
It does not promise cloud publication, valid measurement or current connectivity.
Retries after lost acknowledgement retain identical observation IDs and payloads,
including through rotation and batch splitting. Changed content is disputed.

Errors have fixed safe detail strings: 400 malformed JSON; 401 missing/invalid
token; 403 forbidden binding; 413 bytes/count overflow; 415 media/encoding;
422 invalid structure; 429 bounded rate/concurrency (Retry-After); 503 unavailable
auth database, context capacity or local storage. No validation input echo.

No positive auth cache and no central SQL writes on POST (including last_used_at).
Before parsing or filesystem access, current authorization must pass. Admission
rechecks authorization under the existing facility lock before snapshot resolution
and local commit. Revocation prevents later admissions; a bounded admission already
authorized before revocation may finish. PostgreSQL reads and local SQLite commit
are not an atomic distributed transaction. No SQLite transaction spans provider IO.

## Edge worker integration seam

Existing `EdgeStore.ingest(scope, readings, resolved=...)` remains authoritative.
Push tracking extension: `ingest(..., transport={"batch_id":<stable id>,
"grant_id":<authorized grant id>})` records the durable receipt in the SAME
transaction. `transport_status(scope)` returns last_committed_at, last_batch_id
and bounded cumulative disposition counters. See CULTIVATION_PUSH_EDGE_API.md.
Gateway health aliases these to edge.last_push_received_at / last_push_batch_id.
The extension is mandatory in this release: machine intake never falls back to a commit without atomic transport tracking.
Existing last_received_at, last_valid_observed_at, counts and limits retain their
meanings. Health reports grant state, transport, observation freshness, backlog
and capacity separately. Connection observation freshness never establishes room
or channel coverage. Missing push receipt remains awaiting; imports are not receiving.

Health also returns `ingress:{grant_state,grants_truncated,transport_state,
last_push_received_at,last_push_batch_id}` and `freshness.observation_status`.
Grant states include active, expired, revoked, disabled, unprovisioned, unknown.
Transport is disabled/file, revoked/connection, awaiting/no push, received/no
configured stale threshold, receiving/recent push, stale, or unknown. These are
independent: an expired grant can still have a historical durable receipt.
`edge.oldest_pending_at` and `edge.capacity` pass through the edge read model.
Neither a fresh receipt nor the newest valid connection reading clears another
channel's unknown/stale coverage.

Admission limits are per backend process: four concurrent requests, 60 admitted
batches per connection scope per 60 seconds, up to 1024 retained rate windows.
Body receipt times out after 15 seconds; PostgreSQL final-admission locks time out
after 3 seconds and each query after 5 seconds. Exhaustion never acknowledges.
SQLite authorization uses an explicit read transaction; PostgreSQL uses the
existing facility lock and then the service-account lock. Human grant writers use
the same facility-first ordering. All eight snapshot queries remain set based.
