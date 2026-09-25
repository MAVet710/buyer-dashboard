# Facility adoption and report subscriptions

Implementation Readiness is available from Home and Settings. Automatic evidence is
read from canonical facility records and is never overwritten by annotations.
Administrators can record owners, dates, notes, and explicit manual attestations.
Permission review, operating-mode selection, accounting applicability, and workflow
acceptance require notes. Integration connection validation and successful production
synchronization are separate from operational workflow acceptance. Sandbox syncs and
credential presence never count as production verification.

Scheduled Reports is available under Reports. Only facility administrators and DEV
can manage subscriptions or view recipients and delivery history. Each subscription
uses the existing Executive Report builders and the selected facility's capabilities.
Reports use server defaults and current canonical data, not browser-only scenarios.
The recipient list is an explicit administrator-approved disclosure of the report.
Tests send the same report to the saved recipients with a test subject.

Apply `0080_onboarding_reporting` through the normal migration procedure before
using either page. It adds three tables and scoped indexes without rewriting business
records. PostgreSQL browser roles are revoked and RLS is enabled; the existing runtime
identity retains server access. A downgrade refuses to discard recorded evidence.

## Due-run entrypoint

`POST /api/v1/report-subscriptions/process-due` uses normal authenticated organization
and facility context and requires administrator access. Each call processes at most
10 due subscriptions in that facility. An authorized application service caller may
invoke it repeatedly to drain a larger batch. The UI also exposes this action.
No Windows task, startup worker, release-controller change, or anonymous/global
scheduler is installed. Unattended scheduling requires an authorized caller of this
entrypoint; saving a subscription alone does not start a timer.

The first run is one cadence after creation. Daily and weekly schedules add 1 or 7
UTC days. Monthly schedules advance one calendar month and clamp the day to month
end; subsequent runs retain that clamped day. Missed intervals coalesce into one
current report, then advance to a future occurrence. Resume retains the schedule,
so overdue paused subscriptions become eligible at the next due-run call.

`POST /api/v1/report-subscriptions/{id}/run` requires `X-Idempotency-Key` (1 to 64
letters, digits, underscores or hyphens) and accepts `{"test": true|false}`.
Repeat an identical key and mode to retrieve the existing receipt without resending.
Manual runs do not advance the cadence. History returns 50 records per page via
`GET /api/v1/report-subscriptions/history?offset=0`.
Subscription lists return 100 rows per page using the same `offset` parameter.

## Delivery and recovery

A unique receipt and schedule advancement commit before SMTP. The service resolves
the existing encrypted/environment Spacemail configuration and performs live SMTP
authentication/NOOP validation before report generation and dispatch. It uses SMTP
directly so report attachments are retained; no fallback provider is used. Recipients
are SMTP envelope recipients rather than a visible distribution list.

Unavailable mail records `deferred`; preparation/validation failures record `failed`.
SMTP acceptance records `sent`, which is not proof of inbox delivery. Partial refusal
or ambiguous send failure records `needs_review`. Interrupted workers leave a visible
`processing` receipt; they are never automatically replayed. Review Spacemail/provider
evidence before deliberately issuing a new run key. The database and SMTP cannot
provide atomic exactly-once delivery; this implementation favors at-most-once attempts
over duplicate mail. Reports and provider exception bodies are not persisted in logs
or receipts. Delivery reservations, outcomes, subscription changes, and checklist
reviews use the existing operational audit ledger.

Source-only delivery was requested for this worker. Production migration application,
authorized scheduling invocation, and authenticated PC/public acceptance remain part
of the coordinated release, not this local commit.

## Local verification

- 72 focused and broader backend checks passed, including readiness evidence,
  fixed query count, authorization, concurrent due-run claims, SMTP outcomes,
  report generation compatibility, and migration contracts/rollback preservation.
- Frontend lint, production build, and all 110 unit tests passed.
- Mocked Edge browser checks at 1280px and 390px verified readiness form submission,
  report test payloads and idempotency headers, with no horizontal overflow or
  browser exceptions. These are local UI checks, not authenticated public acceptance.
- Live Spacemail delivery, PostgreSQL migration application, and PC release acceptance
  were not performed under this worker's explicit no-deploy scope.
