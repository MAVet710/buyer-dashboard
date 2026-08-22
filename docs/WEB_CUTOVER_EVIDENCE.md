# Web cutover evidence

Last updated: 2026-08-21

This file records evidence for `WEB_CUTOVER_GATES.md`. A passing local check
does not authorize DNS cutover and does not replace production-clone or pilot
acceptance evidence.

## Proven in the current worktree

- Backend suite: `770 passed` on Python 3.12, including the durable SQL/API
  parity test.
- Frontend: TypeScript, ESLint, 2 Vitest tests, and the Vite production build pass.
- Database: a brand-new SQLite database upgrades from base through
  `0036_supabase_data_api_hardening`, downgrades to
  `0035_facility_capabilities`, and upgrades
  back to head. The cycle is covered by `test_web_infrastructure.py`.
- Desktop browser: all 15 React workspaces load against a fully migrated,
  production-shaped demo database with successful API responses and no browser
  console errors.
- Phone browser (390 x 844): the navigation drawer opens and closes, both
  Product Master scopes are reachable when licensed, populated Production
  Product Master has no page-level horizontal overflow, and the drawer remains
  keyboard-dismissible.
- Facility authorization: a retail-only facility shows only the Retail Product
  Master and Retail Inventory; Production, Extraction, Package Studio, Plants,
  and Production Product Master are hidden. Direct access to the Production API
  returns a structured `403` with a request ID.
- Facility context now carries durable license metadata and independent retail,
  production, cultivation, and commercial capabilities. Cultivation/Plants is
  optional and enforced by both API and UI.
- Representative local parity: `scripts/web_parity_check.py` passed all 22
  direct-database versus live-API comparisons with zero mismatches against a
  clean database migrated through `0036_supabase_data_api_hardening`. The comparisons
  cover account capabilities, both Product Master scopes, both inventory
  scopes, audits, retail sales, production orders, extraction, Package Studio,
  commercial orders, and Data Hub history.
- Supabase boundary: JWT verification requires the configured project issuer,
  audience, subject, and expiry. Operational tables have RLS enabled and direct
  Data API privileges are revoked from `anon` and `authenticated`; the browser
  must use the tenant- and facility-authorized FastAPI service.
- GitHub PR #260: all eight required checks pass on the published branch,
  including both backend suites, the merged repository suite, React lint/test/
  build, both API and frontend container builds and high/critical vulnerability
  scans, and the Python 3.13 Streamlit fallback startup check. The API runtime
  contains patched OS packages and no package installer; the frontend uses the
  digest-pinned `nginx:1.31.4-alpine` runtime.

## Defects found and fixed during the gate

- Retail-to-Production Product Master navigation retained the Retail scope.
- The phone navigation button did not open any navigation.
- Integrations and Admin were unreachable on short desktop viewports.
- Populated Product Master overflowed the phone viewport.
- Alembic revision 0014 used an invalid parameterized execute signature.
- Revision 0001 created the current entire ORM schema and collided with later
  migrations on clean installs.
- Several later migrations ran PostgreSQL RLS SQL on SQLite without a dialect
  guard.
- The initial browser fixture had not been migrated and produced hidden API
  errors; the browser gate was invalidated and repeated against a fully migrated
  database.

## Still required before public cutover

- Run the same suite against a sanitized production PostgreSQL clone with real
  Supabase JWTs, RLS policies, representative roles, facilities, and licenses.
- Verify invitation, sign-in, refresh, sign-out, and password recovery through
  the configured production Supabase project.
- Configure Google Secret Manager, deploy the zero-traffic Cloud Run revision,
  and verify health, logs, retry behavior, backups, restore, and rollback.
- Deploy the Cloudflare Pages preview and repeat desktop/tablet/phone, scanning,
  accessibility, performance, and upload/export checks on the preview URLs.
- Obtain provider-issued DNS targets, then configure `ops.doobielogic.io` and
  `api.doobielogic.io` at Spaceship. Do not guess DNS values.
- Repeat the 22-check parity runner against a sanitized production PostgreSQL
  clone, then complete pilot-facility acceptance and a timed rollback rehearsal
  before changing production DNS.
