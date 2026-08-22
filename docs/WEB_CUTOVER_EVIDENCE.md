# Web cutover evidence

Last updated: 2026-08-22

This file records evidence for `WEB_CUTOVER_GATES.md`. A passing repository or
local check does not authorize DNS cutover and does not replace production-clone
or pilot acceptance evidence.

## Proven in the current worktree

- Streamlit product parity: `MIGRATION_PARITY_TRACKER.md` is fully closed and
  `scripts/verify_streamlit_parity.py` is now enforced by normal PR CI as well as
  the production Cloud Build path.
- Auth parity: Supabase login preserves legacy username/password behavior,
  first-password-change state, role/facility authorization, DEV cross-company
  access, and a signed 24-hour trial session restricted to `dev-sandbox`.
- Trial validation is UI-independent: the FastAPI trial route reads the encrypted
  platform Doobie integration directly and does not import Streamlit.
- Buyer Operations parity: original category/size/strain classification rules,
  synthetic 28g flower and 500mg edible calculations, DOH/reorder behavior,
  category DOS, forecast, product rows, SKU views, Excel exports, Reorder ASAP
  SKU/batch drill-downs, and filtered Doobie Inventory Check are present in React.
- Buyer Intelligence parity: deterministic Buy First, SKU risk, overstock/slow
  watch and category risk remain visible; a real Doobie Buyer Brief operates over
  the same current Buyer evidence.
- Purchase Order parity: manual PO entry, Reorder ASAP bulk-add, smart purchasing
  evidence, inventory cross-check, editable lines, tax/discount/shipping totals,
  vendor/store metadata and PDF generation are restored.
- Compliance parity: reviewed-source upload, template download, grounded Q&A and
  citation display are restored; publication is role-gated to DEV/admin/QA/
  supervisor while normal users retain query/template access.
- Extraction parity: the six Streamlit operating areas are restored, including
  manual run/toll entry and a grounded Doobie Ops Brief over current run evidence.
- Data Hub parity: durable facility-scoped payloads are fingerprinted, versioned
  and persisted in SQL with import history and publisher identity. Buyers,
  planners, supervisors, operators, QA, DEV and sandbox trial users may publish;
  `read_only` remains read-only and archive is elevated.
- Backend suite: the migration branch is exercised on Python 3.12, including the
  durable SQL/API parity tests and restored parity regression tests.
- Frontend: TypeScript, ESLint, Vitest, and the Vite production build pass on the
  parity branch.
- Production API runtime boundary: the built API image starts with no Streamlit
  package installed/imported. The boundary check is part of `web-ci.yml`.
- Database: a brand-new SQLite database upgrades from base through
  `0036_supabase_data_api_hardening`, downgrades to
  `0035_facility_capabilities`, and upgrades back to head. The cycle is covered
  by `test_web_infrastructure.py`.
- Desktop browser: all 15 original migration React workspaces load against a fully
  migrated, production-shaped demo database with successful API responses and no
  browser console errors.
- Phone browser (390 x 844): the navigation drawer opens and closes, both Product
  Master scopes are reachable when licensed, populated Production Product Master
  has no page-level horizontal overflow, and the drawer remains keyboard-dismissible.
- Facility authorization: a retail-only facility shows only the Retail Product
  Master and Retail Inventory; Production, Extraction, Package Studio, Plants,
  and Production Product Master are hidden. Direct access to the Production API
  returns a structured `403` with a request ID.
- Facility context carries durable license metadata and independent retail,
  production, cultivation, and commercial capabilities. Cultivation/Plants is
  optional and enforced by both API and UI.
- Representative local parity: `scripts/web_parity_check.py` passed all 22
  direct-database versus live-API comparisons with zero mismatches against a
  clean database migrated through `0036_supabase_data_api_hardening`. The checks
  cover account capabilities, both Product Master scopes, both inventory scopes,
  audits, retail sales, production orders, extraction, Package Studio, commercial
  orders, and Data Hub history.
- Supabase boundary: JWT verification requires the configured project issuer,
  audience, subject, and expiry. Operational tables have RLS enabled and direct
  Data API privileges are revoked from `anon` and `authenticated`; the browser
  must use the tenant- and facility-authorized FastAPI service.
