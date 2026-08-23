# Phase 8 release-candidate continuity evidence — 2026-08-23

This record supplements `WEB_CUTOVER_EVIDENCE.md` and `PARITY_EXECUTION_CONTROL.md` with read-only verification performed against the connected live DoobieLogic Supabase project after the August 22 preflight record was written.

It does **not** authorize production traffic, DNS cutover, PR merge, or retirement of Streamlit.

## Live database and Auth state verified

- Supabase project `DoobieLogic` is `ACTIVE_HEALTHY` in `us-east-2` on PostgreSQL 17.
- `public.alembic_version` reports `0037_function_acl_hardening`.
- Six active durable `app_users` exist and all six still contain portable bcrypt hashes.
- Six Supabase Auth users exist.
- Durable-user continuity is exact for all six active accounts:
  - 6/6 Supabase Auth UUIDs equal the durable `app_users.id` UUID.
  - 6/6 login emails match the durable login email produced by the migration.
  - 6/6 `app_user_id` Auth metadata values match.
  - 6/6 legacy username metadata values match.
  - 6/6 role metadata values match.
  - 6/6 organization metadata values match the migration plan.
  - 6/6 facility metadata values match the migration plan.
  - 6/6 Supabase Auth password hashes equal the durable legacy bcrypt hashes, confirming password-hash continuity without exposing any password or hash value.
- One active durable account still has `must_change_password=true`; that durable account has the expected matching Supabase Auth UUID. The application remains responsible for enforcing this durable state after authentication.
- Three active users intentionally have no stored organization and resolve through the DEV default organization/facility behavior documented by the migration plan.
- Four active organizations, three active facilities, and three explicit user/facility-role rows exist.
- One active facility is the DEV Sandbox, confirming the durable sandbox facility remains present.

## Database access hardening verified

After 0037:

- Direct `anon` / `authenticated` grants on public application tables: **0**.
- Direct `anon` / `authenticated` grants on public application sequences: **0**.
- `PUBLIC` / `anon` / `authenticated` execute grants on public application functions: **0**.
- Supabase Security Advisor currently reports informational `RLS enabled, no policy` notices on application tables. In the present architecture these tables also have no browser-role grants and operational access is intended to pass through FastAPI, so these notices do not by themselves establish a browser-access defect.
- Supabase Security Advisor reports **Leaked Password Protection Disabled**. This is a hardening follow-up before broad public launch; it is not treated as proof of broken legacy-password continuity.

The Supabase Data API project setting itself was not changed or asserted during this read-only verification. The existing cutover requirement to disable the unused Data API before public production cutover remains open until that project setting is directly verified.

## Responsive/browser release-candidate evidence verified

GitHub Actions `React and FastAPI gates` run **357** on head `cade4ac7820f874b1565c88c52213559f251fcce` completed successfully.

The real Chromium parity matrix passed at all required widths:

- 390 px
- 430 px
- 768 px
- 1024 px
- 1440 px

The browser gate exercised the actual React app shell/components with deterministic release-candidate data and verified:

- Buyer continuous command-center surface and required recorded-workflow sections.
- White Label / Repack and all five Streamlit-style steps.
- Inventory -> Package Studio work-window opening.
- Package Studio full-screen behavior at mobile/tablet widths and right-side drawer behavior at desktop widths.
- Production Inventory as a distinct bulk/cultivation surface.
- No document-level horizontal viewport overflow at any required width.
- No uncaught browser page errors during the matrix.

The workflow uploaded `browser-parity-evidence` artifact **9498594372** (SHA-256 `a915b591fd6302163d1f4d562a69abb3c515b1cad012d459612b14e115242cf0`) with a 14-day retention window.

Both current PR workflows are green on the same head:

- `React and FastAPI gates` run 357 — success.
- General `CI` run 545 — success.

Backend tests, strict parity contract verification, production migration/startup container checks, frontend build, and both fixable-high/critical image security scans are green on the same candidate.

## Continuity blockers found — do not mark Phase 8 complete

### Facility license continuity is not verified

The live database currently has **zero** active facility rows with `coman_facilities.license_number` populated.

There are two active non-sandbox facilities, and both currently have a blank facility license number. Neither of those two non-sandbox facilities has historical facility-linked license evidence in the current extraction/traceability rows queried during this verification.

This does not prove that licenses were lost; it proves that the release candidate cannot currently demonstrate license continuity from its durable facility records. The Phase 8 license gate therefore remains **open**.

### METRC integration continuity is not verified

`integration_configurations` currently contains **zero** rows. A durable traceability transaction exists with provider `metrc` and verified status, which proves that METRC-shaped traceability evidence exists, but it does **not** prove that a live facility-scoped METRC credential/configuration survived cutover.

The Phase 8 METRC configuration/credential continuity gate therefore remains **open**. Do not create, overwrite, or infer a METRC credential merely to close this gate; reconcile it against the actual pre-migration operator/facility configuration.

## Still required before release acceptance

- Reconcile the supplied Streamlit/operator visual evidence side-by-side. The documented Buyer recording could not be retrieved from the current file source during this verification, so operator-recording acceptance remains open even though the automated real-browser matrix is green.
- Reconcile real facility license numbers/types against the pre-migration source of truth and populate only after exact facility ownership is proven.
- Reconcile real METRC facility configuration/credentials against the pre-migration source of truth and validate them without exposing secrets.
- Verify the unused Supabase Data API is disabled while Supabase Auth remains functional.
- Complete the encrypted production backup plus isolated restore drill evidence if it has not already been completed and recorded.
- Verify representative real-account sign-in, refresh, sign-out, password-change/recovery behavior, role/facility switching, DEV cross-company access, and the existing `must_change_password` account through the release candidate UI/API. Hash equality is strong migration evidence but is not a substitute for a real sign-in acceptance pass.
- Verify the approved deployed release candidate returns HTTP 200 from `/health` and `/health/ready` and review candidate logs before production traffic.
- Complete final product-owner browser acceptance before PR #276 leaves draft or is treated as production-complete.
