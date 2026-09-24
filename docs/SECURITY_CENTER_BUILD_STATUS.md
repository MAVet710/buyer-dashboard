# Security Center: observer-stage implementation

Updated September 24, 2026. Status: OBSERVER_IMPLEMENTED_NOT_DEPLOYED.
Branch: feat/security-center-20260924. Based on the unmerged Extraction repair
7453221bae6e206da9281e45d0c417d903ff5573 (PR #582). This supersedes the earlier
partial-scaffold status. The actual candidate commit and CI result belong in the
release receipt; no deployment is implied by this document.

## Implemented
- Alert-only rules for repeated username-login failures, multi-account attempts
  from a trusted source, success after repeated failures, repeated verified-user
  organization/facility denials, and sensitive canonical account-audit changes.
- Observations connected to existing login and authorization outcomes. No new
  blocking, permission bypass, automatic ban, credential change or provider write.
- A bounded 1024-event memory queue, batches of 64, ten-second polling, retry of
  unsaved batches, visible drop/failure counters, and degraded-monitor incidents.
- Privacy: keyed account/source pseudonyms; no passwords, tokens, raw usernames,
  raw addresses, query strings or request bodies in security observations.
- Authenticated platform-DEV-only incident API, optimistic audited triage API,
  and a read-only Security Center panel inside the existing Admin Tools page.
- Additive migration 0079_security_observation, with PostgreSQL RLS enabled and
  direct PUBLIC/anon/authenticated table privileges revoked. Runtime-role grants
  require explicit review at deployment; the migration has not run in production.
- Isolated signed-JWT tests and a PostgreSQL release gate. Browser component
  tests use mocked API responses, not live authenticated customer traffic.

## Verified local evidence
98 selected backend tests passed, covering the new observer, safe empty/populated
rollback handling, existing web infrastructure/security,
username login, admin boundaries, identity/compatibility, migration revision
contracts and Extraction query regressions. Three browser checks passed for
DEV-only visibility, deferred loading and stale-status removal on failed refresh.
Frontend lint and production build passed. All 107 frontend unit tests passed
across 21 test files. These backend suites overlap earlier 54/86 runs; do not add
them as separate unique tests. The first CI failure was the empty rollback
contract, now reproduced, repaired, and covered without weakening the test.
These results are not a full production acceptance or penetration-test report.

## Not implemented or not connected
Email sending was not installed: its write operation was rejected by the execution
service. No recipient was selected, no test email was sent, and pending incident
metadata is NOT proof of a working notification queue. Both API status and UI
explicitly report notification delivery as NOT CONNECTED.
Direct Supabase Auth, Cloudflare, Windows Defender and off-PC availability/heartbeat
collectors are NOT CONNECTED. Email-login traffic sent directly to Supabase is
outside the current username-login observer's coverage.

## Limits and activation gates
The observer is disabled by default. It also refuses capture without a separate
security HMAC secret of at least 32 characters. No secret was generated or copied.
Source correlation stays unavailable behind loopback ingress unless the verified
proxy overwrite and narrowly scoped SECURITY_TRUSTED_PROXY_CIDRS are configured.
The initial thresholds are engineering settings, not evidence of a confirmed attack:
8 failed username logins, 20 failures across at least 5 account keys per source,
or 10 scoped-access denials in five minutes. Fixed 15-minute incident buckets can
produce adjacent-bucket alerts; committed privilege events deduplicate by audit ID.

In-memory requests can be lost on a process crash before a successful batch commit.
Canonical-account-audit polling currently covers the latest five minutes, bounded
to 200 rows. Older outage history is NOT automatically backfilled. Saturation is
reported as degraded, not complete coverage. This is not a tamper-proof external
security ledger. Retention, persisted-storage quotas and long-outage recovery still
require review before production activation. No automatic evidence deletion exists.

Existing runtime readiness requires an exact Alembic revision. Applying 0079 needs
a reviewed compatibility/rollback plan: simply restarting the old 0078 binary is
not a verified rollback. An unused migration can roll back after all three security tables are confirmed empty.
Populated tables refuse rollback; PostgreSQL holds exclusive locks throughout the
check and removal to avoid an observation being written between those operations.
Complete notifications, externally verified outage alerts, retention/capacity,
final candidate gates, startup-task alignment, migration/grants, configured secrets,
and actual PC/public authenticated acceptance before declaring protection active.

## Local locations
Checkout: C:\Users\ndasi\Documents\DoobieLogic\releases\pc-security-center-20260924
Evidence: C:\Users\ndasi\Documents\DoobieLogic\review-evidence\security-center-observer-20260924
The running application was left unchanged at b6845062 during this iteration.

## Engineering references
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- FastAPI lifespan: https://fastapi.tiangolo.com/advanced/events/
