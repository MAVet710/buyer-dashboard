# P0-P2 Production Readiness

This document records the operational contract introduced by the P0-P2 hardening pass. The workflows and deployment configuration remain the executable source of truth.

## Zero-cost hosting contract

DoobieLogic's hosted beta must not require a paid cloud account or silently fall back to a billable service.

- **Frontend:** Netlify Free static hosting for the React/Vite bundle.
- **Frontend domains:** `doobielogic.io` is the primary domain and `ops.doobielogic.io` is a domain alias.
- **Storefront aliases:** exact approved first-level hosts from `deploy/storefront-domains.txt`, currently including `cowboykush.doobielogic.io`, are attached to the same Netlify site. React already maps non-reserved first-level DoobieLogic hosts to storefront slugs.
- **API:** Render Free web service defined by `render.yaml`.
- **API domain:** `api.doobielogic.io`.
- **Auth/data:** existing Supabase project and connection limits remain authoritative.
- **AI:** production hosting defaults to `AI_PROVIDER_MODE=disabled` and `AI_ALLOW_CLOUD_FALLBACK=false`; workstation Local AI remains decoupled from hosted compute.
- **Google Cloud:** no GitHub Actions workflow may authenticate to or create Google Cloud resources.

`python scripts/verify_zero_cost_deployment.py` is the fail-closed contract check. It scans every GitHub Actions workflow for Google control-plane/registry wiring, validates the free Render/Netlify configuration, and verifies that database mutation workflows remain explicitly gated.

### Free-tier failure behavior

Zero-cost is more important than uninterrupted hosting. Do not add a payment method or enable an automatic paid upgrade merely to prevent suspension.

Netlify Free uses a hard monthly usage limit. If the free allowance is exhausted, the site may pause instead of generating an overage charge.

Render's API must remain on `plan: free`. A free Render service can sleep after idle time and cold starts are expected. The performance smoke therefore measures wake-up separately from warm p95 latency. This mode is appropriate for beta/low-volume use, not a paid-SLA replacement for 24/7 facility infrastructure.

## Release gates

### Main release handoff

`.github/workflows/deploy.yml` is a release gate, not a cloud provisioning workflow. It:

1. enforces the zero-cost hosting contract;
2. verifies release parity;
3. builds the exact API Docker image locally;
4. verifies exactly one Alembic head; and
5. proves the production API configuration can initialize with cloud AI disabled.

After repository checks pass, connected Netlify and Render Git integrations deploy `main`. The workflow must not authenticate to a billable cloud control plane, push to a paid registry, or create cloud compute resources.

### Release candidate

`.github/workflows/rc-preview.yml` is intentionally local/synthetic. It builds the API image and frontend, proves the API can initialize inside the Render Free 512 MB / 0.1 CPU envelope, starts a synthetic API container and local Vite preview, then verifies account context and seeded inventory behavior. It must not create external preview infrastructure.

### Backup and restore proof

`.github/workflows/database-backup.yml` must:

1. validate the configured PostgreSQL backup URI without printing credentials;
2. authenticate before creating an artifact;
3. create a consistent custom-format PostgreSQL dump;
4. restore into an isolated PostgreSQL service;
5. verify exactly one Alembic revision and read the restored schema head;
6. encrypt and checksum the backup; and
7. retain only the encrypted artifact and checksum.

The workflow runs on schedule, manually, and after a successful `main` release gate. A stale or rejected `DATABASE_BACKUP_URL` must be rotated outside source control.

### Frontend correctness

The React CI contract requires zero ESLint warnings. Hook dependency warnings are treated as correctness signals rather than suppressed globally. Admin edit forms must preserve unsaved operator input across same-record background query refetches while still synchronizing when the selected record actually changes.

### Realistic-volume performance

`.github/workflows/performance-contract.yml` runs the realistic-volume performance suite as a first-class PR and `main` gate. Existing assertions define the bounded query, payload, lazy-hydration, and latency contract.

### MA Metrc sandbox

`.github/workflows/ma-metrc-sandbox-readonly.yml` performs an authenticated **read-only** MA sandbox Facilities validation after successful `main` release gates and on its weekday schedule. It emits only a redacted evidence summary.

