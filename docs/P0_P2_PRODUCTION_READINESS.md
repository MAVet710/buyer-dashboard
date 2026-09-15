# P0-P2 Production Readiness

This document records the active production-readiness contract after the local-first cutover. `docs/PROJECT_INVARIANTS.md`, the PC-hosted runtime configuration, and the release-validation workflows are the authoritative sources of truth.

## Active production architecture

DoobieLogic production is hosted from Nelson's Windows PC and exposed publicly through Cloudflare Tunnel.

The required request chain is:

`browser -> https://ops.doobielogic.io -> Cloudflare Tunnel -> Caddy 127.0.0.1:8080 -> FastAPI 127.0.0.1:8010 -> local Supabase Auth 127.0.0.1:54321`

- **Public operator URL:** `https://ops.doobielogic.io`.
- **Public edge:** Cloudflare HTTPS/Tunnel.
- **Web/reverse-proxy edge:** Caddy on loopback port `8080`.
- **API:** FastAPI on loopback port `8010`.
- **Auth:** local Supabase Auth gateway on loopback port `54321`.
- **Frontend API calls:** same-origin `/api/*` through `ops.doobielogic.io` in production.
- **Workstation service calls:** direct loopback to `http://127.0.0.1:8010` where appropriate.
- **AI:** local-only by default; cloud fallback remains disabled.
- **Cost policy:** the active runtime must not add a paid cloud deployment merely to improve availability.

Remote browsers must never be configured to call `127.0.0.1`; that address would refer to the remote user's computer. Caddy is responsible for forwarding public same-origin application requests to the correct local services.

## Retired hosting paths

The previous hosted deployment path is retired and must not be restored implicitly.

The repository guard requires these obsolete production-routing artifacts to remain absent:

- the retired hosted deployment blueprint;
- the old Cloudflare Worker origin proxy;
- the Worker's tests; and
- its Wrangler routing configuration.

Operational code and workflows are also checked for obsolete hosted origins, provider-specific runtime environment variables, and the old automatic hosted-deployment trigger.

Any intentional future architecture change must first update `docs/PROJECT_INVARIANTS.md`, the release workflows, and `scripts/verify_zero_cost_deployment.py` in the same reviewed change.

## Release gates

### Main release validation

`.github/workflows/deploy.yml` is a validation gate. It does **not** deploy production to an external host.

It:

1. enforces the PC-hosted zero-cost contract;
2. verifies release parity;
3. builds the API image in CI;
4. verifies exactly one Alembic head;
5. proves the production application can initialize with the expected security configuration; and
6. records the required public-to-local runtime chain.

After checks pass, the workstation remains the production origin. Updating the running workstation is a local operational action, not an automatic handoff to a cloud application host.

### Release candidate

`.github/workflows/rc-preview.yml` remains local/synthetic. It builds the API and frontend, runs them inside a constrained CI envelope, and performs smoke checks without creating external preview infrastructure.

The resource limits in that workflow are CI stress constraints, not a contract with any particular hosting provider.

## Authentication and Supabase

The backend and frontend must use the same intended Supabase identity domain.

For the active workstation runtime:

- FastAPI uses the configured local Supabase URL, normally `http://127.0.0.1:54321`.
- Normal password authentication uses the publishable/anon client key, not a service-role credential.
- The durable DoobieLogic `app_users` row and the linked Supabase Auth identity must share the same UUID.
- `God` remains a durable DoobieLogic username and resolves through `POST /api/v1/account/username-login`.
- A username-login failure must be traced through Cloudflare -> Caddy -> FastAPI -> local Supabase before identities are recreated or relinked.

The production frontend should use same-origin API calls. Its Supabase browser URL must be a public route that Caddy/Tunnel can proxy to the local Auth gateway; it must not expose a workstation loopback address to remote browsers.

## Database runtime contract

`DATABASE_URL` must identify the durable application database intended for the active local stack. The API never silently invents a production database when the configured database is missing.

The SQLAlchemy connection pool remains bounded so application traffic cannot exhaust the available PostgreSQL/Supabase connection budget. Pool sizing is controlled through:

- `DATABASE_POOL_SIZE`
- `DATABASE_MAX_OVERFLOW`
- `DATABASE_POOL_TIMEOUT`

Schema changes remain explicit administrative actions. Production readiness should fail closed when the running code and expected schema are incompatible.

## Backup and restore proof

`.github/workflows/database-backup.yml` retains the dedicated backup-role design and encrypted artifact process.

Every backup run must:

1. validate backup configuration;
2. derive/use the dedicated backup credential without committing it;
3. authenticate before creating an artifact;
4. create the intended schema/data dump;
5. restore into an isolated PostgreSQL service;
6. verify the restored schema/Alembic state;
7. encrypt the dump;
8. generate a checksum;
9. retain only encrypted evidence; and
10. remove plaintext runner files.

The backup workflow remains separate from application hosting and must not become a mechanism for changing the production runtime architecture.

## Frontend and performance correctness

- React CI requires zero ESLint warnings.
- Hook dependency warnings are correctness signals rather than globally suppressed.
- Admin edit forms preserve unsaved operator input across same-record background refetches.
- Playwright remains lockfile-controlled; CI must not mutate the dependency graph during runs.
- Production API calls from the browser must remain same-origin unless an intentional, reviewed architecture change says otherwise.

## MA Metrc sandbox

`.github/workflows/ma-metrc-sandbox-readonly.yml` performs authenticated **read-only** validation and emits redacted evidence.

Automatic validation must never perform provider mutations. Controlled MA sandbox mutation evaluation remains a separate explicitly approved action.

Do not claim Metrc provider validation has passed until live provider evidence proves the literal workbook requirement.

## Public health and latency checks

Public health/performance checks should use the active public operator edge so they exercise the real production chain into the workstation. They must not depend on a retired cloud origin.

A health check is useful only when it confirms the expected application/schema state behind the active tunnel. A DNS response alone does not prove the workstation origin is healthy.

## Local AI audit

`.github/workflows/ai-runtime-revision-guard.yml` verifies that the API remains local-only by default and cannot silently fall back to paid cloud AI.

Optional workstation model configuration may be declared separately, but it must remain compatible with the local-first runtime contract.

## Controlled database mutations

`seed-cowboy-kush-demo.yml` and `reset-dev-sandbox-vertical-inventory.yml` validate definitions automatically but require explicit manual dispatch, exact approval phrases, and server-side credentials before any database mutation. Normal push-triggered validation remains non-mutating.

## Storefront aliases

`.github/workflows/storefront-domain-mappings.yml` is validation-only. Approved aliases belong to the Cloudflare Tunnel -> PC-hosted Caddy routing model and the React storefront host boundary. The workflow does not create DNS or hosting resources.

## Transactional email

Transactional email credentials remain server-side. Resend HTTPS and Spacemail SMTP/IMAP may be used according to configured application policy, but neither transport defines the application hosting architecture.

No mail credential may be committed to the repository or exposed to the browser.

## Merge discipline

Before a production-facing runtime change is merged:

- parity, browser, security, local-runtime, and relevant integration gates must be green;
- `ops.doobielogic.io` must remain the public operator URL unless Nelson explicitly changes it;
- the workstation request chain must remain Cloudflare Tunnel -> Caddy :8080 -> FastAPI :8010 -> local Supabase Auth :54321;
- production frontend API calls must remain safe for remote users;
- required secrets must remain out of source; and
- `scripts/verify_zero_cost_deployment.py` must reject any accidental reintroduction of the retired hosted deployment path.

If the workstation or tunnel is unavailable, loss of availability is preferable to silently switching production to an unapproved paid or hosted fallback.
