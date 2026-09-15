# DoobieLogic Production Runtime

DoobieLogic application compute is **PC-hosted**. `https://ops.doobielogic.io` is the public operator URL and Cloudflare Tunnel carries application traffic to the Windows workstation.

Durable production auth/data remain on the existing hosted DoobieLogic Supabase project.

## Authoritative request chain

Application traffic:

`browser -> https://ops.doobielogic.io -> Cloudflare Tunnel -> Caddy 127.0.0.1:8080 -> FastAPI 127.0.0.1:8010`

Authentication/data authority:

`browser/FastAPI -> https://fovxtygwcxubjzjgovva.supabase.co`

Caddy serves the built React frontend and reverse-proxies `/api/*` to FastAPI. Supabase Auth is **not** moved onto the workstation merely because FastAPI is hosted there.

## Required local services

- Caddy: `127.0.0.1:8080`
- FastAPI: `127.0.0.1:8010`
- public operator app: `https://ops.doobielogic.io`

The existing DoobieLogic Supabase project remains the production Auth/database authority.

## Frontend production configuration

The public frontend must use same-origin DoobieLogic API requests while talking directly to the existing Supabase project for Auth/session operations:

```text
VITE_API_URL=
VITE_SUPABASE_URL=https://fovxtygwcxubjzjgovva.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=<enabled client publishable/anon key from this project>
```

Do **not** build the public frontend with `VITE_API_URL=http://127.0.0.1:8010`; a remote browser would interpret that address as its own device.

Do **not** set `VITE_SUPABASE_URL=https://ops.doobielogic.io`; the application origin and Supabase Auth origin are separate.

## Backend configuration

Use `deploy/api.env.example` as the template. The active PC backend must point to the same existing Supabase project as the browser:

```text
SUPABASE_URL=https://fovxtygwcxubjzjgovva.supabase.co
SUPABASE_JWKS_URL=https://fovxtygwcxubjzjgovva.supabase.co/auth/v1/.well-known/jwks.json
SUPABASE_PUBLISHABLE_KEY=<enabled client publishable/anon key from this project>
CORS_ORIGINS=https://ops.doobielogic.io
```

`DATABASE_URL` / `COMAN_DATABASE_URL` must remain the durable PostgreSQL connection for the DoobieLogic Supabase project. Keep database, encryption, mail, Metrc, and privileged Supabase credentials server-side.

Normal sign-in uses the publishable/anon client key. A service-role key is not a baseline requirement for username/password login.

## GitHub Actions

`.github/workflows/deploy.yml` is a **validation gate**, not a cloud application deployment job. It verifies the PC-hosted application build plus the hosted-Supabase auth contract.

`scripts/verify_zero_cost_deployment.py` fails closed if retired application hosting paths are reintroduced or if production auth is accidentally pointed at a fresh local Supabase instance.

## Cloudflare

Cloudflare routes `ops.doobielogic.io` to the tunnel connected to the workstation Caddy edge. Do not point the operator hostname at a separate hosted frontend or API origin.

Cloudflare does not replace the Supabase project URL for Auth.

## Health checks

Public runtime checks should exercise the real operator application path:

```text
https://ops.doobielogic.io/health/ready
```

That verifies the public Cloudflare-to-PC application chain. Supabase project health is a separate dependency.

## Authentication invariant

`God` is a durable DoobieLogic username. Username login resolves the `app_users` row and authenticates the linked identity in the existing hosted Supabase project. The durable user UUID and Supabase Auth UUID must match.

A login failure must be traced in this order:

`browser -> Cloudflare Tunnel -> Caddy -> FastAPI /api/v1/account/username-login -> https://fovxtygwcxubjzjgovva.supabase.co/auth/v1 -> linked identity`

Before resetting a password or recreating a user, verify that:

- FastAPI `SUPABASE_URL` is the existing DoobieLogic project URL;
- the frontend `VITE_SUPABASE_URL` is the same project URL;
- both use an enabled publishable/anon client key for that project; and
- the durable `app_users.id` matches `auth.users.id`.

Do not recreate the user merely because login fails.

## Architecture changes

Any intentional change away from this topology must update all of the following in the same reviewed change:

- `docs/PROJECT_INVARIANTS.md`
- `DEPLOYMENT_SETUP.md`
- `docs/P0_P2_PRODUCTION_READINESS.md`
- `scripts/verify_zero_cost_deployment.py`
- release/runtime regression tests

Until then, application compute stays PC-hosted and durable auth/data stay on the existing DoobieLogic Supabase project.
