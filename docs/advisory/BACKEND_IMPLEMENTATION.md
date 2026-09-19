# Advisory backend: implementation and deployment contract

The consulting intake is a separate marketing domain. It does not write inventory, operational customers, traceability providers, or consulting outcomes into operational ledgers.

## Durable capture

`POST /api/v1/advisory/leads` validates bounded contact/operation fields, a known service, explicit boolean consent, optional attribution, and optional score answers. The server assigns the configured advisory organization; clients cannot submit an organization or lifecycle status. An accepted response is returned only after the lead and canonical audit event commit together. Email is not a dependency, and this implementation sends no notifications.

An optional `submission_id` UUID makes retries idempotent. Reuse the same UUID and identical normalized answers after an uncertain request. A repeated identifier with different data returns 409. The public response is 202 `{accepted:true,reference:<opaque UUID>}`; no public lookup exposes lead details. The honeypot returns the same response shape without saving spam.

Required fields: `name,email,company,role,state,operation,locations,challenge,service,consent`. Optional: `phone,message,website,source_tool,tool_inputs,attribution,submission_id`. Field bounds are authoritative in `modules/advisory/schemas.py`. Only the eight agreed service values (seven services plus `not-sure`) are accepted. Unknown fields are rejected, including client-supplied scores, CSV bodies, or ownership fields.

Attribution retains only a landing path, referrer origin, and bounded campaign labels. Query strings, fragments, URL credentials, and arbitrary payload properties are not retained. Do not place personal information in campaign tags. Contact details remain in the protected lead table; audit creation records do not duplicate them.

## Scoring and CSV boundary

`shared/advisory_score.json` is the versioned 25-question definition. All known keys must be supplied; answers are strict integers0–4 or null. At least 15 applicable answers are required. The total equals sum(answers)/(4×applicable answers)×100, with the same calculation per category. Results use integer percentages and half-up rounding. A category with no applicable questions has a null score. These are self-reported inputs, not verified business performance.

`POST /api/v1/advisory/score` evaluates `{tool_inputs:{...}}` without persistence. When a lead attributes an operations score, the server recomputes and stores the versioned snapshot and answers. `inventory-health-check` is attribution only: it cannot submit tool inputs, raw CSV rows, filenames, or uploads. Raw inventory analysis remains browser-only. There is no advisory file-upload route.

## Abuse controls

The route guard runs before JSON parsing and dependency resolution. It enforces 32 KiB for both declared and streamed request bodies and rejects browser Origins outside the exact public/apex/www/operator allowlist (configured local development origins only in development). Nonbrowser API requests may omit Origin; they still pass validation and throttling.

A thread-safe in-process limiter permits 5 lead attempts per 15 minutes and 120 other public POST requests per minute per peer/path bucket. It holds at most 4096 expiring keys. Peer addresses are hashed in memory and never persisted. Caller-supplied forwarded headers are not used directly. Optional `DOOBIELOGIC_ADVISORY_TRUSTED_PROXY_CIDRS` (empty by default) permits only matching socket peers to supply `X-Advisory-Client-IP`, validated as one IP address. Untrusted peers, malformed values, and scoped IPv6 values fall back to the socket peer. Caddy must overwrite the dedicated header using its trusted Cloudflare client-IP derivation, never pass through incoming browser values; do not configure broad network ranges. Deployment proxy trust must remain restricted to known ingress; deployments where all users share one proxy peer must configure trusted proxy handling or use an edge limiter to avoid unfair grouping.

This limiter is intentionally **not distributed**. It resets on restart and each worker has its own budget. Use a shared/edge limiter before scaling workers or instances. No CAPTCHA, paid analytics provider, or external service is required.

## Consent-gated aggregate events

`POST /api/v1/advisory/events` accepts exactly `{event,placement,item?,consent:true}`. Twelve approved event names and fixed placement values are enumerated in the schema. `item` is a fixed content slug, not user input. PostgreSQL/SQLite atomic upserts increment one daily bucket per owner/event/placement/item. These rows contain no user identity, IP, cookies, raw URL, or form values. Consent must be a literal boolean true. The browser adapter is responsible for honoring privacy preferences before calling the endpoint.

## Administration

All `/api/v1/advisory/admin/*` routes use existing authentication and additionally require platform DEV. A customer admin, supervisor, buyer, operator, or trial role cannot access them. DEV may retain an existing valid organization/facility session; service queries always bind the separate configured advisory owner. No arbitrary tenant selector is exposed.

