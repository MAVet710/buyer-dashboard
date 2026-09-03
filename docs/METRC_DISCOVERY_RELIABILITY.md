# METRC discovery reliability repair

Branch: `codex/metrc-discovery-reliability`, based on `9b58348`.

## Observed production failures

On September 3, 2026, Cloud Run logged a 300-second 504 for sandbox facility
discovery, database QueuePool exhaustion for integrations/status endpoints, and
subsequent 401 responses for discovery. The old route forwarded METRC 401s as app
401s, so those logs alone cannot distinguish provider authentication from an
expired app session. No credentials were reset or live discovery replayed.

## Changes

- Discovery saves mappings and the provider facility profile, then returns before
  initial provider-resource sync. The browser automatically advances through
  mapped facilities with a separate request per facility and explicit retry UI.
- Navigating away stops scheduling further facilities; already-started work may
  finish. Mappings and imported records remain durable. Discover again to resume;
  repeat imports deduplicate records. This is not an unattended background job.
- Each bootstrap read gets one attempt, preserving retries for other callers.
- Duplicate lookups are batched per resource instead of per record, and database
  connections are not held while provider calls execute.
- Pool exhaustion returns a sanitized 503 with Retry-After, stopping profile
  persistence at the first pool failure rather than repeating the wait per row.
- Provider 401s use 502 with the METRC error message, avoiding app-login refresh
  and automatic replay. A sanitized provider-status log distinguishes future
  provider failures. App-authentication 401 handling is unchanged.
- Bootstrap validates organization, mapping, user, license, MA, and sandbox scope.

## Verification and release

Regression tests cover a one-connection pool, tenant isolation, resumable mapping,
profile preservation, bounded transport attempts, deduplication query counts,
provider-auth status, and pool failure handling. Existing targeted METRC tests,
TypeScript checks, and the Vite production build also pass.

Not deployed. Deploy the API before the frontend because the frontend uses a new
bootstrap endpoint. No database migration or credential change is needed. After
release, verify with the user's sandbox discovery workflow and check provider
status logs; valid METRC credentials have not been established by local tests.

An independent production log showed a missing approved_sources.json artifact.
That unrelated AI catalog packaging error is not changed by this patch.
