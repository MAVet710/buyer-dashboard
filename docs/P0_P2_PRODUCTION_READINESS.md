# P0-P2 Production Readiness

This document records the operational contract introduced by the P0-P2 hardening pass. It is intentionally concise: the workflows remain the executable source of truth.

## Release gates

### Backup and restore proof

`.github/workflows/database-backup.yml` must be able to:

1. validate the configured PostgreSQL backup URI without printing credentials;
2. authenticate to the production database before creating an artifact;
3. create a consistent custom-format PostgreSQL dump;
4. restore the dump into an isolated PostgreSQL service;
5. verify exactly one Alembic revision and read the restored schema head;
6. encrypt and checksum the backup; and
7. retain only the encrypted artifact and checksum.

The workflow runs on schedule, manually, and after a successful production deployment. A stale or rejected `DATABASE_BACKUP_URL` is a release-operations failure and must be rotated outside application source control.

### Frontend correctness

The React CI contract requires zero ESLint warnings. Hook dependency warnings are treated as correctness signals rather than suppressed globally. Admin edit forms must preserve unsaved operator input across same-record background query refetches while still synchronizing when the selected record actually changes.

### Realistic-volume performance

`.github/workflows/performance-contract.yml` runs the realistic-volume performance suite as a first-class PR and `main` gate. The existing test assertions define the bounded query, payload, lazy-hydration, and latency contract.

### MA Metrc sandbox

`.github/workflows/ma-metrc-sandbox-readonly.yml` performs an authenticated **read-only** MA sandbox Facilities validation after successful production deployments and on its weekday schedule. It emits only a redacted evidence summary.

Automatic validation must not perform provider mutations. Controlled MA sandbox mutation evaluation remains in the separate manual workflow and requires its explicit approval phrase.

### Post-deploy production latency

`.github/workflows/post-deploy-performance-smoke.yml` measures both:

- the exact Cloud Run service readiness path using Google workload identity; and
- the public `api.doobielogic.io` readiness path.

The direct readiness endpoint includes the production database/schema round trip. The workflow fails when the configured p95 limits are exceeded or schema readiness is not verified.

## CI efficiency contract

- The canonical CI workflow owns the complete backend regression suite.
- `web-ci.yml` owns focused FastAPI/web security and infrastructure checks rather than duplicating the full backend suite.
- Playwright is pinned in `frontend/package.json` and `frontend/pnpm-lock.yaml`; CI must not mutate the dependency graph with `--lockfile=false` installs.
- Browser jobs share the versioned Chromium cache but still run Playwright's dependency/browser installation command so missing system dependencies fail visibly.

## External infrastructure prerequisites

Application code must not bypass or conceal infrastructure failures.

### Google Cloud billing

Artifact Registry and Cloud Run release workflows require billing to be enabled for the configured `GCP_PROJECT_ID`. If Artifact Registry reports that billing is disabled, do not weaken the RC or production workflow. Restore the billing account/project linkage and rerun the release candidate workflow before merging a release intended for immediate production deployment.

### Production backup credential

`DATABASE_BACKUP_URL` is a GitHub Actions secret and is intentionally not readable or rewritable from application code. When the backup credential preflight reports rejected authentication, rotate this secret to the current production PostgreSQL/Supabase connection URI and rerun the backup/restore workflow.

## Merge discipline

A code-green PR is not the same as a deployable release. Before production cutover:

- code, browser, container/security, and performance gates must be green;
- the RC image must be pushable to the configured Artifact Registry;
- external infrastructure blockers must be cleared; and
- after deployment, the performance smoke, MA Metrc read-only validation, and backup/restore proof must complete successfully.
