# P0-P2 Production Readiness

This document records the operational contract introduced by the P0-P2 hardening pass. Workflows and `render.yaml` remain the executable source of truth.

## Zero-cost hosting contract

DoobieLogic's hosted beta must not require a paid cloud account or silently fall back to a billable service.

- **Frontend:** Render Static Site / CDN for the React/Vite bundle.
- **Frontend domains:** `doobielogic.io` is primary and `ops.doobielogic.io` is an alias on the same static site.
- **API:** Render Free native-Python web service defined by `render.yaml`.
- **API domain:** `api.doobielogic.io`.
- **Auth/data:** existing Supabase Free project remains authoritative.
- **Transactional mail:** hosted production uses HTTPS (`RESEND_API_KEY`). Spacemail SMTP/IMAP remains a local/legacy fallback.
- **AI:** hosted production defaults to `AI_PROVIDER_MODE=disabled` and `AI_ALLOW_CLOUD_FALLBACK=false`; workstation Local AI remains decoupled from hosted compute.
- **Google Cloud:** no permanent GitHub Actions workflow may authenticate to or create Google Cloud resources.

`python scripts/verify_zero_cost_deployment.py` is the fail-closed contract check. It scans workflows for Google control-plane/registry wiring, validates the free Render configuration, verifies HTTPS transactional-mail wiring, and confirms explicitly gated database mutations.

Zero-cost is more important than uninterrupted hosting. Do not add a payment method or automatic paid upgrade merely to prevent a free service from sleeping or suspending.

## Release gates

### Main release handoff

`.github/workflows/deploy.yml` is a release gate, not a cloud provisioning workflow. It:

1. enforces the zero-cost hosting contract;
2. verifies release parity;
3. builds the exact API Docker image locally;
4. verifies exactly one Alembic head;
5. proves production API configuration can initialize with hosted AI disabled; and
6. verifies the Render handoff is check-gated and tied to exact Git commit identity.

After repository checks pass, Render's Git integration is the canonical deployment handoff. The workflow must not authenticate to a billable cloud control plane, push to a paid registry, or create paid compute resources.

### Release candidate

`.github/workflows/rc-preview.yml` is intentionally local/synthetic. It builds the API image and frontend, proves the API can initialize inside the Render Free resource envelope, and runs smoke checks without creating external preview infrastructure.

## Database runtime contract

### Production API role

The hosted API uses a dedicated PostgreSQL role, `doobielogic_render_runtime`, instead of the Supabase `postgres` owner credential.

The role:

- can log in;
- is not a superuser;
- cannot create roles or databases;
- has application DML/sequence/function access in `public`;
- bypasses RLS only because tenant authorization is enforced by the server-mediated API; and
- is bounded by statement, lock, and idle-in-transaction timeouts.

The public Render API process does **not** run `alembic upgrade head`. `/health/ready` fails closed when the live schema does not match the code's Alembic head. Schema migrations remain an explicit administrative/release action.

The current Supabase shared session-pooler shard for this project is `aws-1-us-east-2.pooler.supabase.com:5432`. Do not infer `aws-0` from examples; use the project-assigned pooler endpoint.

### Backup and restore proof

`.github/workflows/database-backup.yml` uses a separate dedicated role, `doobielogic_backup_runtime`.

The backup role is login-enabled, non-superuser, cannot create roles/databases, is read-only on the application schema, and bypasses RLS only so a database-level backup cannot silently omit tenant rows.

The workflow does **not** store a production database URL or database password in GitHub. Instead it derives the backup-role password in memory from `DATABASE_BACKUP_ENCRYPTION_PASSPHRASE` using HMAC-SHA256 with the fixed context `doobielogic-backup-db-v1`. The corresponding PostgreSQL SCRAM verifier was provisioned once in Supabase; the plaintext database password was never committed.

Every backup run must:

1. validate the backup configuration;
2. derive and mask the dedicated backup-role password in memory;
3. authenticate before creating an artifact;
4. create a custom-format `public` schema/data dump;
5. restore into an isolated PostgreSQL 17 service;
6. verify exactly one Alembic revision and read the restored schema head;
7. encrypt the dump with AES-256;
8. generate a SHA-256 checksum;
9. retain only the encrypted artifact and checksum; and
10. remove plaintext runner files.