Automatic validation must not perform provider mutations. Controlled MA sandbox mutation evaluation remains in the separate manual workflow and requires its explicit approval phrase.

### Hosted API latency

`.github/workflows/post-deploy-performance-smoke.yml` probes only `https://api.doobielogic.io/health/ready`. It uses no application password, database credential, or cloud identity token.

For a release-triggered run, the probe waits until Render reports the triggering Git commit in `release_sha` and verifies live schema readiness. Scheduled/manual checks measure a free-tier cold start separately; warm readiness samples then must satisfy the p95 budget.

## Zero-cost operational workflows

### Local AI audit

`.github/workflows/ai-runtime-revision-guard.yml` no longer inspects a Cloud Run revision. It validates that the hosted Render configuration cannot use paid cloud AI fallback and separately checks the optional workstation Local AI declaration.

### Cowboy Kush demo seed

`.github/workflows/seed-cowboy-kush-demo.yml` performs definition validation only on normal `main` pushes. A database write is allowed only by manual dispatch with the exact `I_APPROVE_COWBOY_KUSH_DEMO_SEED` phrase and a server-side `DL_PROD_DB_URL` GitHub secret. It dry-runs before applying.

### DEV Sandbox reset

`.github/workflows/reset-dev-sandbox-vertical-inventory.yml` performs definition validation only on normal `main` pushes. The destructive reset requires manual dispatch with exact `I_APPROVE_DEV_SANDBOX_RESET`, the `DL_PROD_DB_URL` secret, and a read-only dry run before apply. Audit events use a provider-neutral automation actor.

### Hosted storefront aliases

`.github/workflows/storefront-domain-mappings.yml` is validation-only. It validates exact approved storefront aliases and bounds the operating set conservatively to 50. It never creates DNS or hosting resources. Actual aliases are attached to the Netlify Free site during host setup.

## CI efficiency contract

- Canonical CI owns the complete backend regression suite.
- `web-ci.yml` owns focused FastAPI/web security and infrastructure checks rather than duplicating the full backend suite.
- Playwright is pinned in `frontend/package.json` and `frontend/pnpm-lock.yaml`; CI must not mutate the dependency graph with `--lockfile=false` installs.
- Browser jobs share the versioned Chromium cache.

## One-time free-host connection

### Render API

Create/connect a Render Blueprint from `render.yaml` on branch `main`. Keep the service on `free`. Provide these values in Render's secret/environment UI; never commit them:

- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_JWKS_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `INTEGRATION_ENCRYPTION_KEY`

Attach `api.doobielogic.io` and update DNS using Render's provided target. The Docker startup applies idempotent `alembic upgrade head` because a separate paid pre-deploy job is intentionally not required.

### Netlify frontend

Create/connect a Netlify Free site from this repository. `netlify.toml` uses the frozen pnpm lockfile, publishes `frontend/dist`, and contains the SPA fallback/security headers.

Set these public build-time values in Netlify's environment UI:

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_PUBLISHABLE_KEY`

`VITE_API_URL=https://api.doobielogic.io` is versioned because it is not secret.

Attach `doobielogic.io` as the primary domain, `ops.doobielogic.io` as an alias, and each validated storefront hostname from `deploy/storefront-domains.txt` as an additional alias. Do not enable a paid plan or paid overage behavior.

## Remaining external prerequisites

### Production backup credential

`DATABASE_BACKUP_URL` is intentionally not readable or rewritable from application code. Rotate it to the current production PostgreSQL/Supabase connection URI and rerun the backup/restore workflow.

### Explicit database operations credential

`DL_PROD_DB_URL` is required only for manually approved Cowboy Kush demo seed and DEV Sandbox reset jobs. It must not be exposed to push-triggered validation jobs. Prefer a purpose-scoped database role where practical.

## Merge discipline

Before DNS cutover:

- code, browser, container/security, zero-cost contract, local RC, and performance gates must be green;
- Render and Netlify must be connected on their free plans;
- required environment values must be configured without committing secrets;
- `api.doobielogic.io/health/ready` must report the deployed Git SHA and current schema; and
- the backup/restore proof must succeed after `DATABASE_BACKUP_URL` is rotated.

Under the zero-cost mandate, service suspension or cold start is preferable to an unexpected bill.
