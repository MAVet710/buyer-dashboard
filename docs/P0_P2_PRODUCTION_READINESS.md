# P0-P2 Production Readiness

This document records the operational contract introduced by the P0-P2 hardening pass. Workflows and `render.yaml` remain the executable source of truth.

## Zero-cost hosting contract

DoobieLogic's hosted beta must not require a paid cloud account or silently fall back to a billable service.

- **Frontend:** Render Static Site / CDN for the React/Vite bundle.
- **Frontend domains:** `doobielogic.io` is the primary domain and `ops.doobielogic.io` is an alias on the same static site.
- **Storefront aliases:** exact approved first-level hosts from `deploy/storefront-domains.txt` are attached to that same static site after validation.
- **API:** Render Free native-Python web service defined by `render.yaml`.
- **API domain:** `api.doobielogic.io`.
- **Auth/data:** existing Supabase Free project remains authoritative.
- **Transactional mail:** hosted production uses an HTTPS provider (`RESEND_API_KEY`). Spacemail SMTP/IMAP remains a local/legacy fallback because Render Free blocks standard SMTP egress ports.
- **AI:** hosted production defaults to `AI_PROVIDER_MODE=disabled` and `AI_ALLOW_CLOUD_FALLBACK=false`; workstation Local AI remains decoupled from hosted compute.
- **Google Cloud:** no permanent GitHub Actions workflow may authenticate to or create Google Cloud resources.

`python scripts/verify_zero_cost_deployment.py` is the fail-closed contract check. It scans every GitHub Actions workflow for Google control-plane/registry wiring, validates the free Render configuration, verifies HTTPS transactional-mail wiring, and confirms that database mutation workflows remain explicitly gated.

### Free-tier failure behavior

Zero-cost is more important than uninterrupted hosting. Do not add a payment method or enable an automatic paid upgrade merely to prevent suspension.

Render's API must remain on `plan: free`. Free web services can sleep after idle time and cold starts are expected. The performance smoke measures wake-up separately from warm p95 latency. The React static site does not consume free web-service instance hours.

Legacy Render web services should be suspended or deleted after cutover so stray traffic cannot consume the workspace's shared free web-service allowance.

## Release gates

### Main release handoff

`.github/workflows/deploy.yml` is a release gate, not a cloud provisioning workflow. It:

1. enforces the zero-cost hosting contract;
2. verifies release parity;
3. builds the exact API Docker image locally;
4. verifies exactly one Alembic head;
5. proves production API configuration can initialize with cloud AI disabled; and
6. verifies the Render handoff is check-gated and tied to exact Git commit identity.

After repository checks pass, Render's Git integration is the canonical deployment handoff. The workflow must not authenticate to a billable cloud control plane, push to a paid registry, or create cloud compute resources.

### Release candidate

`.github/workflows/rc-preview.yml` is intentionally local/synthetic. It builds the API image and frontend, proves the API can initialize inside the Render Free 512 MB / 0.1 CPU envelope, starts a synthetic API container and local static frontend, then runs smoke checks. It must not create external preview infrastructure.

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

### Database schema authority

The public Render API process does **not** run `alembic upgrade head`. The web runtime receives application DML authority only through its configured database credential and `/health/ready` fails closed if the live schema does not match the code's Alembic head.

Schema migrations are an explicit deployment/administrative action and must not be silently coupled to public web-process startup.

### Frontend correctness

React CI requires zero ESLint warnings. Hook dependency warnings are treated as correctness signals rather than globally suppressed. Admin edit forms preserve unsaved operator input across same-record background refetches while still synchronizing when the selected record actually changes.

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

`.github/workflows/ai-runtime-revision-guard.yml` validates that hosted Render configuration cannot use paid cloud AI fallback and separately checks the optional workstation Local AI declaration.

### Cowboy Kush demo seed

`.github/workflows/seed-cowboy-kush-demo.yml` performs definition validation only on normal `main` pushes. A database write is allowed only by manual dispatch with exact `I_APPROVE_COWBOY_KUSH_DEMO_SEED` and a server-side `DL_PROD_DB_URL` GitHub secret. It dry-runs before applying.

### DEV Sandbox reset

`.github/workflows/reset-dev-sandbox-vertical-inventory.yml` performs definition validation only on normal `main` pushes. The destructive reset requires manual dispatch with exact `I_APPROVE_DEV_SANDBOX_RESET`, the `DL_PROD_DB_URL` secret, and a read-only dry run before apply.

### Hosted storefront aliases

`.github/workflows/storefront-domain-mappings.yml` is validation-only. It validates exact approved storefront aliases and bounds the operating set conservatively to 50. It never creates DNS or hosting resources. Actual aliases are attached to the Render static site during host setup.

## CI efficiency contract

- Canonical CI owns the complete backend regression suite.
- `web-ci.yml` owns focused FastAPI/web security and infrastructure checks rather than duplicating the full backend suite.
- Playwright is pinned in `frontend/package.json` and `frontend/pnpm-lock.yaml`; CI must not mutate the dependency graph with `--lockfile=false` installs.
- Browser jobs share the versioned Chromium cache.

## One-time free-host connection

### Render API

Connect/apply `render.yaml` on branch `main` and keep the API service on `free`. Provide these protected values in Render; never commit them:

- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_JWKS_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `INTEGRATION_ENCRYPTION_KEY`
- `RESEND_API_KEY`

`SUPABASE_SERVICE_ROLE_KEY` is intentionally not a baseline runtime requirement. Normal authentication uses the publishable key; admin-only Supabase operations fail closed when a privileged key is absent.

Attach `api.doobielogic.io` only after the Render service reports `/health/ready` with `schema_matches=true` and the expected release SHA.

### Render static frontend

The second service in `render.yaml` builds with the frozen pnpm lockfile and publishes `frontend/dist`. It includes the SPA fallback, security headers, immutable asset caching, and an uncached `release.json` containing `RENDER_GIT_COMMIT`.

Provide these public build-time values through Render's environment configuration:

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_PUBLISHABLE_KEY`

`VITE_API_URL=https://api.doobielogic.io` is versioned because it is not secret.

Attach `doobielogic.io`, `ops.doobielogic.io`, and validated storefront aliases after the canonical API is healthy.

## Remaining protected credential handoffs

These values cannot be extracted or rewritten through application code and must remain in provider secret stores.

### Production API database credential

`DATABASE_URL` must be supplied directly to the Render API's protected environment. The repository intentionally contains no database password or reversible credential envelope.

### Production backup credential

`DATABASE_BACKUP_URL` must point to a current production PostgreSQL/Supabase connection URI before backup/restore proof can pass.

### Explicit database-operations credential

`DL_PROD_DB_URL` is required only for manually approved Cowboy Kush demo seed and DEV Sandbox reset jobs. It must not be exposed to normal push-triggered validation jobs.

### Transactional email credential

`RESEND_API_KEY` must be stored in Render's protected environment after the DoobieLogic sending domain is verified with the HTTPS mail provider. Do not route hosted mail through Spacemail SMTP on Render Free.

## Merge discipline

Before DNS cutover:

- code, browser, container/security, zero-cost contract, local RC, and performance gates must be green;
- the canonical Render static and API services must remain on free configuration;
- required protected environment values must be configured without committing secrets;
- `api.doobielogic.io/health/ready` must report the deployed Git SHA and current schema; and
- the backup/restore proof must succeed after `DATABASE_BACKUP_URL` is rotated.

Under the zero-cost mandate, service suspension or cold start is preferable to an unexpected bill.
