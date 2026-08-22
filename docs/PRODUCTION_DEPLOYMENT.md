# Buyer Dash production deployment

The production targets are `https://ops.doobielogic.io` and `https://api.doobielogic.io`. DNS is managed at Spaceship. Do not switch either record until the release candidate passes `docs/WEB_CUTOVER_GATES.md` against the production database clone.

## API

1. Create a Google Artifact Registry repository named `buyer-dash` in `us-east1`.
2. Create dedicated `buyer-dash-api` and `buyer-dash-migrate` service accounts. Grant each identity `roles/secretmanager.secretAccessor` only on the secrets used by its manifest: the migration identity receives only `buyer-dash-database-url`; the API identity receives the five required runtime secrets in `deploy/cloudbuild-api.yaml`. Grant the Cloud Build deployer `roles/iam.serviceAccountUser` on those two identities, not project-wide. Do not run either workload as the default Compute Engine service account. `METRC_INTEGRATOR_KEY` is optional; add its secret mapping only after a real integrator credential has been issued.
3. Back up the production database, then submit `deploy/cloudbuild-migrate.yaml`. It creates and waits for a one-shot Cloud Run job with retries disabled. Confirm the job reached Alembic `head` (currently `0037_supabase_function_acl_hardening`) before deploying the API. Never run schema migration concurrently in web containers. Revisions 0036-0037 enable RLS, revoke direct Data API table/sequence access from `anon` and `authenticated`, remove browser/PUBLIC execution from app-owned public functions, and revoke future app-owned default grants. Buyer Dash operational data remains available only through FastAPI.
4. Submit `deploy/cloudbuild-api.yaml`. It deploys a tagged `candidate` revision with `--no-traffic`; do not remove that flag for the first production-shaped verification.
5. Verify `/health`, `/health/ready`, authenticated tenant isolation, logs, and rollback against the candidate URL. Explicitly move traffic only after those checks pass.
6. Map `api.doobielogic.io` to the verified service and add the exact DNS record supplied by Google at Spaceship.

## React client

1. Configure Cloudflare Pages with root directory `frontend`, build command `pnpm build`, and output directory `dist`.
2. Set the three variables in `deploy/frontend.env.example`. Only the Supabase publishable key belongs in the browser.
3. Verify the preview deployment against the zero-traffic API revision.
4. Add `ops.doobielogic.io` as the Pages custom domain and copy the exact CNAME/verification record into Spaceship.

## Supabase

- Add `https://ops.doobielogic.io` as the Site URL and allowed redirect origin.
- Add password recovery and invitation redirect URLs under the same origin.
- Keep the service-role key only in Cloud Run Secret Manager.
- Disable the Supabase Data API before public cutover. Buyer Dash uses Supabase Auth in the browser but does not use direct PostgREST/GraphQL table access. This is required because Supabase-managed objects created by `supabase_admin` retain platform default grants that the application migration role cannot rewrite. Disabling the unused Data API removes that platform-managed exposure path while FastAPI remains the only operational data surface.
- Confirm `auth.users` contains the expected imported Buyer Dash users only after `python -m backend.scripts.migrate_legacy_auth --dry-run` passes in the production deployment environment. Then run the import once and verify username/password sign-in, refresh, sign-out, recovery behavior and facility switching before any traffic move.
- The DoobieLogic project currently remains on Supabase Free by owner decision. Configure `DATABASE_BACKUP_URL` and a unique 32+ character `DATABASE_BACKUP_ENCRYPTION_PASSPHRASE` as GitHub Actions secrets, then manually run `.github/workflows/database-backup.yml` before applying migrations. The workflow uses PostgreSQL 17 clients, creates a custom-format dump, restores it into an isolated PostgreSQL 17 service, verifies the Alembic revision row, encrypts the dump with AES-256, records a SHA-256 checksum, and retains only encrypted artifacts for 30 days.
- Confirm the scheduled backup succeeds daily and perform a documented manual decryption/restore drill before cutover. The encrypted archive contains the full database; the portable restore gate restores and validates the `public` Buyer Dash application schema so Supabase-managed extensions such as `supabase_vault` are not required in the isolated vanilla PostgreSQL target. This compensating control does not provide Supabase Pro uptime, non-pausing, point-in-time recovery, or support guarantees; reconsider Pro before customer-critical operation.

## DNS cutover

Lower TTL before the scheduled window. Confirm both provider-issued targets rather than guessing their values. After propagation, test TLS, auth recovery, facility switching, uploads, inventory write paths, and audit evidence from the public domains. Keep Streamlit available and unchanged until pilot acceptance and rollback rehearsal are complete.
