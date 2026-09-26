# Cultivation intelligence independent acceptance

Date: 2026-09-26. Status: **RELEASE_BLOCKED** pending disposable PostgreSQL execution and primary-owned release acceptance. The owned local acceptance suite passes.

Tested identity: **uncommitted working-tree candidate**, based on HEAD `24b615def545e6c7103e55e1d4f27d4a11b93e16`. The HEAD SHA alone does not identify the tested implementation: backend, edge and frontend implementation files were changing concurrently. Primary must rerun against the integrated committed candidate and record that exact SHA.

Only these owned outputs were added:

- `tests/test_cultivation_intelligence_end_to_end.py`
- `tests/test_cultivation_intelligence_postgres.py`
- This acceptance record.

No application, existing test, migration, frontend, workflow or production files were edited by this acceptance task. No commit, push, deployment, global package installation, Docker startup, production service call or external connector was used. Tests use in-process ASGI, temporary SQLite files and the existing read-only Python interpreter. They do not bind application ports or use a production database URL.

## Local acceptance method

The actual new FastAPI router calls the actual `TelemetryGatewayService` and `IntelligenceService`, the normalized file adapter, and an actual local `EdgeStore`. Central SQLite has foreign keys enabled. Fixtures use canonical `AppUser`, `Organization`, `Facility`, `CultivationRoom`, `CultivationPlant`, `CultivationHarvest` and harvest membership records. Only authenticated `RequestContext`, database and settings dependencies are substituted. Gateway, attribution, domain methods, adapters and rollups are not mocked.

HTTP approval and mapping revision behavior are tested directly. Separate historical fixtures persist an already approved recipe, room/stage/crop occupancy, membership and an effective device mapping before importing historical readings. This is necessary because the mapping API only accepts future revisions and Room360 reads completed hours. No clock or resolver is replaced, and no hand-built edge snapshot is supplied. The actual gateway derives snapshots from these database records.

Coverage includes:

- Draft recipe rejection, authenticated approval, immutable approval and stale version rejection.
- Canonical plant membership and exact canonical harvest linkage, with Cycle360 relationship readback.
- Wrong-tenant room/mapping/import/health rejection and readonly write/import/drain rejection.
- Explicit JSON preview with no central writes or local evidence, followed by explicit import and exact replay.
- Original `77 F` evidence retained locally and normalized to `25 C` by the real implementation.
- Registered device/channel resolution, approved historical stage/crop/room attribution, unknown device queued for mapping, and no attribution before a mapping's effective date.
- Actual drain and persisted rollup: 300 covered seconds, 3300 unknown seconds in the fixture hour, and 300 above-target seconds. Room360's 24-hour summary retains 86100 unknown seconds.
- Cycle360 returns actual cycle-filtered local rollup evidence through `edge_summary.rooms[].summary.streams`.
- Future mapping revision and replay preserve the original immutable snapshot and do not duplicate evidence.
- Missing evidence stays `UNKNOWN`; incomplete coverage stays `PARTIAL`.
- Growlink file activity remains `configured`, `live_supported: false`, with live contract `blocked`.
- Revoked connection rejects subsequent ingestion and preserves local evidence. Import digest binds to connection version.
- Central table counts and captured INSERT/UPDATE/DELETE statements verify gateway processing writes only audit records. No per-sample central observation writes, automatic Work, equipment, inventory, plant or traceability mutations are accepted.
- Direct legacy HTTP Fahrenheit regression verifies canonical and original units after FastAPI/Pydantic validation and replay, with exactly one central manual observation.

`accepted` counts ready observations; pending unmapped observations are reported separately as `queued_for_mapping`. The mixed historical fixture therefore expects one accepted observation and one pending observation, with two duplicates on replay.

## Integration findings

`test_cycle360_returns_attributed_rollup_evidence` requires actual attributed rollup evidence in `GET /api/v1/cultivation-intelligence/cycles/{cycle_id}`. An earlier run exposed absent telemetry evidence while import, attribution, rollup and Room360 passed. The backend changed during this task to return `edge_summary.rooms[].summary.streams`. The final test uses that exact observed shape and passes. No absent behavior was mocked or skipped.

The API document inspected during this task names Room360 `edge_summary` but omits Cycle360's new telemetry field. Primary should align the API document and frontend with the implemented response. The current mapping/sensor writers also advance the connection version. The test requires a stale import digest to fail with 409 after remapping, then obtains a new preview and proves that replay preserves the original snapshot.

Earlier in this concurrent run the gateway seam was still being written. It is now callable through the actual router. Those initial unavailable-seam observations are not the final blocker.

## Reproduce local tests

From the worktree, using only isolated normal-test settings:

