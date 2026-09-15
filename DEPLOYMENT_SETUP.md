# DoobieLogic Production Runtime

DoobieLogic production is **PC-hosted**. `https://ops.doobielogic.io` is the public operator URL and Cloudflare Tunnel carries traffic to the Windows workstation.

## Authoritative request chain

`browser -> https://ops.doobielogic.io -> Cloudflare Tunnel -> Caddy 127.0.0.1:8080 -> FastAPI 127.0.0.1:8010 -> local Supabase Auth 127.0.0.1:54321`

Caddy is the only public-facing application edge on the workstation. It serves the built React frontend and reverse-proxies `/api/*` to FastAPI. Required browser-facing Supabase Auth traffic is also proxied through the public edge to the local Supabase gateway.

## Required local services

- Caddy: `127.0.0.1:8080`
- FastAPI: `127.0.0.1:8010`
- local Supabase gateway/Auth: `127.0.0.1:54321`
- public operator app: `https://ops.doobielogic.io`

FastAPI should be started with the canonical application module used by the current local stack. Do not introduce a second hosted API process to work around a local failure.

## Frontend production configuration

The public frontend must use same-origin API requests:

```text
VITE_API_URL=
VITE_SUPABASE_URL=https://ops.doobielogic.io
VITE_SUPABASE_PUBLISHABLE_KEY=<normal client publishable/anon key>
```

Do **not** build the public frontend with `VITE_API_URL=http://127.0.0.1:8010`; a remote browser would interpret that address as its own device.

## Backend configuration

Use `deploy/api.env.example` as the template. The active backend points at the local Supabase stack, including:

```text
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_JWKS_URL=http://127.0.0.1:54321/auth/v1/.well-known/jwks.json
CORS_ORIGINS=https://ops.doobielogic.io
```

Keep database, encryption, mail, Metrc, and privileged Supabase credentials server-side. Normal sign-in must use the publishable/anon client key rather than requiring a service-role key.

## GitHub Actions

`.github/workflows/deploy.yml` is a **validation gate**, not a cloud deployment job. It verifies the application build and local-first production contract. Passing the workflow does not move production to an external host.

`scripts/verify_zero_cost_deployment.py` fails closed if retired hosted deployment artifacts or origins are reintroduced.

## Cloudflare

Cloudflare must route `ops.doobielogic.io` to the tunnel connected to the workstation Caddy edge. Do not point the operator hostname at a separate hosted frontend or API origin.

## Health checks

Public runtime checks should exercise the real operator path:

```text
https://ops.doobielogic.io/health/ready
```

That verifies the public Cloudflare-to-PC chain rather than a retired or alternate API origin.

## Authentication invariant

`God` is a durable DoobieLogic username. Username login resolves the `app_users` row and authenticates the linked Supabase identity. The durable user UUID and Supabase Auth UUID must match.

A login failure must be traced in this order:

`browser -> Cloudflare Tunnel -> Caddy -> FastAPI /api/v1/account/username-login -> local Supabase Auth -> linked identity`

Do not recreate the user merely because login fails.

## Architecture changes

Any intentional change away from this topology must update all of the following in the same reviewed change:

- `docs/PROJECT_INVARIANTS.md`
- `DEPLOYMENT_SETUP.md`
- `docs/P0_P2_PRODUCTION_READINESS.md`
- `scripts/verify_zero_cost_deployment.py`
- release/runtime regression tests

Until then, the PC-hosted topology above is the production contract.
