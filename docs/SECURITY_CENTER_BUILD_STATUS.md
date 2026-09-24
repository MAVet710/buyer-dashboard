# DoobieLogic Security Center build status

Date: September 24, 2026
Status: PARTIAL_SCAFFOLD_NOT_ACTIVE
Branch: feat/security-center-20260924
Base: 7453221bae6e206da9281e45d0c417d903ff5573 (Extraction PR #582)

## Observed work
- Created an isolated PC checkout; the running release was not changed.
- Added platform-only security event, incident and monitor-state model definitions.
- Added HMAC pseudonym helpers so raw account identifiers/IPs need not be logged.
- Added strict ingress-peer handling. A loopback proxy is not treated as an attacker.
- Added event ID deduplication and fixed-window incident deduplication primitives.
- Added committed-canonical-audit projection scaffolding without copying audit payloads.
- Ran isolated SQLite scaffold tests: 13 passed, 0 failed, in 0.55 seconds.

## Important limits
This is not a finished detector. The write operation that would complete detection
was rejected twice by the execution service. The partial detect() function must
NOT be connected to runtime or counted as implemented detection.
No migration, request/auth instrumentation, worker, protected incident UI,
notification sender, external watchdog or production activation was completed.
The model definitions have NOT been applied to hosted Supabase.
No email was sent. No alert recipient has been selected or verified.
No current activity has been classified as an intrusion.
No new automatic blocking, account changes, firewall rules or privileged access.

The 13 checks validate ONLY scaffolding. They are not end-to-end, real-JWT,
PostgreSQL, notification-delivery, penetration or PC-release acceptance.

## Required continuation gates
1. Complete bounded detection, queue/backpressure, visible monitoring health and
   safe capture hooks without making logging an authorization dependency.
2. Add reviewed migration and PostgreSQL RLS/revokes. Never expose global security
   telemetry directly to browser database roles or customer administrators.
3. Add platform-DEV-only incident review and audited triage. Anonymous requests
   must never supply trusted actor/organization context from headers.
4. Reuse the mail transport with minimal messages, a verified owner recipient,
   delivery-state tracking and storm suppression. Acceptance is not delivery.
5. Mark direct Supabase Auth, Cloudflare, Defender and external heartbeat coverage
   NOT CONNECTED until their collectors and real delivery are verified.
6. Test actual detector thresholds, benign activity, cross-tenant authorization,
   redaction, queue/database failure, persistence, notifications and browser UX.
7. Resolve prior PC startup/release blocker; validate integrated candidate before
   migration/cutover and fresh authenticated public acceptance.

## Files and evidence
Local checkout: C:\Users\ndasi\Documents\DoobieLogic\releases\pc-security-center-20260924
Evidence: C:\Users\ndasi\Documents\DoobieLogic\review-evidence\security-center-scaffold-20260924
The existing live release was b6845062 at the preflight; it must be rechecked.

## Design references (reviewed September 24, 2026)
- https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- https://supabase.com/docs/guides/auth/audit-logs
- https://resend.com/changelog/idempotency-keys
These guide subsequent implementation; they are not claims of connected coverage.