```powershell
$env:APP_ENV = 'test'
$env:DATABASE_URL = 'sqlite:///:memory:'
$env:COMAN_DATABASE_URL = 'sqlite:///:memory:'
$env:AI_ALLOW_CLOUD_FALLBACK = 'false'
& 'C:\Users\ndasi\.codex\worktrees\ceec\repo-next-20260912-174618\.pilot-venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider tests/test_cultivation_intelligence_end_to_end.py tests/test_cultivation_intelligence_postgres.py --tb=short
```

Final local output:

```text
20 passed, 5 skipped, 2 warnings in 14.61s
```

This comprises 12 actual local HTTP/integration cases and eight PostgreSQL pre-SQL safety cases. All five PostgreSQL integration cases skipped because the explicit disposable PostgreSQL opt-in was absent. Third-party FastAPI/Starlette deprecation warnings are not acceptance failures. Cache provider is disabled to avoid unrelated cache writes.

## Disposable PostgreSQL gate

Actual PostgreSQL execution is **not performed locally**. Docker's stopped daemon is not started. Five integration cases are opt-in and skip locally; eight URL/opt-in safety cases run without SQL. PostgreSQL behavior is unverified until disposable CI executes the integration cases successfully.

Before `create_engine` or any SQL, the test validates both:

- `DOOBIELOGIC_PG_RELEASE_TEST=1`
- `DOOBIELOGIC_TEST_POSTGRES_URL` uses PostgreSQL, a literal loopback address or `localhost`, and database exactly `doobielogic_release_test`.

Missing/malformed URLs, non-loopback hosts, unexpected database names and all URL query overrides are rejected. Tests never fall back to `DATABASE_URL` or `COMAN_DATABASE_URL`. An enabled gate with unsafe/missing URL fails instead of skipping. All fixtures use UUIDs and an outer rollback transaction. Browser permission failures and downgrade attempts use nested rollback savepoints. No schema stamping or migration of the target database is performed by the tests.

The PostgreSQL cases check:

- Actual sole head `0086_cultivation_intelligence` descends from `0085_cultivation_telemetry`, and database `alembic_version` matches it.
- All 12 new tables have actual ORM columns, scope foreign keys and enabled RLS; important relationship FKs are composite and tenant scoped. New original-unit columns are nullable.
- Existing `anon` and `authenticated` roles cannot SELECT or INSERT any new table; the test checks SQLSTATE `42501`, not an incidental constraint failure.
- `doobielogic_render_runtime` is BYPASSRLS and non-superuser, has explicit SELECT/INSERT/UPDATE grants but no DELETE and no CREATE in public.
- Real runtime-role connection/device INSERT, SELECT and UPDATE succeed. Wrong-tenant device insertion fails with FK SQLSTATE `23503`. CREATE TABLE under the runtime role fails with permission SQLSTATE `42501`.
- An old-column-only manual observation insert succeeds with all four new columns NULL. Once original-unit evidence is populated, actual migration `downgrade()` refuses inside a rollback savepoint, preserving the evidence and migration version.

The existing `.github/workflows/pc-release-postgres.yml` already supplies disposable PostgreSQL 17 and migrates head. Primary must add role setup **before migration**, because 0086 only grants to roles that already exist. The following setup is for that fresh disposable CI database only, executed by its migration owner:

```sql
CREATE ROLE anon NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE authenticated NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE doobielogic_render_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM doobielogic_render_runtime;
GRANT USAGE ON SCHEMA public TO anon, authenticated, doobielogic_render_runtime;
```

Let the actual migrations grant table privileges. Do not use blanket table grants to make these checks pass. Do not apply this setup to hosted/global roles. This reproduces the documented BYPASSRLS runtime pattern in `docs/advisory/BACKEND_IMPLEMENTATION.md`, with FastAPI remaining the authorization boundary.

After the existing migrate/downgrade-empty/reupgrade steps, CI must explicitly run:

```text
python -m pytest -q tests/test_cultivation_intelligence_postgres.py --junitxml=artifacts/pc-postgres/cultivation-intelligence.xml
```

The current workflow does not select this new test file automatically. Primary owns adding its invocation and relevant trigger paths. This task does not modify CI or old migration 0085.

## Release interpretation

These are local integration and opt-in database gates, not production acceptance. Stubbed authenticated context exercises deterministic authorization and domain behavior but does not prove JWT/login behavior. No browser, mobile UI, public authenticated workflow, production migration, deployed frontend/API identity, PC health/readiness or public `ops.doobielogic.io` acceptance was performed. Readiness/auth-only smoke would not substitute for the affected authenticated functional workflow. Primary retains implementation decisions and all release responsibilities. Do not label this candidate `RELEASED_VERIFIED`.