- Original migration PR #260 passed its required backend, frontend, container and
  vulnerability checks before merge. PR #268 subsequently restored exact product
  parity and merged after its final repository CI and React/FastAPI gates passed.

## Production Supabase read-only preflight — 2026-08-22

- The connected `DoobieLogic` Supabase project is `ACTIVE_HEALTHY` on PostgreSQL
  17 in `us-east-2`.
- `public.alembic_version` is exactly `0036_supabase_data_api_hardening`. The
  Supabase migration ledger ending at `0029_dev_sandbox_ledger_reset` is a
  separate migration history and does not indicate schema drift; Alembic is the
  application schema source of truth for revisions 0030-0036.
- Every public application table returned by the project inspection has RLS
  enabled. `anon` and `authenticated` currently have zero direct table grants in
  `public`, matching the FastAPI-only Data API boundary. Supabase Advisor reports
  informational `rls_enabled_no_policy` notices because these internal tables are
  intentionally not granted to browser roles.
- A modern active Supabase publishable key exists for the React client. The legacy
  anon key remains active for compatibility but is not required by the new browser
  configuration.
- `auth.users` currently contains zero users, proving the one-off legacy-user Auth
  import has not yet been executed.
- Six durable active `app_users` are ready for import and all six have portable
  bcrypt hashes. Three DEV accounts intentionally have no stored organization and
  bootstrap to DEV Sandbox; two buyer accounts are organization-scoped; one
  operator already has an explicit facility assignment.
- The earliest active facility, used only as the DEV bootstrap context by the
  migration script, is DEV Sandbox. Each current buyer/operator organization has
  exactly one active facility, so the present import cannot accidentally grant a
  non-DEV user access across multiple operating facilities.
- `backend/scripts/migrate_legacy_auth.py` now supports `--dry-run`. The dry run
  validates the complete account/context plan and existing Auth rows before any
  external mutation and logs aggregate counts only.

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
- FastAPI trial activation indirectly imported `services/doobie_config.py`, which
  imports Streamlit. Trial license validation was split into a UI-independent
  service and the production API image boundary now passes.
- React Buyer Operations omitted the original flagged SKU/batch drill-down and
  filtered AI Inventory Check. Both were restored using the current durable Buyer
  model and Doobie.
- Buying Recommendations and Extraction initially linked to the general Doobie
  page instead of generating their original workspace-specific briefs. Both now
  generate grounded Doobie briefs from the active evidence.
- Data & Settings was initially admin-only in React even though Streamlit Data Hub
  was a normal licensed workspace. Operational publishing access was restored,
  with archive and read-only permissions kept explicit.
- The legacy Supabase Auth migration had no non-mutating production preflight.
  `--dry-run` now validates all users and access-context decisions before the
  first Auth API call.

## Still required before public cutover

- Run `python -m backend.scripts.migrate_legacy_auth --dry-run` from the production
  deployment environment with the production database URL. The dry-run must show
  the expected six-user create plan before execution.
- Run the same suite against a sanitized production PostgreSQL clone with real
  Supabase JWTs, representative roles, facilities, and licenses.
- Execute the legacy-user Supabase Auth import only after the dry-run passes, then
  verify username/password sign-in, token refresh, sign-out, recovery behavior,
  role/facility switching and DEV cross-company access through the configured
  production project.
- Run/verify an encrypted production database backup and restore drill immediately
  before any production migration/candidate deployment.
- Configure/verify Google Secret Manager, deploy the zero-traffic Cloud Run
  candidate revision, and verify health, logs, retry behavior, backups, restore,
  tenant isolation and rollback without assigning production traffic.
- Deploy the Cloudflare Pages preview and repeat desktop/tablet/phone, scanning,
  accessibility, performance, upload/export and role/license checks on preview URLs.
- Obtain provider-issued DNS targets, then configure `ops.doobielogic.io` and
  `api.doobielogic.io` at Spaceship. Do not guess DNS values.
- Repeat the 22-check parity runner against the sanitized production PostgreSQL
  clone, then complete pilot-facility acceptance and a timed rollback rehearsal
  before changing production DNS or retiring Streamlit.