- `GET /admin/leads?status=&limit=50&offset=0`: bounded list, maximum 100 records.
- `GET /admin/leads/{reference}`: contact, challenge, attribution and score detail.
- `PATCH /admin/leads/{reference}`: `{status,expected_version,note?}`. Known statuses are `NEW,CONTACTED,QUALIFIED,CONSULTATION_BOOKED,PROPOSAL_SENT,CLIENT,CLOSED_LOST`. Allowed lifecycle transitions are explicit in STATUS_TRANSITIONS. CLIENT requires PROPOSAL_SENT first; reopening CLOSED_LOST returns to CONTACTED or QUALIFIED; every changed status/note is audited with authenticated actor and before/after version. Stale changes return409.
- `GET /admin/metrics?days=30`: current status distribution; distinct leads that actually reached each status from canonical history; and aggregated event totals for the bounded1–366-day event window. Reached stages are not inferred from stage order.

`scripts/advisory_admin.py` provides list, show, set-status, and metrics commands through these authenticated API routes. It never accesses the database directly. Supply a short-lived platform DEV token through `ADVISORY_API_TOKEN`, with valid existing context in `ADVISORY_CONTEXT_ORGANIZATION_ID` and `ADVISORY_CONTEXT_FACILITY_ID`. Default API origin is `https://ops.doobielogic.io`; local HTTP is limited to loopback. The list output omits email and phone; explicitly requesting a single lead displays contact details. Do not redirect that output into public artifacts. The deployed public Cloudflare path returned HTTP 403 for the Python CLI user agent during release checks. On the hosting PC, set `ADVISORY_API_BASE=http://127.0.0.1:8080` to use the local Caddy ingress. This is a transport workaround only: the same valid bearer token, platform DEV authorization, and existing organization/facility context are still required. Do not disable authentication or expose the loopback endpoint publicly.

## Deployment status and owner setup

Deployment completed on 2026-09-19. The reviewed additive migration `0078_advisory_leads` was applied to the deployed Supabase database, advancing the existing 0077 schema head. The deployment verified the two advisory tables, runtime grants, enabled RLS, and revoked direct PUBLIC/anon/authenticated access. Application startup does not call `create_all`.

The runtime role `doobielogic_render_runtime` has BYPASSRLS but cannot CREATE in public. Schema changes therefore use the migration/admin connection, with explicit runtime table grants afterward. Keep browser access revoked; FastAPI remains the authorization boundary. Grants and RLS are separate controls; see [Supabase API security](https://supabase.com/docs/guides/api/securing-your-api).

The dedicated active `DoobieLogic Advisory` organization, slug `doobielogic-advisory`, was provisioned. Its ID is configured privately through `DOOBIELOGIC_ADVISORY_ORGANIZATION_ID`; no customer or sandbox organization was reused. No facility is needed for lead ownership or canonical audit writes. Future setup must reuse that same dedicated owner rather than creating duplicate business ownership records.

Intake, analytics, and admin data routes still fail 503 if the configured owner is absent or inactive. Scoring and booking configuration are independent of database availability.

On the deployed PC ingress, Caddy overwrites `X-Advisory-Client-IP` from `CF-Connecting-IP`; the backend trusts only the configured loopback proxy peers. Preserve that overwrite and the restricted ingress path. Do not forward a browser-supplied dedicated header or broaden backend proxy trust to arbitrary peers.

Optionally set `DOOBIELOGIC_ADVISORY_BOOKING_URL` to a real HTTPS booking URL. `GET /api/v1/advisory/booking` returns `{available:false,url:null}` when unconfigured/invalid. It does not invent appointments or expose credentials.

Release verification successfully submitted a synthetic application through the browser and received HTTP 202, confirmed idempotent replay, and confirmed unauthenticated admin access returns HTTP 401. The synthetic test lead was deleted afterward. These checks validate the deployed flow; they are not customer usage or marketing proof. The automated regression tests continue to use isolated SQLite and mocked route dependencies.

## Operational retention and follow-up

Accepted leads persist in the advisory table until an authorized operator explicitly removes them under the business's retention process. There is no automatic expiry, deletion job, or retention-duration guarantee. Apply an approved retention policy to contact fields, stored score answers, and any personal information entered in internal audit notes; deleting a lead does not itself define retention for canonical audit history. Daily analytics contain aggregate counts rather than applicant identities. Raw inventory CSV data is never submitted to this backend.

There are no automatic notification emails or follow-up messages. A durable accepted lead does not mean someone has been notified or a consultation has been booked. Staff must review the authenticated lead list, manage the lifecycle, and arrange follow-up through their approved process.

## Regression coverage

`python -m pytest tests/test_advisory.py tests/test_migration_revision_contract.py -q` covers transactional persistence/failure, idempotency, owner scoping, DEV authorization, optimistic concurrency, cumulative stage counts, score weighting/NA/validation, consent/privacy, atomic event counts, trusted origins, spoofed forwarding headers, streamed body limits, bounded throttling, booking safety, SQLite migration round-trip, and PostgreSQL RLS/revoke statements. Tests execute no external email, provider action, or production database write.


Release-worktree validation: `python -m pytest tests/test_advisory.py tests/test_migration_revision_contract.py -q` passed **50 tests**. The earlier run including `tests/test_beta_application_delivery.py` passed **51 tests**. The beta delivery test remained unchanged.
