# Web cutover evidence

Last updated: 2026-08-22

This file records evidence for `WEB_CUTOVER_GATES.md`. A passing repository or
local check does not authorize DNS cutover and does not replace production-clone
or pilot acceptance evidence.

## Proven in the current worktree

- Streamlit product parity: `MIGRATION_PARITY_TRACKER.md` is fully closed and
  `scripts/verify_streamlit_parity.py` is enforced by normal PR CI as well as the
  production Cloud Build path.
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
- Production API runtime boundary: the built API image starts with no Streamlit
  package installed/imported. The boundary check is part of `web-ci.yml`.
- Database worktree head is now `0037_function_acl_hardening`. A clean SQLite
  database upgrades through 0037, rolls back to 0036, and upgrades to head again
  in `test_web_infrastructure.py`.
- Facility authorization: a retail-only facility hides Production, Extraction,
  Package Studio, Plants and Production Product Master, and direct Production API
  access returns a structured `403` with a request ID.
- Facility context carries durable license metadata and independent retail,
  production, cultivation and commercial capabilities.
- Representative local parity previously passed all 22 direct-database versus
  live-API comparisons with zero mismatches through schema 0036. Schema 0037 is
  access-control-only and does not change operational table shape or calculations;
  the parity runner must still be repeated against the production-shaped clone.
- Supabase JWT verification requires configured issuer, audience, subject and
  expiry. The browser is designed to use Supabase Auth plus the tenant/facility-
  authorized FastAPI service, not direct operational PostgREST/GraphQL access.
- Original migration PR #260 passed its backend/frontend/container/security gates.
  PR #268 subsequently restored exact Streamlit product parity and merged only
  after repository CI and React/FastAPI gates both passed.

## Production Supabase read-only preflight — 2026-08-22

- The connected `DoobieLogic` Supabase project is `ACTIVE_HEALTHY` on PostgreSQL
  17 in `us-east-2`.
- The LIVE production database remains at
  `0036_supabase_data_api_hardening`. Schema 0037 exists only in the current PR
  until it is merged and then deliberately applied after the backup/restore gate.
- The Supabase migration ledger ending at `0029_dev_sandbox_ledger_reset` is a
  separate migration history; the application schema source of truth is Alembic.
- Every returned public application table has RLS enabled. Existing public tables
  currently grant no direct table privileges to `anon` or `authenticated`.
- A modern active Supabase publishable key exists for React. The legacy anon key
  remains active for compatibility but is not needed by the new React data path.
- `auth.users` currently contains zero users, proving the one-off legacy Auth
  import has not been executed.
- Six active durable `app_users` are ready for import and all six have portable
  bcrypt hashes. Three DEV accounts intentionally have no stored organization and
  bootstrap to DEV Sandbox; two buyer accounts are organization-scoped; one
  operator already has an explicit facility assignment.
- The earliest active facility is DEV Sandbox. Each current buyer/operator
  organization has exactly one active facility, so the current migration plan
  cannot accidentally broaden a non-DEV user across multiple operating sites.
- `backend/scripts/migrate_legacy_auth.py` now supports `--dry-run`, which builds
  and validates the full plan before the first external Auth mutation and reports
  aggregate counts only.

### ACL hardening finding

The production audit found an important gap beyond existing table grants:

- The existing public helper function `coman_prevent_inventory_ledger_mutation`
  is currently executable by `PUBLIC`, `anon`, and `authenticated` while LIVE
  production is still on 0036.
- PostgreSQL default ACLs for objects owned by the application migration role
  (`postgres`) no longer auto-grant future tables/sequences to browser roles, but
  future public functions can still inherit execute access on 0036.
- Supabase platform-managed defaults for objects created by `supabase_admin` still
  include browser-role grants for tables, sequences and functions.
- The application migration connection runs as `postgres` and is not a member of
  `supabase_admin`, so it cannot truthfully or safely rewrite another role's
  default ACLs.

Schema `0037_function_acl_hardening` therefore closes every path the application
migration role owns: it revokes existing public-function execution from `PUBLIC`,
`anon`, and `authenticated`, and revokes future postgres-owned default
table/sequence/function grants. The remaining platform-managed `supabase_admin`
path is handled by a separate required cutover control: disable the unused
Supabase Data API before public production cutover. Buyer Dash still uses Supabase
Auth; disabling the Data API does not remove Auth.

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
- FastAPI trial activation indirectly imported Streamlit. Trial license validation
  was split into a UI-independent service and the production API boundary passes.
- React Buyer Operations omitted the flagged SKU/batch drill-down and filtered AI
  Inventory Check. Both were restored using durable Buyer data and Doobie.
- Buying Recommendations and Extraction initially linked to the general Doobie
  page instead of generating workspace-specific briefs. Both now generate
  grounded briefs from active evidence.
- Data & Settings was initially admin-only even though Streamlit Data Hub was a
  normal licensed workspace. Operational publishing access was restored while
  archive and read-only permissions remain explicit.
- The legacy Supabase Auth migration had no non-mutating production preflight.
  `--dry-run` now validates all users and access-context decisions before the
  first Auth API call.
- Schema 0036 did not revoke public function execution and could not control
  `supabase_admin` default ACLs. Schema 0037 closes the app-owned gap, and the
  cutover contract now requires the unused Supabase Data API to be disabled.
- The initial 0037 revision name exceeded the deployed Alembic `varchar(32)`
  revision contract. The identifier was shortened to `0037_function_acl_hardening`
  before merge; no production migration had been run with the oversized value.

## Still required before public cutover

- Merge this hardening PR after all CI gates pass.
- Run and verify the encrypted production backup plus isolated restore drill
  immediately before any production schema/Auth changes.
- Apply Alembic `0037_function_acl_hardening` through the controlled one-shot
  production migration path, then verify `public.alembic_version` reports 0037.
- Verify no `PUBLIC`, `anon`, or `authenticated` execution remains on app-owned
  public functions and no direct browser table/sequence grants exist.
- Disable the Supabase Data API in project settings and verify operational data is
  reachable only through FastAPI while Supabase Auth remains functional.
- Run `python -m backend.scripts.migrate_legacy_auth --dry-run` from the production
  deployment environment. With the current database state it should plan six Auth
  creates and zero Auth refreshes; no execution may occur unless the plan matches
  the expected access contexts.
- Execute the legacy-user Auth import only after dry-run passes, then verify
  username/password sign-in, refresh, sign-out, recovery behavior, role/facility
  switching and DEV cross-company access.
- Run the full suite against a sanitized production PostgreSQL clone with real
  Supabase JWTs and representative roles/facilities/licenses.
- Configure/verify Google Secret Manager, deploy the zero-traffic Cloud Run
  candidate, and verify health, logs, retry behavior, tenant isolation and rollback
  without assigning production traffic.
- Deploy the Cloudflare Pages preview and repeat desktop/tablet/phone, scanning,
  accessibility, performance, upload/export and role/license checks.
- Obtain provider-issued DNS targets and configure `ops.doobielogic.io` and
  `api.doobielogic.io` at Spaceship only after pilot acceptance and a timed
  rollback rehearsal. Do not guess DNS values and do not retire Streamlit early.