A production proof completed successfully on GitHub Actions run `34387423660`: authentication, `pg_dump`, restore, Alembic verification, AES-256 encryption, checksum generation, artifact retention, and cleanup all passed. The retained proof artifact is encrypted and expires under normal retention policy.

The permanent workflow runs on schedule, by manual dispatch, and after a successful `main` release gate. It is not PR-triggered.

## Frontend and performance correctness

- React CI requires zero ESLint warnings.
- Hook dependency warnings are correctness signals rather than globally suppressed.
- Admin edit forms preserve unsaved operator input across same-record background refetches.
- `.github/workflows/performance-contract.yml` is a first-class realistic-volume performance gate.
- Playwright is pinned in the frontend package and lockfile; CI must not mutate the dependency graph during runs.

## MA Metrc sandbox

`.github/workflows/ma-metrc-sandbox-readonly.yml` performs an authenticated **read-only** MA sandbox Facilities validation after successful `main` release gates and on its weekday schedule. It emits only redacted evidence.

Automatic validation must never perform provider mutations. Controlled MA sandbox mutation evaluation remains in the separate manual workflow and requires its exact approval phrase.

Do not claim Metrc provider validation has passed until a real live sandbox execution produces provider evidence.

## Hosted API latency

`.github/workflows/post-deploy-performance-smoke.yml` probes `https://api.doobielogic.io/health/ready` without an application password, database credential, or cloud identity token.

For a release-triggered run, the probe waits until the public API reports the triggering Git commit in `release_sha` and verifies live schema readiness. Free-tier cold start is measured separately from warm p95 latency.

## Zero-cost operational workflows

### Local AI audit

`.github/workflows/ai-runtime-revision-guard.yml` validates that hosted Render configuration cannot use paid cloud AI fallback and separately checks the optional workstation Local AI declaration.

### Controlled database mutations

`seed-cowboy-kush-demo.yml` and `reset-dev-sandbox-vertical-inventory.yml` validate definitions automatically but require explicit manual dispatch, exact approval phrases, and server-side credentials before any database mutation. Normal push-triggered validation remains non-mutating.

### Storefront aliases

`.github/workflows/storefront-domain-mappings.yml` is validation-only. It validates exact approved aliases, bounds the operating set conservatively, and never creates DNS or hosting resources.

## Render configuration

### API

The canonical API service must remain on Render `free` and receive these protected values without committing them:

- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_JWKS_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `INTEGRATION_ENCRYPTION_KEY`
- `RESEND_API_KEY`

`SUPABASE_SERVICE_ROLE_KEY` is intentionally not a baseline runtime requirement. Normal authentication uses the publishable key; admin-only Supabase operations fail closed if a privileged key is absent.

A clean Render Free proof service successfully completed FastAPI application startup against the dedicated runtime role after correcting the project pooler shard from `aws-0` to `aws-1`.

Attach `api.doobielogic.io` to the canonical service only after it reports `/health/ready` with `schema_matches=true` and the expected release SHA.

### Static frontend

The second service in `render.yaml` builds with the frozen pnpm lockfile and publishes `frontend/dist`. It includes SPA fallback, security headers, immutable asset caching, and uncached `release.json` commit identity.

Provide these build-time values through Render:

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_PUBLISHABLE_KEY`

`VITE_API_URL=https://api.doobielogic.io` is versioned because it is not secret.

## Transactional email

Hosted transactional mail uses the Resend HTTPS API because free Render services must not depend on SMTP egress. `doobielogic.io` has been created in Resend with TLS enforced and tracking disabled.

`RESEND_API_KEY` belongs only in Render's protected environment. DNS verification of the sending domain remains a control-plane task and must not be represented as complete until the required records are present and Resend reports the domain verified.

## Merge discipline

Before production DNS cutover:

- canonical code, browser, container/security, zero-cost, RC, and performance gates must be green;
- Render API/static services must remain free;
- required protected environment values must be configured without committing secrets;
- the canonical API must report the deployed Git SHA and current schema; and
- backup/restore proof must remain reproducible with the dedicated derived backup role.

Under the zero-cost mandate, service suspension or cold start is preferable to an unexpected bill.
