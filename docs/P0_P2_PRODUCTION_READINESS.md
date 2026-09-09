# P0-P2 Production Readiness

This document records the operational contract introduced by the P0-P2 hardening pass. The workflows and deployment configuration remain the executable source of truth.

## Zero-cost hosting contract

DoobieLogic's hosted beta must not require a paid cloud account or silently fall back to a billable service.

- **Frontend:** Netlify Free static hosting for the React/Vite bundle.
- **Frontend domains:** `doobielogic.io` is the primary domain and `ops.doobielogic.io` is a domain alias.
- **API:** Render Free web service defined by `render.yaml`.
- **API domain:** `api.doobielogic.io`.
- **Auth/data:** existing Supabase project and connection limits remain authoritative.
- **AI:** production hosting defaults to `AI_PROVIDER_MODE=disabled` and `AI_ALLOW_CLOUD_FALLBACK=false`; local AI can be re-enabled only with an explicitly free/local runtime.
- **Google Cloud:** Cloud Run and Artifact Registry are not part of the active release path.

`python scripts/verify_zero_cost_deployment.py` is the fail-closed contract check. Release and RC workflows execute it, and regression tests prevent the paid-Google release path from returning unnoticed.

### Free-tier failure behavior

Zero-cost is more important than uninterrupted hosting. Do not add a payment method or enable an automatic paid upgrade merely to prevent suspension.

Netlify Free uses a hard monthly usage limit. Keep auto recharge unavailable/off; if the free allowance is exhausted, the site may pause instead of generating an overage charge.

Render's API must remain on `plan: free`. A free Render service can sleep after idle time and cold starts are expected. The performance smoke therefore measures wake-up separately from warm p95 latency. This mode is appropriate for beta/low-volume use, not a paid-SLA replacement for 24/7 facility infrastructure.

## Release gates

### Main release handoff

`.github/workflows/deploy.yml` is a release gate, not a cloud provisioning workflow. It:

1. enforces the zero-cost hosting contract;
2. verifies release parity;
3. builds the exact API Docker image locally;
4. verifies exactly one Alembic head; and
5. proves the production API configuration can initialize with cloud AI disabled.

After repository checks pass, connected Netlify and Render Git integrations deploy `main`. The workflow must not authenticate to Google Cloud, push to a paid registry, or create cloud compute resources.

### Release candidate

`.github/workflows/rc-preview.yml` is intentionally local/synthetic. It builds the API image and frontend, starts a synthetic API container and local Vite preview, then proves account context and seeded inventory behavior. It must not create external preview infrastructure.

Netlify may provide its own free deploy-preview URL after the repository is connected, but the correctness gate does not depend on that feature.

### Backup and restore proof

`.github/workflows/database-backup.yml` must be able to:

1. validate the configured PostgreSQL backup URI without printing credentials;
2. authenticate to the production database before creating an artifact;
3. create a consistent custom-format PostgreSQL dump;
4. restore the dump into an isolated PostgreSQL service;
5. verify exactly one Alembic revision and read the restored schema head;
6. encrypt and checksum the backup; and
7. retain only the encrypted artifact and checksum.

The workflow runs on schedule, manually, and after a successful `main` release gate. A stale or rejected `DATABASE_BACKUP_URL` is an operations failure and must be rotated outside application source control.

### Frontend correctness

The React CI contract requires zero ESLint warnings. Hook dependency warnings are treated as correctness signals rather than suppressed globally. Admin edit forms must preserve unsaved operator input across same-record background query refetches while still synchronizing when the selected record actually changes.

### Realistic-volume performance

`.github/workflows/performance-contract.yml` runs the realistic-volume performance suite as a first-class PR and `main` gate. Existing assertions define the bounded query, payload, lazy-hydration, and latency contract.

### MA Metrc sandbox

`.github/workflows/ma-metrc-sandbox-readonly.yml` performs an authenticated **read-only** MA sandbox Facilities validation after successful `main` release gates and on its weekday schedule. It emits only a redacted evidence summary.

Automatic validation must not perform provider mutations. Controlled MA sandbox mutation evaluation remains in the separate manual workflow and requires its explicit approval phrase.

### Hosted API latency

`.github/workflows/post-deploy-performance-smoke.yml` probes only the public `api.doobielogic.io/health/ready` path. It does not use an application password, database credential, or cloud identity token.

For a release-triggered run, the probe waits until Render reports the exact triggering Git commit in `release_sha` and verifies the live schema revision. For scheduled/manual checks, a free-tier cold start of up to the configured wake budget is measured separately. After wake-up, warm readiness samples must satisfy the configured p95 limit.

## CI efficiency contract

- The canonical CI workflow owns the complete backend regression suite.
- `web-ci.yml` owns focused FastAPI/web security and infrastructure checks rather than duplicating the full backend suite.
- Playwright is pinned in `frontend/package.json` and `frontend/pnpm-lock.yaml`; CI must not mutate the dependency graph with `--lockfile=false` installs.
- Browser jobs share the versioned Chromium cache but still run Playwright's browser/dependency installation command so missing system dependencies fail visibly.

## One-time free-host connection

### Render API

Create/connect a Render Blueprint from this repository's `render.yaml` on branch `main`. Keep the service on the `free` plan and do not attach a paid instance. Provide the following values in Render's secret/environment UI; never commit them:

- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_JWKS_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `INTEGRATION_ENCRYPTION_KEY`

Attach `api.doobielogic.io` to the API service and update DNS when Render provides the target. The Docker command runs idempotent `alembic upgrade head` because Render's separate pre-deploy command is a paid-service feature.

### Netlify frontend

Create/connect a Netlify Free site from this repository. `netlify.toml` fixes the build base to `frontend`, uses the frozen pnpm lockfile, publishes `dist`, and includes the SPA fallback/security headers.

Set these build-time values in Netlify's environment UI:

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_PUBLISHABLE_KEY`

`VITE_API_URL=https://api.doobielogic.io` is intentionally versioned in `netlify.toml` because it is not a secret.

Attach `doobielogic.io` as the primary site domain and `ops.doobielogic.io` as a domain alias. Do not enable a paid plan or auto-recharge behavior.

## Remaining external prerequisite

### Production backup credential

`DATABASE_BACKUP_URL` is a GitHub Actions secret and is intentionally not readable or rewritable from application code. When the backup credential preflight reports rejected authentication, rotate this secret to the current production PostgreSQL/Supabase connection URI and rerun the backup/restore workflow.

## Merge discipline

A code-green PR is not the same as a functioning hosted release. Before DNS cutover:

- code, browser, container/security, zero-cost contract, and performance gates must be green;
- Render and Netlify must be connected on their free plans;
- required environment values must be configured without committing secrets;
- `api.doobielogic.io/health/ready` must report the deployed Git SHA and current schema; and
- the backup/restore proof must succeed after `DATABASE_BACKUP_URL` is rotated.

Under the zero-cost mandate, service suspension or cold start is preferable to an unexpected bill.
