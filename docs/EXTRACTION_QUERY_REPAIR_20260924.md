# Extraction query and connection repair - September 24, 2026

Status: CODE_READY locally; production delivery remains open, not deployed.
Baseline source: 3a168d4dd9b5f4f7d2371d5f790668681fa195b9.

## Reproduced defects
An isolated harness re-executed the saved original overview and performance functions.
The original overview issued 717 SQL statements for 31 synthetic runs.
With a one-connection pool, resource cost was returned as 0 instead of the recorded 5.
The original active-session resource-table probe also swallowed a simulated database error.

## Repair and preserved boundaries
A bounded read projection aggregates canonical records using one session, without per-run queries.
The 500-run limit, tenant/facility scope, response shape, status-specific totals, manual fallbacks,
pricing precedence, QA precedence, toll jobs, and traceability counts are preserved.
Active-session table inspection reuses its connection and propagates real database errors.
There is no migration, provider mutation, credential change, new ledger, or frontend redesign.

## Observed local validation
The new regression suite passed 13 tests. The expanded selected suite passed 97 tests.
These suites overlap; do not add them together as unique test coverage.
Recorded SQL counts: 10 for one run and 10 for 31 runs, about 98.6% fewer than the original fixture.
This is not a measured production latency or throughput improvement.
Python compilation, git whitespace checks, and the repository quality gate passed.
Migrated PostgreSQL real-JWT and single-connection acceptance coverage was added to the PR gate.
That gate and authenticated public acceptance must be verified before production promotion.

## Production delivery blocker
The live PC release was preserved. The protected Windows startup task still points to the older
controller and requires administrator approval through the existing reviewed Finish-StartupTask.ps1.
Do not bypass that permission or interpret a GitHub merge as a completed PC deployment.
Remaining gates: final PR checks, protected startup-task alignment, matching PC release identities,
and fresh authenticated public Extraction acceptance. Preserve the previous compatible release.
