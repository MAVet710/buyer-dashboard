# Security Center release contract

Candidate status: implemented; consult the PC release receipt for deployment status.
Architecture: existing Windows PC, Cloudflare Tunnel, Caddy, FastAPI and hosted Supabase.

## Included
- Threshold-based, alert-only username-login and verified-user scope-denial detection.
- Success-after-failure correlation and committed account-administration audit projection.
- Bounded event queue, bounded queries, visible lost events and monitoring failures.
- Platform-DEV-only review and audited optimistic triage APIs; customer roles are denied.
- Read-only Admin Tools incident display with explicit notification states.
- Optional owner email dispatcher using existing mail transport and strict recipient validation.
- Durable notification claims, per-hour/day budgets, and no automatic replay of uncertain sends.
- Provider acceptance is never described as inbox delivery.
- Seven-day derived-event retention, 90-day resolved-incident retention, and an event capacity guard.
- Unresolved incidents and canonical business/audit records are never deleted by retention.

## Required deployment configuration
SECURITY_MONITOR_ENABLED=true and a distinct SECURITY_HMAC_SECRET of at least 32 characters.
SECURITY_TRUSTED_PROXY_CIDRS must match only the verified loopback proxy when enabled.
Do not trust arbitrary forwarded headers. No credentials go into frontend variables.
Start FastAPI with lifespan enabled and SANDBOX_STARTUP_SEED_ENABLED=false.
Existing hosted Supabase project, encryption keys and user identities are preserved.

## Notifications and coverage
Email is opt-in: valid recipient, working existing sender credentials, and explicit activation.
Until verified, email remains disabled and the UI reports not_connected.
No new email account, domain record, credentials or paid subscription is required by the code.
Direct Supabase Auth, Cloudflare WAF and Defender collectors are not part of this first deployment.
Any separate external heartbeat must be described using its actual checking interval and status.
This is not antivirus, automatic blocking, or proof that every intrusion will be detected.

## Persistence and recovery limitations
Request observations are buffered until batch commit; process crashes may lose that backlog.
Account-audit polling currently has a five-minute lookback; prolonged downtime requires review.
Capacity exhaustion raises a degraded-monitor signal instead of filling the application database.
A fixed 15-minute incident bucket can generate adjacent-bucket incidents.

## Migration and rollback
Alembic 0079 adds only security tables/indexes and scoped grants for the existing runtime role.
Browser and public database roles remain revoked. The migration never changes business data.
Empty-only schema rollback refuses to destroy populated security evidence.
A schema-compatible prior-code rollback release must exist before production activation.
Never weaken readiness checks, delete evidence, or reverse production migrations blindly.

## Validation
Tests cover signed-JWT access, spoofed headers, redaction, queue/database errors,
thresholds, duplicate prevention, sender failures, notification budgets, and retention.
The timestamp fixture uses exact seconds to avoid float-to-datetime rounding flakiness.
Final-candidate CI and real PC/source identities must be captured in the release receipt.
